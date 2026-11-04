"""Draw the benchmark figures from results/summary.json (analysis happens in analyze.py).

Writes figures/holdings_benchmark.png/.svg and figures/latency.png/.svg.

Run with: uv run python -m benchmark.plot
"""

import json
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from benchmark.common import FIGURES_DIR, RESULTS_DIR, setup_logging

log = setup_logging("plot")

# Light-mode tokens from the reference data-viz palette: one hue per figure (single series),
# text in ink tokens, recessive axes.
SERIES = "#2a78d6"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
SURFACE = "#fcfcfb"

PANELS = [
    ("hallucination", "Hallucinated a holding\n(absent titles, lower is better)"),
    ("accuracy_held", "Correct on held titles\n(higher is better)"),
    ("clean_tool_use", "Clean tool use\n(called a tool, no tool errors)"),
]


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def rates_figure(summary: dict, order: list[str]):
    header_in, row_in, footer_in = 1.15, 0.55, 0.9  # fixed header so the title never collides with the panels
    height = header_in + row_in * len(order) + footer_in
    fig, axes = plt.subplots(1, len(PANELS), figsize=(11, height), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    y = list(range(len(order)))[::-1]
    for ax, (key, title) in zip(axes, PANELS):
        vals = [summary[m][key]["rate"] for m in order]
        lo = [summary[m][key]["ci_low"] for m in order]
        hi = [summary[m][key]["ci_high"] for m in order]
        ax.barh(y, vals, height=0.55, color=SERIES, zorder=2)
        ax.errorbar(vals, y, xerr=[[v - l for v, l in zip(vals, lo)], [h - v for v, h in zip(vals, hi)]],
                    fmt="none", ecolor=INK_2, elinewidth=1, capsize=2, zorder=3)
        for yi, v, h in zip(y, vals, hi):
            if not math.isnan(v):
                ax.text(min(h, 1.0) + 0.02, yi, f"{100 * v:.0f}%", va="center", ha="left", fontsize=9, color=INK)
        ax.set_xlim(0, 1.18)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "25", "50", "75", "100%"])
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        _style(ax)
    axes[0].set_yticks(y, order)
    axes[0].tick_params(axis="y", labelcolor=INK)
    n = max(s["n_trials"] + s.get("infra_failures", 0) for s in summary.values())  # trials attempted per model
    fig.text(0.01, 1 - 0.32 / height, "Can an open-weight model be trusted about library holdings?",
             ha="left", va="center", fontsize=13, color=INK, fontweight="bold")
    fig.text(0.01, 1 - 0.68 / height, f"Same agent, instructions and NEXUS tools; only the model changes. "
             f"{n} trials per model (10 held + 10 absent titles, seeded runs). Bars show rates with Wilson 95% intervals; infrastructure failures excluded.",
             ha="left", va="center", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 1 - header_in / height))
    return fig


def latency_figure(summary: dict, order: list[str]):
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(order) + 1.5))
    fig.patch.set_facecolor(SURFACE)
    y = list(range(len(order)))[::-1]
    med = [summary[m]["latency_median_s"] for m in order]
    p25 = [summary[m]["latency_p25_s"] for m in order]
    p75 = [summary[m]["latency_p75_s"] for m in order]
    ax.barh(y, med, height=0.55, color=SERIES, zorder=2)
    ax.errorbar(med, y, xerr=[[m - a for m, a in zip(med, p25)], [b - m for m, b in zip(med, p75)]],
                fmt="none", ecolor=INK_2, elinewidth=1, capsize=2, zorder=3)
    for yi, v, b in zip(y, med, p75):
        if not math.isnan(v):
            ax.text(b + 1, yi, f"{v:.0f} s", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, order)
    ax.set_xlabel("seconds per question (median, interquartile range)", color=INK_2, fontsize=9)
    ax.set_title("Time to answer, local Ollama on Apple Silicon", loc="left", fontsize=11, color=INK, fontweight="bold")
    _style(ax)
    fig.tight_layout()
    return fig


def main():
    summary = json.loads((RESULTS_DIR / "summary.json").read_text())
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    order = sorted(summary, key=lambda m: (summary[m]["hallucination"]["rate"] if not math.isnan(summary[m]["hallucination"]["rate"]) else 9,
                                           -summary[m]["accuracy_all"]["rate"]))
    for name, fn in (("holdings_benchmark", rates_figure), ("latency", latency_figure)):
        fig = fn(summary, order)
        for ext in ("png", "svg"):
            fig.savefig(FIGURES_DIR / f"{name}.{ext}", dpi=200, facecolor=fig.get_facecolor())
        plt.close(fig)
        log.info("wrote %s", FIGURES_DIR / f"{name}.png")


if __name__ == "__main__":
    main()
