#!/usr/bin/env python3
"""Compare benchmark reports side-by-side across models.

Usage:
    python orchestrator/compare.py reports/ministral-8b-q8-*/SUMMARY.csv \\
                                    reports/qwen3.5-4b-q5_*/SUMMARY.csv \\
                                    reports/qwen3.5-4b-q8_*/SUMMARY.csv \\
                                    reports/gemma-4-e4b-q5_*/SUMMARY.csv \\
                                    reports/gemma-4-e4b-q8_*/SUMMARY.csv

Without args, it auto-discovers the latest report dir per model label.

Output: a markdown comparison table per task suite to stdout, plus a
COMPARISON.md saved into the most-recent report's parent directory.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
REPORTS = HARNESS_ROOT / "reports"


def latest_report_per_label() -> dict[str, Path]:
    """Find the latest SUMMARY.csv per model label."""
    pattern = re.compile(r"^(?P<label>[a-z0-9._-]+?)_\d{8}_\d{6}$")
    latest: dict[str, Path] = {}
    if not REPORTS.exists():
        return latest
    for d in REPORTS.iterdir():
        if not d.is_dir():
            continue
        m = pattern.match(d.name)
        if not m:
            continue
        label = m.group("label")
        summary = d / "SUMMARY.csv"
        if not summary.exists():
            continue
        if label not in latest or d.name > latest[label].parent.name:
            latest[label] = summary
    return latest


def load_summary(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def aggregate_by_task(rows: list[dict]) -> dict[str, dict]:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_task[r["task"]].append(r)
    out = {}
    for task, runs in by_task.items():
        parse = mean(float(r["parses_json_rate"]) for r in runs)
        schema = mean(float(r["schema_ok_rate"]) for r in runs)
        latencies = [float(r["mean_latency_s"]) for r in runs if r["mean_latency_s"]]
        tps = [float(r["mean_tokens_per_sec"]) for r in runs if r["mean_tokens_per_sec"]]
        out[task] = {
            "cases": len(runs),
            "parse": parse,
            "schema": schema,
            "latency": mean(latencies) if latencies else None,
            "tps": mean(tps) if tps else None,
        }
    return out


def build_comparison(model_aggregates: dict[str, dict[str, dict]]) -> str:
    """Build a markdown comparison report."""
    all_tasks = sorted({t for agg in model_aggregates.values() for t in agg})
    models = list(model_aggregates.keys())

    lines = ["# Benchmark comparison", "",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
             "Models compared:"]
    for label in models:
        lines.append(f"- `{label}`")
    lines += ["", "Pass-rate format: parse / schema (auto-checks only — judge layer is Phase 3)"]
    lines.append("")

    # Per-task table
    lines += ["## Per-task pass rates", "",
              "| Task | " + " | ".join(models) + " |",
              "|---|" + "|".join(["---"] * len(models)) + "|"]
    for task in all_tasks:
        cells = []
        for label in models:
            agg = model_aggregates[label].get(task)
            if agg is None:
                cells.append("—")
            else:
                cells.append(f"{agg['parse']*100:.0f}% / {agg['schema']*100:.0f}%")
        lines.append(f"| {task} | " + " | ".join(cells) + " |")

    # Latency table
    lines += ["", "## Mean latency per task (seconds)", "",
              "| Task | " + " | ".join(models) + " |",
              "|---|" + "|".join(["---"] * len(models)) + "|"]
    for task in all_tasks:
        cells = []
        for label in models:
            agg = model_aggregates[label].get(task)
            if agg is None or agg["latency"] is None:
                cells.append("—")
            else:
                cells.append(f"{agg['latency']:.2f}")
        lines.append(f"| {task} | " + " | ".join(cells) + " |")

    # Throughput table
    lines += ["", "## Mean throughput (tok/s)", "",
              "| Task | " + " | ".join(models) + " |",
              "|---|" + "|".join(["---"] * len(models)) + "|"]
    for task in all_tasks:
        cells = []
        for label in models:
            agg = model_aggregates[label].get(task)
            if agg is None or agg["tps"] is None:
                cells.append("—")
            else:
                cells.append(f"{agg['tps']:.1f}")
        lines.append(f"| {task} | " + " | ".join(cells) + " |")

    # Overall summary
    lines += ["", "## Per-model rollup", "",
              "| Model | Suites | Mean parse | Mean schema | Mean latency | Mean tok/s |",
              "|---|---|---|---|---|---|"]
    for label in models:
        agg = model_aggregates[label]
        if not agg:
            continue
        parses = [v["parse"] for v in agg.values()]
        schemas = [v["schema"] for v in agg.values()]
        lats = [v["latency"] for v in agg.values() if v["latency"] is not None]
        tpss = [v["tps"] for v in agg.values() if v["tps"] is not None]
        lines.append(
            f"| {label} | {len(agg)} | "
            f"{mean(parses)*100:.0f}% | {mean(schemas)*100:.0f}% | "
            f"{mean(lats):.2f}s | {mean(tpss):.1f} |"
        )

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Compare benchmark reports side-by-side")
    parser.add_argument("summaries", nargs="*",
                        help="Paths to SUMMARY.csv files (omit to auto-discover latest per label)")
    parser.add_argument("--save", type=Path, default=None,
                        help="Save COMPARISON.md to this path (default: reports/COMPARISON_<timestamp>.md)")
    args = parser.parse_args()

    if args.summaries:
        summary_paths = {Path(p).parent.name.rsplit("_", 2)[0]: Path(p) for p in args.summaries}
    else:
        summary_paths = latest_report_per_label()

    if not summary_paths:
        print("No SUMMARY.csv files found. Run a battery first.")
        return 1

    print(f"Comparing {len(summary_paths)} models:")
    for label, p in summary_paths.items():
        print(f"  {label}: {p.parent.name}")
    print()

    model_aggregates = {
        label: aggregate_by_task(load_summary(p))
        for label, p in summary_paths.items()
    }

    md = build_comparison(model_aggregates)
    print(md)

    out_path = args.save or (REPORTS / f"COMPARISON_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    out_path.write_text(md)
    print(f"\nSaved to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
