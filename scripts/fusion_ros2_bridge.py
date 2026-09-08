#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fusion BODY_34 스켈레톤을 ROS2 토픽으로 발행한다."""

# PoseArray의 무효 관절은 BODY_34 인덱스를 지키기 위해 SDK의 NaN 값을 그대로 둔다.

import argparse
import os
import signal
import sys
import time


def _module_path(module):
    path = getattr(module, "__file__", None)
    return os.path.realpath(path) if path else "<경로 없음>"


def _under(path, root):
    if not path or not root:
        return False
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _environment_gate():
    loaded = {}
    errors = {}

    try:
        import numpy
        loaded["numpy"] = numpy
    except Exception as exc:
        errors["numpy"] = str(exc)

    try:
        import pyzed.sl
        loaded["pyzed"] = pyzed.sl
    except Exception as exc:
        errors["pyzed"] = str(exc)

    try:
        import rclpy
        loaded["rclpy"] = rclpy
    except Exception as exc:
        errors["rclpy"] = str(exc)

    paths = {
        name: _module_path(module) for name, module in loaded.items()
    }
    for name, error in errors.items():
        paths[name] = "<import 실패: %s>" % error

    conda_prefix = os.path.realpath(os.environ.get("CONDA_PREFIX", ""))
    numpy_ok = (
        "numpy" in loaded
        and os.path.basename(conda_prefix) == "zed"
        and _under(paths["numpy"], conda_prefix)
    )
    pyzed_ok = "pyzed" in loaded
    rclpy_ok = (
        "rclpy" in loaded
        and _under(paths["rclpy"], "/opt/ros/humble")
    )

    if not (numpy_ok and pyzed_ok and rclpy_ok):
        print("error: 브리지 실행 환경 검사를 통과하지 못했습니다.", file=sys.stderr)
        print("  numpy=%s" % paths.get("numpy", "<import 실패>"), file=sys.stderr)
        print("  pyzed=%s" % paths.get("pyzed", "<import 실패>"), file=sys.stderr)
        print("  rclpy=%s" % paths.get("rclpy", "<import 실패>"), file=sys.stderr)
        print("  scripts/run_bridge.sh 로 실행하세요.", file=sys.stderr)
        raise SystemExit(3)

    print(
        "환경 확인: rclpy=%s numpy=%s (conda zed) pyzed=%s" % (
            paths["rclpy"], loaded["numpy"].__version__, paths["pyzed"]
        )
    )


# 잘못된 환경에서는 argparse나 DDS 초기화보다 먼저 멈춘다.
_environment_gate()

import pyzed.sl as sl
import rclpy
from builtin_interfaces.msg import Duration as DurationMsg
from geometry_msgs.msg import Point, Pose, PoseArray
from rclpy.node import Node
from std_msgs.msg import Int32
from visualization_msgs.msg import Marker, MarkerArray

from zed_fusion_bodytrack import (
    COORD,
    UNIT,
    BODY_FORMAT,
    FUSED_BODY_FORMAT_NAME,
    BONES_34,
    _read_config,
    _open_sender,
    _init_fusion,
    _ok_keypoint,
    _tolist,
)


PALETTE = (
    (0.10, 0.65, 1.00),
    (1.00, 0.35, 0.25),
    (0.25, 0.85, 0.35),
    (0.95, 0.75, 0.15),
    (0.70, 0.35, 0.95),
    (0.10, 0.85, 0.80),
)


def _duration(seconds):
    whole = int(seconds)
    nanosec = int(round((seconds - whole) * 1e9))
    if nanosec == 1000000000:
        whole += 1
        nanosec = 0
    return DurationMsg(sec=whole, nanosec=nanosec)


def _marker(frame_id, stamp, lifetime, body_id, marker_id, marker_type):
    msg = Marker()
    msg.header.frame_id = frame_id
    msg.header.stamp = stamp
    msg.ns = "body_%d" % body_id
    msg.id = marker_id
    msg.type = marker_type
    msg.action = Marker.ADD
    msg.pose.orientation.w = 1.0
    msg.lifetime = _duration(lifetime)

    color = PALETTE[body_id % len(PALETTE)]
    msg.color.r, msg.color.g, msg.color.b = color
    msg.color.a = 1.0
    return msg


def _point(value):
    return Point(x=float(value[0]), y=float(value[1]), z=float(value[2]))


def build_marker_array(bodies_kp, frame_id, stamp, lifetime):
    msg = MarkerArray()

    clear = Marker()
    clear.header.frame_id = frame_id
    clear.header.stamp = stamp
    clear.action = Marker.DELETEALL
    clear.pose.orientation.w = 1.0
    clear.lifetime = _duration(lifetime)
    msg.markers.append(clear)

    for body_id, kp in bodies_kp:
        joints = _marker(
            frame_id, stamp, lifetime, body_id, 0, Marker.SPHERE_LIST)
        joints.scale.x = joints.scale.y = joints.scale.z = 0.05
        joints.points = [_point(point) for point in kp if _ok_keypoint(point)]

        bones = _marker(
            frame_id, stamp, lifetime, body_id, 1, Marker.LINE_LIST)
        bones.scale.x = 0.02
        for a, b in BONES_34:
            if (a < len(kp) and b < len(kp)
                    and _ok_keypoint(kp[a]) and _ok_keypoint(kp[b])):
                bones.points.extend((_point(kp[a]), _point(kp[b])))

        msg.markers.extend((joints, bones))

    return msg


def build_pose_array(kp, frame_id, stamp):
    msg = PoseArray()
    msg.header.frame_id = frame_id
    msg.header.stamp = stamp
    if kp is None:
        return msg
    if len(kp) != 34:
        raise RuntimeError(
            "Fusion %s keypoint가 34개가 아닙니다: %d" %
            (FUSED_BODY_FORMAT_NAME, len(kp)))

    for point in kp:
        pose = Pose()
        pose.position.x = float(point[0])
        pose.position.y = float(point[1])
        pose.position.z = float(point[2])
        pose.orientation.w = 1.0
        msg.poses.append(pose)
    return msg


def build_body_count(count):
    return Int32(data=int(count))


def _parser():
    parser = argparse.ArgumentParser(
        description="Dual ZED-M Fusion BODY_34 ROS2 bridge")
    parser.add_argument(
        "--config", required=True, help="ZED360 Fusion config JSON")
    parser.add_argument(
        "--res", default="HD720",
        help="HD720 fixed for this two-ZED-M USB setup")
    parser.add_argument(
        "--fps", type=int, default=30,
        help="default 30; this rig cannot sustain 2xHD720@60")
    parser.add_argument(
        "--depth", default="NEURAL",
        help="NEURAL | NEURAL_LIGHT | PERFORMANCE")
    parser.add_argument(
        "--conf", type=int, default=40,
        help="sender detection_confidence_threshold")
    parser.add_argument("--min-keypoints", type=int, default=7)
    parser.add_argument("--min-cameras", type=int, default=1)
    parser.add_argument("--smoothing", type=float, default=0.1)
    parser.add_argument("--retry-count", type=int, default=3)
    parser.add_argument("--retry-wait", type=float, default=1.0)
    parser.add_argument("--verbose-fusion", action="store_true")
    parser.add_argument(
        "--duration", type=float, default=0,
        help="seconds; 0 = until Ctrl-C")
    parser.add_argument("--frame-id", default="fusion_world")
    parser.add_argument("--topic-prefix", default="/human")
    parser.add_argument("--marker-lifetime", type=float, default=0.2)
    parser.add_argument("--node-name", default="fusion_skeleton_bridge")
    return parser


def _topic(prefix, name):
    prefix = prefix.rstrip("/")
    return "%s/%s" % (prefix, name) if prefix else "/%s" % name


def run(args):
    senders = []
    fusion = None
    node = None

    rclpy.init()
    try:
        node = Node(args.node_name)
        marker_pub = node.create_publisher(
            MarkerArray, _topic(args.topic_prefix, "skeleton_markers"), 10)
        pose_pub = node.create_publisher(
            PoseArray, _topic(args.topic_prefix, "skeleton_poses"), 10)
        count_pub = node.create_publisher(
            Int32, _topic(args.topic_prefix, "body_count"), 10)

        configs = _read_config(args.config)
        serials = [int(conf.serial_number) for conf in configs]
        print("config cameras:", serials)
        print(
            "bridge: sender=%s fused=%s frame=%s" %
            (BODY_FORMAT, FUSED_BODY_FORMAT_NAME, args.frame_id))

        for conf in configs:
            senders.append(_open_sender(
                conf, args.res, args.fps, args.depth, args.conf,
                args.retry_count, args.retry_wait))

        # 첫 프레임이 있어야 shared-memory sender를 Fusion이 안정적으로 구독한다.
        for sender in senders:
            if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                sender["camera"].retrieve_bodies(
                    sender["bodies"], sender["runtime"])

        fusion, identifiers = _init_fusion(configs, args.verbose_fusion)
        runtime = sl.BodyTrackingFusionRuntimeParameters()
        runtime.skeleton_minimum_allowed_keypoints = int(args.min_keypoints)
        runtime.skeleton_minimum_allowed_camera = int(args.min_cameras)
        runtime.skeleton_smoothing = float(args.smoothing)
        fused = sl.Bodies()

        stop = {"value": False}
        signal.signal(
            signal.SIGINT, lambda *_: stop.__setitem__("value", True))

        n_frames = 0
        warned_multiple = False
        t0 = last = time.time()
        while not stop["value"] and rclpy.ok():
            if args.duration and time.time() - t0 >= args.duration:
                break

            for sender in senders:
                if sender["camera"].grab() <= sl.ERROR_CODE.SUCCESS:
                    sender["camera"].retrieve_bodies(
                        sender["bodies"], sender["runtime"])

            if fusion.process() != sl.FUSION_ERROR_CODE.SUCCESS:
                continue
            status = fusion.retrieve_bodies(
                fused, runtime, sl.CameraIdentifier(),
                sl.FUSION_REFERENCE_FRAME.WORLD)
            if status != sl.FUSION_ERROR_CODE.SUCCESS:
                continue

            bodies_kp = [
                (int(body.id), _tolist(body.keypoint))
                for body in fused.body_list
            ]
            if len(bodies_kp) > 1 and not warned_multiple:
                node.get_logger().warning(
                    "사람이 여러 명입니다. skeleton_poses는 첫 번째 한 명만 발행합니다.")
                warned_multiple = True

            stamp = node.get_clock().now().to_msg()
            marker_pub.publish(build_marker_array(
                bodies_kp, args.frame_id, stamp, args.marker_lifetime))
            pose_pub.publish(build_pose_array(
                bodies_kp[0][1] if bodies_kp else None,
                args.frame_id, stamp))
            count_pub.publish(build_body_count(len(bodies_kp)))
            rclpy.spin_once(node, timeout_sec=0.0)

            n_frames += 1
            now = time.time()
            if now - last >= 1.0:
                fps_live = n_frames / (now - t0) if now > t0 else 0.0
                print(
                    "\rframes=%d ~%.1ffps live=%d cameras=%d   " %
                    (n_frames, fps_live, len(bodies_kp), len(identifiers)),
                    end="", flush=True)
                last = now

        elapsed = time.time() - t0
        print(
            "\ndone. %d frames in %.1fs (~%.1f fps)" %
            (n_frames, elapsed, n_frames / elapsed if elapsed else 0.0))
    finally:
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
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main():
    parser = _parser()
    args = parser.parse_args()
    if args.fps != 30:
        parser.error(
            "Fusion on this hardware is fixed to 30 fps; got --fps %d" %
            args.fps)
    if args.marker_lifetime < 0:
        parser.error("--marker-lifetime은 0 이상이어야 합니다")
    run(args)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print("error:", exc)
        sys.exit(1)
