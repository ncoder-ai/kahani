#!/usr/bin/env python3
"""
Cache-Friendliness Test Script

This script tests that all extraction methods produce identical message prefixes
(messages 1 to N-1) so that LLM prompt caching works correctly.

Only the final message should differ between extraction types.
"""

import asyncio
import sys
import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Add backend to path
sys.path.insert(0, '/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Story, Scene, SceneVariant, StoryFlow, Chapter, StoryBranch, StoryCharacter, Character
from app.services.semantic_integration import get_context_manager_for_user
from app.services.llm.service import UnifiedLLMService
from app.services.llm.prompts import prompt_manager

# Create database connection
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://kahani:kahani@localhost:5432/kahani')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


@dataclass
class ExtractionMessages:
    """Holds messages for an extraction type"""
    name: str
    messages: List[Dict[str, str]]
    final_message_preview: str


def get_message_hash(messages: List[Dict[str, str]], exclude_last: bool = True) -> str:
    """Get a hash of messages for comparison, optionally excluding the last message"""
    msgs_to_hash = messages[:-1] if exclude_last and len(messages) > 1 else messages
    return json.dumps(msgs_to_hash, sort_keys=True)


def compare_message_prefixes(extractions: List[ExtractionMessages]) -> Dict[str, Any]:
    """Compare message prefixes across all extraction types - FULL CONTENT COMPARISON"""
    results = {
        "all_match": True,
        "total_extractions": len(extractions),
        "message_counts": {},
        "prefix_hashes": {},
        "differences": [],
        "details": [],
        "content_verification": []
    }

    if not extractions:
        results["all_match"] = False
        results["error"] = "No extractions to compare"
        return results

    # Get reference (first extraction)
    reference = extractions[0]
    reference_prefix_count = len(reference.messages) - 1

    results["reference"] = {
        "name": reference.name,
        "total_messages": len(reference.messages),
        "prefix_messages": reference_prefix_count
    }

    for ext in extractions:
        msg_count = len(ext.messages)
        prefix_count = msg_count - 1

        results["message_counts"][ext.name] = msg_count

        detail = {
            "name": ext.name,
            "total_messages": msg_count,
            "prefix_messages": prefix_count,
            "final_message_preview": ext.final_message_preview[:200] + "..." if len(ext.final_message_preview) > 200 else ext.final_message_preview,
            "prefix_matches_reference": True,
            "message_by_message": []
        }

        # Compare EACH message in the prefix (excluding final)
        ref_msgs = reference.messages[:-1]
        ext_msgs = ext.messages[:-1]

        if len(ref_msgs) != len(ext_msgs):
            detail["prefix_matches_reference"] = False
            results["all_match"] = False
            results["differences"].append({
                "extraction": ext.name,
                "reference": reference.name,
                "issue": f"Different prefix message counts: {len(ref_msgs)} vs {len(ext_msgs)}"
            })
        else:
            for i, (ref_msg, ext_msg) in enumerate(zip(ref_msgs, ext_msgs)):
                ref_role = ref_msg.get("role", "")
                ext_role = ext_msg.get("role", "")
                ref_content = ref_msg.get("content", "")
                ext_content = ext_msg.get("content", "")

                role_match = ref_role == ext_role
                content_match = ref_content == ext_content

                msg_detail = {
                    "index": i,
                    "role_match": role_match,
                    "content_match": content_match,
                    "ref_role": ref_role,
                    "ext_role": ext_role,
                    "ref_content_len": len(ref_content),
                    "ext_content_len": len(ext_content)
                }

                if not role_match or not content_match:
                    detail["prefix_matches_reference"] = False
                    results["all_match"] = False
                    msg_detail["status"] = "❌ MISMATCH"

                    # Find first difference in content
                    if not content_match:
                        for j, (c1, c2) in enumerate(zip(ref_content, ext_content)):
                            if c1 != c2:
                                msg_detail["first_diff_at"] = j
                                msg_detail["ref_snippet"] = ref_content[max(0, j-20):j+20]
                                msg_detail["ext_snippet"] = ext_content[max(0, j-20):j+20]
                                break
                        else:
                            # Different lengths
                            if len(ref_content) != len(ext_content):
                                msg_detail["length_diff"] = f"{len(ref_content)} vs {len(ext_content)}"

                    results["differences"].append({
                        "extraction": ext.name,
                        "message_index": i,
                        "role_match": role_match,
                        "content_match": content_match,
                        "detail": msg_detail
                    })
                else:
                    msg_detail["status"] = "✅ MATCH"

                detail["message_by_message"].append(msg_detail)

        results["details"].append(detail)

    # Add content verification summary
    print("\n" + "=" * 80)
    print("BYTE-BY-BYTE CONTENT VERIFICATION")
    print("=" * 80)

    for ext in extractions[1:]:  # Skip reference
        print(f"\n--- Comparing {ext.name} to {reference.name} ---")
        ref_msgs = reference.messages[:-1]
        ext_msgs = ext.messages[:-1]

        all_match = True
        for i, (ref_msg, ext_msg) in enumerate(zip(ref_msgs, ext_msgs)):
            ref_content = ref_msg.get("content", "")
            ext_content = ext_msg.get("content", "")

            if ref_content == ext_content:
                print(f"  [MSG {i}] ✅ IDENTICAL ({len(ref_content)} chars)")
            else:
                all_match = False
                print(f"  [MSG {i}] ❌ DIFFERENT!")
                print(f"           Ref: {len(ref_content)} chars")
                print(f"           Ext: {len(ext_content)} chars")

                # Show first difference
                for j, (c1, c2) in enumerate(zip(ref_content, ext_content)):
                    if c1 != c2:
                        print(f"           First diff at char {j}:")
                        print(f"           Ref: ...{repr(ref_content[max(0,j-10):j+10])}...")
                        print(f"           Ext: ...{repr(ext_content[max(0,j-10):j+10])}...")
                        break

        if all_match:
            print(f"  RESULT: ✅ All prefix messages are BYTE-IDENTICAL")
        else:
            print(f"  RESULT: ❌ Some messages differ!")

    return results


async def build_extraction_messages(
    db,
    story_id: int,
    scene_content: str,
    context: Dict[str, Any],
    user_id: int,
    user_settings: Dict[str, Any],
    character_names: List[str],
    explicit_names: List[str]
) -> List[ExtractionMessages]:
    """Build messages for all extraction types"""

    extractions = []
    llm_service = UnifiedLLMService()

    # Get common parameters
    generation_prefs = user_settings.get("generation_preferences", {})
    scene_length = generation_prefs.get("scene_length", "medium")
    choices_count = generation_prefs.get("choices_count", 4)
    separate_choice_generation = generation_prefs.get("separate_choice_generation", False)
    scene_length_description = llm_service._get_scene_length_description(scene_length)
    scene_batch_size = user_settings.get('context_settings', {}).get('scene_batch_size', 10)

    # Get system prompt (same for all)
    system_prompt = prompt_manager.get_prompt(
        "scene_with_immediate", "system",
        user_id=user_id,
        db=db,
        scene_length_description=scene_length_description,
        choices_count=choices_count,
        skip_choices=separate_choice_generation
    )

    # Get context messages (same for all)
    context_messages = llm_service._format_context_as_messages(context, scene_batch_size=scene_batch_size)

    cleaned_scene = llm_service._clean_scene_numbers(scene_content)

    # Helper to build base messages
    def build_base_messages():
        msgs = [{"role": "system", "content": system_prompt.strip()}]
        msgs.extend(context_messages)
        return msgs

    # 1. Choice Generation (reference)
    msgs = build_base_messages()
    final_msg = prompt_manager.get_prompt(
        "choice_generation", "user",
        scene_content=cleaned_scene,
        choices_count=choices_count
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="choice_generation",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 2. Plot Extraction
    msgs = build_base_messages()
    key_events = ["Event 1: Character discovers truth", "Event 2: Confrontation occurs"]
    key_events_formatted = json.dumps(key_events, indent=2, ensure_ascii=False)
    final_msg = prompt_manager.get_prompt(
        "plot_extraction", "user",
        scene_content=cleaned_scene,
        key_events=key_events_formatted
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="plot_extraction",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 3. Combined Extraction
    msgs = build_base_messages()
    character_names_str = ", ".join(character_names) if character_names else "None"
    explicit_names_str = ", ".join(explicit_names) if explicit_names else "None"
    thread_section = "\n- Plot thread 1\n- Plot thread 2"
    final_msg = prompt_manager.get_prompt(
        "combined_extraction", "user",
        scene_content=cleaned_scene,
        character_names=character_names_str,
        explicit_names=explicit_names_str,
        thread_section=thread_section
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="combined_extraction",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 4. Working Memory
    msgs = build_base_messages()
    final_msg = prompt_manager.get_prompt(
        "working_memory_cache_friendly", "user",
        scene_content=cleaned_scene,
        current_focus="Character tension, emotional beat"
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="working_memory",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 5. Relationship Extraction
    msgs = build_base_messages()
    final_msg = prompt_manager.get_prompt(
        "relationship_cache_friendly", "user",
        scene_content=cleaned_scene,
        character_names=character_names_str,
        characters="Alice, Bob",
        previous_relationships="Alice <-> Bob: friends (strength: 0.5)"
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="relationship_extraction",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 6. NPC Extraction
    msgs = build_base_messages()
    final_msg = prompt_manager.get_prompt(
        "npc_extraction_cache_friendly", "user",
        scene_content=cleaned_scene,
        explicit_names=explicit_names_str
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="npc_extraction",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 7. Character Moments Extraction
    msgs = build_base_messages()
    final_msg = prompt_manager.get_prompt(
        "character_moments_cache_friendly", "user",
        scene_content=cleaned_scene,
        character_names=character_names_str
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="character_moments",
        messages=msgs,
        final_message_preview=final_msg
    ))

    # 8. Plot Events Fallback
    msgs = build_base_messages()
    final_msg = prompt_manager.get_prompt(
        "plot_events_cache_friendly", "user",
        scene_content=cleaned_scene,
        thread_context="\n- Active thread 1\n- Active thread 2"
    )
    msgs.append({"role": "user", "content": final_msg})
    extractions.append(ExtractionMessages(
        name="plot_events_fallback",
        messages=msgs,
        final_message_preview=final_msg
    ))

    return extractions


async def main():
    print("=" * 80)
    print("CACHE-FRIENDLINESS TEST")
    print("=" * 80)
    print()

    db = SessionLocal()

    try:
        # Find "memory rest" story or any story with scenes
        story = db.query(Story).filter(Story.title.ilike("%memory%")).first()
        if not story:
            # Fallback to any story with scenes
            story = db.query(Story).join(Scene).filter(Scene.is_deleted == False).first()

        if not story:
            print("ERROR: No story with scenes found in database")
            return

        print(f"Using story: {story.title} (ID: {story.id})")

        # Get active branch
        active_branch = db.query(StoryBranch).filter(
            StoryBranch.story_id == story.id,
            StoryBranch.is_active == True
        ).first()

        if not active_branch:
            print("ERROR: No active branch found")
            return

        print(f"Active branch: {active_branch.name} (ID: {active_branch.id})")

        # Get a scene with content
        scene = db.query(Scene).join(StoryFlow).filter(
            StoryFlow.story_id == story.id,
            StoryFlow.branch_id == active_branch.id,
            StoryFlow.is_active == True,
            Scene.is_deleted == False
        ).order_by(Scene.sequence_number.desc()).first()

        if not scene:
            print("ERROR: No scene found")
            return

        # Get scene content
        variant = db.query(SceneVariant).join(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()

        if not variant or not variant.content:
            print("ERROR: No scene content found")
            return

        scene_content = variant.content
        print(f"Scene: #{scene.sequence_number} (ID: {scene.id})")
        print(f"Content length: {len(scene_content)} chars")
        print()

        # Get character names
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

        # Build user settings (mock)
        user_settings = {
            "generation_preferences": {
                "scene_length": "medium",
                "choices_count": 4,
                "separate_choice_generation": False
            },
            "context_settings": {
                "scene_batch_size": 10,
                "context_strategy": "semantic"
            },
            "llm_settings": {
                "temperature": 0.7
            }
        }
        user_id = 1

        # Build context
        print("Building scene generation context...")
        context_manager = get_context_manager_for_user(user_settings, user_id)
        context = await context_manager.build_scene_generation_context(
            story.id, db, "", is_variant_generation=False
        )
        print(f"Context built with {len(context)} keys")
        print()

        # Build messages for all extraction types
        print("Building messages for all extraction types...")
        extractions = await build_extraction_messages(
            db=db,
            story_id=story.id,
            scene_content=scene_content,
            context=context,
            user_id=user_id,
            user_settings=user_settings,
            character_names=character_names,
            explicit_names=[n.lower() for n in character_names]
        )
        print(f"Built messages for {len(extractions)} extraction types")
        print()

        # Compare prefixes
        print("=" * 80)
        print("COMPARISON RESULTS")
        print("=" * 80)
        print()

        results = compare_message_prefixes(extractions)

        # Print summary
        print(f"Total extractions tested: {results['total_extractions']}")
        print(f"Reference: {results.get('reference', {}).get('name', 'N/A')}")
        print()

        print("Message counts per extraction:")
        for name, count in results["message_counts"].items():
            print(f"  - {name}: {count} messages")
        print()

        print("Prefix comparison (messages 1 to N-1):")
        for detail in results["details"]:
            status = "✅ MATCH" if detail["prefix_matches_reference"] else "❌ MISMATCH"
            print(f"  - {detail['name']}: {status} ({detail['prefix_messages']} prefix messages)")
        print()

        if results["all_match"]:
            print("=" * 80)
            print("✅ ALL EXTRACTIONS ARE CACHE-FRIENDLY!")
            print("=" * 80)
            print()
            print("All extraction types share identical message prefixes.")
            print("Only the final USER message differs (extraction instruction).")
            print("This ensures maximum LLM prompt cache hits.")
        else:
            print("=" * 80)
            print("❌ CACHE FRIENDLINESS ISSUES DETECTED!")
            print("=" * 80)
            print()
            print("Differences found:")
            for diff in results["differences"]:
                print(f"  - {diff['extraction']} vs {diff['reference']}: {diff['issue']}")
                if "detail" in diff:
                    print(f"    Detail: {diff['detail']}")
                if "content_length_diff" in diff:
                    print(f"    Content length: {diff['content_length_diff']}")

        print()
        print("=" * 80)
        print("DETAILED MESSAGE STRUCTURE")
        print("=" * 80)
        print()

        for ext in extractions:
            print(f"--- {ext.name} ---")
            print(f"Total messages: {len(ext.messages)}")
            for i, msg in enumerate(ext.messages):
                role = msg.get("role", "unknown")
                content_len = len(msg.get("content", ""))
                is_final = i == len(ext.messages) - 1
                marker = " [FINAL - DIFFERS]" if is_final else " [CACHED]"
                print(f"  [{i}] {role}: {content_len} chars{marker}")
            print()

        print("=" * 80)
        print("FINAL MESSAGE PREVIEWS")
        print("=" * 80)
        print()

        for ext in extractions:
            print(f"--- {ext.name} ---")
            preview = ext.final_message_preview[:500]
            if len(ext.final_message_preview) > 500:
                preview += "..."
            print(preview)
            print()

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
