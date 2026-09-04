from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


COLORS = {
    "random_local": "#8c8c8c",
    "greedy_local": "#4c78a8",
    "stateless_local_aggregate": "#f58518",
    "centralized_online": "#54a24b",
    "field_local": "#e45756",
}


def _scale(value: float, lo: float, hi: float, start: float, end: float) -> float:
    if hi <= lo:
        return (start + end) / 2
    return start + (value - lo) / (hi - lo) * (end - start)


def write_plot(summary: list[dict[str, Any]], path: Path) -> None:
    densities = sorted({float(row["density"]) for row in summary})
    arms = sorted({str(row["arm"]) for row in summary})
    width, height = 960, 650
    left, right = 78, 930
    top_a, bottom_a = 70, 285
    top_b, bottom_b = 385, 600
    regret_values = [float(row["median_final_regret"]) for row in summary]
    y_hi = max(0.2, max(regret_values or [0.2]) * 1.15)
    bytes_by_density = {}
    for row in summary:
        bytes_by_density.setdefault(float(row["density"]), {})[str(row["arm"])] = float(row["median_bytes"])
    ratio_values = []
    for density, values in bytes_by_density.items():
        central = values.get("centralized_online", 1.0)
        ratio_values.extend(value / max(1.0, central) for value in values.values())
    ratio_hi = max(1.2, max(ratio_values or [1.2]) * 1.10)

    def path_for(key: str, y_top: float, y_bottom: float, hi: float) -> str:
        rows = [row for row in summary if row["arm"] == key]
        rows.sort(key=lambda row: float(row["density"]))
        points = []
        for row in rows:
            x = _scale(float(row["density"]), densities[0], densities[-1], left, right)
            y = _scale(float(row["median_final_regret"] if y_top == top_a else row["median_bytes"] / max(1.0, bytes_by_density[float(row["density"])].get("centralized_online", 1.0))), 0, hi, y_bottom, y_top)
            points.append(f"{x:.1f},{y:.1f}")
        return " ".join(points)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>PheroOS field benchmark density sweep</title>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="78" y="30" font-family="sans-serif" font-size="20" fill="#222">PheroOS field benchmark — density sweep</text>',
        '<text x="78" y="51" font-family="sans-serif" font-size="12" fill="#555">40 paired confirmatory seeds per density; pilot excluded</text>',
    ]

    for y_top, y_bottom, hi, title, ylabel in (
        (top_a, bottom_a, y_hi, "Final path regret (lower is better)", "normalized regret"),
        (top_b, bottom_b, ratio_hi, "Communication ratio vs centralized (lower is better)", "bytes / centralized bytes"),
    ):
        parts.append(f'<rect x="{left}" y="{y_top}" width="{right-left}" height="{y_bottom-y_top}" fill="none" stroke="#bbb"/>')
        parts.append(f'<text x="{left}" y="{y_top-12}" font-family="sans-serif" font-size="14" fill="#222">{escape(title)}</text>')
        for tick in range(0, 6):
            value = hi * tick / 5
            y = _scale(value, 0, hi, y_bottom, y_top)
            parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#eee"/>')
            parts.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#555">{value:.2f}</text>')
        parts.append(f'<text transform="translate(16 {(y_top+y_bottom)/2:.0f}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#222">{escape(ylabel)}</text>')
        for density in densities:
            x = _scale(density, densities[0], densities[-1], left, right)
            parts.append(f'<line x1="{x:.1f}" y1="{y_bottom}" x2="{x:.1f}" y2="{y_bottom+5}" stroke="#777"/>')
            parts.append(f'<text x="{x:.1f}" y="{y_bottom+20}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#555">{density:.2f}</text>')
        parts.append(f'<text x="{(left+right)/2:.0f}" y="{y_bottom+38}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#222">agent density ρ = agents / graph nodes</text>')

    # Quality floor and the communication gate are visible reference lines.
    quality_floor_y = _scale(0.15, 0, y_hi, bottom_a, top_a)
    parts.append(f'<line x1="{left}" y1="{quality_floor_y:.1f}" x2="{right}" y2="{quality_floor_y:.1f}" stroke="#e45756" stroke-dasharray="4 4"/>')
    parts.append(f'<text x="{right-4}" y="{quality_floor_y-4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#e45756">absolute floor 0.15</text>')
    bytes_floor_y = _scale(0.70, 0, ratio_hi, bottom_b, top_b)
    parts.append(f'<line x1="{left}" y1="{bytes_floor_y:.1f}" x2="{right}" y2="{bytes_floor_y:.1f}" stroke="#e45756" stroke-dasharray="4 4"/>')
    parts.append(f'<text x="{right-4}" y="{bytes_floor_y-4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#e45756">communication gate 0.70</text>')

    for arm in arms:
        color = COLORS.get(arm, "#222")
        points_a = path_for(arm, top_a, bottom_a, y_hi)
        parts.append(f'<polyline points="{points_a}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        points_b = []
        rows = sorted((row for row in summary if row["arm"] == arm), key=lambda row: float(row["density"]))
        for row in rows:
            density = float(row["density"])
            central = bytes_by_density[density].get("centralized_online", 1.0)
            x = _scale(density, densities[0], densities[-1], left, right)
            y = _scale(float(row["median_bytes"]) / max(1.0, central), 0, ratio_hi, bottom_b, top_b)
            points_b.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline points="{" ".join(points_b)}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        for row in rows:
            density = float(row["density"])
            x = _scale(density, densities[0], densities[-1], left, right)
            y = _scale(float(row["median_final_regret"]), 0, y_hi, bottom_a, top_a)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
            central = bytes_by_density[density].get("centralized_online", 1.0)
            y = _scale(float(row["median_bytes"]) / max(1.0, central), 0, ratio_hi, bottom_b, top_b)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')

    legend_y = 625
    x = left
    for arm in arms:
        color = COLORS.get(arm, "#222")
        parts.append(f'<line x1="{x}" y1="{legend_y-4}" x2="{x+20}" y2="{legend_y-4}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{x+25}" y="{legend_y}" font-family="sans-serif" font-size="11" fill="#222">{escape(arm)}</text>')
        x += 170 if len(arm) < 18 else 205
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")

