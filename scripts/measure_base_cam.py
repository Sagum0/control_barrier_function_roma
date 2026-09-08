#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ArUco 큐브를 보고 base 기준 ZED pose를 한 대씩 측정한다."""

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
import pyzed.sl as sl

from aruco_cube_datum import (
    average_poses,
    base_T_cam_from_marker,
    base_T_world,
    load_datum,
    mat_to_xyzquat,
    pnp_cam_optical_T_marker,
)


DEFAULT_SERIAL_MAP = "13870389=zed1,19321109=zed2"
COORD = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD
UNIT = sl.UNIT.METER


def parse_serial_map(text):
    result = {}
    for pair in text.split(","):
        fields = pair.strip().split("=", 1)
        if len(fields) != 2 or not fields[0].strip() or not fields[1].strip():
            raise argparse.ArgumentTypeError(
                "--serial-map은 SERIAL=NAME을 쉼표로 구분해야 합니다")
        try:
            serial = int(fields[0])
        except ValueError as exc:
            raise argparse.ArgumentTypeError("serial은 정수여야 합니다") from exc
        if serial in result:
            raise argparse.ArgumentTypeError("serial %d가 중복되었습니다" % serial)
        result[serial] = fields[1].strip()
    if not result:
        raise argparse.ArgumentTypeError("--serial-map이 비어 있습니다")
    return result


def child_frame(name):
    return name if name.endswith("_link") else name + "_link"


def make_detector(dictionary):
    try:
        dict_id = getattr(cv2.aruco, dictionary)
    except AttributeError as exc:
        raise ValueError("지원하지 않는 ArUco dictionary: %s" % dictionary) from exc
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
    return cv2.aruco.ArucoDetector(aruco_dict, cv2.aruco.DetectorParameters())


def camera_matrix(zed):
    # LEFT 영상은 rectified이므로 raw 보정값이나 distortion을 섞지 않는다.
    cam = zed.get_camera_information().camera_configuration.calibration_parameters.left_cam
    return np.array([
        [cam.fx, 0.0, cam.cx],
        [0.0, cam.fy, cam.cy],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)


def read_world_poses(path):
    configs = sl.read_fusion_configuration_file(str(path), COORD, UNIT)
    poses = {}
    for config in configs:
        serial = int(config.serial_number)
        t = np.asarray(config.pose.m, dtype=float).copy()
        if t.shape != (4, 4) or not np.all(np.isfinite(t)):
            raise ValueError("fusion config의 serial %d pose가 올바르지 않습니다" % serial)
        poses[serial] = t
    if not poses:
        raise ValueError("fusion config에 카메라 pose가 없습니다")
    return poses


def open_camera(serial):
    zed = sl.Camera()
    init = sl.InitParameters()
    init.set_from_serial_number(serial)
    init.camera_resolution = sl.RESOLUTION.HD720
    init.camera_fps = 30
    init.depth_mode = sl.DEPTH_MODE.NONE
    init.coordinate_system = COORD
    init.coordinate_units = UNIT
    init.camera_disable_self_calib = True

    status = zed.open(init)
    if status != sl.ERROR_CODE.SUCCESS:
        zed.close()
        raise RuntimeError("serial %d open 실패: %s" % (serial, status))

    opened = int(zed.get_camera_information().serial_number)
    if opened != serial:
        zed.close()
        raise RuntimeError("serial %d 대신 %d가 열렸습니다" % (serial, opened))
    return zed


def debug_path(path, serial, camera_count):
    target = Path(path)
    if camera_count == 1:
        return target
    suffix = target.suffix or ".png"
    return target.with_name("%s_%d%s" % (target.stem, serial, suffix))


def measure_camera(serial, markers, tag_size, detector, args, camera_count):
    zed = open_camera(serial)
    runtime = sl.RuntimeParameters()
    image = sl.Mat()
    candidates = []
    last_debug = None
    stop = False
    stats = {
        "accepted_frames": 0,
        "rejected_frames": 0,
        "accepted_markers": 0,
        "rejected_markers": 0,
        "foreign_markers": 0,
    }

    try:
        K = camera_matrix(zed)

        for _ in range(args.frames):
            if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
                stats["rejected_frames"] += 1
                continue

            zed.retrieve_image(image, sl.VIEW.LEFT)
            bgra = image.get_data()
            bgr = cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
            gray = cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)
            accepted_this_frame = 0

            if ids is not None:
                for corner, marker_number in zip(corners, ids.flatten()):
                    marker_id = int(marker_number)
                    if marker_id not in markers:
                        stats["foreign_markers"] += 1
                        continue

                    solutions = pnp_cam_optical_T_marker(corner[0], tag_size, K)
                    if len(solutions) < 2:
                        stats["rejected_markers"] += 1
                        continue

                    best, second = solutions[0], solutions[1]
                    err0, err1 = best[1], second[1]
                    if not math.isfinite(err0) or not math.isfinite(err1):
                        stats["rejected_markers"] += 1
                        continue
                    if err0 > args.max_reproj:
                        stats["rejected_markers"] += 1
                        continue

                    ratio = err0 / err1 if err1 > 1e-12 else 1.0
                    if ratio > args.ambiguity_ratio:
                        stats["rejected_markers"] += 1
                        continue

                    optical_T_marker = best[0]
                    candidate = base_T_cam_from_marker(markers[marker_id], optical_T_marker)
                    if not np.all(np.isfinite(optical_T_marker)) or not np.all(np.isfinite(candidate)):
                        stats["rejected_markers"] += 1
                        continue

                    candidates.append(candidate)
                    accepted_this_frame += 1
                    stats["accepted_markers"] += 1

                    cv2.aruco.drawDetectedMarkers(
                        bgr, [corner], np.array([[marker_id]], dtype=np.int32))
                    rvec, _ = cv2.Rodrigues(optical_T_marker[:3, :3])
                    cv2.drawFrameAxes(
                        bgr, K, None, rvec, optical_T_marker[:3, 3], tag_size * 0.5)
                    center = corner[0].mean(axis=0).astype(int)
                    cv2.putText(
                        bgr, "ID %d  %.3f px" % (marker_id, err0),
                        (center[0] - 55, center[1] - 12), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 255, 0), 2)

            if accepted_this_frame:
                stats["accepted_frames"] += 1
            else:
                stats["rejected_frames"] += 1

            last_debug = bgr.copy()
            if args.preview:
                cv2.imshow("base pose - ZED %d" % serial, bgr)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    stop = True
                    break
    finally:
        zed.close()
        if args.preview:
            cv2.destroyAllWindows()

    if args.save_debug and last_debug is not None:
        target = debug_path(args.save_debug, serial, camera_count)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), last_debug):
            raise RuntimeError("debug 이미지를 저장하지 못했습니다: %s" % target)
        print("debug 이미지:", target)

    return candidates, stats, stop


def rotation_difference_deg(a, b):
    r = a[:3, :3].T @ b[:3, :3]
    cosine = np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0)
    return math.degrees(math.acos(cosine))


def write_extrinsics(path, camera_poses, world_pose):
    transforms = []
    for child, pose in camera_poses:
        xyz, quat = mat_to_xyzquat(pose)
        transforms.append(("base", child, xyz, quat))
    xyz, quat = mat_to_xyzquat(world_pose)
    transforms.append(("base", "fusion_world", xyz, quat))

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        f.write("coordinate_system: RIGHT_HANDED_Z_UP_X_FWD\n")
        f.write("unit: METER\n")
        f.write("transforms:\n")
        for parent, child, xyz, quat in transforms:
            f.write("  - parent: %s\n" % parent)
            f.write("    child: %s\n" % child)
            f.write("    translation: [%s]\n" %
                    ", ".join("%.12g" % float(v) for v in xyz))
            f.write("    rotation_quat: [%s]\n" %
                    ", ".join("%.12g" % float(v) for v in quat))


def build_parser():
    parser = argparse.ArgumentParser(
        description="ArUco 큐브로 base 기준 ZED pose를 측정해 YAML로 저장")
    parser.add_argument("--datum", default="logs/base_cube_datum.json",
                        help="큐브 데이텀 JSON")
    parser.add_argument("--fusion-config", default="logs/fusion_zed360.json",
                        help="ZED360 Fusion config")
    parser.add_argument("--out", default="logs/base_cam_extrinsics.yaml",
                        help="static TF 좌표 YAML")
    parser.add_argument("--frames", type=int, default=60,
                        help="카메라별 확인할 프레임 수 (기본 60)")
    parser.add_argument("--max-reproj", type=float, default=1.0,
                        help="최대 재투영오차 px (기본 1.0)")
    parser.add_argument("--ambiguity-ratio", type=float, default=0.3,
                        help="IPPE err0/err1 최대값 (기본 0.3)")
    parser.add_argument("--serial-map", type=parse_serial_map,
                        default=parse_serial_map(DEFAULT_SERIAL_MAP),
                        help="SERIAL=NAME 목록; NAME 뒤에 _link를 붙임")
    parser.add_argument("--preview", action="store_true", help="주석 영상을 화면에 표시")
    parser.add_argument("--save-debug", metavar="PATH", help="마지막 주석 이미지를 저장")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames는 1 이상이어야 합니다")
    if not math.isfinite(args.max_reproj) or args.max_reproj <= 0.0:
        parser.error("--max-reproj는 양의 유한값이어야 합니다")
    if not math.isfinite(args.ambiguity_ratio) or not 0.0 < args.ambiguity_ratio < 1.0:
        parser.error("--ambiguity-ratio는 0과 1 사이여야 합니다")

    markers, tag_size, dictionary = load_datum(args.datum)
    detector = make_detector(dictionary)
    world_T_cams = read_world_poses(args.fusion_config)

    connected = {int(dev.serial_number) for dev in sl.Camera.get_device_list()
                 if int(getattr(dev, "serial_number", 0) or 0) != 0}
    serials = [serial for serial in args.serial_map
               if serial in connected and serial in world_T_cams]
    for serial in args.serial_map:
        if serial not in connected:
            print("건너뜀: serial %d 카메라가 연결되어 있지 않습니다" % serial)
        elif serial not in world_T_cams:
            print("건너뜀: serial %d가 fusion config에 없습니다" % serial)
    if not serials:
        raise SystemExit("측정할 카메라가 없습니다")

    camera_results = []
    world_results = []
    for serial in serials:
        print("\nserial %d 측정 시작" % serial)
        try:
            candidates, stats, stop = measure_camera(
                serial, markers, tag_size, detector, args, len(serials))
        except RuntimeError as exc:
            print("측정 실패:", exc)
            continue

        print("serial %d: 채택 %d프레임/%d마커, 폐기 %d프레임/%d마커, 외부 ID %d" % (
            serial, stats["accepted_frames"], stats["accepted_markers"],
            stats["rejected_frames"], stats["rejected_markers"],
            stats["foreign_markers"]))
        if not candidates:
            print("serial %d: 유효한 pose 후보가 없습니다" % serial)
            if stop:
                break
            continue

        base_T_cam = average_poses(candidates)
        estimated_world = base_T_world(base_T_cam, world_T_cams[serial])
        xyz, _ = mat_to_xyzquat(base_T_cam)
        print("serial %d base_T_cam xyz(m): %s" %
              (serial, np.round(xyz, 6).tolist()))
        camera_results.append((child_frame(args.serial_map[serial]), base_T_cam))
        world_results.append(estimated_world)
        if stop:
            break

    if not camera_results:
        raise SystemExit("유효한 카메라 pose를 얻지 못했습니다")

    if len(world_results) >= 2:
        translation_mm = np.linalg.norm(
            world_results[0][:3, 3] - world_results[1][:3, 3]) * 1000.0
        rotation_deg = rotation_difference_deg(world_results[0], world_results[1])
        print("base_T_world 교차검증: translation=%.3f mm, rotation=%.3f deg" %
              (translation_mm, rotation_deg))
    else:
        print("base_T_world 교차검증 생략: 유효한 카메라가 1대입니다")

    final_world = average_poses(world_results)
    write_extrinsics(args.out, camera_results, final_world)
    print("저장:", args.out)


if __name__ == "__main__":
    main()
