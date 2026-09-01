#!/usr/bin/env python3
"""YAML이 가리키는 Piper dataset 전체에서 π0 normalization asset을 만든다."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence


# 이 실행 파일이 속한 workspace의 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# Dependency가 설치된 workspace 전용 conda Python 경로다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"

# Piper package를 import할 workspace source 경로다.
WORKSPACE_SOURCE_ROOT = WORKSPACE_ROOT / "src"

# 고정 OpenPI normalize 구현을 import할 source 경로다.
OPENPI_SOURCE_ROOT = WORKSPACE_ROOT / "third_party" / "openpi" / "src"

# 인자를 생략했을 때 읽는 π0 Piper YAML 경로다.
DEFAULT_CONFIG_PATH = WORKSPACE_ROOT / "config" / "training" / "pi0_piper_lora.yaml"

# 학습 코드가 norm_stats를 찾는 고정 asset namespace다.
PI0_ASSET_NAMESPACE = "pi0_piper_lora"


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 시작했으면 workspace conda Python으로 process를 교체한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    current_python = Path(sys.executable).resolve()
    if current_python == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"workspace conda Python이 없습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def configure_import_paths() -> None:
    """Workspace Piper 코드와 고정 OpenPI 코드를 우선 import하도록 경로를 설정한다."""

    for source_root in (OPENPI_SOURCE_ROOT, WORKSPACE_SOURCE_ROOT):
        source_text = str(source_root)
        if source_text in sys.path:
            sys.path.remove(source_text)
        sys.path.insert(0, source_text)


def build_argument_parser() -> argparse.ArgumentParser:
    """기존 asset 덮어쓰기 옵션이 없는 안전한 통계 생성 parser를 만든다."""

    parser = argparse.ArgumentParser(
        description=(
            "YAML의 LeRobot v3 dataset 전체를 읽어 π0용 state/action norm_stats를 만듭니다. "
            "영상과 GPU는 사용하지 않으며 기존 파일은 덮어쓰지 않습니다."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="dataset_root와 asset_id를 읽을 π0 Piper YAML 경로",
    )
    return parser


def print_statistics(result: object, feature_names: tuple[str, ...]) -> None:
    """계산된 state/action 평균·표준편차와 action 분위수를 축별로 표시한다."""

    state_stats = result.stats["state"]
    action_stats = result.stats["actions"]
    print()
    print(
        f"{'feature':<14}"
        f"{'state mean':>13}"
        f"{'state std':>13}"
        f"{'action mean':>14}"
        f"{'action std':>13}"
        f"{'action q01':>13}"
        f"{'action q99':>13}"
    )
    for feature_index, feature_name in enumerate(feature_names):
        print(
            f"{feature_name:<14}"
            f"{state_stats.mean[feature_index]:>13.6f}"
            f"{state_stats.std[feature_index]:>13.6f}"
            f"{action_stats.mean[feature_index]:>14.6f}"
            f"{action_stats.std[feature_index]:>13.6f}"
            f"{action_stats.q01[feature_index]:>13.6f}"
            f"{action_stats.q99[feature_index]:>13.6f}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """설정을 검증하고 전체 숫자 데이터 통계를 계산·저장·재로드 검증한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    configure_import_paths()

    # 이 명령은 Parquet 숫자만 처리하므로 accelerator가 보이지 않게 고정한다.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["JAX_PLATFORMS"] = "cpu"

    from tqdm import tqdm

    from piper_vla.training.dataset_v3 import PiperV3Dataset, STATE_NAMES
    from piper_vla.training.norm_stats import (
        DEFAULT_STATS_BATCH_FRAMES,
        compute_pi0_norm_stats,
        install_pi0_norm_stats,
    )
    from piper_vla.training.settings import LOCKED_MODEL_CONTRACT, load_pi0_settings

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
    settings = load_pi0_settings(namespace.config, WORKSPACE_ROOT)

    action_horizon = int(LOCKED_MODEL_CONTRACT["action_horizon"])
    dataset = PiperV3Dataset(
        root=settings.paths.dataset_root,
        action_horizon=action_horizon,
        validate_samples=False,
    )
    output_directory = (
        settings.paths.assets_base_dir
        / PI0_ASSET_NAMESPACE
        / settings.dataset.asset_id
    ).resolve()

    print("Dataset          :", settings.paths.dataset_root)
    print("Episodes         :", f"{dataset.num_episodes:,}")
    print("Frames           :", f"{len(dataset):,}")
    print("Action horizon   :", action_horizon)
    print("Stats batch      :", DEFAULT_STATS_BATCH_FRAMES, "frames (reproducibility fixed)")
    print("Output           :", output_directory / "norm_stats.json")
    print("GPU / video      : disabled / not decoded")

    with tqdm(
        total=len(dataset),
        desc="π0 norm stats",
        unit="frame",
        mininterval=0.5,
    ) as progress:

        def update_progress(completed_frames: int, total_frames: int) -> None:
            """완료 frame 수에 맞춰 CPU 통계 진행 표시를 앞으로 이동한다."""

            if total_frames != len(dataset):
                raise AssertionError(
                    f"진행률 전체 frame 수가 다릅니다: {total_frames} != {len(dataset)}"
                )
            progress.update(completed_frames - int(progress.n))

        result = compute_pi0_norm_stats(
            dataset,
            progress_callback=update_progress,
        )

    saved_now = install_pi0_norm_stats(output_directory, result.stats)
    print_statistics(result, STATE_NAMES)
    print()
    print("State vectors    :", f"{result.state_vector_count:,}")
    print("Action vectors   :", f"{result.action_vector_count:,}")
    print("Compute time     :", f"{result.elapsed_seconds:.2f} seconds")
    print("Asset status     :", "saved" if saved_now else "existing identical asset reused")
    print("PASS: π0 normalization asset is durable and reload-equivalent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
