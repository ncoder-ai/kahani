#!/usr/bin/env python3
"""
Trigger extraction methods to generate prompt debug files for testing.

This uses the ACTUAL prefix from scene generation to verify
the cache-friendly prefix is working correctly.
"""

import sys
import os
import json

sys.path.insert(0, '/app')
os.chdir('/app')

# Suppress logging noise
import logging
logging.getLogger('app').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

def trigger_extractions():
    print("\n" + "="*70)
    print("TRIGGERING EXTRACTION METHODS TO GENERATE PROMPT FILES")
    print("="*70 + "\n")

    # Load the scene generation prompt to get the ACTUAL prefix
    scene_prompt_path = '/app/root_logs/prompt_sent_scene.json'
    if not os.path.exists(scene_prompt_path):
        print("❌ No scene prompt found. Generate a scene first.")
        return

    with open(scene_prompt_path) as f:
        scene_data = json.load(f)

    # Get the prefix (all messages except the last one)
    all_messages = scene_data['messages']
    prefix = all_messages[:-1]  # Everything except final task message

    print(f"Using prefix from scene generation: {len(prefix)} messages")
    print(f"System prompt length: {len(prefix[0]['content'])} chars\n")

    # Import prompt manager for final messages
    from app.services.llm.prompts import prompt_manager

    # Mock scene content for extraction
    mock_scene = """
    Radhika stepped into the kitchen, her new dress catching the morning light.
    "Good morning," Ali said, looking up from his coffee with appreciation.
    She smiled and moved to the counter, aware of his gaze following her.
    """

    print("Generating extraction prompt files with same prefix...\n")

    # Test 1: Combined Extraction
    print("1. Creating prompt_combined_extraction.json...")
    try:
        final_message = prompt_manager.get_prompt(
            "combined_extraction", "user",
            scene_content=mock_scene,
            character_names="Radhika, Ali",
            explicit_names="Radhika, Ali",
            thread_section=""
        )

        messages = prefix.copy()
        messages.append({"role": "user", "content": final_message})

        debug_data = {
            "extraction_type": "combined",
            "messages": messages,
            "generation_parameters": {"max_tokens": 4000, "temperature": 0.3}
        }
        with open('/app/root_logs/prompt_combined_extraction.json', 'w') as f:
            json.dump(debug_data, f, indent=2)
        print(f"   ✅ Created with {len(messages)} messages")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 2: Plot Extraction
    print("2. Creating prompt_plot_extraction.json...")
    try:
        key_events = ["Morning greeting between couple", "Appreciation of new dress"]
        key_events_formatted = json.dumps(key_events, indent=2)

        final_message = prompt_manager.get_prompt(
            "plot_extraction", "user",
            scene_content=mock_scene,
            key_events=key_events_formatted
        )

        messages = prefix.copy()
        messages.append({"role": "user", "content": final_message})

        debug_data = {
            "extraction_type": "plot_events",
            "messages": messages,
            "generation_parameters": {"max_tokens": 500, "temperature": 0.3}
        }
        with open('/app/root_logs/prompt_plot_extraction.json', 'w') as f:
            json.dump(debug_data, f, indent=2)
        print(f"   ✅ Created with {len(messages)} messages")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 3: Entity Extraction
    print("3. Creating prompt_entity_extraction.json...")
    try:
        final_message = prompt_manager.get_prompt(
            "entity_only_extraction", "user",
            scene_content=mock_scene,
            character_names="Radhika, Ali",
            chapter_location="Kitchen"
        )

        messages = prefix.copy()
        messages.append({"role": "user", "content": final_message})

        debug_data = {
            "extraction_type": "entity_only",
            "messages": messages,
            "generation_parameters": {"max_tokens": 2000, "temperature": 0.3}
        }
        with open('/app/root_logs/prompt_entity_extraction.json', 'w') as f:
            json.dump(debug_data, f, indent=2)
        print(f"   ✅ Created with {len(messages)} messages")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 4: Relationship Extraction
    print("4. Creating prompt_relationship_extraction.json...")
    try:
        final_message = prompt_manager.get_prompt(
            "relationship_cache_friendly", "user",
            scene_content=mock_scene,
            character_names="Radhika, Ali",
            characters="Radhika, Ali",
            previous_relationships="Married couple"
        )

        messages = prefix.copy()
        messages.append({"role": "user", "content": final_message})

        debug_data = {
            "extraction_type": "relationship",
            "messages": messages,
            "generation_parameters": {"max_tokens": 1024, "temperature": 0.3}
        }
        with open('/app/root_logs/prompt_relationship_extraction.json', 'w') as f:
            json.dump(debug_data, f, indent=2)
        print(f"   ✅ Created with {len(messages)} messages")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 5: NPC Extraction
    print("5. Creating prompt_npc_extraction.json...")
    try:
        final_message = prompt_manager.get_prompt(
            "npc_extraction_cache_friendly", "user",
            scene_content=mock_scene,
            explicit_names="Radhika, Ali"
        )

        messages = prefix.copy()
        messages.append({"role": "user", "content": final_message})

        debug_data = {
            "extraction_type": "npc",
            "messages": messages,
            "generation_parameters": {"max_tokens": 1500, "temperature": 0.3}
        }
        with open('/app/root_logs/prompt_npc_extraction.json', 'w') as f:
            json.dump(debug_data, f, indent=2)
        print(f"   ✅ Created with {len(messages)} messages")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 6: Character Moments
    print("6. Creating prompt_character_moments.json...")
    try:
        final_message = prompt_manager.get_prompt(
            "character_moments_cache_friendly", "user",
            scene_content=mock_scene,
            character_names="Radhika, Ali"
        )

        messages = prefix.copy()
        messages.append({"role": "user", "content": final_message})

        debug_data = {
            "extraction_type": "character_moments",
            "messages": messages,
            "generation_parameters": {"max_tokens": 1500, "temperature": 0.3}
        }
        with open('/app/root_logs/prompt_character_moments.json', 'w') as f:
            json.dump(debug_data, f, indent=2)
        print(f"   ✅ Created with {len(messages)} messages")

    except Exception as e:
        print(f"   ❌ Failed: {e}")

    print("\n" + "="*70)
    print("DONE - All extraction prompts use same prefix as scene generation")
    print("="*70 + "\n")

if __name__ == "__main__":
    trigger_extractions()
