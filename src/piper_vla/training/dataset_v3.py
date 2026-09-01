"""Production LeRobot v3 dataset adapter shared by π0 and π0.5.

This module reads the original LeRobot v3 Parquet/MP4 structure without
rewriting it to LeRobot v2.1.

The adapter returns a model-neutral Piper sample and always decodes the real
camera frames. JAX, normalization, delta-action conversion, and model-specific
transforms belong elsewhere.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import SupportsIndex

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

# LeRobot 영상 유틸리티를 불러올 때 torchvision 0.22~0.24 전환 경고만 숨긴다.
# 다른 UserWarning은 그대로 표시하여 실제 문제를 놓치지 않도록 한다.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=(
            r"The video decoding and encoding capabilities of torchvision are "
            r"deprecated from version 0\.22 and will be removed in version 0\.24\."
        ),
        category=UserWarning,
        module=r"^torchvision\.io\._video_deprecation_warning$",
    )
    from lerobot.common.datasets.video_utils import decode_video_frames


# ---------------------------------------------------------------------------
# 작업공간 경로
# ---------------------------------------------------------------------------

# 이 모듈(dataset_v3.py)이 들어 있는 디렉터리의 절대 경로다.
MODULE_DIR = Path(__file__).resolve().parent
# 저장소 루트 경로다. 현재 배치에서는 ``<workspace>/src/piper_vla``의 두 단계 위다.
WORKSPACE_ROOT = MODULE_DIR.parents[2]
# 데이터셋과 캐시를 모아 두는 ``<workspace>/data`` 경로다.
DATA_ROOT = WORKSPACE_ROOT / "data"

# LeRobot v3 데이터셋의 기본 절대 경로다. ``PIPER_V3_DATASET_ROOT`` 환경 변수가
# 있으면 그 경로를 사용하고, 없으면 workspace 내부의 아래 시나리오 경로를 사용한다.
DEFAULT_DATASET_ROOT = Path(
    os.environ.get(
        "PIPER_V3_DATASET_ROOT",
        str(
            DATA_ROOT
            / "datasets"
            / "pick_green_to_orange"
            / "background_400_0818_v3"
        ),
    )
).expanduser()


# ---------------------------------------------------------------------------
# LeRobot v3 내부 경로
# ---------------------------------------------------------------------------

# 데이터셋 루트를 기준으로 한 버전, FPS, feature 명세 파일의 상대 경로다.
INFO_REL_PATH = Path("meta/info.json")
# 데이터셋 루트를 기준으로 한 task index와 언어 지시문 Parquet의 상대 경로다.
TASKS_REL_PATH = Path("meta/tasks.parquet")

# 모든 episode metadata Parquet shard를 찾는 데이터셋 루트 기준 glob이다.
EPISODES_GLOB = "meta/episodes/chunk-*/file-*.parquet"
# 모든 frame data Parquet shard를 찾는 데이터셋 루트 기준 glob이다.
DATA_GLOB = "data/chunk-*/file-*.parquet"


# ---------------------------------------------------------------------------
# 원본 데이터셋 키
# ---------------------------------------------------------------------------

# Parquet에 저장된 7차원 Piper 목표 action feature의 원본 키다.
SOURCE_ACTION_KEY = "action"
# Parquet에 저장된 7차원 Piper 관절·그리퍼 상태 feature의 원본 키다.
SOURCE_STATE_KEY = "observation.state"
# episode 시작부터의 frame 시각(초)을 나타내는 원본 키다.
SOURCE_TIMESTAMP_KEY = "timestamp"
# 현재 episode 안에서 0부터 시작하는 frame 번호의 원본 키다.
SOURCE_FRAME_INDEX_KEY = "frame_index"
# frame이 속한 episode 번호의 원본 키다.
SOURCE_EPISODE_INDEX_KEY = "episode_index"
# 전체 데이터셋에서 0부터 이어지는 frame 번호의 원본 키다.
SOURCE_GLOBAL_INDEX_KEY = "index"
# frame에 연결된 언어 task 번호의 원본 키다.
SOURCE_TASK_INDEX_KEY = "task_index"

# 고정형 3인칭 카메라 영상 feature의 원본 키다.
SOURCE_THIRD_PERSON_KEY = "observation.images.third_person"
# 로봇 손목 카메라 영상 feature의 원본 키다.
SOURCE_WRIST_KEY = "observation.images.wrist"

# 어댑터가 필수로 읽는 카메라 키의 순서다: 3인칭 카메라, 손목 카메라.
SOURCE_CAMERA_KEYS = (
    SOURCE_THIRD_PERSON_KEY,
    SOURCE_WRIST_KEY,
)


# ---------------------------------------------------------------------------
# Piper/OpenPI 표준 경계 키
# ---------------------------------------------------------------------------

# OpenPI 입력 경계에서 사용하는 3인칭 RGB image 키다.
CANONICAL_IMAGE_KEY = "observation/image"
# OpenPI 입력 경계에서 사용하는 손목 RGB image 키다.
CANONICAL_WRIST_IMAGE_KEY = "observation/wrist_image"
# OpenPI 입력 경계에서 사용하는 Piper 상태 벡터 키다.
CANONICAL_STATE_KEY = "observation/state"
# OpenPI 입력 경계에서 사용하는 future action chunk 키다.
CANONICAL_ACTION_KEY = "actions"
# OpenPI 입력 경계에서 사용하는 언어 지시문 키다.
CANONICAL_PROMPT_KEY = "prompt"

# 각 원본 카메라 feature를 OpenPI 표준 image 키로 바꾸는 매핑이다.
SOURCE_TO_CANONICAL_CAMERA = {
    SOURCE_THIRD_PERSON_KEY: CANONICAL_IMAGE_KEY,
    SOURCE_WRIST_KEY: CANONICAL_WRIST_IMAGE_KEY,
}


# ---------------------------------------------------------------------------
# Piper 스키마
# ---------------------------------------------------------------------------

# Piper 벡터 차원 수다: 관절 6개와 그리퍼 1개를 합친 7차원이다.
PIPER_DIM = 7

# state 벡터 각 축의 고정 순서다. 관절 1~6 뒤에 그리퍼 위치가 온다.
STATE_NAMES = (
    "joint_1.pos",
    "joint_2.pos",
    "joint_3.pos",
    "joint_4.pos",
    "joint_5.pos",
    "joint_6.pos",
    "gripper.pos",
)

# action 벡터의 축 순서는 state 벡터와 같다.
ACTION_NAMES = STATE_NAMES

# 이 어댑터가 허용하는 LeRobot 데이터셋 codebase version이다.
EXPECTED_CODEBASE_VERSION = "v3.0"
# 데이터셋의 예상 sampling frequency다. 단위는 Hz(frame/s)다.
EXPECTED_FPS = 20
# 디코딩된 RGB 영상의 예상 shape다. 순서는 (height, width, channels)다.
EXPECTED_IMAGE_SHAPE = (480, 640, 3)

# 각 관절 위치에 허용하는 절댓값 상한이다. 단위는 radian이다.
PIPER_JOINT_ABS_LIMIT_RAD = 2 * np.pi
# 그리퍼 위치의 허용 최솟값이다. 단위는 meter다.
PIPER_GRIPPER_MIN_M = 0.0
# 그리퍼 위치의 허용 최댓값이다. 단위는 meter다.
PIPER_GRIPPER_MAX_M = 0.085
# 그리퍼 범위 검증에서 부동소수점 오차를 허용하는 여유값이다. 단위는 meter다.
PIPER_GRIPPER_TOLERANCE_M = 1e-4


# ---------------------------------------------------------------------------
# 어댑터 기본값
# ---------------------------------------------------------------------------

# 한 sample이 반환하는 action chunk 길이다. 20 Hz 기준 50 step은 2.5초다.
DEFAULT_ACTION_HORIZON = 50
# 공유 MP4에서 RGB frame을 읽을 때 기본으로 사용하는 decoder backend다.
DEFAULT_VIDEO_BACKEND = "pyav"
# 요청 timestamp와 실제 디코딩 frame timestamp 사이의 허용 오차다. 단위는 초다.
DEFAULT_VIDEO_TOLERANCE_S = 1e-4


# ---------------------------------------------------------------------------
# Episode metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoWindow:
    """공유 LeRobot v3 MP4 안에서 한 episode가 위치한 구간을 나타낸다."""

    chunk_index: int
    file_index: int
    from_timestamp: float
    to_timestamp: float


@dataclass(frozen=True)
class EpisodeWindow:
    """한 episode의 전역 frame 범위와 video 범위를 나타낸다."""

    episode_index: int
    start: int
    stop: int
    length: int
    tasks: tuple[str, ...]
    videos: dict[str, VideoWindow]


# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------


def _read_parquet_files(
    paths: list[Path],
    *,
    label: str,
) -> pa.Table:
    """정렬된 LeRobot v3 Parquet shard를 읽어 하나의 table로 합친다."""

    if not paths:
        raise FileNotFoundError(f"No {label} Parquet files were found")

    tables = [pq.read_table(path) for path in paths]

    if len(tables) == 1:
        return tables[0]

    return pa.concat_tables(tables)


def _scalar_column(
    table: pa.Table,
    name: str,
    dtype: np.dtype,
) -> np.ndarray:
    """Arrow scalar column을 NumPy 배열로 변환한다."""

    if name not in table.column_names:
        raise ValueError(f"Missing Parquet column: {name}")

    column = table[name].combine_chunks()

    return np.asarray(
        column.to_numpy(zero_copy_only=False),
        dtype=dtype,
    )


def _vector_column(
    table: pa.Table,
    name: str,
    width: int,
) -> np.ndarray:
    """Arrow list column을 float32 [N, width] 배열로 변환한다."""

    if name not in table.column_names:
        raise ValueError(f"Missing Parquet column: {name}")

    column = table[name].combine_chunks()

    if pa.types.is_fixed_size_list(column.type):
        if column.type.list_size != width:
            raise ValueError(
                f"{name} list width must be {width}, "
                f"got {column.type.list_size}"
            )

    elif pa.types.is_list(column.type) or pa.types.is_large_list(column.type):
        offsets = np.asarray(
            column.offsets.to_numpy(zero_copy_only=False),
            dtype=np.int64,
        )
        lengths = np.diff(offsets)

        if not np.all(lengths == width):
            raise ValueError(
                f"{name} contains a vector whose width is not {width}"
            )

    else:
        raise TypeError(
            f"{name} must be an Arrow list column, got {column.type}"
        )

    flat_values = np.asarray(
        column.values.to_numpy(zero_copy_only=False),
        dtype=np.float32,
    )

    expected_values = table.num_rows * width

    if flat_values.size != expected_values:
        raise ValueError(
            f"{name} contains {flat_values.size} values; "
            f"expected {expected_values}"
        )

    return flat_values.reshape(table.num_rows, width)


# ---------------------------------------------------------------------------
# Dataset adapter
# ---------------------------------------------------------------------------


class PiperV3Dataset:
    """LeRobot v3 Piper dataset을 OpenPI가 사용하는 표준 sample로 읽는다."""

    def __init__(
        self,
        root: str | Path = DEFAULT_DATASET_ROOT,
        *,
        action_horizon: int = DEFAULT_ACTION_HORIZON,
        video_backend: str = DEFAULT_VIDEO_BACKEND,
        video_tolerance_s: float = DEFAULT_VIDEO_TOLERANCE_S,
        validate_samples: bool = False,
    ) -> None:
        """dataset을 열고 metadata, frame, episode, video 계약을 검증한다."""

        self.root = Path(root).expanduser().resolve()
        self.action_horizon = int(action_horizon)
        self.video_backend = video_backend
        self.video_tolerance_s = float(video_tolerance_s)
        self.validate_samples = bool(validate_samples)

        if self.action_horizon <= 0:
            raise ValueError("action_horizon must be positive")

        self.info = self._load_info()
        self._validate_info()

        self._load_frame_data()
        self._tasks = self._load_tasks()
        self._episodes = self._load_episodes()

        self._validate_frame_data()
        self._validate_episode_ranges()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _load_info(self) -> dict:
        """meta/info.json을 읽어 dataset 기본 정보를 반환한다."""

        info_path = self.root / INFO_REL_PATH

        if not info_path.is_file():
            raise FileNotFoundError(
                f"Missing LeRobot info.json: {info_path}"
            )

        return json.loads(info_path.read_text())

    def _validate_info(self) -> None:
        """dataset version, FPS, feature 구조가 Piper 계약과 맞는지 검사한다."""

        version = self.info.get("codebase_version")

        if version != EXPECTED_CODEBASE_VERSION:
            raise ValueError(
                f"Expected LeRobot {EXPECTED_CODEBASE_VERSION}, "
                f"got {version!r}"
            )

        fps = int(self.info.get("fps", -1))

        if fps != EXPECTED_FPS:
            raise ValueError(
                f"Expected {EXPECTED_FPS} FPS, got {fps}"
            )

        features = self.info.get("features", {})

        self._validate_vector_feature(
            features=features,
            key=SOURCE_STATE_KEY,
            expected_names=STATE_NAMES,
        )

        self._validate_vector_feature(
            features=features,
            key=SOURCE_ACTION_KEY,
            expected_names=ACTION_NAMES,
        )

        for camera_key in SOURCE_CAMERA_KEYS:
            feature = features.get(camera_key)

            if feature is None:
                raise ValueError(
                    f"Missing camera feature: {camera_key}"
                )

            if feature.get("dtype") != "video":
                raise ValueError(
                    f"{camera_key} must be a video feature"
                )

            shape = tuple(feature.get("shape") or ())

            if shape != EXPECTED_IMAGE_SHAPE:
                raise ValueError(
                    f"{camera_key} must have shape "
                    f"{EXPECTED_IMAGE_SHAPE}, got {shape}"
                )

    @staticmethod
    def _validate_vector_feature(
        *,
        features: dict,
        key: str,
        expected_names: tuple[str, ...],
    ) -> None:
        """state 또는 action vector feature의 dtype, shape, 축 이름을 검사한다."""

        feature = features.get(key)

        if feature is None:
            raise ValueError(f"Missing feature: {key}")

        if feature.get("dtype") != "float32":
            raise ValueError(
                f"{key} must be float32, "
                f"got {feature.get('dtype')!r}"
            )

        if feature.get("shape") != [PIPER_DIM]:
            raise ValueError(
                f"{key} must have shape [{PIPER_DIM}]"
            )

        names = tuple(feature.get("names") or ())

        if names != expected_names:
            raise ValueError(
                f"Unexpected {key} dimension order: {names}"
            )

    def _load_frame_data(self) -> None:
        """전체 frame Parquet shard에서 state, action, index를 읽는다."""

        data_paths = sorted(self.root.glob(DATA_GLOB))

        table = _read_parquet_files(
            data_paths,
            label="frame data",
        )

        self._actions = _vector_column(
            table,
            SOURCE_ACTION_KEY,
            PIPER_DIM,
        )

        self._states = _vector_column(
            table,
            SOURCE_STATE_KEY,
            PIPER_DIM,
        )

        self._timestamps = _scalar_column(
            table,
            SOURCE_TIMESTAMP_KEY,
            np.float32,
        )

        self._frame_indices = _scalar_column(
            table,
            SOURCE_FRAME_INDEX_KEY,
            np.int64,
        )

        self._episode_indices = _scalar_column(
            table,
            SOURCE_EPISODE_INDEX_KEY,
            np.int64,
        )

        self._task_indices = _scalar_column(
            table,
            SOURCE_TASK_INDEX_KEY,
            np.int64,
        )

        if SOURCE_GLOBAL_INDEX_KEY in table.column_names:
            self._global_indices = _scalar_column(
                table,
                SOURCE_GLOBAL_INDEX_KEY,
                np.int64,
            )
        else:
            self._global_indices = np.arange(
                table.num_rows,
                dtype=np.int64,
            )

    def _load_tasks(self) -> dict[int, str]:
        """task metadata를 읽고 task index와 prompt 대응표를 만든다."""

        tasks_path = self.root / TASKS_REL_PATH

        if not tasks_path.is_file():
            raise FileNotFoundError(
                f"Missing task metadata: {tasks_path}"
            )

        table = pq.read_table(tasks_path)

        task_indices = _scalar_column(
            table,
            SOURCE_TASK_INDEX_KEY,
            np.int64,
        )

        if "task" not in table.column_names:
            raise ValueError(
                "meta/tasks.parquet is missing the 'task' column"
            )

        task_strings = table["task"].combine_chunks().to_pylist()

        tasks = {
            int(task_index): str(task)
            for task_index, task in zip(
                task_indices,
                task_strings,
                strict=True,
            )
        }

        expected_tasks = int(self.info.get("total_tasks", -1))

        if len(tasks) != expected_tasks:
            raise ValueError(
                f"info.json reports {expected_tasks} tasks, "
                f"tasks.parquet contains {len(tasks)}"
            )

        for task_index, task in tasks.items():
            if not task.strip():
                raise ValueError(
                    f"Task {task_index} is empty"
                )

        return tasks

    def _load_episodes(self) -> dict[int, EpisodeWindow]:
        """episode metadata를 읽고 각 episode의 frame·video 범위를 만든다."""

        episode_paths = sorted(
            self.root.glob(EPISODES_GLOB)
        )

        table = _read_parquet_files(
            episode_paths,
            label="episode metadata",
        )

        required_columns = (
            "episode_index",
            "length",
            "tasks",
            "dataset_from_index",
            "dataset_to_index",
        )

        for column_name in required_columns:
            if column_name not in table.column_names:
                raise ValueError(
                    "Episode metadata is missing column: "
                    f"{column_name}"
                )

        episodes: dict[int, EpisodeWindow] = {}

        for row_index in range(table.num_rows):
            episode_index = int(
                table["episode_index"][row_index].as_py()
            )

            if episode_index in episodes:
                raise ValueError(
                    f"Duplicate episode index: {episode_index}"
                )

            start = int(
                table["dataset_from_index"][row_index].as_py()
            )

            stop = int(
                table["dataset_to_index"][row_index].as_py()
            )

            length = int(
                table["length"][row_index].as_py()
            )

            tasks_value = (
                table["tasks"][row_index].as_py() or []
            )

            episode_tasks = tuple(
                str(task)
                for task in tasks_value
            )

            videos: dict[str, VideoWindow] = {}

            for camera_key in SOURCE_CAMERA_KEYS:
                prefix = f"videos/{camera_key}"

                camera_columns = {
                    "chunk_index": f"{prefix}/chunk_index",
                    "file_index": f"{prefix}/file_index",
                    "from_timestamp": (
                        f"{prefix}/from_timestamp"
                    ),
                    "to_timestamp": (
                        f"{prefix}/to_timestamp"
                    ),
                }

                for column_name in camera_columns.values():
                    if column_name not in table.column_names:
                        raise ValueError(
                            "Episode metadata is missing column: "
                            f"{column_name}"
                        )

                videos[camera_key] = VideoWindow(
                    chunk_index=int(
                        table[
                            camera_columns["chunk_index"]
                        ][row_index].as_py()
                    ),
                    file_index=int(
                        table[
                            camera_columns["file_index"]
                        ][row_index].as_py()
                    ),
                    from_timestamp=float(
                        table[
                            camera_columns["from_timestamp"]
                        ][row_index].as_py()
                    ),
                    to_timestamp=float(
                        table[
                            camera_columns["to_timestamp"]
                        ][row_index].as_py()
                    ),
                )

            episodes[episode_index] = EpisodeWindow(
                episode_index=episode_index,
                start=start,
                stop=stop,
                length=length,
                tasks=episode_tasks,
                videos=videos,
            )

        expected_episodes = int(
            self.info.get("total_episodes", -1)
        )

        if len(episodes) != expected_episodes:
            raise ValueError(
                f"info.json reports {expected_episodes} episodes, "
                f"episode metadata contains {len(episodes)}"
            )

        return episodes

    # ------------------------------------------------------------------
    # Dataset validation
    # ------------------------------------------------------------------

    def _validate_frame_data(self) -> None:
        """전역 frame index와 episode index가 끊김 없이 일치하는지 검사한다."""

        expected_frames = int(
            self.info.get("total_frames", -1)
        )

        if len(self._actions) != expected_frames:
            raise ValueError(
                f"info.json reports {expected_frames} frames, "
                f"Parquet contains {len(self._actions)}"
            )

        arrays = (
            self._states,
            self._timestamps,
            self._frame_indices,
            self._episode_indices,
            self._task_indices,
            self._global_indices,
        )

        for array in arrays:
            if len(array) != expected_frames:
                raise ValueError(
                    "Frame-level Parquet columns have "
                    "different lengths"
                )

        expected_indices = np.arange(
            expected_frames,
            dtype=np.int64,
        )

        if not np.array_equal(
            self._global_indices,
            expected_indices,
        ):
            raise ValueError(
                "Global dataset index is not contiguous from zero"
            )

        if not np.isfinite(self._states).all():
            raise ValueError(
                "observation.state contains NaN or Inf"
            )

        if not np.isfinite(self._actions).all():
            raise ValueError(
                "action contains NaN or Inf"
            )

        self._validate_piper_values(
            "observation.state",
            self._states,
        )

        self._validate_piper_values(
            "action",
            self._actions,
        )

        unknown_tasks = set(
            np.unique(self._task_indices).tolist()
        ) - set(self._tasks)

        if unknown_tasks:
            raise ValueError(
                f"Unknown task indices in frame data: "
                f"{sorted(unknown_tasks)}"
            )

    @staticmethod
    def _validate_piper_values(
        name: str,
        values: np.ndarray,
    ) -> None:
        """Piper 관절각과 gripper 값이 허용 범위 안인지 검사한다."""

        joints = values[..., :6]
        gripper = values[..., 6]

        if np.any(
            np.abs(joints) > PIPER_JOINT_ABS_LIMIT_RAD
        ):
            raise ValueError(
                f"{name} contains a joint outside "
                "+/-2*pi radians"
            )

        lower = (
            PIPER_GRIPPER_MIN_M
            - PIPER_GRIPPER_TOLERANCE_M
        )

        upper = (
            PIPER_GRIPPER_MAX_M
            + PIPER_GRIPPER_TOLERANCE_M
        )

        if np.any(gripper < lower) or np.any(gripper > upper):
            raise ValueError(
                f"{name} gripper must be in meters "
                f"within [{PIPER_GRIPPER_MIN_M}, "
                f"{PIPER_GRIPPER_MAX_M}]"
            )

    def _validate_episode_ranges(self) -> None:
        """episode frame 범위가 전체 dataset을 중복이나 빈틈 없이 덮는지 검사한다."""

        cursor = 0

        for episode_index in sorted(self._episodes):
            episode = self._episodes[episode_index]

            if episode.start != cursor:
                raise ValueError(
                    f"Episode {episode_index} starts at "
                    f"{episode.start}; expected {cursor}"
                )

            if episode.stop <= episode.start:
                raise ValueError(
                    f"Episode {episode_index} has an "
                    "empty or reversed range"
                )

            if episode.stop - episode.start != episode.length:
                raise ValueError(
                    f"Episode {episode_index} range length "
                    f"does not match metadata length"
                )

            row_episode_indices = self._episode_indices[
                episode.start : episode.stop
            ]

            if not np.all(
                row_episode_indices == episode_index
            ):
                raise ValueError(
                    f"Frame rows do not match episode "
                    f"{episode_index} metadata"
                )

            cursor = episode.stop

        if cursor != len(self):
            raise ValueError(
                f"Episode ranges end at {cursor}; "
                f"dataset contains {len(self)} frames"
            )

    # ------------------------------------------------------------------
    # Public dataset information
    # ------------------------------------------------------------------

    @property
    def fps(self) -> int:
        """dataset의 frame rate를 반환한다."""

        return int(self.info["fps"])

    @property
    def num_episodes(self) -> int:
        """dataset에 포함된 episode 수를 반환한다."""

        return len(self._episodes)

    @property
    def episode_indices(self) -> tuple[int, ...]:
        """정렬된 episode index 전체를 반환한다."""

        return tuple(sorted(self._episodes))

    def __len__(self) -> int:
        """학습에서 선택할 수 있는 전체 frame 수를 반환한다."""

        return len(self._actions)

    def summary(self) -> dict:
        """dataset 크기와 주요 계약을 사람이 읽기 쉬운 dict로 반환한다."""

        return {
            "root": str(self.root),
            "codebase_version": self.info["codebase_version"],
            "fps": self.fps,
            "num_frames": len(self),
            "num_episodes": self.num_episodes,
            "num_tasks": len(self._tasks),
            "action_horizon": self.action_horizon,
            "validate_samples": self.validate_samples,
        }

    # ------------------------------------------------------------------
    # Index and episode helpers
    # ------------------------------------------------------------------

    def _normalize_index(
        self,
        index: SupportsIndex,
    ) -> int:
        """음수 index를 포함한 입력 index를 유효한 전역 frame index로 바꾼다."""

        value = index.__index__()

        if value < 0:
            value += len(self)

        if value < 0 or value >= len(self):
            raise IndexError(value)

        return value

    def episode_bounds(
        self,
        episode_index: int,
    ) -> tuple[int, int]:
        """지정한 episode의 시작과 끝 frame 범위를 반환한다."""

        episode = self._episodes[int(episode_index)]

        return episode.start, episode.stop

    def action_chunk(
        self,
        index: SupportsIndex,
    ) -> tuple[np.ndarray, np.ndarray]:
        """현재 frame부터 horizon 길이의 7차원 action과 padding mask를 반환한다."""

        index = self._normalize_index(index)

        episode_index = int(
            self._episode_indices[index]
        )

        episode = self._episodes[episode_index]

        requested_indices = (
            index
            + np.arange(
                self.action_horizon,
                dtype=np.int64,
            )
        )

        selected_indices = np.clip(
            requested_indices,
            episode.start,
            episode.stop - 1,
        )

        is_pad = (
            (requested_indices < episode.start)
            | (requested_indices >= episode.stop)
        )

        actions = self._actions[
            selected_indices
        ].copy()

        return actions, is_pad


    def numeric_batch(
        self,
        begin: int,
        end: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """영상 디코딩 없이 연속 frame의 state와 episode-clipped action chunk를 반환한다."""

        begin = int(begin)
        end = int(end)

        if begin < 0 or end > len(self) or begin >= end:
            raise IndexError(
                "numeric batch 범위가 올바르지 않습니다: "
                f"begin={begin}, end={end}, length={len(self)}"
            )

        current_indices = np.arange(begin, end, dtype=np.int64)
        episode_indices = self._episode_indices[begin:end]
        episode_last_indices = np.fromiter(
            (
                self._episodes[int(episode_index)].stop - 1
                for episode_index in episode_indices
            ),
            dtype=np.int64,
            count=end - begin,
        )
        future_indices = np.minimum(
            current_indices[:, None]
            + np.arange(self.action_horizon, dtype=np.int64)[None, :],
            episode_last_indices[:, None],
        )

        return (
            self._states[begin:end].copy(),
            self._actions[future_indices].copy(),
        )

    # ------------------------------------------------------------------
    # Video handling
    # ------------------------------------------------------------------

    def video_query(
        self,
        index: SupportsIndex,
    ) -> dict[str, tuple[Path, float]]:
        """각 카메라 영상을 독립적으로 찾을 수 있는 video timestamp query를 만든다."""

        index = self._normalize_index(index)

        episode_index = int(
            self._episode_indices[index]
        )

        episode = self._episodes[episode_index]
        relative_timestamp = float(
            self._timestamps[index]
        )

        video_path_template = self.info.get(
            "video_path"
        )

        if not video_path_template:
            raise ValueError(
                "info.json does not define video_path"
            )

        queries: dict[str, tuple[Path, float]] = {}

        for camera_key in SOURCE_CAMERA_KEYS:
            window = episode.videos[camera_key]

            absolute_timestamp = (
                window.from_timestamp
                + relative_timestamp
            )

            if (
                absolute_timestamp
                < window.from_timestamp
                - self.video_tolerance_s
            ):
                raise ValueError(
                    f"{camera_key} query precedes "
                    f"episode {episode_index} video window"
                )

            if (
                absolute_timestamp
                >= window.to_timestamp
                + self.video_tolerance_s
            ):
                raise ValueError(
                    f"{camera_key} query exceeds "
                    f"episode {episode_index} video window"
                )

            relative_path = video_path_template.format(
                video_key=camera_key,
                chunk_index=window.chunk_index,
                file_index=window.file_index,
            )

            video_path = self.root / relative_path

            if not video_path.is_file():
                raise FileNotFoundError(
                    f"Missing video file: {video_path}"
                )

            queries[camera_key] = (
                video_path,
                absolute_timestamp,
            )

        return queries

    def _decode_image(
        self,
        video_path: Path,
        timestamp: float,
    ) -> np.ndarray:
        # torchvision 0.22~0.24 영상 API 폐기 경고만 decode 호출 동안 숨긴다.
        # 메시지·범주·발생 모듈을 모두 제한하므로 다른 UserWarning은 유지된다.
        """지정한 카메라와 timestamp의 JPEG frame을 RGB 배열로 decode한다."""

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=(
                    r"The video decoding and encoding capabilities of torchvision are "
                    r"deprecated from version 0\.22 and will be removed in version 0\.24\."
                ),
                category=UserWarning,
                module=r"^torchvision\.io\._video_deprecation_warning$",
            )
            frames = decode_video_frames(
                video_path,
                [timestamp],
                self.video_tolerance_s,
                self.video_backend,
            )

        if tuple(frames.shape) != (
            1,
            3,
            EXPECTED_IMAGE_SHAPE[0],
            EXPECTED_IMAGE_SHAPE[1],
        ):
            raise ValueError(
                f"Unexpected decoded video shape: "
                f"{tuple(frames.shape)}"
            )

        chw_image = (
            frames[0]
            .detach()
            .cpu()
            .numpy()
        )

        hwc_image = np.moveaxis(
            chw_image,
            0,
            -1,
        )

        return np.clip(
            np.rint(hwc_image * 255.0),
            0,
            255,
        ).astype(np.uint8)

    # ------------------------------------------------------------------
    # Canonical sample
    # ------------------------------------------------------------------

    def __getitem__(
        self,
        index: SupportsIndex,
    ) -> dict:
        """전역 frame index 하나를 OpenPI 학습용 canonical sample로 변환한다."""

        index = self._normalize_index(index)

        episode_index = int(
            self._episode_indices[index]
        )

        task_index = int(
            self._task_indices[index]
        )

        actions, action_is_pad = self.action_chunk(
            index
        )

        video_queries = self.video_query(index)

        third_person_path, third_person_ts = (
            video_queries[SOURCE_THIRD_PERSON_KEY]
        )

        wrist_path, wrist_ts = (
            video_queries[SOURCE_WRIST_KEY]
        )

        sample = {
            CANONICAL_IMAGE_KEY: self._decode_image(
                third_person_path,
                third_person_ts,
            ),
            CANONICAL_WRIST_IMAGE_KEY: self._decode_image(
                wrist_path,
                wrist_ts,
            ),
            CANONICAL_STATE_KEY: self._states[
                index
            ].copy(),
            CANONICAL_ACTION_KEY: actions,
            CANONICAL_PROMPT_KEY: self._tasks[
                task_index
            ],
            "action_is_pad": action_is_pad,
            "episode_index": np.int64(
                episode_index
            ),
            "frame_index": np.int64(
                self._frame_indices[index]
            ),
            "task_index": np.int64(
                task_index
            ),
            "timestamp": np.float32(
                self._timestamps[index]
            ),
        }

        if self.validate_samples:
            self._validate_sample(sample)

        return sample

    def _validate_sample(
        self,
        sample: dict,
    ) -> None:
        """최종 sample의 key, dtype, shape, 유한값 계약을 검사한다."""

        for image_key in (
            CANONICAL_IMAGE_KEY,
            CANONICAL_WRIST_IMAGE_KEY,
        ):
            image = np.asarray(
                sample[image_key]
            )

            if image.dtype != np.uint8:
                raise TypeError(
                    f"{image_key} must be uint8, "
                    f"got {image.dtype}"
                )

            if image.shape != EXPECTED_IMAGE_SHAPE:
                raise ValueError(
                    f"{image_key} must have shape "
                    f"{EXPECTED_IMAGE_SHAPE}, "
                    f"got {image.shape}"
                )

        state = np.asarray(
            sample[CANONICAL_STATE_KEY]
        )

        actions = np.asarray(
            sample[CANONICAL_ACTION_KEY]
        )

        if state.dtype != np.float32:
            raise TypeError(
                f"state must be float32, "
                f"got {state.dtype}"
            )

        if state.shape != (PIPER_DIM,):
            raise ValueError(
                f"state must have shape ({PIPER_DIM},), "
                f"got {state.shape}"
            )

        if actions.dtype != np.float32:
            raise TypeError(
                f"actions must be float32, "
                f"got {actions.dtype}"
            )

        expected_action_shape = (
            self.action_horizon,
            PIPER_DIM,
        )

        if actions.shape != expected_action_shape:
            raise ValueError(
                f"actions must have shape "
                f"{expected_action_shape}, "
                f"got {actions.shape}"
            )

        action_is_pad = np.asarray(
            sample["action_is_pad"]
        )

        if action_is_pad.dtype != np.bool_:
            raise TypeError(
                "action_is_pad must be bool"
            )

        if action_is_pad.shape != (
            self.action_horizon,
        ):
            raise ValueError(
                "action_is_pad has an invalid shape"
            )

        prompt = sample[
            CANONICAL_PROMPT_KEY
        ]

        if (
            not isinstance(prompt, str)
            or not prompt.strip()
        ):
            raise ValueError(
                "prompt must be a non-empty string"
            )
