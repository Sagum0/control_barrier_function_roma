"""Piper LeRobot v3 전체에서 π0용 정규화 통계를 계산하고 안전하게 저장한다."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
import time
from typing import Callable

import numpy as np

from openpi.shared import normalize

from piper_vla.training.dataset_v3 import PIPER_DIM, PiperV3Dataset


# 노트북에서 검증한 frame 단위 통계 계산 batch 크기다.
DEFAULT_STATS_BATCH_FRAMES = 4096

# Absolute action을 delta로 바꾸는 Piper 관절 축의 개수다.
PI0_DELTA_JOINT_DIM = 6

# π0 normalization asset에 정확히 필요한 두 통계 key다.
PI0_NORM_STATS_KEYS = frozenset({"state", "actions"})

# 진행률 callback이 받는 값은 완료 frame 수와 전체 frame 수다.
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class Pi0NormStatsResult:
    """전체 데이터 통계와 실제로 누적한 벡터 수·시간을 묶는다."""

    # OpenPI가 저장하고 학습 때 읽는 state/action 통계다.
    stats: dict[str, normalize.NormStats]

    # 통계에 포함한 7D state 벡터 수다.
    state_vector_count: int

    # 통계에 포함한 7D future action 벡터 수다.
    action_vector_count: int

    # Dataset 준비가 끝난 뒤 통계 누적에 걸린 시간이다.
    elapsed_seconds: float


def compute_pi0_norm_stats(
    dataset: PiperV3Dataset,
    *,
    progress_callback: ProgressCallback | None = None,
) -> Pi0NormStatsResult:
    """고정 batch 순서로 전체 state와 6축 delta·gripper absolute action 통계를 계산한다."""

    if dataset.action_horizon <= 0:
        raise ValueError(f"action_horizon은 양수여야 합니다: {dataset.action_horizon}")

    state_running = normalize.RunningStats()
    action_running = normalize.RunningStats()
    state_vector_count = 0
    action_vector_count = 0
    total_frames = len(dataset)
    started_at = time.perf_counter()

    for begin in range(0, total_frames, DEFAULT_STATS_BATCH_FRAMES):
        end = min(begin + DEFAULT_STATS_BATCH_FRAMES, total_frames)
        states, absolute_action_chunks = dataset.numeric_batch(begin, end)

        delta_action_chunks = absolute_action_chunks.copy()
        delta_action_chunks[..., :PI0_DELTA_JOINT_DIM] -= states[
            :, None, :PI0_DELTA_JOINT_DIM
        ]

        state_running.update(states)
        action_running.update(delta_action_chunks)

        current_frames = end - begin
        state_vector_count += current_frames
        action_vector_count += current_frames * dataset.action_horizon

        if progress_callback is not None:
            progress_callback(end, total_frames)

    result = Pi0NormStatsResult(
        stats={
            "state": state_running.get_statistics(),
            "actions": action_running.get_statistics(),
        },
        state_vector_count=state_vector_count,
        action_vector_count=action_vector_count,
        elapsed_seconds=time.perf_counter() - started_at,
    )
    validate_pi0_norm_stats(result.stats, expected_dim=PIPER_DIM)

    if result.state_vector_count != total_frames:
        raise AssertionError(
            "state 통계 벡터 수가 전체 frame 수와 다릅니다: "
            f"count={result.state_vector_count}, frames={total_frames}"
        )
    expected_action_count = total_frames * dataset.action_horizon
    if result.action_vector_count != expected_action_count:
        raise AssertionError(
            "action 통계 벡터 수가 예상값과 다릅니다: "
            f"count={result.action_vector_count}, expected={expected_action_count}"
        )

    return result


def validate_pi0_norm_stats(
    stats: dict[str, normalize.NormStats],
    *,
    expected_dim: int = PIPER_DIM,
) -> None:
    """통계 key·shape·유한값·분위수 순서가 π0 Piper 계약과 같은지 확인한다."""

    if set(stats) != PI0_NORM_STATS_KEYS:
        raise ValueError(
            "정규화 통계 key가 올바르지 않습니다: "
            f"expected={sorted(PI0_NORM_STATS_KEYS)}, actual={sorted(stats)}"
        )

    for stats_key in sorted(PI0_NORM_STATS_KEYS):
        norm_stats = stats[stats_key]
        for field_name in ("mean", "std", "q01", "q99"):
            value = getattr(norm_stats, field_name)
            if value is None:
                raise ValueError(f"정규화 통계가 비어 있습니다: {stats_key}.{field_name}")
            array = np.asarray(value)
            if array.shape != (expected_dim,):
                raise ValueError(
                    "정규화 통계 shape이 올바르지 않습니다: "
                    f"{stats_key}.{field_name}={array.shape}, expected={(expected_dim,)}"
                )
            if not np.isfinite(array).all():
                raise ValueError(f"정규화 통계에 NaN 또는 Inf가 있습니다: {stats_key}.{field_name}")

        if np.any(np.asarray(norm_stats.std) <= 0.0):
            raise ValueError(f"표준편차가 0 이하입니다: {stats_key}.std")
        if np.any(np.asarray(norm_stats.q01) > np.asarray(norm_stats.q99)):
            raise ValueError(f"q01이 q99보다 큽니다: {stats_key}")


def assert_pi0_norm_stats_equal(
    expected: dict[str, normalize.NormStats],
    actual: dict[str, normalize.NormStats],
) -> None:
    """저장 전후의 모든 통계 배열이 수치 허용오차 안에서 같은지 확인한다."""

    validate_pi0_norm_stats(expected)
    validate_pi0_norm_stats(actual)

    for stats_key in sorted(PI0_NORM_STATS_KEYS):
        for field_name in ("mean", "std", "q01", "q99"):
            np.testing.assert_allclose(
                np.asarray(getattr(actual[stats_key], field_name)),
                np.asarray(getattr(expected[stats_key], field_name)),
                rtol=1e-12,
                atol=1e-12,
                err_msg=f"정규화 통계 불일치: {stats_key}.{field_name}",
            )


def install_pi0_norm_stats(
    output_directory: Path,
    stats: dict[str, normalize.NormStats],
) -> bool:
    """완성된 JSON을 원자적으로 신규 설치하고 기존 파일은 절대 덮어쓰지 않는다."""

    validate_pi0_norm_stats(stats)
    output_directory = Path(output_directory).resolve()
    output_path = output_directory / "norm_stats.json"

    if output_path.exists():
        existing = normalize.load(output_directory)
        try:
            assert_pi0_norm_stats_equal(stats, existing)
        except AssertionError as error:
            raise RuntimeError(
                "기존 norm_stats.json이 현재 데이터 계산 결과와 다릅니다. "
                "자동으로 덮어쓰지 않습니다: "
                f"{output_path}"
            ) from error
        return False

    output_directory.mkdir(parents=True, exist_ok=True)
    serialized = normalize.serialize_json(stats)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_directory,
            prefix=".norm_stats.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())

        try:
            os.link(temporary_path, output_path)
        except FileExistsError:
            existing = normalize.load(output_directory)
            try:
                assert_pi0_norm_stats_equal(stats, existing)
            except AssertionError as error:
                raise RuntimeError(
                    "동시에 생성된 norm_stats.json이 현재 계산 결과와 다릅니다. "
                    "자동으로 덮어쓰지 않습니다: "
                    f"{output_path}"
                ) from error
            return False

        directory_descriptor = os.open(output_directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    reloaded = normalize.load(output_directory)
    assert_pi0_norm_stats_equal(stats, reloaded)
    return True
