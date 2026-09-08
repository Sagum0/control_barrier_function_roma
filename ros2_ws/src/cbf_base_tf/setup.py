#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from glob import glob
from setuptools import find_packages, setup


package_name = "cbf_base_tf"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="cbf_ws",
    maintainer_email="noreply@example.com",
    description="base 기준 ZED와 Fusion world static TF 발행기",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "static_tf_node = cbf_base_tf.static_tf_node:main",
        ],
    },
)
