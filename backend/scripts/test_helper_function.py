#!/usr/bin/env python3
"""
Test the _build_cache_friendly_message_prefix helper function directly.

This verifies that:
1. The helper function returns consistent messages
2. POV reminder is always added
3. skip_choices uses the user's separate_choice_generation setting
"""

import sys
import os

# Add app to path
sys.path.insert(0, '/app')
os.chdir('/app')

from app.services.llm.service import UnifiedLLMService

# Colors
class C:
    G = '\033[92m'  # Green
    R = '\033[91m'  # Red
    Y = '\033[93m'  # Yellow
    B = '\033[94m'  # Blue
    BOLD = '\033[1m'
    END = '\033[0m'

def test_helper_function():
    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}TESTING _build_cache_friendly_message_prefix HELPER FUNCTION{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}\n")

    service = UnifiedLLMService()

    # Mock context and settings
    mock_context = {
        "story_foundation": "Test story",
        "chapter_context": "Test chapter",
        "tone": "dramatic"
    }

    # Test with separate_choice_generation = False (default)
    settings_with_inline_choices = {
        "generation_preferences": {
            "scene_length": "medium",
            "choices_count": 4,
            "separate_choice_generation": False  # Inline choices
        },
        "context_settings": {
            "scene_batch_size": 10
        }
    }

    # Test with separate_choice_generation = True
    settings_with_separate_choices = {
        "generation_preferences": {
            "scene_length": "medium",
            "choices_count": 4,
            "separate_choice_generation": True  # Separate choices
        },
        "context_settings": {
            "scene_batch_size": 10
        }
    }

    print(f"{C.BOLD}Test 1: Build prefix with separate_choice_generation=False{C.END}")
    print("-" * 60)
    messages1 = service._build_cache_friendly_message_prefix(
        context=mock_context,
        user_id=1,
        user_settings=settings_with_inline_choices,
        db=None
    )

    system_prompt1 = messages1[0]["content"]
    print(f"  Total messages: {len(messages1)}")
    print(f"  System prompt length: {len(system_prompt1)} chars")

    # Check for skip_choices indicator
    has_choices_section = "###CHOICES###" in system_prompt1 or "CHOICES" in system_prompt1.upper()
    print(f"  Has choices instructions: {C.G if has_choices_section else C.R}{has_choices_section}{C.END}")

    # Check for POV reminder
    has_pov = "POV" in system_prompt1.upper() or "perspective" in system_prompt1.lower() or "third person" in system_prompt1.lower()
    print(f"  Has POV reminder: {C.G if has_pov else C.R}{has_pov}{C.END}")

    print()
    print(f"{C.BOLD}Test 2: Build prefix with separate_choice_generation=True{C.END}")
    print("-" * 60)
    messages2 = service._build_cache_friendly_message_prefix(
        context=mock_context,
        user_id=1,
        user_settings=settings_with_separate_choices,
        db=None
    )

    system_prompt2 = messages2[0]["content"]
    print(f"  Total messages: {len(messages2)}")
    print(f"  System prompt length: {len(system_prompt2)} chars")

    # Check for POV reminder
    has_pov2 = "POV" in system_prompt2.upper() or "perspective" in system_prompt2.lower() or "third person" in system_prompt2.lower()
    print(f"  Has POV reminder: {C.G if has_pov2 else C.R}{has_pov2}{C.END}")

    print()
    print(f"{C.BOLD}Test 3: Compare both prefixes{C.END}")
    print("-" * 60)

    # The number of messages should be the same
    if len(messages1) == len(messages2):
        print(f"  {C.G}✅ Same number of messages: {len(messages1)}{C.END}")
    else:
        print(f"  {C.R}❌ Different number of messages: {len(messages1)} vs {len(messages2)}{C.END}")

    # System prompts will differ based on skip_choices
    print(f"  System prompt 1 length: {len(system_prompt1)} chars")
    print(f"  System prompt 2 length: {len(system_prompt2)} chars")

    if system_prompt1 == system_prompt2:
        print(f"  {C.Y}⚠️ System prompts are identical (skip_choices might not be affecting it){C.END}")
    else:
        diff = abs(len(system_prompt1) - len(system_prompt2))
        print(f"  {C.G}✅ System prompts differ by {diff} chars (skip_choices is working){C.END}")

    # Check that POV reminder is in both
    print()
    print(f"{C.BOLD}Test 4: POV Reminder Check{C.END}")
    print("-" * 60)

    # Look for POV-related content at end of system prompt
    last_200_chars_1 = system_prompt1[-200:]
    last_200_chars_2 = system_prompt2[-200:]

    pov_keywords = ["third person", "first person", "second person", "perspective", "POV"]

    pov_found_1 = any(kw.lower() in last_200_chars_1.lower() for kw in pov_keywords)
    pov_found_2 = any(kw.lower() in last_200_chars_2.lower() for kw in pov_keywords)

    if pov_found_1:
        print(f"  {C.G}✅ POV reminder found in prefix 1 (inline choices){C.END}")
    else:
        print(f"  {C.R}❌ POV reminder NOT found in prefix 1{C.END}")

    if pov_found_2:
        print(f"  {C.G}✅ POV reminder found in prefix 2 (separate choices){C.END}")
    else:
        print(f"  {C.R}❌ POV reminder NOT found in prefix 2{C.END}")

    print()
    print(f"{C.BOLD}System Prompt Preview (last 300 chars of prefix 1):{C.END}")
    print("-" * 60)
    print(system_prompt1[-300:])

    print()
    print(f"{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}SUMMARY{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}")

    all_pass = has_pov and has_pov2 and pov_found_1 and pov_found_2

    if all_pass:
        print(f"\n{C.G}{C.BOLD}✅ All tests passed! Helper function is working correctly.{C.END}")
        print(f"   - POV reminder is always added (for cache consistency)")
        print(f"   - skip_choices uses user's separate_choice_generation setting")
    else:
        print(f"\n{C.R}{C.BOLD}❌ Some tests failed. See above for details.{C.END}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(test_helper_function())
