"""Piper π0 LoRA YAML을 GPU 초기화 없이 엄격하게 읽는다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

import yaml


# 현재 loader가 해석하는 YAML 구조 버전이다.
SETTINGS_SCHEMA_VERSION = 3

# 설정 파일 최상위에서 정확히 허용하는 section 이름이다.
TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "paths",
        "dataset",
        "finetuning",
        "training",
        "runtime",
        "optimizer",
        "lr_schedule",
        "model_contract",
    }
)

# path section에서 허용하는 key다.
PATH_KEYS = frozenset(
    {"dataset_root", "assets_base_dir", "runs_root", "base_params"}
)

# dataset section에서 허용하는 key다.
DATASET_KEYS = frozenset({"asset_id"})

# finetuning section에서 허용하는 key다.
FINETUNING_KEYS = frozenset({"vision_encoder"})

# Vision encoder를 학습할 때 쓰는 canonical 설정값이다.
VISION_ENCODER_TRAINABLE = "trainable"

# Vision encoder를 고정할 때 쓰는 canonical 설정값이다.
VISION_ENCODER_FROZEN = "frozen"

# YAML에서 정확히 허용하는 Vision encoder 학습 모드다.
VISION_ENCODER_MODES = frozenset(
    {VISION_ENCODER_TRAINABLE, VISION_ENCODER_FROZEN}
)


# training section에서 허용하는 key다.
TRAINING_KEYS = frozenset(
    {
        "num_train_steps",
        "batch_size",
        "num_workers",
        "log_interval",
        "save_interval",
        "keep_period",
        "seed",
    }
)

# runtime section에서 허용하는 key다.
RUNTIME_KEYS = frozenset({"jax_memory_fraction", "progress_refresh_seconds"})

# 현재 production 코드와 정확히 같아야 하는 AdamW 계약이다.
LOCKED_OPTIMIZER = {
    "name": "adamw",
    "b1": 0.9,
    "b2": 0.95,
    "eps": 1.0e-8,
    "weight_decay": 1.0e-10,
    "clip_gradient_norm": 1.0,
}

# 현재 production 코드와 정확히 같아야 하는 learning-rate 계약이다.
LOCKED_LR_SCHEDULE = {
    "name": "cosine_decay",
    "warmup_steps": 1_000,
    "peak_lr": 2.5e-5,
    "decay_steps": 30_000,
    "decay_lr": 2.5e-6,
}

# checkpoint·dataset·추론이 공유하는 현재 π0 모델 계약이다.
LOCKED_MODEL_CONTRACT = {
    "openpi_profile": "pi0_libero_low_mem_finetune",
    "pi05": False,
    "paligemma_variant": "gemma_2b_lora",
    "action_expert_variant": "gemma_300m_lora",
    "dtype": "bfloat16",
    "action_dim": 32,
    "action_horizon": 50,
    "max_token_len": 48,
    "robot_dim": 7,
    "delta_joint_dim": 6,
    "normalization": "zscore",
    "freeze_mode": "official_lora_filter",
    "ema_decay": None,
    "fsdp_devices": 1,
}

# asset과 run 식별자에 사용할 수 있는 안전한 이름 형식이다.
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

# 검증되지 않은 activation 증가를 막는 global batch 상한이다.
MAX_BATCH_SIZE = 32

# 과도한 process와 host RAM 사용을 막는 DataLoader worker 상한이다.
MAX_NUM_WORKERS = 8

# 지나치게 잦은 checkpoint 저장을 막는 최소 step 간격이다.
MIN_SAVE_INTERVAL = 10

# JAX가 모델을 올릴 최소 GPU memory pool 비율이다.
MIN_JAX_MEMORY_FRACTION = 0.50

# OS와 display process에 여유를 남길 최대 GPU memory pool 비율이다.
MAX_JAX_MEMORY_FRACTION = 0.95

# TTY dashboard가 학습을 방해하지 않도록 허용할 최소 갱신 간격이다.
MIN_PROGRESS_REFRESH_SECONDS = 1.0

# 너무 오래 멈춘 화면으로 보이지 않도록 허용할 최대 갱신 간격이다.
MAX_PROGRESS_REFRESH_SECONDS = 60.0

# TTY dashboard의 기본 갱신 간격이다.
DEFAULT_PROGRESS_REFRESH_SECONDS = 1.0


class UniqueKeySafeLoader(yaml.SafeLoader):
    """안전한 YAML 타입만 허용하면서 모든 mapping의 중복 key를 거부한다."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    """같은 YAML mapping 안에서 이미 등장한 key를 발견하면 즉시 중단한다."""

    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"YAML key가 중복됐습니다: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


# PyYAML의 모든 일반 mapping에 중복 key 검사를 적용한다.
UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class Pi0PathSettings:
    """학습 input과 output의 workspace 내부 절대 경로를 보관한다."""

    # LeRobot v3 dataset의 절대 경로다.
    dataset_root: Path

    # normalization asset 상위 절대 경로다.
    assets_base_dir: Path

    # checkpoint와 diagnostics 상위 절대 경로다.
    runs_root: Path

    # fresh 학습용 π0 base params 절대 경로다.
    base_params: Path


@dataclass(frozen=True)
class Pi0DatasetSettings:
    """Dataset과 normalization asset을 연결하는 설정을 보관한다."""

    # norm_stats와 checkpoint asset에서 공유하는 안전한 식별자다.
    asset_id: str


@dataclass(frozen=True)
class Pi0FinetuningSettings:
    """실제로 parameter 학습 범위를 바꾸는 fine-tuning 설정을 보관한다."""

    # Vision encoder를 학습할지 고정할지 나타내는 canonical 모드다.
    vision_encoder: str


@dataclass(frozen=True)
class Pi0TrainingSettings:
    """기존 검증된 train_pi0 CLI로 전달할 안전한 학습값을 보관한다."""

    # 학습이 도달할 최종 absolute step이다.
    num_train_steps: int

    # 한 step에서 처리하는 global sample 수다.
    batch_size: int

    # MP4/Parquet을 읽는 DataLoader subprocess 수다.
    num_workers: int

    # metric을 동기화해 기록하는 step 간격이다.
    log_interval: int

    # durable checkpoint를 저장하는 step 간격이다.
    save_interval: int

    # 장기 보존 checkpoint의 step 간격이다.
    keep_period: int

    # loader shuffle과 JAX RNG에 사용할 seed다.
    seed: int


@dataclass(frozen=True)
class Pi0RuntimeSettings:
    """JAX를 import하기 전에 적용할 process runtime 설정을 보관한다."""

    # JAX GPU memory pool에 예약할 0.50 이상 0.95 이하의 비율이다.
    jax_memory_fraction: float

    # 학습 계산과 무관하게 TTY dashboard를 다시 그릴 시간 간격이다.
    progress_refresh_seconds: float


@dataclass(frozen=True)
class Pi0Settings:
    """검증된 π0 YAML의 안전한 실행 설정을 하나로 묶는다."""

    # 실제로 읽은 YAML 파일의 절대 경로다.
    config_path: Path

    # 모든 상대 경로의 기준이 되는 workspace 절대 경로다.
    workspace_root: Path

    # Dataset과 output에 필요한 절대 경로 설정이다.
    paths: Pi0PathSettings

    # Dataset/normalization asset 식별 설정이다.
    dataset: Pi0DatasetSettings

    # Parameter 학습 범위를 정하는 fine-tuning 설정이다.
    finetuning: Pi0FinetuningSettings

    # 기존 train_pi0 CLI에 전달할 학습 설정이다.
    training: Pi0TrainingSettings

    # JAX import 전에 적용할 runtime 설정이다.
    runtime: Pi0RuntimeSettings


def _require_mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    """YAML 값이 문자열 key를 가진 mapping인지 확인한다."""

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name}은 mapping이어야 합니다: {type(value).__name__}")
    invalid_keys = [key for key in value if not isinstance(key, str)]
    if invalid_keys:
        raise TypeError(f"{field_name}에 문자열이 아닌 key가 있습니다: {invalid_keys}")
    return value


def _require_exact_keys(
    mapping: Mapping[str, Any],
    expected: frozenset[str],
    *,
    field_name: str,
) -> None:
    """누락되거나 문서화되지 않은 YAML key를 즉시 거부한다."""

    actual = frozenset(mapping)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise ValueError(
            f"{field_name} key 오류: missing={missing}, unknown={unknown}"
        )


def _require_integer(value: Any, *, field_name: str, minimum: int) -> int:
    """bool이 아닌 정수이며 지정한 최솟값 이상인지 확인한다."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name}은 정수여야 합니다: {value!r}")
    if value < minimum:
        raise ValueError(f"{field_name}은 {minimum} 이상이어야 합니다: {value}")
    return value


def _require_number(value: Any, *, field_name: str) -> float:
    """bool이 아닌 유한 실수 값을 float로 변환한다."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name}은 숫자여야 합니다: {value!r}")
    result = float(value)
    if result != result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{field_name}은 유한해야 합니다: {value!r}")
    return result


def _require_string(value: Any, *, field_name: str) -> str:
    """비어 있지 않은 문자열 설정을 확인한다."""

    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name}은 비어 있지 않은 문자열이어야 합니다: {value!r}")
    return value.strip()


def _resolve_workspace_path(
    value: Any,
    *,
    workspace_root: Path,
    field_name: str,
) -> Path:
    """YAML 경로를 workspace 아래의 절대 경로로 제한한다."""

    path_text = _require_string(value, field_name=field_name)
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(workspace_root):
        raise ValueError(
            f"{field_name}이 workspace를 벗어났습니다: {resolved} not under {workspace_root}"
        )
    return resolved


def _validate_locked_section(
    value: Any,
    expected: Mapping[str, Any],
    *,
    field_name: str,
) -> None:
    """잠긴 section의 각 값이 검증된 baseline과 타입까지 같은지 확인한다."""

    actual = _require_mapping(value, field_name=field_name)
    _require_exact_keys(actual, frozenset(expected), field_name=field_name)
    mismatches = {
        key: {
            "expected": expected[key],
            "expected_type": type(expected[key]).__name__,
            "actual": actual[key],
            "actual_type": type(actual[key]).__name__,
        }
        for key in expected
        if type(actual[key]) is not type(expected[key]) or actual[key] != expected[key]
    }
    if mismatches:
        raise ValueError(
            f"{field_name}은 현재 baseline에서 잠긴 계약입니다. "
            f"기존 run을 resume하지 말고 별도 구현이 필요합니다: {mismatches}"
        )


def load_pi0_settings(config_path: Path, workspace_root: Path) -> Pi0Settings:
    """YAML을 읽어 strict schema와 잠긴 π0 계약을 검증한다."""

    resolved_workspace = workspace_root.expanduser().resolve()
    resolved_config = config_path.expanduser()
    if not resolved_config.is_absolute():
        resolved_config = resolved_workspace / resolved_config
    resolved_config = resolved_config.resolve()
    if not resolved_config.is_relative_to(resolved_workspace):
        raise ValueError(
            f"config가 workspace를 벗어났습니다: {resolved_config} not under {resolved_workspace}"
        )
    if not resolved_config.is_file():
        raise FileNotFoundError(f"π0 YAML config가 없습니다: {resolved_config}")

    loaded = yaml.load(
        resolved_config.read_text(encoding="utf-8"),
        Loader=UniqueKeySafeLoader,
    )
    root = _require_mapping(loaded, field_name="config")
    _require_exact_keys(root, TOP_LEVEL_KEYS, field_name="config")

    schema_version = _require_integer(
        root["schema_version"],
        field_name="schema_version",
        minimum=1,
    )
    if schema_version != SETTINGS_SCHEMA_VERSION:
        raise ValueError(
            "지원하지 않는 config schema입니다: "
            f"expected={SETTINGS_SCHEMA_VERSION}, actual={schema_version}"
        )

    paths = _require_mapping(root["paths"], field_name="paths")
    dataset = _require_mapping(root["dataset"], field_name="dataset")
    finetuning = _require_mapping(root["finetuning"], field_name="finetuning")
    training = _require_mapping(root["training"], field_name="training")
    runtime = _require_mapping(root["runtime"], field_name="runtime")
    _require_exact_keys(paths, PATH_KEYS, field_name="paths")
    _require_exact_keys(dataset, DATASET_KEYS, field_name="dataset")
    _require_exact_keys(finetuning, FINETUNING_KEYS, field_name="finetuning")
    _require_exact_keys(training, TRAINING_KEYS, field_name="training")
    _require_exact_keys(runtime, RUNTIME_KEYS, field_name="runtime")

    _validate_locked_section(
        root["optimizer"],
        LOCKED_OPTIMIZER,
        field_name="optimizer",
    )
    _validate_locked_section(
        root["lr_schedule"],
        LOCKED_LR_SCHEDULE,
        field_name="lr_schedule",
    )
    _validate_locked_section(
        root["model_contract"],
        LOCKED_MODEL_CONTRACT,
        field_name="model_contract",
    )

    asset_id = _require_string(dataset["asset_id"], field_name="dataset.asset_id")
    if SAFE_NAME_PATTERN.fullmatch(asset_id) is None:
        raise ValueError(
            "dataset.asset_id는 영문자/숫자로 시작하고 영문자·숫자·._-만 허용합니다: "
            f"{asset_id!r}"
        )

    vision_encoder = _require_string(
        finetuning["vision_encoder"],
        field_name="finetuning.vision_encoder",
    )
    if vision_encoder not in VISION_ENCODER_MODES:
        raise ValueError(
            "finetuning.vision_encoder는 trainable 또는 frozen이어야 합니다: "
            f"{vision_encoder!r}"
        )


    num_train_steps = _require_integer(
        training["num_train_steps"],
        field_name="training.num_train_steps",
        minimum=1,
    )
    batch_size = _require_integer(
        training["batch_size"],
        field_name="training.batch_size",
        minimum=1,
    )
    num_workers = _require_integer(
        training["num_workers"],
        field_name="training.num_workers",
        minimum=0,
    )
    log_interval = _require_integer(
        training["log_interval"],
        field_name="training.log_interval",
        minimum=1,
    )
    save_interval = _require_integer(
        training["save_interval"],
        field_name="training.save_interval",
        minimum=MIN_SAVE_INTERVAL,
    )
    keep_period = _require_integer(
        training["keep_period"],
        field_name="training.keep_period",
        minimum=1,
    )
    seed = _require_integer(
        training["seed"],
        field_name="training.seed",
        minimum=0,
    )
    if batch_size > MAX_BATCH_SIZE:
        raise ValueError(
            f"training.batch_size는 {MAX_BATCH_SIZE} 이하여야 합니다: {batch_size}"
        )
    if num_workers > MAX_NUM_WORKERS:
        raise ValueError(
            f"training.num_workers는 {MAX_NUM_WORKERS} 이하여야 합니다: {num_workers}"
        )
    if keep_period < save_interval or keep_period % save_interval != 0:
        raise ValueError(
            "training.keep_period는 save_interval 이상이면서 그 배수여야 합니다: "
            f"keep={keep_period}, save={save_interval}"
        )

    memory_fraction = _require_number(
        runtime["jax_memory_fraction"],
        field_name="runtime.jax_memory_fraction",
    )
    if not MIN_JAX_MEMORY_FRACTION <= memory_fraction <= MAX_JAX_MEMORY_FRACTION:
        raise ValueError(
            "runtime.jax_memory_fraction은 "
            f"{MIN_JAX_MEMORY_FRACTION:.2f} 이상 {MAX_JAX_MEMORY_FRACTION:.2f} 이하여야 합니다: "
            f"{memory_fraction}"
        )

    progress_refresh_seconds = _require_number(
        runtime["progress_refresh_seconds"],
        field_name="runtime.progress_refresh_seconds",
    )
    if not (
        MIN_PROGRESS_REFRESH_SECONDS
        <= progress_refresh_seconds
        <= MAX_PROGRESS_REFRESH_SECONDS
    ):
        raise ValueError(
            "runtime.progress_refresh_seconds는 "
            f"{MIN_PROGRESS_REFRESH_SECONDS:.1f}~"
            f"{MAX_PROGRESS_REFRESH_SECONDS:.1f}초여야 합니다: "
            f"{progress_refresh_seconds}"
        )

    return Pi0Settings(
        config_path=resolved_config,
        workspace_root=resolved_workspace,
        paths=Pi0PathSettings(
            dataset_root=_resolve_workspace_path(
                paths["dataset_root"],
                workspace_root=resolved_workspace,
                field_name="paths.dataset_root",
            ),
            assets_base_dir=_resolve_workspace_path(
                paths["assets_base_dir"],
                workspace_root=resolved_workspace,
                field_name="paths.assets_base_dir",
            ),
            runs_root=_resolve_workspace_path(
                paths["runs_root"],
                workspace_root=resolved_workspace,
                field_name="paths.runs_root",
            ),
            base_params=_resolve_workspace_path(
                paths["base_params"],
                workspace_root=resolved_workspace,
                field_name="paths.base_params",
            ),
        ),
        dataset=Pi0DatasetSettings(asset_id=asset_id),
        finetuning=Pi0FinetuningSettings(vision_encoder=vision_encoder),
        training=Pi0TrainingSettings(
            num_train_steps=num_train_steps,
            batch_size=batch_size,
            num_workers=num_workers,
            log_interval=log_interval,
            save_interval=save_interval,
            keep_period=keep_period,
            seed=seed,
        ),
        runtime=Pi0RuntimeSettings(
            jax_memory_fraction=memory_fraction,
            progress_refresh_seconds=progress_refresh_seconds,
        ),
    )
