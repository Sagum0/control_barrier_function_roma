#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_yaml = get_package_share_directory("cbf_base_tf") + \
        "/config/base_cam_extrinsics.yaml"
    extrinsics = LaunchConfiguration("extrinsics")

    return LaunchDescription([
        DeclareLaunchArgument(
            "extrinsics",
            default_value=default_yaml,
            description="measure_base_cam.py가 만든 좌표 YAML",
        ),
        Node(
            package="cbf_base_tf",
            executable="static_tf_node",
            name="cbf_base_static_tf",
            output="screen",
            parameters=[{"extrinsics": extrinsics}],
        ),
    ])
