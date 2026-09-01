"""RoMaLab 관측과 OpenPI Piper 입출력의 순수 NumPy 계약을 검증한다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from piper_vla.inference import romalab_contract


# OpenPI Piper policy가 받는 canonical key 집합이다.
CANONICAL_OBSERVATION_KEYS = frozenset(
    {
        "observation/image",
        "observation/wrist_image",
        "observation/state",
        "prompt",
    }
)


def _is_real_numeric_dtype(dtype: np.dtype[Any]) -> bool:
    """bool·complex를 제외한 정수 또는 부동소수 dtype인지 확인한다."""

    return bool(
        np.issubdtype(dtype, np.integer) or np.issubdtype(dtype, np.floating)
    )


def _validate_rgb_image(image: Any, *, field_name: str) -> np.ndarray:
    """한 RGB 영상을 480×640 HWC uint8 contiguous 배열로 검증한다."""

    array = np.asarray(image)
    expected_shape = (
        romalab_contract.CAMERA_HEIGHT,
        romalab_contract.CAMERA_WIDTH,
        3,
    )
    if array.shape != expected_shape:
        raise ValueError(
            f"{field_name} shape이 올바르지 않습니다: "
            f"expected={expected_shape}, actual={array.shape}"
        )
    if array.dtype != np.uint8:
        raise TypeError(f"{field_name} dtype은 uint8이어야 합니다: {array.dtype}")
    return np.ascontiguousarray(array)


def decode_rgb_jpeg(encoded: bytes | bytearray | memoryview) -> np.ndarray:
    """ROS CompressedImage JPEG bytes를 검증된 RGB uint8 영상으로 decode한다."""

    if not isinstance(encoded, (bytes, bytearray, memoryview)) or len(encoded) == 0:
        raise TypeError("JPEG payload는 비어 있지 않은 bytes 계열이어야 합니다.")

    # OpenCV는 무거운 선택 의존성이므로 실제 decode 호출 시점에만 import한다.
    import cv2

    buffer = np.frombuffer(encoded, dtype=np.uint8)
    bgr_image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if bgr_image is None:
        raise ValueError("JPEG payload를 decode하지 못했습니다.")
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    return _validate_rgb_image(rgb_image, field_name="decoded RGB image")


def build_canonical_observation(
    third_person_rgb: Any,
    wrist_rgb: Any,
    state: Sequence[float] | np.ndarray,
    prompt: str,
) -> dict[str, Any]:
    """두 RGB 영상과 absolute 7차원 state를 OpenPI 입력 dict로 만든다."""

    third_person = _validate_rgb_image(
        third_person_rgb,
        field_name="observation/image",
    )
    wrist = _validate_rgb_image(
        wrist_rgb,
        field_name="observation/wrist_image",
    )
    state_array = np.asarray(state)
    if state_array.shape != (romalab_contract.ROBOT_DIM,):
        raise ValueError(
            "observation/state shape이 올바르지 않습니다: "
            f"expected=({romalab_contract.ROBOT_DIM},), actual={state_array.shape}"
        )
    if not _is_real_numeric_dtype(state_array.dtype):
        raise TypeError(
            "observation/state은 실수형 정수 또는 부동소수 배열이어야 합니다: "
            f"{state_array.dtype}"
        )
    state_array = np.ascontiguousarray(state_array, dtype=np.float32)
    if not np.isfinite(state_array).all():
        raise ValueError("observation/state에 NaN 또는 Inf가 있습니다.")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt는 비어 있지 않은 문자열이어야 합니다.")

    return {
        "observation/image": third_person,
        "observation/wrist_image": wrist,
        "observation/state": state_array,
        "prompt": prompt.strip(),
    }


def validate_canonical_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """외부 client가 보낸 canonical observation 전체를 다시 검증한다."""

    if not isinstance(observation, Mapping):
        raise TypeError(f"observation은 mapping이어야 합니다: {type(observation).__name__}")
    if set(observation) != set(CANONICAL_OBSERVATION_KEYS):
        raise ValueError(
            "canonical observation key가 올바르지 않습니다: "
            f"expected={sorted(CANONICAL_OBSERVATION_KEYS)}, actual={sorted(observation)}"
        )
    return build_canonical_observation(
        observation["observation/image"],
        observation["observation/wrist_image"],
        observation["observation/state"],
        observation["prompt"],
    )


def validate_policy_output(result: Mapping[str, Any]) -> dict[str, Any]:
    """OpenPI 출력이 유한한 absolute `(50, 7)` action chunk인지 검증한다."""

    if not isinstance(result, Mapping):
        raise TypeError(f"policy 결과는 mapping이어야 합니다: {type(result).__name__}")
    if "actions" not in result:
        raise KeyError("policy 결과에 actions가 없습니다.")
    actions = np.asarray(result["actions"])
    expected_shape = (
        romalab_contract.ACTION_HORIZON,
        romalab_contract.ROBOT_DIM,
    )
    if actions.shape != expected_shape:
        raise ValueError(
            f"policy actions shape이 올바르지 않습니다: "
            f"expected={expected_shape}, actual={actions.shape}"
        )
    if not _is_real_numeric_dtype(actions.dtype):
        raise TypeError(
            "policy actions는 실수형 정수 또는 부동소수 배열이어야 합니다: "
            f"{actions.dtype}"
        )
    actions = np.ascontiguousarray(actions, dtype=np.float32)
    if not np.isfinite(actions).all():
        raise ValueError("policy actions에 NaN 또는 Inf가 있습니다.")

    validated = dict(result)
    validated["actions"] = actions
    return validated
