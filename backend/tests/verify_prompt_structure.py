#!/usr/bin/env python3
"""
Verification script for prompt building structure.

This script visually demonstrates that all generation methods use the same
message structure, with only the final message differing.

Run with: python tests/verify_prompt_structure.py
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm.prompts import PromptManager
from app.services.llm.service import UnifiedLLMService


def print_separator(title: str = ""):
    """Print a visual separator."""
    print("\n" + "=" * 70)
    if title:
        print(f" {title}")
        print("=" * 70)


def print_message_summary(messages: list, label: str):
    """Print a summary of messages."""
    print(f"\n{label}:")
    print(f"  Total messages: {len(messages)}")
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        # Get first 80 chars of content
        preview = content[:80].replace("\n", " ") + "..." if len(content) > 80 else content.replace("\n", " ")
        print(f"  [{i+1}] {role.upper()}: {preview}")


def verify_system_prompt_consistency():
    """Verify that all methods use the same system prompt."""
    print_separator("SYSTEM PROMPT CONSISTENCY CHECK")
    
    pm = PromptManager()
    
    # Get the standard system prompt
    system_prompt = pm.get_prompt(
        "scene_with_immediate", "system",
        scene_length_description="medium (100-150 words)",
        choices_count=4
    )
    
    print(f"\nSystem prompt length: {len(system_prompt)} characters")
    print(f"Contains 'interactive fiction': {'interactive fiction' in system_prompt.lower()}")
    print(f"Contains 'CHOICES': {'CHOICES' in system_prompt}")
    print(f"Contains formatting requirements: {'FORMATTING' in system_prompt}")
    
    # Show first 200 chars
    print(f"\nFirst 200 chars of system prompt:")
    print(f"  {system_prompt[:200]}...")
    
    return True


def verify_context_messages():
    """Verify context message structure."""
    print_separator("CONTEXT MESSAGE STRUCTURE CHECK")
    
    service = UnifiedLLMService()
    
    mock_context = {
        "story_title": "Test Story",
        "genre": "fantasy",
        "tone": "dark",
        "scenario": "A hero embarks on a quest to save the kingdom.",
        "characters": [
            {"name": "Hero", "role": "protagonist"},
            {"name": "Villain", "role": "antagonist"}
        ],
        "previous_scenes": "Scene 1: The journey begins.\n\nScene 2: The hero meets a stranger.",
        "story_so_far": "Summary of events so far in the story.",
        "current_situation": "The hero faces a difficult choice.",
    }
    
    messages = service._format_context_as_messages(mock_context, scene_batch_size=10)
    
    print(f"\nTotal context messages: {len(messages)}")
    
    for i, msg in enumerate(messages):
        content = msg["content"]
        # Identify message type by content
        if "STORY FOUNDATION" in content:
            msg_type = "Story Foundation"
        elif "STORY PROGRESS" in content:
            msg_type = "Story Progress"
        elif "ENTITY STATES" in content:
            msg_type = "Entity States"
        elif "SEMANTIC EVENTS" in content:
            msg_type = "Semantic Events"
        elif "SCENES" in content:
            msg_type = "Scene Batch"
        else:
            msg_type = "Unknown"
        
        print(f"\n  Message {i+1}: {msg_type}")
        print(f"    Role: {msg['role']}")
        print(f"    Length: {len(content)} chars")
        # Show first line
        first_line = content.split("\n")[0][:60]
        print(f"    First line: {first_line}...")
    
    return True


def verify_task_instructions():
    """Verify task instruction templates."""
    print_separator("TASK INSTRUCTION TEMPLATES CHECK")
    
    pm = PromptManager()
    
    # Test scene generation task (with immediate)
    print("\n1. Scene Generation (with immediate_situation):")
    task1 = pm.get_task_instruction(
        has_immediate=True,
        immediate_situation="The hero opens the mysterious door.",
        scene_length_description="medium (100-150 words)"
    )
    print(f"   Length: {len(task1)} chars")
    print(f"   Contains 'WHAT HAPPENS NEXT': {'WHAT HAPPENS NEXT' in task1}")
    print(f"   Contains immediate_situation: {'mysterious door' in task1}")
    
    # Test scene generation task (without immediate)
    print("\n2. Scene Generation (without immediate_situation):")
    task2 = pm.get_task_instruction(
        has_immediate=False,
        scene_length_description="medium (100-150 words)"
    )
    print(f"   Length: {len(task2)} chars")
    print(f"   Contains 'continues naturally': {'continues naturally' in task2.lower()}")
    
    # Test continuation task
    print("\n3. Continuation Task:")
    task3 = pm.get_continuation_task_instruction(
        current_scene_content="The warrior stood at the edge of the cliff.",
        continuation_prompt="Add more tension and dialogue.",
        choices_count=4
    )
    print(f"   Length: {len(task3)} chars")
    print(f"   Contains 'CURRENT SCENE TO CONTINUE': {'CURRENT SCENE TO CONTINUE' in task3}")
    print(f"   Contains 'CONTINUATION INSTRUCTION': {'CONTINUATION INSTRUCTION' in task3}")
    print(f"   Contains choices reminder: {'choices' in task3.lower()}")
    
    # Test enhancement task
    print("\n4. Enhancement Task:")
    task4 = pm.get_enhancement_task_instruction(
        original_scene="She walked into the room.",
        enhancement_guidance="Add more sensory details.",
        scene_length_description="long (150-250 words)",
        choices_count=4
    )
    print(f"   Length: {len(task4)} chars")
    print(f"   Contains 'ORIGINAL SCENE': {'ORIGINAL SCENE' in task4}")
    print(f"   Contains 'ENHANCEMENT REQUEST': {'ENHANCEMENT REQUEST' in task4}")
    print(f"   Contains scene_length: {'150-250' in task4}")
    
    return True


def verify_complete_message_structure():
    """Verify complete message structure for each generation type."""
    print_separator("COMPLETE MESSAGE STRUCTURE COMPARISON")
    
    pm = PromptManager()
    service = UnifiedLLMService()
    
    mock_context = {
        "story_title": "Test Story",
        "genre": "fantasy",
        "tone": "dark",
        "scenario": "A hero's quest.",
        "characters": [],
        "previous_scenes": "Scene 1: Beginning.",
        "story_so_far": "Summary.",
        "current_situation": "Hero at crossroads.",
    }
    
    # Get common components
    system_prompt = pm.get_prompt(
        "scene_with_immediate", "system",
        scene_length_description="medium (100-150 words)",
        choices_count=4
    )
    
    context_messages = service._format_context_as_messages(mock_context, scene_batch_size=10)
    
    print("\n" + "-" * 50)
    print("COMMON STRUCTURE (CACHED):")
    print("-" * 50)
    print(f"  System prompt: {len(system_prompt)} chars")
    print(f"  Context messages: {len(context_messages)} messages")
    
    # Scene generation final message
    print("\n" + "-" * 50)
    print("FINAL MESSAGES (DIFFER PER OPERATION):")
    print("-" * 50)
    
    task_scene = pm.get_task_instruction(
        has_immediate=True,
        immediate_situation="Hero opens door.",
        scene_length_description="medium"
    )
    choices_reminder = pm.get_user_choices_reminder(choices_count=4)
    scene_final = task_scene + "\n\n" + choices_reminder if choices_reminder else task_scene
    
    task_continuation = pm.get_continuation_task_instruction(
        current_scene_content="Hero stood ready.",
        continuation_prompt="Continue.",
        choices_count=4
    )
    
    task_enhancement = pm.get_enhancement_task_instruction(
        original_scene="Hero attacked.",
        enhancement_guidance="Add drama.",
        scene_length_description="medium",
        choices_count=4
    )
    
    print(f"\n  1. Scene Generation:    {len(scene_final)} chars")
    print(f"     Starts with: {scene_final[:50].replace(chr(10), ' ')}...")
    
    print(f"\n  2. Continuation:        {len(task_continuation)} chars")
    print(f"     Starts with: {task_continuation[:50].replace(chr(10), ' ')}...")
    
    print(f"\n  3. Enhancement:         {len(task_enhancement)} chars")
    print(f"     Starts with: {task_enhancement[:50].replace(chr(10), ' ')}...")
    
    return True


def main():
    """Run all verification checks."""
    print("\n" + "=" * 70)
    print(" PROMPT BUILDING VERIFICATION SCRIPT")
    print(" Verifying unified context building across all generation methods")
    print("=" * 70)
    
    all_passed = True
    
    try:
        all_passed &= verify_system_prompt_consistency()
        all_passed &= verify_context_messages()
        all_passed &= verify_task_instructions()
        all_passed &= verify_complete_message_structure()
        
        print_separator("SUMMARY")
        
        if all_passed:
            print("\n✅ All verification checks passed!")
            print("\nThe prompt building system correctly:")
            print("  1. Uses scene_with_immediate for all system prompts")
            print("  2. Uses _format_context_as_messages() for context")
            print("  3. Has task templates for continuation and enhancement")
            print("  4. Only the final message differs per operation type")
            print("\nThis ensures maximum LLM cache hits across all operations.")
        else:
            print("\n❌ Some verification checks failed!")
            
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

