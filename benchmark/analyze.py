"""Summarize benchmark trials into per-model metrics (no plotting here).

Reads results/*.jsonl, writes results/summary.json and results/summary.md.

Run with: uv run python -m benchmark.analyze
"""

import json
import math
import statistics
from collections import defaultdict

from benchmark.common import RESULTS_DIR, setup_logging

log = setup_logging("analyze")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Proportion with a Wilson 95% interval; (nan, nan, nan) when n == 0."""
    if n == 0:
        return (math.nan, math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> dict:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "ci_low": lo, "ci_high": hi}


def summarize(trials: list[dict]) -> dict:
    held = [t for t in trials if t["expected"] == "held"]
    absent = [t for t in trials if t["expected"] == "absent"]
    ok = [t for t in trials if t["status"] == "ok"]
    lat = [t["latency_s"] for t in ok]
    return {
        "n_trials": len(trials),
        "completed": rate(len(ok), len(trials)),
        "accuracy_all": rate(sum(t["correct"] for t in trials), len(trials)),
        "accuracy_held": rate(sum(t["correct"] for t in held), len(held)),
        "accuracy_absent": rate(sum(t["correct"] for t in absent), len(absent)),
        "hallucination": rate(sum(t["hallucinated"] for t in absent), len(absent)),
        "unsure": rate(sum(t["verdict"] == "UNSURE" for t in trials), len(trials)),
        "unparsed": rate(sum(t["verdict"] == "UNPARSED" for t in ok), len(ok)),
        "used_primo": rate(sum(t["used_primo"] for t in trials), len(trials)),
        "clean_tool_use": rate(sum(t["n_tool_calls"] > 0 and t["n_tool_errors"] == 0 for t in trials), len(trials)),
        "any_tool_error": rate(sum(t["n_tool_errors"] > 0 for t in trials), len(trials)),
        "fabricated_link": rate(sum(t["fabricated_links"] > 0 for t in ok), len(ok)),
        "status_counts": dict(sorted(defaultdict(int, {s: sum(t["status"] == s for t in trials) for s in {t["status"] for t in trials}}).items())),
        "latency_median_s": statistics.median(lat) if lat else math.nan,
        "latency_p25_s": statistics.quantiles(lat, n=4)[0] if len(lat) >= 2 else math.nan,
        "latency_p75_s": statistics.quantiles(lat, n=4)[2] if len(lat) >= 2 else math.nan,
        "mean_tool_calls": statistics.fmean(t["n_tool_calls"] for t in trials) if trials else math.nan,
    }


def secs(x: float) -> str:
    return "–" if math.isnan(x) else f"{x:.0f} s"


def pct(r: dict) -> str:
    return "–" if math.isnan(r["rate"]) else f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']})"


def main():
    files = sorted(RESULTS_DIR.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"No results in {RESULTS_DIR}. Run `make bench` first.")
    summary = {}
    for f in files:
        trials = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        if not trials:
            continue
        model = trials[0]["model"]
        summary[model] = summarize(trials)
        log.info("%s: %d trials", model, len(trials))

    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=1))

    order = sorted(summary, key=lambda m: (summary[m]["hallucination"]["rate"] if not math.isnan(summary[m]["hallucination"]["rate"]) else 9, -summary[m]["accuracy_all"]["rate"]))
    lines = [
        "| Model | Trials | Hallucinated (absent titles) | Correct (held) | Correct (absent) | Unsure | Used primo_search | Tool error in trial | Fabricated link | Median latency |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in order:
        s = summary[m]
        lines.append(
            f"| `{m}` | {s['n_trials']} | {pct(s['hallucination'])} | {pct(s['accuracy_held'])} | {pct(s['accuracy_absent'])} | "
            f"{pct(s['unsure'])} | {pct(s['used_primo'])} | {pct(s['any_tool_error'])} | {pct(s['fabricated_link'])} | {secs(s['latency_median_s'])} |"
        )
    md = "\n".join(lines) + "\n"
    (RESULTS_DIR / "summary.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
