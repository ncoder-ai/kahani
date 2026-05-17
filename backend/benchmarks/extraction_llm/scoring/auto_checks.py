"""Deterministic checks on extraction-LLM output.

Cheap, runs on every output. Returns a dict of {check_name: bool|str|num}.
Schema-aware: dispatches on `expected_schema.type` from the fixture.

These checks catch the failure modes that cost us hours in prod:
- JSON nesting (small models return dicts where strings expected)
- Missing required keys
- Enum violations
- Output that doesn't even parse

Semantic correctness ("did it get the right answer") is the judge's job — see scoring/judge.py (Phase 3).
"""
from __future__ import annotations

import json
import re
from typing import Any


def strip_thinking_and_fences(raw: str) -> str:
    """Match kahani's robust JSON extraction — strips <think> tags + ```json fences."""
    text = raw
    # Strip common thinking tags
    for tag_open, tag_close in [
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
        ("<reasoning>", "</reasoning>"),
    ]:
        if tag_open in text and tag_close in text:
            idx = text.index(tag_close) + len(tag_close)
            text = text[idx:]
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def try_parse_json(raw: str) -> tuple[bool, Any]:
    """Try to parse JSON. Returns (parsed_ok, value-or-None)."""
    cleaned = strip_thinking_and_fences(raw)
    try:
        return True, json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find the first {...} or [...] block
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            try:
                return True, json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return False, None


def _has_nested_objects_where_strings_expected(parsed: Any, flat_string_fields: list[str]) -> list[str]:
    """Return names of fields that contain dicts when strings were expected."""
    violations = []
    if not isinstance(parsed, dict):
        return violations
    for field in flat_string_fields:
        if field in parsed:
            val = parsed[field]
            # Lists of strings are fine; lists of dicts are not (for known flat fields)
            if isinstance(val, dict):
                violations.append(field)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        violations.append(f"{field}[]")
                        break
    return violations


def check_decompose(parsed: Any, schema: dict) -> dict[str, Any]:
    """T1 semantic decompose: intent enum + queries list."""
    out = {}
    if not isinstance(parsed, dict):
        out["schema_ok"] = False
        out["schema_reason"] = "not an object"
        return out
    intent = parsed.get("intent")
    queries = parsed.get("queries")
    out["has_intent"] = intent is not None
    out["intent_value"] = intent if isinstance(intent, str) else None
    out["enum_in_set"] = intent in {"direct", "recall", "react"}
    out["has_queries"] = isinstance(queries, list)
    out["query_count"] = len(queries) if isinstance(queries, list) else 0
    expected_intent = schema.get("expected_intent")
    if expected_intent:
        out["intent_matches_expected"] = intent == expected_intent
    if "min_queries" in schema and out["has_queries"]:
        out["queries_in_range"] = (
            schema["min_queries"] <= out["query_count"] <= schema.get("max_queries", 99)
        )
    out["schema_ok"] = out["has_intent"] and out["has_queries"] and out["enum_in_set"]
    return out


def check_working_memory(parsed: Any, schema: dict) -> dict[str, Any]:
    """T5: flat strings, not nested objects."""
    out = {}
    if not isinstance(parsed, dict):
        out["schema_ok"] = False
        out["schema_reason"] = "not an object"
        return out
    flat_fields = schema.get("flat_string_fields", ["recent_focus"])
    nesting_violations = _has_nested_objects_where_strings_expected(parsed, flat_fields)
    out["no_nesting"] = not nesting_violations
    out["nesting_violations"] = nesting_violations
    # Lists of strings check
    list_fields = schema.get("list_of_strings_fields", [])
    for field in list_fields:
        if field in parsed:
            val = parsed[field]
            out[f"{field}_is_list_of_strings"] = (
                isinstance(val, list) and all(isinstance(x, str) for x in val)
            )
    out["schema_ok"] = out["no_nesting"]
    return out


def check_entity_state(parsed: Any, schema: dict) -> dict[str, Any]:
    """T9: entity state batch — character/location/object lists with flat string fields."""
    out = {}
    if not isinstance(parsed, dict):
        out["schema_ok"] = False
        return out
    # Common shape: {characters: [...], locations: [...], objects: [...]}
    # Each character record should have string fields, not nested dicts (except relationship_changes).
    char_list = parsed.get("characters", [])
    out["has_characters_list"] = isinstance(char_list, list)
    if isinstance(char_list, list):
        out["character_count"] = len(char_list)
        # Check each character has string-valued primary fields
        nested = 0
        for c in char_list:
            if not isinstance(c, dict):
                continue
            for k in ("location", "emotional_state", "physical_condition"):
                if isinstance(c.get(k), dict):
                    nested += 1
        out["no_nesting_in_chars"] = nested == 0
        out["nested_field_count"] = nested
    out["schema_ok"] = out["has_characters_list"] and out.get("no_nesting_in_chars", True)
    return out


def check_plot_progress(parsed: Any, schema: dict) -> dict[str, Any]:
    """T8: indexed true/false dict, e.g. {"1": true, "2": false}."""
    out = {}
    if not isinstance(parsed, dict):
        # Legacy array format is also accepted
        if isinstance(parsed, list):
            out["legacy_array_format"] = True
            out["schema_ok"] = True
            return out
        out["schema_ok"] = False
        return out
    keys = list(parsed.keys())
    out["all_keys_are_numeric"] = all(k.isdigit() for k in keys)
    out["all_values_are_bool"] = all(isinstance(v, bool) for v in parsed.values())
    out["key_count"] = len(keys)
    out["schema_ok"] = out["all_keys_are_numeric"] and out["all_values_are_bool"]
    return out


def check_moderation(parsed: Any, schema: dict) -> dict[str, Any]:
    """[LEGACY] JSON-shaped moderation (kept for backward compat with old fixtures)."""
    out = {}
    if not isinstance(parsed, dict):
        out["schema_ok"] = False
        return out
    blocked = parsed.get("is_blocked")
    out["has_is_blocked"] = isinstance(blocked, bool)
    out["has_reason"] = isinstance(parsed.get("reason"), str)
    expected = schema.get("expected_block")
    if expected is not None and isinstance(blocked, bool):
        out["matches_expected_block"] = blocked == expected
    out["schema_ok"] = out["has_is_blocked"]
    return out


def check_allow_block_token(raw_output: str, schema: dict) -> dict[str, Any]:
    """T7 in production form: parses plaintext ALLOW or BLOCK token.

    Mirrors `content_filter.py:_verdict_is_block` — fail-open if neither
    token is present (matches production safety: don't block on garbled output).
    """
    text = (raw_output or "").strip().upper()
    has_block = "BLOCK" in text
    has_allow = "ALLOW" in text
    # Production rule: BLOCK wins if both appear (defensive)
    if has_block:
        verdict_block = True
    elif has_allow:
        verdict_block = False
    else:
        verdict_block = False  # fail-open
    out: dict[str, Any] = {
        "has_block_token": has_block,
        "has_allow_token": has_allow,
        "verdict_block": verdict_block,
        "schema_ok": has_block or has_allow,  # one or the other must be present
    }
    expected = schema.get("expected_block")
    if expected is not None:
        out["matches_expected_block"] = verdict_block == expected
    return out


def check_object_indexed_bools(parsed: Any, schema: dict) -> dict[str, Any]:
    """Alias used in extracted plot_extraction fixture."""
    return check_plot_progress(parsed, schema)


def check_entity_state_batch(parsed: Any, schema: dict) -> dict[str, Any]:
    return check_entity_state(parsed, schema)


# Schema-type → checker dispatcher
SCHEMA_CHECKERS = {
    "decompose": check_decompose,
    "working_memory": check_working_memory,
    "entity_state": check_entity_state,
    "entity_state_batch": check_entity_state_batch,
    "object_indexed_bools": check_object_indexed_bools,
    "plot_progress": check_plot_progress,
    "moderation": check_moderation,
}


def run_auto_checks(raw_output: str, fixture: dict) -> dict[str, Any]:
    """Run all applicable auto-checks for a fixture.

    Returns a flat dict with: parses_json (or N/A for plaintext-token tasks),
    schema_ok, plus schema-specific keys.
    """
    result: dict[str, Any] = {"raw_length": len(raw_output)}
    schema = fixture.get("expected_schema", {}) or {}
    schema_type = schema.get("type")

    # Plaintext-token tasks (e.g. content moderation ALLOW/BLOCK) don't
    # produce JSON — short-circuit to a string-level check.
    if schema_type == "allow_block_token":
        result["parses_json"] = True  # N/A but kept for SUMMARY uniformity
        token_result = check_allow_block_token(raw_output, schema)
        result.update(token_result)
        return result

    parsed_ok, parsed = try_parse_json(raw_output)
    result["parses_json"] = parsed_ok
    if not parsed_ok:
        result["schema_ok"] = False
        result["schema_reason"] = "did not parse"
        return result

    checker = SCHEMA_CHECKERS.get(schema_type)
    if checker is None:
        result["schema_ok"] = True
        result["schema_note"] = f"no checker registered for type={schema_type!r}"
        return result

    type_result = checker(parsed, schema)
    result.update(type_result)
    return result
