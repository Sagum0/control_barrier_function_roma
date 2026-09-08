#!/usr/bin/env python3
"""ZED-M 2대 Body Tracking Fusion -> JSONL / top-down video.

ZED360 또는 scripts/zed_make_fusion_config.py가 만든 Fusion config JSON을
입력으로 받는다. 좌표는 METER, RIGHT_HANDED_Z_UP_X_FWD이며 결과 keypoint는
fusion world frame 기준이다.

실행 예:
  python3 scripts/zed_fusion_bodytrack.py --config logs/fusion_manual.json --duration 20 --topdown
"""
import argparse
import json
import math
import os
import signal
import sys
import time

import pyzed.sl as sl

COORD = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD
UNIT = sl.UNIT.METER
BODY_FORMAT = sl.BODY_FORMAT.BODY_18
FUSED_BODY_FORMAT_NAME = "BODY_34"

BONES_34 = [
    (0, 1), (1, 2), (2, 3), (3, 26), (26, 27),
    (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (7, 10),
    (3, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (14, 17),
    (0, 18), (18, 19), (19, 20), (20, 21), (20, 32),
    (0, 22), (22, 23), (23, 24), (24, 25), (24, 33),
    (27, 28), (28, 29), (27, 30), (30, 31),
]


def _tolist(value):
    try:
        return value.tolist()
    except Exception:
        return list(value)


def _enum_text(value):
    text = str(value)
    return text.split(".", 1)[-1] if "." in text else text


def _ok_keypoint(point):
    if point is None or len(point) < 3:
        return False
    try:
        return all(math.isfinite(float(v)) for v in point[:3])
    except Exception:
        return False


def _camera_identifier(serial):
    uuid = sl.CameraIdentifier()
    uuid.serial_number = int(serial)
    return uuid


def _status_failed(status, success):
    try:
        return status > success
    except TypeError:
        return status != success


def _available_serials():
    out = set()
    for dev in sl.Camera.get_device_list():
        serial = int(getattr(dev, "serial_number", 0) or 0)
        state = getattr(dev, "camera_state", None)
        if serial and state == sl.CAMERA_STATE.AVAILABLE:
            out.add(serial)
    return out


def _joint_indices(body_format_name):
    parts = getattr(sl, body_format_name + "_PARTS")
    out = {}
    for name in ("HEAD", "LEFT_WRIST", "RIGHT_WRIST"):
        member = getattr(parts, name, None)
        if member is not None:
            out[name] = int(getattr(member, "value", member))
    return out


def _joint(kp, conf, idx):
    if idx >= len(kp):
        return None
    return {"xyz": kp[idx], "conf": float(conf[idx]) if idx < len(conf) else 0.0}


def _body_record(body, t_ns, joints, source, frame):
    kp = _tolist(body.keypoint)
    conf = _tolist(body.keypoint_confidence)
    record = {
        "t_ns": int(t_ns),
        "frame": frame,
        "source": source,
        "id": int(body.id),
        "unique_object_id": str(getattr(body, "unique_object_id", "")),
        "tracking_state": _enum_text(body.tracking_state),
        "action_state": _enum_text(body.action_state),
        "confidence": float(getattr(body, "confidence", 0.0)),
        "n_kp": len(kp),
        "kp": kp,
        "kp_conf": conf,
        "joints": {name: _joint(kp, conf, idx) for name, idx in joints.items()},
    }
    if hasattr(body, "position"):
        record["position"] = _tolist(body.position)
    return record


def _open_sender(conf, res, fps, depth, conf_threshold, retry_count, retry_wait):
    serial = int(conf.serial_number)
    last_status = None
    for attempt in range(1, retry_count + 1):
        zed = sl.Camera()
        init = sl.InitParameters()
        init.coordinate_units = UNIT
        init.coordinate_system = COORD
        init.depth_mode = getattr(sl.DEPTH_MODE, depth)
        init.camera_resolution = getattr(sl.RESOLUTION, res)
        init.camera_fps = fps
        if conf.input_type.is_init():
            init.input = conf.input_type
        else:
            init.set_from_serial_number(serial)

        status = zed.open(init)
        if not _status_failed(status, sl.ERROR_CODE.SUCCESS):
            pt = sl.PositionalTrackingParameters()
            pt.set_as_static = True
            status = zed.enable_positional_tracking(pt)
            if _status_failed(status, sl.ERROR_CODE.SUCCESS):
                zed.close()
                raise RuntimeError("S/N %s positional tracking failed: %s" % (serial, status))

            bt = sl.BodyTrackingParameters()
            bt.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_ACCURATE
            bt.body_format = BODY_FORMAT
            bt.enable_tracking = False
            bt.enable_body_fitting = False
            bt.enable_segmentation = False
            status = zed.enable_body_tracking(bt)
            if _status_failed(status, sl.ERROR_CODE.SUCCESS):
                zed.close()
                raise RuntimeError("S/N %s body tracking failed: %s" % (serial, status))

            rt = sl.BodyTrackingRuntimeParameters()
            rt.detection_confidence_threshold = int(conf_threshold)

            status = zed.start_publishing(conf.communication_parameters)
            if _status_failed(status, sl.ERROR_CODE.SUCCESS):
                zed.disable_body_tracking()
                zed.close()
                raise RuntimeError("S/N %s start_publishing failed: %s" % (serial, status))

            print("  sender S/N %s publishing (%s @ %dfps)" % (serial, res, fps))
            return {"serial": serial, "camera": zed, "runtime": rt, "bodies": sl.Bodies()}

        last_status = status
        print("  sender S/N %s open failed (%s), retry %d/%d" % (serial, status, attempt, retry_count))
        zed.close()
        time.sleep(retry_wait)

    raise RuntimeError("S/N %s open failed after retries: %s" % (serial, last_status))


def _read_config(path):
    confs = sl.read_fusion_configuration_file(path, COORD, UNIT)
    if len(confs) < 2:
        raise RuntimeError("Fusion config must contain at least 2 cameras: %s" % path)
    return confs


def _init_fusion(configs, verbose):
    params = sl.InitFusionParameters()
    params.coordinate_units = UNIT
    params.coordinate_system = COORD
    params.output_performance_metrics = True
    params.verbose = bool(verbose)

    fusion = sl.Fusion()
    status = fusion.init(params)
    if status != sl.FUSION_ERROR_CODE.SUCCESS:
        raise RuntimeError("fusion.init failed: %s" % status)

    identifiers = []
    for conf in configs:
        uuid = _camera_identifier(conf.serial_number)
        status = fusion.subscribe(uuid, conf.communication_parameters, conf.pose, conf.override_gravity)
        if status != sl.FUSION_ERROR_CODE.SUCCESS:
            print("  subscribe S/N %s failed: %s" % (conf.serial_number, status))
            continue
        identifiers.append(uuid)
        print("  subscribed S/N %s override_gravity=%s" % (conf.serial_number, conf.override_gravity))

    if len(identifiers) < 2:
        fusion.close()
        raise RuntimeError("Fusion needs at least 2 subscribed cameras")

    body_params = sl.BodyTrackingFusionParameters()
    body_params.enable_tracking = True
    body_params.enable_body_fitting = True
    status = fusion.enable_body_tracking(body_params)
    if status != sl.FUSION_ERROR_CODE.SUCCESS:
        fusion.close()
        raise RuntimeError("fusion.enable_body_tracking failed: %s" % status)

    return fusion, identifiers


def _make_topdown_writer(path, fps, size):
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise RuntimeError("--topdown requires cv2/numpy: %s" % exc)

    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (size, size))
    if not writer.isOpened():
        raise RuntimeError("could not open top-down writer: %s" % path)
    return cv2, np, writer


def _draw_topdown(cv2, np, size, scale, fused_bodies, raw_by_serial, joints):
    img = np.full((size, size, 3), 245, dtype=np.uint8)
    origin = (size // 2, int(size * 0.72))

    def project(point):
        x = int(origin[0] + point[0] * scale)
        y = int(origin[1] - point[1] * scale)
        return x, y

    cv2.line(img, (0, origin[1]), (size, origin[1]), (215, 215, 215), 1, cv2.LINE_AA)
    cv2.line(img, (origin[0], 0), (origin[0], size), (215, 215, 215), 1, cv2.LINE_AA)
    cv2.putText(img, "fusion world top-down (x/y meters)", (16, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (35, 35, 35), 2, cv2.LINE_AA)

    for row, (serial, bodies) in enumerate(raw_by_serial.items()):
        for body in bodies.body_list:
            kp = _tolist(body.keypoint)
            for point in kp:
                if _ok_keypoint(point):
                    cv2.circle(img, project(point), 3, (170, 170, 170), -1, cv2.LINE_AA)
        cv2.putText(img, "raw %s: %d" % (serial, len(bodies.body_list)), (16, size - 58 + 20 * row),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 120, 120), 1, cv2.LINE_AA)

    for body in fused_bodies.body_list:
        kp = _tolist(body.keypoint)
        conf = _tolist(body.keypoint_confidence)
        for a, b in BONES_34:
            if a < len(kp) and b < len(kp) and _ok_keypoint(kp[a]) and _ok_keypoint(kp[b]):
                c = 0.0
                if a < len(conf) and b < len(conf):
                    c = max(0.0, min(100.0, 0.5 * (float(conf[a]) + float(conf[b]))))
                color = (0, int(2.55 * c), int(2.55 * (100.0 - c)))
                cv2.line(img, project(kp[a]), project(kp[b]), color, 2, cv2.LINE_AA)
        for idx, point in enumerate(kp):
            if _ok_keypoint(point):
                c = max(0.0, min(100.0, float(conf[idx]) if idx < len(conf) else 0.0))
                color = (0, int(2.55 * c), int(2.55 * (100.0 - c)))
                cv2.circle(img, project(point), 5, color, -1, cv2.LINE_AA)
        root = project(kp[0]) if kp and _ok_keypoint(kp[0]) else (18, 54)
        cv2.putText(img, "id %d" % int(body.id), root, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

    cv2.putText(img, "fused=%d  raw gray, fused red->green by confidence" % len(fused_bodies.body_list),
                (16, size - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (35, 35, 35), 1, cv2.LINE_AA)
    return img


def main():
    parser = argparse.ArgumentParser(description="Dual ZED-M Fusion body tracking logger")
    parser.add_argument("--config", "--calib", dest="config", required=True, help="ZED360/manual Fusion config JSON")
    parser.add_argument("--res", default="HD720", help="HD720 fixed for this two-ZED-M USB setup")
    parser.add_argument("--fps", type=int, default=30, help="default 30; this rig cannot sustain 2xHD720@60")
    parser.add_argument("--depth", default="NEURAL", help="NEURAL | NEURAL_LIGHT | PERFORMANCE")
    parser.add_argument("--conf", type=int, default=40, help="sender detection_confidence_threshold")
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 = until Ctrl-C")
    parser.add_argument("--outdir", default="logs")
    parser.add_argument("--min-keypoints", type=int, default=7)
    parser.add_argument("--min-cameras", type=int, default=1)
    parser.add_argument("--smoothing", type=float, default=0.1)
    parser.add_argument("--topdown", action="store_true", help="save a top-down fused skeleton MP4")
    parser.add_argument("--topdown-size", type=int, default=900)
    parser.add_argument("--topdown-scale", type=float, default=180.0, help="pixels per meter")
    parser.add_argument("--record-raw", action="store_true", help="also write per-camera raw body records")
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--retry-wait", type=float, default=1.0)
    parser.add_argument("--verbose-fusion", action="store_true")
    args = parser.parse_args()

    if args.fps != 30:
        print("error: Fusion on this hardware is fixed to 30 fps; got --fps %d" % args.fps)
        sys.exit(2)

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
    topdown = None
    os.makedirs(args.outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(args.outdir, "fusion_%s.jsonl" % stamp)
    meta_path = os.path.join(args.outdir, "fusion_%s_meta.json" % stamp)
    video_path = os.path.join(args.outdir, "fusion_topdown_%s.mp4" % stamp)

    try:
        for conf in configs:
            senders.append(_open_sender(conf, args.res, args.fps, args.depth, args.conf, args.retry_count, args.retry_wait))

        # 첫 frame을 밀어 넣어 shared-memory sender가 Fusion subscribe 전에 준비되게 한다.
        warmup = sl.Bodies()
        for sender in senders:
            if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                sender["camera"].retrieve_bodies(warmup, sender["runtime"])

        fusion, identifiers = _init_fusion(configs, args.verbose_fusion)

        runtime = sl.BodyTrackingFusionRuntimeParameters()
        runtime.skeleton_minimum_allowed_keypoints = int(args.min_keypoints)
        runtime.skeleton_minimum_allowed_camera = int(args.min_cameras)
        runtime.skeleton_smoothing = float(args.smoothing)

        joints = _joint_indices(FUSED_BODY_FORMAT_NAME)
        fused = sl.Bodies()
        raw_by_serial = {sender["serial"]: sl.Bodies() for sender in senders}

        if args.topdown:
            topdown = _make_topdown_writer(video_path, args.fps, args.topdown_size)
            print("top-down video ->", video_path)

        meta = {
            "config": os.path.abspath(args.config),
            "serials": serials,
            "frame": "fusion_world",
            "coordinate_system": "RIGHT_HANDED_Z_UP_X_FWD",
            "unit": "METER",
            "fps": args.fps,
            "resolution": args.res,
            "depth": args.depth,
            "sender_body_format": "BODY_18",
            "fused_body_format": FUSED_BODY_FORMAT_NAME,
            "manual_config_note": "manual configs are only for pipeline bootstrap; use ZED360 for quantitative fusion.",
            "runtime": {
                "sender_conf": args.conf,
                "skeleton_minimum_allowed_keypoints": args.min_keypoints,
                "skeleton_minimum_allowed_camera": args.min_cameras,
                "skeleton_smoothing": args.smoothing,
            },
            "log_path": os.path.abspath(log_path),
            "topdown_path": os.path.abspath(video_path) if args.topdown else None,
        }
        with open(meta_path, "w") as mf:
            json.dump(meta, mf, ensure_ascii=False, indent=2)
        print("metadata ->", meta_path)
        print("logging ->", log_path)

        stop = {"value": False}
        signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("value", True))

        n_frames = 0
        n_fused_records = 0
        n_raw_records = 0
        t0 = last = time.time()
        with open(log_path, "w") as lf:
            while not stop["value"]:
                if args.duration and time.time() - t0 >= args.duration:
                    break

                for sender in senders:
                    if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                        sender["camera"].retrieve_bodies(raw_by_serial[sender["serial"]], sender["runtime"])

                status = fusion.process()
                if status != sl.FUSION_ERROR_CODE.SUCCESS:
                    continue

                status = fusion.retrieve_bodies(fused, runtime, sl.CameraIdentifier(), sl.FUSION_REFERENCE_FRAME.WORLD)
                if status != sl.FUSION_ERROR_CODE.SUCCESS:
                    continue

                t_ns = int(time.time() * 1e9)
                n_frames += 1
                cameras_with_body = sum(1 for bodies in raw_by_serial.values() if len(bodies.body_list) > 0)

                for body in fused.body_list:
                    record = _body_record(body, t_ns, joints, "fusion", "fusion_world")
                    record["n_cameras_configured"] = len(identifiers)
                    record["n_cameras_seen"] = cameras_with_body
                    record["n_cameras_seen_note"] = "frame-level raw camera count; SDK does not expose per-joint source cameras in BodyData"
                    record["fusion_runtime"] = {
                        "min_keypoints": args.min_keypoints,
                        "min_cameras": args.min_cameras,
                        "smoothing": args.smoothing,
                    }
                    lf.write(json.dumps(record, ensure_ascii=False) + "\n")
                    n_fused_records += 1

                if args.record_raw:
                    raw_joints = _joint_indices("BODY_18")
                    for serial, bodies in raw_by_serial.items():
                        for body in bodies.body_list:
                            record = _body_record(body, t_ns, raw_joints, "camera_%s" % serial, "camera")
                            record["serial_number"] = serial
                            lf.write(json.dumps(record, ensure_ascii=False) + "\n")
                            n_raw_records += 1

                if topdown is not None:
                    cv2, np, writer = topdown
                    writer.write(_draw_topdown(cv2, np, args.topdown_size, args.topdown_scale, fused, raw_by_serial, joints))

                lf.flush()
                now = time.time()
                if now - last >= 1.0:
                    fps_live = n_frames / (now - t0) if now > t0 else 0.0
                    print("\rframes=%d fused_records=%d raw_records=%d ~%.1ffps live=%d   " % (
                        n_frames, n_fused_records, n_raw_records, fps_live, len(fused.body_list)), end="")
                    last = now

        elapsed = time.time() - t0
        print("\ndone. %d frames in %.1fs (~%.1f fps), fused=%d raw=%d -> %s" % (
            n_frames, elapsed, n_frames / elapsed if elapsed else 0.0, n_fused_records, n_raw_records, log_path))

    finally:
        if topdown is not None:
            topdown[2].release()
        if fusion is not None:
            fusion.close()
        for sender in senders:
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
