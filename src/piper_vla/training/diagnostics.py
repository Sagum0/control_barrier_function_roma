"""π0 장기 학습의 loss, 처리시간, 메모리, checkpoint 진단을 JSONL로 기록한다."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import resource
import sys
import threading
import time
from typing import Any, Mapping, TextIO, TYPE_CHECKING
import unicodedata
import uuid

import jax
import jax.numpy as jnp

from openpi.training import sharding as training_sharding

from piper_vla.training.data import TrainingBatch, next_training_batch
from piper_vla.training.settings import (
    DEFAULT_PROGRESS_REFRESH_SECONDS,
    MAX_PROGRESS_REFRESH_SECONDS,
    MIN_PROGRESS_REFRESH_SECONDS,
)

if TYPE_CHECKING:
    from piper_vla.training.trainer import TrainingRuntime


# 각 run의 루트에 누적 저장할 구조화 metric 로그 파일 이름이다.
TRAINING_METRICS_FILENAME = "training_metrics.jsonl"

# 이후 schema 변경을 구분할 현재 JSONL record 버전이다.
TRAINING_METRICS_SCHEMA_VERSION = 3

# byte 단위 memory 값을 사람이 읽을 GiB로 바꿀 기준값이다.
GIB = 1024**3

# 넓은 terminal에서도 지나치게 길어지지 않을 progress bar 최대 문자 수다.
MAX_PROGRESS_BAR_WIDTH = 60

# Terminal에서 항상 같은 위치를 덮어쓸 dashboard 행 수다.
DASHBOARD_LINE_COUNT = 5

# 실행 중인 dashboard에서 순서대로 보여줄 ASCII spinner frame이다.
RUNNING_INDICATOR_FRAMES = ("|", "/", "-", "\\")


@dataclasses.dataclass(frozen=True)
class MemorySnapshot:
    """한 sync 지점에서 관측한 JAX GPU와 Python process memory를 보관한다."""

    # JAX allocator가 실제 tensor에 사용 중이라고 보고한 GPU byte다.
    gpu_bytes_in_use: int | None

    # 현재 process에서 관측된 JAX GPU 사용량의 누적 peak byte다.
    gpu_peak_bytes_in_use: int | None

    # JAX allocator가 사용할 수 있다고 보고한 GPU 최대 byte다.
    gpu_bytes_limit: int | None

    # Linux `/proc`에서 읽은 현재 process resident memory byte다.
    host_rss_bytes: int | None

    # process 시작 이후 관측된 host resident memory peak byte다.
    host_peak_rss_bytes: int


@dataclasses.dataclass(frozen=True)
class JsonlMetricLogger:
    """학습 진단 record를 한 줄씩 flush·fsync하여 resume 뒤에도 이어 쓴다."""

    # 현재 run root의 JSONL 파일 절대 경로다.
    path: Path

    def append(self, record: Mapping[str, Any]) -> None:
        """하나의 JSON record를 durable append하고 즉시 디스크에 반영한다."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())

@dataclasses.dataclass
class TerminalProgressReporter:
    """여러 thread가 요청해도 TTY dashboard 출력을 한 번에 하나씩 처리한다."""

    # Progress dashboard를 표시할 terminal stream이다.
    stream: TextIO

    # 이전 단일 행 reporter와의 상태 호환을 위한 dashboard 열림 표시다.
    line_open: bool = False

    # 직전 갱신에서 화면에 그린 dashboard 행 수다.
    rendered_lines: int = 0

    # Terminal 출력 오류 뒤 추가 출력을 영구 중단할지 나타낸다.
    disabled: bool = False

    # Background refresh와 main sync 출력이 섞이지 않도록 보호하는 lock이다.
    _write_lock: threading.Lock = dataclasses.field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def _enabled_unlocked(self) -> bool:
        """호출자가 write lock을 가진 상태에서 TTY 출력 가능 여부를 확인한다."""

        if self.disabled:
            return False
        try:
            return bool(self.stream.isatty())
        except (AttributeError, OSError, ValueError):
            self.disabled = True
            return False

    def enabled(self) -> bool:
        """현재 stream이 cursor 갱신을 지원하는 TTY인지 thread-safe하게 반환한다."""

        with self._write_lock:
            return self._enabled_unlocked()

    def terminal_columns(self, fallback: int = 180) -> int:
        """Dashboard stream 자체의 terminal 폭을 읽고 실패하면 안전한 기본값을 쓴다."""

        if fallback <= 0:
            raise ValueError(f"Terminal fallback 폭은 양수여야 합니다: {fallback}")
        with self._write_lock:
            try:
                return max(os.get_terminal_size(self.stream.fileno()).columns, 1)
            except (AttributeError, OSError, ValueError):
                return fallback

    def update(self, lines: tuple[str, ...] | str) -> None:
        """기존 dashboard를 지우고 새 여러 행을 같은 화면 위치에 직렬화해 표시한다."""

        dashboard_lines = (lines,) if isinstance(lines, str) else tuple(lines)
        if not dashboard_lines:
            return
        with self._write_lock:
            if not self._enabled_unlocked():
                return
            try:
                chunks = ["\r"]
                if self.rendered_lines > 1:
                    chunks.append(f"\x1b[{self.rendered_lines - 1}A")
                for index, line in enumerate(dashboard_lines):
                    chunks.extend(("\x1b[2K", line))
                    if index + 1 < len(dashboard_lines):
                        chunks.append("\r\n")
                self.stream.write("".join(chunks))
                self.stream.flush()
                self.line_open = True
                self.rendered_lines = len(dashboard_lines)
            except (OSError, ValueError):
                self.disabled = True
                self.line_open = False
                self.rendered_lines = 0

    def close(self) -> None:
        """열려 있는 dashboard 아래로 cursor를 한 번 내리고 상태를 안전하게 닫는다."""

        with self._write_lock:
            if not self.line_open:
                return
            try:
                self.stream.write("\r\n")
                self.stream.flush()
            except (OSError, ValueError):
                self.disabled = True
            finally:
                self.line_open = False
                self.rendered_lines = 0


def format_duration(seconds: float | None) -> str:
    """초 단위 시간을 ETA 표시에 맞는 HH:MM:SS 문자열로 바꾼다."""

    if seconds is None or not math.isfinite(seconds):
        return "--:--:--"
    total_seconds = max(int(round(seconds)), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def format_optional_gib(value: int | None) -> str:
    """선택적 byte 값을 짧은 GiB 문자열로 바꾼다."""

    return "n/a" if value is None else f"{value / GIB:.2f}"


def jax_memory_usage_percent(snapshot: MemorySnapshot) -> float | None:
    """JAX allocator 상한 중 현재 tensor가 사용하는 비율을 계산한다."""

    if (
        snapshot.gpu_bytes_in_use is None
        or snapshot.gpu_bytes_limit is None
        or snapshot.gpu_bytes_limit <= 0
    ):
        return None
    return 100.0 * snapshot.gpu_bytes_in_use / snapshot.gpu_bytes_limit


def build_block_bar(fraction: float | None, width: int) -> str:
    """0~1 비율을 굵은 block과 옅은 block으로 구성한 progress bar로 바꾼다."""

    if width <= 0:
        raise ValueError(f"Progress bar 폭은 양수여야 합니다: {width}")
    if fraction is None or not math.isfinite(fraction):
        return "░" * width
    clamped_fraction = min(max(fraction, 0.0), 1.0)
    filled_width = int(clamped_fraction * width)
    if clamped_fraction >= 1.0:
        filled_width = width
    if 0.0 < clamped_fraction and filled_width == 0:
        return "▏" + "░" * (width - 1)
    return "█" * filled_width + "░" * (width - filled_width)


def terminal_cell_width(text: str) -> int:
    """한글과 block 문자를 포함한 문자열이 terminal에서 차지하는 칸 수를 계산한다."""

    width = 0
    for character in unicodedata.normalize("NFC", text):
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
    return width


def clip_to_terminal_width(text: str, maximum_width: int) -> str:
    """문자나 한글 음절을 자르지 않고 terminal 표시 폭 안으로 문자열을 줄인다."""

    if maximum_width <= 0:
        return ""
    clipped: list[str] = []
    used_width = 0
    for character in unicodedata.normalize("NFC", text):
        character_width = (
            0
            if unicodedata.combining(character)
            else 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        )
        if used_width + character_width > maximum_width:
            break
        clipped.append(character)
        used_width += character_width
    return "".join(clipped)


def format_activity_label(activity_label: str) -> str:
    """내부 dashboard 상태값을 사람이 바로 이해할 수 있는 한국어로 바꾼다."""

    return {
        "compiling": "첫 JIT 컴파일 중",
        "running": "학습 중",
        "complete": "학습 완료",
        "failed": "학습 실패",
    }.get(activity_label, activity_label)


def format_vision_label(vision_encoder_mode: str, *, compact: bool) -> str:
    """Vision encoder 모드를 terminal 폭에 맞는 쉬운 문구로 바꾼다."""

    if vision_encoder_mode == "trainable":
        return "V=train" if compact else "Vision encoder 학습"
    if vision_encoder_mode == "frozen":
        return "V=frozen" if compact else "Vision encoder 동결"
    return vision_encoder_mode


def format_optional_rate(value: float | None) -> str:
    """선택적 처리량을 terminal 폭이 늘어나지 않는 짧은 문자열로 바꾼다."""

    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.3g}"

def format_optional_metric(metrics: Mapping[str, float] | None, key: str) -> str:
    """마지막 sync metric이 아직 없으면 n/a, 있으면 짧은 숫자로 표시한다."""

    if metrics is None:
        return "n/a"
    value = metrics.get(key)
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.6g}"


def build_progress_lines(
    *,
    step: int,
    target_step: int,
    elapsed_s: float,
    eta_s: float | None,
    vision_encoder_mode: str,
    metrics: Mapping[str, float] | None,
    snapshot: MemorySnapshot,
    terminal_columns: int,
    steps_per_second: float | None = None,
    samples_per_second: float | None = None,
    activity_label: str = "running",
    running_indicator: str = "-",
) -> tuple[str, ...]:
    """마지막 sync 값과 움직이는 시간을 폭 제한 5행 dashboard로 만든다."""

    if target_step <= 0:
        raise ValueError(f"목표 step은 양수여야 합니다: {target_step}")
    progress_fraction = min(max(step / target_step, 0.0), 1.0)
    progress_percent = 100.0 * progress_fraction
    maximum_width = max(terminal_columns - 1, 1)
    bar_width = max(min(maximum_width - 2, MAX_PROGRESS_BAR_WIDTH), 1)
    progress_bar = build_block_bar(progress_fraction, bar_width)
    memory_usage = jax_memory_usage_percent(snapshot)
    jax_memory = "/".join(
        (
            format_optional_gib(snapshot.gpu_bytes_in_use),
            format_optional_gib(snapshot.gpu_peak_bytes_in_use),
            format_optional_gib(snapshot.gpu_bytes_limit),
        )
    )
    usage_suffix = "n/a" if memory_usage is None else f"{memory_usage:.1f}%"
    if maximum_width >= 100:
        dashboard_lines = (
            (
                f"[{step}/{target_step} steps]  {progress_percent:.1f}% "
                f"{format_activity_label(activity_label)} [{running_indicator}] · "
                f"{format_vision_label(vision_encoder_mode, compact=False)} · 다음 동기화 후 수치 갱신"
            ),
            f"[{progress_bar}]",
            (
                f"시간  경과 {format_duration(elapsed_s)} · ETA {format_duration(eta_s)} · "
                f"{format_optional_rate(steps_per_second)} step/s · "
                f"{format_optional_rate(samples_per_second)} sample/s"
            ),
            (
                f"지표  loss {format_optional_metric(metrics, 'loss')} · "
                f"grad_norm {format_optional_metric(metrics, 'grad_norm')} · "
                f"param_norm {format_optional_metric(metrics, 'param_norm')} · 최근 구간 평균"
            ),
            f"JAX   사용/최고/상한 {jax_memory} GiB · {usage_suffix} · 최근 동기화 기준",
        )
    elif maximum_width >= 60:
        dashboard_lines = (
            (
                f"[{step}/{target_step}] {progress_percent:.1f}% "
                f"{format_activity_label(activity_label)} [{running_indicator}] · "
                f"{format_vision_label(vision_encoder_mode, compact=True)}"
            ),
            f"[{progress_bar}]",
            (
                f"T {format_duration(elapsed_s)} · ETA {format_duration(eta_s)} · "
                f"{format_optional_rate(steps_per_second)} step/s · "
                f"{format_optional_rate(samples_per_second)} sample/s"
            ),
            (
                f"L {format_optional_metric(metrics, 'loss')} · "
                f"G {format_optional_metric(metrics, 'grad_norm')} · "
                f"P {format_optional_metric(metrics, 'param_norm')} · sync 평균"
            ),
            f"JAX {jax_memory} GiB · {usage_suffix} · live/peak/limit",
        )
    else:
        dashboard_lines = (
            (
                f"[{step}/{target_step}] {progress_percent:.1f}% "
                f"{format_activity_label(activity_label)} [{running_indicator}] · "
                f"{format_vision_label(vision_encoder_mode, compact=True)}"
            ),
            f"[{progress_bar}]",
            (
                f"T {format_duration(elapsed_s)} E {format_duration(eta_s)} · "
                f"{format_optional_rate(steps_per_second)}st/s"
            ),
            (
                f"L{format_optional_metric(metrics, 'loss')} "
                f"G{format_optional_metric(metrics, 'grad_norm')} "
                f"P{format_optional_metric(metrics, 'param_norm')}"
            ),
            f"JAX {jax_memory}G · {usage_suffix}",
        )
    if len(dashboard_lines) != DASHBOARD_LINE_COUNT:
        raise AssertionError("Terminal dashboard 행 수 계약이 깨졌습니다.")
    return tuple(clip_to_terminal_width(line, maximum_width) for line in dashboard_lines)

@dataclasses.dataclass(frozen=True)
class ProgressDashboardView:
    """Background UI가 읽을 마지막 host sync 값만 불변 형태로 보관한다."""

    # 이번 process 실행의 monotonic 시작 시각이다.
    session_started_at_s: float

    # 마지막 JAX sync를 host 값으로 게시한 monotonic 시각이다.
    last_sync_at_s: float

    # 실제 JAX sync로 확인한 마지막 absolute step이다.
    last_sync_step: int

    # 학습이 도달할 최종 absolute step이다.
    target_step: int

    # 현재 Vision encoder 학습 모드다.
    vision_encoder_mode: str

    # compiling, running, complete, failed 중 화면에 보여줄 상태다.
    activity_label: str

    # 마지막 sync 구간의 평균 loss다.
    loss: float | None

    # 마지막 sync 구간의 평균 gradient norm이다.
    grad_norm: float | None

    # 마지막 sync 구간의 평균 parameter norm이다.
    param_norm: float | None

    # 마지막 sync 시점에서 계산한 예상 잔여 시간이다.
    eta_at_sync_s: float | None

    # 첫 JIT 구간을 제외해 계산한 초당 step 수다.
    steps_per_second: float | None

    # 현재 batch를 반영한 초당 sample 수다.
    samples_per_second: float | None

    # 마지막 main-thread sync에서 수집한 순수 Python memory 값이다.
    memory_snapshot: MemorySnapshot


@dataclasses.dataclass
class PeriodicProgressDashboard:
    """JAX와 분리된 daemon thread로 cached host dashboard만 주기 갱신한다."""

    # ANSI dashboard의 실제 쓰기를 직렬화하는 reporter다.
    reporter: TerminalProgressReporter

    # 두 자동 화면 갱신 사이에서 기다릴 초 단위 간격이다.
    refresh_seconds: float

    # 첫 JIT 전 즉시 표시할 placeholder view다.
    initial_view: ProgressDashboardView

    # 게시 상태와 lifecycle flag를 보호하는 lock이다.
    _state_lock: threading.Lock = dataclasses.field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    # 동시 render와 stop-close 사이의 순서를 보장하는 lock이다.
    _render_lock: threading.Lock = dataclasses.field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    # Background wait를 즉시 깨워 종료시키는 event다.
    _stop_event: threading.Event = dataclasses.field(
        default_factory=threading.Event,
        init=False,
        repr=False,
    )

    # 현재 background thread가 읽는 불변 host view다.
    _view: ProgressDashboardView = dataclasses.field(init=False, repr=False)

    # 생성된 daemon thread다.
    _thread: threading.Thread | None = dataclasses.field(
        default=None,
        init=False,
        repr=False,
    )

    # Spinner frame을 고르는 누적 render 횟수다.
    _render_count: int = dataclasses.field(default=0, init=False, repr=False)

    # start가 한 번 호출됐는지 나타낸다.
    _started: bool = dataclasses.field(default=False, init=False, repr=False)

    # TTY가 확인되어 실제 dashboard가 활성화됐는지 나타낸다.
    _active: bool = dataclasses.field(default=False, init=False, repr=False)

    # stop barrier가 시작되어 새 publish를 거부하는지 나타낸다.
    _stopped: bool = dataclasses.field(default=False, init=False, repr=False)

    # UI worker의 예상하지 못한 오류를 학습과 분리해 보관한다.
    _worker_error: BaseException | None = dataclasses.field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """갱신 간격을 검증하고 첫 immutable view를 설치한다."""

        if (
            not math.isfinite(self.refresh_seconds)
            or not MIN_PROGRESS_REFRESH_SECONDS
            <= self.refresh_seconds
            <= MAX_PROGRESS_REFRESH_SECONDS
        ):
            raise ValueError(
                "Dashboard 갱신 간격 범위가 잘못됐습니다: "
                f"{self.refresh_seconds!r}; "
                f"허용={MIN_PROGRESS_REFRESH_SECONDS:.1f}~{MAX_PROGRESS_REFRESH_SECONDS:.1f}초"
            )
        self._view = self.initial_view

    def start(self) -> bool:
        """TTY이면 placeholder를 즉시 그린 뒤 daemon refresh thread를 시작한다."""

        with self._state_lock:
            if self._started:
                raise RuntimeError("Periodic progress dashboard는 두 번 시작할 수 없습니다.")
            if self._stopped:
                return False
            self._started = True
        if not self.reporter.enabled():
            return False

        with self._state_lock:
            if self._stopped:
                return False
            self._active = True
        self._render_once()
        if not self.reporter.enabled():
            with self._state_lock:
                self._active = False
            return False

        worker = threading.Thread(
            target=self._run,
            name="pi0-progress-dashboard",
            daemon=True,
        )
        try:
            # stop()이 아직 시작하지 않은 thread를 놓치지 않도록 생성과 시작을
            # 같은 lifecycle lock 안에서 처리한다.
            with self._state_lock:
                if self._stopped:
                    self._active = False
                    return False
                self._thread = worker
                worker.start()
        except (OSError, RuntimeError) as error:
            with self._state_lock:
                self._worker_error = error
                self._thread = None
                self._active = False
                self._stopped = True
            self._stop_event.set()
            self.reporter.close()
            return False
        return True

    def publish(self, view: ProgressDashboardView, *, render_now: bool = True) -> bool:
        """Main thread가 새 host sync view를 원자적으로 게시한다."""

        with self._state_lock:
            if self._stopped:
                return False
            self._view = view
            active = self._active
        if active and render_now:
            self._render_once()
        return active

    def set_activity(self, activity_label: str, *, render_now: bool = True) -> bool:
        """Step과 metric은 유지한 채 complete 또는 failed 상태만 바꾼다."""

        with self._state_lock:
            if self._stopped:
                return False
            self._view = dataclasses.replace(self._view, activity_label=activity_label)
            active = self._active
        if active and render_now:
            self._render_once()
        return active

    def stop(self) -> None:
        """Stop event를 알리고 worker를 join한 뒤 dashboard cursor를 닫는다."""

        with self._state_lock:
            self._stopped = True
            self._active = False
            worker = self._thread
        self._stop_event.set()
        if (
            worker is not None
            and worker is not threading.current_thread()
            and worker.ident is not None
        ):
            worker.join()
        with self._render_lock:
            self.reporter.close()

    def _run(self) -> None:
        """지정 간격마다 cached Python view만 다시 그리며 JAX에는 접근하지 않는다."""

        try:
            while not self._stop_event.wait(self.refresh_seconds):
                self._render_once()
        except BaseException as error:
            with self._state_lock:
                self._worker_error = error
                self._active = False
            self._stop_event.set()

    def _render_once(self) -> None:
        """현재 cached view로 elapsed·ETA·spinner를 다시 계산해 한 번 그린다."""

        with self._render_lock:
            with self._state_lock:
                if not self._active or self._stopped:
                    return
                view = self._view
                render_index = self._render_count
                self._render_count += 1

            now = time.perf_counter()
            elapsed_s = max(now - view.session_started_at_s, 0.0)
            since_sync_s = max(now - view.last_sync_at_s, 0.0)
            eta_s = (
                None
                if view.eta_at_sync_s is None
                else max(view.eta_at_sync_s - since_sync_s, 0.0)
            )
            if view.activity_label == "complete":
                running_indicator = "+"
            elif view.activity_label == "failed":
                running_indicator = "!"
            else:
                running_indicator = RUNNING_INDICATOR_FRAMES[
                    render_index % len(RUNNING_INDICATOR_FRAMES)
                ]
            metrics = {
                key: value
                for key, value in (
                    ("loss", view.loss),
                    ("grad_norm", view.grad_norm),
                    ("param_norm", view.param_norm),
                )
                if value is not None
            }
            terminal_columns = self.reporter.terminal_columns()
            self.reporter.update(
                build_progress_lines(
                    step=view.last_sync_step,
                    target_step=view.target_step,
                    elapsed_s=elapsed_s,
                    eta_s=eta_s,
                    vision_encoder_mode=view.vision_encoder_mode,
                    metrics=metrics or None,
                    snapshot=view.memory_snapshot,
                    terminal_columns=terminal_columns,
                    steps_per_second=view.steps_per_second,
                    samples_per_second=view.samples_per_second,
                    activity_label=view.activity_label,
                    running_indicator=running_indicator,
                )
            )

def utc_timestamp() -> str:
    """정렬과 파싱이 가능한 UTC ISO-8601 timestamp를 반환한다."""

    return datetime.now(timezone.utc).isoformat()


def optional_int(stats: Mapping[str, Any], key: str) -> int | None:
    """JAX memory stats의 선택적 숫자 값을 안전하게 int로 변환한다."""

    value = stats.get(key)
    return None if value is None else int(value)


def read_current_host_rss_bytes() -> int | None:
    """Linux `/proc/self/status`에서 현재 process RSS를 byte 단위로 읽는다."""

    status_path = Path("/proc/self/status")
    if not status_path.is_file():
        return None
    for line in status_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) >= 2:
                return int(fields[1]) * 1024
    return None


def capture_memory_snapshot() -> MemorySnapshot:
    """지원되지 않는 backend에서도 실패하지 않도록 GPU·host memory를 수집한다."""

    memory_stats: Mapping[str, Any] = {}
    devices = jax.devices()
    if devices:
        try:
            memory_stats = devices[0].memory_stats() or {}
        except (AttributeError, RuntimeError):
            memory_stats = {}

    return MemorySnapshot(
        gpu_bytes_in_use=optional_int(memory_stats, "bytes_in_use"),
        gpu_peak_bytes_in_use=optional_int(memory_stats, "peak_bytes_in_use"),
        gpu_bytes_limit=optional_int(memory_stats, "bytes_limit"),
        host_rss_bytes=read_current_host_rss_bytes(),
        host_peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
    )


def memory_record(snapshot: MemorySnapshot) -> dict[str, int | None]:
    """MemorySnapshot을 JSON 직렬화 가능한 key/value record로 변환한다."""

    return dataclasses.asdict(snapshot)


def diagnostics_path(runtime: TrainingRuntime) -> Path:
    """현재 checkpoint run root에 대응하는 JSONL 진단 로그 경로를 반환한다."""

    return Path(runtime.config.checkpoint_dir).resolve() / TRAINING_METRICS_FILENAME


def run_training_loop_with_diagnostics(
    runtime: TrainingRuntime,
    first_batch: TrainingBatch,
    first_batch_data_time_s: float,
    *,
    progress_refresh_seconds: float = DEFAULT_PROGRESS_REFRESH_SECONDS,
) -> int:
    """학습 loop를 실행하며 sync 구간별 metric·시간·memory·checkpoint를 기록한다."""

    # 순환 import를 피하면서 검증된 학습 helper를 runtime에 재사용한다.
    from piper_vla.training import trainer as training

    if first_batch_data_time_s < 0:
        raise ValueError(f"첫 batch data 시간이 음수입니다: {first_batch_data_time_s}")
    if (
        not math.isfinite(progress_refresh_seconds)
        or not MIN_PROGRESS_REFRESH_SECONDS
        <= progress_refresh_seconds
        <= MAX_PROGRESS_REFRESH_SECONDS
    ):
        raise ValueError(
            "Dashboard 갱신 간격 범위가 잘못됐습니다: "
            f"{progress_refresh_seconds!r}; "
            f"허용={MIN_PROGRESS_REFRESH_SECONDS:.1f}~{MAX_PROGRESS_REFRESH_SECONDS:.1f}초"
        )

    target_step = runtime.config.num_train_steps
    current_step = int(jax.device_get(runtime.state.step))
    if current_step > target_step:
        raise ValueError(f"현재 step {current_step}이 목표 {target_step}보다 큽니다.")
    if current_step == target_step:
        return current_step

    session_start_step = current_step
    session_started_at = time.perf_counter() - first_batch_data_time_s
    steady_elapsed_s = 0.0
    steady_steps = 0
    placeholder_created_at = time.perf_counter()
    dashboard = PeriodicProgressDashboard(
        reporter=TerminalProgressReporter(sys.stderr),
        refresh_seconds=progress_refresh_seconds,
        initial_view=ProgressDashboardView(
            session_started_at_s=session_started_at,
            last_sync_at_s=placeholder_created_at,
            last_sync_step=current_step,
            target_step=target_step,
            vision_encoder_mode=runtime.vision_encoder_mode,
            activity_label="compiling",
            loss=None,
            grad_norm=None,
            param_norm=None,
            eta_at_sync_s=None,
            steps_per_second=None,
            samples_per_second=None,
            memory_snapshot=MemorySnapshot(None, None, None, None, 0),
        ),
    )
    logger = JsonlMetricLogger(diagnostics_path(runtime))
    session_id = uuid.uuid4().hex[:12]
    logger.append(
        {
            "schema_version": TRAINING_METRICS_SCHEMA_VERSION,
            "event": "session_start",
            "session_id": session_id,
            "timestamp_utc": utc_timestamp(),
            "start_step": current_step,
            "target_step": target_step,
            "session_total_steps": target_step - current_step,
            "batch_size": runtime.config.batch_size,
            "log_interval": runtime.config.log_interval,
            "save_interval": runtime.config.save_interval,
            "vision_encoder_mode": runtime.vision_encoder_mode,
        }
    )

    jitted_train_step = training.build_jitted_train_step(runtime)
    first_iteration = True
    last_saved_step = runtime.checkpoint_manager.latest_step()
    window_started = time.perf_counter()
    window_steps = 0
    window_data_time_s = first_batch_data_time_s
    first_window_extra_time_s = first_batch_data_time_s
    window_metrics: list[Mapping[str, Any]] = []

    try:
        dashboard.start()
        while current_step < target_step:
            if first_iteration:
                batch = first_batch
            else:
                data_started = time.perf_counter()
                batch = next_training_batch(runtime.data, runtime.config, validate=False)
                window_data_time_s += time.perf_counter() - data_started

            # OpenPI train_step이 내부에서 고정 RNG에 state.step을 fold-in한다.
            with training_sharding.set_mesh(runtime.data.mesh):
                next_state, step_metrics = jitted_train_step(
                    runtime.train_rng,
                    runtime.state,
                    batch,
                )

            completed_step = current_step + 1
            window_steps += 1
            window_metrics.append(step_metrics)
            should_log = first_iteration or completed_step % runtime.config.log_interval == 0
            should_save = (
                completed_step % runtime.config.save_interval == 0
                or completed_step == target_step
            )
            should_sync = should_log or should_save

            if should_sync:
                stacked_metrics = jax.tree.map(
                    lambda *values: jnp.stack(values),
                    *window_metrics,
                )
                averaged_metrics = jax.tree.map(jnp.mean, stacked_metrics)
                jax.block_until_ready((next_state, averaged_metrics))
                synchronized_at = time.perf_counter()
                actual_step = int(jax.device_get(next_state.step))
                if actual_step != completed_step:
                    raise RuntimeError(
                        f"train step 증가가 올바르지 않습니다: {actual_step} != {completed_step}"
                    )
                host_metrics = training.metrics_to_host(averaged_metrics)
                interval_wall_time_s = (
                    synchronized_at - window_started + first_window_extra_time_s
                )
                average_data_time_s = window_data_time_s / window_steps
                average_non_data_wall_time_s = max(
                    interval_wall_time_s - window_data_time_s,
                    0.0,
                ) / window_steps
                average_step_time_s = interval_wall_time_s / window_steps
                snapshot = capture_memory_snapshot()
            else:
                host_metrics = None
                average_data_time_s = None
                average_non_data_wall_time_s = None
                average_step_time_s = None
                snapshot = None

            # donation된 이전 state는 다시 사용하지 않고 새 state로 즉시 교체한다.
            runtime.state = next_state
            current_step = completed_step

            checkpoint_time_s = 0.0
            if should_save:
                if host_metrics is None:
                    raise AssertionError("checkpoint 저장 전에 metric 검증이 수행되지 않았습니다.")
                checkpoint_started = time.perf_counter()
                training.save_training_checkpoint(runtime, current_step)
                checkpoint_time_s = time.perf_counter() - checkpoint_started
                last_saved_step = current_step
                snapshot = capture_memory_snapshot()

            if should_sync:
                if host_metrics is None or snapshot is None:
                    raise AssertionError("동기화 지점의 metric 또는 memory snapshot이 없습니다.")
                jit_compile_included = first_iteration
                steady_window_time_s = interval_wall_time_s + checkpoint_time_s
                if not jit_compile_included:
                    steady_elapsed_s += steady_window_time_s
                    steady_steps += window_steps
                steady_avg_step_wall_time_s = (
                    steady_elapsed_s / steady_steps
                    if steady_steps > 0
                    else None
                )
                session_elapsed_s = time.perf_counter() - session_started_at
                session_completed_steps = current_step - session_start_step
                session_remaining_steps = target_step - current_step
                eta_s = (
                    session_remaining_steps * steady_avg_step_wall_time_s
                    if steady_avg_step_wall_time_s is not None
                    else None
                )
                progress_fraction = min(max(current_step / target_step, 0.0), 1.0)
                session_progress_fraction = session_completed_steps / (
                    target_step - session_start_step
                )
                steps_per_second = (
                    1.0 / steady_avg_step_wall_time_s
                    if steady_avg_step_wall_time_s not in (None, 0.0)
                    else None
                )
                samples_per_second = (
                    steps_per_second * runtime.config.batch_size
                    if steps_per_second is not None
                    else None
                )
                memory_usage_percent = jax_memory_usage_percent(snapshot)
                record: dict[str, Any] = {
                    "schema_version": TRAINING_METRICS_SCHEMA_VERSION,
                    "event": "train_step",
                    "session_id": session_id,
                    "timestamp_utc": utc_timestamp(),
                    "step": current_step,
                    "target_step": target_step,
                    "vision_encoder_mode": runtime.vision_encoder_mode,
                    "progress_fraction": progress_fraction,
                    "progress_percent": 100.0 * progress_fraction,
                    "session_progress_fraction": session_progress_fraction,
                    "session_elapsed_s": session_elapsed_s,
                    "session_completed_steps": session_completed_steps,
                    "session_remaining_steps": session_remaining_steps,
                    "loss": host_metrics["loss"],
                    "grad_norm": host_metrics["grad_norm"],
                    "param_norm": host_metrics["param_norm"],
                    "interval_steps": window_steps,
                    "jit_compile_included": jit_compile_included,
                    "avg_step_wall_time_s": average_step_time_s,
                    "steady_avg_step_wall_time_s": steady_avg_step_wall_time_s,
                    "eta_s": eta_s,
                    "steps_per_second": steps_per_second,
                    "samples_per_second": samples_per_second,
                    "avg_data_time_s": average_data_time_s,
                    "avg_non_data_wall_time_s": average_non_data_wall_time_s,
                    "checkpoint_saved": should_save,
                    "checkpoint_time_s": checkpoint_time_s,
                    "jax_memory_usage_percent": memory_usage_percent,
                    **memory_record(snapshot),
                }
                logger.append(record)

                dashboard.publish(
                    ProgressDashboardView(
                        session_started_at_s=session_started_at,
                        last_sync_at_s=time.perf_counter(),
                        last_sync_step=current_step,
                        target_step=target_step,
                        vision_encoder_mode=runtime.vision_encoder_mode,
                        activity_label=(
                            "complete" if current_step == target_step else "running"
                        ),
                        loss=host_metrics["loss"],
                        grad_norm=host_metrics["grad_norm"],
                        param_norm=host_metrics["param_norm"],
                        eta_at_sync_s=eta_s,
                        steps_per_second=steps_per_second,
                        samples_per_second=samples_per_second,
                        memory_snapshot=snapshot,
                    )
                )

                window_started = time.perf_counter()
                window_steps = 0
                window_data_time_s = 0.0
                first_window_extra_time_s = 0.0
                window_metrics = []

            first_iteration = False
    except Exception as error:
        dashboard.set_activity("failed")
        logger.append(
            {
                "schema_version": TRAINING_METRICS_SCHEMA_VERSION,
                "event": "failure",
                "session_id": session_id,
                "timestamp_utc": utc_timestamp(),
                "step": current_step,
                "target_step": target_step,
                "vision_encoder_mode": runtime.vision_encoder_mode,
                "session_elapsed_s": time.perf_counter() - session_started_at,
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        )
        raise
    finally:
        dashboard.stop()
        runtime.checkpoint_manager.wait_until_finished()

    if last_saved_step != target_step:
        raise RuntimeError(
            f"마지막 목표 checkpoint가 저장되지 않았습니다: {last_saved_step} != {target_step}"
        )
    logger.append(
        {
            "schema_version": TRAINING_METRICS_SCHEMA_VERSION,
            "event": "session_complete",
            "session_id": session_id,
            "timestamp_utc": utc_timestamp(),
            "step": target_step,
            "target_step": target_step,
            "vision_encoder_mode": runtime.vision_encoder_mode,
            "session_elapsed_s": time.perf_counter() - session_started_at,
        }
    )
    return target_step
