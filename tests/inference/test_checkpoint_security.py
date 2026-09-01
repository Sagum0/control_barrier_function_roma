"""Orbax checkpoint 경로 탈출과 자산 오염을 막는 CPU 회귀 테스트다."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from piper_vla.inference.checkpoint import inspect_committed_checkpoint


# 내부 symlink 공격을 재현할 checkpoint 필수 파일 경로다.
SYMLINK_TARGETS = (
    "_CHECKPOINT_METADATA",
    "params/_METADATA",
    "params/manifest.ocdbt",
    "assets/test_asset/norm_stats.json",
)


def _make_checkpoint(step_dir: Path) -> None:
    """보안 검사용 최소 커밋 완료 checkpoint fixture를 만든다."""

    (step_dir / "params").mkdir(parents=True)
    (step_dir / "assets/test_asset").mkdir(parents=True)
    (step_dir / "_CHECKPOINT_METADATA").write_text(
        json.dumps(
            {
                "commit_timestamp_nsecs": 1,
                "item_handlers": {
                    "assets": "CallbackHandler",
                    "params": "PyTreeCheckpointHandler",
                    "train_state": "PyTreeCheckpointHandler",
                },
            }
        ),
        encoding="utf-8",
    )
    (step_dir / "params/_METADATA").write_text("{}", encoding="utf-8")
    (step_dir / "params/manifest.ocdbt").write_bytes(b"manifest")
    vector = [float(index + 1) for index in range(7)]
    stats = {
        key: {
            "mean": vector,
            "std": vector,
            "q01": vector,
            "q99": vector,
        }
        for key in ("state", "actions")
    }
    (step_dir / "assets/test_asset/norm_stats.json").write_text(
        json.dumps({"norm_stats": stats}),
        encoding="utf-8",
    )


class CheckpointSecurityTest(unittest.TestCase):
    """checkpoint 내부 경로와 norm JSON의 strict 계약을 검사한다."""

    def test_internal_symlinks_are_rejected(self) -> None:
        """필수 파일 네 종류가 외부 symlink이면 모두 실패해야 한다."""

        for relative_path in SYMLINK_TARGETS:
            with self.subTest(relative_path=relative_path):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    step_dir = root / "10"
                    _make_checkpoint(step_dir)
                    target = step_dir / relative_path
                    outside = root / f"outside_{target.name}"
                    outside.write_bytes(target.read_bytes())
                    target.unlink()
                    target.symlink_to(outside)
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        inspect_committed_checkpoint(step_dir, asset_id="test_asset")

    def test_unknown_norm_stats_top_level_key_is_rejected(self) -> None:
        """정규화 자산에 알 수 없는 최상위 key가 있으면 실패해야 한다."""

        with tempfile.TemporaryDirectory() as temporary:
            step_dir = Path(temporary) / "10"
            _make_checkpoint(step_dir)
            norm_path = step_dir / "assets/test_asset/norm_stats.json"
            payload = json.loads(norm_path.read_text(encoding="utf-8"))
            payload["unexpected"] = True
            norm_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "최상위 key"):
                inspect_committed_checkpoint(step_dir, asset_id="test_asset")


if __name__ == "__main__":
    unittest.main()
