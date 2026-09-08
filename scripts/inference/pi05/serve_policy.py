#!/usr/bin/env python3
"""완료된 Piper π0.5 checkpoint를 OpenPI WebSocket server로 실행한다."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
from typing import Sequence


# 이 launcher가 속한 workspace와 공통 π0 launcher 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"
BASE_LAUNCHER_PATH = WORKSPACE_ROOT / "scripts" / "inference" / "pi0" / "serve_policy.py"
DEFAULT_CONFIG_PATH = (
    WORKSPACE_ROOT / "config" / "inference" / "pi05" / "piper_inference.yaml"
)


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python이면 π0.5 launcher를 workspace Python으로 다시 실행한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"workspace conda Python이 없습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def _load_base_launcher() -> object:
    """π0와 공통인 repository/runtime 검증 함수를 불러온다."""

    spec = importlib.util.spec_from_file_location(
        "piper_vla_pi05_base_launcher",
        BASE_LAUNCHER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"공통 inference launcher를 읽지 못했습니다: {BASE_LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_argument_parser() -> argparse.ArgumentParser:
    """명시 step과 opt-in latest를 분리한 π0.5 server parser를 만든다."""

    parser = argparse.ArgumentParser(
        description="완료된 Piper π0.5 Orbax checkpoint를 WebSocket으로 제공합니다."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--step", type=int, help="사용할 정확한 checkpoint step")
    selection.add_argument("--latest", action="store_true", help="최신 커밋 checkpoint 선택")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--print-config", action="store_true")
    operation.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """설정·checkpoint를 먼저 검사하고 serve에서만 π0.5 policy를 복원한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    base = _load_base_launcher()
    base.configure_workspace_source_path()

    from piper_vla.inference.pi05.checkpoint import select_checkpoint
    from piper_vla.inference.pi05.settings import load_pi05_inference_settings

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
    if namespace.step is not None and namespace.step <= 0:
        parser.error(f"--step은 양수여야 합니다: {namespace.step}")

    settings = load_pi05_inference_settings(namespace.config, WORKSPACE_ROOT)
    requested_step: int | str = "latest" if namespace.latest else (
        settings.checkpoint.step if namespace.step is None else namespace.step
    )
    base.print_settings(settings, selected_step=requested_step)
    if namespace.print_config:
        base.assert_lightweight_import_boundary()
        return 0

    checkpoint = select_checkpoint(
        settings,
        step_override=namespace.step,
        latest=namespace.latest,
    )
    print("Checkpoint         :", checkpoint.step_dir)
    print("Norm stats SHA256  :", checkpoint.norm_stats_sha256)
    if namespace.check_only:
        base.assert_lightweight_import_boundary()
        print("PASS: committed π0.5 checkpoint and embedded quantile stats")
        print("PASS: JAX/OpenPI policy/GPU not initialized")
        return 0

    base.configure_openpi_runtime(settings.runtime.jax_memory_fraction)
    from piper_vla.inference.pi05.policy_server import (
        require_jax_gpu_backend,
        serve_piper_policy,
    )

    print("JAX backend        :", require_jax_gpu_backend())
    print("Health check       :", f"http://{settings.server.host}:{settings.server.port}/healthz")
    print("Loading π0.5 policy and starting WebSocket server...", flush=True)
    serve_piper_policy(settings, checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
