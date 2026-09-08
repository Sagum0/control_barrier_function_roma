"""Piper π0.5 추론 YAML을 공통 strict loader로 읽는다."""

from __future__ import annotations

from pathlib import Path

from piper_vla.inference.pi0.settings import (
    AsyncClientOptions,
    InferenceCheckpointSettings,
    InferenceClientSettings,
    InferencePolicySettings,
    InferenceRuntimeSettings,
    InferenceServerSettings,
    Pi0InferenceSettings,
    load_inference_settings,
)


# π0.5 학습 checkpoint가 저장되는 config namespace다.
PIPER_PI05_CONFIG_NAME = "pi05_piper_lora"

# 공통 설정 구조는 같고 checkpoint/model 계약만 π0.5로 고정한다.
Pi05InferenceSettings = Pi0InferenceSettings


def load_pi05_inference_settings(
    config_path: Path,
    workspace_root: Path,
) -> Pi05InferenceSettings:
    """Piper π0.5 namespace로 고정해 추론 YAML을 읽는다."""

    return load_inference_settings(
        config_path,
        workspace_root,
        expected_config_name=PIPER_PI05_CONFIG_NAME,
        model_label="π0.5",
    )


__all__ = [
    "AsyncClientOptions",
    "InferenceCheckpointSettings",
    "InferenceClientSettings",
    "InferencePolicySettings",
    "InferenceRuntimeSettings",
    "InferenceServerSettings",
    "PIPER_PI05_CONFIG_NAME",
    "Pi05InferenceSettings",
    "load_pi05_inference_settings",
]
