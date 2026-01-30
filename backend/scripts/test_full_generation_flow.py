#!/usr/bin/env python3
"""
Full Generation Flow Test

Tests the complete scene generation flow to verify cache-friendliness:
1. Scene generation (establishes cache)
2. Choice generation (should hit cache)
3. All extractions (should hit cache)

This demonstrates the real-world benefit of cache-friendly architecture.
"""

import asyncio
import sys
import os
import json
import time
from typing import Dict, Any, List

sys.path.insert(0, '/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Story, Scene, SceneVariant, StoryFlow, StoryBranch, StoryCharacter, Character, UserSettings
from app.services.semantic_integration import get_context_manager_for_user
from app.services.llm.service import UnifiedLLMService

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://kahani:kahani@localhost:5432/kahani')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


async def test_full_flow():
    print("=" * 80)
    print("FULL GENERATION FLOW TEST")
    print("Scene Generation → Choices → All Extractions")
    print("=" * 80)
    print()

    db = SessionLocal()

    try:
        # Find story
        story = db.query(Story).filter(Story.title.ilike("%memory%")).first()
        if not story:
            story = db.query(Story).join(Scene).filter(Scene.is_deleted == False).first()

        if not story:
            print("ERROR: No story found")
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

        print(f"Branch: {active_branch.name} (ID: {active_branch.id})")

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

        print(f"Characters: {character_names}")

        # Get user settings (nishant = user_id 2)
        user_id = 2
        db_user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

        if not db_user_settings:
            print("ERROR: No user settings found")
            return

        user_settings = db_user_settings.to_dict()

        # FORCE using main LLM to test caching
        user_settings['extraction_model_settings'] = {
            'enabled': False,
            'fallback_to_main': True
        }

        llm_settings = user_settings.get("llm_settings", {})
        if not llm_settings.get("api_url"):
            print("ERROR: LLM API URL not configured")
            return

        print(f"LLM: {llm_settings.get('model_name')} @ {llm_settings.get('api_url')[:30]}...")
        print()

        # Build context
        print("Building context...")
        context_manager = get_context_manager_for_user(user_settings, user_id)
        context = await context_manager.build_scene_generation_context(
            story.id, db, "Continue the story with David's arrival", is_variant_generation=False
        )
        print(f"Context built with {len(context)} keys")
        print()

        llm_service = UnifiedLLMService()
        timings = []

        # ========== 1. SCENE GENERATION (establishes cache) ==========
        print("=" * 80)
        print("STEP 1: SCENE GENERATION (establishes cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        # Generate scene with choices using the unified service
        scene_content, choices = await llm_service.generate_scene_with_choices(
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        scene_time = (end_time - start_time) * 1000
        timings.append({"name": "Scene Generation", "time_ms": scene_time})

        print(f"TIME: {scene_time:.0f}ms")
        print()

        if scene_content:
            print(f"Generated scene ({len(scene_content)} chars):")
            print("-" * 40)
            print(scene_content[:500] + "..." if len(scene_content) > 500 else scene_content)
            print("-" * 40)
            if choices:
                print(f"\nInline choices: {len(choices)}")
        else:
            print("ERROR: Failed to generate scene")
            return

        print()

        # ========== 2. CHOICE GENERATION (should hit cache) ==========
        print("=" * 80)
        print("STEP 2: CHOICE GENERATION (should hit cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        choices_result = await llm_service.generate_choices(
            scene_content=scene_content,
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        choices_time = (end_time - start_time) * 1000
        timings.append({"name": "Choice Generation", "time_ms": choices_time})

        print(f"TIME: {choices_time:.0f}ms (vs Scene: {scene_time:.0f}ms, Speedup: {scene_time/choices_time:.1f}x)")
        print()

        if choices_result:
            print("Choices generated:")
            for i, choice in enumerate(choices_result, 1):
                if isinstance(choice, dict):
                    print(f"  {i}. {choice.get('text', choice)[:80]}...")
                else:
                    print(f"  {i}. {str(choice)[:80]}...")
        print()

        # ========== 3. WORKING MEMORY (should hit cache) ==========
        print("=" * 80)
        print("STEP 3: WORKING MEMORY EXTRACTION (should hit cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        wm_result = await llm_service.extract_working_memory_cache_friendly(
            scene_content=scene_content,
            current_focus="Character dynamics and tension",
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        wm_time = (end_time - start_time) * 1000
        timings.append({"name": "Working Memory", "time_ms": wm_time})

        print(f"TIME: {wm_time:.0f}ms (vs Scene: {scene_time:.0f}ms, Speedup: {scene_time/wm_time:.1f}x)")
        print()
        if wm_result:
            print(json.dumps(wm_result, indent=2)[:500])
        print()

        # ========== 4. RELATIONSHIP EXTRACTION (should hit cache) ==========
        print("=" * 80)
        print("STEP 4: RELATIONSHIP EXTRACTION (should hit cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        rel_result = await llm_service.extract_relationship_cache_friendly(
            scene_content=scene_content,
            character_names=character_names,
            characters_in_scene=character_names[:2] if len(character_names) >= 2 else character_names,
            previous_relationships="No previous relationships.",
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        rel_time = (end_time - start_time) * 1000
        timings.append({"name": "Relationship", "time_ms": rel_time})

        print(f"TIME: {rel_time:.0f}ms (vs Scene: {scene_time:.0f}ms, Speedup: {scene_time/rel_time:.1f}x)")
        print()
        if rel_result:
            print(json.dumps(rel_result, indent=2)[:500])
        print()

        # ========== 5. NPC EXTRACTION (should hit cache) ==========
        print("=" * 80)
        print("STEP 5: NPC EXTRACTION (should hit cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        npc_result = await llm_service.extract_npcs_cache_friendly(
            scene_content=scene_content,
            explicit_names=[n.lower() for n in character_names],
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        npc_time = (end_time - start_time) * 1000
        timings.append({"name": "NPC Extraction", "time_ms": npc_time})

        print(f"TIME: {npc_time:.0f}ms (vs Scene: {scene_time:.0f}ms, Speedup: {scene_time/npc_time:.1f}x)")
        print()
        if npc_result:
            print(f"NPCs found: {len(npc_result)}")
            for npc in npc_result[:3]:
                print(f"  - {npc.get('name', 'Unknown')}")
        print()

        # ========== 6. CHARACTER MOMENTS (should hit cache) ==========
        print("=" * 80)
        print("STEP 6: CHARACTER MOMENTS (should hit cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        moments_result = await llm_service.extract_character_moments_cache_friendly(
            scene_content=scene_content,
            character_names=character_names,
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        moments_time = (end_time - start_time) * 1000
        timings.append({"name": "Character Moments", "time_ms": moments_time})

        print(f"TIME: {moments_time:.0f}ms (vs Scene: {scene_time:.0f}ms, Speedup: {scene_time/moments_time:.1f}x)")
        print()
        if moments_result:
            print(f"Moments found: {len(moments_result)}")
            for moment in moments_result[:3]:
                print(f"  - {moment.get('character', 'Unknown')}: {moment.get('moment_type', 'Unknown')}")
        print()

        # ========== 7. PLOT EVENTS (should hit cache) ==========
        print("=" * 80)
        print("STEP 7: PLOT EVENTS (should hit cache)")
        print("=" * 80)

        start_time = time.perf_counter()

        plot_result = await llm_service.extract_plot_events_fallback_cache_friendly(
            scene_content=scene_content,
            thread_context="\n- Investigation continues\n- Tension building",
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            db=db
        )

        end_time = time.perf_counter()
        plot_time = (end_time - start_time) * 1000
        timings.append({"name": "Plot Events", "time_ms": plot_time})

        print(f"TIME: {plot_time:.0f}ms (vs Scene: {scene_time:.0f}ms, Speedup: {scene_time/plot_time:.1f}x)")
        print()
        if plot_result:
            print(f"Events found: {len(plot_result)}")
            for event in plot_result[:3]:
                print(f"  - {event.get('event_type', 'Unknown')}: {event.get('description', '')[:60]}...")
        print()

        # ========== TIMING SUMMARY ==========
        print("=" * 80)
        print("TIMING SUMMARY")
        print("=" * 80)
        print()
        print(f"{'Operation':<25} {'Time (ms)':<12} {'vs Scene':<12} {'Cache Hit?':<10}")
        print("-" * 60)

        baseline = timings[0]["time_ms"]
        total_time = 0
        cached_time = 0

        for i, t in enumerate(timings):
            time_ms = t["time_ms"]
            total_time += time_ms

            if i == 0:
                speedup = "baseline"
                cache_status = "NEW"
            else:
                speedup = f"{baseline/time_ms:.1f}x"
                cached_time += time_ms
                cache_status = "✅ YES" if time_ms < baseline * 0.8 else "⚠️ MAYBE"

            print(f"{t['name']:<25} {time_ms:<12.0f} {speedup:<12} {cache_status:<10}")

        print("-" * 60)
        print()

        # Calculate savings
        uncached_estimate = baseline * len(timings)
        time_saved = uncached_estimate - total_time
        savings_percent = (time_saved / uncached_estimate) * 100 if uncached_estimate > 0 else 0

        print(f"Total time:           {total_time/1000:.1f}s")
        print(f"Without caching:      ~{uncached_estimate/1000:.1f}s (estimated)")
        print(f"Time saved:           ~{time_saved/1000:.1f}s ({savings_percent:.0f}%)")
        print()

        avg_cached = cached_time / (len(timings) - 1) if len(timings) > 1 else 0
        print(f"Scene generation:     {baseline/1000:.1f}s")
        print(f"Avg cached operation: {avg_cached/1000:.1f}s")
        print(f"Cache efficiency:     {baseline/avg_cached:.1f}x faster")

        print()
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_full_flow())
