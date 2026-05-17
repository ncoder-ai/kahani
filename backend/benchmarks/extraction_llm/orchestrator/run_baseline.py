#!/usr/bin/env python3
"""Run all single-turn fixtures against the currently-loaded extraction LLM.

Usage:
    python orchestrator/run_baseline.py --label ministral-8b-q8
    python orchestrator/run_baseline.py --label qwen3.5-4b-q5 --runs 3

Reads config.yaml for endpoint + run settings. Writes per-run JSON records
under reports/<label>_<timestamp>/, plus a SUMMARY.md / SUMMARY.csv aggregated
across all runs.

Does NOT swap models — assumes you've already started llama-server with
the model you want to test (use orchestrator/launch_model.sh first).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from statistics import mean

import yaml

HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
sys.path.insert(0, str(HARNESS_ROOT))

from runners.single_turn_runner import (  # noqa: E402
    iter_fixtures, load_fixture, run_one, write_record,
)
from runners.base_runner import wait_for_endpoint, check_thinking_health  # noqa: E402


def load_config() -> dict:
    """Load config.yaml and expand ${MODELS_DIR} / ${HOME} placeholders.

    MODELS_DIR defaults to ${HOME}/App/kobold but can be overridden via env.
    """
    raw = (HARNESS_ROOT / "config.yaml").read_text()
    home = os.environ.get("HOME", str(Path.home()))
    models_dir = os.environ.get("MODELS_DIR", f"{home}/App/kobold")
    raw = raw.replace("${MODELS_DIR}", models_dir).replace("${HOME}", home)
    return yaml.safe_load(raw)


def aggregate_summary(records: list, report_dir: Path) -> None:
    """Aggregate per-run records into SUMMARY.md + SUMMARY.csv."""
    by_case: dict[tuple[str, str], list] = {}
    for r in records:
        by_case.setdefault((r.task, r.case_id), []).append(r)

    rows = []
    for (task, case_id), runs in sorted(by_case.items()):
        successes = [r for r in runs if not r.error]
        n = len(runs)
        n_ok = len(successes)
        parses = sum(1 for r in successes if r.auto_checks.get("parses_json"))
        schemas = sum(1 for r in successes if r.auto_checks.get("schema_ok"))
        latencies = [r.elapsed_s for r in successes]
        tps = [r.tokens_per_sec for r in successes if r.tokens_per_sec]
        compl_tokens = [r.completion_tokens for r in successes if r.completion_tokens]
        rows.append({
            "task": task,
            "case_id": case_id,
            "runs": n,
            "ok": n_ok,
            "parses_json_rate": parses / n if n else 0,
            "schema_ok_rate": schemas / n if n else 0,
            "mean_latency_s": round(mean(latencies), 3) if latencies else None,
            "mean_tokens_per_sec": round(mean(tps), 2) if tps else None,
            "mean_completion_tokens": round(mean(compl_tokens), 1) if compl_tokens else None,
        })

    # CSV
    csv_path = report_dir / "SUMMARY.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    # Markdown
    md_path = report_dir / "SUMMARY.md"
    lines = [
        f"# Benchmark report — {report_dir.name}",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "## Per-case summary",
        "",
        "| Task | Case | Runs | OK | Parse | Schema | Mean latency | tok/s | Compl tokens |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {task} | {case_id} | {runs} | {ok} | "
            "{p:.0%} | {s:.0%} | {lat}s | {tps} | {ct} |".format(
                task=r["task"], case_id=r["case_id"], runs=r["runs"], ok=r["ok"],
                p=r["parses_json_rate"], s=r["schema_ok_rate"],
                lat=r["mean_latency_s"] if r["mean_latency_s"] is not None else "—",
                tps=r["mean_tokens_per_sec"] if r["mean_tokens_per_sec"] is not None else "—",
                ct=r["mean_completion_tokens"] if r["mean_completion_tokens"] is not None else "—",
            )
        )

    # Per-task rollup
    by_task: dict[str, list] = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)

    lines += ["", "## Per-task rollup", "", "| Task | Cases | Parse rate | Schema rate | Mean latency |", "|---|---|---|---|---|"]
    for task, task_rows in sorted(by_task.items()):
        parse_rate = mean(r["parses_json_rate"] for r in task_rows)
        schema_rate = mean(r["schema_ok_rate"] for r in task_rows)
        lats = [r["mean_latency_s"] for r in task_rows if r["mean_latency_s"] is not None]
        lat = mean(lats) if lats else None
        lines.append(
            "| {task} | {n} | {p:.0%} | {s:.0%} | {lat} |".format(
                task=task, n=len(task_rows), p=parse_rate, s=schema_rate,
                lat=f"{lat:.2f}s" if lat is not None else "—",
            )
        )

    md_path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run benchmark battery against currently-loaded extraction LLM.")
    parser.add_argument("--label", required=True,
                        help="Label for this run (e.g. ministral-8b-q8, qwen3.5-4b-q5)")
    parser.add_argument("--runs", type=int, default=None,
                        help="Override runs_per_fixture from config.yaml")
    parser.add_argument("--filter", default=None,
                        help="Run only suites matching this substring (e.g. 'T1' or 'working_memory')")
    parser.add_argument("--skip-wait", action="store_true",
                        help="Skip health-check wait (use if endpoint is known up)")
    parser.add_argument("--no-preflight", action="store_true",
                        help="Skip the thinking-mode preflight check (debugging only)")
    parser.add_argument("--endpoint", default=None,
                        help="Override endpoint URL (default: from config.yaml)")
    args = parser.parse_args()

    config = load_config()
    endpoint = args.endpoint or config["endpoint"]["url"]
    inference_path = config["endpoint"]["inference_path"]
    health_path = config["endpoint"]["health_path"]
    runs_per_fixture = args.runs or config["run_settings"]["runs_per_fixture"]
    per_case_timeout = config["run_settings"]["per_case_timeout_s"]

    if not args.skip_wait:
        print(f"Checking {endpoint}{health_path}...")
        if not wait_for_endpoint(endpoint, timeout_s=15, health_path=health_path):
            print(f"ERROR: endpoint not reachable at {endpoint}")
            return 1
        print("Endpoint is up.")

    # Pre-flight: catch thinking-mode misconfiguration before running 100s of
    # fixtures with empty outputs. Looks up the model entry in config.yaml by
    # --label and applies its thinking_disable setting. Skip if --no-preflight.
    thinking_disable_for_model = None
    model_entry = next((m for m in config.get("models", []) if m.get("label") == args.label), None)
    if model_entry:
        thinking_disable_for_model = model_entry.get("thinking_disable")
    if not args.no_preflight:
        ok, msg = check_thinking_health(
            endpoint=endpoint,
            model_label=args.label,
            thinking_disable=thinking_disable_for_model,
            inference_path=inference_path,
        )
        if not ok:
            print(f"ERROR: preflight thinking-health check failed: {msg}")
            print("       To bypass (debugging only) pass --no-preflight.")
            return 1
        print(f"Preflight: {msg}")

    fixtures_root = HARNESS_ROOT / "fixtures"
    fixture_paths = iter_fixtures(fixtures_root)
    if args.filter:
        fixture_paths = [(s, p) for s, p in fixture_paths if args.filter in s or args.filter in p.name]
    if not fixture_paths:
        print("No fixtures matched. Did you run extract_fixtures.py?")
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = HARNESS_ROOT / "reports" / f"{args.label}_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    print(f"Report dir: {report_dir}")
    print(f"Found {len(fixture_paths)} fixtures, {runs_per_fixture} runs each = {len(fixture_paths) * runs_per_fixture} calls")
    print()

    all_records = []
    start_total = time.time()
    for suite_name, fixture_path in fixture_paths:
        try:
            fixture = load_fixture(fixture_path)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! failed to load {fixture_path}: {exc}")
            continue

        for run_idx in range(1, runs_per_fixture + 1):
            record = run_one(
                fixture=fixture,
                endpoint=endpoint,
                timeout_s=per_case_timeout,
                model_label=args.label,
                run_idx=run_idx,
                inference_path=inference_path,
                thinking_disable=thinking_disable_for_model,
            )
            all_records.append(record)
            write_record(report_dir, record)
            status = "ok"
            if record.error:
                status = f"ERR({record.error_kind})"
            elif not record.auto_checks.get("parses_json", False):
                status = "parse_fail"
            elif not record.auto_checks.get("schema_ok", False):
                status = "schema_fail"
            print(
                f"  [{suite_name}/{fixture['case_id']}] run {run_idx}/{runs_per_fixture}: "
                f"{status}  {record.elapsed_s}s  "
                f"{record.completion_tokens}t/{record.tokens_per_sec}tps"
            )

    aggregate_summary(all_records, report_dir)
    total_elapsed = time.time() - start_total
    print(f"\nDone. {len(all_records)} runs in {total_elapsed:.1f}s.")
    print(f"Summary: {report_dir / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
