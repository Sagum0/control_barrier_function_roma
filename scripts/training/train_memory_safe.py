#!/usr/bin/env python3
"""기존 pi0 YAML 학습에 저메모리 Orbax checkpoint manager를 적용한다."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable, Sequence


# 이 launcher가 속한 workspace 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# 학습 dependency가 설치된 workspace conda Python 경로다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"

# 검증된 YAML 파싱과 인자 변환을 재사용할 기존 wrapper다.
CONFIG_WRAPPER_PATH = WORKSPACE_ROOT / "scripts" / "training" / "train_from_config.py"

# OpenPI commit·cache·Python path 검증을 재사용할 기존 bootstrap이다.
TRAIN_BOOTSTRAP_PATH = WORKSPACE_ROOT / "scripts" / "training" / "train.py"

# Full params에서 동시에 host staging할 최대 decimal GB다.
# 가장 큰 bf16 leaf 약 2.42GB보다 크면서 기존 기본값 96GB보다 작다.
PARAMS_CONCURRENT_GB = 3

# AdamW state에서 동시에 host staging할 최대 decimal GB다.
# 가장 큰 float32 leaf 약 0.54GB보다 큰 안전한 최소값이다.
TRAIN_STATE_CONCURRENT_GB = 1

# 동적으로 불러온 기존 config wrapper의 내부 module 이름이다.
CONFIG_WRAPPER_MODULE_NAME = "_piper_config_wrapper_memory_safe"

# 동적으로 불러온 기존 train bootstrap의 내부 module 이름이다.
TRAIN_BOOTSTRAP_MODULE_NAME = "_piper_train_bootstrap_memory_safe"


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 실행됐으면 workspace conda Python으로 교체한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"workspace Python이 없습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def load_local_module(path: Path, module_name: str) -> ModuleType:
    """기존 실행 파일을 main 실행 없이 고유 module 이름으로 불러온다."""

    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"Module spec을 만들 수 없습니다: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    return module


def build_memory_limited_initializer() -> Callable[..., tuple[Any, bool]]:
    """OpenPI 형식은 유지하고 PyTree host staging만 제한하는 함수를 만든다."""

    # JAX memory 환경을 설정한 뒤에만 무거운 Orbax/OpenPI module을 불러온다.
    import orbax.checkpoint as ocp
    from openpi.training import checkpoints

    def initialize_checkpoint_dir(
        checkpoint_dir: Path | str,
        *,
        keep_period: int | None,
        overwrite: bool,
        resume: bool,
    ) -> tuple[Any, bool]:
        """기존 layout·retention·async 계약으로 memory-limited manager를 연다."""

        if overwrite:
            raise RuntimeError("Memory-safe launcher는 checkpoint overwrite를 허용하지 않습니다.")
        resolved_dir = Path(checkpoint_dir).resolve()
        resuming = False
        if resolved_dir.exists():
            if resume:
                resuming = True
            else:
                raise FileExistsError(
                    f"Checkpoint directory가 이미 있습니다: {resolved_dir}. "
                    "새 run 이름 또는 --resume을 사용하세요."
                )
        resolved_dir.mkdir(parents=True, exist_ok=True)

        manager = ocp.CheckpointManager(
            resolved_dir,
            item_handlers={
                "assets": checkpoints.CallbackHandler(),
                "train_state": ocp.PyTreeCheckpointHandler(
                    save_concurrent_gb=TRAIN_STATE_CONCURRENT_GB,
                    restore_concurrent_gb=TRAIN_STATE_CONCURRENT_GB,
                ),
                "params": ocp.PyTreeCheckpointHandler(
                    save_concurrent_gb=PARAMS_CONCURRENT_GB,
                    restore_concurrent_gb=PARAMS_CONCURRENT_GB,
                ),
            },
            options=ocp.CheckpointManagerOptions(
                max_to_keep=1,
                keep_period=keep_period,
                create=False,
                async_options=ocp.AsyncOptions(timeout_secs=7200),
            ),
        )

        # OpenPI와 동일하게 비어 있거나 step 0뿐인 경로는 resume으로 보지 않는다.
        if resuming and tuple(manager.all_steps()) in [(), (0,)]:
            resuming = False
        return manager, resuming

    return initialize_checkpoint_dir


def main(argv: Sequence[str] | None = None) -> int:
    """YAML을 검증한 뒤 checkpoint manager만 제한해 기존 학습 main을 호출한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)

    config_wrapper = load_local_module(
        CONFIG_WRAPPER_PATH,
        CONFIG_WRAPPER_MODULE_NAME,
    )
    config_wrapper.configure_python_path()

    # 이 loader는 JAX/OpenPI를 import하지 않으므로 memory 환경 설정 전에도 안전하다.
    from piper_vla.training.settings import load_pi0_settings

    namespace = config_wrapper.build_argument_parser().parse_args(arguments)
    settings = load_pi0_settings(namespace.config, WORKSPACE_ROOT)
    target_step = (
        settings.training.num_train_steps
        if namespace.target_step is None
        else namespace.target_step
    )
    if target_step <= 0:
        raise ValueError(f"--target-step은 양수여야 합니다: {target_step}")
    if target_step > settings.training.num_train_steps:
        raise ValueError(
            "--target-step은 YAML training.num_train_steps 이하만 허용합니다: "
            f"target={target_step}, final={settings.training.num_train_steps}"
        )

    config_wrapper.print_resolved_settings(settings, target_step=target_step)
    if namespace.print_config:
        print(
            "Checkpoint staging:",
            f"params {PARAMS_CONCURRENT_GB}GB + train_state {TRAIN_STATE_CONCURRENT_GB}GB",
        )
        return 0

    run_name = config_wrapper.validate_run_name(namespace.run_name)
    forwarded = config_wrapper.build_forward_arguments(
        settings,
        run_name=run_name,
        target_step=target_step,
        resume=namespace.resume,
        check_only=namespace.check_only,
    )

    # 기존 train bootstrap이 JAX를 import하기 전에 allocator 상한을 읽도록 한다.
    os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = format(
        settings.runtime.jax_memory_fraction,
        ".12g",
    )
    train_bootstrap = load_local_module(
        TRAIN_BOOTSTRAP_PATH,
        TRAIN_BOOTSTRAP_MODULE_NAME,
    )
    train_bootstrap.configure_process_environment(forwarded)
    train_bootstrap.validate_openpi_import()

    from openpi.training import checkpoints

    checkpoints.initialize_checkpoint_dir = build_memory_limited_initializer()
    print("Run name          :", run_name, flush=True)
    print("Resume            :", namespace.resume, flush=True)
    print(
        "Checkpoint staging:",
        f"params {PARAMS_CONCURRENT_GB}GB + train_state {TRAIN_STATE_CONCURRENT_GB}GB",
        flush=True,
    )

    # Patch된 module 객체를 pi0_training이 import한 뒤 기존 검증된 main을 그대로 쓴다.
    from piper_vla.training.trainer import main as training_main

    return training_main(forwarded, workspace_root=WORKSPACE_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
