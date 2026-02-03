#!/usr/bin/env python3
"""
Test script to verify cache-friendly message prefix implementation.

This script:
1. Loads all prompt debug JSON files
2. Compares them message-by-message
3. Shows detailed output of any differences
4. Verifies that all prompts share the same prefix

Usage:
    docker compose exec backend python scripts/test_cache_prefix.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional
import hashlib

# Determine logs directory
if os.path.exists("/app/root_logs"):
    LOGS_DIR = Path("/app/root_logs")
elif os.path.exists("/app/logs"):
    LOGS_DIR = Path("/app/logs")
else:
    LOGS_DIR = Path(__file__).parent.parent / "logs"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def load_json(filename: str) -> Optional[dict]:
    """Load a JSON file from logs directory."""
    path = LOGS_DIR / filename
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_content_hash(content: str) -> str:
    """Get a short hash of content for comparison."""
    return hashlib.md5(content.encode()).hexdigest()[:8]

def truncate(text: str, max_len: int = 80) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."

def print_message_summary(msg: dict, index: int, indent: str = "  "):
    """Print a summary of a message."""
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    content_hash = get_content_hash(content)
    content_len = len(content)
    first_line = content.split("\n")[0][:60]

    print(f"{indent}[{index}] {Colors.CYAN}{role}{Colors.RESET} | {content_len:,} chars | hash:{content_hash} | {truncate(first_line, 50)}")

def compare_messages(msg1: dict, msg2: dict, index: int) -> tuple[bool, str]:
    """Compare two messages and return (match, description)."""
    role1, role2 = msg1.get("role"), msg2.get("role")
    content1, content2 = msg1.get("content", ""), msg2.get("content", "")

    if role1 != role2:
        return False, f"Role mismatch: '{role1}' vs '{role2}'"

    if content1 != content2:
        # Find first difference
        min_len = min(len(content1), len(content2))
        for i in range(min_len):
            if content1[i] != content2[i]:
                context_start = max(0, i - 20)
                context_end = min(len(content1), i + 20)
                return False, f"Content differs at char {i}:\n      Base: ...{content1[context_start:context_end]}...\n      Other: ...{content2[context_start:context_end]}..."

        # Length difference
        return False, f"Content length differs: {len(content1)} vs {len(content2)} chars"

    return True, "Match"

def main():
    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}CACHE-FRIENDLY MESSAGE PREFIX TEST{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"\n{Colors.BLUE}Logs directory:{Colors.RESET} {LOGS_DIR}\n")

    # List available prompt files
    print(f"{Colors.BOLD}Available prompt files:{Colors.RESET}")
    prompt_files = sorted(LOGS_DIR.glob("prompt_*.json"))
    if not prompt_files:
        print(f"  {Colors.RED}No prompt files found!{Colors.RESET}")
        print(f"  Generate a scene first to populate the debug files.")
        sys.exit(1)

    for f in prompt_files:
        size = f.stat().st_size
        print(f"  - {f.name} ({size:,} bytes)")

    print()

    # Load base prompt (scene generation)
    base = load_json("prompt_sent_scene.json")
    base_filename = "prompt_sent_scene.json"
    if not base:
        base = load_json("prompt_sent.json")
        base_filename = "prompt_sent.json"
    if not base:
        print(f"{Colors.RED}No base scene prompt found!{Colors.RESET}")
        print("Expected: prompt_sent_scene.json or prompt_sent.json")
        sys.exit(1)

    base_messages = base.get("messages", [])

    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}BASE PROMPT: {base_filename}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"Total messages: {len(base_messages)}")
    print(f"Prefix messages (all except last): {len(base_messages) - 1}")
    print()

    print(f"{Colors.BOLD}Message breakdown:{Colors.RESET}")
    for i, msg in enumerate(base_messages):
        is_last = i == len(base_messages) - 1
        marker = f" {Colors.YELLOW}<-- FINAL (varies){Colors.RESET}" if is_last else f" {Colors.GREEN}<-- CACHED{Colors.RESET}"
        print_message_summary(msg, i)
        print(f"      {marker}")

    # Get base prefix (all messages except last)
    base_prefix = base_messages[:-1] if len(base_messages) > 1 else base_messages

    # List of files to compare
    comparison_files = [
        ("prompt_sent_scene.json", "Scene generation"),
        ("prompt_sent_variant.json", "Variant generation"),
        ("prompt_sent_continuation.json", "Continuation generation"),
        ("prompt_sent_conclusion.json", "Chapter conclusion"),
        ("prompt_sent_choices.json", "Choice generation"),
        ("prompt_entity_extraction.json", "Entity extraction"),
        ("prompt_combined_extraction.json", "Combined extraction"),
        ("prompt_batch_extraction.json", "Batch extraction"),
        ("prompt_working_memory.json", "Working memory"),
        ("prompt_relationship_extraction.json", "Relationship extraction"),
        ("prompt_plot_extraction.json", "Plot extraction"),
        ("prompt_plot_fallback_extraction.json", "Plot fallback"),
        ("prompt_npc_extraction.json", "NPC extraction"),
        ("prompt_character_moments.json", "Character moments"),
    ]

    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}MESSAGE-BY-MESSAGE COMPARISON{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")

    results = []

    for filename, description in comparison_files:
        if filename == base_filename:
            continue

        data = load_json(filename)
        if not data:
            results.append((filename, description, "NOT_FOUND", None))
            continue

        messages = data.get("messages", [])
        prefix = messages[:-1] if len(messages) > 1 else messages

        # Compare prefix
        if len(prefix) != len(base_prefix):
            results.append((filename, description, "LENGTH_MISMATCH",
                          f"Prefix length: {len(prefix)} vs base: {len(base_prefix)}"))
            continue

        all_match = True
        first_diff = None
        for i, (base_msg, other_msg) in enumerate(zip(base_prefix, prefix)):
            match, diff = compare_messages(base_msg, other_msg, i)
            if not match:
                all_match = False
                first_diff = f"Message {i}: {diff}"
                break

        if all_match:
            results.append((filename, description, "MATCH", f"{len(messages)} messages"))
        else:
            results.append((filename, description, "CONTENT_MISMATCH", first_diff))

    # Print results
    match_count = 0
    mismatch_count = 0
    not_found_count = 0

    for filename, description, status, detail in results:
        if status == "NOT_FOUND":
            print(f"  {Colors.YELLOW}⚪{Colors.RESET} {filename}")
            print(f"      {description}: Not found (not yet generated)")
            not_found_count += 1
        elif status == "MATCH":
            print(f"  {Colors.GREEN}✅{Colors.RESET} {filename}")
            print(f"      {description}: {detail} - PREFIX MATCHES")
            match_count += 1
        else:
            print(f"  {Colors.RED}❌{Colors.RESET} {filename}")
            print(f"      {description}: {status}")
            print(f"      {Colors.RED}{detail}{Colors.RESET}")
            mismatch_count += 1
        print()

    # Summary
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}SUMMARY{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"  Matching prefixes: {Colors.GREEN}{match_count}{Colors.RESET}")
    print(f"  Mismatched prefixes: {Colors.RED}{mismatch_count}{Colors.RESET}")
    print(f"  Not found: {Colors.YELLOW}{not_found_count}{Colors.RESET}")
    print()

    if mismatch_count == 0 and match_count > 0:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ SUCCESS: All found prompts share the same prefix!{Colors.RESET}")
        print(f"   Cache hits will occur for the prefix ({len(base_prefix)} messages).")
    elif mismatch_count > 0:
        print(f"{Colors.RED}{Colors.BOLD}❌ FAILURE: Some prompts have mismatched prefixes!{Colors.RESET}")
        print(f"   This will cause cache misses.")
        sys.exit(1)
    else:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️ No comparison files found.{Colors.RESET}")
        print(f"   Generate scenes and trigger extractions to populate debug files.")

    # Show system prompt preview
    if base_messages:
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}SYSTEM PROMPT PREVIEW (first 500 chars){Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        system_content = base_messages[0].get("content", "")[:500]
        print(system_content)
        if len(base_messages[0].get("content", "")) > 500:
            print("...")

        # Check for POV reminder
        full_system = base_messages[0].get("content", "")
        if "POV CONSISTENCY" in full_system or "point of view" in full_system.lower():
            print(f"\n{Colors.GREEN}✅ POV reminder detected in system prompt{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}⚠️ No POV reminder found in system prompt{Colors.RESET}")

if __name__ == "__main__":
    main()
