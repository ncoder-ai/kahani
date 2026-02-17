"""
Context Formatter Module

Provides functions to format story context dictionaries into text strings
for LLM prompts. These are used for various generation tasks like titles,
scenarios, plots, summaries, etc.
"""

import re
import logging
from typing import Dict, Any, List, Tuple

from .prompts import prompt_manager

logger = logging.getLogger(__name__)


def get_scene_length_description(scene_length: str) -> str:
    """Convert scene_length setting to word range description"""
    length_map = {
        "short": "approximately 100-150 words",
        "medium": "approximately 200-300 words",
        "long": "approximately 400-500 words"
    }
    return length_map.get(scene_length, "approximately 200-300 words")


def format_context_for_titles(context: Dict[str, Any]) -> str:
    """Format context for title generation"""
    context_parts = []

    if context.get("genre"):
        context_parts.append(f"Genre: {context['genre']}")

    if context.get("tone"):
        context_parts.append(f"Tone: {context['tone']}")

    # Character information
    characters = context.get("characters", [])
    if characters:
        char_descriptions = []
        for char in characters:
            char_info = f"• {char.get('name', 'Unknown')}"
            if char.get('role'):
                char_info += f" ({char['role']})"
            if char.get('description'):
                char_info += f": {char['description']}"
            char_descriptions.append(char_info)
        context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")

    # Story scenario
    if context.get("scenario"):
        context_parts.append(f"Story Scenario:\n{context['scenario']}")

    # Story elements
    story_elements = context.get("story_elements", {})
    if story_elements:
        elements = []
        for key, value in story_elements.items():
            if value:
                elements.append(f"{key.title()}: {value}")
        if elements:
            context_parts.append(f"Story Elements:\n{chr(10).join(elements)}")

    return "\n".join(context_parts)


def format_context_for_continuation(context: Dict[str, Any]) -> str:
    """Format context for scene continuation"""
    context_parts = []

    if context.get("genre"):
        context_parts.append(f"Genre: {context['genre']}")

    if context.get("tone"):
        context_parts.append(f"Tone: {context['tone']}")

    if context.get("characters"):
        char_descriptions = [f"- {char.get('name', 'Unknown')}: {char.get('description', 'No description')}"
                           for char in context["characters"]]
        context_parts.append(f"Characters:\n{chr(10).join(char_descriptions)}")

    if context.get("previous_content"):
        context_parts.append(f"Previous content: {context['previous_content'][-600:]}")  # Last 600 chars

    if context.get("choice_made"):
        context_parts.append(f"Reader's choice: {context['choice_made']}")

    if context.get("current_situation"):
        context_parts.append(f"Current situation: {context['current_situation']}")

    if context.get("continuation_prompt"):
        context_parts.append(f"Continuation instruction: {context['continuation_prompt']}")

    return "\n".join(context_parts)


def format_context_for_scenario(context: Dict[str, Any]) -> str:
    """Format context for scenario generation"""
    context_parts = []

    if context.get("genre"):
        context_parts.append(f"Genre: {context['genre']}")

    if context.get("tone"):
        context_parts.append(f"Tone: {context['tone']}")

    # Character information
    characters = context.get("characters", [])
    if characters:
        char_descriptions = []
        for char in characters:
            char_info = f"• {char.get('name', 'Unknown')}"
            if char.get('role'):
                char_info += f" ({char['role']})"
            if char.get('description'):
                char_info += f": {char['description']}"
            char_descriptions.append(char_info)
        context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")

    return "\n".join(context_parts)


def format_elements_for_scenario(context: Dict[str, Any]) -> str:
    """Format story elements for scenario generation"""
    elements = []
    if context.get("opening"):
        elements.append(f"Story opening: {context['opening']}")
    if context.get("setting"):
        elements.append(f"Setting: {context['setting']}")
    if context.get("conflict"):
        elements.append(f"Driving force: {context['conflict']}")

    return "\n".join(elements)


def format_context_for_plot(context: Dict[str, Any]) -> str:
    """Format context for plot generation"""
    context_parts = []

    if context.get("genre"):
        context_parts.append(f"Genre: {context['genre']}")

    if context.get("tone"):
        context_parts.append(f"Tone: {context['tone']}")

    # Character information
    characters = context.get("characters", [])
    if characters:
        char_descriptions = []
        for char in characters:
            char_info = f"• {char.get('name', 'Unknown')}"
            if char.get('role'):
                char_info += f" ({char['role']})"
            if char.get('description'):
                char_info += f": {char['description']}"
            char_descriptions.append(char_info)
        context_parts.append(f"Main Characters:\n{chr(10).join(char_descriptions)}")

    # Story scenario
    if context.get("scenario"):
        context_parts.append(f"Story Scenario:\n{context['scenario']}")

    # World setting
    if context.get("world_setting"):
        context_parts.append(f"World Setting:\n{context['world_setting']}")

    return "\n".join(context_parts)


def format_context_for_chapters(context: Dict[str, Any]) -> str:
    """Format context for chapter generation"""
    return format_context_for_plot(context)  # Same format as plot


def format_context_for_summary(context: Dict[str, Any]) -> str:
    """Format context for summary generation"""
    context_parts = []

    if context.get("title"):
        context_parts.append(f"Title: {context['title']}")

    if context.get("genre"):
        context_parts.append(f"Genre: {context['genre']}")

    if context.get("scene_count"):
        context_parts.append(f"Number of scenes: {context['scene_count']}")

    return "\n".join(context_parts)


def format_characters_section(characters: Any, include_voice_style: bool = True) -> str:
    """
    Format characters section for context.

    Args:
        characters: Either a list of character dicts or a dict with active_characters/inactive_characters
        include_voice_style: Whether to include voice style in character descriptions (default: True)

    Returns:
        Formatted characters string
    """
    if not characters:
        return ""

    char_descriptions = []

    # Check if characters is a dict with active_characters/inactive_characters
    if isinstance(characters, dict) and "active_characters" in characters:
        active_chars = characters.get("active_characters", [])
        inactive_chars = characters.get("inactive_characters", [])

        # Active characters - full details
        if active_chars:
            char_descriptions.append("Active Characters (in this chapter):")
            for char in active_chars:
                char_desc = f"- {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_desc += f" ({char['role']})"
                char_desc += f": {char.get('description', 'No description')}"
                if char.get('personality'):
                    char_desc += f". Personality: {char['personality']}"
                if char.get('background'):
                    char_desc += f". Background: {char['background']}"
                if char.get('goals'):
                    char_desc += f". Goals: {char['goals']}"
                if char.get('fears'):
                    char_desc += f". Fears & Weaknesses: {char['fears']}"
                if char.get('appearance'):
                    char_desc += f". Appearance: {char['appearance']}"
                # Add voice/speech style if specified and requested
                if include_voice_style and char.get('voice_style'):
                    voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                    if voice_instruction:
                        char_desc += f"\n  {voice_instruction}"
                char_descriptions.append(char_desc)

        # Inactive characters - brief format
        if inactive_chars:
            char_descriptions.append("\nInactive Characters (available for reference):")
            for char in inactive_chars:
                char_desc = f"- {char.get('name', 'Unknown')}"
                if char.get('role'):
                    char_desc += f" ({char['role']})"
                char_descriptions.append(char_desc)
    else:
        # Legacy format - all characters are active
        for char in characters:
            char_desc = f"- {char.get('name', 'Unknown')}"
            if char.get('role'):
                char_desc += f" ({char['role']})"
            char_desc += f": {char.get('description', 'No description')}"
            if char.get('personality'):
                char_desc += f". Personality: {char['personality']}"
            if char.get('background'):
                char_desc += f". Background: {char['background']}"
            if char.get('goals'):
                char_desc += f". Goals: {char['goals']}"
            if char.get('fears'):
                char_desc += f". Fears & Weaknesses: {char['fears']}"
            if char.get('appearance'):
                char_desc += f". Appearance: {char['appearance']}"
            # Add voice/speech style if specified and requested
            if include_voice_style and char.get('voice_style'):
                voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
                if voice_instruction:
                    char_desc += f"\n  {voice_instruction}"
            char_descriptions.append(char_desc)

    if char_descriptions:
        return f"Characters:\n{chr(10).join(char_descriptions)}"
    return ""


def format_character_voice_styles(characters: Any) -> str:
    """
    Format character voice styles as a separate section.
    This is used to add emphasis to voice styles in multi-message format.

    Args:
        characters: Either a list of character dicts or a dict with active_characters/inactive_characters

    Returns:
        Formatted voice styles string, or empty string if no voice styles
    """
    if not characters:
        return ""

    voice_styles = []

    # Get the list of characters to process
    char_list = []
    if isinstance(characters, dict) and "active_characters" in characters:
        char_list = characters.get("active_characters", [])
    else:
        char_list = characters

    for char in char_list:
        if char.get('voice_style'):
            voice_instruction = prompt_manager.get_voice_style_instruction(char['voice_style'])
            if voice_instruction:
                voice_styles.append(f"**{char.get('name', 'Unknown')}**: {voice_instruction}")

    if voice_styles:
        return "\n".join(voice_styles)
    return ""


def batch_scenes_as_messages(scenes_text: str, batch_size: int = 10) -> List[Dict[str, str]]:
    """
    Parse scenes and group them into batch-aligned messages for optimal caching.

    Context manager now provides batch-aligned scenes, so:
    - All batches except the last are complete (have all scenes from batch_start to batch_end)
    - The last batch is the "active" batch that changes each scene

    Complete batches use fixed headers (=== SCENES 41-50 ===) for stable caching.
    Active batch uses fixed header (=== RECENT SCENES ===) for stable caching.

    Args:
        scenes_text: Raw text containing scenes in format "Scene XX: content"
        batch_size: Number of scenes per batch (default: 10)

    Returns:
        List of message dicts, one per batch
    """
    messages = []

    # Parse individual scenes using regex
    # Pattern matches "Scene XX:" followed by content until next "Scene XX:" or end
    scene_pattern = re.compile(r'Scene\s+(\d+):\s*(.*?)(?=Scene\s+\d+:|$)', re.DOTALL)
    matches = list(scene_pattern.finditer(scenes_text))

    if not matches:
        # No scene pattern found, return as single message
        if scenes_text.strip():
            messages.append({
                "role": "user",
                "content": "=== RECENT SCENES ===\n" + scenes_text.strip()
            })
        return messages

    # Group scenes by batch
    # Batch boundaries: 1-10, 11-20, 21-30, etc. (based on scene numbers, not indices)
    batches: Dict[int, List[Tuple[int, str]]] = {}

    for match in matches:
        scene_num = int(match.group(1))
        scene_content = match.group(2).strip()

        # Calculate batch number (0-indexed): scenes 1-10 -> batch 0, 11-20 -> batch 1, etc.
        batch_num = (scene_num - 1) // batch_size

        if batch_num not in batches:
            batches[batch_num] = []
        batches[batch_num].append((scene_num, scene_content))

    if not batches:
        return messages

    # Sort batches by batch number
    sorted_batch_nums = sorted(batches.keys())

    # The last batch in sorted order is the active batch (changes each scene)
    # All other batches are complete and stable (context_manager guarantees this)
    last_batch_idx = len(sorted_batch_nums) - 1

    for idx, batch_num in enumerate(sorted_batch_nums):
        scenes_in_batch = batches[batch_num]
        # Sort scenes within batch by scene number
        scenes_in_batch.sort(key=lambda x: x[0])

        # Calculate FIXED batch range based on batch number
        # Batch 4 is always scenes 41-50, batch 5 is always 51-60, etc.
        batch_start = batch_num * batch_size + 1
        batch_end = batch_start + batch_size - 1

        # Format scenes without "Scene X:" prefix to avoid teaching LLM bad habits
        formatted_scenes = []
        for scene_num, content in scenes_in_batch:
            formatted_scenes.append(content)

        batch_content = "\n\n".join(formatted_scenes)

        # Last batch is always the active batch (changes each scene)
        # All other batches are complete and stable (context_manager guarantees this)
        is_active_batch = (idx == last_batch_idx)

        if is_active_batch:
            # Active batch - use FIXED header for stable caching (scene numbers change content, not header)
            header = f"=== RECENT SCENES ==="
        else:
            # Complete batch - use FIXED batch boundaries for stable caching
            header = f"=== SCENES {batch_start}-{batch_end} ==="

        messages.append({
            "role": "user",
            "content": f"{header}\n{batch_content}"
        })

    logger.debug(f"[SCENE BATCHING] Created {len(messages)} batch messages from {len(matches)} scenes (batch_size={batch_size})")

    return messages
