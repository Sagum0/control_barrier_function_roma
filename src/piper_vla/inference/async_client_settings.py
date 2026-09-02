"""LeRobot async client 설정값을 부작용 없이 엄격하게 검증한다."""

from __future__ import annotations

import math
from typing import Any


def _require_integer(value: Any, *, field_name: str) -> int:
    """bool과 float를 허용하지 않는 정확한 정수를 반환한다."""

    if type(value) is not int:
        raise TypeError(f"{field_name}은 정수여야 합니다: {value!r}")
    return value


def _require_real(value: Any, *, field_name: str) -> float:
    """bool을 제외한 유한한 실수를 반환한다."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name}은 실수여야 합니다: {value!r}")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field_name}은 유한해야 합니다: {value!r}")
    return converted


def validate_async_client_values(
    raw: dict[str, Any],
    *,
    action_horizon: int,
    aggregate_functions: frozenset[str],
) -> dict[str, Any]:
    """strict-load된 async_client mapping을 dataclass 생성용 값으로 바꾼다."""

    episode_time_raw = raw["episode_time_seconds"]
    episode_time_seconds: float | None
    if episode_time_raw is None:
        episode_time_seconds = None
    else:
        episode_time_seconds = _require_real(
            episode_time_raw,
            field_name="async_client.episode_time_seconds",
        )
        if episode_time_seconds <= 0.0:
            raise ValueError(
                "async_client.episode_time_seconds는 양수 또는 null이어야 합니다: "
                f"{episode_time_seconds}"
            )

    actions_per_chunk = _require_integer(
        raw["actions_per_chunk"],
        field_name="async_client.actions_per_chunk",
    )
    if not 1 <= actions_per_chunk <= action_horizon:
        raise ValueError(
            "async_client.actions_per_chunk 범위가 잘못됐습니다: "
            f"{actions_per_chunk}; 허용=1~{action_horizon}"
        )

    chunk_size_threshold = _require_real(
        raw["chunk_size_threshold"],
        field_name="async_client.chunk_size_threshold",
    )
    if not 0.0 <= chunk_size_threshold <= 1.0:
        raise ValueError(
            "async_client.chunk_size_threshold는 0.0~1.0이어야 합니다: "
            f"{chunk_size_threshold}"
        )

    aggregate_fn_name = raw["aggregate_fn_name"]
    if not isinstance(aggregate_fn_name, str) or not aggregate_fn_name.strip():
        raise TypeError(
            "async_client.aggregate_fn_name은 비어 있지 않은 문자열이어야 합니다."
        )
    aggregate_fn_name = aggregate_fn_name.strip()
    if aggregate_fn_name not in aggregate_functions:
        raise ValueError(
            "async_client.aggregate_fn_name이 올바르지 않습니다: "
            f"actual={aggregate_fn_name!r}, allowed={sorted(aggregate_functions)}"
        )

    fps = _require_integer(raw["fps"], field_name="async_client.fps")
    if not 1 <= fps <= 100:
        raise ValueError(f"async_client.fps는 1~100이어야 합니다: {fps}")

    queue_timeout = _require_real(
        raw["observation_queue_timeout_seconds"],
        field_name="async_client.observation_queue_timeout_seconds",
    )
    if not 0.1 <= queue_timeout <= 60.0:
        raise ValueError(
            "async_client.observation_queue_timeout_seconds는 0.1~60.0초여야 합니다: "
            f"{queue_timeout}"
        )

    debug_queue = raw["debug_visualize_queue_size"]
    if type(debug_queue) is not bool:
        raise TypeError(
            "async_client.debug_visualize_queue_size는 bool이어야 합니다: "
            f"{debug_queue!r}"
        )

    return {
        "episode_time_seconds": episode_time_seconds,
        "actions_per_chunk": actions_per_chunk,
        "chunk_size_threshold": chunk_size_threshold,
        "aggregate_fn_name": aggregate_fn_name,
        "fps": fps,
        "observation_queue_timeout_seconds": queue_timeout,
        "debug_visualize_queue_size": debug_queue,
    }
