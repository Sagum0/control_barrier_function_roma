"""LeRobot async client YAML과 명령 생성의 CPU 회귀 테스트다."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from piper_vla.inference.client_command import build_vla_pipeline_client_command
from piper_vla.inference.settings import load_pi0_inference_settings


# 테스트와 실제 설정이 공유하는 task prompt다.
TEST_PROMPT = "pick up the green blocks one at a time and place them in the white box"


def _config_text() -> str:
    """schema 2의 최소 유효 설정을 반환한다."""

    return (
        "schema_version: 2\n"
        "checkpoint:\n"
        "  runs_root: data/runs\n"
        "  config_name: pi0_piper_lora\n"
        "  run_name: test_run\n"
        "  asset_id: test_asset\n"
        "  step: 30000\n"
        "policy:\n"
        f"  prompt: {TEST_PROMPT!r}\n"
        "  num_inference_steps: 10\n"
        "server:\n"
        "  host: 0.0.0.0\n"
        "  port: 8080\n"
        "runtime:\n"
        "  jax_memory_fraction: 0.7\n"
        "async_client:\n"
        "  actions_per_chunk: 50\n"
        "  chunk_size_threshold: 0.5\n"
        "  aggregate_fn_name: weighted_average\n"
        "  fps: 20\n"
        "  observation_queue_timeout_seconds: 1.0\n"
        "  debug_visualize_queue_size: true\n"
    )


class AsyncClientSettingsTest(unittest.TestCase):
    """strict async 설정과 생성된 기존 client CLI를 검사한다."""

    def _load(self, text: str):
        """임시 workspace에서 설정 문자열을 load한다."""

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name).resolve()
        config_path = workspace / "config/inference.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(text, encoding="utf-8")
        return load_pi0_inference_settings(config_path, workspace)

    def test_schema2_values_and_client_command(self) -> None:
        """YAML 값이 typed 설정과 client CLI에 그대로 반영돼야 한다."""

        settings = self._load(_config_text())
        self.assertIsNotNone(settings.async_client)
        async_client = settings.async_client
        assert async_client is not None
        self.assertEqual(async_client.actions_per_chunk, 50)
        self.assertEqual(async_client.chunk_size_threshold, 0.5)
        self.assertEqual(async_client.aggregate_fn_name, "weighted_average")
        self.assertEqual(async_client.fps, 20)

        command = build_vla_pipeline_client_command(
            settings,
            requested_step=30000,
        )
        self.assertIn("--server_address=GPU_SERVER_IP:8080", command)
        self.assertIn("--actions_per_chunk=50", command)
        self.assertIn("--chunk_size_threshold=0.5", command)
        self.assertIn("--aggregate_fn_name=weighted_average", command)
        self.assertIn("--fps=20", command)

    def test_invalid_async_values_fail_before_jax(self) -> None:
        """오타·범위·bool 타입은 설정 load 단계에서 실패해야 한다."""

        with self.assertRaisesRegex(ValueError, "aggregate_fn_name"):
            self._load(
                _config_text().replace(
                    "aggregate_fn_name: weighted_average",
                    "aggregate_fn_name: unknown",
                )
            )
        with self.assertRaisesRegex(ValueError, "actions_per_chunk"):
            self._load(_config_text().replace("actions_per_chunk: 50", "actions_per_chunk: 51"))
        with self.assertRaisesRegex(TypeError, "actions_per_chunk"):
            self._load(_config_text().replace("actions_per_chunk: 50", "actions_per_chunk: true"))


if __name__ == "__main__":
    unittest.main()
