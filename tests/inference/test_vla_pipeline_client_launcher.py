"""vla_ws YAML 기반 vla_pipeline client launcher 회귀 테스트다."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = (
    WORKSPACE_ROOT / "scripts" / "inference" / "run_vla_pipeline_client.py"
)


def _load_launcher() -> object:
    """process 교체 없이 launcher의 순수 구성 함수만 불러온다."""

    spec = importlib.util.spec_from_file_location(
        "piper_vla_pipeline_client_launcher_test",
        LAUNCHER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"client launcher를 읽지 못했습니다: {LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(
    *,
    episode_time_seconds: float | None,
    mode: str = "async",
) -> SimpleNamespace:
    """launcher argument와 environment를 검사할 최소 설정을 만든다."""

    return SimpleNamespace(
        checkpoint=SimpleNamespace(run_name="test_run"),
        policy=SimpleNamespace(prompt="pick up the green block"),
        server=SimpleNamespace(host="0.0.0.0", port=8080),
        client=SimpleNamespace(
            mode=mode,
            episode_time_seconds=episode_time_seconds,
            actions_per_chunk=50,
            fps=20,
            async_options=SimpleNamespace(
                chunk_size_threshold=0.75,
                aggregate_fn_name="weighted_average",
                debug_visualize_queue_size=True,
            ),
        ),
    )


class VlaPipelineClientLauncherTest(unittest.TestCase):
    """YAML 값이 기존 client 계약으로 손실 없이 전달돼야 한다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = _load_launcher()

    def test_builds_existing_client_arguments_from_settings(self) -> None:
        """step·prompt·서버·chunk 설정을 draccus argument로 변환해야 한다."""

        arguments = self.launcher.build_client_arguments(
            _settings(episode_time_seconds=35.0),
            checkpoint_step=30000,
        )
        self.assertEqual(arguments[1:3], ["-m", "piper_bridge.async_client"])
        self.assertIn("--server_address=127.0.0.1:8080", arguments)
        self.assertIn("--pretrained_name_or_path=test_run/30000", arguments)
        self.assertIn("--task=pick up the green block", arguments)
        self.assertIn("--actions_per_chunk=50", arguments)
        self.assertIn("--chunk_size_threshold=0.75", arguments)
        self.assertIn("--fps=20", arguments)
        self.assertIn("--debug_visualize_queue_size=true", arguments)

    def test_duration_is_forced_and_null_explicitly_clears_limit(self) -> None:
        """35는 환경변수로 전달하고 null은 이전 shell 값을 지워야 한다."""

        limited = self.launcher.build_client_environment(
            _settings(episode_time_seconds=35.0),
            {"PIPER_EPISODE_TIME_S": "999"},
        )
        unlimited = self.launcher.build_client_environment(
            _settings(episode_time_seconds=None),
            {"PIPER_EPISODE_TIME_S": "999"},
        )
        self.assertEqual(limited["PIPER_EPISODE_TIME_S"], "35")
        self.assertEqual(unlimited["PIPER_EPISODE_TIME_S"], "")
        self.assertIn("/home/pc/vla_pipeline", limited["PYTHONPATH"])
        self.assertIn(str(WORKSPACE_ROOT / "src"), limited["PYTHONPATH"])

    def test_ipv6_wildcard_uses_local_connect_address(self) -> None:
        """IPv6 wildcard bind도 같은 PC에서 접속 가능한 주소가 돼야 한다."""

        self.assertEqual(self.launcher._server_address("::", 8080), "[::1]:8080")

    def test_sync_arguments_ignore_all_async_options(self) -> None:
        """sync 명령에는 queue threshold·aggregation·queue 시각화가 없어야 한다."""

        settings = _settings(episode_time_seconds=35.0, mode="sync")
        arguments = self.launcher.build_client_arguments(settings, checkpoint_step=30000)
        command = " ".join(arguments)
        self.assertEqual(arguments[1:3], ["-m", "piper_vla.inference.sync_client"])
        self.assertIn("--episode-time-seconds=35", arguments)
        self.assertNotIn("chunk_size_threshold", command)
        self.assertNotIn("aggregate_fn_name", command)
        self.assertNotIn("debug_visualize_queue_size", command)

        environment = self.launcher.build_client_environment(
            settings,
            {"PIPER_EPISODE_TIME_S": "999"},
        )
        self.assertEqual(environment["PIPER_EPISODE_TIME_S"], "")


if __name__ == "__main__":
    unittest.main()
