"""Piper π0 server-first 추론 경계의 CPU 전용 회귀 테스트다."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from typing import Any, Mapping

import numpy as np

from piper_vla.inference.checkpoint import select_checkpoint
from piper_vla.inference.observation import (
    build_canonical_observation,
    validate_policy_output,
)
from piper_vla.inference.policy_server import (
    ValidatedPiperPolicy,
    require_jax_gpu_backend,
)
from piper_vla.inference.romalab_contract import build_romalab_policy_metadata
from piper_vla.inference.settings import load_pi0_inference_settings


# 테스트에 사용하는 정확한 task prompt다.
TEST_PROMPT = "pick up the green blocks one at a time and place them in the white box"


class _FakePolicy:
    """GPU 없이 server 입출력 wrapper를 검사하는 가짜 policy다."""

    @property
    def metadata(self) -> Mapping[str, Any]:
        """가짜 policy 식별 metadata를 반환한다."""

        return {"fake": True}

    def infer(self, observation: Mapping[str, Any]) -> Mapping[str, Any]:
        """입력 prompt를 확인하고 고정 `(50, 7)` action을 반환한다."""

        if observation["prompt"] != TEST_PROMPT:
            raise AssertionError("prompt가 wrapper를 통과하지 않았습니다.")
        return {
            "actions": np.zeros((50, 7), dtype=np.float32),
            "policy_timing": {"infer_ms": 1.0},
        }


class InferenceCoreTest(unittest.TestCase):
    """설정, checkpoint, canonical 입출력을 함께 검증한다."""

    def _write_config(self, workspace: Path, *, duplicate_port: bool = False) -> Path:
        """임시 workspace 안에 strict YAML fixture를 만든다."""

        config_dir = workspace / "config"
        config_dir.mkdir(parents=True)
        duplicate_line = "  port: 8001\n" if duplicate_port else ""
        config_path = config_dir / "inference.yaml"
        config_path.write_text(
            "schema_version: 1\n"
            "checkpoint:\n"
            "  runs_root: data/runs\n"
            "  config_name: pi0_piper_lora\n"
            "  run_name: test_run\n"
            "  asset_id: test_asset\n"
            "  step: 10\n"
            "policy:\n"
            f"  prompt: {TEST_PROMPT!r}\n"
            "  num_inference_steps: 10\n"
            "server:\n"
            "  host: 127.0.0.1\n"
            "  port: 8000\n"
            f"{duplicate_line}"
            "runtime:\n"
            "  jax_memory_fraction: 0.7\n",
            encoding="utf-8",
        )
        return config_path

    def _make_checkpoint(self, workspace: Path, step: int) -> None:
        """커밋 완료 Orbax checkpoint의 최소 정적 fixture를 만든다."""

        step_dir = workspace / "data/runs/pi0_piper_lora/test_run" / str(step)
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

    def test_strict_settings_and_duplicate_key(self) -> None:
        """정상 YAML은 통과하고 같은 section의 중복 key는 실패해야 한다."""

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            config_path = self._write_config(workspace)
            settings = load_pi0_inference_settings(config_path, workspace)
            self.assertEqual(settings.checkpoint.step, 10)
            self.assertEqual(settings.policy.prompt, TEST_PROMPT)

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            config_path = self._write_config(workspace, duplicate_port=True)
            with self.assertRaisesRegex(ValueError, "중복"):
                load_pi0_inference_settings(config_path, workspace)

    def test_latest_ignores_orbax_temporary_directory(self) -> None:
        """latest는 숫자 완료 step만 고르고 Orbax 임시 디렉터리를 무시해야 한다."""

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            settings = load_pi0_inference_settings(
                self._write_config(workspace),
                workspace,
            )
            self._make_checkpoint(workspace, 5)
            self._make_checkpoint(workspace, 10)
            temporary_step = (
                workspace
                / "data/runs/pi0_piper_lora/test_run/20.orbax-checkpoint-tmp-1"
            )
            temporary_step.mkdir(parents=True)
            selected = select_checkpoint(settings, latest=True)
            self.assertEqual(selected.step, 10)
            self.assertEqual(len(selected.norm_stats_sha256), 64)

    def test_observation_and_policy_output_contract(self) -> None:
        """canonical 관측과 `(50, 7)` action이 dtype·shape를 보존해야 한다."""

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        observation = build_canonical_observation(
            image,
            image,
            np.zeros(7, dtype=np.float64),
            TEST_PROMPT,
        )
        self.assertEqual(observation["observation/state"].dtype, np.float32)
        validated = validate_policy_output(
            {"actions": np.zeros((50, 7), dtype=np.float64)}
        )
        self.assertEqual(validated["actions"].dtype, np.float32)
        with self.assertRaises(ValueError):
            validate_policy_output({"actions": np.zeros((49, 7), dtype=np.float32)})
        with self.assertRaises(TypeError):
            build_canonical_observation(
                image,
                image,
                np.zeros(7, dtype=np.complex64),
                TEST_PROMPT,
            )
        with self.assertRaises(TypeError):
            validate_policy_output(
                {"actions": np.zeros((50, 7), dtype=np.complex64)}
            )

    def test_validated_policy_blocks_bad_contract(self) -> None:
        """server wrapper가 입력과 출력 계약을 실제 infer 경계에서 강제해야 한다."""

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        observation = build_canonical_observation(
            image,
            image,
            np.zeros(7, dtype=np.float32),
            TEST_PROMPT,
        )
        policy = ValidatedPiperPolicy(
            _FakePolicy(),
            {"checkpoint_step": 10},
            expected_prompt=TEST_PROMPT,
        )
        result = policy.infer(observation)
        self.assertEqual(result["actions"].shape, (50, 7))
        self.assertEqual(policy.metadata["checkpoint_step"], 10)

        wrong_prompt = dict(observation)
        wrong_prompt["prompt"] = "do a different task"
        with self.assertRaisesRegex(ValueError, "prompt"):
            policy.infer(wrong_prompt)

    def test_gpu_backend_and_chunk_metadata_contract(self) -> None:
        """CPU 경로에서 GPU fail-fast와 완료된 RoMaLab chunk 계약을 검사한다."""

        self.assertEqual(require_jax_gpu_backend(lambda: "gpu"), "gpu")
        with self.assertRaisesRegex(RuntimeError, "GPU backend"):
            require_jax_gpu_backend(lambda: "cpu")

        chunk_contract = build_romalab_policy_metadata()["chunk_contract"]
        self.assertEqual(chunk_contract["frame_id_template"], "chunk_{chunk_id}")
        self.assertEqual(chunk_contract["point_count"], 50)
        self.assertEqual(chunk_contract["point_period_seconds"], 0.05)
        self.assertEqual(
            chunk_contract["empty_point_fields"],
            ["velocities", "accelerations", "effort"],
        )
        self.assertEqual(
            chunk_contract["qos"],
            {
                "history": "keep_last",
                "depth": 10,
                "reliability": "reliable",
                "durability": "volatile",
            },
        )


if __name__ == "__main__":
    unittest.main()
