#!/usr/bin/env python3
"""
Test Few-Shot Extraction Prompts

Tests all updated extraction prompts against a real scene from story 5.
Tests both prompt loading (can the template be read and formatted?) and
actual LLM calls to evaluate output quality.
"""

import asyncio
import sys
import os
import json
import time
from typing import Dict, Any, List, Optional

sys.path.insert(0, '/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Story, Scene, SceneVariant, StoryFlow, StoryBranch, StoryCharacter, Character, User, UserSettings
from app.models.chapter import Chapter
from app.services.semantic_integration import get_context_manager_for_user
from app.services.llm.service import UnifiedLLMService
from app.services.llm.extraction_service import ExtractionLLMService
from app.services.llm.prompts import prompt_manager

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://kahani:kahani@localhost:5432/kahani')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

STORY_ID = 5


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text


def print_section(title: str):
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)
    print()


def print_result(label: str, result: Any, elapsed_ms: float = None):
    timing = f" ({elapsed_ms:.0f}ms)" if elapsed_ms else ""
    print(f"--- {label}{timing} ---")
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(str(result)[:2000])
    print()


def evaluate_entity_states(result: Dict[str, Any], label: str = "") -> List[str]:
    """Check entity state output for common quality issues."""
    issues = []
    prefix = f"[{label}] " if label else ""

    characters = result.get("characters", [])
    if isinstance(result.get("entity_states"), dict):
        characters = result["entity_states"].get("characters", [])

    for char in characters:
        name = char.get("name", "?")

        # Purple prose in emotional_state
        emo = char.get("emotional_state", "")
        if emo and len(emo.split()) > 3:
            issues.append(f"{prefix}{name}: emotional_state too verbose: '{emo}'")

        # Purple prose in physical_condition
        phys = char.get("physical_condition", "")
        if phys and len(phys.split()) > 4:
            issues.append(f"{prefix}{name}: physical_condition too verbose: '{phys}'")

        # Furniture as location
        loc = char.get("location", "")
        if loc:
            furniture = ["chaise", "sofa", "couch", "chair", "bed", "table", "desk", "ottoman", "stool", "counter"]
            for f in furniture:
                if f == loc.lower().strip():
                    issues.append(f"{prefix}{name}: location is furniture: '{loc}'")

        # Spatial reference as location
        if loc and any(loc.lower().startswith(p) for p in ["next to", "by the", "near ", "beside ", "in front of"]):
            issues.append(f"{prefix}{name}: location is spatial reference: '{loc}'")

    # Check locations
    locations = result.get("locations", [])
    if isinstance(result.get("entity_states"), dict):
        locations = result["entity_states"].get("locations", [])

    for loc_obj in locations:
        loc_name = loc_obj.get("name", "")
        furniture = ["table", "chair", "bed", "sofa", "desk", "counter", "stool", "ottoman", "chaise", "door", "window"]
        if loc_name.lower().strip() in furniture:
            issues.append(f"{prefix}Location is furniture: '{loc_name}'")

    # Check objects
    objects = result.get("objects", [])
    if isinstance(result.get("entity_states"), dict):
        objects = result["entity_states"].get("objects", [])

    for obj in objects:
        obj_name = obj.get("name", "").lower()
        body_parts = ["hands", "eyes", "face", "arms", "legs", "head", "fingers", "lips", "hair"]
        furniture_names = ["table", "chair", "bed", "sofa", "desk", "counter", "floor"]
        if obj_name in body_parts:
            issues.append(f"{prefix}Body part extracted as object: '{obj_name}'")
        if obj_name in furniture_names:
            issues.append(f"{prefix}Furniture extracted as object: '{obj_name}'")

    return issues


def evaluate_npcs(result: Dict[str, Any], explicit_names: List[str], label: str = "") -> List[str]:
    """Check NPC extraction for over-extraction issues."""
    issues = []
    prefix = f"[{label}] " if label else ""

    npcs = result.get("npcs", [])

    non_character_patterns = [
        "marble", "granite", "tile", "coffee", "espresso", "wine",
        "kitchen", "sunroom", "office", "hallway", "bedroom",
        "table", "chair", "sofa", "couch", "counter", "workbench",
        "rain", "sun", "wind", "traffic", "silence", "tension",
        "carrara", "calacatta"
    ]

    for npc in npcs:
        name = npc.get("name", "").lower()

        # Check for non-character extraction
        for pattern in non_character_patterns:
            if pattern in name:
                issues.append(f"{prefix}Non-character extracted as NPC: '{npc.get('name')}'")

        # Check for explicit characters leaked through
        for explicit in explicit_names:
            if explicit.lower() == name:
                issues.append(f"{prefix}Explicit character extracted as NPC: '{npc.get('name')}'")

        # Check for generic descriptors
        generic = ["the man", "the woman", "someone", "a stranger", "the waiter", "the crowd"]
        if name in generic:
            issues.append(f"{prefix}Generic descriptor as NPC: '{npc.get('name')}'")

    return issues


async def test_prompt_loading():
    """Test 1: Verify all updated prompt templates can be loaded and formatted."""
    print_section("TEST 1: PROMPT TEMPLATE LOADING")

    templates = {
        "plot_extraction.user": {
            "scene_content": "Test scene content",
            "key_events": "1. Event A\n2. Event B"
        },
        "combined_extraction.user": {
            "scene_content": "Test scene",
            "character_names": "Alice, Bob",
            "explicit_names": "alice, bob",
            "thread_section": ""
        },
        "entity_only_extraction.user": {
            "scene_content": "Test scene",
            "character_names": "Alice, Bob",
            "chapter_location": "apartment"
        },
        "npc_extraction_cache_friendly.user": {
            "scene_content": "Test scene",
            "explicit_names": "alice, bob"
        },
        "character_moments_cache_friendly.user": {
            "scene_content": "Test scene",
            "character_names": "Alice, Bob"
        },
        "moments_and_npcs.user": {
            "scene_content": "Test scene",
            "character_names": "Alice, Bob",
            "explicit_names": "alice, bob"
        },
        "entity_state_extraction.single.system": {},
        "entity_state_extraction.single.user": {
            "scene_content": "Test scene",
            "scene_sequence": 1,
            "character_names": "Alice, Bob",
            "chapter_location": "apartment"
        },
        # Note: entity_state_extraction.extraction_service exists in YAML but is not
        # registered in prompts.py yaml_mapping (no code uses it — only .single and .batch are used)
        "entity_state_extraction.batch.system": {},
        "entity_state_extraction.batch.user": {
            "character_names": "Alice, Bob",
            "explicit_names": "alice, bob",
            "thread_section": "",
            "batch_content": "Scene 1: Test"
        },
    }

    all_ok = True
    for template_path, format_args in templates.items():
        try:
            parts = template_path.rsplit(".", 1)
            key = parts[0]
            field = parts[1]

            result = prompt_manager.get_prompt(key, field, **format_args)

            if result and len(result) > 20:
                is_system = template_path.endswith(".system")
                has_example = "EXAMPLE" in result
                example_str = "n/a (system)" if is_system else ("yes" if has_example else "NO")
                print(f"  OK  {template_path:<55} ({len(result):>5} chars, example={example_str})")
            else:
                print(f"  FAIL {template_path} - Too short or empty: {len(result) if result else 0} chars")
                all_ok = False
        except Exception as e:
            print(f"  FAIL {template_path} - {e}")
            all_ok = False

    print()
    if all_ok:
        print("  ALL TEMPLATES LOADED SUCCESSFULLY")
    else:
        print("  SOME TEMPLATES FAILED - check above")

    return all_ok


async def test_llm_extractions():
    """Test 2: Run actual LLM extractions against a story 5 scene."""
    print_section("TEST 2: LLM EXTRACTION CALLS (Story 5)")

    db = SessionLocal()
    all_issues = []

    try:
        # Get story 5
        story = db.query(Story).filter(Story.id == STORY_ID).first()
        if not story:
            print(f"ERROR: Story {STORY_ID} not found")
            return

        print(f"Story: {story.title} (ID: {story.id})")

        # Get active branch
        active_branch = db.query(StoryBranch).filter(
            StoryBranch.story_id == story.id,
            StoryBranch.is_active == True
        ).first()
        if not active_branch:
            print("ERROR: No active branch")
            return

        # Get latest scene
        scene = db.query(Scene).join(StoryFlow).filter(
            StoryFlow.story_id == story.id,
            StoryFlow.branch_id == active_branch.id,
            StoryFlow.is_active == True,
            Scene.is_deleted == False
        ).order_by(Scene.sequence_number.desc()).first()

        if not scene:
            print("ERROR: No scene found")
            return

        variant = db.query(SceneVariant).join(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()

        if not variant or not variant.content:
            print("ERROR: No scene content")
            return

        scene_content = variant.content
        print(f"Scene: #{scene.sequence_number} ({len(scene_content)} chars)")
        print(f"Preview: {scene_content[:300]}...")
        print()

        # Get characters
        story_characters = db.query(StoryCharacter).filter(
            StoryCharacter.story_id == story.id,
            StoryCharacter.branch_id == active_branch.id
        ).all()

        character_names = []
        for sc in story_characters:
            char = db.query(Character).filter(Character.id == sc.character_id).first()
            if char:
                character_names.append(char.name)

        explicit_names_lower = [n.lower() for n in character_names]
        print(f"Characters: {character_names}")

        # Get chapter location
        chapter = db.query(Chapter).filter(
            Chapter.story_id == story.id,
            Chapter.branch_id == active_branch.id
        ).order_by(Chapter.chapter_number.desc()).first()

        chapter_location = "Unknown"
        key_events = []
        if chapter and chapter.chapter_plot:
            plot = chapter.chapter_plot if isinstance(chapter.chapter_plot, dict) else json.loads(chapter.chapter_plot)
            chapter_location = chapter.location_name or "Unknown"
            key_events = plot.get("key_events", [])
            print(f"Chapter: {chapter.title} (Location: {chapter_location})")
            print(f"Key events: {len(key_events)}")
        print()

        # Get user settings
        user_id = 2
        db_user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not db_user_settings:
            print("ERROR: No user settings for user_id=2")
            return

        user_settings = db_user_settings.to_dict()
        llm_settings = user_settings.get("llm_settings", {})
        print(f"Main LLM: {llm_settings.get('model_name', 'NOT SET')}")

        # Check if extraction model is configured
        ext_settings = user_settings.get("extraction_model_settings", {})
        ext_enabled = ext_settings.get("enabled", False)
        print(f"Extraction model: {'enabled' if ext_enabled else 'disabled (using main LLM)'}")
        if ext_enabled:
            print(f"  Model: {ext_settings.get('model_name', 'NOT SET')}")
            print(f"  URL: {ext_settings.get('url', 'NOT SET')}")
        print()

        # Build context for cache-friendly methods
        print("Building context...")
        context_manager = get_context_manager_for_user(user_settings, user_id)
        context = await context_manager.build_scene_generation_context(
            story.id, db, "", is_variant_generation=False
        )
        print(f"Context built ({len(context)} keys)")
        print()

        llm_service = UnifiedLLMService()

        # =====================================================================
        # Test A: Entity State (cache-friendly entity_only_extraction)
        # =====================================================================
        print_section("A. ENTITY-ONLY EXTRACTION (cache-friendly)")
        try:
            start = time.perf_counter()
            result_raw = await llm_service.extract_entity_states_cache_friendly(
                scene_content=scene_content,
                character_names=character_names,
                chapter_location=chapter_location,
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )
            elapsed = (time.perf_counter() - start) * 1000

            if isinstance(result_raw, str):
                if result_raw.strip():
                    result = json.loads(strip_code_fences(result_raw))
                else:
                    print("EMPTY STRING returned from LLM")
                    result = {}
            else:
                result = result_raw

            print_result("Entity States", result, elapsed)
            issues = evaluate_entity_states(result, "entity-only")
            all_issues.extend(issues)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()

        # =====================================================================
        # Test B: NPC Extraction (cache-friendly)
        # =====================================================================
        print_section("B. NPC EXTRACTION (cache-friendly)")
        try:
            start = time.perf_counter()
            result_raw = await llm_service.extract_npcs_cache_friendly(
                scene_content=scene_content,
                explicit_names=explicit_names_lower,
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )
            elapsed = (time.perf_counter() - start) * 1000

            if isinstance(result_raw, str):
                if result_raw.strip():
                    result = json.loads(result_raw)
                else:
                    result = {"npcs": []}
            elif isinstance(result_raw, list):
                result = {"npcs": result_raw}
            else:
                result = result_raw

            print_result("NPCs", result, elapsed)
            if isinstance(result, dict):
                issues = evaluate_npcs(result, character_names, "npc-cache")
                all_issues.extend(issues)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()

        # =====================================================================
        # Test C: Character Moments (cache-friendly)
        # =====================================================================
        print_section("C. CHARACTER MOMENTS (cache-friendly)")
        try:
            start = time.perf_counter()
            result = await llm_service.extract_character_moments_cache_friendly(
                scene_content=scene_content,
                character_names=character_names,
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )
            elapsed = (time.perf_counter() - start) * 1000
            print_result("Character Moments", result, elapsed)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()

        # =====================================================================
        # Test D: Plot Extraction (with key_events)
        # =====================================================================
        print_section("D. PLOT EXTRACTION (key events)")
        if key_events:
            try:
                start = time.perf_counter()
                result = await llm_service.extract_plot_events_with_context(
                    scene_content=scene_content,
                    key_events=key_events,
                    context=context,
                    user_id=user_id,
                    user_settings=user_settings,
                    db=db
                )
                elapsed = (time.perf_counter() - start) * 1000
                print_result("Plot Events Completed", result, elapsed)
            except Exception as e:
                print(f"ERROR: {e}")
                import traceback; traceback.print_exc()
        else:
            print("SKIPPED: No key_events in chapter plot")

        # =====================================================================
        # Test E: Moments + NPCs combined (cache-friendly)
        # =====================================================================
        print_section("E. MOMENTS + NPCs COMBINED (cache-friendly)")
        try:
            start = time.perf_counter()
            result_raw = await llm_service.extract_moments_and_npcs_cache_friendly(
                scene_content=scene_content,
                character_names=character_names,
                explicit_character_names=character_names,
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )
            elapsed = (time.perf_counter() - start) * 1000

            if isinstance(result_raw, str):
                if result_raw.strip():
                    result = json.loads(strip_code_fences(result_raw))
                else:
                    print("EMPTY STRING returned from LLM")
                    result = {}
            else:
                result = result_raw

            print_result("Moments+NPCs", result, elapsed)
            if isinstance(result, dict):
                issues = evaluate_npcs(result, character_names, "moments+npcs")
                all_issues.extend(issues)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()

        # =====================================================================
        # Test F: Combined batch extraction (cache-friendly)
        # =====================================================================
        print_section("F. COMBINED BATCH EXTRACTION (cache-friendly)")
        try:
            thread_context = ""
            start = time.perf_counter()
            result_raw = await llm_service.extract_combined_cache_friendly(
                scene_content=scene_content,
                character_names=character_names,
                explicit_character_names=character_names,
                thread_context=thread_context,
                context=context,
                user_id=user_id,
                user_settings=user_settings,
                db=db
            )
            elapsed = (time.perf_counter() - start) * 1000

            if isinstance(result_raw, str):
                if result_raw.strip():
                    result = json.loads(strip_code_fences(result_raw))
                else:
                    print("EMPTY STRING returned from LLM")
                    result = {}
            else:
                result = result_raw

            print_result("Combined Extraction", result, elapsed)
            if isinstance(result, dict):
                issues = evaluate_entity_states(result, "combined")
                all_issues.extend(issues)
                issues = evaluate_npcs(result, character_names, "combined")
                all_issues.extend(issues)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback; traceback.print_exc()

        # =====================================================================
        # Test G: Extraction model (if enabled) - entity states
        # =====================================================================
        if ext_enabled and ext_settings.get("url") and ext_settings.get("model_name"):
            print_section("G. EXTRACTION MODEL - ENTITY STATES (direct)")
            try:
                extraction_svc = ExtractionLLMService(
                    url=ext_settings["url"],
                    model=ext_settings["model_name"],
                    api_key=ext_settings.get("api_key", ""),
                    temperature=ext_settings.get("temperature", 0.3),
                    max_tokens=ext_settings.get("max_tokens", 1000),
                    timeout_total=llm_settings.get("timeout_total", 240),
                    top_p=ext_settings.get("top_p", 1.0),
                    repetition_penalty=ext_settings.get("repetition_penalty", 1.0),
                    min_p=ext_settings.get("min_p", 0.0),
                    thinking_disable_method=ext_settings.get("thinking_disable_method", "none"),
                    thinking_disable_custom=ext_settings.get("thinking_disable_custom", "")
                )

                # Test entity states via extraction model
                start = time.perf_counter()
                result = await extraction_svc.extract_entity_states(
                    scene_content=scene_content,
                    scene_sequence=scene.sequence_number,
                    character_names=character_names,
                    chapter_location=chapter_location
                )
                elapsed = (time.perf_counter() - start) * 1000
                print_result("Entity States (extraction model)", result, elapsed)
                issues = evaluate_entity_states(result, "ext-entity")
                all_issues.extend(issues)

                # Test NPC extraction via extraction model
                print_section("H. EXTRACTION MODEL - NPC EXTRACTION (direct)")
                start = time.perf_counter()
                result = await extraction_svc.extract_npcs(
                    scene_content=scene_content,
                    scene_sequence=scene.sequence_number,
                    explicit_character_names=character_names
                )
                elapsed = (time.perf_counter() - start) * 1000
                print_result("NPCs (extraction model)", result, elapsed)
                issues = evaluate_npcs(result, character_names, "ext-npc")
                all_issues.extend(issues)

                # Test character details
                print_section("I. EXTRACTION MODEL - CHARACTER DETAILS")
                start = time.perf_counter()
                result = await extraction_svc.extract_character_details(
                    character_name=character_names[0] if character_names else "Unknown",
                    character_scenes_text=scene_content[:2000]
                )
                elapsed = (time.perf_counter() - start) * 1000
                print_result("Character Details (extraction model)", result, elapsed)

                # Test summary generation
                print_section("J. EXTRACTION MODEL - SUMMARY GENERATION")
                start = time.perf_counter()
                result = await extraction_svc.generate_summary(
                    story_content=scene_content[:2000],
                    story_context=f"Story: {story.title}"
                )
                elapsed = (time.perf_counter() - start) * 1000
                print_result("Summary (extraction model)", result, elapsed)

            except Exception as e:
                print(f"ERROR creating extraction service: {e}")
                import traceback; traceback.print_exc()
        else:
            print_section("G-J. EXTRACTION MODEL TESTS SKIPPED (not enabled)")
            print("Enable extraction model in settings to test ExtractionLLMService prompts directly.")

        # =====================================================================
        # Quality Summary
        # =====================================================================
        print_section("QUALITY EVALUATION SUMMARY")

        if all_issues:
            print(f"  ISSUES FOUND: {len(all_issues)}")
            print()
            for issue in all_issues:
                print(f"    - {issue}")
        else:
            print("  NO QUALITY ISSUES DETECTED")
            print()
            print("  All extractions passed:")
            print("    - No purple prose in emotional_state/physical_condition")
            print("    - No furniture as locations")
            print("    - No body parts or furniture as objects")
            print("    - No non-characters extracted as NPCs")
            print("    - No explicit characters leaked into NPC list")

        print()

    finally:
        db.close()


async def main():
    print_section("FEW-SHOT EXTRACTION PROMPT TEST SUITE")

    # Test 1: Template loading
    templates_ok = await test_prompt_loading()

    if not templates_ok:
        print("\nABORTING: Template loading failed. Fix prompts.yml before testing LLM calls.")
        return

    # Test 2: LLM calls
    await test_llm_extractions()

    print_section("ALL TESTS COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
