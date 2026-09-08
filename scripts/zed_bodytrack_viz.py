#!/usr/bin/env python3
"""Live/annotated ZED-M body-tracking VISUALIZER — draws the 2D skeleton on the
actual camera image (like ZED Studio's skeleton view).

Live window (needs a display):
  python scripts/zed_bodytrack_viz.py --fps 30
Headless render to a video (no display needed):
  python scripts/zed_bodytrack_viz.py --fps 30 --save --duration 15 --outdir logs

Joints/bones colored by confidence (red=low, green=high). Close ZED Studio first.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np
import pyzed.sl as sl

BONES = [
    (0, 1), (1, 2), (2, 3), (3, 26), (26, 27),
    (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (7, 10),
    (3, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (14, 17),
    (0, 18), (18, 19), (19, 20), (20, 21), (20, 32),
    (0, 22), (22, 23), (23, 24), (24, 25), (24, 33),
    (27, 28), (28, 29), (27, 30), (30, 31),
]


def cc(c):
    c = 0.0 if (c is None or c != c) else max(0.0, min(100.0, c))
    return (0, int(2.55 * c), int(2.55 * (100 - c)))


def ok2d(p):
    return p is not None and p[0] == p[0] and p[1] == p[1] and p[0] > 0 and p[1] > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", type=int, default=0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--res", default="HD720")
    ap.add_argument("--conf", type=int, default=40)
    ap.add_argument("--save", action="store_true", help="render to a video instead of a live window")
    ap.add_argument("--duration", type=float, default=0)
    ap.add_argument("--outdir", default="logs")
    args = ap.parse_args()

    zed = sl.Camera()
    init = sl.InitParameters()
    if args.serial:
        init.set_from_serial_number(args.serial)
    init.camera_resolution = getattr(sl.RESOLUTION, args.res)
    init.camera_fps = args.fps
    init.depth_mode = sl.DEPTH_MODE.NEURAL
    init.coordinate_units = sl.UNIT.METER
    if zed.open(init) != sl.ERROR_CODE.SUCCESS:
        print("open failed (ZED Studio using the camera?)")
        sys.exit(1)

    ptp = sl.PositionalTrackingParameters()
    ptp.set_as_static = True
    zed.enable_positional_tracking(ptp)
    bt = sl.BodyTrackingParameters()
    bt.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_ACCURATE
    bt.body_format = sl.BODY_FORMAT.BODY_34
    bt.enable_tracking = True
    bt.enable_body_fitting = True
    zed.enable_body_tracking(bt)
    rt = sl.BodyTrackingRuntimeParameters()
    rt.detection_confidence_threshold = args.conf

    info = zed.get_camera_information()
    res = info.camera_configuration.resolution
    W, H = res.width, res.height

    writer = None
    if args.save:
        os.makedirs(args.outdir, exist_ok=True)
        out = os.path.join(args.outdir, "overlay_%s.mp4" % time.strftime("%Y%m%d_%H%M%S"))
        writer = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (W, H))
        print("rendering ->", out)
    else:
        cv2.namedWindow("ZED body tracking", cv2.WINDOW_NORMAL)

    bodies = sl.Bodies()
    mat = sl.Mat()
    runtime = sl.RuntimeParameters()
    t0 = time.time()
    n = 0
    preview_saved = False
    while True:
        if args.duration and time.time() - t0 >= args.duration:
            break
        if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
            continue
        zed.retrieve_image(mat, sl.VIEW.LEFT)
        zed.retrieve_bodies(bodies, rt)
        img = mat.get_data()[:, :, :3].copy()  # BGRA -> BGR
        for b in bodies.body_list:
            k2 = b.keypoint_2d
            cf = b.keypoint_confidence
            for a, c in BONES:
                if a < len(k2) and c < len(k2) and ok2d(k2[a]) and ok2d(k2[c]):
                    col = cc(0.5 * ((cf[a] or 0) + (cf[c] or 0)))
                    cv2.line(img, (int(k2[a][0]), int(k2[a][1])), (int(k2[c][0]), int(k2[c][1])), col, 2, cv2.LINE_AA)
            for j in range(len(k2)):
                if ok2d(k2[j]):
                    cv2.circle(img, (int(k2[j][0]), int(k2[j][1])), 5, cc(cf[j]), -1, cv2.LINE_AA)
            cv2.putText(img, "id %d %s" % (int(b.id), str(b.tracking_state)),
                        (int(k2[0][0]) if ok2d(k2[0]) else 20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(img, "bodies=%d  conf red->green" % len(bodies.body_list),
                    (16, H - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 2, cv2.LINE_AA)
        n += 1
        if writer is not None:
            writer.write(img)
            if not preview_saved and n > 5:
                cv2.imwrite(os.path.join(args.outdir, "overlay_preview.png"), img)
                preview_saved = True
        else:
            cv2.imshow("ZED body tracking", img)
            if cv2.waitKey(1) & 0xFF == 27:  # ESC
                break

    if writer is not None:
        writer.release()
        print("done, %d frames" % n)
    else:
        cv2.destroyAllWindows()
    zed.disable_body_tracking()
    zed.close()


if __name__ == "__main__":
    main()
