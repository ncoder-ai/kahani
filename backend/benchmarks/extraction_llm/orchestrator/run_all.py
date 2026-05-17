#!/usr/bin/env python3
"""Run the full benchmark battery across every enabled model in config.yaml.

For each model: teardown current llama-server → launch this model →
wait for health → run baseline.py → record path to report.

Usage:
    python orchestrator/run_all.py                  # all enabled models
    python orchestrator/run_all.py --only qwen      # only models whose label matches 'qwen'
    python orchestrator/run_all.py --skip-baseline  # don't re-run the baseline
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
sys.path.insert(0, str(HARNESS_ROOT))

from runners.base_runner import wait_for_endpoint  # noqa: E402
import yaml  # noqa: E402


def load_config() -> dict:
    raw = (HARNESS_ROOT / "config.yaml").read_text()
    home = os.environ.get("HOME", str(Path.home()))
    models_dir = os.environ.get("MODELS_DIR", f"{home}/App/kobold")
    raw = raw.replace("${MODELS_DIR}", models_dir).replace("${HOME}", home)
    return yaml.safe_load(raw)


def teardown(port: int) -> None:
    script = HERE / "teardown.sh"
    subprocess.run([str(script), str(port)], check=False)


def launch(model_path: str, ctx_size: int, port: int) -> subprocess.Popen:
    script = HERE / "launch_model.sh"
    log_path = HARNESS_ROOT / "reports" / f"launch_{Path(model_path).stem}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    f = log_path.open("w")
    proc = subprocess.Popen(
        [str(script), model_path, str(ctx_size), str(port)],
        stdout=f, stderr=subprocess.STDOUT,
    )
    return proc


def run_battery(label: str, endpoint: str) -> int:
    script = HERE / "run_baseline.py"
    cmd = [
        sys.executable, str(script),
        "--label", label,
        "--endpoint", endpoint,
        "--skip-wait",
    ]
    return subprocess.run(cmd, check=False).returncode


def main():
    parser = argparse.ArgumentParser(description="Run benchmark battery across all enabled models")
    parser.add_argument("--only", default=None, help="Substring filter on model label")
    parser.add_argument("--skip-baseline", action="store_true",
                        help="Skip re-running the baseline model")
    parser.add_argument("--port", type=int, default=5002, help="Port for llama-server")
    args = parser.parse_args()

    config = load_config()
    endpoint = config["endpoint"]["url"]
    health_path = config["endpoint"]["health_path"]

    models = [m for m in config["models"] if m.get("enabled", True)]
    if args.only:
        models = [m for m in models if args.only.lower() in m["label"].lower()]
    if args.skip_baseline:
        models = [m for m in models if m.get("role") != "baseline"]
    if not models:
        print("No models matched. Check config.yaml `enabled:` flags and --only filter.")
        return 1

    print(f"Will benchmark {len(models)} models on port {args.port}:")
    for m in models:
        print(f"  - {m['label']} ({m.get('role','?')})  →  {m['path']}")
    print()

    summary = []
    for i, m in enumerate(models, start=1):
        label = m["label"]
        path = m["path"]
        ctx_size = m.get("ctx_size", 32768)

        print(f"\n{'='*70}\n[{i}/{len(models)}] {label}\n{'='*70}")

        if not Path(path).exists():
            print(f"  ! GGUF not found at {path} — skipping")
            summary.append((label, "skipped (missing GGUF)", None))
            continue

        print(f"  step 1: teardown port {args.port}")
        teardown(args.port)

        print(f"  step 2: launch {Path(path).name}")
        proc = launch(path, ctx_size, args.port)

        print(f"  step 3: wait for health (up to 60s)")
        if not wait_for_endpoint(endpoint, timeout_s=60, health_path=health_path):
            print(f"  ! health check failed — see launch log")
            proc.terminate()
            summary.append((label, "failed to start", None))
            continue

        # Give it a moment to fully initialize the KV cache
        time.sleep(2)

        print(f"  step 4: run battery")
        rc = run_battery(label, endpoint)
        if rc == 0:
            print(f"  ok ✓")
            summary.append((label, "ok", "reports/"))
        else:
            print(f"  ! battery exited with code {rc}")
            summary.append((label, f"battery exit {rc}", None))

    print(f"\n{'='*70}\nFinal teardown\n{'='*70}")
    teardown(args.port)

    print(f"\n{'='*70}\nSummary\n{'='*70}")
    for label, status, reports in summary:
        print(f"  {label:30}  {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
