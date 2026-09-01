#!/usr/bin/env python3
"""워크스페이스의 OpenPI와 Piper π0 학습 CLI를 연결한다."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Sequence


# 이 실행 파일이 속한 vla_ws의 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# 학습 dependency가 설치된 workspace 내부 conda Python 경로다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"

# Git submodule로 고정한 공식 OpenPI 소스의 루트 경로다.
OPENPI_ROOT = WORKSPACE_ROOT / "third_party" / "openpi"

# 현재 학습 코드가 검증된 OpenPI submodule commit이다.
EXPECTED_OPENPI_COMMIT = "215abfb217dbac7d5f1273282331b9b1866c0479"

# OpenPI Python 패키지가 들어 있는 소스 경로다.
OPENPI_SOURCE_ROOT = OPENPI_ROOT / "src"

# Piper 학습 패키지가 들어 있는 워크스페이스 소스 경로다.
WORKSPACE_SOURCE_ROOT = WORKSPACE_ROOT / "src"

# OpenPI가 모델과 tokenizer 자산을 저장할 워크스페이스 내부 캐시 경로다.
DEFAULT_OPENPI_DATA_HOME = WORKSPACE_ROOT / "data" / "cache" / "openpi"

# Hugging Face가 내려받은 파일을 저장할 워크스페이스 내부 캐시 경로다.
DEFAULT_HUGGINGFACE_HOME = WORKSPACE_ROOT / "data" / "cache" / "huggingface"

# JAX가 컴파일 결과를 재사용할 워크스페이스 내부 캐시 경로다.
DEFAULT_JAX_CACHE_DIR = WORKSPACE_ROOT / "data" / "cache" / "jax"

# RTX 6000 Ada에서 실제 학습에 예약할 기본 JAX 메모리 비율이다.
DEFAULT_JAX_MEMORY_FRACTION = "0.80"

# GPU를 사용하지 않는 data-contract 검사 모드를 고르는 CLI 인자다.
CHECK_ONLY_ARGUMENT = "--check-only"


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 시작했으면 dependency가 설치된 workspace conda Python으로 교체한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    current_python = Path(sys.executable).resolve()
    if current_python == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(
            "workspace conda Python이 없습니다. environment.yml로 먼저 환경을 생성하세요: "
            f"{expected_python}"
        )

    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def resolve_git_directory(repository_root: Path) -> Path:
    """일반 repository와 submodule의 실제 Git metadata 경로를 찾는다."""

    marker = repository_root / ".git"
    if marker.is_dir():
        return marker.resolve()
    if not marker.is_file():
        raise FileNotFoundError(f"OpenPI .git metadata가 없습니다: {marker}")

    marker_text = marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not marker_text.startswith(prefix):
        raise RuntimeError(f"알 수 없는 submodule .git 형식입니다: {marker_text!r}")
    git_directory = Path(marker_text[len(prefix) :].strip())
    if not git_directory.is_absolute():
        git_directory = marker.parent / git_directory
    return git_directory.resolve()


def read_repository_head(repository_root: Path) -> str:
    """외부 git 명령 없이 repository의 현재 HEAD commit을 읽는다."""

    git_directory = resolve_git_directory(repository_root)
    head_text = (git_directory / "HEAD").read_text(encoding="utf-8").strip()
    if not head_text.startswith("ref:"):
        return head_text

    reference_name = head_text.removeprefix("ref:").strip()
    loose_reference = git_directory / reference_name
    if loose_reference.is_file():
        return loose_reference.read_text(encoding="utf-8").strip()

    packed_references = git_directory / "packed-refs"
    if packed_references.is_file():
        for line in packed_references.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            commit, name = line.split(" ", maxsplit=1)
            if name == reference_name:
                return commit
    raise RuntimeError(f"OpenPI HEAD reference를 찾을 수 없습니다: {reference_name}")


def configure_process_environment(arguments: Sequence[str]) -> None:
    """JAX와 OpenPI를 import하기 전에 버전, 경로, 캐시 환경을 고정한다."""

    required_paths = {
        "OpenPI root": OPENPI_ROOT,
        "OpenPI source": OPENPI_SOURCE_ROOT,
        "workspace source": WORKSPACE_SOURCE_ROOT,
    }
    missing_paths = [f"{name}: {path}" for name, path in required_paths.items() if not path.exists()]
    if missing_paths:
        raise FileNotFoundError("필수 소스 경로가 없습니다:\n" + "\n".join(missing_paths))

    actual_commit = read_repository_head(OPENPI_ROOT)
    if actual_commit != EXPECTED_OPENPI_COMMIT:
        raise RuntimeError(
            "검증되지 않은 OpenPI commit입니다: "
            f"expected={EXPECTED_OPENPI_COMMIT}, actual={actual_commit}"
        )

    os.environ.setdefault("OPENPI_DATA_HOME", str(DEFAULT_OPENPI_DATA_HOME))
    os.environ.setdefault("HF_HOME", str(DEFAULT_HUGGINGFACE_HOME))
    os.environ.setdefault("JAX_COMPILATION_CACHE_DIR", str(DEFAULT_JAX_CACHE_DIR))

    if CHECK_ONLY_ARGUMENT in arguments:
        # check-only는 GPU를 전혀 초기화하지 않아 Jupyter와 VRAM을 공유해도 안전하다.
        os.environ["JAX_PLATFORMS"] = "cpu"
        os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
    else:
        os.environ.setdefault(
            "XLA_PYTHON_CLIENT_MEM_FRACTION",
            DEFAULT_JAX_MEMORY_FRACTION,
        )

    # OpenPI repository root를 먼저 두어 공식 scripts package도 일관되게 찾도록 한다.
    import_paths = (OPENPI_ROOT, OPENPI_SOURCE_ROOT, WORKSPACE_SOURCE_ROOT)
    for path in reversed(import_paths):
        path_text = str(path)
        if path_text in sys.path:
            sys.path.remove(path_text)
        sys.path.insert(0, path_text)


def validate_openpi_import() -> None:
    """import된 openpi 패키지가 workspace의 고정 submodule인지 확인한다."""

    import openpi

    imported_path = Path(openpi.__file__).resolve()
    if not imported_path.is_relative_to(OPENPI_SOURCE_ROOT.resolve()):
        raise RuntimeError(
            "다른 환경의 openpi가 import됐습니다: "
            f"expected under={OPENPI_SOURCE_ROOT}, actual={imported_path}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """workspace Python과 환경을 준비한 뒤 실제 Piper π0 학습 명령을 실행한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    configure_process_environment(arguments)
    validate_openpi_import()

    # 환경 변수가 JAX import보다 먼저 적용되도록 의도적으로 함수 안에서 import한다.
    from piper_vla.training.trainer import main as training_main

    return training_main(arguments, workspace_root=WORKSPACE_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
