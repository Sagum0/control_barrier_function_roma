#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""측정 YAML의 좌표 상수를 /tf_static으로 한 번에 발행한다."""

import math

import rclpy
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
import yaml


def _numbers(value, length, name):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError("%s는 숫자 %d개의 목록이어야 합니다" % (name, length))
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("%s에 NaN 또는 inf가 있습니다" % name)
    return result


def load_transforms(path):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or not isinstance(data.get("transforms"), list):
        raise ValueError("YAML에 transforms 목록이 없습니다")
    if data.get("coordinate_system") != "RIGHT_HANDED_Z_UP_X_FWD":
        raise ValueError("coordinate_system은 RIGHT_HANDED_Z_UP_X_FWD여야 합니다")
    if data.get("unit") != "METER":
        raise ValueError("unit은 METER여야 합니다")

    result = []
    children = set()
    for i, item in enumerate(data["transforms"]):
        if not isinstance(item, dict):
            raise ValueError("transforms[%d]가 객체가 아닙니다" % i)
        parent = str(item.get("parent", "")).strip()
        child = str(item.get("child", "")).strip()
        if not parent or not child or parent == child:
            raise ValueError("transforms[%d]의 parent/child가 올바르지 않습니다" % i)
        if child in children:
            raise ValueError("child frame %s가 중복되었습니다" % child)
        children.add(child)

        translation = _numbers(item.get("translation"), 3, "%s translation" % child)
        quaternion = _numbers(item.get("rotation_quat"), 4, "%s rotation_quat" % child)
        norm = math.sqrt(sum(v * v for v in quaternion))
        if norm < 1e-12 or abs(norm - 1.0) > 1e-3:
            raise ValueError("%s quaternion norm %.9f가 1이 아닙니다" % (child, norm))

        # 실측 파일의 반올림 오차는 없애되, 큰 오차를 조용히 숨기지는 않는다.
        quaternion = [v / norm for v in quaternion]
        result.append((parent, child, translation, quaternion))

    if not result:
        raise ValueError("발행할 transform이 없습니다")
    return result


class StaticTfNode(Node):

    def __init__(self):
        super().__init__("cbf_base_static_tf")
        default_path = get_package_share_directory("cbf_base_tf") + \
            "/config/base_cam_extrinsics.yaml"
        self.declare_parameter("extrinsics", default_path)
        path = self.get_parameter("extrinsics").get_parameter_value().string_value

        broadcaster = StaticTransformBroadcaster(self)
        stamp = self.get_clock().now().to_msg()
        messages = []
        for parent, child, translation, quaternion in load_transforms(path):
            msg = TransformStamped()
            msg.header.stamp = stamp
            msg.header.frame_id = parent
            msg.child_frame_id = child
            msg.transform.translation.x = translation[0]
            msg.transform.translation.y = translation[1]
            msg.transform.translation.z = translation[2]
            msg.transform.rotation.x = quaternion[0]
            msg.transform.rotation.y = quaternion[1]
            msg.transform.rotation.z = quaternion[2]
            msg.transform.rotation.w = quaternion[3]
            messages.append(msg)

        # 리스트로 한 번에 보내야 세 static edge가 같은 시점에 준비된다.
        broadcaster.sendTransform(messages)
        self._broadcaster = broadcaster
        self.get_logger().info("static TF %d개 발행: %s" % (len(messages), path))


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = StaticTfNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
