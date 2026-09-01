"""완료된 Piper π0 checkpoint를 OpenPI WebSocket policy server로 제공한다."""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Mapping, Protocol

from piper_vla.inference.checkpoint import SelectedCheckpoint
from piper_vla.inference.observation import (
    validate_canonical_observation,
    validate_policy_output,
)
from piper_vla.inference.romalab_contract import build_romalab_policy_metadata
from piper_vla.inference.settings import Pi0InferenceSettings


# 학습 때 상속한 고정 OpenPI π0 LoRA profile 이름이다.
OFFICIAL_PI0_LORA_CONFIG_NAME = "pi0_libero_low_mem_finetune"

# 정책 metadata 형식의 버전이다.
POLICY_METADATA_SCHEMA_VERSION = 1

# 고정 OpenPI π0 내부 action 차원이다.
PI0_MODEL_ACTION_DIM = 32

# 고정 OpenPI π0 action chunk 길이다.
PI0_ACTION_HORIZON = 50


class PolicyProtocol(Protocol):
    """OpenPI policy와 CPU fake policy가 함께 만족할 최소 인터페이스다."""

    @property
    def metadata(self) -> Mapping[str, Any]:
        """client 연결 시 전달할 policy metadata를 반환한다."""

    def infer(self, observation: Mapping[str, Any]) -> Mapping[str, Any]:
        """한 canonical observation에서 action chunk를 예측한다."""


class WebsocketServerProtocol(Protocol):
    """OpenPI WebSocket server의 실행에 필요한 최소 인터페이스다."""

    def serve_forever(self) -> None:
        """서버가 종료될 때까지 요청을 처리한다."""


@dataclasses.dataclass(frozen=True)
class PolicyServerRuntime:
    """실행 준비가 끝난 policy와 checkpoint 정보를 묶는다."""

    # canonical 입출력 검증이 적용된 policy다.
    policy: PolicyProtocol

    # 실제로 복원한 커밋 완료 checkpoint다.
    checkpoint: SelectedCheckpoint


class ValidatedPiperPolicy:
    """OpenPI policy 앞뒤에서 Piper canonical 계약을 강제하는 얇은 wrapper다."""

    def __init__(
        self,
        policy: PolicyProtocol,
        metadata: Mapping[str, Any],
        *,
        expected_prompt: str,
    ) -> None:
        """원본 policy, server metadata, 단일 task prompt를 저장한다."""

        if not isinstance(expected_prompt, str) or not expected_prompt.strip():
            raise ValueError("expected_prompt는 비어 있지 않은 문자열이어야 합니다.")
        self._policy = policy
        self._expected_prompt = expected_prompt.strip()
        merged_metadata = dict(policy.metadata or {})
        merged_metadata.update(metadata)
        self._metadata = merged_metadata

    @property
    def metadata(self) -> Mapping[str, Any]:
        """OpenPI 기본값과 Piper/RoMaLab 계약을 합친 metadata를 반환한다."""

        return dict(self._metadata)

    def infer(self, observation: Mapping[str, Any]) -> Mapping[str, Any]:
        """입력을 검증하고 OpenPI가 만든 `(50, 7)` absolute action만 통과시킨다."""

        validated_observation = validate_canonical_observation(observation)
        if validated_observation["prompt"] != self._expected_prompt:
            raise ValueError(
                "요청 prompt가 이 단일-task checkpoint의 설정과 다릅니다: "
                f"expected={self._expected_prompt!r}, "
                f"actual={validated_observation['prompt']!r}"
            )
        result = self._policy.infer(validated_observation)
        return validate_policy_output(result)


def require_jax_gpu_backend(
    backend_resolver: Callable[[], str] | None = None,
) -> str:
    """실제 weight 복원 전에 JAX가 GPU backend를 선택했는지 확인한다."""

    if backend_resolver is None:
        # JAX import와 backend 초기화는 실제 serve 경로에서만 수행한다.
        import jax

        backend_resolver = jax.default_backend
    backend = str(backend_resolver())
    if backend != "gpu":
        raise RuntimeError(
            "Piper π0 추론에는 JAX GPU backend가 필요합니다: "
            f"actual={backend!r}"
        )
    return backend


def build_policy_metadata(
    settings: Pi0InferenceSettings,
    checkpoint: SelectedCheckpoint,
) -> dict[str, Any]:
    """client가 checkpoint와 ROS2 계약을 확인할 self-describing metadata를 만든다."""

    metadata = build_romalab_policy_metadata()
    metadata.update(
        {
            "schema_version": POLICY_METADATA_SCHEMA_VERSION,
            "model_type": "pi0",
            "config_name": settings.checkpoint.config_name,
            "run_name": settings.checkpoint.run_name,
            "checkpoint_step": checkpoint.step,
            "asset_id": checkpoint.asset_id,
            "norm_stats_sha256": checkpoint.norm_stats_sha256,
            "prompt": settings.policy.prompt,
            "num_inference_steps": settings.policy.num_inference_steps,
        }
    )
    return metadata


def build_inference_train_config(
    settings: Pi0InferenceSettings,
    checkpoint: SelectedCheckpoint,
) -> Any:
    """학습과 같은 π0 구조를 checkpoint 내부 normalization 자산으로 재구성한다."""

    # JAX/OpenPI heavy import는 실제 policy load 시점까지 의도적으로 지연한다.
    from openpi.models import model as model_api
    from openpi.training import config as training_config

    from piper_vla.training.data import PiperDataConfigFactory

    official_config = training_config.get_config(OFFICIAL_PI0_LORA_CONFIG_NAME)
    model_config = official_config.model
    if model_config.model_type is not model_api.ModelType.PI0:
        raise ValueError(f"π0가 아닌 official profile입니다: {model_config.model_type}")
    if getattr(model_config, "pi05", False):
        raise ValueError("현재 inference server는 π0.5가 아니라 π0 전용입니다.")
    if model_config.action_horizon != PI0_ACTION_HORIZON:
        raise ValueError(f"π0 action horizon이 다릅니다: {model_config.action_horizon}")
    if model_config.action_dim != PI0_MODEL_ACTION_DIM:
        raise ValueError(f"π0 action dimension이 다릅니다: {model_config.action_dim}")

    checkpoint_assets_dir = checkpoint.step_dir / "assets"
    data_factory = PiperDataConfigFactory(
        repo_id=checkpoint.asset_id,
        assets=training_config.AssetsConfig(
            assets_dir=str(checkpoint_assets_dir),
            asset_id=checkpoint.asset_id,
        ),
    )
    return dataclasses.replace(
        official_config,
        name=settings.checkpoint.config_name,
        exp_name=settings.checkpoint.run_name,
        data=data_factory,
        assets_base_dir=str(checkpoint.step_dir),
        checkpoint_base_dir=str(settings.checkpoint.runs_root),
        policy_metadata=build_policy_metadata(settings, checkpoint),
    )


def create_piper_policy(
    settings: Pi0InferenceSettings,
    checkpoint: SelectedCheckpoint,
    *,
    policy_factory: Callable[..., PolicyProtocol] | None = None,
) -> ValidatedPiperPolicy:
    """숫자 step의 params와 내장 norm stats로 검증 wrapper가 적용된 policy를 만든다."""

    train_config = build_inference_train_config(settings, checkpoint)
    if policy_factory is None:
        # 모델 restore를 수행하는 import는 실제 serve 경로에서만 실행한다.
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


def create_websocket_server(
    policy: PolicyProtocol,
    settings: Pi0InferenceSettings,
    *,
    server_factory: Callable[..., WebsocketServerProtocol] | None = None,
) -> WebsocketServerProtocol:
    """policy를 설정된 host와 port에 bind할 OpenPI WebSocket server를 만든다."""

    if server_factory is None:
        from openpi.serving import websocket_policy_server

        server_factory = websocket_policy_server.WebsocketPolicyServer
    return server_factory(
        policy=policy,
        host=settings.server.host,
        port=settings.server.port,
        metadata=dict(policy.metadata),
    )


def serve_piper_policy(
    settings: Pi0InferenceSettings,
    checkpoint: SelectedCheckpoint,
) -> None:
    """Piper π0 policy를 복원하고 WebSocket 요청을 종료할 때까지 처리한다."""

    runtime = PolicyServerRuntime(
        policy=create_piper_policy(settings, checkpoint),
        checkpoint=checkpoint,
    )
    server = create_websocket_server(runtime.policy, settings)
    server.serve_forever()
