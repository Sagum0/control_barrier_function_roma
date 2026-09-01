"""분리된 training과 inference canonical 경로를 검증한다."""

from __future__ import annotations

from pathlib import Path
import unittest

from piper_vla.training import settings as training_settings


# 테스트 기준 workspace root다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class TrainingLayoutTest(unittest.TestCase):
    """production 코드가 training과 inference 경로에만 존재하는지 검사한다."""

    def test_training_settings_are_importable(self) -> None:
        """canonical training settings loader를 직접 import할 수 있어야 한다."""

        self.assertTrue(callable(training_settings.load_pi0_settings))
        self.assertTrue(hasattr(training_settings, "Pi0Settings"))

    def test_canonical_workspace_paths_exist(self) -> None:
        """학습과 추론의 canonical source·script·config가 분리돼 있어야 한다."""

        expected_paths = (
            "src/piper_vla/training/trainer.py",
            "src/piper_vla/inference/policy_server.py",
            "scripts/training/train_from_config.py",
            "scripts/inference/serve_policy.py",
            "config/training/pi0_piper_lora.yaml",
            "config/inference/pi0_piper_inference.yaml",
        )
        for relative_path in expected_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((WORKSPACE_ROOT / relative_path).is_file())


if __name__ == "__main__":
    unittest.main()
