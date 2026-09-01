#!/usr/bin/env python3
"""π0 JSONL 진단 로그를 추가 dependency 없이 SVG 그래프로 변환한다."""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape


# 이 plot script가 속한 workspace 절대 경로다.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# JSONL을 기록한 학습 설정의 고정 이름이다.
PIPER_PI0_CONFIG_NAME = "pi0_piper_lora"

# 학습 코드가 run root에 기록하는 기본 JSONL 이름이다.
TRAINING_METRICS_FILENAME = "training_metrics.jsonl"

# 별도 출력 경로가 없을 때 생성할 SVG 파일 이름이다.
TRAINING_PLOT_FILENAME = "training_diagnostics.svg"

# 학습 dependency와 동일한 workspace conda Python 경로다.
WORKSPACE_PYTHON = WORKSPACE_ROOT / ".conda" / "env" / "bin" / "python"

# run 이름을 단일 안전 경로 요소로 제한하는 문자 규칙이다.
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

# 생성할 SVG 전체 가로 크기다.
SVG_WIDTH = 1400

# 생성할 SVG 전체 세로 크기다.
SVG_HEIGHT = 940

# byte memory 값을 GiB로 바꿀 기준값이다.
GIB = 1024**3

# 각 선 그래프가 순서대로 사용할 색상 목록이다.
PLOT_COLORS = ("#2563eb", "#dc2626", "#16a34a", "#9333ea")


@dataclasses.dataclass(frozen=True)
class PlotSeries:
    """하나의 SVG panel에 그릴 label, 색상, step/value 점을 보관한다."""

    # panel legend에 표시할 선 이름이다.
    label: str

    # SVG polyline에 적용할 CSS 색상이다.
    color: str

    # `(absolute step, numeric value)` 순서쌍이다.
    points: tuple[tuple[int, float], ...]


def ensure_workspace_python(arguments: Sequence[str]) -> None:
    """다른 Python으로 실행됐으면 workspace conda Python으로 process를 교체한다."""

    expected_python = WORKSPACE_PYTHON.resolve()
    if Path(sys.executable).resolve() == expected_python:
        return
    if not expected_python.is_file():
        raise FileNotFoundError(f"workspace conda Python이 없습니다: {expected_python}")
    os.execv(
        str(expected_python),
        [str(expected_python), str(Path(__file__).resolve()), *arguments],
    )
    raise AssertionError("os.execv가 반환됐습니다.")


def validate_safe_name(value: str) -> str:
    """run 이름이 workspace 아래의 단일 안전 경로 요소인지 확인한다."""

    if value in {".", ".."} or SAFE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"안전하지 않은 run 이름입니다: {value!r}")
    return value


def resolve_workspace_path(path: Path) -> Path:
    """상대 경로를 workspace 기준으로 절대화하고 workspace 밖 경로를 거부한다."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = WORKSPACE_ROOT / expanded
    resolved = expanded.resolve()
    if not resolved.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f"경로는 workspace 안에 있어야 합니다: {resolved}")
    return resolved


def load_training_records(path: Path) -> list[dict[str, Any]]:
    """JSONL을 읽고 step별 마지막 train record만 남겨 정렬한다."""

    if not path.is_file():
        raise FileNotFoundError(
            "학습 진단 로그가 없습니다. 진단 코드 적용 후 다음 학습 step을 먼저 실행하세요: "
            f"{path}"
        )

    raw_text = path.read_text(encoding="utf-8")
    lines = raw_text.splitlines()
    records_by_step: dict[int, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            if line_number == len(lines) and not raw_text.endswith("\n"):
                continue
            raise ValueError(f"JSONL {line_number}행을 해석할 수 없습니다: {path}") from error
        if record.get("event") != "train_step":
            continue
        step = int(record["step"])
        records_by_step[step] = record

    if not records_by_step:
        raise ValueError(f"train_step record가 없습니다: {path}")
    return [records_by_step[step] for step in sorted(records_by_step)]


def finite_number(value: Any) -> float | None:
    """JSON 값을 finite float로 변환하고 None·NaN·Inf는 제외한다."""

    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def make_series(
    records: Iterable[dict[str, Any]],
    key: str,
    label: str,
    color: str,
    *,
    divisor: float = 1.0,
) -> PlotSeries:
    """JSON record의 숫자 key를 SVG용 step/value series로 변환한다."""

    points: list[tuple[int, float]] = []
    for record in records:
        value = finite_number(record.get(key))
        if value is not None:
            points.append((int(record["step"]), value / divisor))
    return PlotSeries(label=label, color=color, points=tuple(points))


def padded_range(values: Sequence[float]) -> tuple[float, float]:
    """상수 series도 보이도록 최소 padding을 포함한 y축 범위를 계산한다."""

    minimum = min(values)
    maximum = max(values)
    if math.isclose(minimum, maximum):
        padding = max(abs(minimum) * 0.05, 1e-6)
    else:
        padding = (maximum - minimum) * 0.08
    return minimum - padding, maximum + padding


def format_axis_value(value: float) -> str:
    """축 label을 값 크기에 맞는 짧은 문자열로 표현한다."""

    absolute = abs(value)
    if absolute >= 1000 or (absolute > 0 and absolute < 0.001):
        return f"{value:.2e}"
    if absolute >= 10:
        return f"{value:.1f}"
    return f"{value:.3f}"


def render_panel(
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    series: Sequence[PlotSeries],
    unit: str,
    session_boundaries: Sequence[int],
) -> str:
    """하나 이상의 numeric series를 축·grid·legend가 있는 SVG panel로 그린다."""

    available_series = [item for item in series if item.points]
    panel = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        'rx="12" fill="#ffffff" stroke="#cbd5e1"/>',
        f'<text x="{x + 20}" y="{y + 30}" font-size="18" font-weight="700" '
        f'fill="#0f172a">{escape(title)}</text>',
    ]
    if not available_series:
        panel.append(
            f'<text x="{x + width / 2}" y="{y + height / 2}" '
            'text-anchor="middle" fill="#64748b">No data</text>'
        )
        return "\n".join(panel)

    all_points = [point for item in available_series for point in item.points]
    x_min = min(point[0] for point in all_points)
    x_max = max(point[0] for point in all_points)
    if x_min == x_max:
        x_max = x_min + 1
    y_min, y_max = padded_range([point[1] for point in all_points])

    plot_left = x + 72
    plot_top = y + 48
    plot_right = x + width - 24
    plot_bottom = y + height - 50
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    for index in range(5):
        fraction = index / 4
        grid_y = plot_top + plot_height * fraction
        axis_value = y_max - (y_max - y_min) * fraction
        panel.append(
            f'<line x1="{plot_left}" y1="{grid_y:.1f}" x2="{plot_right}" '
            f'y2="{grid_y:.1f}" stroke="#e2e8f0"/>'
        )
        panel.append(
            f'<text x="{plot_left - 8}" y="{grid_y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#64748b">{escape(format_axis_value(axis_value))}</text>'
        )

    panel.extend(
        (
            f'<text x="{plot_left}" y="{plot_bottom + 22}" font-size="11" '
            f'fill="#64748b">step {x_min}</text>',
            f'<text x="{plot_right}" y="{plot_bottom + 22}" text-anchor="end" '
            f'font-size="11" fill="#64748b">step {x_max}</text>',
            f'<text x="{plot_left - 50}" y="{plot_top - 10}" font-size="11" '
            f'fill="#64748b">{escape(unit)}</text>',
        )
    )

    for boundary_step in session_boundaries:
        if x_min < boundary_step <= x_max:
            boundary_x = plot_left + (boundary_step - x_min) / (x_max - x_min) * plot_width
            panel.append(
                f'<line x1="{boundary_x:.1f}" y1="{plot_top}" '
                f'x2="{boundary_x:.1f}" y2="{plot_bottom}" '
                'stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="5 4"/>'
            )
            panel.append(
                f'<text x="{boundary_x + 4:.1f}" y="{plot_top + 13}" '
                'font-size="10" fill="#b45309">resume</text>'
            )

    for legend_index, item in enumerate(available_series):
        point_text: list[str] = []
        for step, value in item.points:
            plot_x = plot_left + (step - x_min) / (x_max - x_min) * plot_width
            plot_y = plot_bottom - (value - y_min) / (y_max - y_min) * plot_height
            point_text.append(f"{plot_x:.1f},{plot_y:.1f}")
        if len(point_text) == 1:
            point_x, point_y = point_text[0].split(",")
            panel.append(
                f'<circle cx="{point_x}" cy="{point_y}" r="4" fill="{item.color}"/>'
            )
        else:
            panel.append(
                f'<polyline points="{" ".join(point_text)}" fill="none" '
                f'stroke="{item.color}" stroke-width="2.5" stroke-linejoin="round"/>'
            )
        legend_x = plot_left + legend_index * 145
        panel.append(
            f'<line x1="{legend_x}" y1="{y + 38}" x2="{legend_x + 20}" '
            f'y2="{y + 38}" stroke="{item.color}" stroke-width="3"/>'
        )
        panel.append(
            f'<text x="{legend_x + 26}" y="{y + 42}" font-size="11" '
            f'fill="#334155">{escape(item.label)}</text>'
        )
    return "\n".join(panel)


def render_diagnostics_svg(records: Sequence[dict[str, Any]], title: str) -> str:
    """Loss·gradient·시간·memory 4개 panel을 포함한 완전한 SVG 문서를 만든다."""

    latest = records[-1]
    steady_records = [
        record for record in records if not bool(record.get("jit_compile_included"))
    ] or list(records)
    session_count = len({record.get("session_id") for record in records})
    session_boundaries: list[int] = []
    previous_session = records[0].get("session_id")
    for record in records[1:]:
        current_session = record.get("session_id")
        if current_session != previous_session:
            session_boundaries.append(int(record["step"]))
        previous_session = current_session
    losses = [float(record["loss"]) for record in records]
    data_times = [
        float(record["avg_data_time_s"])
        for record in steady_records
        if record.get("avg_data_time_s") is not None
    ]
    non_data_times = [
        float(record["avg_non_data_wall_time_s"])
        for record in steady_records
        if record.get("avg_non_data_wall_time_s") is not None
    ]
    summary = (
        f"records={len(records)} · sessions={session_count} · steps={records[0]['step']}–{latest['step']} · "
        f"latest loss={losses[-1]:.6f} · min loss={min(losses):.6f} · "
        f"median data={statistics.median(data_times):.3f}s · "
        f"median non-data={statistics.median(non_data_times):.3f}s"
    )

    loss_series = (make_series(records, "loss", "loss", PLOT_COLORS[0]),)
    gradient_series = (
        make_series(records, "grad_norm", "grad norm", PLOT_COLORS[1]),
    )
    timing_series = (
        make_series(steady_records, "avg_data_time_s", "data", PLOT_COLORS[2]),
        make_series(steady_records, "avg_non_data_wall_time_s", "non-data", PLOT_COLORS[0]),
        make_series(steady_records, "checkpoint_time_s", "checkpoint", PLOT_COLORS[1]),
    )
    memory_series = (
        make_series(records, "gpu_bytes_in_use", "JAX used", PLOT_COLORS[0], divisor=GIB),
        make_series(
            records,
            "gpu_peak_bytes_in_use",
            "JAX peak",
            PLOT_COLORS[1],
            divisor=GIB,
        ),
        make_series(
            records,
            "gpu_bytes_limit",
            "JAX limit",
            PLOT_COLORS[3],
            divisor=GIB,
        ),
        make_series(records, "host_rss_bytes", "host RSS", PLOT_COLORS[2], divisor=GIB),
    )

    panels = (
        render_panel(30, 120, 660, 360, "Training loss", loss_series, "loss", session_boundaries),
        render_panel(710, 120, 660, 360, "Gradient norm", gradient_series, "norm", session_boundaries),
        render_panel(30, 510, 660, 360, "Data / non-data / checkpoint time", timing_series, "seconds", session_boundaries),
        render_panel(710, 510, 660, 360, "Process memory", memory_series, "GiB", session_boundaries),
    )
    return "\n".join(
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" '
            f'height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
            '<rect width="100%" height="100%" fill="#f1f5f9"/>',
            f'<text x="30" y="48" font-size="28" font-weight="700" '
            f'fill="#0f172a">{escape(title)}</text>',
            f'<text x="30" y="78" font-size="14" fill="#475569">{escape(summary)}</text>',
            *panels,
            "</svg>",
        )
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Run 이름, 로그 위치, 출력 SVG, 최근 record 범위를 받는 parser를 만든다."""

    parser = argparse.ArgumentParser(description="π0 JSONL 진단 로그를 SVG로 변환합니다.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("data/runs"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="최근 N개 logged step만 표시",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """JSONL record를 읽어 summary를 출력하고 SVG 진단 그래프를 저장한다."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_workspace_python(arguments)
    namespace = build_argument_parser().parse_args(arguments)
    run_name = validate_safe_name(namespace.run_name)
    runs_root = resolve_workspace_path(namespace.runs_root)
    run_dir = runs_root / PIPER_PI0_CONFIG_NAME / run_name
    metrics_path = run_dir / TRAINING_METRICS_FILENAME
    output_path = (
        run_dir / TRAINING_PLOT_FILENAME
        if namespace.output is None
        else resolve_workspace_path(namespace.output)
    )

    output_path = output_path.resolve()
    if output_path.parent != run_dir.resolve():
        raise ValueError(f"--output은 현재 run root 바로 아래여야 합니다: {output_path}")
    if output_path.suffix.lower() != ".svg":
        raise ValueError(f"--output은 .svg 파일이어야 합니다: {output_path}")

    records = load_training_records(metrics_path)
    if namespace.last is not None:
        if namespace.last <= 0:
            raise ValueError(f"--last는 양수여야 합니다: {namespace.last}")
        records = records[-namespace.last :]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_diagnostics_svg(records, f"π0 diagnostics · {run_name}"),
        encoding="utf-8",
    )
    print("Metrics log       :", metrics_path)
    print("Logged steps      :", f"{records[0]['step']} -> {records[-1]['step']}")
    print("Latest loss       :", f"{float(records[-1]['loss']):.6f}")
    print("Diagnostic plot   :", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
