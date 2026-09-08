"""Piper π0.5 추론의 CPU 전용 설정·checkpoint·transport 회귀 테스트다."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from piper_vla.inference.pi05.checkpoint import select_checkpoint
from piper_vla.inference.pi05.policy_server import build_policy_metadata
from piper_vla.inference.pi05.settings import load_pi05_inference_settings
from piper_vla.inference.transports.vla_pipeline.lerobot_grpc import (
    RemotePolicyConfigCompat,
    validate_remote_policy_config,
)


TEST_PROMPT = "pick up the green blocks one at a time and place them in the white box"


class Pi05InferenceCoreTest(unittest.TestCase):
    """π0와 섞이면 안 되는 π0.5 namespace와 metadata를 검사한다."""

    def _write_config(self, workspace: Path, *, config_name: str) -> Path:
        """schema 1의 최소 π0.5 설정을 만든다."""

        path = workspace / "config/inference.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            "schema_version: 1\n"
            "checkpoint:\n"
            "  runs_root: data/runs\n"
            f"  config_name: {config_name}\n"
            "  run_name: test_run\n"
            "  asset_id: test_asset\n"
            "  step: 10\n"
            "policy:\n"
            f"  prompt: {TEST_PROMPT!r}\n"
            "  num_inference_steps: 10\n"
            "server:\n"
            "  host: 127.0.0.1\n"
            "  port: 8001\n"
            "runtime:\n"
            "  jax_memory_fraction: 0.6\n",
            encoding="utf-8",
        )
        return path

    def _make_checkpoint(self, workspace: Path) -> None:
        """커밋 완료 checkpoint의 최소 정적 fixture를 만든다."""

        step_dir = workspace / "data/runs/pi05_piper_lora/test_run/10"
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
            key: {"mean": vector, "std": vector, "q01": vector, "q99": vector}
            for key in ("state", "actions")
        }
        (step_dir / "assets/test_asset/norm_stats.json").write_text(
            json.dumps({"norm_stats": stats}),
            encoding="utf-8",
        )

    def test_pi05_namespace_checkpoint_and_metadata(self) -> None:
        """π0.5 설정이 정확한 run을 선택하고 self-describing metadata를 만든다."""

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            settings = load_pi05_inference_settings(
                self._write_config(workspace, config_name="pi05_piper_lora"),
                workspace,
            )
            self._make_checkpoint(workspace)
            checkpoint = select_checkpoint(settings)
            metadata = build_policy_metadata(settings, checkpoint)
            self.assertEqual(checkpoint.step, 10)
            self.assertEqual(metadata["model_type"], "pi05")
            self.assertEqual(metadata["normalization"], "quantile")
            self.assertEqual(metadata["checkpoint_step"], 10)

    def test_pi0_namespace_is_rejected(self) -> None:
        """π0 checkpoint namespace를 π0.5 server에서 조용히 받지 않는다."""

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, "pi05_piper_lora"):
                load_pi05_inference_settings(
                    self._write_config(workspace, config_name="pi0_piper_lora"),
                    workspace,
                )

    def test_grpc_handshake_requires_pi05(self) -> None:
        """π0.5 gRPC server가 π0 client handshake를 거부한다."""

        config = RemotePolicyConfigCompat(
            policy_type="pi05",
            pretrained_name_or_path="test_run/10",
            lerobot_features={},
            actions_per_chunk=50,
        )
        with self.assertRaisesRegex(ValueError, "feature key"):
            validate_remote_policy_config(
                config,
                expected_actions_per_chunk=50,
                expected_policy_type="pi05",
            )
        config.policy_type = "pi0"
        with self.assertRaisesRegex(ValueError, "pi05"):
            validate_remote_policy_config(
                config,
                expected_actions_per_chunk=50,
                expected_policy_type="pi05",
            )


if __name__ == "__main__":
    unittest.main()
