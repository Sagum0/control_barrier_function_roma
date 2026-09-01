"""검증된 OpenPI π0 LoRA 학습을 Piper LeRobot v3 데이터에 실행한다."""

from __future__ import annotations

import argparse
import dataclasses
import functools
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import sys
import time
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence

from flax import nnx
import jax
import numpy as np
import openpi

from openpi.models import model as model_api
from openpi.shared import normalize as openpi_normalize
from openpi.shared import nnx_utils
from openpi.training import checkpoints
from openpi.training import config as training_config
from openpi.training import sharding as training_sharding
from openpi.training import weight_loaders

from piper_vla.training.data import (
    PI0_ACTION_HORIZON,
    PI0_MODEL_ACTION_DIM,
    PI0_PROMPT_TOKEN_LENGTH,
    PiperDataConfigFactory,
    TrainingBatch,
    TrainingDataBundle,
    build_training_data_bundle,
    next_training_batch,
    validate_norm_stats,
)
from piper_vla.training.settings import (
    DEFAULT_PROGRESS_REFRESH_SECONDS,
    MAX_PROGRESS_REFRESH_SECONDS,
    MIN_PROGRESS_REFRESH_SECONDS,
    VISION_ENCODER_FROZEN,
    VISION_ENCODER_MODES,
    VISION_ENCODER_TRAINABLE,
)


# 공식 OpenPI에서 계승할 저메모리 π0 LoRA 설정 이름이다.
OFFICIAL_PI0_LORA_CONFIG_NAME = "pi0_libero_low_mem_finetune"

# Piper π0 checkpoint와 normalization asset을 묶는 설정 이름이다.
PIPER_PI0_CONFIG_NAME = "pi0_piper_lora"

# 검증된 π0 language/image expert의 LoRA variant 이름이다.
EXPECTED_PALIGEMMA_VARIANT = "gemma_2b_lora"

# 검증된 π0 action expert의 LoRA variant 이름이다.
EXPECTED_ACTION_EXPERT_VARIANT = "gemma_300m_lora"

# 경로 탈출을 막으면서 실험과 asset 이름에 허용할 문자 규칙이다.
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

# PaliGemma 내부 Vision tower 전체를 선택하는 NNX parameter 경로 규칙이다.
VISION_ENCODER_FILTER_PATTERN = r"PaliGemma/img/.*"

# Vision encoder 동결 모드에서 공식 freeze filter와 합칠 NNX filter다.
VISION_ENCODER_FILTER = nnx_utils.PathRegex(VISION_ENCODER_FILTER_PATTERN)

# 실제 학습의 기본 global batch size다.
DEFAULT_BATCH_SIZE = 1

# 전체 학습이 도달할 기본 최종 step이다.
DEFAULT_NUM_TRAIN_STEPS = 30_000

# notebook에서 검증된 안정적인 초기 worker 수다.
DEFAULT_NUM_WORKERS = 0

# metric을 화면에 동기화해 출력하는 기본 간격이다.
DEFAULT_LOG_INTERVAL = 10
# durable checkpoint를 남기는 기본 간격이다.
DEFAULT_SAVE_INTERVAL = 1_000

# 장기 보존 checkpoint의 기본 간격이다.
DEFAULT_KEEP_PERIOD = 5_000

# 데이터 순서와 학습 RNG에 함께 쓰는 기본 seed다.
DEFAULT_SEED = 42

# checkpoint 크기와 디스크 여유를 표시할 GiB 단위다.
GIB = 1024**3

# 공식 train.py를 독립 module 이름으로 불러올 때 사용할 내부 이름이다.
OPENPI_TRAIN_MODULE_NAME = "_piper_openpi_train"


def load_openpi_train_module() -> ModuleType:
    """설치 위치와 무관하게 현재 openpi checkout의 공식 scripts/train.py를 불러온다."""

    loaded_module = sys.modules.get(OPENPI_TRAIN_MODULE_NAME)
    if loaded_module is not None:
        return loaded_module

    openpi_init = Path(openpi.__file__).resolve()
    openpi_root = openpi_init.parents[2]
    train_script = openpi_root / "scripts" / "train.py"
    if not train_script.is_file():
        raise FileNotFoundError(f"OpenPI 공식 train.py를 찾을 수 없습니다: {train_script}")

    module_spec = importlib.util.spec_from_file_location(
        OPENPI_TRAIN_MODULE_NAME,
        train_script,
    )
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"OpenPI train.py import spec 생성에 실패했습니다: {train_script}")

    module = importlib.util.module_from_spec(module_spec)
    sys.modules[OPENPI_TRAIN_MODULE_NAME] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(OPENPI_TRAIN_MODULE_NAME, None)
        raise
    return module


# CLI wrapper 없이 package만 import해도 동작하도록 공식 train module을 절대 경로로 고정한다.
OPENPI_TRAIN = load_openpi_train_module()

# train step을 직접 호출하는 JIT 함수의 형식 별칭이다.
JittedTrainStep = Callable[[jax.Array, Any, TrainingBatch], tuple[Any, Mapping[str, Any]]]


@dataclasses.dataclass(frozen=True)
class TrainingOptions:
    """CLI에서 받은 π0 학습 경로와 안전 설정을 보관한다."""

    # 모든 상대 경로의 기준이 되는 workspace 루트다.
    workspace_root: Path

    # Piper LeRobot v3 dataset의 로컬 루트다.
    dataset_root: Path

    # config별 normalization asset을 저장하는 상위 경로다.
    assets_base_dir: Path

    # config와 실험 이름별 checkpoint를 저장하는 상위 경로다.
    runs_root: Path

    # fresh 학습에서 불러올 공식 π0 base params 경로다.
    base_params: Path

    # dataset과 checkpoint asset을 연결하는 안전한 식별자다.
    asset_id: str

    # 같은 설정 아래 개별 학습 실행을 구분하는 안전한 이름이다.
    run_name: str

    # Vision encoder를 학습할지 고정할지 정하는 명시적 모드다.
    vision_encoder_mode: str = VISION_ENCODER_TRAINABLE

    # 추가 step 수가 아니라 학습이 도달할 최종 step이다.
    num_train_steps: int = DEFAULT_NUM_TRAIN_STEPS

    # 한 train step에서 처리하는 global sample 수다.
    batch_size: int = DEFAULT_BATCH_SIZE

    # PyTorch DataLoader가 사용할 subprocess 수다.
    num_workers: int = DEFAULT_NUM_WORKERS

    # metric을 동기화해 출력할 step 간격이다.
    log_interval: int = DEFAULT_LOG_INTERVAL

    # 학습 계산과 무관한 TTY dashboard 갱신 간격이다.
    progress_refresh_seconds: float = DEFAULT_PROGRESS_REFRESH_SECONDS

    # checkpoint를 저장할 step 간격이다.
    save_interval: int = DEFAULT_SAVE_INTERVAL

    # checkpoint manager가 장기 보존할 step 간격이다.
    keep_period: int = DEFAULT_KEEP_PERIOD

    # JAX RNG와 loader shuffle에 사용할 seed다.
    seed: int = DEFAULT_SEED

    # 기존 checkpoint에서 params와 AdamW state를 복원할지 여부다.
    resume: bool = False

    # 모델 weight나 run directory를 건드리지 않고 데이터 계약까지만 검사할지 여부다.
    check_only: bool = False


@dataclasses.dataclass
class TrainingRuntime:
    """학습 중 갱신되는 TrainState와 고정 실행 객체를 묶는다."""

    # 실제 train step이 참조하는 OpenPI 설정이다.
    config: training_config.TrainConfig

    # checkpoint 저장에도 재사용하는 Piper v3 loader 묶음이다.
    data: TrainingDataBundle

    # 현재 params, optimizer, absolute step을 가진 OpenPI TrainState다.
    state: Any

    # TrainState 입출력에 적용할 JAX sharding tree다.
    state_sharding: Any

    # 비동기 checkpoint 저장과 retention을 관리하는 Orbax manager다.
    checkpoint_manager: Any

    # train_step 내부에서 state.step과 fold-in할 고정 base RNG다.
    train_rng: jax.Array

    # 현재 run이 사용하는 Vision encoder 학습 모드다.
    vision_encoder_mode: str


@dataclasses.dataclass(frozen=True)
class RejectBaseWeightLoader:
    """Resume 중 base checkpoint에 잘못 접근하면 즉시 중단한다."""

    def load(self, params: Any) -> Any:
        """Checkpoint-only resume에서 허용되지 않는 base weight load를 거부한다."""

        del params
        raise AssertionError("Resume 중 base weight_loader.load()가 호출됐습니다.")


def validate_safe_name(value: str, *, field_name: str) -> str:
    """실험·asset 이름이 하위 경로 하나로만 안전하게 표현되는지 확인한다."""

    if value in {".", ".."} or SAFE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{field_name}은 영문자/숫자로 시작하고 영문자·숫자·._-만 써야 합니다: "
            f"{value!r}"
        )
    return value


def resolve_workspace_path(path: Path, workspace_root: Path) -> Path:
    """상대 경로를 현재 shell이 아니라 workspace를 기준으로 절대화한다."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = workspace_root / expanded
    return expanded.resolve()


def validate_workspace_path(path: Path, workspace_root: Path, *, field_name: str) -> None:
    """사용자가 지정한 저장·입력 경로가 단일 workspace 안에 있는지 확인한다."""

    resolved_path = path.expanduser().resolve()
    resolved_workspace = workspace_root.expanduser().resolve()
    if not resolved_path.is_relative_to(resolved_workspace):
        raise ValueError(
            f"{field_name} 경로는 workspace 안에 있어야 합니다: "
            f"{resolved_path} not under {resolved_workspace}"
        )


def validate_training_options(options: TrainingOptions) -> None:
    """외부 파일을 읽기 전에 CLI 이름, 수치, workspace 경계를 먼저 검증한다."""

    validate_safe_name(options.asset_id, field_name="asset_id")
    validate_safe_name(options.run_name, field_name="run_name")
    if options.vision_encoder_mode not in VISION_ENCODER_MODES:
        raise ValueError(
            f"지원하지 않는 Vision encoder 모드입니다: {options.vision_encoder_mode!r}"
        )
    validate_workspace_path(options.dataset_root, options.workspace_root, field_name="dataset_root")
    validate_workspace_path(
        options.assets_base_dir,
        options.workspace_root,
        field_name="assets_base_dir",
    )
    validate_workspace_path(options.runs_root, options.workspace_root, field_name="runs_root")
    validate_workspace_path(options.base_params, options.workspace_root, field_name="base_params")

    positive_values = {
        "num_train_steps": options.num_train_steps,
        "batch_size": options.batch_size,
        "log_interval": options.log_interval,
        "save_interval": options.save_interval,
        "keep_period": options.keep_period,
    }
    invalid_values = {name: value for name, value in positive_values.items() if value <= 0}
    if invalid_values:
        raise ValueError(f"양수여야 하는 학습 설정이 잘못됐습니다: {invalid_values}")
    if (
        not math.isfinite(options.progress_refresh_seconds)
        or not MIN_PROGRESS_REFRESH_SECONDS
        <= options.progress_refresh_seconds
        <= MAX_PROGRESS_REFRESH_SECONDS
    ):
        raise ValueError(
            "progress_refresh_seconds 범위가 잘못됐습니다: "
            f"{options.progress_refresh_seconds!r}; "
            f"허용={MIN_PROGRESS_REFRESH_SECONDS:.1f}~{MAX_PROGRESS_REFRESH_SECONDS:.1f}초"
        )
    if options.num_workers < 0:
        raise ValueError(f"num_workers는 음수가 될 수 없습니다: {options.num_workers}")
    if not options.dataset_root.is_dir():
        raise FileNotFoundError(f"LeRobot v3 dataset 경로가 없습니다: {options.dataset_root}")

    expected_norm_path = (
        options.assets_base_dir
        / PIPER_PI0_CONFIG_NAME
        / options.asset_id
        / "norm_stats.json"
    ).resolve()
    if not expected_norm_path.is_file():
        raise FileNotFoundError(f"Piper normalization asset이 없습니다: {expected_norm_path}")

    checkpoint_dir = (
        options.runs_root / PIPER_PI0_CONFIG_NAME / options.run_name
    ).resolve()
    if not options.check_only:
        if options.resume:
            if not checkpoint_dir.is_dir():
                raise FileNotFoundError(f"resume할 run directory가 없습니다: {checkpoint_dir}")
        else:
            if checkpoint_dir.exists():
                raise FileExistsError(
                    "새 학습 run 경로가 이미 존재합니다. 삭제하거나 덮어쓰지 않습니다. "
                    f"새 --run-name을 사용하세요: {checkpoint_dir}"
                )
            if not options.base_params.is_dir():
                raise FileNotFoundError(f"π0 base params 경로가 없습니다: {options.base_params}")


def build_freeze_filter(official_filter: Any, vision_encoder_mode: str) -> Any:
    """공식 LLM LoRA filter에 선택적으로 Vision tower 동결 범위를 합친다."""

    if vision_encoder_mode == VISION_ENCODER_TRAINABLE:
        return official_filter
    if vision_encoder_mode == VISION_ENCODER_FROZEN:
        return nnx.Any(official_filter, VISION_ENCODER_FILTER)
    raise ValueError(
        f"지원하지 않는 Vision encoder 모드입니다: {vision_encoder_mode!r}"
    )


def build_pi0_train_config(options: TrainingOptions) -> training_config.TrainConfig:
    """공식 low-memory π0 LoRA 설정을 Piper 경로와 transform으로 파생한다."""

    official_config = training_config.get_config(OFFICIAL_PI0_LORA_CONFIG_NAME)
    config = dataclasses.replace(
        official_config,
        name=PIPER_PI0_CONFIG_NAME,
        exp_name=options.run_name,
        data=PiperDataConfigFactory(
            repo_id=options.asset_id,
            assets=training_config.AssetsConfig(asset_id=options.asset_id),
        ),
        weight_loader=weight_loaders.CheckpointWeightLoader(str(options.base_params)),
        freeze_filter=build_freeze_filter(official_config.freeze_filter, options.vision_encoder_mode),
        assets_base_dir=str(options.assets_base_dir),
        checkpoint_base_dir=str(options.runs_root),
        batch_size=options.batch_size,
        num_workers=options.num_workers,
        num_train_steps=options.num_train_steps,
        log_interval=options.log_interval,
        save_interval=options.save_interval,
        keep_period=options.keep_period,
        seed=options.seed,
        fsdp_devices=1,
        wandb_enabled=False,
        overwrite=False,
        resume=options.resume,
    )
    validate_pi0_train_config(config, options)
    return config


def validate_pi0_train_config(
    config: training_config.TrainConfig,
    options: TrainingOptions,
) -> None:
    """공식 π0 LoRA 구조와 Piper normalization 계약이 보존됐는지 확인한다."""

    if config.name != PIPER_PI0_CONFIG_NAME or config.exp_name != options.run_name:
        raise ValueError("TrainConfig의 config/run 이름이 요청과 다릅니다.")
    if config.model.model_type is not model_api.ModelType.PI0:
        raise ValueError(f"π0가 아닌 model type입니다: {config.model.model_type}")
    if getattr(config.model, "pi05", False):
        raise ValueError("현재 학습 코드는 π0.5가 아니라 π0 전용입니다.")
    if config.model.paligemma_variant != EXPECTED_PALIGEMMA_VARIANT:
        raise ValueError(f"PaliGemma LoRA variant가 다릅니다: {config.model.paligemma_variant}")
    if config.model.action_expert_variant != EXPECTED_ACTION_EXPERT_VARIANT:
        raise ValueError(
            f"action expert LoRA variant가 다릅니다: {config.model.action_expert_variant}"
        )
    if config.model.action_dim != PI0_MODEL_ACTION_DIM:
        raise ValueError(f"π0 action dimension 오류: {config.model.action_dim}")
    if config.model.action_horizon != PI0_ACTION_HORIZON:
        raise ValueError(f"π0 action horizon 오류: {config.model.action_horizon}")
    if config.model.max_token_len != PI0_PROMPT_TOKEN_LENGTH:
        raise ValueError(f"π0 prompt token length 오류: {config.model.max_token_len}")
    if config.ema_decay is not None:
        raise ValueError("공식 low-memory π0 LoRA는 EMA를 사용하지 않아야 합니다.")
    if config.freeze_filter is None:
        raise ValueError("π0 LoRA freeze filter가 없습니다.")
    if config.overwrite:
        raise ValueError("이 학습 명령은 checkpoint 자동 overwrite를 허용하지 않습니다.")
    if config.resume != options.resume:
        raise ValueError("TrainConfig와 CLI의 resume 설정이 다릅니다.")

    expected_config_root = (options.runs_root / PIPER_PI0_CONFIG_NAME).resolve()
    checkpoint_dir = Path(config.checkpoint_dir).resolve()
    if not checkpoint_dir.is_relative_to(expected_config_root):
        raise ValueError(
            "checkpoint 경로가 허용된 run root를 벗어났습니다: "
            f"{checkpoint_dir} not under {expected_config_root}"
        )

    data_config = config.data.create(config.assets_dirs, config.model)
    if data_config.repo_id != options.asset_id or data_config.asset_id != options.asset_id:
        raise ValueError("Piper dataset과 normalization asset 식별자가 다릅니다.")
    if data_config.use_quantile_norm:
        raise ValueError("π0는 quantile normalization을 사용하면 안 됩니다.")


def validate_resume_norm_stats(
    checkpoint_dir: Path,
    step: int,
    data_config: training_config.DataConfig,
) -> Path:
    """Checkpoint asset과 현재 dataset의 normalization 통계가 정확히 같은지 검증한다."""

    if data_config.asset_id is None or data_config.norm_stats is None:
        raise ValueError("현재 Piper DataConfig에 asset_id 또는 norm_stats가 없습니다.")
    validate_norm_stats(data_config.norm_stats)

    checkpoint_step_dir = (checkpoint_dir / str(step)).resolve()
    required_checkpoint_paths = (
        checkpoint_step_dir / "_CHECKPOINT_METADATA",
        checkpoint_step_dir / "params",
        checkpoint_step_dir / "train_state",
    )
    missing_checkpoint_paths = [
        str(path) for path in required_checkpoint_paths if not path.exists()
    ]
    if missing_checkpoint_paths:
        raise FileNotFoundError(
            f"checkpoint 필수 항목이 없습니다: {missing_checkpoint_paths}"
        )

    checkpoint_asset_dir = (
        checkpoint_step_dir / "assets" / data_config.asset_id
    ).resolve()
    checkpoint_norm_path = checkpoint_asset_dir / "norm_stats.json"
    if not checkpoint_norm_path.is_file():
        raise FileNotFoundError(
            f"checkpoint normalization asset이 없습니다: {checkpoint_norm_path}"
        )

    checkpoint_stats = openpi_normalize.load(checkpoint_asset_dir)
    validate_norm_stats(checkpoint_stats)
    if set(checkpoint_stats) != set(data_config.norm_stats):
        raise ValueError(
            "checkpoint와 현재 normalization key가 다릅니다: "
            f"checkpoint={tuple(checkpoint_stats)}, current={tuple(data_config.norm_stats)}"
        )

    for key in ("state", "actions"):
        for field_name in ("mean", "std", "q01", "q99"):
            checkpoint_value = np.asarray(getattr(checkpoint_stats[key], field_name))
            current_value = np.asarray(getattr(data_config.norm_stats[key], field_name))
            try:
                np.testing.assert_allclose(
                    checkpoint_value,
                    current_value,
                    rtol=0.0,
                    atol=0.0,
                )
            except AssertionError as error:
                raise ValueError(
                    "checkpoint와 현재 normalization 값이 다릅니다: "
                    f"{key}.{field_name}"
                ) from error
    return checkpoint_norm_path


def run_data_contract_check(
    options: TrainingOptions,
    config: training_config.TrainConfig,
) -> None:
    """모델 weight나 run directory 없이 실제 v3 sample 한 batch를 검증한다."""

    bundle = build_training_data_bundle(
        config,
        options.dataset_root,
        shuffle=False,
        num_batches=1,
    )
    observation, actions = next_training_batch(bundle, config, validate=True)
    print("Dataset frames    :", f"{len(bundle.raw_dataset):,}")
    print("State batch       :", observation.state.shape, observation.state.dtype)
    print("Action batch      :", actions.shape, actions.dtype)
    print("Prompt batch      :", observation.tokenized_prompt.shape)
    print("PASS: Piper v3 -> OpenPI π0 data contract")
    print("PASS: model weights not loaded")
    print("PASS: run directory not created")


def validate_resume_vision_encoder_mode(
    checkpoint_dir: Path,
    requested_mode: str,
) -> Path:
    """기존 JSONL의 Vision 학습 모드가 현재 resume 요청과 같은지 검증한다."""

    if requested_mode not in VISION_ENCODER_MODES:
        raise ValueError(
            f"지원하지 않는 Vision encoder 모드입니다: {requested_mode!r}"
        )

    metrics_path = checkpoint_dir.resolve() / "training_metrics.jsonl"
    if not metrics_path.is_file():
        raise FileNotFoundError(
            "Vision encoder 모드를 검증할 기존 JSONL이 없습니다: "
            f"{metrics_path}"
        )

    raw_text = metrics_path.read_text(encoding="utf-8")
    if raw_text and not raw_text.endswith("\n"):
        raise ValueError(
            "기존 JSONL의 마지막 record가 newline으로 끝나지 않습니다. "
            f"자동 수정하지 않으므로 로그를 확인하세요: {metrics_path}"
        )
    lines = raw_text.splitlines()
    recorded_modes: set[str] = set()
    session_records = 0
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"기존 JSONL {line_number}행을 해석할 수 없습니다: {metrics_path}"
            ) from error
        if record.get("event") != "session_start":
            continue
        session_records += 1
        recorded_mode = record.get(
            "vision_encoder_mode",
            VISION_ENCODER_TRAINABLE,
        )
        if recorded_mode not in VISION_ENCODER_MODES:
            raise ValueError(
                f"기존 JSONL에 알 수 없는 Vision encoder 모드가 있습니다: {recorded_mode!r}"
            )
        recorded_modes.add(recorded_mode)

    if session_records == 0:
        raise ValueError(f"기존 JSONL에 session_start record가 없습니다: {metrics_path}")
    if recorded_modes != {requested_mode}:
        raise ValueError(
            "Vision encoder 학습 모드가 기존 run과 다릅니다. "
            f"recorded={sorted(recorded_modes)}, requested={requested_mode!r}. "
            "다른 모드는 새 --run-name으로 시작하세요."
        )
    return metrics_path

def create_resume_manager(config: training_config.TrainConfig) -> tuple[Any, int]:
    """기존 run을 resume 모드로 열고 Orbax가 인정한 최신 완료 step을 반환한다."""

    manager, resuming = checkpoints.initialize_checkpoint_dir(
        config.checkpoint_dir,
        keep_period=config.keep_period,
        overwrite=False,
        resume=True,
    )
    if not resuming:
        raise RuntimeError(f"유효한 resume checkpoint가 없습니다: {config.checkpoint_dir}")

    available_steps = tuple(manager.all_steps())
    latest_step = manager.latest_step()
    if latest_step is None or latest_step <= 0 or latest_step not in available_steps:
        raise RuntimeError(
            f"checkpoint manager의 latest step이 올바르지 않습니다: {available_steps=}"
        )
    if latest_step > config.num_train_steps:
        raise ValueError(
            f"latest checkpoint {latest_step}이 목표 {config.num_train_steps}보다 큽니다."
        )
    return manager, int(latest_step)


def initialize_fresh_runtime(
    config: training_config.TrainConfig,
    data: TrainingDataBundle,
    *,
    vision_encoder_mode: str,
) -> TrainingRuntime:
    """π0 base params에서 실제 LoRA TrainState를 만든 뒤 새 run manager를 생성한다."""

    checkpoint_dir = Path(config.checkpoint_dir)
    if checkpoint_dir.exists():
        raise FileExistsError(f"새 run 경로가 이미 존재합니다: {checkpoint_dir}")

    master_rng = jax.random.key(config.seed)
    train_rng, init_rng = jax.random.split(master_rng)
    print("Loading π0 base weights and initializing LoRA TrainState...")
    state, state_sharding = OPENPI_TRAIN.init_train_state(
        config,
        init_rng,
        data.mesh,
        resume=False,
    )
    state = jax.block_until_ready(state)
    if int(jax.device_get(state.step)) != 0:
        raise RuntimeError(f"fresh TrainState가 step 0이 아닙니다: {state.step}")

    manager, resuming = checkpoints.initialize_checkpoint_dir(
        config.checkpoint_dir,
        keep_period=config.keep_period,
        overwrite=False,
        resume=False,
    )
    if resuming:
        raise RuntimeError("새 run manager가 예기치 않게 resume 상태로 열렸습니다.")

    return TrainingRuntime(
        config=config,
        data=data,
        state=state,
        state_sharding=state_sharding,
        checkpoint_manager=manager,
        train_rng=train_rng,
        vision_encoder_mode=vision_encoder_mode,
    )


def initialize_resumed_runtime(
    config: training_config.TrainConfig,
    data: TrainingDataBundle,
    manager: Any,
    latest_step: int,
    *,
    vision_encoder_mode: str,
) -> TrainingRuntime:
    """base weight를 읽지 않고 최신 checkpoint의 params와 AdamW state를 복원한다."""

    resume_config = dataclasses.replace(
        config,
        weight_loader=RejectBaseWeightLoader(),
        overwrite=False,
        resume=True,
    )
    checkpoint_norm_path = validate_resume_norm_stats(
        Path(resume_config.checkpoint_dir),
        latest_step,
        data.data_config,
    )
    print("Resume norm asset  :", checkpoint_norm_path)

    master_rng = jax.random.key(resume_config.seed)
    train_rng, init_rng = jax.random.split(master_rng)
    abstract_state, state_sharding = OPENPI_TRAIN.init_train_state(
        resume_config,
        init_rng,
        data.mesh,
        resume=True,
    )
    state = checkpoints.restore_state(
        manager,
        abstract_state,
        data.loader,
        step=latest_step,
    )
    state = jax.block_until_ready(state)
    restored_step = int(jax.device_get(state.step))
    if restored_step != latest_step:
        raise RuntimeError(
            f"복원된 TrainState step이 latest와 다릅니다: {restored_step} != {latest_step}"
        )

    return TrainingRuntime(
        config=resume_config,
        data=data,
        state=state,
        state_sharding=state_sharding,
        checkpoint_manager=manager,
        train_rng=train_rng,
        vision_encoder_mode=vision_encoder_mode,
    )


def prepare_training_runtime(
    config: training_config.TrainConfig,
    data: TrainingDataBundle,
    *,
    resume_manager: Any | None,
    resume_step: int,
    vision_encoder_mode: str,
) -> TrainingRuntime:
    """Fresh 또는 resume 설정에 맞는 실제 학습 runtime을 준비한다."""

    if config.resume:
        if resume_manager is None or resume_step <= 0:
            raise ValueError("resume manager 또는 latest step이 준비되지 않았습니다.")
        return initialize_resumed_runtime(
            config,
            data,
            resume_manager,
            resume_step,
            vision_encoder_mode=vision_encoder_mode,
        )
    if resume_manager is not None or resume_step != 0:
        raise ValueError("fresh 학습에 resume 객체가 전달됐습니다.")
    return initialize_fresh_runtime(
        config,
        data,
        vision_encoder_mode=vision_encoder_mode,
    )


def build_jitted_train_step(runtime: TrainingRuntime) -> JittedTrainStep:
    """OpenPI 공식 sharding과 state donation을 적용한 직접 호출 JIT 함수를 만든다."""

    return jax.jit(
        functools.partial(OPENPI_TRAIN.train_step, runtime.config),
        in_shardings=(
            runtime.data.replicated_sharding,
            runtime.state_sharding,
            runtime.data.data_sharding,
        ),
        out_shardings=(
            runtime.state_sharding,
            runtime.data.replicated_sharding,
        ),
        donate_argnums=(1,),
    )


def metrics_to_host(metrics: Mapping[str, Any]) -> dict[str, float]:
    """세 scalar metric만 host float로 옮기고 NaN/Inf를 거부한다."""

    host_metrics = jax.device_get(metrics)
    expected_keys = {"loss", "grad_norm", "param_norm"}
    if set(host_metrics) != expected_keys:
        raise ValueError(f"train metric key가 다릅니다: {tuple(host_metrics)}")

    result = {name: float(np.asarray(value)) for name, value in host_metrics.items()}
    if not all(np.isfinite(value) for value in result.values()):
        raise FloatingPointError(f"train metric에 NaN/Inf가 있습니다: {result}")
    if any(result[name] < 0 for name in expected_keys):
        raise FloatingPointError(f"train metric에 음수가 있습니다: {result}")
    return result


def tree_logical_nbytes(tree: Any) -> int:
    """장치 배열을 host로 복사하지 않고 pytree의 논리 byte 수를 계산한다."""

    total = 0
    for leaf in jax.tree.leaves(tree):
        if hasattr(leaf, "shape") and hasattr(leaf, "dtype"):
            total += math.prod(leaf.shape) * int(leaf.dtype.itemsize)
    return int(total)


def nearest_existing_parent(path: Path) -> Path:
    """디스크 여유를 조회할 수 있는 가장 가까운 기존 상위 경로를 찾는다."""

    current = path
    while not current.exists():
        if current.parent == current:
            raise RuntimeError(f"기존 상위 경로를 찾을 수 없습니다: {path}")
        current = current.parent
    return current


def verify_checkpoint_disk_space(runtime: TrainingRuntime) -> tuple[int, int]:
    """Orbax 임시 파일을 포함해 다음 checkpoint를 저장할 여유가 있는지 확인한다."""

    payload_bytes = (
        tree_logical_nbytes(runtime.state.params)
        + tree_logical_nbytes(runtime.state.opt_state)
        + tree_logical_nbytes(runtime.state.step)
    )
    required_bytes = int(payload_bytes * 1.25) + 2 * GIB
    filesystem_root = nearest_existing_parent(Path(runtime.config.checkpoint_dir))
    free_bytes = shutil.disk_usage(filesystem_root).free
    if free_bytes < required_bytes:
        raise RuntimeError(
            "checkpoint 디스크 여유가 부족합니다: "
            f"free={free_bytes / GIB:.2f} GiB, required={required_bytes / GIB:.2f} GiB"
        )
    return free_bytes, required_bytes


def save_training_checkpoint(runtime: TrainingRuntime, step: int) -> None:
    """현재 state와 Piper norm asset을 비동기로 저장하고 commit 완료까지 기다린다."""

    actual_step = int(jax.device_get(runtime.state.step))
    if actual_step != step:
        raise RuntimeError(f"저장 step과 TrainState step이 다릅니다: {step} != {actual_step}")

    manager = runtime.checkpoint_manager
    manager.wait_until_finished()
    existing_steps = tuple(manager.all_steps())
    if step in existing_steps:
        raise FileExistsError(f"같은 checkpoint step을 덮어쓰지 않습니다: {step}")

    verify_checkpoint_disk_space(runtime)
    checkpoints.save_state(
        manager,
        runtime.state,
        runtime.data.loader,
        step,
    )
    manager.wait_until_finished()

    saved_steps = tuple(manager.all_steps())
    if step not in saved_steps or manager.latest_step() != step:
        raise RuntimeError(
            f"checkpoint commit 검증에 실패했습니다: steps={saved_steps}, latest={manager.latest_step()}"
        )



def print_configuration_summary(
    options: TrainingOptions,
    config: training_config.TrainConfig,
) -> None:
    """쓰기 작업 전에 최종 경로와 핵심 학습 계약을 한 화면에 출력한다."""

    norm_path = (
        options.assets_base_dir
        / PIPER_PI0_CONFIG_NAME
        / options.asset_id
        / "norm_stats.json"
    )
    print("Config name       :", config.name)
    print("Experiment name   :", config.exp_name)
    print("Dataset           :", options.dataset_root)
    print("Norm stats        :", norm_path)
    print("Checkpoint dir    :", config.checkpoint_dir)
    print("Base params       :", options.base_params if not options.resume else "NOT USED")
    print(
        "LoRA variants     :",
        config.model.paligemma_variant,
        "/",
        config.model.action_expert_variant,
    )
    print("Vision encoder    :", options.vision_encoder_mode)
    print("Steps / batch     :", config.num_train_steps, "/", config.batch_size)
    print("Progress refresh  :", options.progress_refresh_seconds, "seconds")
    print("Mode              :", "CHECK ONLY" if options.check_only else "RESUME" if options.resume else "FRESH")


def execute(options: TrainingOptions) -> int:
    """검증, loader 연결, state 초기화/복원, 학습 loop를 안전한 순서로 실행한다."""

    validate_training_options(options)
    config = build_pi0_train_config(options)
    print_configuration_summary(options, config)

    if options.check_only:
        run_data_contract_check(options, config)
        return 0

    resume_manager = None
    resume_step = 0
    if options.resume:
        validate_resume_vision_encoder_mode(
            Path(config.checkpoint_dir),
            options.vision_encoder_mode,
        )
        resume_manager, resume_step = create_resume_manager(config)
        if resume_step == options.num_train_steps:
            current_data_config = config.data.create(config.assets_dirs, config.model)
            checkpoint_norm_path = validate_resume_norm_stats(
                Path(config.checkpoint_dir),
                resume_step,
                current_data_config,
            )
            resume_manager.wait_until_finished()
            print("Resume norm asset  :", checkpoint_norm_path)
            print(
                "PASS: Orbax latest checkpoint가 이미 목표 step입니다; "
                "모델·GPU·run directory를 변경하지 않았습니다."
            )
            return 0

    if jax.default_backend() != "gpu":
        raise RuntimeError(f"실제 학습에는 JAX GPU backend가 필요합니다: {jax.default_backend()}")

    if options.resume:
        print(
            "Resume note       : loader iterator 위치는 checkpoint되지 않으므로 "
            f"shuffle seed를 seed+latest_step({options.seed}+{resume_step})로 재시작합니다."
        )

    data = build_training_data_bundle(
        config,
        options.dataset_root,
        shuffle=True,
        seed_offset=resume_step,
        num_batches=None,
    )
    first_batch_started = time.perf_counter()
    first_batch = next_training_batch(data, config, validate=True)
    first_batch_data_time_s = time.perf_counter() - first_batch_started
    print(
        "PASS: first shuffled JAX batch validated",
        f"({first_batch_data_time_s:.3f}s)",
    )

    runtime = prepare_training_runtime(
        config,
        data,
        resume_manager=resume_manager,
        resume_step=resume_step,
        vision_encoder_mode=options.vision_encoder_mode,
    )
    restored_or_initialized_step = int(jax.device_get(runtime.state.step))
    print("TrainState step    :", restored_or_initialized_step)
    print("JAX device         :", jax.devices())
    from piper_vla.training.diagnostics import run_training_loop_with_diagnostics

    run_training_loop_with_diagnostics(
        runtime,
        first_batch,
        first_batch_data_time_s,
        progress_refresh_seconds=options.progress_refresh_seconds,
    )
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    """자동 overwrite 옵션이 없는 안전한 π0 학습 CLI parser를 만든다."""

    parser = argparse.ArgumentParser(
        description="Piper LeRobot v3 데이터로 OpenPI π0 LoRA를 학습합니다.",
    )
    parser.add_argument(
        "--run-name",
        required=True,
        help="새 실행 또는 기존 resume checkpoint를 식별하는 이름",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/datasets/pick_green_to_orange/background_400_0818_v3"),
        help="Piper LeRobot v3 dataset 경로",
    )
    parser.add_argument(
        "--asset-id",
        default="background_400_0818_v3",
        help="norm_stats와 checkpoint asset에 사용할 식별자",
    )
    parser.add_argument(
        "--assets-base-dir",
        type=Path,
        default=Path("data/assets"),
        help="config별 normalization asset 상위 경로",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("data/runs"),
        help="config와 run 이름별 checkpoint 상위 경로",
    )
    parser.add_argument(
        "--base-params",
        type=Path,
        default=Path("data/cache/openpi/openpi-assets/checkpoints/pi0_base/params"),
        help="fresh 학습에서만 사용하는 π0 base params 경로",
    )
    parser.add_argument(
        "--vision-encoder",
        choices=sorted(VISION_ENCODER_MODES),
        default=VISION_ENCODER_TRAINABLE,
        help="Vision encoder parameter를 학습(trainable)하거나 고정(frozen)",
    )

    parser.add_argument(
        "--num-train-steps",
        type=int,
        default=DEFAULT_NUM_TRAIN_STEPS,
        help="추가 횟수가 아니라 학습이 도달할 최종 absolute step",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--num-workers", type=int, default=DEFAULT_NUM_WORKERS)
    parser.add_argument("--log-interval", type=int, default=DEFAULT_LOG_INTERVAL)
    parser.add_argument(
        "--progress-refresh-seconds",
        type=float,
        default=DEFAULT_PROGRESS_REFRESH_SECONDS,
        help="TTY dashboard 갱신 간격(초); metric/JAX 동기화 주기와 무관",
    )
    parser.add_argument("--save-interval", type=int, default=DEFAULT_SAVE_INTERVAL)
    parser.add_argument("--keep-period", type=int, default=DEFAULT_KEEP_PERIOD)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="같은 run의 latest checkpoint에서 이어서 학습",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="CPU에서 실제 sample 한 batch까지만 검사하고 weight/run은 건드리지 않음",
    )
    return parser


def options_from_namespace(
    namespace: argparse.Namespace,
    workspace_root: Path,
) -> TrainingOptions:
    """argparse 결과의 모든 경로를 workspace 기준 절대 경로로 변환한다."""

    workspace_root = workspace_root.expanduser().resolve()
    return TrainingOptions(
        workspace_root=workspace_root,
        dataset_root=resolve_workspace_path(namespace.dataset_root, workspace_root),
        assets_base_dir=resolve_workspace_path(namespace.assets_base_dir, workspace_root),
        runs_root=resolve_workspace_path(namespace.runs_root, workspace_root),
        base_params=resolve_workspace_path(namespace.base_params, workspace_root),
        asset_id=namespace.asset_id,
        run_name=namespace.run_name,
        vision_encoder_mode=namespace.vision_encoder,
        num_train_steps=namespace.num_train_steps,
        batch_size=namespace.batch_size,
        num_workers=namespace.num_workers,
        log_interval=namespace.log_interval,
        progress_refresh_seconds=namespace.progress_refresh_seconds,
        save_interval=namespace.save_interval,
        keep_period=namespace.keep_period,
        seed=namespace.seed,
        resume=namespace.resume,
        check_only=namespace.check_only,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    workspace_root: Path | None = None,
) -> int:
    """CLI 인자를 해석해 Piper π0 LoRA 학습을 실행한다."""

    resolved_workspace = (
        Path.cwd().resolve() if workspace_root is None else workspace_root.expanduser().resolve()
    )
    parser = build_argument_parser()
    namespace = parser.parse_args(argv)
    options = options_from_namespace(namespace, resolved_workspace)
    return execute(options)
