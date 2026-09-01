#!/usr/bin/env python3
"""실행 중인 pi0 JSONL 로그를 읽어 TTY에 5줄 진행 대시보드로 표시한다."""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence, TextIO
import unicodedata


# 이 모니터 스크립트가 속한 workspace 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# pi0 학습 run이 저장되는 config 이름이다.
PI0_CONFIG_NAME = "pi0_piper_lora"

# 학습 process가 run root에 누적 기록하는 JSONL 파일 이름이다.
TRAINING_METRICS_FILENAME = "training_metrics.jsonl"

# 인자를 생략했을 때 사용할 run 상위 경로다.
DEFAULT_RUNS_ROOT = WORKSPACE_ROOT / "data" / "runs"

# 화면을 다시 그리는 기본 간격이다.
DEFAULT_REFRESH_SECONDS = 1.0

# systemd 상태 확인 process가 지나치게 자주 생기지 않도록 둘 최소 간격이다.
UNIT_STATUS_REFRESH_SECONDS = 10.0

# 넓은 terminal에서도 progress bar가 과도하게 길어지지 않을 최대 폭이다.
MAX_PROGRESS_BAR_WIDTH = 60

# 같은 위치에 반복해서 그릴 dashboard 행 수다.
DASHBOARD_LINE_COUNT = 5

# 실행 중임을 눈으로 확인할 ASCII spinner frame이다.
RUNNING_INDICATOR_FRAMES = ("|", "/", "-", "\\")

# 경로 탈출을 막기 위한 run 이름 규칙이다.
SAFE_RUN_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

# systemd unit 인자에 shell 문법이 섞이지 않도록 제한하는 규칙이다.
SAFE_UNIT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]*")

# byte 단위 memory를 GiB로 바꿀 기준값이다.
GIB = 1024**3


@dataclasses.dataclass(frozen=True)
class DashboardSnapshot:
    """JSONL에서 복원한 마지막 학습 상태를 순수 Python 값으로 보관한다."""

    # 가장 최근 session 식별자다.
    session_id: str

    # 마지막으로 확인된 absolute 학습 step이다.
    step: int

    # 학습이 도달할 absolute 목표 step이다.
    target_step: int

    # trainable 또는 frozen Vision encoder 모드다.
    vision_encoder_mode: str

    # compiling, running, complete, failed 중 하나인 학습 상태다.
    activity: str

    # 마지막 동기화 구간의 metric 값이다.
    metrics: Mapping[str, float] | None

    # 마지막 동기화 당시 이번 session의 경과 시간이다.
    session_elapsed_s: float

    # 마지막 동기화 당시 계산된 예상 잔여 시간이다.
    eta_s: float | None

    # 첫 JIT 구간을 제외해 계산한 초당 step 수다.
    steps_per_second: float | None

    # 현재 batch를 반영한 초당 sample 수다.
    samples_per_second: float | None

    # 마지막 동기화 JAX tensor 사용 byte다.
    gpu_bytes_in_use: int | None

    # 현재 학습 process에서 관측한 JAX peak byte다.
    gpu_peak_bytes_in_use: int | None

    # JAX allocator가 사용할 수 있는 상한 byte다.
    gpu_bytes_limit: int | None

    # 이 snapshot을 기록한 UTC wall-clock 시각이다.
    timestamp_utc: datetime


@dataclasses.dataclass
class TerminalDashboard:
    """여러 줄 dashboard를 같은 terminal 위치에 안전하게 덮어쓴다."""

    # Dashboard를 표시할 TTY stream이다.
    stream: TextIO

    # 직전 화면에 그린 행 수다.
    rendered_lines: int = 0

    # 출력 오류 뒤 추가 렌더링을 중단할지 나타낸다.
    disabled: bool = False

    def enabled(self) -> bool:
        """현재 출력 대상이 ANSI cursor 갱신을 지원하는 TTY인지 확인한다."""

        if self.disabled:
            return False
        try:
            return bool(self.stream.isatty())
        except (AttributeError, OSError, ValueError):
            self.disabled = True
            return False

    def terminal_columns(self, fallback: int = 120) -> int:
        """현재 stream의 terminal 폭을 읽고 실패하면 안전한 기본값을 쓴다."""

        try:
            return max(os.get_terminal_size(self.stream.fileno()).columns, 1)
        except (AttributeError, OSError, ValueError):
            return fallback

    def update(self, lines: Sequence[str]) -> None:
        """이전 dashboard를 지우고 새 5줄 화면을 같은 위치에 그린다."""

        if not self.enabled():
            return
        dashboard_lines = tuple(lines)
        if len(dashboard_lines) != DASHBOARD_LINE_COUNT:
            raise ValueError(f"Dashboard는 정확히 {DASHBOARD_LINE_COUNT}행이어야 합니다.")
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
            self.rendered_lines = len(dashboard_lines)
        except (OSError, ValueError):
            self.disabled = True
            self.rendered_lines = 0

    def close(self) -> None:
        """열린 dashboard 아래로 cursor를 내리고 일반 shell 입력 위치를 복구한다."""

        if self.rendered_lines == 0:
            return
        try:
            self.stream.write("\r\n")
            self.stream.flush()
        except (OSError, ValueError):
            self.disabled = True
        finally:
            self.rendered_lines = 0


@dataclasses.dataclass
class UnitStatusCache:
    """systemd 상태 조회를 제한된 주기로만 수행해 마지막 결과를 재사용한다."""

    # 조회할 user systemd unit 이름이다.
    unit_name: str | None

    # 직전 systemctl 실행 monotonic 시각이다.
    checked_at_s: float = 0.0

    # 직전 systemctl이 반환한 active 상태 문자열이다.
    status: str | None = None

    def get(self, now_s: float) -> str | None:
        """필요할 때만 systemctl을 실행하고 그 사이에는 cached 상태를 반환한다."""

        if self.unit_name is None:
            return None
        if now_s - self.checked_at_s < UNIT_STATUS_REFRESH_SECONDS and self.status:
            return self.status
        try:
            result = subprocess.run(
                ("systemctl", "--user", "is-active", self.unit_name),
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            self.status = result.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            self.status = "unknown"
        self.checked_at_s = now_s
        return self.status


def finite_float(value: Any) -> float | None:
    """JSON 숫자를 finite float로 바꾸고 없거나 비정상이면 None을 반환한다."""

    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def optional_int(value: Any) -> int | None:
    """선택적 JSON 정수를 Python int로 변환한다."""

    return None if value is None else int(value)


def parse_timestamp(value: Any) -> datetime:
    """JSON UTC timestamp를 timezone-aware datetime으로 변환한다."""

    if not isinstance(value, str):
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_complete_json_records(path: Path) -> list[dict[str, Any]]:
    """Writer가 쓰는 중인 마지막 조각은 무시하고 완성된 JSONL 행만 읽는다."""

    if not path.is_file():
        raise FileNotFoundError(f"학습 metric 로그가 아직 없습니다: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_bytes().splitlines(keepends=True), start=1):
        if not raw_line.endswith(b"\n"):
            continue
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"JSONL {line_number}행이 손상됐습니다: {path}") from error
        if isinstance(record, dict):
            records.append(record)
    return records


def latest_session_snapshot(records: Sequence[Mapping[str, Any]]) -> DashboardSnapshot:
    """여러 resume session 중 마지막 session과 그 최신 metric을 dashboard로 합친다."""

    session: Mapping[str, Any] | None = None
    train_record: Mapping[str, Any] | None = None
    terminal_record: Mapping[str, Any] | None = None
    for record in records:
        event = record.get("event")
        if event == "session_start":
            session = record
            train_record = None
            terminal_record = None
            continue
        if session is None or record.get("session_id") != session.get("session_id"):
            continue
        if event == "train_step":
            train_record = record
        elif event in {"failure", "session_complete"}:
            terminal_record = record

    if session is None:
        raise ValueError("session_start record가 아직 없습니다.")
    newest = terminal_record or train_record or session
    if terminal_record is not None:
        activity = "failed" if terminal_record.get("event") == "failure" else "complete"
    elif train_record is None:
        activity = "compiling"
    else:
        activity = "running"

    metric_source = train_record
    metrics = None
    if metric_source is not None:
        metrics = {
            "loss": float(metric_source["loss"]),
            "grad_norm": float(metric_source["grad_norm"]),
            "param_norm": float(metric_source["param_norm"]),
        }
    step = int(newest.get("step", session.get("start_step", 0)))
    target_step = int(newest.get("target_step", session["target_step"]))
    elapsed_source = newest if newest.get("session_elapsed_s") is not None else train_record
    elapsed_s = (
        float(elapsed_source["session_elapsed_s"])
        if elapsed_source is not None and elapsed_source.get("session_elapsed_s") is not None
        else 0.0
    )
    return DashboardSnapshot(
        session_id=str(session.get("session_id", "unknown")),
        step=step,
        target_step=target_step,
        vision_encoder_mode=str(
            newest.get("vision_encoder_mode", session.get("vision_encoder_mode", "unknown"))
        ),
        activity=activity,
        metrics=metrics,
        session_elapsed_s=elapsed_s,
        eta_s=finite_float(metric_source.get("eta_s")) if metric_source is not None else None,
        steps_per_second=(
            finite_float(metric_source.get("steps_per_second"))
            if metric_source is not None
            else None
        ),
        samples_per_second=(
            finite_float(metric_source.get("samples_per_second"))
            if metric_source is not None
            else None
        ),
        gpu_bytes_in_use=(
            optional_int(metric_source.get("gpu_bytes_in_use"))
            if metric_source is not None
            else None
        ),
        gpu_peak_bytes_in_use=(
            optional_int(metric_source.get("gpu_peak_bytes_in_use"))
            if metric_source is not None
            else None
        ),
        gpu_bytes_limit=(
            optional_int(metric_source.get("gpu_bytes_limit"))
            if metric_source is not None
            else None
        ),
        timestamp_utc=parse_timestamp(newest.get("timestamp_utc")),
    )


def format_duration(seconds: float | None) -> str:
    """초 단위 시간을 dashboard용 HH:MM:SS 문자열로 바꾼다."""

    if seconds is None or not math.isfinite(seconds):
        return "--:--:--"
    total_seconds = max(int(round(seconds)), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def format_metric(metrics: Mapping[str, float] | None, key: str) -> str:
    """마지막 metric이 없으면 n/a, 있으면 짧은 숫자 문자열로 표시한다."""

    if metrics is None or key not in metrics:
        return "n/a"
    return f"{metrics[key]:.6g}"


def format_rate(value: float | None) -> str:
    """선택적 처리량 값을 짧은 문자열로 표시한다."""

    return "n/a" if value is None else f"{value:.3g}"


def format_gib(value: int | None) -> str:
    """선택적 byte 값을 GiB 숫자로 표시한다."""

    return "n/a" if value is None else f"{value / GIB:.2f}"


def build_block_bar(fraction: float, width: int) -> str:
    """0~1 진행률을 굵은 block과 옅은 block으로 구성한 bar로 바꾼다."""

    clamped = min(max(fraction, 0.0), 1.0)
    filled = width if clamped >= 1.0 else int(clamped * width)
    if 0.0 < clamped and filled == 0:
        return "▏" + "░" * (width - 1)
    return "█" * filled + "░" * (width - filled)


def terminal_cell_width(text: str) -> int:
    """한글과 block 문자를 포함한 문자열의 terminal 표시 칸 수를 계산한다."""

    width = 0
    for character in unicodedata.normalize("NFC", text):
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
    return width


def clip_to_width(text: str, maximum_width: int) -> str:
    """한글 음절을 쪼개지 않고 terminal 폭 안으로 문자열을 자른다."""

    clipped: list[str] = []
    used = 0
    for character in unicodedata.normalize("NFC", text):
        character_width = (
            0
            if unicodedata.combining(character)
            else 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        )
        if used + character_width > maximum_width:
            break
        clipped.append(character)
        used += character_width
    return "".join(clipped)


def activity_label(activity: str) -> str:
    """내부 상태 이름을 사람이 이해하기 쉬운 한국어로 바꾼다."""

    return {
        "compiling": "첫 JIT 컴파일 중",
        "running": "학습 중",
        "complete": "학습 완료",
        "failed": "학습 실패",
        "inactive": "서비스 중지",
    }.get(activity, activity)


def vision_label(mode: str, *, compact: bool) -> str:
    """Vision encoder 모드를 terminal 폭에 맞는 문구로 바꾼다."""

    if mode == "trainable":
        return "V=train" if compact else "Vision encoder 학습"
    if mode == "frozen":
        return "V=frozen" if compact else "Vision encoder 동결"
    return mode


def effective_activity(snapshot: DashboardSnapshot, unit_status: str | None) -> str:
    """JSONL 완료 상태를 우선하고 systemd 실패·중지 상태를 보조 반영한다."""

    if snapshot.activity in {"complete", "failed"}:
        return snapshot.activity
    if unit_status == "failed":
        return "failed"
    if unit_status in {"inactive", "deactivating"}:
        return "inactive"
    return snapshot.activity


def build_dashboard_lines(
    snapshot: DashboardSnapshot,
    *,
    now_utc: datetime,
    columns: int,
    spinner: str,
    unit_status: str | None,
) -> tuple[str, ...]:
    """최신 JSONL snapshot을 학습 화면과 같은 폭 제한 5줄 dashboard로 만든다."""

    activity = effective_activity(snapshot, unit_status)
    running = activity in {"compiling", "running"}
    record_age_s = max((now_utc - snapshot.timestamp_utc).total_seconds(), 0.0)
    elapsed_s = snapshot.session_elapsed_s + (record_age_s if running else 0.0)
    eta_s = (
        None
        if snapshot.eta_s is None
        else max(snapshot.eta_s - (record_age_s if running else 0.0), 0.0)
    )
    progress_fraction = min(max(snapshot.step / snapshot.target_step, 0.0), 1.0)
    progress_percent = 100.0 * progress_fraction
    maximum_width = max(columns - 1, 1)
    bar_width = max(min(maximum_width - 2, MAX_PROGRESS_BAR_WIDTH), 1)
    bar = build_block_bar(progress_fraction, bar_width)
    memory = "/".join(
        (
            format_gib(snapshot.gpu_bytes_in_use),
            format_gib(snapshot.gpu_peak_bytes_in_use),
            format_gib(snapshot.gpu_bytes_limit),
        )
    )
    memory_percent = (
        None
        if snapshot.gpu_bytes_in_use is None
        or snapshot.gpu_bytes_limit is None
        or snapshot.gpu_bytes_limit <= 0
        else 100.0 * snapshot.gpu_bytes_in_use / snapshot.gpu_bytes_limit
    )
    memory_suffix = "n/a" if memory_percent is None else f"{memory_percent:.1f}%"
    indicator = "+" if activity == "complete" else "!" if activity in {"failed", "inactive"} else spinner

    if maximum_width >= 100:
        lines = (
            (
                f"[{snapshot.step}/{snapshot.target_step} steps] {progress_percent:.1f}% "
                f"{activity_label(activity)} [{indicator}] · "
                f"{vision_label(snapshot.vision_encoder_mode, compact=False)} · "
                f"마지막 sync {record_age_s:.0f}초 전"
            ),
            f"[{bar}]",
            (
                f"시간  경과 {format_duration(elapsed_s)} · ETA {format_duration(eta_s)} · "
                f"{format_rate(snapshot.steps_per_second)} step/s · "
                f"{format_rate(snapshot.samples_per_second)} sample/s"
            ),
            (
                f"지표  loss {format_metric(snapshot.metrics, 'loss')} · "
                f"grad_norm {format_metric(snapshot.metrics, 'grad_norm')} · "
                f"param_norm {format_metric(snapshot.metrics, 'param_norm')} · 최근 구간 평균"
            ),
            f"JAX   사용/최고/상한 {memory} GiB · {memory_suffix} · 최근 동기화 기준",
        )
    elif maximum_width >= 60:
        lines = (
            (
                f"[{snapshot.step}/{snapshot.target_step}] {progress_percent:.1f}% "
                f"{activity_label(activity)} [{indicator}] · "
                f"{vision_label(snapshot.vision_encoder_mode, compact=True)}"
            ),
            f"[{bar}]",
            (
                f"T {format_duration(elapsed_s)} · ETA {format_duration(eta_s)} · "
                f"{format_rate(snapshot.steps_per_second)} step/s · "
                f"{format_rate(snapshot.samples_per_second)} sample/s"
            ),
            (
                f"L {format_metric(snapshot.metrics, 'loss')} · "
                f"G {format_metric(snapshot.metrics, 'grad_norm')} · "
                f"P {format_metric(snapshot.metrics, 'param_norm')} · sync 평균"
            ),
            f"JAX {memory} GiB · {memory_suffix} · live/peak/limit",
        )
    else:
        lines = (
            f"[{snapshot.step}/{snapshot.target_step}] {progress_percent:.1f}% {activity_label(activity)} [{indicator}]",
            f"[{bar}]",
            f"T {format_duration(elapsed_s)} E {format_duration(eta_s)} · {format_rate(snapshot.steps_per_second)}st/s",
            (
                f"L{format_metric(snapshot.metrics, 'loss')} "
                f"G{format_metric(snapshot.metrics, 'grad_norm')} "
                f"P{format_metric(snapshot.metrics, 'param_norm')}"
            ),
            f"JAX {memory}G · {memory_suffix}",
        )
    return tuple(clip_to_width(line, maximum_width) for line in lines)


def validate_safe_name(value: str, pattern: re.Pattern[str], label: str) -> str:
    """Run 또는 systemd unit 이름이 단일 안전 문자열인지 검사한다."""

    if value in {".", ".."} or pattern.fullmatch(value) is None:
        raise ValueError(f"안전하지 않은 {label}입니다: {value!r}")
    return value


def resolve_runs_root(path: Path) -> Path:
    """Runs root를 workspace 내부 절대 경로로 변환하고 경로 탈출을 거부한다."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = WORKSPACE_ROOT / expanded
    resolved = expanded.resolve()
    if not resolved.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f"--runs-root는 workspace 내부여야 합니다: {resolved}")
    return resolved


def build_argument_parser() -> argparse.ArgumentParser:
    """모니터링할 run과 선택적 systemd unit을 받는 CLI parser를 만든다."""

    parser = argparse.ArgumentParser(
        description="실행 중인 pi0 JSONL을 읽어 5줄 TTY 진행 화면으로 표시합니다."
    )
    parser.add_argument("--run-name", required=True, help="모니터링할 학습 run 이름")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--unit", default=None, help="상태까지 확인할 user systemd unit 이름")
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=DEFAULT_REFRESH_SECONDS,
        help="화면을 다시 그릴 간격(초)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """JSONL을 읽기 전용으로 polling하며 Ctrl+C까지 dashboard를 갱신한다."""

    namespace = build_argument_parser().parse_args(argv)
    run_name = validate_safe_name(namespace.run_name, SAFE_RUN_NAME_PATTERN, "run 이름")
    unit_name = (
        None
        if namespace.unit is None
        else validate_safe_name(namespace.unit, SAFE_UNIT_NAME_PATTERN, "systemd unit 이름")
    )
    refresh_seconds = float(namespace.refresh_seconds)
    if not math.isfinite(refresh_seconds) or not 0.2 <= refresh_seconds <= 60.0:
        raise ValueError(f"--refresh-seconds는 0.2~60.0초여야 합니다: {refresh_seconds!r}")
    metrics_path = (
        resolve_runs_root(namespace.runs_root)
        / PI0_CONFIG_NAME
        / run_name
        / TRAINING_METRICS_FILENAME
    )
    reporter = TerminalDashboard(sys.stderr)
    if not reporter.enabled():
        raise RuntimeError("이 모니터는 cursor 갱신이 가능한 TTY terminal에서 실행해야 합니다.")
    unit_cache = UnitStatusCache(unit_name)
    spinner_index = 0

    try:
        while True:
            records = read_complete_json_records(metrics_path)
            snapshot = latest_session_snapshot(records)
            now_monotonic = time.monotonic()
            lines = build_dashboard_lines(
                snapshot,
                now_utc=datetime.now(timezone.utc),
                columns=reporter.terminal_columns(),
                spinner=RUNNING_INDICATOR_FRAMES[spinner_index % len(RUNNING_INDICATOR_FRAMES)],
                unit_status=unit_cache.get(now_monotonic),
            )
            reporter.update(lines)
            spinner_index += 1
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        reporter.close()


if __name__ == "__main__":
    raise SystemExit(main())
