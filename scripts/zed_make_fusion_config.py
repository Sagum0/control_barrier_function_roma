#!/usr/bin/env python3
"""수동 pose로 ZED Fusion config JSON을 생성한다.

정량 융합에는 ZED360 캘리브레이션 결과를 사용해야 한다. 이 스크립트의
출력은 두 카메라 Fusion 파이프라인을 먼저 기동하기 위한 부트스트랩용이다.

예:
  python3 scripts/zed_make_fusion_config.py --output logs/fusion_manual.json
  python3 scripts/zed_make_fusion_config.py \
    --serials 13870389,19321109 \
    --left-translation 0,0,0 --left-rpy 0,0,0 \
    --right-translation 0,-1.5,0 --right-rpy 0,0,180 \
    --output logs/fusion_manual.json
"""
import argparse
import json
import math
import os
import sys

import pyzed.sl as sl

COORD = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD
UNIT = sl.UNIT.METER
DEFAULT_SERIALS = (13870389, 19321109)


def _parse_triplet(text, name):
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("%s must be three comma-separated numbers" % name)
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("%s has a non-numeric value: %s" % (name, exc))


def _parse_serials(text):
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--serials must contain exactly two serial numbers")
    try:
        return tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--serials has a non-integer value: %s" % exc)


def _pose(translation, rpy_deg):
    tx, ty, tz = translation
    roll, pitch, yaw = [math.radians(value) for value in rpy_deg]

    tr = sl.Translation()
    tr.init_vector(tx, ty, tz)

    rot = sl.Rotation()
    rot.set_euler_angles(roll, pitch, yaw, True)

    transform = sl.Transform()
    transform.init_rotation_translation(rot, tr)
    return transform


def _config(serial, translation, rpy_deg, override_gravity):
    conf = sl.FusionConfiguration()
    conf.serial_number = int(serial)
    conf.communication_parameters.set_for_shared_memory()
    conf.input_type.set_from_serial_number(int(serial))
    conf.pose = _pose(translation, rpy_deg)
    conf.override_gravity = bool(override_gravity)
    return conf


def _safe_unlink(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Create a manual ZED Fusion config JSON")
    parser.add_argument("--serials", type=_parse_serials, default=DEFAULT_SERIALS,
                        help="left,right serials; default: 13870389,19321109")
    parser.add_argument("--left-translation", type=lambda v: _parse_triplet(v, "--left-translation"),
                        default=(0.0, 0.0, 0.0), help="x,y,z meters")
    parser.add_argument("--left-rpy", type=lambda v: _parse_triplet(v, "--left-rpy"),
                        default=(0.0, 0.0, 0.0), help="roll,pitch,yaw degrees")
    parser.add_argument("--right-translation", type=lambda v: _parse_triplet(v, "--right-translation"),
                        default=(0.0, -1.5, 0.0), help="x,y,z meters")
    parser.add_argument("--right-rpy", type=lambda v: _parse_triplet(v, "--right-rpy"),
                        default=(0.0, 0.0, 180.0), help="roll,pitch,yaw degrees")
    parser.add_argument("--output", default="logs/fusion_manual.json")
    parser.add_argument("--no-override-gravity", action="store_true",
                        help="leave Fusion override_gravity false; default true for measured absolute poses")
    parser.add_argument("--force", action="store_true", help="overwrite output if it already exists")
    args = parser.parse_args()

    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    if os.path.exists(output) and not args.force:
        print("output exists; pass --force to overwrite:", output)
        sys.exit(2)
    if args.force:
        _safe_unlink(output)

    override_gravity = not args.no_override_gravity
    left_serial, right_serial = args.serials
    configs = [
        _config(left_serial, args.left_translation, args.left_rpy, override_gravity),
        _config(right_serial, args.right_translation, args.right_rpy, override_gravity),
    ]

    sl.write_configuration_file(output, configs, COORD, UNIT)
    readback = sl.read_fusion_configuration_file(output, COORD, UNIT)
    if len(readback) != 2:
        print("round-trip failed: expected 2 configs, got", len(readback))
        sys.exit(1)

    sidecar = {
        "warning": "manual Fusion config; use ZED360 output for quantitative skeleton fusion",
        "coordinate_system": "RIGHT_HANDED_Z_UP_X_FWD",
        "unit": "METER",
        "left": {
            "serial": left_serial,
            "translation_m": list(args.left_translation),
            "rpy_deg": list(args.left_rpy),
        },
        "right": {
            "serial": right_serial,
            "translation_m": list(args.right_translation),
            "rpy_deg": list(args.right_rpy),
        },
        "override_gravity": override_gravity,
        "fusion_config": output,
    }
    sidecar_path = os.path.splitext(output)[0] + "_manual_pose.json"
    with open(sidecar_path, "w") as sf:
        json.dump(sidecar, sf, ensure_ascii=False, indent=2)

    print("wrote Fusion config:", output)
    print("wrote manual pose note:", sidecar_path)
    print("readback serials:", [int(conf.serial_number) for conf in readback])


if __name__ == "__main__":
    main()
