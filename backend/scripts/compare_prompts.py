#!/usr/bin/env python3
"""
Compare prompt JSON files to verify cache-friendly structure.

Checks that all extraction prompts share the same message prefix as scene generation,
which is required for prompt caching to work.

Usage:
    python scripts/compare_prompts.py
    # or from docker:
    docker compose exec backend python scripts/compare_prompts.py
"""

import json
import os
import sys
from pathlib import Path

# Determine logs directory - check Docker first, then bare-metal
if os.path.exists("/app/root_logs"):
    LOGS_DIR = Path("/app/root_logs")
elif os.path.exists("/app/logs"):
    LOGS_DIR = Path("/app/logs")
else:
    LOGS_DIR = Path(__file__).parent.parent / "logs"

def load_json(filename: str) -> dict | None:
    """Load a JSON file from logs directory."""
    path = LOGS_DIR / filename
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_message_prefix(data: dict, exclude_last_n: int = 1) -> list:
    """Get all messages except the last N (which differ per extraction type)."""
    messages = data.get("messages", [])
    if len(messages) <= exclude_last_n:
        return messages
    return messages[:-exclude_last_n]

def compare_messages(base_messages: list, other_messages: list) -> tuple[bool, str]:
    """Compare two message lists and return (match, diff_description)."""
    if len(base_messages) != len(other_messages):
        return False, f"Length mismatch: {len(base_messages)} vs {len(other_messages)}"

    for i, (base, other) in enumerate(zip(base_messages, other_messages)):
        if base.get("role") != other.get("role"):
            return False, f"Message {i}: role mismatch ({base.get('role')} vs {other.get('role')})"
        if base.get("content") != other.get("content"):
            # Show first difference
            base_content = base.get("content", "")[:100]
            other_content = other.get("content", "")[:100]
            return False, f"Message {i}: content differs\n  Base: {base_content}...\n  Other: {other_content}..."

    return True, "Match"

def main():
    print("=" * 70)
    print("PROMPT CACHE COMPARISON")
    print("=" * 70)
    print(f"\nLogs directory: {LOGS_DIR}\n")

    # Load base prompt (scene generation) - try new name first, then old
    base = load_json("prompt_sent_scene.json")
    base_filename = "prompt_sent_scene.json"
    if not base:
        base = load_json("prompt_sent.json")
        base_filename = "prompt_sent.json"
    if not base:
        print("❌ No scene prompt found - generate a scene first!")
        print("   Expected: prompt_sent_scene.json or prompt_sent.json")
        sys.exit(1)

    base_prefix = get_message_prefix(base, exclude_last_n=1)
    print(f"Base: {base_filename} ({len(base.get('messages', []))} messages, prefix={len(base_prefix)})")
    print("-" * 70)

    # List of all prompt files to compare
    prompt_files = [
        # Generation methods
        ("prompt_sent_scene.json", "Scene generation"),
        ("prompt_sent_variant.json", "Variant generation"),
        ("prompt_sent_continuation.json", "Continuation generation"),
        ("prompt_sent_conclusion.json", "Chapter conclusion"),
        ("prompt_sent_choices.json", "Choice generation"),
        # Extraction methods
        ("prompt_entity_extraction.json", "Entity extraction (inline)"),
        ("prompt_combined_extraction.json", "Combined extraction"),
        ("prompt_batch_extraction.json", "Batch extraction"),
        ("prompt_working_memory.json", "Working memory extraction"),
        ("prompt_relationship_extraction.json", "Relationship extraction"),
        ("prompt_plot_extraction.json", "Plot events (cache-friendly)"),
        ("prompt_plot_fallback_extraction.json", "Plot events (fallback)"),
        ("prompt_npc_extraction.json", "NPC extraction"),
        ("prompt_character_moments.json", "Character moments extraction"),
    ]

    found_any = False
    all_match = True

    for filename, description in prompt_files:
        # Skip the base file
        if filename == base_filename:
            continue
        data = load_json(filename)
        if data is None:
            print(f"⚪ {filename}: Not found")
            continue

        found_any = True
        messages = data.get("messages", [])
        prefix = get_message_prefix(data, exclude_last_n=1)

        # Check if it's the old format (only 2 messages = not cache-friendly)
        if len(messages) <= 2:
            print(f"❌ {filename}: Only {len(messages)} messages - NOT CACHE-FRIENDLY!")
            all_match = False
            continue

        match, diff = compare_messages(base_prefix, prefix)

        if match:
            print(f"✅ {filename}: {len(messages)} msgs, prefix matches ({len(prefix)} msgs)")
        else:
            print(f"❌ {filename}: {len(messages)} msgs, PREFIX MISMATCH!")
            print(f"   {diff}")
            all_match = False

    print("-" * 70)

    if not found_any:
        print("\n⚠️  No extraction files found. Generate a scene to create them.")
    elif all_match:
        print("\n✅ All extraction prompts share the same prefix - CACHE-FRIENDLY!")
    else:
        print("\n❌ Some prompts don't match - check the mismatches above.")

    # Show system prompt preview
    print("\n" + "=" * 70)
    print("SYSTEM PROMPT PREVIEW (first 500 chars)")
    print("=" * 70)
    if base.get("messages"):
        system_msg = base["messages"][0].get("content", "")[:500]
        print(system_msg + "...")

if __name__ == "__main__":
    main()
