"""완료된 Piper π0.5 checkpoint를 OpenPI policy server로 제공한다."""

from __future__ import annotations

from typing import Any, Callable

from piper_vla.inference.pi0.policy_server import (
    POLICY_METADATA_SCHEMA_VERSION,
    PolicyProtocol,
    PolicyServerRuntime,
    ValidatedPiperPolicy,
    WebsocketServerProtocol,
    create_websocket_server,
    require_jax_gpu_backend,
)
from piper_vla.inference.pi05.checkpoint import SelectedCheckpoint
from piper_vla.inference.pi05.settings import (
    PIPER_PI05_CONFIG_NAME,
    Pi05InferenceSettings,
)
from piper_vla.inference.common.romalab_contract import build_romalab_policy_metadata


# 학습과 동일한 π0.5 LoRA 모델 계약이다.
PI05_PALIGEMMA_VARIANT = "gemma_2b_lora"
PI05_ACTION_EXPERT_VARIANT = "gemma_300m_lora"
PI05_MODEL_ACTION_DIM = 32
PI05_ACTION_HORIZON = 50
PI05_MAX_TOKEN_LEN = 200


def build_policy_metadata(
    settings: Pi05InferenceSettings,
    checkpoint: SelectedCheckpoint,
) -> dict[str, Any]:
    """client가 π0.5 checkpoint와 로봇 계약을 확인할 metadata를 만든다."""

    metadata = build_romalab_policy_metadata()
    metadata.update(
        {
            "schema_version": POLICY_METADATA_SCHEMA_VERSION,
            "model_type": "pi05",
            "config_name": settings.checkpoint.config_name,
            "run_name": settings.checkpoint.run_name,
            "checkpoint_step": checkpoint.step,
            "asset_id": checkpoint.asset_id,
            "norm_stats_sha256": checkpoint.norm_stats_sha256,
            "normalization": "quantile",
            "prompt": settings.policy.prompt,
            "num_inference_steps": settings.policy.num_inference_steps,
        }
    )
    return metadata


def build_inference_train_config(
    settings: Pi05InferenceSettings,
    checkpoint: SelectedCheckpoint,
) -> Any:
    """학습과 같은 π0.5 모델·data transform을 checkpoint asset으로 재구성한다."""

    # JAX/OpenPI heavy import는 실제 policy load 시점까지 지연한다.
    from openpi.models import model as model_api
    from openpi.models import pi0_config
    from openpi.training import config as training_config

    from piper_vla.training.pi05.data import PiperPi05DataConfigFactory

    model_config = pi0_config.Pi0Config(
        pi05=True,
        paligemma_variant=PI05_PALIGEMMA_VARIANT,
        action_expert_variant=PI05_ACTION_EXPERT_VARIANT,
        action_dim=PI05_MODEL_ACTION_DIM,
        action_horizon=PI05_ACTION_HORIZON,
        max_token_len=PI05_MAX_TOKEN_LEN,
        discrete_state_input=True,
    )
    if model_config.model_type is not model_api.ModelType.PI05:
        raise ValueError(f"π0.5가 아닌 model type입니다: {model_config.model_type}")
    if not model_config.pi05 or not model_config.discrete_state_input:
        raise ValueError("π0.5 discrete-state 모델 계약이 꺼져 있습니다.")

    checkpoint_assets_dir = checkpoint.step_dir / "assets"
    data_factory = PiperPi05DataConfigFactory(
        repo_id=checkpoint.asset_id,
        assets=training_config.AssetsConfig(
            assets_dir=str(checkpoint_assets_dir),
            asset_id=checkpoint.asset_id,
        ),
    )
    return training_config.TrainConfig(
        name=PIPER_PI05_CONFIG_NAME,
        exp_name=settings.checkpoint.run_name,
        model=model_config,
        data=data_factory,
        assets_base_dir=str(checkpoint.step_dir),
        checkpoint_base_dir=str(settings.checkpoint.runs_root),
        policy_metadata=build_policy_metadata(settings, checkpoint),
    )


def create_piper_policy(
    settings: Pi05InferenceSettings,
    checkpoint: SelectedCheckpoint,
    *,
    policy_factory: Callable[..., PolicyProtocol] | None = None,
) -> ValidatedPiperPolicy:
    """π0.5 params와 quantile stats로 검증 wrapper가 적용된 policy를 만든다."""

    train_config = build_inference_train_config(settings, checkpoint)
    if policy_factory is None:
        from openpi.policies import policy_config

        policy_factory = policy_config.create_trained_policy
    policy = policy_factory(
        train_config,
        checkpoint.step_dir,
        default_prompt=settings.policy.prompt,
        sample_kwargs={"num_steps": settings.policy.num_inference_steps},
    )
    return ValidatedPiperPolicy(
        policy,
        build_policy_metadata(settings, checkpoint),
        expected_prompt=settings.policy.prompt,
    )


def serve_piper_policy(
    settings: Pi05InferenceSettings,
    checkpoint: SelectedCheckpoint,
) -> None:
    """Piper π0.5 policy를 복원하고 WebSocket 요청을 계속 처리한다."""

    runtime = PolicyServerRuntime(
        policy=create_piper_policy(settings, checkpoint),
        checkpoint=checkpoint,
    )
    server = create_websocket_server(runtime.policy, settings)
    server.serve_forever()


__all__ = [
    "build_inference_train_config",
    "build_policy_metadata",
    "create_piper_policy",
    "create_websocket_server",
    "require_jax_gpu_backend",
    "serve_piper_policy",
]
