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
    """현재 schema 4의 최소 유효 설정을 반환한다."""

    return (
        "schema_version: 4\n"
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
        "client:\n"
        "  mode: async\n"
        "  episode_time_seconds: 35\n"
        "  actions_per_chunk: 50\n"
        "  fps: 20\n"
        "  observation_queue_timeout_seconds: 1.0\n"
        "  async_options:\n"
        "    chunk_size_threshold: 0.5\n"
        "    aggregate_fn_name: weighted_average\n"
        "    debug_visualize_queue_size: true\n"
    )


def _legacy_schema2_text() -> str:
    """시간 제한이 없던 schema 2 호환 fixture를 반환한다."""

    return (
        _config_text()
        .replace("schema_version: 4", "schema_version: 2")
        .replace("client:\n  mode: async\n", "async_client:\n")
        .replace("  episode_time_seconds: 35\n", "")
        .replace("  async_options:\n", "")
        .replace("    chunk_size_threshold", "  chunk_size_threshold")
        .replace("    aggregate_fn_name", "  aggregate_fn_name")
        .replace("    debug_visualize_queue_size", "  debug_visualize_queue_size")
    )


def _legacy_schema3_text() -> str:
    """직전 async 전용 schema 3 호환 fixture를 반환한다."""

    return (
        _config_text()
        .replace("schema_version: 4", "schema_version: 3")
        .replace("client:\n  mode: async\n", "async_client:\n")
        .replace("  async_options:\n", "")
        .replace("    chunk_size_threshold", "  chunk_size_threshold")
        .replace("    aggregate_fn_name", "  aggregate_fn_name")
        .replace("    debug_visualize_queue_size", "  debug_visualize_queue_size")
    )


class ClientSettingsTest(unittest.TestCase):
    """strict sync/async 설정과 생성된 기존 client CLI를 검사한다."""

    def _load(self, text: str):
        """임시 workspace에서 설정 문자열을 load한다."""

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name).resolve()
        config_path = workspace / "config/inference.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(text, encoding="utf-8")
        return load_pi0_inference_settings(config_path, workspace)

    def test_schema4_async_values_and_client_command(self) -> None:
        """YAML 값이 typed 설정과 client CLI에 그대로 반영돼야 한다."""

        settings = self._load(_config_text())
        self.assertIsNotNone(settings.client)
        client = settings.client
        assert client is not None
        self.assertEqual(client.mode, "async")
        self.assertEqual(client.episode_time_seconds, 35.0)
        self.assertEqual(client.actions_per_chunk, 50)
        self.assertEqual(client.async_options.chunk_size_threshold, 0.5)
        self.assertEqual(client.async_options.aggregate_fn_name, "weighted_average")
        self.assertEqual(client.fps, 20)

        command = build_vla_pipeline_client_command(
            settings,
            requested_step=30000,
        )
        self.assertIn("--server_address=GPU_SERVER_IP:8080", command)
        self.assertIn("PIPER_EPISODE_TIME_S=35", command)
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
        with self.assertRaisesRegex(ValueError, "episode_time_seconds"):
            self._load(
                _config_text().replace(
                    "episode_time_seconds: 35",
                    "episode_time_seconds: 0",
                )
            )

    def test_null_episode_time_generates_explicit_unlimited_command(self) -> None:
        """null은 상속된 시간 제한 환경변수도 지우는 무제한 명령이어야 한다."""

        settings = self._load(
            _config_text().replace(
                "episode_time_seconds: 35",
                "episode_time_seconds: null",
            )
        )
        client = settings.client
        assert client is not None
        self.assertIsNone(client.episode_time_seconds)
        command = build_vla_pipeline_client_command(
            settings,
            requested_step=settings.checkpoint.step,
        )
        self.assertIn("PIPER_EPISODE_TIME_S= PYTHONPATH=", command)

    def test_schema2_remains_unlimited_for_compatibility(self) -> None:
        """기존 schema 2 설정은 시간 제한이 없던 동작을 유지해야 한다."""

        settings = self._load(
            _legacy_schema2_text()
        )
        client = settings.client
        assert client is not None
        self.assertEqual(client.mode, "async")
        self.assertIsNone(client.episode_time_seconds)

    def test_schema3_remains_async_for_compatibility(self) -> None:
        """직전 schema 3 설정은 별도 mode 없이 async로 해석해야 한다."""

        settings = self._load(_legacy_schema3_text())
        client = settings.client
        assert client is not None
        self.assertEqual(client.mode, "async")
        self.assertEqual(client.episode_time_seconds, 35.0)

    def test_sync_mode_loads_but_rejects_legacy_async_command(self) -> None:
        """sync는 같은 공통값을 읽되 기존 async 명령 생성 경로를 사용하지 않아야 한다."""

        settings = self._load(_config_text().replace("mode: async", "mode: sync"))
        client = settings.client
        assert client is not None
        self.assertEqual(client.mode, "sync")
        with self.assertRaisesRegex(ValueError, "mode=async"):
            build_vla_pipeline_client_command(settings, requested_step=30000)


if __name__ == "__main__":
    unittest.main()
