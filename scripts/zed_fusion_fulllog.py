#!/usr/bin/env python3
"""ZED-M 2대의 fused/raw 바디 전 필드와 LEFT 영상을 기록한다."""
import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time

import numpy as np
import pyzed.sl as sl

from zed_fusion_bodytrack import (
    _available_serials,
    _camera_identifier,
    _enum_text,
    _init_fusion,
    _open_sender,
    _read_config,
    _status_failed,
    _tolist,
)


COORD_NAME = "RIGHT_HANDED_Z_UP_X_FWD"
UNIT_NAME = "METER"
RAW_BODY_FORMAT_NAME = "BODY_18"
FUSED_BODY_FORMAT_NAME = "BODY_34"


def _finite_json(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _finite_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json(item) for item in value]
    try:
        return _finite_json(value.item())
    except Exception:
        return str(value)


def _array_value(value):
    if value is None:
        return None
    return _finite_json(_tolist(value))


def _timestamp_ns(bodies):
    try:
        return int(bodies.timestamp.get_nanoseconds())
    except Exception:
        return None


def _body_record(body, bodies, record_type, frame_idx, t_wall_ns=None, serial_number=None):
    keypoints_covariance = getattr(body, "keypoints_covariance", None)
    if keypoints_covariance is None:
        keypoints_covariance = getattr(body, "keypoint_covariances", None)

    body_format = FUSED_BODY_FORMAT_NAME if record_type == "fused" else RAW_BODY_FORMAT_NAME
    record = {
        "record": record_type,
        "t_sdk_ns": _timestamp_ns(bodies),
        "t_wall_ns": int(time.time_ns() if t_wall_ns is None else t_wall_ns),
        "is_new": bool(bodies.is_new),
        "is_tracked": bool(bodies.is_tracked),
        "body_format": body_format,
        "frame": "fusion_world" if record_type == "fused" else "camera",
        "frame_idx": frame_idx,
        "id": int(body.id),
        "unique_object_id": str(getattr(body, "unique_object_id", "")),
        "tracking_state": _enum_text(body.tracking_state),
        "action_state": _enum_text(body.action_state),
        "confidence": float(getattr(body, "confidence", 0.0)),
        "position": _array_value(getattr(body, "position", None)),
        "velocity": _array_value(getattr(body, "velocity", None)),
        "position_covariance": _array_value(getattr(body, "position_covariance", None)),
        "dimensions": _array_value(getattr(body, "dimensions", None)),
        "bounding_box": _array_value(getattr(body, "bounding_box", None)),
        "head_position": _array_value(getattr(body, "head_position", None)),
        "head_bounding_box": _array_value(getattr(body, "head_bounding_box", None)),
        "keypoint": _array_value(getattr(body, "keypoint", None)),
        "keypoint_confidence": _array_value(getattr(body, "keypoint_confidence", None)),
        "keypoints_covariance": _array_value(keypoints_covariance),
        "local_position_per_joint": _array_value(getattr(body, "local_position_per_joint", None)),
        "local_orientation_per_joint": _array_value(getattr(body, "local_orientation_per_joint", None)),
        "global_root_orientation": _array_value(getattr(body, "global_root_orientation", None)),
    }
    if record_type == "raw":
        record.update({
            "serial_number": int(serial_number),
            "keypoint_2d": _array_value(getattr(body, "keypoint_2d", None)),
            "bounding_box_2d": _array_value(getattr(body, "bounding_box_2d", None)),
            "head_bounding_box_2d": _array_value(getattr(body, "head_bounding_box_2d", None)),
        })
    return _finite_json(record)


def _metrics_record(metrics, frame_idx, t_sdk_ns, t_wall_ns):
    camera_stats = {}
    for identifier, stats in metrics.camera_individual_stats.items():
        serial = getattr(identifier, "serial_number", identifier)
        try:
            serial = str(int(serial))
        except Exception:
            serial = str(serial)
        camera_stats[serial] = {
            "delta_ts": float(stats.delta_ts),
            "is_present": bool(stats.is_present),
            "ratio_detection": float(stats.ratio_detection),
            "received_fps": float(stats.received_fps),
            "received_latency": float(stats.received_latency),
            "synced_latency": float(stats.synced_latency),
        }
    return _finite_json({
        "record": "metrics",
        "t_sdk_ns": t_sdk_ns,
        "t_wall_ns": int(t_wall_ns),
        "frame_idx": frame_idx,
        "mean_camera_fused": float(metrics.mean_camera_fused),
        "mean_stdev_between_camera": float(metrics.mean_stdev_between_camera),
        "camera_individual_stats": camera_stats,
    })


def _enable_svo(sender, directory, stamp):
    if not directory:
        sender["recording"] = False
        sender["svo_path"] = None
        return
    os.makedirs(directory, exist_ok=True)
    path = os.path.abspath(os.path.join(directory, "svo_%s_%s.svo2" % (sender["serial"], stamp)))
    params = sl.RecordingParameters(path, sl.SVO_COMPRESSION_MODE.H264)
    status = sender["camera"].enable_recording(params)
    if _status_failed(status, sl.ERROR_CODE.SUCCESS):
        sender["recording"] = False
        sender["svo_path"] = None
        print("warning: S/N %s SVO2 recording failed (%s); continuing" % (sender["serial"], status))
        return
    sender["recording"] = True
    sender["svo_path"] = path
    print("  S/N %s SVO2 -> %s" % (sender["serial"], path))


class _FfmpegH264Writer:
    def __init__(self, path, fps, size):
        self._process = None
        self._released = False
        self._broken_pipe = False
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", "%dx%d" % size, "-r", str(fps), "-i", "-",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
            "-movflags", "+faststart", path,
        ]
        try:
            self._process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError:
            self._process = None

    def isOpened(self):
        return (
            not self._released
            and self._process is not None
            and self._process.poll() is None
            and self._process.stdin is not None
        )

    def write(self, bgr):
        if self._broken_pipe or not self.isOpened():
            return
        try:
            self._process.stdin.write(np.ascontiguousarray(bgr).tobytes())
        except BrokenPipeError:
            self._broken_pipe = True
            print("warning: ffmpeg video pipe closed; camera video frames will be ignored")

    def release(self):
        if self._released:
            return
        self._released = True
        process = self._process
        if process is None:
            return

        if process.stdin is not None:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            process.stdin = None
        try:
            _, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate()
            print("warning: ffmpeg did not exit within 30 seconds and was terminated")
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[-2000:]
            print("warning: ffmpeg video writer exited with code %s: %s" % (
                process.returncode, detail or "no error output"))


def _open_video_writers(senders, outdir, stamp, fps, use_mp4v):
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError("video recording requires cv2: %s" % exc)

    videos = {}
    try:
        for sender in senders:
            serial = sender["serial"]
            info = sender["camera"].get_camera_information()
            resolution = info.camera_configuration.resolution
            size = (int(resolution.width), int(resolution.height))
            path = os.path.abspath(os.path.join(outdir, "fulllog_%s_cam%s.mp4" % (stamp, serial)))
            codec = "mp4v"
            if use_mp4v:
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
            else:
                writer = _FfmpegH264Writer(path, fps, size)
                if writer.isOpened():
                    codec = "h264"
                else:
                    writer.release()
                    print("warning: ffmpeg not found; falling back to cv2 mp4v "
                          "(MPEG-4 Part 2, limited player support)")
                    writer = cv2.VideoWriter(
                        path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
            if not writer.isOpened():
                writer.release()
                raise RuntimeError("could not open camera video writer: %s" % path)
            videos[serial] = {
                "path": path, "codec": codec, "writer": writer, "image": sl.Mat()}
    except Exception:
        for video in videos.values():
            video["writer"].release()
        raise
    return cv2, videos


def _write_video_frame(cv2, video, camera):
    status = camera.retrieve_image(video["image"], sl.VIEW.LEFT)
    if _status_failed(status, sl.ERROR_CODE.SUCCESS):
        raise RuntimeError("LEFT image retrieval failed: %s" % status)
    image = video["image"].get_data()
    if image is None or len(image.shape) != 3 or image.shape[2] != 4:
        raise RuntimeError("LEFT image is not BGRA")
    video["writer"].write(cv2.cvtColor(image, cv2.COLOR_BGRA2BGR))


def _write_record(log_file, record):
    log_file.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _parse_args():
    parser = argparse.ArgumentParser(description="Dual ZED-M Fusion full-field logger")
    parser.add_argument("--config", "--calib", dest="config", required=True,
                        help="ZED360/manual Fusion config JSON")
    parser.add_argument("--res", default="HD720", help="HD720 fixed for this two-ZED-M USB setup")
    parser.add_argument("--fps", type=int, default=30,
                        help="default 30; this rig cannot sustain 2xHD720@60")
    parser.add_argument("--depth", default="NEURAL", help="NEURAL | NEURAL_LIGHT | PERFORMANCE")
    parser.add_argument("--conf", type=int, default=40, help="sender detection_confidence_threshold")
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 = until Ctrl-C")
    parser.add_argument(
        "--outdir", default="logs",
        help="create <outdir>/fulllog_<stamp>/ for each run and save outputs there")
    parser.add_argument("--min-keypoints", type=int, default=7)
    parser.add_argument("--min-cameras", type=int, default=1)
    parser.add_argument("--smoothing", type=float, default=0.1)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--retry-wait", type=float, default=1.0)
    parser.add_argument("--verbose-fusion", action="store_true")
    parser.add_argument("--record-svo", metavar="DIR",
                        help="save per-camera H264 SVO2 files under DIR")
    parser.add_argument("--metrics-every", type=int, default=30, metavar="N",
                        help="write Fusion metrics every N processed frames (default: 30)")
    parser.add_argument("--no-raw", action="store_true", help="do not write per-camera raw body records")
    parser.add_argument("--no-video", action="store_true", help="do not save per-camera LEFT MP4 files")
    parser.add_argument(
        "--video-mp4v", action="store_true",
        help="use cv2 mp4v instead of ffmpeg H.264 (fallback encoder; limited player support)")
    args = parser.parse_args()
    if args.fps != 30:
        parser.error("Fusion on this hardware is fixed to 30 fps; got --fps %d" % args.fps)
    if args.metrics_every < 1:
        parser.error("--metrics-every must be >= 1")
    return args


def main():
    args = _parse_args()
    configs = _read_config(args.config)
    serials = [int(conf.serial_number) for conf in configs]
    print("config cameras:", serials)
    available = _available_serials()
    missing = [serial for serial in serials if serial not in available]
    if missing:
        print("warning: config cameras not currently AVAILABLE:", missing)
        print("         close ZED Studio/other camera clients before running.")

    senders = []
    fusion = None
    identifiers = []
    cv2 = None
    videos = {}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.abspath(os.path.join(args.outdir, "fulllog_%s" % stamp))
    os.makedirs(run_dir, exist_ok=True)
    log_path = os.path.abspath(os.path.join(run_dir, "fulllog_%s.jsonl" % stamp))
    meta_path = os.path.abspath(os.path.join(run_dir, "fulllog_%s_meta.json" % stamp))
    print("run dir ->", run_dir)

    try:
        for conf in configs:
            sender = _open_sender(conf, args.res, args.fps, args.depth, args.conf,
                                  args.retry_count, args.retry_wait)
            senders.append(sender)
            _enable_svo(sender, args.record_svo, stamp)

        # 첫 frame을 밀어 넣어 shared-memory sender가 Fusion subscribe 전에 준비되게 한다.
        warmup = sl.Bodies()
        for sender in senders:
            if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                sender["camera"].retrieve_bodies(warmup, sender["runtime"])

        fusion, identifiers = _init_fusion(configs, args.verbose_fusion)
        if not args.no_video:
            cv2, videos = _open_video_writers(
                senders, run_dir, stamp, args.fps, args.video_mp4v)
            for video in videos.values():
                print("camera video [%s] -> %s" % (video["codec"], video["path"]))

        runtime = sl.BodyTrackingFusionRuntimeParameters()
        runtime.skeleton_minimum_allowed_keypoints = int(args.min_keypoints)
        runtime.skeleton_minimum_allowed_camera = int(args.min_cameras)
        runtime.skeleton_smoothing = float(args.smoothing)

        fused = sl.Bodies()
        raw_by_serial = {sender["serial"]: sl.Bodies() for sender in senders}
        frame_idx = {sender["serial"]: None for sender in senders}
        next_frame_idx = {sender["serial"]: 0 for sender in senders}

        meta = {
            "args": _finite_json(vars(args)),
            "config": os.path.abspath(args.config),
            "sdk_version": sl.Camera.get_sdk_version(),
            "serials": serials,
            "body_format": {"sender": RAW_BODY_FORMAT_NAME, "fused": FUSED_BODY_FORMAT_NAME},
            "coordinate_system": COORD_NAME,
            "unit": UNIT_NAME,
            "run_dir": run_dir,
            "log_path": log_path,
            "video_paths": [
                {"serial_number": serial, "path": video["path"], "codec": video["codec"]}
                for serial, video in videos.items()
            ],
            "svo_paths": [
                {"serial_number": sender["serial"], "path": sender["svo_path"]}
                for sender in senders if sender.get("svo_path")
            ],
        }
        with open(meta_path, "w") as meta_file:
            json.dump(meta, meta_file, ensure_ascii=False, indent=2, allow_nan=False)
        print("metadata ->", meta_path)
        print("logging ->", log_path)

        stop = {"value": False}
        stop_handler = lambda *_: stop.__setitem__("value", True)
        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)

        n_frames = 0
        n_frame_records = 0
        n_fused_records = 0
        n_raw_records = 0
        n_metrics_records = 0
        t0 = last = time.time()
        with open(log_path, "w") as log_file:
            while not stop["value"]:
                if args.duration and time.time() - t0 >= args.duration:
                    break

                grabbed_serials = set()
                for sender in senders:
                    serial = sender["serial"]
                    if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                        sender["camera"].retrieve_bodies(raw_by_serial[serial], sender["runtime"])
                        current_idx = next_frame_idx[serial]
                        if serial in videos:
                            _write_video_frame(cv2, videos[serial], sender["camera"])
                        frame_idx[serial] = current_idx
                        next_frame_idx[serial] = current_idx + 1
                        grabbed_serials.add(serial)

                status = fusion.process()
                if status != sl.FUSION_ERROR_CODE.SUCCESS:
                    continue

                status = fusion.retrieve_bodies(
                    fused, runtime, _camera_identifier(0), sl.FUSION_REFERENCE_FRAME.WORLD)
                if status != sl.FUSION_ERROR_CODE.SUCCESS:
                    continue

                n_frames += 1
                t_wall_ns = time.time_ns()
                fused_frame_idx = {str(serial): frame_idx[serial] for serial in serials}
                _write_record(log_file, {
                    "record": "frame",
                    "frame_idx": fused_frame_idx,
                    "t_sdk_ns": _timestamp_ns(fused),
                    "t_wall_ns": t_wall_ns,
                    "n_bodies": len(fused.body_list),
                    "body_ids": [int(body.id) for body in fused.body_list],
                })
                n_frame_records += 1
                for body in fused.body_list:
                    _write_record(log_file, _body_record(
                        body, fused, "fused", fused_frame_idx, t_wall_ns=t_wall_ns))
                    n_fused_records += 1

                if not args.no_raw:
                    for serial in serials:
                        if serial not in grabbed_serials:
                            continue
                        bodies = raw_by_serial[serial]
                        for body in bodies.body_list:
                            _write_record(log_file, _body_record(
                                body, bodies, "raw", frame_idx[serial], t_wall_ns=t_wall_ns,
                                serial_number=serial))
                            n_raw_records += 1

                if n_frames % args.metrics_every == 0:
                    status, metrics = fusion.get_process_metrics()
                    if status == sl.FUSION_ERROR_CODE.SUCCESS:
                        _write_record(log_file, _metrics_record(
                            metrics, fused_frame_idx, _timestamp_ns(fused), t_wall_ns))
                        n_metrics_records += 1
                    else:
                        print("\nwarning: Fusion metrics retrieval failed: %s" % status)

                log_file.flush()
                now = time.time()
                if now - last >= 1.0:
                    fps_live = n_frames / (now - t0) if now > t0 else 0.0
                    print("\rframes=%d frame_records=%d fused=%d raw=%d metrics=%d "
                          "~%.1ffps live=%d   " % (
                              n_frames, n_frame_records, n_fused_records, n_raw_records,
                              n_metrics_records, fps_live, len(fused.body_list)), end="")
                    last = now

        elapsed = time.time() - t0
        print("\ndone. %d frames in %.1fs (~%.1f fps), frame_records=%d "
              "fused=%d raw=%d metrics=%d -> %s" % (
            n_frames, elapsed, n_frames / elapsed if elapsed else 0.0,
            n_frame_records, n_fused_records, n_raw_records, n_metrics_records, log_path))

    finally:
        for video in videos.values():
            video["writer"].release()
        if fusion is not None:
            for identifier in identifiers:
                try:
                    fusion.unsubscribe(identifier)
                except Exception:
                    pass
            fusion.close()
        for sender in senders:
            if sender.get("recording"):
                try:
                    sender["camera"].disable_recording()
                except Exception:
                    pass
            try:
                sender["camera"].stop_publishing()
            except Exception:
                pass
            try:
                sender["camera"].disable_body_tracking()
            except Exception:
                pass
            try:
                sender["camera"].close()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print("error:", exc)
        sys.exit(1)
