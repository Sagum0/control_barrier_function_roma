#!/usr/bin/env python3
"""ZED-M Human Pose (Body Tracking) minimal prototype — stream A.

Definition-of-Done artifacts for this stage:
  * per-body 3D keypoints + per-joint confidence + capture timestamp, appended as
    JSONL (one line per detected body per frame) — the raw material for eps(t).
  * optional SVO2 recording for offline reprocessing / config sweeps.

Coordinates: meters, RIGHT_HANDED_Z_UP_X_FWD (ROS / REP-103 aligned).
The camera->base transform (T_base_cam) is applied LATER (after hand-eye calib);
here keypoints are in the camera frame.

Verified against ZED SDK 5.4 / pyzed. Run inside the `zed` conda env.
  python scripts/zed_bodytrack_min.py --fps 30
Stop with Ctrl-C.  NOTE: close ZED Studio / other ZED apps first (they hold the camera).
"""
import argparse
import json
import os
import signal
import sys
import time

import pyzed.sl as sl


def _tolist(a):
    try:
        return a.tolist()
    except Exception:
        return list(a)


def _joint(kp, conf, idx):
    try:
        return {"xyz": _tolist(kp[idx]), "conf": float(conf[idx])}
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="ZED-M body tracking -> JSONL log")
    ap.add_argument("--serial", type=int, default=0, help="ZED serial number; 0 = first available")
    ap.add_argument("--res", default="HD720", help="HD720 | HD1080 | VGA ...")
    ap.add_argument("--fps", type=int, default=30, help="camera fps (2x ZED-M @60 exceeds USB3 here; use 30)")
    ap.add_argument("--depth", default="NEURAL", help="NEURAL | NEURAL_PLUS | NEURAL_LIGHT | PERFORMANCE")
    ap.add_argument("--body-format", default="BODY_34", help="BODY_34 | BODY_38 | BODY_18")
    ap.add_argument("--conf", type=int, default=40, help="detection_confidence_threshold (indoor ~40-50)")
    ap.add_argument("--duration", type=float, default=0, help="seconds; 0 = until Ctrl-C")
    ap.add_argument("--outdir", default="logs", help="output directory")
    ap.add_argument("--record-svo", action="store_true", help="also record a .svo2 file")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(args.outdir, "pose_%s.jsonl" % stamp)

    # ---- open camera ----
    zed = sl.Camera()
    init = sl.InitParameters()
    if args.serial:
        init.set_from_serial_number(args.serial)
    init.camera_resolution = getattr(sl.RESOLUTION, args.res)
    init.camera_fps = args.fps
    init.depth_mode = getattr(sl.DEPTH_MODE, args.depth)
    init.coordinate_units = sl.UNIT.METER
    init.coordinate_system = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD  # ROS-aligned
    err = zed.open(init)
    if err != sl.ERROR_CODE.SUCCESS:
        print("open failed:", err, "(is ZED Studio / another app using the camera?)")
        sys.exit(1)
    info = zed.get_camera_information()
    print("opened S/N %s @ %s %dfps, depth=%s" % (
        getattr(info, "serial_number", "?"), args.res, args.fps, args.depth))

    # ---- static mount + body tracking ----
    pt = sl.PositionalTrackingParameters()
    pt.set_as_static = True                      # fixed mount
    zed.enable_positional_tracking(pt)

    bt = sl.BodyTrackingParameters()
    bt.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_ACCURATE
    bt.body_format = getattr(sl.BODY_FORMAT, args.body_format)
    bt.enable_tracking = True
    bt.enable_body_fitting = (args.body_format == "BODY_34")   # required for BODY_34
    bt.enable_segmentation = False
    print("enabling body tracking (FIRST run may TensorRT-optimize the model for a few minutes)...")
    err = zed.enable_body_tracking(bt)
    if err != sl.ERROR_CODE.SUCCESS:
        print("enable_body_tracking failed:", err)
        zed.close()
        sys.exit(1)

    rt = sl.BodyTrackingRuntimeParameters()
    rt.detection_confidence_threshold = args.conf  # 40 default; doc's 52 was a ZED-2i paper value

    # ---- optional SVO2 recording ----
    recording = False
    if args.record_svo:
        svo_path = os.path.join(args.outdir, "session_%s.svo2" % stamp)
        if zed.enable_recording(sl.RecordingParameters(svo_path, sl.SVO_COMPRESSION_MODE.H264)) == sl.ERROR_CODE.SUCCESS:
            recording = True
            print("recording ->", svo_path)
        else:
            print("recording failed to start; continuing without SVO")

    # ---- joints the barrier consumes (head, wrists) ----
    parts = getattr(sl, args.body_format + "_PARTS")
    # pyzed 5.x enum members expose the index via .value (int() on the member fails)
    joints = {}
    for n in ("HEAD", "LEFT_WRIST", "RIGHT_WRIST"):
        m = getattr(parts, n, None)
        if m is not None:
            joints[n] = int(getattr(m, "value", m))
    print("tracked joints:", joints, "-> log:", log_path)

    bodies = sl.Bodies()
    runtime = sl.RuntimeParameters()
    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("v", True))

    n_frames = n_records = 0
    t0 = last = time.time()
    with open(log_path, "w") as lf:
        while not stop["v"]:
            if args.duration and (time.time() - t0) >= args.duration:
                break
            if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
                continue
            zed.retrieve_bodies(bodies, rt)
            t_img_ns = zed.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds()  # capture time
            n_frames += 1
            for b in bodies.body_list:
                kp, conf = b.keypoint, b.keypoint_confidence
                lf.write(json.dumps({
                    "t_img_ns": int(t_img_ns),
                    "id": int(b.id),
                    "tracking_state": str(b.tracking_state),
                    "kp": _tolist(kp),          # (N,3) meters, camera frame
                    "kp_conf": _tolist(conf),   # (N,)  <- eps(t) material
                    "joints": {k: _joint(kp, conf, i) for k, i in joints.items()},
                }) + "\n")
                n_records += 1
            lf.flush()
            now = time.time()
            if now - last >= 1.0:
                print("\r frames=%d records=%d ~%.1ffps live_bodies=%d   " % (
                    n_frames, n_records, n_frames / (now - t0), len(bodies.body_list)), end="")
                last = now

    print("\nstopping...")
    if recording:
        zed.disable_recording()
    zed.disable_body_tracking()
    zed.close()
    dt = time.time() - t0
    print("done. %d frames in %.1fs (~%.1f fps), %d body-records -> %s" % (
        n_frames, dt, n_frames / dt if dt else 0, n_records, log_path))


if __name__ == "__main__":
    main()
