"""RoMaLab dev_e2e_piper 브랜치와 맞춘 ROS2 정책 계약이다."""

from __future__ import annotations

from typing import Any


# 계약을 확인한 RoMaLab 브랜치 이름이다.
ROMALAB_BRANCH = "dev_e2e_piper"

# 계약을 확인한 RoMaLab commit이다.
ROMALAB_COMMIT = "74c35ccb551e395e0201ac889d21dd4a4bd7ee14"

# 두 PC의 ROS2 DDS discovery에 사용할 domain id다.
ROS_DOMAIN_ID = 17

# 3인칭 JPEG 카메라 토픽이다.
THIRD_PERSON_TOPIC = "/piper/third_person/image"

# 손목 JPEG 카메라 토픽이다.
WRIST_TOPIC = "/piper/wrist/image"

# 로봇의 absolute 7차원 feedback 토픽이다.
STATE_TOPIC = "/piper/inference/slave_state"

# executor가 소비하는 absolute 7차원 action 토픽이다.
ACTION_TOPIC = "/piper/inference/output"

# 로봇 PC가 발행하는 로컬 enable gate 토픽이다.
GATE_TOPIC = "/piper/inference/ready"

# 원본 action chunk를 rollout bag에 남기는 토픽이다.
CHUNK_TOPIC = "/piper/inference/chunk"

# executor가 RUN 상태를 알리는 토픽이다.
EXECUTOR_READY_TOPIC = "/piper/policy_executor/ready"

# 카메라가 발행하는 압축 영상 메시지 형식이다.
CAMERA_MESSAGE_TYPE = "sensor_msgs/msg/CompressedImage"

# state와 step action이 사용하는 메시지 형식이다.
JOINT_STATE_MESSAGE_TYPE = "sensor_msgs/msg/JointState"

# 원본 action chunk가 사용하는 메시지 형식이다.
CHUNK_MESSAGE_TYPE = "trajectory_msgs/msg/JointTrajectory"

# 로봇 state와 action의 정확한 축 순서다.
JOINT_NAMES = (
    "joint1",
    "joint2",
    "joint3",
    "joint4",
    "joint5",
    "joint6",
    "gripper",
)

# RoMaLab이 발행하는 RGB 영상의 높이다.
CAMERA_HEIGHT = 480

# RoMaLab이 발행하는 RGB 영상의 너비다.
CAMERA_WIDTH = 640

# π0 action chunk를 실행하고 기록할 주기다.
CONTROL_FPS = 20

# π0가 한 번에 예측하는 action 개수다.
ACTION_HORIZON = 50

# Piper의 실제 state와 action 차원이다.
ROBOT_DIM = 7

# executor가 action을 stale로 판단하는 시간이다.
ACTION_TIMEOUT_SECONDS = 0.5

# executor가 로컬 gate를 stale로 판단하는 시간이다.
GATE_TIMEOUT_SECONDS = 1.0

# 향후 ROS2 adapter가 사용할 chunk frame_id 형식이다.
CHUNK_FRAME_ID_TEMPLATE = "chunk_{chunk_id}"

# 향후 ROS2 adapter가 만들 chunk point 사이의 상대 시간 간격이다.
CHUNK_POINT_PERIOD_SECONDS = 1.0 / CONTROL_FPS

# 향후 ROS2 adapter가 chunk point에서 비워 둘 trajectory field다.
CHUNK_EMPTY_POINT_FIELDS = ("velocities", "accelerations", "effort")

# RoMaLab recorder와 호환되도록 향후 adapter가 사용할 chunk QoS 계약이다.
CHUNK_QOS = {
    "history": "keep_last",
    "depth": 10,
    "reliability": "reliable",
    "durability": "volatile",
}


def build_romalab_policy_metadata() -> dict[str, Any]:
    """WebSocket client가 확인할 고정 RoMaLab ROS2 계약을 반환한다."""

    return {
        "romalab_branch": ROMALAB_BRANCH,
        "romalab_commit": ROMALAB_COMMIT,
        "ros_domain_id": ROS_DOMAIN_ID,
        "camera_topics": {
            "third_person": THIRD_PERSON_TOPIC,
            "wrist": WRIST_TOPIC,
        },
        "state_topic": STATE_TOPIC,
        "action_topic": ACTION_TOPIC,
        "gate_topic": GATE_TOPIC,
        "chunk_topic": CHUNK_TOPIC,
        "executor_ready_topic": EXECUTOR_READY_TOPIC,
        "camera_message_type": CAMERA_MESSAGE_TYPE,
        "joint_state_message_type": JOINT_STATE_MESSAGE_TYPE,
        "chunk_message_type": CHUNK_MESSAGE_TYPE,
        "joint_names": list(JOINT_NAMES),
        "camera_shape": [CAMERA_HEIGHT, CAMERA_WIDTH, 3],
        "control_fps": CONTROL_FPS,
        "action_horizon": ACTION_HORIZON,
        "robot_dim": ROBOT_DIM,
        "action_representation": "absolute",
        "action_units": ["rad", "rad", "rad", "rad", "rad", "rad", "m"],
        "action_timeout_seconds": ACTION_TIMEOUT_SECONDS,
        "gate_timeout_seconds": GATE_TIMEOUT_SECONDS,
        "chunk_contract": {
            "frame_id_template": CHUNK_FRAME_ID_TEMPLATE,
            "joint_names": list(JOINT_NAMES),
            "point_count": ACTION_HORIZON,
            "positions_units": ["rad", "rad", "rad", "rad", "rad", "rad", "m"],
            "time_from_start_rule": "point_index / control_fps",
            "point_period_seconds": CHUNK_POINT_PERIOD_SECONDS,
            "empty_point_fields": list(CHUNK_EMPTY_POINT_FIELDS),
            "qos": dict(CHUNK_QOS),
        },
    }
