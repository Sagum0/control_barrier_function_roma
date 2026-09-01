#!/usr/bin/env python3
"""한국어 주석 YAML을 기존 검증된 Piper π0 학습 CLI로 변환한다."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
from typing import Sequence


# 이 실행 파일이 속한 vla_ws의 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# 학습 dependency가 설치된 workspace 내부 conda Python 경로다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"

# YAML loader가 들어 있는 workspace Python source 경로다.
WORKSPACE_SOURCE_ROOT = WORKSPACE_ROOT / "src"

# 실제 JAX/OpenPI 학습을 담당하는 기존 검증된 실행 파일이다.
TRAIN_PI0_SCRIPT = WORKSPACE_ROOT / "scripts" / "training" / "train.py"

# 인자를 생략했을 때 읽는 한국어 주석 config 경로다.
DEFAULT_CONFIG_PATH = WORKSPACE_ROOT / "config" / "training" / "pi0_piper_lora.yaml"

# checkpoint 경로 탈출을 막기 위한 run 이름 형식이다.
SAFE_RUN_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 시작했으면 workspace conda Python으로 안전하게 교체한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    current_python = Path(sys.executable).resolve()
    if current_python == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(
            "workspace conda Python이 없습니다. environment.yml로 환경을 먼저 생성하세요: "
            f"{expected_python}"
        )
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def configure_python_path() -> None:
    """JAX를 import하지 않고 workspace의 YAML loader만 import할 수 있게 한다."""

    source_text = str(WORKSPACE_SOURCE_ROOT)
    if source_text in sys.path:
        sys.path.remove(source_text)
    sys.path.insert(0, source_text)


def build_argument_parser() -> argparse.ArgumentParser:
    """자동 overwrite가 없고 resume를 명시해야 하는 config wrapper parser를 만든다."""

    parser = argparse.ArgumentParser(
        description=(
            "config/training/pi0_piper_lora.yaml을 검사한 뒤 기존 검증된 scripts/training/train.py를 실행합니다."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="한국어 주석 π0 YAML 경로",
    )
    parser.add_argument(
        "--run-name",
        help="새 실행 또는 기존 resume checkpoint를 식별하는 이름",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="같은 run의 latest checkpoint에서 이어서 학습",
    )
    parser.add_argument(
        "--target-step",
        type=int,
        help="YAML final step 이하에서 임시로 멈출 absolute step",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="CPU에서 실제 sample 한 batch까지만 검사하고 weight/run은 건드리지 않음",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="YAML을 검증하고 resolved 값만 출력한 뒤 종료",
    )
    return parser


def validate_run_name(run_name: str | None) -> str:
    """실제 학습 실행에 필요한 안전한 run 이름을 검증한다."""

    if run_name is None:
        raise ValueError("학습 또는 check-only 실행에는 --run-name을 명시해야 합니다.")
    if run_name in {".", ".."} or SAFE_RUN_NAME_PATTERN.fullmatch(run_name) is None:
        raise ValueError(
            "--run-name은 영문자/숫자로 시작하고 영문자·숫자·._-만 허용합니다: "
            f"{run_name!r}"
        )
    return run_name


def print_resolved_settings(settings: object, *, target_step: int) -> None:
    """GPU나 checkpoint를 건드리지 않고 실제 전달될 설정을 표시한다."""

    print("Config file       :", settings.config_path)
    print("Dataset           :", settings.paths.dataset_root)
    print("Asset id          :", settings.dataset.asset_id)
    print("Assets root       :", settings.paths.assets_base_dir)
    print("Runs root         :", settings.paths.runs_root)
    print("Base params       :", settings.paths.base_params)
    print("Vision encoder    :", settings.finetuning.vision_encoder)
    print("Target step       :", target_step)
    print("Batch / workers   :", settings.training.batch_size, "/", settings.training.num_workers)
    print(
        "Log / save / keep:",
        settings.training.log_interval,
        "/",
        settings.training.save_interval,
        "/",
        settings.training.keep_period,
    )
    print("Seed              :", settings.training.seed)
    print("JAX memory fraction:", settings.runtime.jax_memory_fraction)
    print("Progress refresh  :", settings.runtime.progress_refresh_seconds, "seconds")
    print("YAML locked mirror: PASS")


def build_forward_arguments(
    settings: object,
    *,
    run_name: str,
    target_step: int,
    resume: bool,
    check_only: bool,
) -> list[str]:
    """YAML 값을 기존 scripts/training/train.py가 이미 검증하는 CLI 인자로 변환한다."""

    arguments = [
        "--run-name",
        run_name,
        "--dataset-root",
        str(settings.paths.dataset_root),
        "--asset-id",
        settings.dataset.asset_id,
        "--assets-base-dir",
        str(settings.paths.assets_base_dir),
        "--runs-root",
        str(settings.paths.runs_root),
        "--base-params",
        str(settings.paths.base_params),
        "--vision-encoder",
        settings.finetuning.vision_encoder,
        "--num-train-steps",
        str(target_step),
        "--batch-size",
        str(settings.training.batch_size),
        "--num-workers",
        str(settings.training.num_workers),
        "--log-interval",
        str(settings.training.log_interval),
        "--save-interval",
        str(settings.training.save_interval),
        "--keep-period",
        str(settings.training.keep_period),
        "--seed",
        str(settings.training.seed),
        "--progress-refresh-seconds",
        str(settings.runtime.progress_refresh_seconds),
    ]
    if resume:
        arguments.append("--resume")
    if check_only:
        arguments.append("--check-only")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    """YAML을 strict-load하고 기존 검증된 π0 학습 process로 교체한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    configure_python_path()

    # JAX/OpenPI를 import하지 않는 순수 YAML loader다.
    from piper_vla.training.settings import load_pi0_settings

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
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

    print_resolved_settings(settings, target_step=target_step)
    if namespace.print_config:
        return 0

    run_name = validate_run_name(namespace.run_name)
    forwarded = build_forward_arguments(
        settings,
        run_name=run_name,
        target_step=target_step,
        resume=namespace.resume,
        check_only=namespace.check_only,
    )

    # 기존 scripts/training/train.py가 JAX를 import하기 전에 읽도록 환경 값을 먼저 고정한다.
    os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = format(
        settings.runtime.jax_memory_fraction,
        ".12g",
    )
    print("Run name          :", run_name, flush=True)
    print("Resume            :", namespace.resume, flush=True)
    print("Delegating to     :", TRAIN_PI0_SCRIPT, flush=True)
    os.execv(
        str(WORKSPACE_PYTHON),
        [str(WORKSPACE_PYTHON), str(TRAIN_PI0_SCRIPT), *forwarded],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


if __name__ == "__main__":
    raise SystemExit(main())
