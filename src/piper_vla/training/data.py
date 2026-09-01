"""Piper LeRobot v3 데이터를 OpenPI π0 학습 입력으로 연결한다."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Iterator, TypeAlias

import jax
import numpy as np
from jax.sharding import Mesh, NamedSharding, PartitionSpec as P
from typing_extensions import override

from openpi import transforms
from openpi.models import model as model_api
from openpi.policies import libero_policy
from openpi.training import config as training_config
from openpi.training import data_loader
from openpi.training import sharding as training_sharding

from piper_vla.training.dataset_v3 import PiperV3Dataset


# Piper의 관절 6축과 그리퍼 1축을 합친 실제 로봇 차원이다.
PIPER_ROBOT_DIM = 7

# absolute action을 delta로 바꾸는 관절 축의 개수다.
PIPER_DELTA_JOINT_DIM = 6

# π0가 한 번에 예측하는 action chunk 길이다.
PI0_ACTION_HORIZON = 50

# π0 내부 state/action 표현의 고정 차원이다.
PI0_MODEL_ACTION_DIM = 32

# π0 image encoder에 들어가는 정사각 영상 크기다.
PI0_IMAGE_SIZE = 224

# π0 tokenizer가 사용하는 최대 prompt token 길이다.
PI0_PROMPT_TOKEN_LENGTH = 48

# Piper 원본 샘플에서 OpenPI가 사용할 canonical key만 남기는 매핑이다.
PIPER_CANONICAL_REPACK = {
    "observation/image": "observation/image",
    "observation/wrist_image": "observation/wrist_image",
    "observation/state": "observation/state",
    "actions": "actions",
    "prompt": "prompt",
}

# 관절 6축만 delta로 변환하고 그리퍼는 absolute 값을 유지하는 마스크다.
PIPER_DELTA_MASK = transforms.make_bool_mask(PIPER_DELTA_JOINT_DIM, -1)

# OpenPI loader가 반환하는 `(Observation, actions)` 묶음의 형식 별칭이다.
TrainingBatch: TypeAlias = tuple[model_api.Observation, jax.Array]


@dataclasses.dataclass(frozen=True)
class PiperDataConfigFactory(training_config.DataConfigFactory):
    """Piper v3 canonical sample을 π0 학습·추론 transform으로 연결한다."""

    # prompt가 비어 있을 때 사용할 선택적 기본 task 문장이다.
    default_prompt: str | None = None

    @override
    def create(
        self,
        assets_dirs: Path,
        model_config: model_api.BaseModelConfig,
    ) -> training_config.DataConfig:
        """저장된 정규화 통계를 포함한 Piper 전용 DataConfig를 생성한다."""

        if model_config.model_type is not model_api.ModelType.PI0:
            raise ValueError(f"현재 데이터 설정은 π0만 지원합니다: {model_config.model_type=}")
        if model_config.action_horizon != PI0_ACTION_HORIZON:
            raise ValueError(
                "Piper adapter와 모델의 action horizon이 다릅니다: "
                f"adapter={PI0_ACTION_HORIZON}, model={model_config.action_horizon}"
            )
        if model_config.action_dim != PI0_MODEL_ACTION_DIM:
            raise ValueError(
                "π0 model action dimension이 예상값과 다릅니다: "
                f"expected={PI0_MODEL_ACTION_DIM}, actual={model_config.action_dim}"
            )

        base_config = self.create_base_config(assets_dirs, model_config)
        validate_norm_stats(base_config.norm_stats)

        repack_transforms = transforms.Group(
            inputs=(transforms.RepackTransform(PIPER_CANONICAL_REPACK),),
        )
        data_transforms = transforms.Group(
            inputs=(
                libero_policy.LiberoInputs(model_type=model_config.model_type),
                transforms.DeltaActions(PIPER_DELTA_MASK),
            ),
            outputs=(
                transforms.AbsoluteActions(PIPER_DELTA_MASK),
                libero_policy.LiberoOutputs(),
            ),
        )

        return dataclasses.replace(
            base_config,
            repack_transforms=repack_transforms,
            data_transforms=data_transforms,
            model_transforms=training_config.ModelTransformFactory(
                default_prompt=self.default_prompt,
            )(model_config),
            use_quantile_norm=False,
            action_sequence_keys=("actions",),
            prompt_from_task=False,
        )


@dataclasses.dataclass(frozen=True)
class TrainingDataBundle:
    """학습 loop가 공유해야 하는 dataset, loader, sharding 객체를 묶는다."""

    # MP4와 Parquet을 직접 읽는 Piper LeRobot v3 dataset이다.
    raw_dataset: PiperV3Dataset

    # 정규화와 robot/model transform을 포함한 OpenPI 데이터 설정이다.
    data_config: training_config.DataConfig

    # checkpoint asset 저장에도 재사용하는 OpenPI JAX loader다.
    loader: data_loader.DataLoaderImpl

    # 학습 batch를 순서대로 공급하는 loader iterator다.
    iterator: Iterator[TrainingBatch]

    # 단일 GPU 학습의 batch/fsdp 축을 정의하는 JAX mesh다.
    mesh: Mesh

    # observation/action batch에 적용하는 JAX sharding이다.
    data_sharding: NamedSharding

    # RNG와 metric처럼 복제할 값에 적용하는 JAX sharding이다.
    replicated_sharding: NamedSharding


def validate_norm_stats(norm_stats: dict[str, Any] | None) -> None:
    """Piper 정규화 통계의 key, 차원, 유한값을 검증한다."""

    if norm_stats is None:
        raise FileNotFoundError("Piper norm_stats.json을 불러오지 못했습니다.")
    if set(norm_stats) != {"state", "actions"}:
        raise ValueError(f"정규화 통계 key가 올바르지 않습니다: {tuple(norm_stats)}")

    for key in ("state", "actions"):
        stats = norm_stats[key]
        for field_name in ("mean", "std", "q01", "q99"):
            field_value = getattr(stats, field_name, None)
            if field_value is None:
                raise ValueError(f"정규화 통계가 누락됐습니다: {key}.{field_name}")
            array = np.asarray(field_value)
            if array.shape != (PIPER_ROBOT_DIM,):
                raise ValueError(
                    f"정규화 통계 shape이 올바르지 않습니다: "
                    f"{key}.{field_name}={array.shape}"
                )
            if not np.isfinite(array).all():
                raise ValueError(f"정규화 통계에 NaN/Inf가 있습니다: {key}.{field_name}")

        if np.any(np.asarray(stats.std) <= 0):
            raise ValueError(f"정규화 표준편차는 양수여야 합니다: {key}.std")
        if np.any(np.asarray(stats.q01) > np.asarray(stats.q99)):
            raise ValueError(f"정규화 quantile 순서가 잘못됐습니다: {key}")


def build_training_data_bundle(
    config: training_config.TrainConfig,
    dataset_root: Path,
    *,
    shuffle: bool,
    seed_offset: int = 0,
    num_batches: int | None = None,
) -> TrainingDataBundle:
    """PiperV3Dataset을 OpenPI transform과 JAX loader에 연결한다."""

    dataset_root = dataset_root.expanduser().resolve()
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"LeRobot v3 dataset 경로가 없습니다: {dataset_root}")
    if jax.process_count() != 1:
        raise RuntimeError(
            "현재 OpenPI loader는 단일 JAX process만 지원합니다: "
            f"process_count={jax.process_count()}"
        )
    if config.batch_size <= 0 or config.batch_size % jax.process_count() != 0:
        raise ValueError(
            "global batch size가 JAX process 수로 나누어져야 합니다: "
            f"batch={config.batch_size}, processes={jax.process_count()}"
        )
    if config.batch_size % jax.device_count() != 0:
        raise ValueError(
            "global batch size가 JAX device 수로 나누어져야 합니다: "
            f"batch={config.batch_size}, devices={jax.device_count()}"
        )
    if seed_offset < 0:
        raise ValueError(f"loader seed offset은 음수가 될 수 없습니다: {seed_offset}")

    raw_dataset = PiperV3Dataset(
        root=dataset_root,
        action_horizon=config.model.action_horizon,
        validate_samples=False,
    )
    data_config = config.data.create(config.assets_dirs, config.model)
    validate_norm_stats(data_config.norm_stats)
    if data_config.use_quantile_norm:
        raise ValueError("π0는 quantile이 아니라 mean/std z-score 정규화를 사용해야 합니다.")

    transformed_dataset = data_loader.transform_dataset(
        raw_dataset,
        data_config,
        skip_norm_stats=False,
    )
    mesh = training_sharding.make_mesh(config.fsdp_devices)
    data_sharding = NamedSharding(mesh, P(training_sharding.DATA_AXIS))
    replicated_sharding = NamedSharding(mesh, P())
    local_batch_size = config.batch_size // jax.process_count()

    inner_loader = data_loader.TorchDataLoader(
        transformed_dataset,
        local_batch_size=local_batch_size,
        sharding=data_sharding,
        shuffle=shuffle,
        sampler=None,
        num_batches=num_batches,
        num_workers=config.num_workers,
        seed=config.seed + seed_offset,
        framework="jax",
    )
    loader = data_loader.DataLoaderImpl(data_config, inner_loader)

    return TrainingDataBundle(
        raw_dataset=raw_dataset,
        data_config=data_config,
        loader=loader,
        iterator=iter(loader),
        mesh=mesh,
        data_sharding=data_sharding,
        replicated_sharding=replicated_sharding,
    )


def validate_training_batch(
    batch: TrainingBatch,
    config: training_config.TrainConfig,
) -> None:
    """실제 JAX batch가 검증된 π0 shape, dtype, mask 계약을 만족하는지 확인한다."""

    observation, actions = batch
    batch_size = config.batch_size
    expected_image_shape = (batch_size, PI0_IMAGE_SIZE, PI0_IMAGE_SIZE, 3)

    if not isinstance(observation, model_api.Observation):
        raise TypeError(f"Observation 형식이 아닙니다: {type(observation)!r}")
    if set(observation.images) != set(model_api.IMAGE_KEYS):
        raise ValueError(f"π0 camera key가 다릅니다: {tuple(observation.images)}")
    if set(observation.image_masks) != set(model_api.IMAGE_KEYS):
        raise ValueError(f"π0 camera mask key가 다릅니다: {tuple(observation.image_masks)}")

    for key in model_api.IMAGE_KEYS:
        image = observation.images[key]
        mask = observation.image_masks[key]
        if image.shape != expected_image_shape or image.dtype != np.float32:
            raise ValueError(f"영상 batch 계약 오류: {key} {image.shape} {image.dtype}")
        if mask.shape != (batch_size,) or mask.dtype != np.bool_:
            raise ValueError(f"영상 mask 계약 오류: {key} {mask.shape} {mask.dtype}")
        image_host = np.asarray(jax.device_get(image))
        if not np.isfinite(image_host).all():
            raise ValueError(f"영상에 NaN/Inf가 있습니다: {key}")
        if image_host.min() < -1.00001 or image_host.max() > 1.00001:
            raise ValueError(f"영상 정규화 범위가 올바르지 않습니다: {key}")

    mask_values = {
        key: bool(np.asarray(jax.device_get(observation.image_masks[key]))[0])
        for key in model_api.IMAGE_KEYS
    }
    expected_masks = {
        "base_0_rgb": True,
        "left_wrist_0_rgb": True,
        "right_wrist_0_rgb": False,
    }
    if mask_values != expected_masks:
        raise ValueError(f"Piper camera mask가 올바르지 않습니다: {mask_values}")

    if observation.state.shape != (batch_size, PI0_MODEL_ACTION_DIM):
        raise ValueError(f"state batch shape 오류: {observation.state.shape}")
    if observation.state.dtype != np.float32:
        raise ValueError(f"state dtype 오류: {observation.state.dtype}")
    if actions.shape != (batch_size, PI0_ACTION_HORIZON, PI0_MODEL_ACTION_DIM):
        raise ValueError(f"action batch shape 오류: {actions.shape}")
    if actions.dtype != np.float32:
        raise ValueError(f"action dtype 오류: {actions.dtype}")
    if observation.tokenized_prompt is None or observation.tokenized_prompt_mask is None:
        raise ValueError("prompt token 또는 prompt mask가 없습니다.")
    if observation.tokenized_prompt.shape != (batch_size, PI0_PROMPT_TOKEN_LENGTH):
        raise ValueError(f"prompt token shape 오류: {observation.tokenized_prompt.shape}")
    if observation.tokenized_prompt_mask.shape != (batch_size, PI0_PROMPT_TOKEN_LENGTH):
        raise ValueError(f"prompt mask shape 오류: {observation.tokenized_prompt_mask.shape}")

    state_host = np.asarray(jax.device_get(observation.state))
    actions_host = np.asarray(jax.device_get(actions))
    if not np.isfinite(state_host).all() or not np.isfinite(actions_host).all():
        raise ValueError("state/action batch에 NaN/Inf가 있습니다.")
    if not np.allclose(state_host[..., PIPER_ROBOT_DIM:], 0.0):
        raise ValueError("state의 7D 이후 padding 값이 0이 아닙니다.")
    if not np.allclose(actions_host[..., PIPER_ROBOT_DIM:], 0.0):
        raise ValueError("action의 7D 이후 padding 값이 0이 아닙니다.")


def next_training_batch(
    bundle: TrainingDataBundle,
    config: training_config.TrainConfig,
    *,
    validate: bool = False,
) -> TrainingBatch:
    """다음 학습 batch를 가져오고 요청된 경우 전체 계약을 검증한다."""

    batch = next(bundle.iterator)
    if validate:
        validate_training_batch(batch, config)
    return batch
