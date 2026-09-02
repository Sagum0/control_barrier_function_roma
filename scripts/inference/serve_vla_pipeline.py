#!/usr/bin/env python3
"""기존 vla_pipeline LeRobot 0.6 client용 OpenPI π0 gRPC server를 실행한다."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Sequence


# 이 launcher와 workspace의 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# 공통 checkpoint/runtime 검증을 재사용할 기존 launcher module 경로다.
BASE_LAUNCHER_PATH = WORKSPACE_ROOT / "scripts" / "inference" / "serve_policy.py"

# 기존 vla_pipeline용 기본 설정 파일이다.
DEFAULT_CONFIG_PATH = (
    WORKSPACE_ROOT / "config" / "inference" / "pi0_piper_vla_pipeline.yaml"
)


# workspace 전용 conda Python 실행 파일이다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 시작했으면 이 launcher 자신을 workspace Python으로 교체한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(
            f"workspace Python을 찾지 못했습니다: {expected_python}"
        )
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv()가 예기치 않게 반환했습니다.")


def _load_base_launcher() -> object:
    """기존 launcher의 검증 함수들을 파일 경로로 안전하게 불러온다."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "piper_vla_base_inference_launcher",
        BASE_LAUNCHER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"기존 inference launcher를 읽지 못했습니다: {BASE_LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_argument_parser() -> argparse.ArgumentParser:
    """명시 step과 latest/check-only를 분리한 호환 server parser를 만든다."""

    parser = argparse.ArgumentParser(
        description="기존 vla_pipeline용 LeRobot AsyncInference gRPC π0 server"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--step", type=int, help="사용할 정확한 checkpoint step")
    selection.add_argument(
        "--latest",
        action="store_true",
        help="임시 디렉터리를 제외한 최신 커밋 완료 checkpoint 선택",
    )
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--print-config",
        action="store_true",
        help="설정만 검증하고 JAX/GPU를 건드리지 않고 종료",
    )
    operation.add_argument(
        "--check-only",
        action="store_true",
        help="checkpoint와 내장 norm stats까지만 검증하고 종료",
    )
    operation.add_argument(
        "--print-client-command",
        action="store_true",
        help="같은 YAML 값으로 기존 vla_pipeline client 명령을 출력하고 종료",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """고정 checkpoint를 복원하고 LeRobot 0.6 gRPC 표면으로 제공한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    base = _load_base_launcher()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    base.configure_workspace_source_path()

    from piper_vla.inference.checkpoint import select_checkpoint
    from piper_vla.inference.client_command import build_vla_pipeline_client_command
    from piper_vla.inference.settings import load_pi0_inference_settings

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
    if namespace.step is not None and namespace.step <= 0:
        parser.error(f"--step은 양수여야 합니다: {namespace.step}")

    settings = load_pi0_inference_settings(namespace.config, WORKSPACE_ROOT)
    async_client = settings.async_client
    if async_client is None:
        parser.error("vla_pipeline server config에는 schema 2 async_client가 필요합니다.")
    requested_step: int | str = "latest" if namespace.latest else (
        settings.checkpoint.step if namespace.step is None else namespace.step
    )
    print("Config file        :", settings.config_path)
    print("Run                :", settings.checkpoint.run_name)
    print("Requested step     :", requested_step)
    print("Asset id           :", settings.checkpoint.asset_id)
    print("Prompt             :", settings.policy.prompt)
    print("Inference steps    :", settings.policy.num_inference_steps)
    print("Transport          : LeRobot 0.6 AsyncInference gRPC")
    print("Server             :", f"{settings.server.host}:{settings.server.port}")
    print("JAX memory fraction:", settings.runtime.jax_memory_fraction)
    print("Actions per chunk  :", async_client.actions_per_chunk)
    print("Queue threshold    :", async_client.chunk_size_threshold)
    print("Aggregate function :", async_client.aggregate_fn_name)
    print("Control FPS        :", async_client.fps)
    print("Observation timeout:", async_client.observation_queue_timeout_seconds)
    print("Queue visualization:", async_client.debug_visualize_queue_size)
    if namespace.print_client_command:
        print("\nClient command:")
        print(
            build_vla_pipeline_client_command(
                settings,
                requested_step=requested_step,
            )
        )
        base.assert_lightweight_import_boundary()
        return 0
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
        print("PASS: committed checkpoint and embedded norm stats")
        print("PASS: JAX/OpenPI policy/GPU not initialized")
        return 0

    base.configure_openpi_runtime(settings.runtime.jax_memory_fraction)
    from piper_vla.inference.lerobot_grpc import create_lerobot_grpc_server
    from piper_vla.inference.policy_server import (
        create_piper_policy,
        require_jax_gpu_backend,
    )

    jax_backend = require_jax_gpu_backend()
    print("JAX backend        :", jax_backend)
    print("Loading π0 policy for vla_pipeline gRPC client...", flush=True)
    policy = create_piper_policy(settings, checkpoint)
    server = create_lerobot_grpc_server(policy, settings)
    print(
        "Ready              :",
        f"{server.host}:{server.bound_port} / transport.AsyncInference",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
