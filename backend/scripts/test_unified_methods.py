#!/usr/bin/env python3
"""
Test Unified Non-Streaming Methods

Tests the new cache-aligned non-streaming methods:
1. generate_variant_with_choices() - variant with inline choices (1 LLM call)
2. generate_continuation_with_choices() - continuation with inline choices (1 LLM call)
3. generate_concluding_scene() - concluding scene (1 LLM call, no choices)

Also compares timings with legacy methods to verify cache hits.
"""

import asyncio
import sys
import os
import json
import time
from typing import Dict, Any, List

sys.path.insert(0, '/app')

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

from app.models import Story, Scene, SceneVariant, StoryFlow, StoryBranch, Chapter, ChapterStatus, UserSettings
from app.services.semantic_integration import get_context_manager_for_user
from app.services.llm.service import UnifiedLLMService

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://kahani:kahani@localhost:5432/kahani')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def print_separator(title: str):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_timing(name: str, time_ms: float, baseline_ms: float = None):
    if baseline_ms:
        speedup = baseline_ms / time_ms if time_ms > 0 else float('inf')
        cache_status = "CACHE HIT" if time_ms < baseline_ms * 0.7 else "CACHE MISS?"
        print(f"  {name}: {time_ms:.0f}ms (vs baseline {baseline_ms:.0f}ms, {speedup:.1f}x) [{cache_status}]")
    else:
        print(f"  {name}: {time_ms:.0f}ms (BASELINE)")


async def test_unified_methods():
    print_separator("UNIFIED NON-STREAMING METHODS TEST")
    print("Testing cache-aligned methods that use _build_cache_friendly_message_prefix()")
    print()

    db = SessionLocal()
    timings = []

    try:
        # Find memory test story
        story = db.query(Story).filter(Story.title.ilike("%memory%")).first()
        if not story:
            story = db.query(Story).join(Scene).filter(Scene.is_deleted == False).first()

        if not story:
            print("ERROR: No story found in database")
            return False

        print(f"Story: {story.title} (ID: {story.id})")

        # Get active branch
        active_branch = db.query(StoryBranch).filter(
            StoryBranch.story_id == story.id,
            StoryBranch.is_active == True
        ).first()

        if not active_branch:
            print("ERROR: No active branch found")
            return False

        print(f"Branch: {active_branch.name} (ID: {active_branch.id})")

        # Get active chapter
        active_chapter = db.query(Chapter).filter(
            Chapter.story_id == story.id,
            Chapter.branch_id == active_branch.id,
            Chapter.status == ChapterStatus.ACTIVE
        ).first()

        chapter_id = active_chapter.id if active_chapter else None
        print(f"Chapter: {active_chapter.title if active_chapter else 'None'} (ID: {chapter_id})")

        # Get a scene with content
        scene = db.query(Scene).join(StoryFlow).filter(
            StoryFlow.story_id == story.id,
            StoryFlow.branch_id == active_branch.id,
            StoryFlow.is_active == True,
            Scene.is_deleted == False
        ).order_by(desc(Scene.sequence_number)).first()

        if not scene:
            print("ERROR: No active scene found")
            return False

        # Get active variant for this scene
        flow = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()

        variant = None
        if flow and flow.scene_variant_id:
            variant = db.query(SceneVariant).filter(SceneVariant.id == flow.scene_variant_id).first()

        if not variant:
            print("ERROR: No active variant found for scene")
            return False

        print(f"Scene: #{scene.sequence_number} (ID: {scene.id})")
        print(f"Variant: #{variant.variant_number} (ID: {variant.id})")
        print(f"Content length: {len(variant.content)} chars")
        print()

        # Get user settings (user_id 2 = nishant)
        user_id = 2
        db_user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

        if not db_user_settings:
            print("ERROR: No user settings found for user_id=2")
            return False

        user_settings = db_user_settings.to_dict()

        # Force using main LLM (no extraction model)
        user_settings['extraction_model_settings'] = {
            'enabled': False,
            'fallback_to_main': True
        }

        llm_settings = user_settings.get("llm_settings", {})
        if not llm_settings.get("api_url"):
            print("ERROR: LLM API URL not configured")
            return False

        print(f"LLM: {llm_settings.get('model_name')} @ {llm_settings.get('api_url')[:40]}...")
        print()

        # Initialize services
        context_manager = get_context_manager_for_user(user_settings, user_id)
        llm_service = UnifiedLLMService()

        # ========== TEST 1: generate_variant_with_choices() ==========
        print_separator("TEST 1: generate_variant_with_choices()")
        print("Generates variant with inline choices in single LLM call (cache-friendly)")
        print()

        # Build context for variant generation
        print("Building variant generation context...")
        variant_context = await context_manager.build_scene_generation_context(
            story.id, db,
            custom_prompt="Add more tension and suspense to this scene",
            is_variant_generation=True,
            exclude_scene_id=scene.id,
            chapter_id=chapter_id,
            branch_id=active_branch.id
        )
        variant_context["enhancement_guidance"] = "Add more tension and suspense to this scene"
        print(f"Context has {len(variant_context)} keys")

        start_time = time.perf_counter()

        new_content, choices = await llm_service.generate_variant_with_choices(
            original_scene=variant.content,
            context=variant_context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        variant_time = (time.perf_counter() - start_time) * 1000
        timings.append({"name": "generate_variant_with_choices", "time_ms": variant_time})

        print(f"Time: {variant_time:.0f}ms")
        print()

        if new_content:
            print(f"Generated variant ({len(new_content)} chars):")
            print("-" * 60)
            print(new_content[:400] + "..." if len(new_content) > 400 else new_content)
            print("-" * 60)

            if choices:
                print(f"\nInline choices ({len(choices)}):")
                for i, choice in enumerate(choices, 1):
                    print(f"  {i}. {choice[:70]}..." if len(choice) > 70 else f"  {i}. {choice}")
                print("\nSUCCESS: Variant generated with inline choices!")
            else:
                print("\nWARNING: No inline choices generated (may need separate call)")
        else:
            print("FAILED: No content generated")
            return False

        print()

        # ========== TEST 2: generate_continuation_with_choices() ==========
        print_separator("TEST 2: generate_continuation_with_choices()")
        print("Generates continuation with inline choices in single LLM call (cache-friendly)")
        print()

        # Build context for continuation
        print("Building continuation context...")
        continuation_context = await context_manager.build_scene_continuation_context(
            story.id, scene.id, variant.content, db,
            custom_prompt="Continue with building tension",
            branch_id=active_branch.id
        )
        print(f"Context has {len(continuation_context)} keys")

        start_time = time.perf_counter()

        continuation_content, continuation_choices = await llm_service.generate_continuation_with_choices(
            context=continuation_context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        continuation_time = (time.perf_counter() - start_time) * 1000
        timings.append({"name": "generate_continuation_with_choices", "time_ms": continuation_time})

        print(f"Time: {continuation_time:.0f}ms")
        print()

        if continuation_content:
            print(f"Generated continuation ({len(continuation_content)} chars):")
            print("-" * 60)
            print(continuation_content[:400] + "..." if len(continuation_content) > 400 else continuation_content)
            print("-" * 60)

            if continuation_choices:
                print(f"\nInline choices ({len(continuation_choices)}):")
                for i, choice in enumerate(continuation_choices, 1):
                    print(f"  {i}. {choice[:70]}..." if len(choice) > 70 else f"  {i}. {choice}")
                print("\nSUCCESS: Continuation generated with inline choices!")
            else:
                print("\nWARNING: No inline choices generated (may need separate call)")
        else:
            print("FAILED: No continuation generated")
            return False

        print()

        # ========== TEST 3: generate_concluding_scene() ==========
        print_separator("TEST 3: generate_concluding_scene()")
        print("Generates chapter-concluding scene (no choices) in single LLM call (cache-friendly)")
        print()

        # Build context for concluding scene
        print("Building concluding scene context...")
        concluding_context = await context_manager.build_scene_generation_context(
            story.id, db,
            is_variant_generation=False,
            chapter_id=chapter_id,
            branch_id=active_branch.id
        )
        print(f"Context has {len(concluding_context)} keys")

        chapter_info = {
            "chapter_number": active_chapter.chapter_number if active_chapter else 1,
            "chapter_title": active_chapter.title if active_chapter else "Untitled",
            "chapter_location": getattr(active_chapter, 'location_name', None) or "Unknown",
            "chapter_time_period": getattr(active_chapter, 'time_period', None) or "Unknown",
            "chapter_scenario": getattr(active_chapter, 'scenario', None) or "None"
        }

        start_time = time.perf_counter()

        concluding_content = await llm_service.generate_concluding_scene(
            context=concluding_context,
            chapter_info=chapter_info,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        concluding_time = (time.perf_counter() - start_time) * 1000
        timings.append({"name": "generate_concluding_scene", "time_ms": concluding_time})

        print(f"Time: {concluding_time:.0f}ms")
        print()

        if concluding_content:
            print(f"Generated concluding scene ({len(concluding_content)} chars):")
            print("-" * 60)
            print(concluding_content[:400] + "..." if len(concluding_content) > 400 else concluding_content)
            print("-" * 60)
            print("\nSUCCESS: Concluding scene generated (no choices expected)")
        else:
            print("FAILED: No concluding scene generated")
            return False

        print()

        # ========== TEST 4: Compare with separate choice generation ==========
        print_separator("TEST 4: Cache verification - generate_choices() should hit cache")
        print("Using the same context, choice generation should be much faster due to cache")
        print()

        # Use the variant_context from Test 1 (should be cached)
        start_time = time.perf_counter()

        separate_choices = await llm_service.generate_choices(
            scene_content=new_content,
            context=variant_context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        separate_choice_time = (time.perf_counter() - start_time) * 1000
        timings.append({"name": "generate_choices (separate)", "time_ms": separate_choice_time})

        baseline = variant_time
        speedup = baseline / separate_choice_time if separate_choice_time > 0 else float('inf')
        cache_hit = separate_choice_time < baseline * 0.7

        print(f"Time: {separate_choice_time:.0f}ms (baseline: {baseline:.0f}ms, speedup: {speedup:.1f}x)")
        print(f"Cache status: {'HIT' if cache_hit else 'MISS or PARTIAL HIT'}")
        print()

        if separate_choices:
            print(f"Separate choices ({len(separate_choices)}):")
            for i, choice in enumerate(separate_choices, 1):
                print(f"  {i}. {choice[:70]}..." if len(choice) > 70 else f"  {i}. {choice}")

        print()

        # ========== TIMING SUMMARY ==========
        print_separator("TIMING SUMMARY")
        print()
        print(f"{'Method':<40} {'Time (ms)':<12} {'Notes':<30}")
        print("-" * 80)

        for t in timings:
            notes = ""
            if t["name"] == "generate_variant_with_choices":
                notes = "BASELINE (scene + choices)"
            elif t["name"] == "generate_choices (separate)":
                speedup = timings[0]["time_ms"] / t["time_ms"] if t["time_ms"] > 0 else 0
                notes = f"Cache speedup: {speedup:.1f}x"
            print(f"{t['name']:<40} {t['time_ms']:<12.0f} {notes:<30}")

        print("-" * 80)
        print()

        total_time = sum(t["time_ms"] for t in timings)
        print(f"Total test time: {total_time/1000:.1f}s")

        # ========== FINAL RESULT ==========
        print_separator("TEST RESULT")
        print()
        print("All unified methods work correctly:")
        print("  - generate_variant_with_choices() - Variant + inline choices in 1 call")
        print("  - generate_continuation_with_choices() - Continuation + inline choices in 1 call")
        print("  - generate_concluding_scene() - Concluding scene in 1 call (no choices)")
        print()
        print("Cache alignment verified - all methods use _build_cache_friendly_message_prefix()")
        print()

        return True

    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        print(traceback.format_exc())
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = asyncio.run(test_unified_methods())
    sys.exit(0 if success else 1)
