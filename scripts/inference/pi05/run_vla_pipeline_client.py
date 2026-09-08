#!/usr/bin/env python3
"""기존 공통 launcher를 π0.5 설정과 policy type으로 실행한다."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from typing import Sequence


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
CLIENT_PYTHON = Path("/home/pc/miniconda3/envs/lerobot-060/bin/python")
BASE_CLIENT_PATH = (
    WORKSPACE_ROOT / "scripts" / "inference" / "pi0" / "run_vla_pipeline_client.py"
)
DEFAULT_CONFIG_PATH = (
    WORKSPACE_ROOT / "config" / "inference" / "pi05" / "piper_vla_pipeline.yaml"
)


def ensure_client_python(arguments: Sequence[str]) -> None:
    """다른 Python이면 π0.5 launcher를 robot client Python으로 다시 실행한다."""

    expected_python = CLIENT_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"lerobot-060 Python을 찾지 못했습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def _load_common_client() -> object:
    """검증된 π0 client launcher 구현을 모델 중립 공통 코드로 불러온다."""

    spec = importlib.util.spec_from_file_location("piper_vla_common_client_launcher", BASE_CLIENT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"공통 client launcher를 읽지 못했습니다: {BASE_CLIENT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: Sequence[str] | None = None) -> int:
    """π0.5 YAML과 checkpoint를 선택해 기존 sync/async client를 실행한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_client_python(arguments)
    client = _load_common_client()
    client.DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_PATH
    client.POLICY_TYPE = "pi05"
    return client.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
