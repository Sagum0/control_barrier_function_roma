"""서버 YAML에서 기존 vla_pipeline async client 명령을 만든다."""

from __future__ import annotations

import shlex
from typing import Any


# client PC에서 그대로 접속 주소로 사용할 수 없는 server bind 주소다.
NON_ROUTABLE_SERVER_HOSTS = frozenset(
    {"127.0.0.1", "localhost", "0.0.0.0", "::", "::1"}
)


def _shell_option(name: str, value: object) -> str:
    """한 CLI option을 shell-safe한 `--name=value` 형식으로 만든다."""

    return f"--{name}={shlex.quote(str(value))}"


def build_vla_pipeline_client_command(
    settings: Any,
    *,
    requested_step: int | str,
) -> str:
    """같은 YAML 값으로 기존 Piper async client 실행 명령을 만든다."""

    async_client = getattr(settings, "async_client", None)
    if async_client is None:
        raise ValueError(
            "client 명령 생성에는 async_client 설정이 필요합니다."
        )

    server_host = str(settings.server.host)
    if server_host in NON_ROUTABLE_SERVER_HOSTS:
        server_host = "GPU_SERVER_IP"
    server_address = f"{server_host}:{settings.server.port}"
    checkpoint_label = f"{settings.checkpoint.run_name}/{requested_step}"
    debug_queue = str(async_client.debug_visualize_queue_size).lower()
    episode_time = async_client.episode_time_seconds
    episode_time_environment = (
        "PIPER_EPISODE_TIME_S="
        if episode_time is None
        else f"PIPER_EPISODE_TIME_S={episode_time:g}"
    )

    options = [
        f"{episode_time_environment} PYTHONPATH=/path/to/vla_pipeline "
        "python -m piper_bridge.async_client",
        _shell_option("server_address", server_address),
        "--robot.type=piper_bridge",
        "--policy_type=pi0",
        _shell_option("pretrained_name_or_path", checkpoint_label),
        _shell_option("task", settings.policy.prompt),
        "--policy_device=cuda",
        "--client_device=cpu",
        _shell_option("actions_per_chunk", async_client.actions_per_chunk),
        _shell_option("chunk_size_threshold", async_client.chunk_size_threshold),
        _shell_option("aggregate_fn_name", async_client.aggregate_fn_name),
        _shell_option("fps", async_client.fps),
        _shell_option("debug_visualize_queue_size", debug_queue),
    ]
    return " \\\n  ".join(options)
