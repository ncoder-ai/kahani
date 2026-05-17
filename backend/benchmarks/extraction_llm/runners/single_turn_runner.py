"""Run a single-turn fixture N times against an extraction endpoint.

Used by all suites except T2 (recall agent), which has its own multi-turn
replay runner (Phase 4).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Make the harness root importable when this runs as a script
HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
sys.path.insert(0, str(HARNESS_ROOT))

from runners.base_runner import CallResult, call_chat_completion  # noqa: E402
from scoring.auto_checks import run_auto_checks  # noqa: E402


@dataclass
class RunRecord:
    model_label: str
    task: str
    case_id: str
    run_idx: int
    raw_output: str
    elapsed_s: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tokens_per_sec: float
    finish_reason: str
    error: str | None
    error_kind: str | None
    auto_checks: dict[str, Any] = field(default_factory=dict)
    fixture_source: str = ""


def load_fixture(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def iter_fixtures(fixtures_root: Path) -> list[tuple[str, Path]]:
    """Walk fixtures_root and yield (suite_dir_name, fixture_path).

    Skips:
    - Files starting with `_` (e.g. _raw_scenes/ — not a real suite yet)
    - The README.md
    - The T2_recall_agent suite (different runner)
    """
    out: list[tuple[str, Path]] = []
    for suite_dir in sorted(fixtures_root.iterdir()):
        if not suite_dir.is_dir():
            continue
        if suite_dir.name.startswith("_"):
            continue
        if suite_dir.name == "T2_recall_agent":
            continue
        for f in sorted(suite_dir.glob("*.json")):
            out.append((suite_dir.name, f))
    return out


def run_one(
    fixture: dict,
    endpoint: str,
    timeout_s: float,
    model_label: str,
    run_idx: int,
    inference_path: str = "/v1/chat/completions",
    thinking_disable: str | None = None,
) -> RunRecord:
    """Run one fixture once against the endpoint, return a populated RunRecord."""
    result: CallResult = call_chat_completion(
        endpoint=endpoint,
        messages=fixture["messages"],
        request_params=fixture.get("request_params", {}),
        timeout_s=timeout_s,
        inference_path=inference_path,
        model_label=model_label,
        thinking_disable=thinking_disable,
    )
    auto = {}
    if result.raw_output:
        try:
            auto = run_auto_checks(result.raw_output, fixture)
        except Exception as exc:  # noqa: BLE001
            auto = {"checker_error": str(exc)}
    return RunRecord(
        model_label=model_label,
        task=fixture["task"],
        case_id=fixture["case_id"],
        run_idx=run_idx,
        raw_output=result.raw_output,
        elapsed_s=result.elapsed_s,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        tokens_per_sec=result.tokens_per_sec,
        finish_reason=result.finish_reason,
        error=result.error,
        error_kind=result.error_kind,
        auto_checks=auto,
        fixture_source=fixture.get("source", ""),
    )


def write_record(report_dir: Path, record: RunRecord) -> Path:
    """Persist one run record to disk."""
    suite_dir = report_dir / record.task
    suite_dir.mkdir(parents=True, exist_ok=True)
    out_path = suite_dir / f"{record.case_id}_run{record.run_idx}.json"
    with out_path.open("w") as f:
        json.dump(asdict(record), f, indent=2, ensure_ascii=False)
    return out_path
