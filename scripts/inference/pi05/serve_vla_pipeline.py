#!/usr/bin/env python3
"""기존 vla_pipeline client용 OpenPI π0.5 gRPC server를 실행한다."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
from pathlib import Path
import sys
from typing import Sequence


# π0.5 WebSocket launcher의 공통 검증 함수와 기본 설정을 재사용한다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"
BASE_LAUNCHER_PATH = WORKSPACE_ROOT / "scripts" / "inference" / "pi05" / "serve_policy.py"
DEFAULT_CONFIG_PATH = (
    WORKSPACE_ROOT / "config" / "inference" / "pi05" / "piper_vla_pipeline.yaml"
)


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python이면 이 π0.5 launcher를 workspace Python으로 다시 실행한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"workspace Python을 찾지 못했습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def _load_base_launcher() -> object:
    """π0.5 WebSocket launcher의 lightweight 검증 함수를 불러온다."""

    spec = importlib.util.spec_from_file_location(
        "piper_vla_pi05_policy_launcher",
        BASE_LAUNCHER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"π0.5 launcher를 읽지 못했습니다: {BASE_LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_argument_parser() -> argparse.ArgumentParser:
    """π0.5 vla_pipeline server의 checkpoint와 동작 parser를 만든다."""

    parser = argparse.ArgumentParser(description="LeRobot AsyncInference gRPC π0.5 server")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--step", type=int)
    selection.add_argument("--latest", action="store_true")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--print-config", action="store_true")
    operation.add_argument("--check-only", action="store_true")
    operation.add_argument("--print-client-command", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """π0.5 policy를 기존 vla_pipeline gRPC 표면으로 제공한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    base = _load_base_launcher()
    policy_base = base._load_base_launcher()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    policy_base.configure_workspace_source_path()

    from piper_vla.inference.pi05.checkpoint import select_checkpoint
    from piper_vla.inference.pi05.settings import load_pi05_inference_settings
    from piper_vla.inference.transports.vla_pipeline.client_command import build_vla_pipeline_client_command

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
    if namespace.step is not None and namespace.step <= 0:
        parser.error(f"--step은 양수여야 합니다: {namespace.step}")
    settings = load_pi05_inference_settings(namespace.config, WORKSPACE_ROOT)
    client = settings.client
    if client is None:
        parser.error("vla_pipeline server config에는 client 설정이 필요합니다.")
    requested_step: int | str = "latest" if namespace.latest else (
        settings.checkpoint.step if namespace.step is None else namespace.step
    )
    policy_base.print_settings(settings, selected_step=requested_step)
    print("Transport          : LeRobot 0.6 AsyncInference gRPC")
    print("Execution mode     :", client.mode)
    print("Actions per chunk  :", client.actions_per_chunk)
    print("Control FPS        :", client.fps)

    if namespace.print_client_command:
        if client.mode == "async":
            print(build_vla_pipeline_client_command(
                settings,
                requested_step=requested_step,
                policy_type="pi05",
            ))
        else:
            print(
                "./scripts/inference/pi05/run_vla_pipeline_client.py "
                f"--config {settings.config_path} --print-command"
            )
        policy_base.assert_lightweight_import_boundary()
        return 0
    if namespace.print_config:
        policy_base.assert_lightweight_import_boundary()
        return 0

    checkpoint = select_checkpoint(settings, step_override=namespace.step, latest=namespace.latest)
    print("Checkpoint         :", checkpoint.step_dir)
    print("Norm stats SHA256  :", checkpoint.norm_stats_sha256)
    if namespace.check_only:
        policy_base.assert_lightweight_import_boundary()
        print("PASS: committed π0.5 checkpoint and embedded quantile stats")
        print("PASS: JAX/OpenPI policy/GPU not initialized")
        return 0

    policy_base.configure_openpi_runtime(settings.runtime.jax_memory_fraction)
    from piper_vla.inference.pi05.policy_server import create_piper_policy, require_jax_gpu_backend
    from piper_vla.inference.transports.vla_pipeline.lerobot_grpc import create_lerobot_grpc_server

    print("JAX backend        :", require_jax_gpu_backend())
    print("Loading π0.5 policy for vla_pipeline gRPC client...", flush=True)
    policy = create_piper_policy(settings, checkpoint)
    server = create_lerobot_grpc_server(policy, settings, policy_type="pi05")
    print("Ready              :", f"{server.host}:{server.bound_port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
