#!/usr/bin/env python3
"""완료된 Piper π0 checkpoint를 안전한 OpenPI WebSocket server로 실행한다."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


# 이 실행 파일이 속한 vla_ws 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# 추론 dependency가 설치된 workspace conda Python이다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"

# 고정 OpenPI submodule의 repository root다.
OPENPI_ROOT = WORKSPACE_ROOT / "third_party" / "openpi"

# 현재 추론 코드가 검증된 OpenPI commit이다.
EXPECTED_OPENPI_COMMIT = "215abfb217dbac7d5f1273282331b9b1866c0479"

# OpenPI Python package source 경로다.
OPENPI_SOURCE_ROOT = OPENPI_ROOT / "src"

# Piper Python package source 경로다.
WORKSPACE_SOURCE_ROOT = WORKSPACE_ROOT / "src"

# OpenPI model/tokenizer cache 경로다.
DEFAULT_OPENPI_DATA_HOME = WORKSPACE_ROOT / "data" / "cache" / "openpi"

# Hugging Face cache 경로다.
DEFAULT_HUGGINGFACE_HOME = WORKSPACE_ROOT / "data" / "cache" / "huggingface"

# JAX compilation cache 경로다.
DEFAULT_JAX_CACHE_DIR = WORKSPACE_ROOT / "data" / "cache" / "jax"

# 인자를 생략했을 때 읽는 실제 추론 config다.
DEFAULT_CONFIG_PATH = WORKSPACE_ROOT / "config" / "inference" / "pi0_piper_inference.yaml"


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 시작했으면 workspace conda Python으로 process를 교체한다."""

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


def configure_workspace_source_path() -> None:
    """JAX import 없이 Piper settings/checkpoint 모듈을 찾게 한다."""

    source_text = str(WORKSPACE_SOURCE_ROOT)
    if source_text in sys.path:
        sys.path.remove(source_text)
    sys.path.insert(0, source_text)


def resolve_git_directory(repository_root: Path) -> Path:
    """일반 repository와 submodule의 실제 Git metadata 경로를 찾는다."""

    marker = repository_root / ".git"
    if marker.is_dir():
        return marker.resolve()
    if not marker.is_file():
        raise FileNotFoundError(f"OpenPI .git metadata가 없습니다: {marker}")
    marker_text = marker.read_text(encoding="utf-8").strip()
    if not marker_text.startswith("gitdir:"):
        raise RuntimeError(f"알 수 없는 submodule .git 형식입니다: {marker_text!r}")
    git_directory = Path(marker_text.removeprefix("gitdir:").strip())
    if not git_directory.is_absolute():
        git_directory = marker.parent / git_directory
    return git_directory.resolve()


def read_repository_head(repository_root: Path) -> str:
    """외부 git process 없이 repository의 현재 HEAD commit을 읽는다."""

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
    raise RuntimeError(f"OpenPI HEAD reference를 찾지 못했습니다: {reference_name}")


def validate_openpi_repository() -> None:
    """OpenPI commit과 tracked·untracked worktree가 검증된 clean 상태인지 확인한다."""

    actual_commit = read_repository_head(OPENPI_ROOT)
    if actual_commit != EXPECTED_OPENPI_COMMIT:
        raise RuntimeError(
            "검증되지 않은 OpenPI commit입니다: "
            f"expected={EXPECTED_OPENPI_COMMIT}, actual={actual_commit}"
        )
    status = subprocess.run(
        ["git", "-C", str(OPENPI_ROOT), "status", "--porcelain", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        raise RuntimeError(f"OpenPI worktree 상태를 읽지 못했습니다: {status.stderr.strip()}")
    if status.stdout.strip():
        raise RuntimeError(
            "OpenPI submodule에 검증되지 않은 변경이 있습니다:\n" + status.stdout.strip()
        )


def configure_openpi_runtime(memory_fraction: float) -> None:
    """JAX/OpenPI import 전에 repository, cache, GPU allocator, import path를 고정한다."""

    validate_openpi_repository()
    os.environ.setdefault("OPENPI_DATA_HOME", str(DEFAULT_OPENPI_DATA_HOME))
    os.environ.setdefault("HF_HOME", str(DEFAULT_HUGGINGFACE_HOME))
    os.environ.setdefault("JAX_COMPILATION_CACHE_DIR", str(DEFAULT_JAX_CACHE_DIR))
    os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = format(memory_fraction, ".12g")

    for path in reversed((OPENPI_ROOT, OPENPI_SOURCE_ROOT, WORKSPACE_SOURCE_ROOT)):
        path_text = str(path)
        if path_text in sys.path:
            sys.path.remove(path_text)
        sys.path.insert(0, path_text)


def build_argument_parser() -> argparse.ArgumentParser:
    """명시 step과 opt-in latest를 분리한 policy server parser를 만든다."""

    parser = argparse.ArgumentParser(
        description="완료된 Piper π0 Orbax checkpoint를 WebSocket policy server로 제공합니다."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--step", type=int, help="YAML 대신 사용할 정확한 checkpoint step")
    selection.add_argument(
        "--latest",
        action="store_true",
        help="임시 디렉터리를 제외한 최신 커밋 완료 checkpoint 선택",
    )
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--print-config",
        action="store_true",
        help="YAML만 검증하고 GPU/checkpoint를 건드리지 않고 종료",
    )
    operation.add_argument(
        "--check-only",
        action="store_true",
        help="checkpoint 구조와 내장 norm stats까지만 검증하고 JAX를 import하지 않음",
    )
    return parser


def print_settings(settings: object, *, selected_step: int | str) -> None:
    """실제 server가 사용할 경로와 sampling 설정을 한 번 출력한다."""

    print("Config file        :", settings.config_path)
    print("Run                :", settings.checkpoint.run_name)
    print("Requested step     :", selected_step)
    print("Asset id           :", settings.checkpoint.asset_id)
    print("Prompt             :", settings.policy.prompt)
    print("Inference steps    :", settings.policy.num_inference_steps)
    print("Server             :", f"ws://{settings.server.host}:{settings.server.port}")
    print("JAX memory fraction:", settings.runtime.jax_memory_fraction)


def assert_lightweight_import_boundary() -> None:
    """check-only 경로가 JAX, OpenPI policy, Torch, ROS를 import하지 않았는지 확인한다."""

    forbidden_prefixes = ("jax", "openpi", "torch", "rclpy", "roslibpy")
    imported = sorted(
        name
        for name in sys.modules
        if name in forbidden_prefixes
        or name.startswith(tuple(f"{prefix}." for prefix in forbidden_prefixes))
    )
    if imported:
        raise RuntimeError(f"check-only에서 무거운 모듈이 import됐습니다: {imported[:10]}")


def main(argv: Sequence[str] | None = None) -> int:
    """설정·checkpoint를 먼저 검사하고 실제 serve에서만 JAX policy를 복원한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    configure_workspace_source_path()

    from piper_vla.inference.checkpoint import select_checkpoint
    from piper_vla.inference.settings import load_pi0_inference_settings

    parser = build_argument_parser()
    namespace = parser.parse_args(arguments)
    if namespace.step is not None and namespace.step <= 0:
        parser.error(f"--step은 양수여야 합니다: {namespace.step}")

    settings = load_pi0_inference_settings(namespace.config, WORKSPACE_ROOT)
    requested_step: int | str = "latest" if namespace.latest else (
        settings.checkpoint.step if namespace.step is None else namespace.step
    )
    print_settings(settings, selected_step=requested_step)
    if namespace.print_config:
        assert_lightweight_import_boundary()
        return 0

    checkpoint = select_checkpoint(
        settings,
        step_override=namespace.step,
        latest=namespace.latest,
    )
    print("Checkpoint         :", checkpoint.step_dir)
    print("Norm stats SHA256  :", checkpoint.norm_stats_sha256)
    if namespace.check_only:
        assert_lightweight_import_boundary()
        print("PASS: committed checkpoint and embedded norm stats")
        print("PASS: JAX/OpenPI policy/GPU not initialized")
        return 0

    configure_openpi_runtime(settings.runtime.jax_memory_fraction)
    from piper_vla.inference.policy_server import (
        require_jax_gpu_backend,
        serve_piper_policy,
    )

    jax_backend = require_jax_gpu_backend()
    print("JAX backend        :", jax_backend)
    print("Health check       :", f"http://{settings.server.host}:{settings.server.port}/healthz")
    print("Loading π0 policy and starting WebSocket server...", flush=True)
    serve_piper_policy(settings, checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
