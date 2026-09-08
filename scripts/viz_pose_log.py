#!/usr/bin/env python3
"""Render a pose JSONL log (from zed_bodytrack_min.py) into a human-viewable
skeleton video (front view, joints/bones colored by confidence).

  python scripts/viz_pose_log.py logs/pose_XXXX.jsonl
  -> writes logs/pose_XXXX.mp4  (+ a preview PNG of the middle frame)

Uses only numpy + opencv (already in the `zed` env). No camera needed.
Projection: camera frame is RIGHT_HANDED_Z_UP_X_FWD (x=fwd depth, y=left, z=up);
we draw the y-z plane (a front view). Confidence: red=low ... green=high.
"""
import json
import os
import sys

import cv2
import numpy as np

# BODY_34 topology (index pairs). Indices per ZED BODY_34_PARTS.
BONES = [
    (0, 1), (1, 2), (2, 3), (3, 26), (26, 27),          # spine + head
    (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (7, 10),   # left arm/hand
    (3, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (14, 17),  # right arm/hand
    (0, 18), (18, 19), (19, 20), (20, 21), (20, 32),    # left leg
    (0, 22), (22, 23), (23, 24), (24, 25), (24, 33),    # right leg
    (27, 28), (28, 29), (27, 30), (30, 31),             # face
]

W, H, MARGIN = 900, 720, 90
CONF_MIN = 5.0  # below this a joint is treated as not-detected


def conf_color(c):
    c = max(0.0, min(100.0, c))
    return (0, int(2.55 * c), int(2.55 * (100 - c)))  # BGR: red(low)->green(high)


def main():
    if len(sys.argv) < 2:
        print("usage: viz_pose_log.py <pose.jsonl>")
        sys.exit(1)
    path = sys.argv[1]
    rows = [json.loads(l) for l in open(path) if l.strip()]
    if not rows:
        print("empty log")
        sys.exit(1)

    # ---- fit projection to the data (y,z of confident joints across all frames) ----
    ys, zs = [], []
    for r in rows:
        kp, cf = r["kp"], r["kp_conf"]
        for j in range(len(kp)):
            if cf[j] is not None and cf[j] == cf[j] and cf[j] > CONF_MIN:
                ys.append(kp[j][1]); zs.append(kp[j][2])
    if not ys:
        print("no confident joints to plot")
        sys.exit(1)
    ymin, ymax, zmin, zmax = min(ys), max(ys), min(zs), max(zs)
    span = max(ymax - ymin, zmax - zmin, 0.3)
    scale = (min(W, H) - 2 * MARGIN) / span
    cy_data = 0.5 * (ymin + ymax)
    cz_data = 0.5 * (zmin + zmax)

    def project(p):
        u = int(W / 2 - (p[1] - cy_data) * scale)   # +y (left) -> left of image
        v = int(H / 2 - (p[2] - cz_data) * scale)   # +z (up)   -> top of image
        return u, v

    base = os.path.splitext(path)[0]
    out_mp4 = base + ".mp4"
    writer = cv2.VideoWriter(out_mp4, cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
    if not writer.isOpened():
        out_mp4 = base + ".avi"
        writer = cv2.VideoWriter(out_mp4, cv2.VideoWriter_fourcc(*"XVID"), 30, (W, H))

    t0 = rows[0]["t_img_ns"]
    mid_png = None
    for fi, r in enumerate(rows):
        img = np.full((H, W, 3), 24, np.uint8)
        kp, cf = r["kp"], r["kp_conf"]
        pts = [project(p) for p in kp]
        # bones
        for a, b in BONES:
            if a < len(kp) and b < len(kp) and cf[a] and cf[b] and cf[a] > CONF_MIN and cf[b] > CONF_MIN:
                c = conf_color(0.5 * (cf[a] + cf[b]))
                cv2.line(img, pts[a], pts[b], c, 2, cv2.LINE_AA)
        # joints
        for j in range(len(kp)):
            if cf[j] and cf[j] > CONF_MIN:
                cv2.circle(img, pts[j], 4, conf_color(cf[j]), -1, cv2.LINE_AA)
        # HUD
        tsec = (r["t_img_ns"] - t0) / 1e9
        cv2.putText(img, "frame %d/%d  t=%.2fs  id=%s  %s" % (fi + 1, len(rows), tsec, r["id"], r["tracking_state"]),
                    (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(img, "conf: red=low  green=high", (12, H - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)
        writer.write(img)
        if fi == len(rows) // 2:
            mid_png = base + "_preview.png"
            cv2.imwrite(mid_png, img)
    writer.release()
    print("wrote", out_mp4, "(%d frames)" % len(rows))
    if mid_png:
        print("preview", mid_png)


if __name__ == "__main__":
    main()
