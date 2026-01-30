#!/usr/bin/env python3
"""
Test Extraction Outputs

Actually calls the LLM with each extraction type and displays the outputs
to verify they return expected results. Also measures timing to show cache benefits.
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

from app.models import Story, Scene, SceneVariant, StoryFlow, StoryBranch, StoryCharacter, Character, User, UserSettings
from app.services.semantic_integration import get_context_manager_for_user
from app.services.llm.service import UnifiedLLMService

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://kahani:kahani@localhost:5432/kahani')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


async def test_extractions():
    print("=" * 80)
    print("EXTRACTION OUTPUT TEST - CALLING ACTUAL LLM")
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

        # Get scene
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
        print()
        print("Scene content preview:")
        print("-" * 40)
        print(scene_content[:500] + "..." if len(scene_content) > 500 else scene_content)
        print("-" * 40)
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

        print(f"Characters: {character_names}")
        print()

        # Get actual user settings from database
        # Use nishant (user_id=2) who has LLM configured
        user_id = 2
        db_user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

        if not db_user_settings:
            print("ERROR: No user settings found for user_id=1")
            print("Please configure LLM settings in the UI first.")
            return

        # Convert to dict using the model's to_dict() method
        user_settings = db_user_settings.to_dict()

        # Check that LLM is configured
        llm_settings = user_settings.get("llm_settings", {})
        if not llm_settings.get("api_url"):
            print("ERROR: LLM API URL not configured in user settings")
            print("Please configure LLM settings in the UI first.")
            return

        # FORCE using main LLM (not extraction LLM) to test caching
        user_settings['extraction_model_settings'] = {
            'enabled': False,
            'fallback_to_main': True
        }

        print(f"LLM Configuration (MAIN LLM - extraction disabled for test):")
        print(f"  API URL: {llm_settings.get('api_url', 'NOT SET')[:50]}...")
        print(f"  Model: {llm_settings.get('model_name', 'NOT SET')}")
        print(f"  Temperature: {llm_settings.get('temperature', 'NOT SET')}")
        print()

        # Build context
        print("Building context...")
        context_manager = get_context_manager_for_user(user_settings, user_id)
        context = await context_manager.build_scene_generation_context(
            story.id, db, "", is_variant_generation=False
        )
        print(f"Context built with {len(context)} keys")
        print()

        llm_service = UnifiedLLMService()

        # Test each extraction type
        extractions_to_test = [
            {
                "name": "Working Memory",
                "method": "extract_working_memory_cache_friendly",
                "args": {
                    "scene_content": scene_content,
                    "current_focus": "Character tension, emotional dynamics",
                    "context": context,
                    "user_id": user_id,
                    "user_settings": user_settings,
                    "db": db
                }
            },
            {
                "name": "Relationship Extraction",
                "method": "extract_relationship_cache_friendly",
                "args": {
                    "scene_content": scene_content,
                    "character_names": character_names,
                    "characters_in_scene": character_names[:2] if len(character_names) >= 2 else character_names,
                    "previous_relationships": "No previous relationships established.",
                    "context": context,
                    "user_id": user_id,
                    "user_settings": user_settings,
                    "db": db
                }
            },
            {
                "name": "NPC Extraction",
                "method": "extract_npcs_cache_friendly",
                "args": {
                    "scene_content": scene_content,
                    "explicit_names": [n.lower() for n in character_names],
                    "context": context,
                    "user_id": user_id,
                    "user_settings": user_settings,
                    "db": db
                }
            },
            {
                "name": "Character Moments",
                "method": "extract_character_moments_cache_friendly",
                "args": {
                    "scene_content": scene_content,
                    "character_names": character_names,
                    "context": context,
                    "user_id": user_id,
                    "user_settings": user_settings,
                    "db": db
                }
            },
            {
                "name": "Plot Events (Fallback)",
                "method": "extract_plot_events_fallback_cache_friendly",
                "args": {
                    "scene_content": scene_content,
                    "thread_context": "\n- Characters investigating a mystery\n- Tension building between parties",
                    "context": context,
                    "user_id": user_id,
                    "user_settings": user_settings,
                    "db": db
                }
            }
        ]

        # Track timing for each extraction
        timings = []
        first_call_time = None

        for i, extraction in enumerate(extractions_to_test):
            print("=" * 80)
            print(f"TESTING: {extraction['name']} (Call #{i+1})")
            print("=" * 80)
            print()

            try:
                method = getattr(llm_service, extraction["method"])

                # Measure time
                start_time = time.perf_counter()
                result = await method(**extraction["args"])
                end_time = time.perf_counter()

                elapsed_ms = (end_time - start_time) * 1000
                timings.append({
                    "name": extraction["name"],
                    "call_number": i + 1,
                    "time_ms": elapsed_ms
                })

                if first_call_time is None:
                    first_call_time = elapsed_ms

                print(f"TIME: {elapsed_ms:.0f}ms", end="")
                if i > 0:
                    speedup = first_call_time / elapsed_ms if elapsed_ms > 0 else 0
                    print(f" (First call: {first_call_time:.0f}ms, Speedup: {speedup:.1f}x)")
                else:
                    print(" (First call - establishes cache)")
                print()

                print("RESULT:")
                print("-" * 40)
                if isinstance(result, dict):
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                elif isinstance(result, list):
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print(result)
                print("-" * 40)

                # Validate result
                if result:
                    print("STATUS: ✅ Got valid output")
                else:
                    print("STATUS: ⚠️ Empty result (may be expected if nothing to extract)")

            except Exception as e:
                print(f"ERROR: {e}")
                import traceback
                print(traceback.format_exc())
                timings.append({
                    "name": extraction["name"],
                    "call_number": i + 1,
                    "time_ms": -1,
                    "error": str(e)
                })

            print()

        # Print timing summary
        print("=" * 80)
        print("TIMING SUMMARY")
        print("=" * 80)
        print()
        print(f"{'Extraction':<30} {'Call #':<8} {'Time (ms)':<12} {'vs First':<10}")
        print("-" * 60)

        for t in timings:
            if t["time_ms"] > 0:
                vs_first = f"{first_call_time / t['time_ms']:.1f}x" if t["call_number"] > 1 else "baseline"
                print(f"{t['name']:<30} {t['call_number']:<8} {t['time_ms']:<12.0f} {vs_first:<10}")
            else:
                print(f"{t['name']:<30} {t['call_number']:<8} {'ERROR':<12} {'N/A':<10}")

        print()

        # Calculate average of subsequent calls
        if len(timings) > 1:
            subsequent_times = [t["time_ms"] for t in timings[1:] if t["time_ms"] > 0]
            if subsequent_times:
                avg_subsequent = sum(subsequent_times) / len(subsequent_times)
                print(f"First call time:      {first_call_time:.0f}ms")
                print(f"Avg subsequent time:  {avg_subsequent:.0f}ms")
                print(f"Average speedup:      {first_call_time / avg_subsequent:.1f}x")
                print()

                if avg_subsequent < first_call_time * 0.8:
                    print("✅ CACHE APPEARS TO BE WORKING! Subsequent calls are faster.")
                else:
                    print("⚠️ Cache benefit not clearly visible (may depend on LLM provider)")

        print()
        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_extractions())
