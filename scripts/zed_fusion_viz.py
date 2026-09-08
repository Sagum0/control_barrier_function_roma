#!/usr/bin/env python3
"""Dual ZED-M Fusion 라이브 뷰어.

두 창을 띄운다.
  1. cameras (raw 2D): 각 sender 카메라 영상 위 BODY_18 2D 스켈레톤
  2. fusion world view: Fusion BODY_34 world-frame top/front/side 투영

Headless 환경에서는 --save 로 고정 레이아웃 MP4를 저장한다.
"""
import argparse
import math
import os
import signal
import sys
import time

import pyzed.sl as sl

from zed_fusion_bodytrack import (
    BONES_34,
    FUSED_BODY_FORMAT_NAME,
    _available_serials,
    _init_fusion,
    _joint_indices,
    _ok_keypoint,
    _open_sender,
    _read_config,
    _tolist,
)

CAMERA_WINDOW = "cameras (raw 2D)"
TOPDOWN_WINDOW = "fusion top-down (world)"
WORLD_WINDOW = "fusion world view"
COMPOSITE_WIDTH = 1280
CAMERA_TILE_SIZE = (640, 360)
COMPOSITE_HEIGHT = CAMERA_TILE_SIZE[1] + COMPOSITE_WIDTH
VIEW_AXES = {
    "top": "h=+X forward, v=+Y left",
    "front": "h=-Y right, v=+Z up",
    "side": "h=+X forward, v=+Z up",
    "orbit": "h=rotated X/Y, v=tilted X/Y/Z",
}

BODY_18_FALLBACK_BONES = [
    (0, 1),   # 코-목
    (1, 2), (2, 3), (3, 4),
    (1, 5), (5, 6), (6, 7),
    (1, 8), (8, 9), (9, 10),
    (1, 11), (11, 12), (12, 13),
    (0, 14), (14, 16),
    (0, 15), (15, 17),
]


def _load_visual_modules():
    global cv2, np
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise RuntimeError("cv2/numpy are required for zed_fusion_viz.py: %s" % exc)


def _enum_index(value):
    return int(getattr(value, "value", value))


def _body18_bones():
    bones = getattr(sl, "BODY_18_BONES", None)
    if bones:
        return [(_enum_index(a), _enum_index(b)) for a, b in bones]
    return BODY_18_FALLBACK_BONES


def _cc(confidence):
    try:
        c = float(confidence)
    except Exception:
        c = 0.0
    if not math.isfinite(c):
        c = 0.0
    c = max(0.0, min(100.0, c))
    return (0, int(2.55 * c), int(2.55 * (100.0 - c)))


def _confidence_at(confidences, idx):
    if idx >= len(confidences):
        return 0.0
    try:
        c = float(confidences[idx])
    except Exception:
        return 0.0
    if not math.isfinite(c):
        return 0.0
    return max(0.0, min(100.0, c))


def _project_world(point, view, az, el):
    x = float(point[0])
    y = float(point[1])
    z = float(point[2])
    if view == "top":
        return x, y
    if view == "front":
        return -y, z
    if view == "side":
        return x, z
    if view == "orbit":
        az_rad = math.radians(float(az))
        el_rad = math.radians(float(el))
        # az=0,el=0 이 front(-Y,+Z), az=90,el=0 이 side(+X,+Z) 와 일치하도록 부호를 맞춘다.
        h = x * math.sin(az_rad) - y * math.cos(az_rad)
        v = (x * math.cos(az_rad) + y * math.sin(az_rad)) * math.sin(el_rad) + z * math.cos(el_rad)
        return h, v
    raise ValueError("unsupported world view: %s" % view)


def _world_origin(size, view):
    if view == "top":
        return size // 2, int(size * 0.72)
    return size // 2, int(size * 0.85)


def _world_screen(point, size, scale, view, az, el):
    h, v = _project_world(point, view, az, el)
    ox, oy = _world_origin(size, view)
    return int(ox + h * scale), int(oy - v * scale)


def _draw_world_reference(img, size, scale, view, az, el):
    ox, oy = _world_origin(size, view)
    if view == "top":
        cv2.line(img, (0, oy), (size, oy), (215, 215, 215), 1, cv2.LINE_AA)
        cv2.line(img, (ox, 0), (ox, size), (215, 215, 215), 1, cv2.LINE_AA)
        x1 = _world_screen((0.0, 0.0, 0.0), size, scale, view, az, el)
        x2 = _world_screen((1.0, 0.0, 0.0), size, scale, view, az, el)
        y2 = _world_screen((0.0, 1.0, 0.0), size, scale, view, az, el)
        cv2.line(img, x1, x2, (80, 80, 220), 2, cv2.LINE_AA)
        cv2.line(img, x1, y2, (80, 170, 80), 2, cv2.LINE_AA)
        cv2.putText(img, "+X", (x2[0] + 6, x2[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 180), 1, cv2.LINE_AA)
        cv2.putText(img, "+Y", (y2[0] + 6, y2[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (70, 140, 70), 1, cv2.LINE_AA)
        return

    floor_y = _world_screen((0.0, 0.0, 0.0), size, scale, view, az, el)[1]
    cv2.line(img, (0, floor_y), (size, floor_y), (205, 205, 205), 1, cv2.LINE_AA)
    cv2.putText(img, "Z=0 floor", (16, max(18, floor_y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1, cv2.LINE_AA)

    tick_x = 48
    cv2.line(img, (tick_x, floor_y), (tick_x, max(0, floor_y - int(2.0 * scale))),
             (190, 190, 190), 1, cv2.LINE_AA)
    for meters in (0.5, 1.0, 1.5, 2.0):
        y = int(floor_y - meters * scale)
        if 0 <= y < size:
            cv2.line(img, (tick_x - 6, y), (tick_x + 6, y), (150, 150, 150), 1, cv2.LINE_AA)
            cv2.putText(img, "%.1fm" % meters, (tick_x + 12, y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1, cv2.LINE_AA)


def _draw_world_triad(img, size, scale, view, az, el):
    origin = _world_screen((0.0, 0.0, 0.0), size, scale, view, az, el)
    axes = [
        ("+X", (0.55, 0.0, 0.0), (40, 40, 220)),
        ("+Y", (0.0, 0.55, 0.0), (40, 170, 40)),
        ("+Z", (0.0, 0.0, 0.55), (220, 70, 40)),
    ]
    for label, endpoint, color in axes:
        end = _world_screen(endpoint, size, scale, view, az, el)
        cv2.line(img, origin, end, color, 2, cv2.LINE_AA)
        cv2.circle(img, end, 4, color, -1, cv2.LINE_AA)
        cv2.putText(img, label, (end[0] + 6, end[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def _draw_world_view(cv2, np, size, scale, view, fused, raw_by_serial, joints, az, el):
    del joints
    img = np.full((size, size, 3), 245, dtype=np.uint8)
    if view == "orbit":
        _draw_world_triad(img, size, scale, view, az, el)
    else:
        _draw_world_reference(img, size, scale, view, az, el)

    title = "view=%s axes=%s" % (view, VIEW_AXES[view])
    if view == "orbit":
        title += " az=%.1f el=%.1f" % (az, el)
    cv2.putText(img, title, (16, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (35, 35, 35), 2, cv2.LINE_AA)

    for row, (serial, bodies) in enumerate(raw_by_serial.items()):
        for body in bodies.body_list:
            kp = _tolist(body.keypoint)
            for point in kp:
                if _ok_keypoint(point):
                    cv2.circle(img, _world_screen(point, size, scale, view, az, el),
                               3, (170, 170, 170), -1, cv2.LINE_AA)
        cv2.putText(img, "raw %s: %d" % (serial, len(bodies.body_list)), (16, size - 78 + 20 * row),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 120, 120), 1, cv2.LINE_AA)

    for body in fused.body_list:
        kp = _tolist(body.keypoint)
        conf = _tolist(body.keypoint_confidence)
        for a, b in BONES_34:
            if a < len(kp) and b < len(kp) and _ok_keypoint(kp[a]) and _ok_keypoint(kp[b]):
                c = 0.5 * (_confidence_at(conf, a) + _confidence_at(conf, b))
                cv2.line(img,
                         _world_screen(kp[a], size, scale, view, az, el),
                         _world_screen(kp[b], size, scale, view, az, el),
                         _cc(c), 2, cv2.LINE_AA)
        for idx, point in enumerate(kp):
            if _ok_keypoint(point):
                cv2.circle(img, _world_screen(point, size, scale, view, az, el),
                           5, _cc(_confidence_at(conf, idx)), -1, cv2.LINE_AA)
        root = _world_screen(kp[0], size, scale, view, az, el) if kp and _ok_keypoint(kp[0]) else (18, 54)
        cv2.putText(img, "id %d" % int(body.id), root, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

    cv2.putText(img, "fused=%d  raw gray, fused red->green by confidence" % len(fused.body_list),
                (16, size - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (35, 35, 35), 1, cv2.LINE_AA)
    return img


def _ok2d(point):
    if point is None or len(point) < 2:
        return False
    try:
        x = float(point[0])
        y = float(point[1])
    except Exception:
        return False
    return math.isfinite(x) and math.isfinite(y) and x > 0 and y > 0


def _blank_camera_tile(serial):
    img = np.full((CAMERA_TILE_SIZE[1], CAMERA_TILE_SIZE[0], 3), 32, dtype=np.uint8)
    cv2.putText(img, "S/N %s" % serial, (16, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2, cv2.LINE_AA)
    cv2.putText(img, "no frame", (16, 72),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (160, 160, 160), 2, cv2.LINE_AA)
    return img


def _draw_raw_overlay(img, bodies, serial, fps_text, bones):
    if img is None:
        img = _blank_camera_tile(serial)

    h, _w = img.shape[:2]
    for body in bodies.body_list:
        keypoints = body.keypoint_2d
        conf = body.keypoint_confidence
        for a, b in bones:
            if a < len(keypoints) and b < len(keypoints) and _ok2d(keypoints[a]) and _ok2d(keypoints[b]):
                c = 0.0
                if a < len(conf) and b < len(conf):
                    c = 0.5 * (float(conf[a] or 0.0) + float(conf[b] or 0.0))
                cv2.line(img,
                         (int(keypoints[a][0]), int(keypoints[a][1])),
                         (int(keypoints[b][0]), int(keypoints[b][1])),
                         _cc(c), 2, cv2.LINE_AA)
        for idx, point in enumerate(keypoints):
            if _ok2d(point):
                cv2.circle(img, (int(point[0]), int(point[1])),
                           5, _cc(conf[idx] if idx < len(conf) else 0.0), -1, cv2.LINE_AA)
        if len(keypoints) and _ok2d(keypoints[0]):
            cv2.putText(img, "id %d" % int(body.id), (int(keypoints[0][0]), int(keypoints[0][1])),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

    cv2.putText(img, "S/N %s  raw BODY_18  bodies=%d" % (serial, len(bodies.body_list)),
                (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (240, 240, 240), 2, cv2.LINE_AA)
    cv2.putText(img, "%s  conf red->green" % fps_text,
                (16, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (240, 240, 240), 2, cv2.LINE_AA)
    return img


def _resize_to_height(img, height):
    h, w = img.shape[:2]
    if h == height:
        return img
    width = max(1, int(w * (height / float(h))))
    return cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)


def _camera_panel(overlays, serials, fixed):
    panels = []
    for idx, serial in enumerate(serials[:2]):
        if idx < len(overlays):
            panel = overlays[idx]
        else:
            panel = _blank_camera_tile(serial)
        if fixed:
            panel = cv2.resize(panel, CAMERA_TILE_SIZE, interpolation=cv2.INTER_AREA)
        else:
            panel = _resize_to_height(panel, min(720, panel.shape[0]))
        panels.append(panel)

    while len(panels) < 2:
        panels.append(_blank_camera_tile("missing"))

    if not fixed and panels[0].shape[0] != panels[1].shape[0]:
        height = min(panels[0].shape[0], panels[1].shape[0])
        panels = [_resize_to_height(panel, height) for panel in panels]
    return cv2.hconcat(panels)


def _composite_frame(camera_panel, world_img):
    camera_fixed = cv2.resize(camera_panel, (COMPOSITE_WIDTH, CAMERA_TILE_SIZE[1]), interpolation=cv2.INTER_AREA)
    world_fixed = cv2.resize(world_img, (COMPOSITE_WIDTH, COMPOSITE_WIDTH), interpolation=cv2.INTER_AREA)
    return cv2.vconcat([camera_fixed, world_fixed])


def _make_writer(path, fps):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (COMPOSITE_WIDTH, COMPOSITE_HEIGHT))
    if not writer.isOpened():
        raise RuntimeError("could not open video writer: %s" % path)
    return writer


def _show(display_state, camera_panel, world_img, save_enabled):
    if not display_state["enabled"]:
        return save_enabled
    try:
        cv2.imshow(CAMERA_WINDOW, camera_panel)
        cv2.imshow(WORLD_WINDOW, world_img)
        return save_enabled
    except cv2.error as exc:
        print("warning: imshow failed; switching to headless save mode: %s" % exc)
        display_state["enabled"] = False
        return True


def _parse_args():
    parser = argparse.ArgumentParser(description="Dual ZED-M Fusion live viewer")
    parser.add_argument("--config", "--calib", dest="config", required=True, help="ZED360/manual Fusion config JSON")
    parser.add_argument("--res", default="HD720", help="HD720 fixed for this two-ZED-M USB setup")
    parser.add_argument("--fps", type=int, default=30, help="default 30; 60 is rejected for this rig")
    parser.add_argument("--depth", default="NEURAL", help="NEURAL | NEURAL_LIGHT | PERFORMANCE")
    parser.add_argument("--conf", type=int, default=40, help="sender detection_confidence_threshold")
    parser.add_argument("--min-keypoints", type=int, default=7)
    parser.add_argument("--min-cameras", type=int, default=1)
    parser.add_argument("--smoothing", type=float, default=0.1)
    parser.add_argument("--topdown-size", type=int, default=900)
    parser.add_argument("--topdown-scale", type=float, default=180.0, help="pixels per meter")
    parser.add_argument("--view", choices=("top", "front", "side", "orbit"), default="front",
                        help="initial world view")
    parser.add_argument("--az", type=float, default=30.0, help="initial orbit azimuth degrees")
    parser.add_argument("--el", type=float, default=20.0, help="initial orbit elevation degrees")
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 = until q/ESC/Ctrl-C")
    parser.add_argument("--save", action="store_true", help="also write composite MP4")
    parser.add_argument("--outdir", default="logs")
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--retry-wait", type=float, default=1.0)
    parser.add_argument("--verbose-fusion", action="store_true")
    return parser.parse_args()


def main():
    args = _parse_args()
    if args.fps != 30:
        print("error: Fusion on this hardware is fixed to 30 fps; got --fps %d" % args.fps)
        sys.exit(2)

    display_state = {"enabled": bool(os.environ.get("DISPLAY"))}
    if not display_state["enabled"]:
        if not args.save:
            print("error: 디스플레이 없음 -> --save 필요")
            sys.exit(2)
        print("DISPLAY is not set; running headless and saving composite MP4 only.")

    _load_visual_modules()

    configs = _read_config(args.config)
    serials = [int(conf.serial_number) for conf in configs]
    print("config cameras:", serials)
    available = _available_serials()
    missing = [serial for serial in serials if serial not in available]
    if missing:
        print("warning: config cameras not currently AVAILABLE:", missing)
        print("         close ZED Studio/other camera clients before running.")

    os.makedirs(args.outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(args.outdir, "fusion_viz_%s.mp4" % stamp)

    bones18 = _body18_bones()
    senders = []
    fusion = None
    writer = None
    save_enabled = bool(args.save)
    current_view = args.view
    default_az = float(args.az)
    default_el = float(args.el)

    try:
        for conf in configs:
            sender = _open_sender(conf, args.res, args.fps, args.depth, args.conf, args.retry_count, args.retry_wait)
            sender["mat"] = sl.Mat()
            sender["last_image"] = None
            senders.append(sender)

        warmup = sl.Bodies()
        for sender in senders:
            if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                sender["camera"].retrieve_bodies(warmup, sender["runtime"])

        fusion, _identifiers = _init_fusion(configs, args.verbose_fusion)

        runtime = sl.BodyTrackingFusionRuntimeParameters()
        runtime.skeleton_minimum_allowed_keypoints = int(args.min_keypoints)
        runtime.skeleton_minimum_allowed_camera = int(args.min_cameras)
        runtime.skeleton_smoothing = float(args.smoothing)

        joints = _joint_indices(FUSED_BODY_FORMAT_NAME)
        fused = sl.Bodies()
        raw_by_serial = {sender["serial"]: sl.Bodies() for sender in senders}

        if save_enabled:
            writer = _make_writer(video_path, args.fps)
            print("composite video ->", video_path)
        elif display_state["enabled"]:
            cv2.namedWindow(CAMERA_WINDOW, cv2.WINDOW_NORMAL)
            cv2.namedWindow(WORLD_WINDOW, cv2.WINDOW_NORMAL)

        stop = {"value": False}
        signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("value", True))

        t0 = time.time()
        last_print = t0
        frame_count = 0
        last_fps = 0.0

        while not stop["value"]:
            now = time.time()
            if args.duration and now - t0 >= args.duration:
                break

            overlays = []
            for sender in senders:
                serial = sender["serial"]
                if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                    sender["camera"].retrieve_image(sender["mat"], sl.VIEW.LEFT)
                    sender["camera"].retrieve_bodies(raw_by_serial[serial], sender["runtime"])
                    sender["last_image"] = sender["mat"].get_data()[:, :, :3].copy()  # BGRA -> BGR 변환
                fps_text = "~%.1ffps" % last_fps if last_fps else "warming up"
                overlays.append(_draw_raw_overlay(sender["last_image"].copy() if sender["last_image"] is not None else None,
                                                  raw_by_serial[serial], serial, fps_text, bones18))

            status = fusion.process()
            if status != sl.FUSION_ERROR_CODE.SUCCESS:
                continue

            status = fusion.retrieve_bodies(fused, runtime, sl.CameraIdentifier(), sl.FUSION_REFERENCE_FRAME.WORLD)
            if status != sl.FUSION_ERROR_CODE.SUCCESS:
                continue

            frame_count += 1
            elapsed = time.time() - t0
            last_fps = frame_count / elapsed if elapsed > 0 else 0.0

            camera_live = _camera_panel(overlays, serials, fixed=False)
            camera_fixed = _camera_panel(overlays, serials, fixed=True)
            world_img = _draw_world_view(cv2, np, args.topdown_size, args.topdown_scale,
                                         current_view, fused, raw_by_serial, joints, args.az, args.el)
            cv2.putText(world_img, "~%.1ffps  fused BODY_34 bodies=%d" % (last_fps, len(fused.body_list)),
                        (16, 54 if current_view != "orbit" else 94),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.56, (35, 35, 35), 2, cv2.LINE_AA)

            save_enabled = _show(display_state, camera_live, world_img, save_enabled)
            if save_enabled and writer is None:
                writer = _make_writer(video_path, args.fps)
                print("composite video ->", video_path)
            if writer is not None:
                writer.write(_composite_frame(camera_fixed, world_img))

            if display_state["enabled"]:
                key = cv2.waitKey(1) & 0xFF
                if key in (27, 113):
                    break
                if key == ord("1"):
                    current_view = "top"
                elif key == ord("2"):
                    current_view = "front"
                elif key == ord("3"):
                    current_view = "side"
                elif key == ord("4"):
                    current_view = "orbit"
                elif key == ord("j"):
                    args.az -= 5.0
                    current_view = "orbit"
                elif key == ord("l"):
                    args.az += 5.0
                    current_view = "orbit"
                elif key == ord("i"):
                    args.el += 5.0
                    current_view = "orbit"
                elif key == ord("k"):
                    args.el -= 5.0
                    current_view = "orbit"
                elif key == ord("u"):
                    args.az = default_az
                    args.el = default_el
                    current_view = "orbit"

            now = time.time()
            if now - last_print >= 1.0:
                print("\rframes=%d ~%.1ffps fused=%d   " % (frame_count, last_fps, len(fused.body_list)), end="")
                last_print = now

        elapsed = time.time() - t0
        print("\ndone. %d frames in %.1fs (~%.1f fps)" % (
            frame_count, elapsed, frame_count / elapsed if elapsed else 0.0))
        if writer is not None:
            print("saved ->", video_path)

    finally:
        if writer is not None:
            writer.release()
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
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print("error:", exc)
        sys.exit(1)
