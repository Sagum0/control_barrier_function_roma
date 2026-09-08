#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""발행 중인 base 좌표 변환을 실측 YAML과 대조한다."""

import argparse
import math
import os
import sys
import time

import rclpy
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.time import Time
from tf2_geometry_msgs import do_transform_point
from tf2_ros import Buffer, TransformException, TransformListener
import yaml


def _numbers(value, length, name):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError("%s는 숫자 %d개의 목록이어야 합니다" % (name, length))
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("%s에 NaN 또는 inf가 있습니다" % name)
    return result


def load_base_to_world(path):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or not isinstance(data.get("transforms"), list):
        raise ValueError("YAML에 transforms 목록이 없습니다")
    if data.get("coordinate_system") != "RIGHT_HANDED_Z_UP_X_FWD":
        raise ValueError("coordinate_system은 RIGHT_HANDED_Z_UP_X_FWD여야 합니다")
    if data.get("unit") != "METER":
        raise ValueError("unit은 METER여야 합니다")

    for item in data["transforms"]:
        if (isinstance(item, dict) and item.get("parent") == "base"
                and item.get("child") == "fusion_world"):
            xyz = _numbers(item.get("translation"), 3, "translation")
            quat = _numbers(item.get("rotation_quat"), 4, "rotation_quat")
            norm = math.sqrt(sum(v * v for v in quat))
            if norm < 1e-12 or abs(norm - 1.0) > 1e-3:
                raise ValueError("rotation_quat norm %.9f가 1이 아닙니다" % norm)
            return xyz, [v / norm for v in quat]

    raise ValueError("base→fusion_world transform이 없습니다")


def transform_by_hand(point, xyz, quat):
    x, y, z, w = quat
    px, py, pz = point
    return [
        xyz[0] + (1 - 2 * (y * y + z * z)) * px
        + 2 * (x * y - z * w) * py
        + 2 * (x * z + y * w) * pz,
        xyz[1] + 2 * (x * y + z * w) * px
        + (1 - 2 * (x * x + z * z)) * py
        + 2 * (y * z - x * w) * pz,
        xyz[2] + 2 * (x * z - y * w) * px
        + 2 * (y * z + x * w) * py
        + (1 - 2 * (x * x + y * y)) * pz,
    ]


def lookup(node, buffer, timeout):
    deadline = time.monotonic() + timeout
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=min(0.05, max(0.0, deadline - time.monotonic())))
        if buffer.can_transform("base", "fusion_world", Time()):
            return buffer.lookup_transform("base", "fusion_world", Time())
    raise TransformException("base ← fusion_world TF를 %g초 안에 찾지 못했습니다" % timeout)


def is_placeholder(transform):
    t = transform.transform.translation
    q = transform.transform.rotation
    return (
        max(abs(t.x), abs(t.y), abs(t.z)) <= 1e-12
        and max(abs(q.x), abs(q.y), abs(q.z)) <= 1e-12
        and abs(abs(q.w) - 1.0) <= 1e-12
    )


def check_points(transform, xyz, quat):
    points = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.37, -0.42, 1.15),
    )
    worst = 0.0
    worst_point = None

    for point in points:
        msg = PointStamped()
        msg.header.frame_id = "fusion_world"
        msg.point.x, msg.point.y, msg.point.z = point
        result = do_transform_point(msg, transform).point
        actual = (result.x, result.y, result.z)
        expected = transform_by_hand(point, xyz, quat)
        error = max(abs(a - b) for a, b in zip(actual, expected))
        if error > worst:
            worst = error
            worst_point = point

    if worst > 1e-6:
        raise ValueError(
            "TF/YAML 변환 불일치: point=%s max_error=%.9g" %
            (worst_point, worst))
    return worst


def _parser():
    parser = argparse.ArgumentParser(
        description="base ← fusion_world static TF를 실측 YAML과 대조")
    parser.add_argument(
        "--extrinsics", default="logs/base_cam_extrinsics.yaml",
        help="measure_base_cam.py가 만든 실측 YAML")
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


def main():
    args = _parser().parse_args()
    if args.timeout <= 0:
        print("error: --timeout은 0보다 커야 합니다", file=sys.stderr)
        return 1

    try:
        xyz, quat = load_base_to_world(args.extrinsics)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print("error: extrinsics를 읽지 못했습니다: %s" % exc, file=sys.stderr)
        return 1

    rclpy.init()
    node = Node("check_tf_to_base")
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    try:
        try:
            transform = lookup(node, buffer, args.timeout)
        except TransformException as exc:
            print("error:", exc, file=sys.stderr)
            print(
                "실측 YAML 절대경로로 static TF를 실행했는지 확인하세요:\n"
                "  ros2 launch cbf_base_tf base_tf.launch.py extrinsics:=%s" %
                os.path.abspath(args.extrinsics), file=sys.stderr)
            return 1

        if is_placeholder(transform):
            print(
                "warning: placeholder YAML이 발행되고 있습니다. "
                "launch에 실측 extrinsics 절대경로를 넘겼는지 확인하세요.")

        try:
            worst = check_points(transform, xyz, quat)
        except ValueError as exc:
            print("error:", exc, file=sys.stderr)
            return 1

        print("OK: base ← fusion_world, 5 points max_error=%.3g" % worst)
        return 0
    finally:
        del listener
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
