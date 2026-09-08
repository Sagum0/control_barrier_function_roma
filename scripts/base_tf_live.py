#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZED LEFT 영상에 고정된 base 원점 좌표축을 겹쳐 그린다."""

import argparse
import ast
import math
import os
from pathlib import Path

import cv2
import numpy as np
import pyzed.sl as sl

from aruco_cube_datum import (
    T_BODY_OPTICAL,
    _quat_to_mat,
    average_poses,
    base_T_cam_from_marker,
    load_datum,
    mat_to_xyzquat,
    pnp_cam_optical_T_marker,
)
from measure_base_cam import (
    COORD,
    DEFAULT_SERIAL_MAP,
    UNIT,
    camera_matrix,
    child_frame,
    make_detector,
    open_camera,
    parse_serial_map,
)


def load_yaml_pose(path, child):
    transforms = []
    current = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- parent:"):
                if current is not None:
                    transforms.append(current)
                current = {"parent": line.split(":", 1)[1].strip()}
            elif current is not None and ":" in line:
                key, value = line.split(":", 1)
                current[key.strip()] = value.strip()
    if current is not None:
        transforms.append(current)

    for item in transforms:
        if item.get("child") != child:
            continue
        try:
            xyz = np.asarray(ast.literal_eval(item["translation"]), dtype=float)
            quat = np.asarray(ast.literal_eval(item["rotation_quat"]), dtype=float)
        except (KeyError, SyntaxError, ValueError) as exc:
            raise ValueError("%s의 %s transform 형식이 올바르지 않습니다" %
                             (path, child)) from exc

        if xyz.shape != (3,) or not np.all(np.isfinite(xyz)):
            raise ValueError("%s의 %s translation이 올바르지 않습니다" %
                             (path, child))
        if (quat.shape != (4,) or not np.all(np.isfinite(quat))
                or np.linalg.norm(quat) <= 1e-12):
            raise ValueError("%s의 %s rotation_quat가 올바르지 않습니다" %
                             (path, child))

        T = np.eye(4, dtype=float)
        T[:3, :3] = _quat_to_mat(quat)
        T[:3, 3] = xyz
        return T

    raise ValueError("%s에 child=%s transform이 없습니다" % (path, child))


def measure_base_pose(zed, K, markers, tag_size, detector, args):
    runtime = sl.RuntimeParameters()
    image = sl.Mat()
    candidates = []
    accepted_frames = 0
    rejected_frames = 0
    accepted_markers = 0
    rejected_markers = 0
    foreign_markers = 0

    for _ in range(args.warmup):
        if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
            rejected_frames += 1
            continue

        zed.retrieve_image(image, sl.VIEW.LEFT)
        bgra = image.get_data()
        gray = cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        accepted_this_frame = 0

        if ids is not None:
            for corner, marker_number in zip(corners, ids.flatten()):
                marker_id = int(marker_number)
                if marker_id not in markers:
                    foreign_markers += 1
                    continue

                solutions = pnp_cam_optical_T_marker(corner[0], tag_size, K)
                if len(solutions) < 2:
                    rejected_markers += 1
                    continue

                best, second = solutions[0], solutions[1]
                err0, err1 = best[1], second[1]
                if not math.isfinite(err0) or not math.isfinite(err1):
                    rejected_markers += 1
                    continue
                if err0 > args.max_reproj:
                    rejected_markers += 1
                    continue

                ratio = err0 / err1 if err1 > 1e-12 else 1.0
                if ratio > args.ambiguity_ratio:
                    rejected_markers += 1
                    continue

                optical_T_marker = best[0]
                candidate = base_T_cam_from_marker(
                    markers[marker_id], optical_T_marker)
                if (not np.all(np.isfinite(optical_T_marker))
                        or not np.all(np.isfinite(candidate))):
                    rejected_markers += 1
                    continue

                candidates.append(candidate)
                accepted_this_frame += 1
                accepted_markers += 1

        if accepted_this_frame:
            accepted_frames += 1
        else:
            rejected_frames += 1

    print("채택 %d프레임/%d마커, 폐기 %d프레임/%d마커, 외부 ID %d" % (
        accepted_frames, accepted_markers, rejected_frames, rejected_markers,
        foreign_markers))
    if not candidates:
        return None
    return average_poses(candidates)


def base_axis_pose(base_T_cam):
    # base_T_cam은 body 축 기준이므로 LEFT optical 축으로 한 번 더 바꿔야 한다.
    optical_T_base = np.linalg.inv(T_BODY_OPTICAL) @ np.linalg.inv(base_T_cam)
    rvec, _ = cv2.Rodrigues(optical_T_base[:3, :3])
    return rvec, optical_T_base[:3, 3]


def mat_to_rpy_deg(r):
    # roll=X, pitch=Y, yaw=Z인 ZYX 오일러를 도 단위로 읽는다.
    sy = math.hypot(r[0, 0], r[1, 0])
    pitch = math.atan2(-r[2, 0], sy)
    if sy > 1e-9:
        roll = math.atan2(r[2, 1], r[2, 2])
        yaw = math.atan2(r[1, 0], r[0, 0])
    else:
        roll = math.atan2(-r[1, 2], r[1, 1])
        yaw = 0.0
    return np.degrees([roll, pitch, yaw])


def overlay_loop(zed, K, base_T_cam, serial, name, mode, readout, args, show):
    runtime = sl.RuntimeParameters()
    image = sl.Mat()
    rvec, tvec = base_axis_pose(base_T_cam)
    xyz, _, rpy, dist = readout
    pos_text = "pos(m)  x=% .3f  y=% .3f  z=% .3f  |t|=%.3f" % (
        xyz[0], xyz[1], xyz[2], dist)
    rpy_text = "rpy(deg)  r=% .2f  p=% .2f  y=% .2f" % tuple(rpy)
    window = "base TF - %s (%d)" % (name, serial)
    last_frame = None
    shown = False
    attempts = 0

    while show or attempts < args.warmup:
        attempts += 1
        if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
            continue

        zed.retrieve_image(image, sl.VIEW.LEFT)
        bgra = image.get_data()
        bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
        cv2.drawFrameAxes(bgr, K, None, rvec, tvec, args.axis_len)
        cv2.putText(
            bgr, "%s  S/N %d" % (name, serial), (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(
            bgr, "base origin  %s" % mode, (20, 62),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(
            bgr, pos_text, (20, 92),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(
            bgr, rpy_text, (20, 122),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        last_frame = bgr.copy()

        if show:
            try:
                cv2.imshow(window, bgr)
                shown = True
                key = cv2.waitKey(1) & 0xFF
            except cv2.error as exc:
                if not args.save_frame:
                    raise RuntimeError(
                        "imshow 실패: 화면 세션을 확인하거나 --save-frame을 지정하세요") from exc
                print("imshow 실패: --save-frame 헤드리스 모드로 전환합니다")
                show = False
                continue
            if key in (ord("q"), 27):
                break

    if shown:
        cv2.destroyWindow(window)
    return last_frame


def run_camera(serial, name, markers, tag_size, detector, args, show):
    zed = open_camera(serial)
    try:
        K = camera_matrix(zed)
        if args.from_yaml:
            base_T_cam = load_yaml_pose(args.from_yaml, child_frame(name))
            mode = "from-yaml"
        else:
            base_T_cam = measure_base_pose(
                zed, K, markers, tag_size, detector, args)
            mode = "measured"
            if base_T_cam is None:
                print("serial %d: 유효한 pose 후보가 없어 건너뜁니다" % serial)
                return None

        xyz, q = mat_to_xyzquat(base_T_cam)
        rpy = mat_to_rpy_deg(base_T_cam[:3, :3])
        dist = float(np.linalg.norm(xyz))
        print(
            "serial %d base_T_cam xyz(m): x=% .6f y=% .6f z=% .6f "
            "dist=%.6f [%s]" %
            (serial, xyz[0], xyz[1], xyz[2], dist, mode))
        print("  rpy(deg): roll=% .3f pitch=% .3f yaw=% .3f" % tuple(rpy))
        print("  quat(xyzw): x=% .6f y=% .6f z=% .6f w=% .6f" % tuple(q))
        readout = xyz, q, rpy, dist
        return overlay_loop(
            zed, K, base_T_cam, serial, name, mode, readout, args, show)
    finally:
        zed.close()


def build_parser():
    parser = argparse.ArgumentParser(
        description="ZED LEFT 영상에 base 원점 좌표축을 실시간 오버레이")
    parser.add_argument("--datum", default="logs/base_cube_datum.json",
                        help="큐브 데이텀 JSON")
    parser.add_argument("--serial-map", type=parse_serial_map,
                        default=parse_serial_map(DEFAULT_SERIAL_MAP),
                        help="SERIAL=NAME 목록; 기본 카메라를 순차 확인")
    parser.add_argument("--serial", type=int,
                        help="지정한 serial 한 대만 확인")
    parser.add_argument("--warmup", type=int, default=60,
                        help="측정 및 헤드리스 오버레이 프레임 수 (기본 60)")
    parser.add_argument("--max-reproj", type=float, default=1.0,
                        help="최대 재투영오차 px (기본 1.0)")
    parser.add_argument("--ambiguity-ratio", type=float, default=0.3,
                        help="IPPE err0/err1 최대값 (기본 0.3)")
    parser.add_argument("--axis-len", type=float, default=0.2,
                        help="base 좌표축 길이 m (기본 0.2)")
    parser.add_argument("--from-yaml", metavar="PATH",
                        help="저장된 base_T_cam YAML로 warmup 측정 생략")
    parser.add_argument("--save-frame", metavar="PATH",
                        help="마지막 오버레이 프레임을 이미지로 저장")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.warmup <= 0:
        parser.error("--warmup은 1 이상이어야 합니다")
    if not math.isfinite(args.max_reproj) or args.max_reproj <= 0.0:
        parser.error("--max-reproj는 양의 유한값이어야 합니다")
    if not math.isfinite(args.ambiguity_ratio) or not 0.0 < args.ambiguity_ratio < 1.0:
        parser.error("--ambiguity-ratio는 0과 1 사이여야 합니다")
    if not math.isfinite(args.axis_len) or args.axis_len <= 0.0:
        parser.error("--axis-len은 양의 유한값이어야 합니다")
    if args.serial is not None and args.serial not in args.serial_map:
        parser.error("--serial %d가 --serial-map에 없습니다" % args.serial)

    show = bool(os.environ.get("DISPLAY"))
    if not show and not args.save_frame:
        parser.error(
            "DISPLAY가 없습니다. 화면 세션에서 실행하거나 --save-frame을 지정하세요")

    markers, tag_size, dictionary = load_datum(args.datum)
    detector = make_detector(dictionary)
    serials = ([args.serial] if args.serial is not None
               else list(args.serial_map))
    last_frame = None
    completed = 0

    # COORD/UNIT 설정은 재사용한 open_camera가 HD720@30과 함께 적용한다.
    _ = COORD, UNIT

    for serial in serials:
        name = args.serial_map[serial]
        print("\nserial %d (%s) 시작" % (serial, name))
        try:
            frame = run_camera(
                serial, name, markers, tag_size, detector, args, show)
        except (OSError, RuntimeError, ValueError) as exc:
            print("serial %d 건너뜀: %s" % (serial, exc))
            continue
        if frame is not None:
            last_frame = frame
            completed += 1

    if completed == 0:
        raise SystemExit("오버레이할 유효한 카메라 pose를 얻지 못했습니다")

    if args.save_frame:
        if last_frame is None:
            raise SystemExit("저장할 오버레이 프레임이 없습니다")
        target = Path(args.save_frame)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), last_frame):
            raise SystemExit("오버레이 이미지를 저장하지 못했습니다: %s" % target)
        print("저장:", target)


if __name__ == "__main__":
    main()
