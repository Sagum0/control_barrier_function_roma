"""기존 vla_pipeline LeRobot 0.6 gRPC 호환 표면의 CPU 회귀 테스트다."""

from __future__ import annotations

import pickle
from types import SimpleNamespace
import unittest

import grpc
import numpy as np

from piper_vla.inference.lerobot_grpc import (
    LEROBOT_GRPC_SERVICE_NAME,
    RemotePolicyConfigCompat,
    TimedObservationCompat,
    WIRE_TYPES,
    create_lerobot_grpc_server,
    lerobot_pickle_dumps,
    validate_remote_policy_config,
)


# 테스트와 실제 config가 공유하는 정확한 단일 task prompt다.
TEST_PROMPT = "pick up the green blocks one at a time and place them in the white box"


class _FakePolicy:
    """GPU 없이 canonical observation과 action 응답을 검사하는 policy다."""

    def infer(self, observation):
        """state 첫 값을 넣은 고정 `(50, 7)` action을 반환한다."""

        if observation["prompt"] != TEST_PROMPT:
            raise AssertionError("prompt가 canonical policy까지 전달되지 않았습니다.")
        actions = np.zeros((50, 7), dtype=np.float32)
        actions[:, 0] = observation["observation/state"][0]
        return {"actions": actions}


def _remote_config(actions_per_chunk: int = 32) -> RemotePolicyConfigCompat:
    """기존 PiperBridgeRobot의 dataset feature 계약을 만든다."""

    return RemotePolicyConfigCompat(
        policy_type="pi0",
        pretrained_name_or_path="two_block_pnp_b32_vt_s30000_r002/30000",
        lerobot_features={
            "observation.state": {
                "dtype": "float32",
                "shape": (7,),
                "names": [
                    "joint_1.pos",
                    "joint_2.pos",
                    "joint_3.pos",
                    "joint_4.pos",
                    "joint_5.pos",
                    "joint_6.pos",
                    "gripper.pos",
                ],
            },
            "observation.images.third_person": {
                "dtype": "image",
                "shape": (480, 640, 3),
                "names": ["height", "width", "channels"],
                "info": {"is_depth_map": False},
            },
            "observation.images.wrist": {
                "dtype": "image",
                "shape": (480, 640, 3),
                "names": ["height", "width", "channels"],
                "info": {"is_depth_map": False},
            },
        },
        actions_per_chunk=actions_per_chunk,
        device="cuda",
    )


def _timed_observation() -> TimedObservationCompat:
    """실제 client가 보내는 raw key와 RGB dtype을 갖춘 관측을 만든다."""

    raw = {
        **{f"joint_{index}.pos": float(index) for index in range(1, 7)},
        "gripper.pos": 0.04,
        "third_person": np.zeros((480, 640, 3), dtype=np.uint8),
        "wrist": np.zeros((480, 640, 3), dtype=np.uint8),
        "task": TEST_PROMPT,
    }
    return TimedObservationCompat(
        timestamp=1000.0,
        timestep=7,
        observation=raw,
        must_go=True,
    )


def _server_settings(actions_per_chunk: int = 32) -> SimpleNamespace:
    """CPU loopback용 server와 async client 계약을 만든다."""

    return SimpleNamespace(
        server=SimpleNamespace(host="127.0.0.1", port=0),
        client=SimpleNamespace(
            observation_queue_timeout_seconds=1.0,
            actions_per_chunk=actions_per_chunk,
            fps=20,
        ),
    )


class LeRobotGrpcCompatibilityTest(unittest.TestCase):
    """실제 gRPC method path와 pickle DTO 호환성을 함께 검사한다."""

    def test_loopback_returns_lerobot_timed_actions(self) -> None:
        """공식 client와 같은 네 RPC 순서로 `(N, 7)` action chunk를 받는다."""

        settings = _server_settings()
        server = create_lerobot_grpc_server(_FakePolicy(), settings)
        server.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{server.bound_port}")
        try:
            ready = channel.unary_unary(
                "/transport.AsyncInference/Ready",
                request_serializer=lambda value: value.SerializeToString(),
                response_deserializer=WIRE_TYPES.Empty.FromString,
            )
            instructions = channel.unary_unary(
                "/transport.AsyncInference/SendPolicyInstructions",
                request_serializer=lambda value: value.SerializeToString(),
                response_deserializer=WIRE_TYPES.Empty.FromString,
            )
            observations = channel.stream_unary(
                "/transport.AsyncInference/SendObservations",
                request_serializer=lambda value: value.SerializeToString(),
                response_deserializer=WIRE_TYPES.Empty.FromString,
            )
            get_actions = channel.unary_unary(
                "/transport.AsyncInference/GetActions",
                request_serializer=lambda value: value.SerializeToString(),
                response_deserializer=WIRE_TYPES.Actions.FromString,
            )

            ready(WIRE_TYPES.Empty(), timeout=2.0)
            instructions(
                WIRE_TYPES.PolicySetup(data=lerobot_pickle_dumps(_remote_config())),
                timeout=2.0,
            )
            observations(
                iter(
                    [
                        WIRE_TYPES.Observation(
                            transfer_state=3,
                            data=lerobot_pickle_dumps(_timed_observation()),
                        )
                    ]
                ),
                timeout=2.0,
            )
            response = get_actions(WIRE_TYPES.Empty(), timeout=5.0)
            timed_actions = pickle.loads(response.data)  # nosec - local test payload
            self.assertEqual(len(timed_actions), 32)
            self.assertEqual(timed_actions[0].get_timestep(), 7)
            self.assertEqual(timed_actions[-1].get_timestep(), 38)
            self.assertEqual(tuple(timed_actions[0].get_action().shape), (7,))
            self.assertAlmostEqual(
                timed_actions[1].get_timestamp() - timed_actions[0].get_timestamp(),
                0.05,
            )
            self.assertEqual(float(timed_actions[0].get_action()[0]), 1.0)
        finally:
            channel.close()
            server.stop()

    def test_wire_descriptor_matches_lerobot_v060_contract(self) -> None:
        """공식 v0.6.0 proto의 package, field 번호, RPC 이름을 고정한다."""

        observation = WIRE_TYPES.Observation.DESCRIPTOR
        self.assertEqual(observation.full_name, "transport.Observation")
        self.assertEqual(observation.fields_by_name["transfer_state"].number, 1)
        self.assertEqual(observation.fields_by_name["data"].number, 2)
        self.assertEqual(WIRE_TYPES.Actions.DESCRIPTOR.fields_by_name["data"].number, 1)
        self.assertEqual(WIRE_TYPES.PolicySetup.DESCRIPTOR.fields_by_name["data"].number, 1)
        self.assertEqual(LEROBOT_GRPC_SERVICE_NAME, "transport.AsyncInference")

    def test_remote_feature_semantics_are_exact(self) -> None:
        """축 이름·dtype·rename_map이 다른 client handshake를 거부한다."""

        config = _remote_config()
        validate_remote_policy_config(config)

        with self.assertRaisesRegex(ValueError, "server YAML"):
            validate_remote_policy_config(
                config, expected_actions_per_chunk=50
            )

        config = _remote_config()
        config.lerobot_features["observation.state"]["dtype"] = "float64"
        with self.assertRaisesRegex(ValueError, "dtype"):
            validate_remote_policy_config(config)

        config = _remote_config()
        config.lerobot_features["observation.state"]["names"] = ["wrong"] * 7
        with self.assertRaisesRegex(ValueError, "names"):
            validate_remote_policy_config(config)

        config = _remote_config()
        config.rename_map = {"third_person": "camera1"}
        with self.assertRaisesRegex(ValueError, "rename_map"):
            validate_remote_policy_config(config)

    def test_invalid_policy_type_is_rejected(self) -> None:
        """기존 server에 다른 정책군을 요청하면 gRPC INVALID_ARGUMENT가 된다."""

        settings = _server_settings()
        server = create_lerobot_grpc_server(_FakePolicy(), settings)
        server.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{server.bound_port}")
        try:
            ready = channel.unary_unary(
                "/transport.AsyncInference/Ready",
                request_serializer=lambda value: value.SerializeToString(),
                response_deserializer=WIRE_TYPES.Empty.FromString,
            )
            instructions = channel.unary_unary(
                "/transport.AsyncInference/SendPolicyInstructions",
                request_serializer=lambda value: value.SerializeToString(),
                response_deserializer=WIRE_TYPES.Empty.FromString,
            )
            ready(WIRE_TYPES.Empty(), timeout=2.0)
            config = _remote_config()
            config.policy_type = "smolvla"
            with self.assertRaises(grpc.RpcError) as captured:
                instructions(
                    WIRE_TYPES.PolicySetup(data=lerobot_pickle_dumps(config)),
                    timeout=2.0,
                )
            self.assertEqual(captured.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)
        finally:
            channel.close()
            server.stop()


if __name__ == "__main__":
    unittest.main()
