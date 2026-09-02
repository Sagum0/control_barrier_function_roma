#!/usr/bin/env python3
"""YAML 하나로 기존 Piper 동기·비동기 client를 선택해 실행한다."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import sys
from typing import Mapping, Sequence


# 이 launcher가 속한 vla_ws와 공통 설정 파일이다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_SOURCE_ROOT = WORKSPACE_ROOT / "src"
DEFAULT_CONFIG_PATH = (
    WORKSPACE_ROOT / "config" / "inference" / "pi0_piper_vla_pipeline.yaml"
)

# robot/ROS bridge와 비동기 client는 vla_pipeline의 검증된 구현을 재사용한다.
VLA_PIPELINE_ROOT = Path("/home/pc/vla_pipeline")
CLIENT_PYTHON = Path("/home/pc/miniconda3/envs/lerobot-060/bin/python")


def ensure_client_python(arguments: Sequence[str]) -> None:
    """lerobot-060이 아니면 같은 launcher를 해당 Python으로 다시 시작한다."""

    expected_python = CLIENT_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"lerobot-060 Python을 찾지 못했습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv()가 예기치 않게 반환했습니다.")


def configure_import_paths() -> None:
    """vla_ws 설정 코드와 기존 piper_bridge를 import할 수 있게 한다."""

    for path in (WORKSPACE_SOURCE_ROOT, VLA_PIPELINE_ROOT):
        resolved = str(path.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def build_argument_parser() -> argparse.ArgumentParser:
    """YAML 기본값과 일회성 checkpoint override만 받는 parser를 만든다."""

    parser = argparse.ArgumentParser(
        description="vla_ws YAML 기반 Piper sync/async client"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--step", type=int, help="YAML 대신 사용할 checkpoint step")
    selection.add_argument(
        "--latest",
        action="store_true",
        help="최신 커밋 완료 checkpoint를 선택",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="검증된 실제 client 명령과 환경변수만 출력하고 종료",
    )
    return parser


def _server_address(host: str, port: int) -> str:
    """같은 PC에서 wildcard bind 주소로 접속 가능한 gRPC 주소를 만든다."""

    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}"


def build_client_arguments(settings: object, *, checkpoint_step: int) -> list[str]:
    """YAML mode에 맞는 동기 또는 비동기 client argument를 만든다."""

    client = getattr(settings, "client", None)
    if client is None:
        raise ValueError("vla_pipeline client config에는 client 설정이 필요합니다.")
    checkpoint = getattr(settings, "checkpoint")
    policy = getattr(settings, "policy")
    server = getattr(settings, "server")
    server_address = _server_address(server.host, server.port)
    checkpoint_label = f"{checkpoint.run_name}/{checkpoint_step}"
    if client.mode == "async":
        async_options = client.async_options
        return [
            str(CLIENT_PYTHON),
            "-m",
            "piper_bridge.async_client",
            f"--server_address={server_address}",
            "--robot.type=piper_bridge",
            "--policy_type=pi0",
            f"--pretrained_name_or_path={checkpoint_label}",
            f"--task={policy.prompt}",
            "--policy_device=cuda",
            "--client_device=cpu",
            f"--actions_per_chunk={client.actions_per_chunk}",
            f"--chunk_size_threshold={async_options.chunk_size_threshold}",
            f"--aggregate_fn_name={async_options.aggregate_fn_name}",
            f"--fps={client.fps}",
            "--debug_visualize_queue_size="
            f"{str(async_options.debug_visualize_queue_size).lower()}",
        ]
    if client.mode != "sync":
        raise ValueError(f"지원하지 않는 client mode입니다: {client.mode!r}")

    arguments = [
        str(CLIENT_PYTHON),
        "-m",
        "piper_vla.inference.sync_client",
        f"--server-address={server_address}",
        f"--checkpoint-label={checkpoint_label}",
        f"--task={policy.prompt}",
        f"--actions-per-chunk={client.actions_per_chunk}",
        f"--fps={client.fps}",
    ]
    if client.episode_time_seconds is not None:
        arguments.append(f"--episode-time-seconds={client.episode_time_seconds:g}")
    return arguments


def build_client_environment(
    settings: object,
    current_environment: Mapping[str, str],
) -> dict[str, str]:
    """YAML의 episode 제한과 두 workspace 경로를 client 환경으로 고정한다."""

    client = getattr(settings, "client", None)
    if client is None:
        raise ValueError("vla_pipeline client config에는 client 설정이 필요합니다.")

    environment = dict(current_environment)
    episode_time = client.episode_time_seconds
    environment["PIPER_EPISODE_TIME_S"] = (
        "" if client.mode == "sync" or episode_time is None else f"{episode_time:g}"
    )

    import_paths = [str(VLA_PIPELINE_ROOT.resolve()), str(WORKSPACE_SOURCE_ROOT.resolve())]
    inherited_pythonpath = environment.get("PYTHONPATH")
    if inherited_pythonpath:
        import_paths.append(inherited_pythonpath)
    environment["PYTHONPATH"] = os.pathsep.join(import_paths)

    client_library_path = str(CLIENT_PYTHON.resolve().parents[1] / "lib")
    inherited_library_path = environment.get("LD_LIBRARY_PATH")
    environment["LD_LIBRARY_PATH"] = (
        client_library_path
        if not inherited_library_path
        else os.pathsep.join((client_library_path, inherited_library_path))
    )
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def _print_resolved_configuration(
    settings: object,
    *,
    checkpoint: object,
    environment: Mapping[str, str],
    arguments: Sequence[str],
) -> None:
    """실제 실행 직전 YAML 해석 결과를 사람이 확인할 수 있게 출력한다."""

    client = getattr(settings, "client")
    print("Config file        :", getattr(settings, "config_path"))
    print("Checkpoint         :", getattr(checkpoint, "step_dir"))
    print("Execution mode     :", client.mode)
    print("Server             :", arguments[3].split("=", 1)[1])
    print("Prompt             :", getattr(settings, "policy").prompt)
    print(
        "Episode time       :",
        "unlimited"
        if client.episode_time_seconds is None
        else f"{client.episode_time_seconds:g}s",
    )
    print("Control FPS        :", client.fps)
    print("Actions per chunk  :", client.actions_per_chunk)
    if client.mode == "async":
        print("Queue threshold    :", client.async_options.chunk_size_threshold)
        print("Aggregate function :", client.async_options.aggregate_fn_name)
        print("PIPER_EPISODE_TIME_S:", repr(environment["PIPER_EPISODE_TIME_S"]))
    else:
        print("Async options      : ignored")
    print("Client command     :", shlex.join(arguments), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    """checkpoint를 검증한 뒤 YAML mode에 맞는 client process로 교체한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_client_python(arguments)
    configure_import_paths()

    from piper_vla.inference.checkpoint import select_checkpoint
    from piper_vla.inference.settings import load_pi0_inference_settings

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
    if namespace.step is not None and namespace.step <= 0:
        parser.error(f"--step은 양수여야 합니다: {namespace.step}")
    if not VLA_PIPELINE_ROOT.is_dir():
        parser.error(f"기존 vla_pipeline을 찾지 못했습니다: {VLA_PIPELINE_ROOT}")

    settings = load_pi0_inference_settings(namespace.config, WORKSPACE_ROOT)
    if settings.client is None:
        parser.error("vla_pipeline client config에는 client 설정이 필요합니다.")
    if settings.client.mode == "async" and not (
        VLA_PIPELINE_ROOT / "piper_bridge" / "async_client.py"
    ).is_file():
        parser.error("기존 piper_bridge.async_client를 찾지 못했습니다.")
    checkpoint = select_checkpoint(
        settings,
        step_override=namespace.step,
        latest=namespace.latest,
    )
    client_arguments = build_client_arguments(settings, checkpoint_step=checkpoint.step)
    environment = build_client_environment(settings, os.environ)
    _print_resolved_configuration(
        settings,
        checkpoint=checkpoint,
        environment=environment,
        arguments=client_arguments,
    )
    if namespace.print_command:
        return 0

    os.execve(str(CLIENT_PYTHON), client_arguments, environment)
    raise AssertionError("os.execve()가 예기치 않게 반환했습니다.")


if __name__ == "__main__":
    raise SystemExit(main())
