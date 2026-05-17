#!/usr/bin/env python3
"""Render benchmark fixtures using REAL prompt templates from backend/prompts.yml.

Each fixture this writes uses the same system/user prompt strings that
kahani sends in production — pulled straight from prompts.yml and rendered
with real scene content from `_scenes_pool/` (DB-extracted SFW + NSFW scenes).

This is the corrected approach. Earlier `extract_fixtures.py` synthetic probes
used hand-written prompts that approximated production — those are only useful
as supplementary edge-case coverage, never as substitutes for the real templates.

Each task documents:
- Which prompt key in prompts.yml it pulls from
- Which placeholders it fills (mirroring the production call site)

The format produced is always `[system, user]` — the 2-message simple form
that the extraction LLM actually receives in production (cache-friendly
multi-message variants are MAIN-LLM-only because Ministral's strict Jinja
template rejects consecutive user messages).

Usage:
    python orchestrator/render_real_fixtures.py [--force]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
KAHANI_ROOT = HARNESS_ROOT.parent.parent.parent  # repo root
PROMPTS_YML = KAHANI_ROOT / "backend" / "prompts.yml"
SCENES_POOL = HARNESS_ROOT / "fixtures" / "_scenes_pool"


def load_prompts() -> dict:
    with PROMPTS_YML.open() as f:
        return yaml.safe_load(f)


def get_nested(prompts: dict, dotted_key: str) -> str | None:
    """Resolve a dotted key like 'entity_state_extraction.single.user'."""
    cur = prompts
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, str) else None


def load_scenes_pool() -> list[dict]:
    """Load every scene fixture from _scenes_pool/."""
    scenes = []
    for f in sorted(SCENES_POOL.glob("*.json")):
        if f.name == "README.md":
            continue
        with f.open() as fh:
            scenes.append(json.load(fh))
    return scenes


def write_fixture(suite_dir: Path, case_label: str, fixture: dict, force: bool) -> bool:
    suite_dir.mkdir(parents=True, exist_ok=True)
    path = suite_dir / f"{case_label}.json"
    if path.exists() and not force:
        return False
    with path.open("w") as f:
        json.dump(fixture, f, indent=2, ensure_ascii=False)
    return True


def render_t4_scene_events(prompts: dict, scenes: list[dict], force: bool) -> int:
    """T4 — `scene_event_extraction.cache_friendly.user` is the user task.

    The cache-friendly template has only a user block (no system). For the
    extraction LLM (simple 2-msg form), production builds a minimal system
    prompt — we mirror that here. The user template expects {scene_content}.
    """
    user_template = get_nested(prompts, "scene_event_extraction.cache_friendly.user")
    if not user_template:
        print("  ! T4: scene_event_extraction.cache_friendly.user not found")
        return 0
    # Minimal system prompt mirroring what kahani uses when sending the
    # cache-friendly user task to extraction LLM in standalone form.
    system_msg = (
        "You extract scene-level events for semantic search and memory indexing. "
        "Return ONLY valid JSON. Use blunt, searchable vocabulary — never literary euphemism."
    )
    suite_dir = HARNESS_ROOT / "fixtures" / "T4_scene_events"
    written = 0
    for sc in scenes:
        scene = sc["scene"]
        content = scene["content"]
        chars = scene.get("characters_present") or ["protagonist"]
        try:
            user_msg = user_template.format(
                scene_content=content,
                character_names=", ".join(str(c) for c in chars),
            )
        except KeyError as exc:
            print(f"  ! T4 template missing placeholder: {exc}")
            return written
        case_label = f"{sc['case_id']}"
        fixture = {
            "task": "T4_scene_events",
            "case_id": case_label,
            "source": f"rendered from prompts.yml scene_event_extraction.cache_friendly + {sc['source']}",
            "story_meta": sc["story_meta"],
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "request_params": {"temperature": 0.3, "max_tokens": 1500},
            "expected_schema": {"type": "scene_events_list"},
        }
        if write_fixture(suite_dir, case_label, fixture, force):
            written += 1
    print(f"  + T4 scene_events: {written} fixtures from prompts.yml")
    return written


def render_t5_working_memory(prompts: dict, scenes: list[dict], force: bool) -> int:
    """T5 — production path uses `working_memory_cache_friendly.user`.

    Production source: `service.py:extract_working_memory_cache_friendly()` line 3438.
    System prompt is hardcoded in `service.py:3446` (see EXTRACTION_ISSUES.md #1
    and #3 — should be moved to prompts.yml as `working_memory_cache_friendly.system`).
    Placeholders in the user template: {scene_content}, {current_focus}.

    NOTE: the legacy `working_memory_update.user` template (also in prompts.yml)
    is the non-cache-friendly fallback and is NOT what production sends.
    """
    # Hardcoded system prompt — pulled verbatim from service.py:3446
    system_msg = (
        "You extract working memory updates (narrative focus and character "
        "spotlight) from story scenes. Return only valid JSON."
    )
    user_template = get_nested(prompts, "working_memory_cache_friendly.user")
    if not user_template:
        print("  ! T5: working_memory_cache_friendly.user not found in prompts.yml")
        return 0
    suite_dir = HARNESS_ROOT / "fixtures" / "T5_working_memory"
    written = 0
    # Group by story so we can use the previous-pool-scene as `current_focus`
    by_story: dict[int, list[dict]] = {}
    for sc in scenes:
        by_story.setdefault(sc["story_meta"]["story_id"], []).append(sc)
    for sid, story_scenes in by_story.items():
        story_scenes.sort(key=lambda s: s["scene"]["sequence_number"])
        for i, sc in enumerate(story_scenes):
            prev_focus = (
                story_scenes[i - 1]["scene"]["content"][:400]
                if i > 0
                else "(first scene — no prior focus)"
            )
            try:
                user_msg = user_template.format(
                    scene_content=sc["scene"]["content"],
                    current_focus=prev_focus,
                )
            except KeyError as exc:
                print(f"  ! T5 template missing placeholder: {exc}")
                return written
            case_label = f"{sc['case_id']}"
            fixture = {
                "task": "T5_working_memory",
                "case_id": case_label,
                "source": f"rendered from prompts.yml working_memory_cache_friendly + {sc['source']}",
                "story_meta": sc["story_meta"],
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                # max_tokens=512 + temperature=0.3 match production
                # (service.py:extract_working_memory_cache_friendly line 3469-3470).
                "request_params": {"temperature": 0.3, "max_tokens": 512},
                "expected_schema": {
                    "type": "working_memory",
                    "flat_string_fields": ["recent_focus"],
                    "list_of_strings_fields": ["pending_items"],
                },
            }
            if write_fixture(suite_dir, case_label, fixture, force):
                written += 1
    print(f"  + T5 working_memory: {written} fixtures from prompts.yml")
    return written


def render_t7_content_moderation(prompts: dict, scenes: list[dict], force: bool) -> int:
    """T7 — `content_moderation.input` and `.output` are PLAIN STRINGS (system prompt).

    The user message is just the text being moderated. Production sends:
      [system=moderation_prompt, user=text_to_moderate]
    We render one fixture per scene against the .output moderator (it
    checks generated text) and a smaller set of user-intent probes against .input.
    """
    output_mod = get_nested(prompts, "content_moderation.output")
    input_mod = get_nested(prompts, "content_moderation.input")
    if not output_mod or not input_mod:
        print("  ! T7: content_moderation.{input,output} not found")
        return 0
    suite_dir = HARNESS_ROOT / "fixtures" / "T7_content_moderation"
    written = 0
    # Production behavior verified in content_filter.py:moderate_content():
    #   - Routes to EXTRACTION LLM first (not main LLM — my inventory was wrong)
    #   - max_tokens=10, temperature=0.0
    #   - Expects plaintext ALLOW or BLOCK (NOT JSON)
    #   - _verdict_is_block parser scans for either token, fail-open if neither
    for sc in scenes:
        text = sc["scene"]["content"][:2000]
        rating = sc["story_meta"]["content_rating"]
        case_label = f"output_{rating}_{sc['case_id']}"
        fixture = {
            "task": "T7_content_moderation",
            "case_id": case_label,
            "source": f"rendered from prompts.yml content_moderation.output + {sc['source']}",
            "story_meta": sc["story_meta"],
            "messages": [
                {"role": "system", "content": output_mod},
                {"role": "user", "content": text},
            ],
            "request_params": {"temperature": 0.0, "max_tokens": 10},
            "expected_schema": {
                "type": "allow_block_token",
                # SFW story scenes should be ALLOWED. NSFW story scenes
                # should usually be BLOCKED — though openings (scene 1) often
                # lack explicit content and may legitimately ALLOW. The auto
                # check reports the verdict; the judge layer (Phase 3) will
                # score borderline cases against reference outputs.
                "expected_block": rating.lower() == "nsfw",
                "stratify_by": "rating",
            },
        }
        if write_fixture(suite_dir, case_label, fixture, force):
            written += 1
    print(f"  + T7 content_moderation: {written} fixtures from prompts.yml")
    return written


def render_t9_entity_state(prompts: dict, scenes: list[dict], force: bool) -> int:
    """T9 — `entity_state_extraction.single.system` + `.user`.

    Placeholders: {scene_sequence}, {scene_content}, {character_names},
    {chapter_location}, {previous_states}.
    """
    system_msg = get_nested(prompts, "entity_state_extraction.single.system")
    user_template = get_nested(prompts, "entity_state_extraction.single.user")
    if not system_msg or not user_template:
        print("  ! T9: entity_state_extraction.single.{system,user} not found")
        return 0
    suite_dir = HARNESS_ROOT / "fixtures" / "T9_entity_state"
    written = 0
    for sc in scenes:
        chars = sc["scene"].get("characters_present") or []
        # characters_present is often empty in DB scenes — synthesize from story
        # genre as a fallback so the prompt has something to anchor on.
        if not chars:
            chars = ["protagonist", "supporting cast"]
        try:
            user_msg = user_template.format(
                scene_sequence=sc["scene"]["sequence_number"],
                scene_content=sc["scene"]["content"],
                character_names=", ".join(str(c) for c in chars),
                chapter_location="Unknown",
                previous_states="(none — first extraction)",
            )
        except KeyError as exc:
            print(f"  ! T9 template missing placeholder: {exc}")
            return written
        case_label = f"{sc['case_id']}"
        fixture = {
            "task": "T9_entity_state",
            "case_id": case_label,
            "source": f"rendered from prompts.yml entity_state_extraction.single + {sc['source']}",
            "story_meta": sc["story_meta"],
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "request_params": {"temperature": 0.3, "max_tokens": 2000},
            "expected_schema": {"type": "entity_state"},
        }
        if write_fixture(suite_dir, case_label, fixture, force):
            written += 1
    print(f"  + T9 entity_state: {written} fixtures from prompts.yml")
    return written


def render_t10_character_moments(prompts: dict, scenes: list[dict], force: bool) -> int:
    """T10a — `character_moments_cache_friendly.user`.

    Placeholders: {scene_content}, {character_names}.
    """
    user_template = get_nested(prompts, "character_moments_cache_friendly.user")
    if not user_template:
        print("  ! T10a: character_moments_cache_friendly.user not found")
        return 0
    system_msg = (
        "You extract character moments (emotional/relational beats) from scenes. "
        "Return only valid JSON."
    )
    suite_dir = HARNESS_ROOT / "fixtures" / "T10_char_moments"
    written = 0
    for sc in scenes:
        chars = sc["scene"].get("characters_present") or ["protagonist"]
        try:
            user_msg = user_template.format(
                scene_content=sc["scene"]["content"],
                character_names=", ".join(str(c) for c in chars),
            )
        except KeyError as exc:
            print(f"  ! T10a template missing placeholder: {exc}")
            return written
        case_label = f"{sc['case_id']}"
        fixture = {
            "task": "T10_char_moments",
            "case_id": case_label,
            "source": f"rendered from prompts.yml character_moments_cache_friendly + {sc['source']}",
            "story_meta": sc["story_meta"],
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "request_params": {"temperature": 0.3, "max_tokens": 1200},
            "expected_schema": {"type": "char_moments"},
        }
        if write_fixture(suite_dir, case_label, fixture, force):
            written += 1
    print(f"  + T10_char_moments: {written} fixtures from prompts.yml")
    return written


def render_t10_npcs(prompts: dict, scenes: list[dict], force: bool) -> int:
    """T10b — `npc_extraction_cache_friendly.user`.

    Placeholders: {scene_content}, {existing_npcs}.
    """
    user_template = get_nested(prompts, "npc_extraction_cache_friendly.user")
    if not user_template:
        print("  ! T10b: npc_extraction_cache_friendly.user not found")
        return 0
    system_msg = (
        "You extract named non-protagonist characters (NPCs) from story scenes. "
        "Return only valid JSON."
    )
    suite_dir = HARNESS_ROOT / "fixtures" / "T10_npcs"
    written = 0
    for sc in scenes:
        try:
            user_msg = user_template.format(
                scene_content=sc["scene"]["content"],
                explicit_names="(none tracked yet)",
            )
        except KeyError as exc:
            print(f"  ! T10b template missing placeholder: {exc}")
            return written
        case_label = f"{sc['case_id']}"
        fixture = {
            "task": "T10_npcs",
            "case_id": case_label,
            "source": f"rendered from prompts.yml npc_extraction_cache_friendly + {sc['source']}",
            "story_meta": sc["story_meta"],
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "request_params": {"temperature": 0.3, "max_tokens": 1200},
            "expected_schema": {"type": "npcs_list"},
        }
        if write_fixture(suite_dir, case_label, fixture, force):
            written += 1
    print(f"  + T10_npcs: {written} fixtures from prompts.yml")
    return written


def remove_synthetic_probes_from_real_suites() -> int:
    """Move synthetic probes into a clearly-labeled subdirectory.

    The previous code wrote synthetic probes alongside real fixtures, which
    is misleading. Now they live in `fixtures/_synthetic_probes/` so they
    can still be run as supplementary edge-case coverage when wanted but
    won't dominate task-level scores.
    """
    moved = 0
    probe_home = HARNESS_ROOT / "fixtures" / "_synthetic_probes"
    probe_home.mkdir(parents=True, exist_ok=True)
    for suite in ["T1_semantic_decompose", "T5_working_memory", "T7_content_moderation"]:
        suite_dir = HARNESS_ROOT / "fixtures" / suite
        if not suite_dir.exists():
            continue
        for f in suite_dir.glob("probe_*.json"):
            target = probe_home / suite / f.name
            target.parent.mkdir(parents=True, exist_ok=True)
            f.rename(target)
            moved += 1
            print(f"  → moved {suite}/{f.name} → _synthetic_probes/")
    return moved


def main():
    parser = argparse.ArgumentParser(description="Render real fixtures from prompts.yml + scene pool")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing rendered fixtures")
    args = parser.parse_args()

    if not PROMPTS_YML.exists():
        print(f"ERROR: {PROMPTS_YML} not found")
        return 1
    if not SCENES_POOL.exists() or not list(SCENES_POOL.glob("*.json")):
        print(f"ERROR: scenes pool empty. Run db_extract_scenes.py first.")
        return 1

    prompts = load_prompts()
    scenes = load_scenes_pool()
    print(f"Loaded {len(scenes)} scenes from pool.")

    print("\n== Moving synthetic probes out of real-suite directories ==")
    remove_synthetic_probes_from_real_suites()

    print("\n== Rendering real fixtures from prompts.yml ==")
    total = 0
    total += render_t4_scene_events(prompts, scenes, args.force)
    total += render_t5_working_memory(prompts, scenes, args.force)
    total += render_t7_content_moderation(prompts, scenes, args.force)
    total += render_t9_entity_state(prompts, scenes, args.force)
    total += render_t10_character_moments(prompts, scenes, args.force)
    total += render_t10_npcs(prompts, scenes, args.force)

    print(f"\nDone. {total} real fixtures rendered from prompts.yml.")
    print("\nFollow-ups (real captures still needed, currently using probes/synthetic):")
    print("  - T1 semantic_decompose: capture from service.py:_maybe_improve_semantic_scenes")
    print("    by patching the decompose call to dump logs/prompt_semantic_decompose.json")
    print("  - T6 chapter_summary: needs full chapter scene batches — separate renderer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
