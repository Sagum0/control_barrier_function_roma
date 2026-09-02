"""완료된 OpenPI Orbax checkpoint를 부작용 없이 선택하고 검증한다."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from piper_vla.inference.settings import Pi0InferenceSettings


# Orbax가 checkpoint 전체 commit 상태를 기록하는 파일 이름이다.
CHECKPOINT_METADATA_FILENAME = "_CHECKPOINT_METADATA"

# OpenPI가 복원할 parameter tree의 필수 marker다.
PARAMS_METADATA_RELATIVE_PATH = Path("params/_METADATA")

# Orbax OCDBT parameter manifest의 필수 경로다.
PARAMS_MANIFEST_RELATIVE_PATH = Path("params/manifest.ocdbt")

# OpenPI 학습 checkpoint가 저장해야 하는 item handler key다.
REQUIRED_ITEM_HANDLERS = frozenset({"assets", "params", "train_state"})

# Piper normalization 통계가 포함해야 하는 최상위 key다.
NORM_STAT_KEYS = frozenset({"state", "actions"})

# 각 normalization 통계가 포함해야 하는 수치 field다.
NORM_FIELD_NAMES = ("mean", "std", "q01", "q99")

# Piper state와 action normalization 벡터의 길이다.
PIPER_ROBOT_DIM = 7


@dataclasses.dataclass(frozen=True)
class SelectedCheckpoint:
    """정적 검증을 통과한 한 개의 커밋 완료 checkpoint다."""

    # 학습 run의 절대 경로다.
    run_dir: Path

    # 선택된 absolute 학습 step이다.
    step: int

    # OpenPI loader에 넘길 숫자 step 디렉터리다.
    step_dir: Path

    # checkpoint에 포함된 normalization 자산 식별자다.
    asset_id: str

    # checkpoint 내부 norm_stats.json 절대 경로다.
    norm_stats_path: Path

    # normalization 파일의 SHA256 digest다.
    norm_stats_sha256: str


def _require_regular_file_under(
    path: Path,
    root: Path,
    *,
    field_name: str,
) -> Path:
    """root 아래 모든 구성 요소가 symlink가 아닌 일반 파일 경로인지 검사한다."""

    canonical_root = root.resolve()
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        raise ValueError(f"{field_name} 경로가 checkpoint를 벗어났습니다: {path}") from None

    current = root
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{field_name} 경로에 symlink를 허용하지 않습니다: {current}")
    if not current.is_file() or current.stat().st_size <= 0:
        raise FileNotFoundError(f"{field_name} 파일이 없거나 비어 있습니다: {current}")
    resolved = current.resolve()
    if not resolved.is_relative_to(canonical_root):
        raise ValueError(f"{field_name} 경로가 checkpoint를 벗어났습니다: {resolved}")
    return resolved


def _load_json_object(path: Path, *, field_name: str) -> dict[str, Any]:
    """UTF-8 JSON 파일을 읽고 최상위 object 형식을 검증한다."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"{field_name} 파일이 없습니다: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} JSON이 손상됐습니다: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} 최상위 값은 object여야 합니다: {path}")
    return value


def _require_finite_vector(value: Any, *, field_name: str) -> tuple[float, ...]:
    """정확히 7개의 유한 실수로 된 normalization 벡터를 반환한다."""

    if not isinstance(value, list) or len(value) != PIPER_ROBOT_DIM:
        raise ValueError(
            f"{field_name}은 길이 {PIPER_ROBOT_DIM} list여야 합니다: {value!r}"
        )
    vector: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(f"{field_name}[{index}]는 실수여야 합니다: {item!r}")
        converted = float(item)
        if not math.isfinite(converted):
            raise ValueError(f"{field_name}[{index}]에 NaN/Inf가 있습니다.")
        vector.append(converted)
    return tuple(vector)


def validate_norm_stats_file(path: Path) -> str:
    """OpenPI Piper norm_stats의 key·shape·유한값을 검증하고 digest를 반환한다."""

    if path.is_symlink():
        raise ValueError(f"norm_stats symlink는 허용하지 않습니다: {path}")
    payload = _load_json_object(path, field_name="norm_stats")
    if set(payload) != {"norm_stats"}:
        raise ValueError(
            "norm_stats 최상위 key가 올바르지 않습니다: "
            f"expected=['norm_stats'], actual={sorted(payload)}"
        )
    norm_stats = payload["norm_stats"]
    if not isinstance(norm_stats, dict) or set(norm_stats) != set(NORM_STAT_KEYS):
        actual_keys = sorted(norm_stats) if isinstance(norm_stats, dict) else []
        raise ValueError(
            "norm_stats key가 올바르지 않습니다: "
            f"expected={sorted(NORM_STAT_KEYS)}, actual={actual_keys}"
        )

    for key in ("state", "actions"):
        stats = norm_stats.get(key)
        if not isinstance(stats, dict) or set(stats) != set(NORM_FIELD_NAMES):
            raise ValueError(f"norm_stats.{key} field가 올바르지 않습니다.")
        vectors = {
            field_name: _require_finite_vector(
                stats[field_name],
                field_name=f"norm_stats.{key}.{field_name}",
            )
            for field_name in NORM_FIELD_NAMES
        }
        if any(value <= 0.0 for value in vectors["std"]):
            raise ValueError(f"norm_stats.{key}.std는 모두 양수여야 합니다.")
        if any(low > high for low, high in zip(vectors["q01"], vectors["q99"])):
            raise ValueError(f"norm_stats.{key}의 q01이 q99보다 큽니다.")

    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_committed_checkpoint(
    step_dir: Path,
    *,
    asset_id: str,
) -> SelectedCheckpoint:
    """한 숫자 step 디렉터리가 완전히 commit됐는지 정적으로 검사한다."""

    if step_dir.is_symlink():
        raise ValueError(f"checkpoint step symlink는 허용하지 않습니다: {step_dir}")
    if not step_dir.exists():
        raise FileNotFoundError(f"checkpoint step 디렉터리가 없습니다: {step_dir}")
    if not step_dir.is_dir() or not step_dir.name.isdecimal():
        raise ValueError(f"checkpoint는 숫자 step 디렉터리여야 합니다: {step_dir}")
    canonical_step_dir = step_dir.resolve()
    if canonical_step_dir != step_dir.absolute():
        raise ValueError(f"checkpoint 경로의 상위 symlink를 허용하지 않습니다: {step_dir}")
    step = int(step_dir.name)
    if step <= 0:
        raise ValueError(f"checkpoint step은 양수여야 합니다: {step}")

    metadata_path = _require_regular_file_under(
        step_dir / CHECKPOINT_METADATA_FILENAME,
        step_dir,
        field_name="checkpoint metadata",
    )
    metadata = _load_json_object(metadata_path, field_name="checkpoint metadata")
    commit_timestamp = metadata.get("commit_timestamp_nsecs")
    if type(commit_timestamp) is not int or commit_timestamp <= 0:
        raise ValueError(
            "checkpoint가 아직 commit되지 않았습니다: "
            f"{metadata_path}, commit_timestamp_nsecs={commit_timestamp!r}"
        )
    item_handlers = metadata.get("item_handlers")
    if not isinstance(item_handlers, dict) or not REQUIRED_ITEM_HANDLERS.issubset(item_handlers):
        actual_handlers = sorted(item_handlers) if isinstance(item_handlers, dict) else []
        raise ValueError(
            "checkpoint item handler가 누락됐습니다: "
            f"required={sorted(REQUIRED_ITEM_HANDLERS)}, actual={actual_handlers}"
        )

    for relative_path in (PARAMS_METADATA_RELATIVE_PATH, PARAMS_MANIFEST_RELATIVE_PATH):
        _require_regular_file_under(
            step_dir / relative_path,
            step_dir,
            field_name="parameter checkpoint marker",
        )

    norm_stats_path = _require_regular_file_under(
        step_dir / "assets" / asset_id / "norm_stats.json",
        step_dir,
        field_name="checkpoint norm_stats",
    )
    norm_digest = validate_norm_stats_file(norm_stats_path)
    return SelectedCheckpoint(
        run_dir=canonical_step_dir.parent,
        step=step,
        step_dir=canonical_step_dir,
        asset_id=asset_id,
        norm_stats_path=norm_stats_path,
        norm_stats_sha256=norm_digest,
    )


def select_checkpoint(
    settings: Pi0InferenceSettings,
    *,
    step_override: int | None = None,
    latest: bool = False,
) -> SelectedCheckpoint:
    """명시 step 또는 opt-in latest 중 하나의 완료 checkpoint를 선택한다."""

    if latest and step_override is not None:
        raise ValueError("--latest와 --step은 동시에 사용할 수 없습니다.")
    if step_override is not None and (type(step_override) is not int or step_override <= 0):
        raise ValueError(f"--step은 양수 정수여야 합니다: {step_override!r}")

    checkpoint_settings = settings.checkpoint
    run_dir = (
        checkpoint_settings.runs_root
        / checkpoint_settings.config_name
        / checkpoint_settings.run_name
    ).resolve()
    if not run_dir.is_relative_to(settings.workspace_root):
        raise ValueError(f"학습 run 경로가 workspace를 벗어났습니다: {run_dir}")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"학습 run 디렉터리가 없습니다: {run_dir}")

    if not latest:
        requested_step = checkpoint_settings.step if step_override is None else step_override
        return inspect_committed_checkpoint(
            run_dir / str(requested_step),
            asset_id=checkpoint_settings.asset_id,
        )

    committed: list[SelectedCheckpoint] = []
    for candidate in run_dir.iterdir():
        if not candidate.name.isdecimal() or candidate.is_symlink():
            continue
        try:
            committed.append(
                inspect_committed_checkpoint(candidate, asset_id=checkpoint_settings.asset_id)
            )
        except (FileNotFoundError, TypeError, ValueError):
            continue
    if not committed:
        raise FileNotFoundError(f"커밋 완료 checkpoint가 없습니다: {run_dir}")
    return max(committed, key=lambda checkpoint: checkpoint.step)
