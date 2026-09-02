"""Piper π0 추론 YAML을 부작용 없이 읽고 엄격하게 검증한다."""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
import re
from typing import Any

import yaml

from piper_vla.inference.async_client_settings import (
    validate_client_values,
)

# 기본 WebSocket 설정이 사용하는 이전 추론 schema다.
LEGACY_INFERENCE_SCHEMA_VERSION = 1

# 시간 제한이 없던 기존 async client schema다.
LEGACY_ASYNC_INFERENCE_SCHEMA_VERSION = 2

# episode 시간 제한까지 포함하던 이전 async 전용 schema다.
LEGACY_TIMED_ASYNC_INFERENCE_SCHEMA_VERSION = 3

# 동기·비동기 모드 선택과 조건부 옵션을 포함하는 현재 추론 schema다.
INFERENCE_SCHEMA_VERSION = 4

# 학습과 동일하게 사용하는 OpenPI config namespace다.
PIPER_PI0_CONFIG_NAME = "pi0_piper_lora"

# 경로 구성 요소로 안전하게 사용할 수 있는 이름 형식이다.
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

# schema 1 설정 파일 최상위에서 허용하는 key다.
LEGACY_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "checkpoint", "policy", "server", "runtime"}
)

# schema 2·3 async client 설정 파일 최상위에서 허용하는 key다.
LEGACY_ASYNC_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "checkpoint",
        "policy",
        "server",
        "runtime",
        "async_client",
    }
)

# 현재 동기·비동기 client 설정 파일 최상위에서 허용하는 key다.
TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "checkpoint",
        "policy",
        "server",
        "runtime",
        "client",
    }
)

# checkpoint section에서 허용하는 key다.
CHECKPOINT_KEYS = frozenset({"runs_root", "config_name", "run_name", "asset_id", "step"})

# policy section에서 허용하는 key다.
POLICY_KEYS = frozenset({"prompt", "num_inference_steps"})

# server section에서 허용하는 key다.
SERVER_KEYS = frozenset({"host", "port"})

# runtime section에서 허용하는 key다.
RUNTIME_KEYS = frozenset({"jax_memory_fraction"})

# schema 2 async_client section에서 허용하던 key다.
LEGACY_ASYNC_CLIENT_KEYS = frozenset(
    {
        "actions_per_chunk",
        "chunk_size_threshold",
        "aggregate_fn_name",
        "fps",
        "observation_queue_timeout_seconds",
        "debug_visualize_queue_size",
    }
)

# schema 3 async_client section에서 허용하는 key다.
TIMED_ASYNC_CLIENT_KEYS = LEGACY_ASYNC_CLIENT_KEYS | {"episode_time_seconds"}

# schema 4 client 공통 section에서 허용하는 key다.
CLIENT_KEYS = frozenset(
    {
        "mode",
        "episode_time_seconds",
        "actions_per_chunk",
        "fps",
        "observation_queue_timeout_seconds",
        "async_options",
    }
)

# 비동기 모드에서만 client 동작에 사용하는 key다.
ASYNC_OPTIONS_KEYS = frozenset(
    {
        "chunk_size_threshold",
        "aggregate_fn_name",
        "debug_visualize_queue_size",
    }
)

# LeRobot 0.6 async client가 제공하는 chunk 합성 함수다.
ASYNC_AGGREGATE_FUNCTIONS = frozenset(
    {"weighted_average", "latest_only", "average", "conservative"}
)

# 현재 Piper π0 checkpoint가 생성하는 최대 action chunk 길이다.
PI0_ACTION_HORIZON = 50

# 추론 JAX allocator에 허용하는 최소 GPU 메모리 비율이다.
MIN_JAX_MEMORY_FRACTION = 0.30

# 추론 JAX allocator에 허용하는 최대 GPU 메모리 비율이다.
MAX_JAX_MEMORY_FRACTION = 0.95


class UniqueKeySafeLoader(yaml.SafeLoader):
    """같은 YAML mapping 안의 중복 key를 거부하는 안전 loader다."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    """중복 key를 발견하면 마지막 값으로 덮지 않고 즉시 실패한다."""

    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"YAML key가 중복됐습니다: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


# 모든 YAML mapping에 중복 key 검사를 적용한다.
UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclasses.dataclass(frozen=True)
class InferenceCheckpointSettings:
    """추론에 사용할 학습 run과 checkpoint 자산 설정이다."""

    # 학습 run들이 저장된 workspace 내부 경로다.
    runs_root: Path

    # OpenPI 학습 config namespace다.
    config_name: str

    # 추론 대상 학습 run 이름이다.
    run_name: str

    # checkpoint 안의 normalization 자산 식별자다.
    asset_id: str

    # 기본으로 선택할 커밋 완료 checkpoint step이다.
    step: int


@dataclasses.dataclass(frozen=True)
class InferencePolicySettings:
    """π0 sampling과 언어 지시문 설정이다."""

    # 학습 데이터와 동일하게 사용할 기본 task 문장이다.
    prompt: str

    # π0 flow-matching action sampling에서 사용할 Euler 적분 횟수다.
    num_inference_steps: int


@dataclasses.dataclass(frozen=True)
class InferenceServerSettings:
    """OpenPI WebSocket policy server의 bind 설정이다."""

    # 서버가 연결을 받을 주소다.
    host: str

    # 서버가 연결을 받을 TCP port다.
    port: int


@dataclasses.dataclass(frozen=True)
class InferenceRuntimeSettings:
    """JAX 추론 process의 자원 설정이다."""

    # JAX allocator가 사용할 GPU 메모리 비율이다.
    jax_memory_fraction: float


@dataclasses.dataclass(frozen=True)
class AsyncClientOptions:
    """비동기 client에서만 사용하는 queue·aggregation 설정이다."""

    chunk_size_threshold: float
    aggregate_fn_name: str
    debug_visualize_queue_size: bool


@dataclasses.dataclass(frozen=True)
class InferenceClientSettings:
    """동기·비동기 client와 gRPC server가 공유하는 실행 계약이다."""

    # async는 추론·제어 중첩, sync는 chunk 단위 순차 실행이다.
    mode: str

    # control loop 시작 후 자동 종료할 시간이다. None이면 무제한으로 실행한다.
    episode_time_seconds: float | None

    # π0가 생성한 50개 action 중 client에 보낼 개수다.
    actions_per_chunk: int

    # action을 실행하고 timestamp를 만드는 제어 주파수다.
    fps: int

    # 서버가 새 observation을 기다리는 최대 시간이다.
    observation_queue_timeout_seconds: float

    # sync에서는 무시하고 async에서만 적용하는 옵션 묶음이다.
    async_options: AsyncClientOptions


@dataclasses.dataclass(frozen=True)
class Pi0InferenceSettings:
    """검증과 경로 해석을 마친 전체 Piper π0 추론 설정이다."""

    # 실제로 읽은 YAML 파일의 절대 경로다.
    config_path: Path

    # 모든 상대 경로를 해석하는 workspace 절대 경로다.
    workspace_root: Path

    # checkpoint 선택 설정이다.
    checkpoint: InferenceCheckpointSettings

    # 정책 sampling 설정이다.
    policy: InferencePolicySettings

    # WebSocket server 설정이다.
    server: InferenceServerSettings

    # JAX process 자원 설정이다.
    runtime: InferenceRuntimeSettings

    # gRPC client를 사용하는 schema에서 제공하는 실행 계약이다.
    client: InferenceClientSettings | None


def _require_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    """설정 값이 문자열 key를 가진 mapping인지 검증한다."""

    if not isinstance(value, dict):
        raise TypeError(f"{field_name}은 mapping이어야 합니다: {type(value).__name__}")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{field_name}의 모든 key는 문자열이어야 합니다.")
    return value


def _require_exact_keys(
    mapping: dict[str, Any],
    expected: frozenset[str],
    *,
    field_name: str,
) -> None:
    """누락 key와 알 수 없는 key를 함께 거부한다."""

    actual = set(mapping)
    if actual != set(expected):
        raise ValueError(
            f"{field_name} key가 올바르지 않습니다: "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )


def _require_string(value: Any, *, field_name: str) -> str:
    """비어 있지 않은 문자열 설정을 반환한다."""

    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name}은 비어 있지 않은 문자열이어야 합니다.")
    return value.strip()


def _require_integer(value: Any, *, field_name: str) -> int:
    """bool과 float를 허용하지 않는 정확한 정수 설정을 반환한다."""

    if type(value) is not int:
        raise TypeError(f"{field_name}은 정수여야 합니다: {value!r}")
    return value


def _require_real(value: Any, *, field_name: str) -> float:
    """유한한 실수 설정을 float로 반환한다."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name}은 실수여야 합니다: {value!r}")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field_name}은 유한해야 합니다: {value!r}")
    return converted


def _validate_safe_name(value: str, *, field_name: str) -> str:
    """경로 탈출 없이 한 디렉터리 이름으로 사용할 값을 검증한다."""

    if value in {".", ".."} or SAFE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field_name}은 영문자/숫자로 시작하고 영문자·숫자·._-만 허용합니다: "
            f"{value!r}"
        )
    return value


def _resolve_workspace_path(
    value: Any,
    workspace_root: Path,
    *,
    field_name: str,
) -> Path:
    """상대 경로를 workspace 기준으로 해석하고 외부 탈출을 거부한다."""

    raw_path = Path(_require_string(value, field_name=field_name)).expanduser()
    resolved = (workspace_root / raw_path if not raw_path.is_absolute() else raw_path).resolve()
    if not resolved.is_relative_to(workspace_root):
        raise ValueError(
            f"{field_name}은 workspace 안에 있어야 합니다: "
            f"{resolved} not under {workspace_root}"
        )
    return resolved


def load_pi0_inference_settings(
    config_path: Path,
    workspace_root: Path,
) -> Pi0InferenceSettings:
    """추론 YAML을 strict-load하고 typed 설정으로 변환한다."""

    resolved_workspace = workspace_root.expanduser().resolve()
    resolved_config = config_path.expanduser()
    if not resolved_config.is_absolute():
        resolved_config = resolved_workspace / resolved_config
    resolved_config = resolved_config.resolve()
    if not resolved_config.is_relative_to(resolved_workspace):
        raise ValueError(f"추론 config는 workspace 안에 있어야 합니다: {resolved_config}")
    if not resolved_config.is_file():
        raise FileNotFoundError(f"추론 config 파일이 없습니다: {resolved_config}")

    raw = yaml.load(resolved_config.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader)
    root = _require_mapping(raw, field_name="config")
    schema_version = _require_integer(root["schema_version"], field_name="schema_version")
    if schema_version == LEGACY_INFERENCE_SCHEMA_VERSION:
        _require_exact_keys(root, LEGACY_TOP_LEVEL_KEYS, field_name="config")
    elif schema_version in {
        LEGACY_ASYNC_INFERENCE_SCHEMA_VERSION,
        LEGACY_TIMED_ASYNC_INFERENCE_SCHEMA_VERSION,
    }:
        _require_exact_keys(root, LEGACY_ASYNC_TOP_LEVEL_KEYS, field_name="config")
    elif schema_version == INFERENCE_SCHEMA_VERSION:
        _require_exact_keys(root, TOP_LEVEL_KEYS, field_name="config")
    else:
        raise ValueError(
            f"지원하지 않는 추론 schema입니다: "
            f"expected={LEGACY_INFERENCE_SCHEMA_VERSION} 또는 "
            f"{LEGACY_ASYNC_INFERENCE_SCHEMA_VERSION} 또는 "
            f"{LEGACY_TIMED_ASYNC_INFERENCE_SCHEMA_VERSION} 또는 "
            f"{INFERENCE_SCHEMA_VERSION}, actual={schema_version}"
        )

    checkpoint_raw = _require_mapping(root["checkpoint"], field_name="checkpoint")
    policy_raw = _require_mapping(root["policy"], field_name="policy")
    server_raw = _require_mapping(root["server"], field_name="server")
    runtime_raw = _require_mapping(root["runtime"], field_name="runtime")
    _require_exact_keys(checkpoint_raw, CHECKPOINT_KEYS, field_name="checkpoint")
    _require_exact_keys(policy_raw, POLICY_KEYS, field_name="policy")
    _require_exact_keys(server_raw, SERVER_KEYS, field_name="server")
    _require_exact_keys(runtime_raw, RUNTIME_KEYS, field_name="runtime")

    client_raw: dict[str, Any] | None = None
    if schema_version in {
        LEGACY_ASYNC_INFERENCE_SCHEMA_VERSION,
        LEGACY_TIMED_ASYNC_INFERENCE_SCHEMA_VERSION,
    }:
        async_client_raw = _require_mapping(
            root["async_client"],
            field_name="async_client",
        )
        _require_exact_keys(
            async_client_raw,
            LEGACY_ASYNC_CLIENT_KEYS
            if schema_version == LEGACY_ASYNC_INFERENCE_SCHEMA_VERSION
            else TIMED_ASYNC_CLIENT_KEYS,
            field_name="async_client",
        )
        if schema_version == LEGACY_ASYNC_INFERENCE_SCHEMA_VERSION:
            async_client_raw = dict(async_client_raw)
            async_client_raw["episode_time_seconds"] = None
        client_raw = {
            "mode": "async",
            "episode_time_seconds": async_client_raw["episode_time_seconds"],
            "actions_per_chunk": async_client_raw["actions_per_chunk"],
            "fps": async_client_raw["fps"],
            "observation_queue_timeout_seconds": async_client_raw[
                "observation_queue_timeout_seconds"
            ],
            "async_options": {
                "chunk_size_threshold": async_client_raw["chunk_size_threshold"],
                "aggregate_fn_name": async_client_raw["aggregate_fn_name"],
                "debug_visualize_queue_size": async_client_raw[
                    "debug_visualize_queue_size"
                ],
            },
        }
    elif schema_version == INFERENCE_SCHEMA_VERSION:
        client_raw = _require_mapping(root["client"], field_name="client")
        _require_exact_keys(client_raw, CLIENT_KEYS, field_name="client")
        async_options_raw = _require_mapping(
            client_raw["async_options"],
            field_name="client.async_options",
        )
        _require_exact_keys(
            async_options_raw,
            ASYNC_OPTIONS_KEYS,
            field_name="client.async_options",
        )

    config_name = _validate_safe_name(
        _require_string(checkpoint_raw["config_name"], field_name="checkpoint.config_name"),
        field_name="checkpoint.config_name",
    )
    if config_name != PIPER_PI0_CONFIG_NAME:
        raise ValueError(
            "현재 추론기는 Piper π0 학습 namespace만 지원합니다: "
            f"expected={PIPER_PI0_CONFIG_NAME!r}, actual={config_name!r}"
        )
    step = _require_integer(checkpoint_raw["step"], field_name="checkpoint.step")
    if step <= 0:
        raise ValueError(f"checkpoint.step은 양수여야 합니다: {step}")

    prompt = _require_string(policy_raw["prompt"], field_name="policy.prompt")
    num_inference_steps = _require_integer(
        policy_raw["num_inference_steps"],
        field_name="policy.num_inference_steps",
    )
    if not 1 <= num_inference_steps <= 100:
        raise ValueError(
            "policy.num_inference_steps는 1~100이어야 합니다: "
            f"{num_inference_steps}"
        )

    host = _require_string(server_raw["host"], field_name="server.host")
    if any(character.isspace() for character in host):
        raise ValueError(f"server.host에 공백을 넣을 수 없습니다: {host!r}")
    port = _require_integer(server_raw["port"], field_name="server.port")
    if not 1024 <= port <= 65535:
        raise ValueError(f"server.port는 1024~65535여야 합니다: {port}")

    memory_fraction = _require_real(
        runtime_raw["jax_memory_fraction"],
        field_name="runtime.jax_memory_fraction",
    )
    if not MIN_JAX_MEMORY_FRACTION <= memory_fraction <= MAX_JAX_MEMORY_FRACTION:
        raise ValueError(
            "runtime.jax_memory_fraction 범위가 잘못됐습니다: "
            f"{memory_fraction}; 허용={MIN_JAX_MEMORY_FRACTION}~{MAX_JAX_MEMORY_FRACTION}"
        )

    client: InferenceClientSettings | None = None
    if client_raw is not None:
        client_values = validate_client_values(
            client_raw,
            action_horizon=PI0_ACTION_HORIZON,
            aggregate_functions=ASYNC_AGGREGATE_FUNCTIONS,
        )
        client = InferenceClientSettings(
            mode=client_values["mode"],
            episode_time_seconds=client_values["episode_time_seconds"],
            actions_per_chunk=client_values["actions_per_chunk"],
            fps=client_values["fps"],
            observation_queue_timeout_seconds=client_values[
                "observation_queue_timeout_seconds"
            ],
            async_options=AsyncClientOptions(**client_values["async_options"]),
        )

    return Pi0InferenceSettings(
        config_path=resolved_config,
        workspace_root=resolved_workspace,
        checkpoint=InferenceCheckpointSettings(
            runs_root=_resolve_workspace_path(
                checkpoint_raw["runs_root"],
                resolved_workspace,
                field_name="checkpoint.runs_root",
            ),
            config_name=config_name,
            run_name=_validate_safe_name(
                _require_string(checkpoint_raw["run_name"], field_name="checkpoint.run_name"),
                field_name="checkpoint.run_name",
            ),
            asset_id=_validate_safe_name(
                _require_string(checkpoint_raw["asset_id"], field_name="checkpoint.asset_id"),
                field_name="checkpoint.asset_id",
            ),
            step=step,
        ),
        policy=InferencePolicySettings(
            prompt=prompt,
            num_inference_steps=num_inference_steps,
        ),
        server=InferenceServerSettings(host=host, port=port),
        runtime=InferenceRuntimeSettings(jax_memory_fraction=memory_fraction),
        client=client,
    )
