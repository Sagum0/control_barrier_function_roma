"""기존 vla_pipeline용 LeRobot 0.6 AsyncInference gRPC 호환 서버다.

원본 프로토콜의 네 RPC와 pickle wire object 이름은 유지하되, 실제 정책 로딩과
추론은 이 workspace의 검증된 OpenPI π0 policy가 담당한다.
"""

from __future__ import annotations

from concurrent import futures
import dataclasses
from enum import Enum
import importlib
import io
import logging
import math
from numbers import Real
import pickle
from queue import Empty, Queue
import sys
import threading
import types
from typing import Any, Iterable, Mapping, Protocol

import numpy as np
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from piper_vla.inference.observation import (
    build_canonical_observation,
    validate_policy_output,
)
from piper_vla.inference.romalab_contract import ACTION_HORIZON, ROBOT_DIM


# LeRobot 0.6 proto package와 service의 정확한 이름이다.
LEROBOT_GRPC_SERVICE_NAME = "transport.AsyncInference"

# 기존 client가 pickle에서 참조하는 helper module 경로다.
LEROBOT_HELPERS_MODULE = "lerobot.async_inference.helpers"

# 기존 client가 pickle에서 참조하는 feature type module 경로다.
LEROBOT_TYPES_MODULE = "lerobot.configs.types"

# 관측 pickle과 두 RGB 배열을 충분히 담되 비정상 메모리 사용을 막는 상한이다.
MAX_PICKLE_BYTES = 32 * 1024 * 1024

# gRPC 단일 메시지의 송수신 상한이다.
MAX_GRPC_MESSAGE_BYTES = 32 * 1024 * 1024

# LeRobot transport.proto TransferState 값이다.
TRANSFER_UNKNOWN = 0

# 다중 chunk 전송의 첫 조각 값이다.
TRANSFER_BEGIN = 1

# 다중 chunk 전송의 중간 조각 값이다.
TRANSFER_MIDDLE = 2

# 마지막 또는 단일 조각 값이다.
TRANSFER_END = 3

# 기존 PiperBridgeRobot이 내보내는 state key 순서다.
CLIENT_STATE_KEYS = (
    "joint_1.pos",
    "joint_2.pos",
    "joint_3.pos",
    "joint_4.pos",
    "joint_5.pos",
    "joint_6.pos",
    "gripper.pos",
)

# 기존 PiperBridgeRobot의 두 raw image key다.
CLIENT_THIRD_PERSON_KEY = "third_person"

# 기존 PiperBridgeRobot의 손목 raw image key다.
CLIENT_WRIST_KEY = "wrist"

# LeRobot client가 task 문자열을 넣는 raw key다.
CLIENT_TASK_KEY = "task"

# client가 보내야 할 LeRobot dataset feature key다.
EXPECTED_LEROBOT_FEATURE_KEYS = frozenset(
    {
        "observation.state",
        "observation.images.third_person",
        "observation.images.wrist",
    }
)

# 기존 PiperBridgeRobot이 client handshake에서 보내는 state feature 계약이다.
EXPECTED_STATE_FEATURE = {
    "dtype": "float32",
    "shape": (ROBOT_DIM,),
    "names": list(CLIENT_STATE_KEYS),
}

# 기존 PiperBridgeRobot이 client handshake에서 보내는 RGB feature 계약이다.
EXPECTED_IMAGE_FEATURE = {
    "dtype": "image",
    "shape": (480, 640, 3),
    "names": ["height", "width", "channels"],
    "info": {"is_depth_map": False},
}


class PolicyProtocol(Protocol):
    """OpenPI policy wrapper가 제공해야 할 최소 인터페이스다."""

    def infer(self, observation: Mapping[str, Any]) -> Mapping[str, Any]:
        """한 canonical observation에서 action chunk를 반환한다."""


class ServerProtocol(Protocol):
    """policy_server dispatcher가 공통으로 사용할 server 인터페이스다."""

    def serve_forever(self) -> None:
        """종료될 때까지 요청을 처리한다."""


class FeatureTypeCompat(str, Enum):
    """RemotePolicyConfig pickle 복원에 필요한 LeRobot feature enum이다."""

    STATE = "STATE"
    VISUAL = "VISUAL"
    ENV = "ENV"
    ACTION = "ACTION"
    REWARD = "REWARD"
    LANGUAGE = "LANGUAGE"


@dataclasses.dataclass
class PolicyFeatureCompat:
    """RemotePolicyConfig에 포함될 수 있는 LeRobot PolicyFeature 호환형이다."""

    type: FeatureTypeCompat
    shape: tuple[int, ...]


@dataclasses.dataclass
class RemotePolicyConfigCompat:
    """LeRobot 0.6 client가 SendPolicyInstructions로 보내는 설정이다."""

    policy_type: str
    pretrained_name_or_path: str
    lerobot_features: dict[str, Any]
    actions_per_chunk: int
    device: str = "cpu"
    rename_map: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class TimedObservationCompat:
    """LeRobot 0.6 client가 보내는 timestamp 포함 raw observation이다."""

    timestamp: float
    timestep: int
    observation: dict[str, Any]
    must_go: bool = False

    def get_timestamp(self) -> float:
        """client가 기록한 Unix timestamp를 반환한다."""

        return self.timestamp

    def get_timestep(self) -> int:
        """해당 관측이 기준으로 삼은 action timestep을 반환한다."""

        return self.timestep

    def get_observation(self) -> dict[str, Any]:
        """PiperBridgeRobot의 raw observation을 반환한다."""

        return self.observation


@dataclasses.dataclass
class TimedActionCompat:
    """기존 client가 action queue에 바로 넣을 수 있는 action 한 점이다."""

    timestamp: float
    timestep: int
    action: Any

    def get_timestamp(self) -> float:
        """원본 observation 기준 예상 실행 timestamp를 반환한다."""

        return self.timestamp

    def get_timestep(self) -> int:
        """client action queue에서 사용할 절대 timestep을 반환한다."""

        return self.timestep

    def get_action(self) -> Any:
        """CPU torch tensor action을 반환한다."""

        return self.action


class _RestrictedClientUnpickler(pickle.Unpickler):
    """기존 client의 필요한 DTO와 NumPy 배열 외 global 복원을 거부한다."""

    # pickle에서 허용하는 정확한 global 경로다.
    _ALLOWED_GLOBALS = {
        (LEROBOT_HELPERS_MODULE, "RemotePolicyConfig"): RemotePolicyConfigCompat,
        (LEROBOT_HELPERS_MODULE, "TimedObservation"): TimedObservationCompat,
        (LEROBOT_TYPES_MODULE, "PolicyFeature"): PolicyFeatureCompat,
        (LEROBOT_TYPES_MODULE, "FeatureType"): FeatureTypeCompat,
        ("numpy", "ndarray"): np.ndarray,
        ("numpy", "dtype"): np.dtype,
        ("numpy.core.multiarray", "_reconstruct"): np.core.multiarray._reconstruct,
        ("numpy._core.multiarray", "_reconstruct"): np.core.multiarray._reconstruct,
        ("numpy.core.multiarray", "scalar"): np.core.multiarray.scalar,
        ("numpy._core.multiarray", "scalar"): np.core.multiarray.scalar,
        ("builtins", "slice"): slice,
        ("builtins", "complex"): complex,
        ("builtins", "set"): set,
        ("builtins", "frozenset"): frozenset,
    }

    def find_class(self, module: str, name: str) -> Any:
        """allowlist 밖의 pickle global import를 차단한다."""

        allowed = self._ALLOWED_GLOBALS.get((module, name))
        if allowed is None:
            raise pickle.UnpicklingError(
                f"허용하지 않는 client pickle global입니다: {module}.{name}"
            )
        return allowed


@dataclasses.dataclass(frozen=True)
class LeRobotWireTypes:
    """동적으로 만든 wire-compatible protobuf message class 묶음이다."""

    Empty: type[Any]
    Observation: type[Any]
    Actions: type[Any]
    PolicySetup: type[Any]


def _add_proto_field(
    message: descriptor_pb2.DescriptorProto,
    *,
    name: str,
    number: int,
    field_type: int,
    type_name: str = "",
) -> None:
    """동적 protobuf message에 필드 하나를 추가한다."""

    field = message.field.add()
    field.name = name
    field.number = number
    field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field.type = field_type
    if type_name:
        field.type_name = type_name


def build_lerobot_wire_types() -> LeRobotWireTypes:
    """LeRobot 0.6 services.proto와 wire-compatible한 message class를 만든다."""

    file_descriptor = descriptor_pb2.FileDescriptorProto()
    file_descriptor.name = "piper_vla_lerobot_compat.proto"
    file_descriptor.package = "transport"
    file_descriptor.syntax = "proto3"

    transfer_state = file_descriptor.enum_type.add()
    transfer_state.name = "TransferState"
    for name, number in (
        ("TRANSFER_UNKNOWN", TRANSFER_UNKNOWN),
        ("TRANSFER_BEGIN", TRANSFER_BEGIN),
        ("TRANSFER_MIDDLE", TRANSFER_MIDDLE),
        ("TRANSFER_END", TRANSFER_END),
    ):
        value = transfer_state.value.add()
        value.name = name
        value.number = number

    file_descriptor.message_type.add().name = "Empty"
    observation = file_descriptor.message_type.add()
    observation.name = "Observation"
    _add_proto_field(
        observation,
        name="transfer_state",
        number=1,
        field_type=descriptor_pb2.FieldDescriptorProto.TYPE_ENUM,
        type_name=".transport.TransferState",
    )
    _add_proto_field(
        observation,
        name="data",
        number=2,
        field_type=descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,
    )
    actions = file_descriptor.message_type.add()
    actions.name = "Actions"
    _add_proto_field(
        actions,
        name="data",
        number=1,
        field_type=descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,
    )
    policy_setup = file_descriptor.message_type.add()
    policy_setup.name = "PolicySetup"
    _add_proto_field(
        policy_setup,
        name="data",
        number=1,
        field_type=descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,
    )

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_descriptor)
    return LeRobotWireTypes(
        Empty=message_factory.GetMessageClass(
            pool.FindMessageTypeByName("transport.Empty")
        ),
        Observation=message_factory.GetMessageClass(
            pool.FindMessageTypeByName("transport.Observation")
        ),
        Actions=message_factory.GetMessageClass(
            pool.FindMessageTypeByName("transport.Actions")
        ),
        PolicySetup=message_factory.GetMessageClass(
            pool.FindMessageTypeByName("transport.PolicySetup")
        ),
    )


# 같은 process와 테스트에서 재사용할 동적 protobuf class다.
WIRE_TYPES = build_lerobot_wire_types()


def restricted_client_loads(payload: bytes, expected_type: type[Any]) -> Any:
    """크기 제한과 global allowlist를 적용해 client pickle 하나를 복원한다."""

    if not isinstance(payload, bytes) or not payload:
        raise TypeError("client pickle payload는 비어 있지 않은 bytes여야 합니다.")
    if len(payload) > MAX_PICKLE_BYTES:
        raise ValueError(
            f"client pickle payload가 너무 큽니다: {len(payload)} > {MAX_PICKLE_BYTES}"
        )
    value = _RestrictedClientUnpickler(io.BytesIO(payload)).load()
    if not isinstance(value, expected_type):
        raise TypeError(
            "client pickle object type이 올바르지 않습니다: "
            f"expected={expected_type.__name__}, actual={type(value).__name__}"
        )
    return value


def _install_lerobot_pickle_aliases() -> None:
    """출력 pickle이 기존 client의 TimedAction class 이름을 사용하게 한다."""

    try:
        lerobot_module = importlib.import_module("lerobot")
    except ImportError:
        lerobot_module = types.ModuleType("lerobot")
        lerobot_module.__path__ = []  # type: ignore[attr-defined]
        sys.modules["lerobot"] = lerobot_module

    async_module_name = "lerobot.async_inference"
    async_module = sys.modules.get(async_module_name)
    if async_module is None:
        async_module = types.ModuleType(async_module_name)
        async_module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[async_module_name] = async_module
        setattr(lerobot_module, "async_inference", async_module)

    helpers_module = sys.modules.get(LEROBOT_HELPERS_MODULE)
    if helpers_module is None:
        helpers_module = types.ModuleType(LEROBOT_HELPERS_MODULE)
        sys.modules[LEROBOT_HELPERS_MODULE] = helpers_module
        setattr(async_module, "helpers", helpers_module)

    aliases = {
        "RemotePolicyConfig": RemotePolicyConfigCompat,
        "TimedObservation": TimedObservationCompat,
        "TimedAction": TimedActionCompat,
    }
    for wire_name, wire_class in aliases.items():
        wire_class.__module__ = LEROBOT_HELPERS_MODULE
        wire_class.__name__ = wire_name
        wire_class.__qualname__ = wire_name
        setattr(helpers_module, wire_name, wire_class)


def lerobot_pickle_dumps(value: Any) -> bytes:
    """기존 LeRobot client가 import 가능한 class 이름으로 값을 직렬화한다."""

    _install_lerobot_pickle_aliases()
    return pickle.dumps(value, protocol=4)


def raw_client_observation_to_canonical(raw: Mapping[str, Any]) -> dict[str, Any]:
    """기존 PiperBridgeRobot raw dict를 OpenPI canonical observation으로 바꾼다."""

    if not isinstance(raw, Mapping):
        raise TypeError(f"raw observation은 mapping이어야 합니다: {type(raw).__name__}")
    expected_keys = {
        *CLIENT_STATE_KEYS,
        CLIENT_THIRD_PERSON_KEY,
        CLIENT_WRIST_KEY,
        CLIENT_TASK_KEY,
    }
    if set(raw) != expected_keys:
        raise ValueError(
            "vla_pipeline raw observation key가 올바르지 않습니다: "
            f"missing={sorted(expected_keys - set(raw))}, "
            f"unknown={sorted(set(raw) - expected_keys)}"
        )
    state_values: list[float] = []
    for key in CLIENT_STATE_KEYS:
        value = raw[key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise TypeError(
                f"vla_pipeline state 값은 실수 scalar여야 합니다: key={key}, "
                f"actual={type(value).__name__}"
            )
        converted = float(value)
        if not math.isfinite(converted):
            raise ValueError(f"vla_pipeline state 값이 유한하지 않습니다: key={key}")
        state_values.append(converted)
    state = np.asarray(state_values, dtype=np.float32)
    return build_canonical_observation(
        raw[CLIENT_THIRD_PERSON_KEY],
        raw[CLIENT_WRIST_KEY],
        state,
        raw[CLIENT_TASK_KEY],
    )


def _validate_feature_mapping(
    feature: Any,
    expected: Mapping[str, Any],
    *,
    feature_name: str,
) -> None:
    """LeRobot client가 보낸 dataset feature의 의미를 exact-match한다."""

    if not isinstance(feature, Mapping):
        raise TypeError(
            f"LeRobot feature는 mapping이어야 합니다: key={feature_name}, "
            f"actual={type(feature).__name__}"
        )
    if set(feature) != set(expected):
        raise ValueError(
            f"LeRobot feature key가 다릅니다: key={feature_name}, "
            f"expected={sorted(expected)}, actual={sorted(feature)}"
        )
    for key, expected_value in expected.items():
        actual_value = feature[key]
        if key in {"shape", "names"}:
            actual_value = tuple(actual_value)
            expected_value = tuple(expected_value)
        if type(actual_value) is not type(expected_value) or actual_value != expected_value:
            raise ValueError(
                f"LeRobot feature 값이 다릅니다: feature={feature_name}, field={key}, "
                f"expected={expected_value!r}, actual={actual_value!r}"
            )


def validate_remote_policy_config(
    config: RemotePolicyConfigCompat,
    *,
    expected_actions_per_chunk: int | None = None,
) -> None:
    """client 요청이 이 고정 π0 서버와 호환되는지 모델 로드 없이 검사한다."""

    if config.policy_type != "pi0":
        raise ValueError(f"policy_type은 pi0여야 합니다: {config.policy_type!r}")
    if not isinstance(config.pretrained_name_or_path, str) or not config.pretrained_name_or_path:
        raise ValueError("pretrained_name_or_path는 비어 있지 않은 호환 식별자여야 합니다.")
    if type(config.actions_per_chunk) is not int or not 1 <= config.actions_per_chunk <= ACTION_HORIZON:
        raise ValueError(
            f"actions_per_chunk는 1~{ACTION_HORIZON}이어야 합니다: "
            f"{config.actions_per_chunk!r}"
        )
    if (
        expected_actions_per_chunk is not None
        and config.actions_per_chunk != expected_actions_per_chunk
    ):
        raise ValueError(
            "client actions_per_chunk가 server YAML과 다릅니다: "
            f"expected={expected_actions_per_chunk}, actual={config.actions_per_chunk}"
        )
    if not isinstance(config.device, str) or not config.device:
        raise ValueError("client policy_device는 비어 있지 않아야 합니다.")
    if not isinstance(config.lerobot_features, dict):
        raise TypeError("lerobot_features는 dict여야 합니다.")
    if not isinstance(config.rename_map, dict):
        raise TypeError("rename_map은 dict여야 합니다.")
    if config.rename_map:
        raise ValueError(
            "이 서버는 Piper raw key를 직접 변환하므로 client rename_map은 비어 있어야 합니다."
        )
    actual_feature_keys = set(config.lerobot_features)
    if actual_feature_keys != set(EXPECTED_LEROBOT_FEATURE_KEYS):
        raise ValueError(
            "Piper LeRobot feature key가 올바르지 않습니다: "
            f"expected={sorted(EXPECTED_LEROBOT_FEATURE_KEYS)}, "
            f"actual={sorted(actual_feature_keys)}"
        )
    _validate_feature_mapping(
        config.lerobot_features["observation.state"],
        EXPECTED_STATE_FEATURE,
        feature_name="observation.state",
    )
    for image_key in (
        "observation.images.third_person",
        "observation.images.wrist",
    ):
        _validate_feature_mapping(
            config.lerobot_features[image_key],
            EXPECTED_IMAGE_FEATURE,
            feature_name=image_key,
        )


def _receive_observation_bytes(chunks: Iterable[Any]) -> bytes:
    """LeRobot Observation stream을 한 pickle payload로 엄격하게 결합한다."""

    payload = bytearray()
    started = False
    ended = False
    for chunk in chunks:
        if ended:
            raise ValueError("TRANSFER_END 뒤에 추가 observation chunk가 왔습니다.")
        transfer_state = int(chunk.transfer_state)
        if transfer_state == TRANSFER_BEGIN:
            if started or payload:
                raise ValueError("TRANSFER_BEGIN이 중복됐습니다.")
            started = True
        elif transfer_state == TRANSFER_MIDDLE:
            if not started:
                raise ValueError("TRANSFER_BEGIN 없이 TRANSFER_MIDDLE이 왔습니다.")
        elif transfer_state == TRANSFER_END:
            ended = True
        else:
            raise ValueError(f"알 수 없는 TransferState입니다: {transfer_state}")
        payload.extend(chunk.data)
        if len(payload) > MAX_PICKLE_BYTES:
            raise ValueError(
                f"observation stream이 너무 큽니다: {len(payload)} > {MAX_PICKLE_BYTES}"
            )
    if not ended or not payload:
        raise ValueError("observation stream이 TRANSFER_END로 끝나지 않았습니다.")
    return bytes(payload)


class LeRobotGrpcPolicyService:
    """고정 OpenPI policy를 LeRobot 0.6 AsyncInference RPC로 노출한다."""

    def __init__(
        self,
        policy: PolicyProtocol,
        *,
        observation_queue_timeout_seconds: float,
        expected_actions_per_chunk: int,
        control_fps: int,
    ) -> None:
        """policy와 YAML의 chunk·timing 계약을 저장하고 빈 session을 준비한다."""

        if not math.isfinite(observation_queue_timeout_seconds) or not (
            0.1 <= observation_queue_timeout_seconds <= 60.0
        ):
            raise ValueError(
                "observation_queue_timeout_seconds는 0.1~60.0이어야 합니다."
            )
        if type(expected_actions_per_chunk) is not int or not 1 <= expected_actions_per_chunk <= ACTION_HORIZON:
            raise ValueError(
                f"expected_actions_per_chunk는 1~{ACTION_HORIZON}이어야 합니다."
            )
        if type(control_fps) is not int or not 1 <= control_fps <= 100:
            raise ValueError("control_fps는 1~100이어야 합니다.")
        self._policy = policy
        self._expected_actions_per_chunk = expected_actions_per_chunk
        self._control_fps = control_fps
        self._observation_queue_timeout_seconds = observation_queue_timeout_seconds
        self._observation_queue: Queue[TimedObservationCompat] = Queue(maxsize=1)
        self._state_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._policy_config: RemotePolicyConfigCompat | None = None

    def _reset_session(self) -> None:
        """새 client 접속 전에 이전 queue와 설정을 제거한다."""

        with self._state_lock:
            self._observation_queue = Queue(maxsize=1)
            self._policy_config = None

    def Ready(self, request: Any, context: Any) -> Any:  # noqa: N802, ARG002
        """기존 client handshake를 받고 server-side session을 초기화한다."""

        self._reset_session()
        return WIRE_TYPES.Empty()

    def SendPolicyInstructions(self, request: Any, context: Any) -> Any:  # noqa: N802
        """client config를 검증하되 모델은 서버 YAML checkpoint로 고정한다."""

        try:
            config = restricted_client_loads(request.data, RemotePolicyConfigCompat)
            validate_remote_policy_config(
                config,
                expected_actions_per_chunk=self._expected_actions_per_chunk,
            )
        except Exception as error:
            context.abort(
                self._grpc_status("INVALID_ARGUMENT"),
                f"policy instruction 검증 실패: {error}",
            )
            raise AssertionError("gRPC context.abort가 반환됐습니다.") from error
        with self._state_lock:
            self._policy_config = config
        logging.info(
            "LeRobot client connected: policy=%s, actions_per_chunk=%d, client_label=%s",
            config.policy_type,
            config.actions_per_chunk,
            config.pretrained_name_or_path,
        )
        return WIRE_TYPES.Empty()

    def SendObservations(self, request_iterator: Iterable[Any], context: Any) -> Any:  # noqa: N802
        """최신 raw observation을 canonical 형식으로 선검증해 queue에 넣는다."""

        try:
            payload = _receive_observation_bytes(request_iterator)
            observation = restricted_client_loads(payload, TimedObservationCompat)
            if not math.isfinite(float(observation.timestamp)):
                raise ValueError("observation timestamp는 유한해야 합니다.")
            if type(observation.timestep) is not int or observation.timestep < 0:
                raise ValueError("observation timestep은 0 이상의 정수여야 합니다.")
            if type(observation.must_go) is not bool:
                raise TypeError("observation must_go는 bool이어야 합니다.")
            raw_client_observation_to_canonical(observation.observation)
        except Exception as error:
            context.abort(
                self._grpc_status("INVALID_ARGUMENT"),
                f"observation 검증 실패: {error}",
            )
            raise AssertionError("gRPC context.abort가 반환됐습니다.") from error

        with self._state_lock:
            queue = self._observation_queue
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(observation)
        return WIRE_TYPES.Empty()

    def GetActions(self, request: Any, context: Any) -> Any:  # noqa: N802, ARG002
        """가장 최근 관측에서 action chunk를 예측해 TimedAction list로 반환한다."""

        with self._state_lock:
            policy_config = self._policy_config
            queue = self._observation_queue
        if policy_config is None:
            context.abort(
                self._grpc_status("FAILED_PRECONDITION"),
                "SendPolicyInstructions가 먼저 호출되어야 합니다.",
            )
            raise AssertionError("gRPC context.abort가 반환됐습니다.")
        try:
            timed_observation = queue.get(
                timeout=self._observation_queue_timeout_seconds
            )
        except Empty:
            return WIRE_TYPES.Actions(data=b"")

        try:
            canonical = raw_client_observation_to_canonical(
                timed_observation.observation
            )
            with self._inference_lock:
                result = validate_policy_output(self._policy.infer(canonical))
            actions = result["actions"][
                : policy_config.actions_per_chunk
            ]
            if actions.shape != (policy_config.actions_per_chunk, ROBOT_DIM):
                raise ValueError(f"잘린 action chunk shape이 잘못됐습니다: {actions.shape}")
            if not np.isfinite(actions).all():
                raise ValueError("action chunk에 NaN 또는 Inf가 있습니다.")

            # torch는 client queue가 요구하는 CPU Tensor를 만들 때만 지연 import한다.
            import torch

            timed_actions = [
                TimedActionCompat(
                    timestamp=float(timed_observation.timestamp)
                    + index / float(self._control_fps),
                    timestep=timed_observation.timestep + index,
                    action=torch.from_numpy(np.ascontiguousarray(action)),
                )
                for index, action in enumerate(actions)
            ]
            return WIRE_TYPES.Actions(data=lerobot_pickle_dumps(timed_actions))
        except Exception as error:
            logging.exception("OpenPI π0 inference failed")
            context.abort(
                self._grpc_status("INTERNAL"),
                f"OpenPI π0 inference 실패: {error}",
            )
            raise AssertionError("gRPC context.abort가 반환됐습니다.") from error

    @staticmethod
    def _grpc_status(name: str) -> Any:
        """grpc import를 실제 server 경로까지 지연하고 StatusCode를 반환한다."""

        import grpc

        return getattr(grpc.StatusCode, name)


class LeRobotGrpcServer:
    """실제 grpc.Server와 bind 결과를 관리하는 작은 lifecycle wrapper다."""

    def __init__(self, server: Any, *, host: str, requested_port: int, bound_port: int) -> None:
        """grpc server와 실제 bind endpoint를 저장한다."""

        self._server = server
        self.host = host
        self.requested_port = requested_port
        self.bound_port = bound_port

    def start(self) -> None:
        """gRPC worker를 시작한다."""

        self._server.start()

    def stop(self, grace_seconds: float = 2.0) -> None:
        """새 요청을 막고 진행 중 요청에 제한된 종료 시간을 준다."""

        self._server.stop(grace_seconds).wait(timeout=grace_seconds + 1.0)

    def serve_forever(self) -> None:
        """서버를 시작하고 SIGINT까지 대기한다."""

        logging.info(
            "LeRobot AsyncInference gRPC server listening on %s:%d",
            self.host,
            self.bound_port,
        )
        self.start()
        try:
            self._server.wait_for_termination()
        except KeyboardInterrupt:
            self.stop()


def _message_deserializer(message_class: type[Any]) -> Any:
    """gRPC handler에 넘길 protobuf deserializer를 만든다."""

    return message_class.FromString


def _message_serializer(message: Any) -> bytes:
    """동적 protobuf message를 wire bytes로 직렬화한다."""

    return message.SerializeToString()


def create_lerobot_grpc_server(
    policy: PolicyProtocol,
    settings: Any,
) -> LeRobotGrpcServer:
    """기존 vla_pipeline client와 호환되는 gRPC server를 bind한다."""

    import grpc

    async_client = getattr(settings, "async_client", None)
    if async_client is None:
        raise ValueError(
            "vla_pipeline gRPC server에는 schema 2 async_client 설정이 필요합니다."
        )
    service = LeRobotGrpcPolicyService(
        policy,
        observation_queue_timeout_seconds=async_client.observation_queue_timeout_seconds,
        expected_actions_per_chunk=async_client.actions_per_chunk,
        control_fps=async_client.fps,
    )
    handlers = {
        "Ready": grpc.unary_unary_rpc_method_handler(
            service.Ready,
            request_deserializer=_message_deserializer(WIRE_TYPES.Empty),
            response_serializer=_message_serializer,
        ),
        "SendPolicyInstructions": grpc.unary_unary_rpc_method_handler(
            service.SendPolicyInstructions,
            request_deserializer=_message_deserializer(WIRE_TYPES.PolicySetup),
            response_serializer=_message_serializer,
        ),
        "SendObservations": grpc.stream_unary_rpc_method_handler(
            service.SendObservations,
            request_deserializer=_message_deserializer(WIRE_TYPES.Observation),
            response_serializer=_message_serializer,
        ),
        "GetActions": grpc.unary_unary_rpc_method_handler(
            service.GetActions,
            request_deserializer=_message_deserializer(WIRE_TYPES.Empty),
            response_serializer=_message_serializer,
        ),
    }
    grpc_server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        options=(
            ("grpc.max_receive_message_length", MAX_GRPC_MESSAGE_BYTES),
            ("grpc.max_send_message_length", MAX_GRPC_MESSAGE_BYTES),
        ),
    )
    grpc_server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler(LEROBOT_GRPC_SERVICE_NAME, handlers),)
    )
    host = str(settings.server.host)
    requested_port = int(settings.server.port)
    bound_port = grpc_server.add_insecure_port(f"{host}:{requested_port}")
    if bound_port == 0:
        raise RuntimeError(f"gRPC server bind에 실패했습니다: {host}:{requested_port}")
    return LeRobotGrpcServer(
        grpc_server,
        host=host,
        requested_port=requested_port,
        bound_port=bound_port,
    )
