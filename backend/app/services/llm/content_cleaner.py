"""
Content Cleaner Module

Provides functions to clean LLM-generated content by removing junk patterns,
instruction tags, scene numbers, and other artifacts that LLMs commonly add.
"""

import re
import logging
from typing import Optional

from app.services.llm.thinking_parser import ThinkingTagParser

logger = logging.getLogger(__name__)


def clean_scene_content(content: str) -> str:
    """
    Comprehensive cleaning of LLM-generated scene content.
    Removes various junk patterns that LLMs commonly add to scenes.
    Uses multi-pass cleaning to catch nested patterns.
    """
    if not content:
        return content

    original_content = content

    # Strip thinking/reasoning tags (e.g. <think>...</think>) that some models
    # emit inline in the text content rather than via the reasoning_content field
    content = ThinkingTagParser.strip_thinking_tags(content)

    # Multi-pass cleaning to catch nested patterns (max 3 passes)
    for pass_num in range(3):
        old_content = content

        # === AGGRESSIVE MARKDOWN HEADER REMOVAL ===
        # Remove ANY line that starts with markdown-style headers
        # These are NEVER legitimate prose - always LLM junk
        # Must come FIRST before other patterns
        # Exception: Preserve ###CHOICES### marker (used for choice generation)

        # Remove lines starting with 2+ hash marks (##, ###, ####, etc.)
        # But NOT ###CHOICES### (negative lookahead)
        content = re.sub(r'^#{2,}(?!#*CHOICES###)[^\n]*\n?', '', content, flags=re.MULTILINE | re.IGNORECASE).strip()

        # Remove lines starting with 2+ equals signs (==, ===, ====, etc.)
        content = re.sub(r'^={2,}[^\n]*\n?', '', content, flags=re.MULTILINE).strip()

        # Remove lines starting with 2+ dashes (--, ---, ----, etc.)
        content = re.sub(r'^-{2,}[^\n]*\n?', '', content, flags=re.MULTILINE).strip()

        # Remove lines starting with 2+ asterisks (**, ***, ****, etc.)
        # Preserves single * for thoughts
        content = re.sub(r'^\*{2,}[^\n]*\n?', '', content, flags=re.MULTILINE).strip()

        # === HEADER/PREFIX PATTERNS (at start of content) ===
        # Order matters: most specific patterns first, most general last

        # "WHAT HAPPENS NEXT" instruction echo - LLM sometimes echoes back the task instruction
        # Pattern: "####### WHAT HAPPENS NEXT #######" or "WHAT HAPPENS NEXT" followed by the user's text
        content = re.sub(r'^#{2,}\s*WHAT\s+HAPPENS\s+NEXT\s*#{2,}\s*\n?', '', content, flags=re.IGNORECASE).strip()
        content = re.sub(r'^WHAT\s+HAPPENS\s+NEXT\s*\n', '', content, flags=re.IGNORECASE).strip()
        # Also clean the closing delimiter if present
        content = re.sub(r'^#{2,}\s*\n?', '', content, flags=re.MULTILINE).strip()

        # Markdown scene headers with numbers: "### SCENE 113 ###", "## SCENE 7 ##"
        # Must come BEFORE generic scene markers to catch specific pattern
        content = re.sub(r'^#{1,6}\s*SCENE\s+\d+\s*#{1,6}\s*\n?', '', content, flags=re.IGNORECASE).strip()

        # Scene numbers and titles: "Scene 7:", "Scene 7: The Escape", "### Scene 7 ###", "SCENE 1"
        content = re.sub(r'^#{1,6}\s*Scene\s+\d+[^#\n]*#{0,6}\s*\n?', '', content, flags=re.IGNORECASE).strip()
        content = re.sub(r'^Scene\s+\d+(?:\s*[:\-]\s*[^\n]*)?\s*\n', '', content, flags=re.IGNORECASE).strip()

        # Standalone numbers as titles: "7:", "7. The Beginning"
        content = re.sub(r'^\d+[:.]\s*[A-Z][^.\n]*(\n|$)', '', content).strip()

        # Scene response markers: "=== SCENE RESPONSE ==="
        content = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s+RESPONSE\s*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()

        # Scene expansion markers: "### SCENE EXPANSION ###", "=== SCENE EXPANSION ==="
        content = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s*(?:EXPANSION|CONTINUATION|CONTENT|START|BEGIN)[^#=\-\*\n]*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()

        # Regenerated/Revised scene markers: "=== REGENERATED SCENE ===", "### REVISED SCENE ###"
        # Also handles typos like "REGNERATED" and makes "SCENE" word optional
        content = re.sub(r'^[#=\-\*]{2,}\s*(?:REGE?NERATED|REVISED|UPDATED|NEW|REWRITTEN)(?:\s+SCENE)?[^#=\-\*\n]*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()

        # Generic section markers at start: "### SCENE ###", "=== SCENE ==="
        content = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s*\d*\s*[#=\-\*]*\s*\n?', '', content, flags=re.IGNORECASE).strip()

        # "Continue scene" prefixes: "Continue scene:", "Continuing the scene:"
        content = re.sub(r'^(?:Continue|Continuing|Continued)\s+(?:the\s+)?scene[:\s]*\n?', '', content, flags=re.IGNORECASE).strip()

        # "Here is" prefixes: "Here is the scene:", "Here's the continuation:"
        content = re.sub(r'^Here(?:\'s|\s+is)\s+(?:the\s+)?(?:scene|continuation|next\s+part|story)[:\s]*\n?', '', content, flags=re.IGNORECASE).strip()

        # Instruction acknowledgments: "Understood, here's the scene:", "Got it. Here's the scene:"
        content = re.sub(r'^(?:Understood|Got\s+it|Okay|Sure|Certainly)[.,!]?\s*(?:Here(?:\'s|\s+is)[^:]*:)?\s*\n?', '', content, flags=re.IGNORECASE).strip()

        # Chapter/Part markers at start: "Chapter 7:", "Part 3:"
        content = re.sub(r'^(?:Chapter|Part)\s+\d+[:\s].*?(\n|$)', '', content, flags=re.IGNORECASE).strip()

        # === INSTRUCTION TAGS (can appear anywhere) ===

        # Llama-style instruction tags: [/inst], [inst], <<SYS>>, <</SYS>>
        content = re.sub(r'\[/?inst\]', '', content, flags=re.IGNORECASE)
        content = re.sub(r'<<?/?SYS>>?', '', content, flags=re.IGNORECASE)

        # Assistant/User role markers that leak through
        content = re.sub(r'^(?:Assistant|AI|Model):\s*', '', content, flags=re.IGNORECASE | re.MULTILINE).strip()

        # === TRAILING JUNK PATTERNS ===

        # "End of scene" markers: "--- End of Scene ---", "=== END ==="
        content = re.sub(r'\n?[#=\-\*]{2,}\s*(?:END|FIN|THE\s+END)\s*(?:OF\s+SCENE)?[^#=\-\*\n]*[#=\-\*]*\s*$', '', content, flags=re.IGNORECASE).strip()

        # "To be continued" markers
        content = re.sub(r'\n?\s*(?:\[|\()?(?:To\s+be\s+continued|TBC|Continued\s+in\s+next\s+scene)(?:\]|\))?\s*\.?\s*$', '', content, flags=re.IGNORECASE).strip()

        # Word count annotations: "(Word count: 150)", "[~200 words]"
        content = re.sub(r'\n?\s*(?:\[|\()?\s*(?:~?\s*\d+\s*words?|word\s*count[:\s]*\d+)\s*(?:\]|\))?\s*$', '', content, flags=re.IGNORECASE).strip()

        # === CHOICES MARKER CLEANUP (at end of content) ===
        # Remove CHOICES [...] format that LLMs sometimes output instead of ###CHOICES###
        # Pattern: "CHOICES" followed by JSON array at end of content
        # Newline is optional (\n?) since LLM may output directly after text
        content = re.sub(r'\n?\s*CHOICES\s+\[.*\]\s*$', '', content, flags=re.IGNORECASE | re.DOTALL).strip()
        # Also remove ###CHOICES### marker and everything after it
        content = re.sub(r'\n?\s*###\s*CHOICES\s*###.*$', '', content, flags=re.IGNORECASE | re.DOTALL).strip()

        # === EMBEDDED METADATA (anywhere in content) ===

        # Scene numbers embedded: "### Scene 113 ###" in middle of text
        content = re.sub(r'\n[#=\-\*]{2,}\s*SCENE\s+\d+\s*[#=\-\*]*\s*\n', '\n', content, flags=re.IGNORECASE)

        # Remove multiple consecutive blank lines (normalize to max 2)
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Check if any changes were made this pass
        if content == old_content:
            logger.debug(f"[SCENE_CLEAN] Cleaning converged after {pass_num + 1} pass(es)")
            break

    # Log if significant cleaning occurred
    if len(original_content) - len(content) > 10:
        removed_preview = original_content[:150].replace('\n', '\\n')
        logger.info(f"[SCENE_CLEAN] Removed {len(original_content) - len(content)} chars. Preview: {removed_preview}")

    return content.strip()


def clean_scene_numbers(content: str) -> str:
    """
    Remove scene numbers and LLM junk from generated content.
    This is an alias for clean_scene_content for backward compatibility.
    """
    return clean_scene_content(content)


def clean_instruction_tags(content: str) -> str:
    """Remove instruction tags like [/inst][inst] that may appear in LLM responses"""
    # Remove [/inst] and [inst] tags (with or without closing brackets)
    content = re.sub(r'\[/inst\]\s*\[inst\]', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\[/inst\]', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\[inst\]', '', content, flags=re.IGNORECASE)
    return content.strip()


def clean_scene_numbers_from_summary(summary: str) -> str:
    """
    Remove scene numbers and markers from chapter summaries.

    The LLM generates summaries with scene markers like:
    - **SCENE 248**
    - **SCENES 249-250**
    - ### SCENE 5 ###
    - Scene 10:

    These teach the LLM to generate scene numbers, so we strip them.
    """
    if not summary:
        return summary

    # Remove bold scene markers: **SCENE 248**, **SCENES 249-250**
    summary = re.sub(r'\*\*SCENES?\s+\d+(?:-\d+)?\*\*\s*\n?', '', summary, flags=re.IGNORECASE)

    # Remove markdown scene headers: ### SCENE 5 ###, ## Scene 10 ##
    summary = re.sub(r'^#{1,6}\s*SCENES?\s+\d+(?:-\d+)?[^#\n]*#{0,6}\s*\n?', '', summary, flags=re.MULTILINE | re.IGNORECASE)

    # Remove plain scene markers: Scene 10:, SCENE 5 -
    summary = re.sub(r'^SCENES?\s+\d+(?:-\d+)?\s*[:\-]?\s*\n?', '', summary, flags=re.MULTILINE | re.IGNORECASE)

    # Remove horizontal rules that separate scene sections: ---, ===, ***
    summary = re.sub(r'^\s*[-=*]{3,}\s*$\n?', '', summary, flags=re.MULTILINE)

    # Normalize multiple blank lines to single
    summary = re.sub(r'\n{3,}', '\n\n', summary)

    return summary.strip()


def clean_scene_numbers_chunk(chunk: str, chars_processed: int = 0) -> str:
    """
    Clean scene numbers and junk from streaming chunks.
    Position-aware: aggressive cleaning only at start of response.

    Args:
        chunk: The chunk to clean
        chars_processed: Total characters processed so far (for position awareness)
    """
    if not chunk:
        return chunk

    stripped = chunk.strip()

    # Strip inline thinking tags (e.g. <think>...</think>) within a single chunk
    if '<think' in chunk.lower() or '<reasoning' in chunk.lower() or '<reflection' in chunk.lower():
        chunk = ThinkingTagParser.strip_thinking_tags(chunk, preserve_whitespace=True)
        if not chunk.strip():
            return ''
        stripped = chunk.strip()

    # === POSITION-AWARE MARKDOWN HEADER REMOVAL ===
    # Only apply aggressive ## removal in first ~200 chars (where SCENE junk appears)
    # After that, allow ## patterns through (for ###CHOICES### marker)
    HEADER_REMOVAL_THRESHOLD = 200  # Only strip ## headers in first 200 chars

    if stripped.startswith(('##', '==', '--', '**')):
        if chars_processed < HEADER_REMOVAL_THRESHOLD:
            # Early in response - this is likely SCENE junk, strip it
            return ''
        else:
            # Later in response - could be CHOICES marker, preserve it
            pass  # Fall through to return chunk

    # Check for "START OF SCENE" and similar patterns early in response
    # These patterns might appear in chunks that don't start with ##
    # (e.g., when "############\nSTART OF SCENE\n############" is split across chunks)
    if chars_processed < HEADER_REMOVAL_THRESHOLD:
        if re.search(r'^(?:#+\s*)?START\s+OF\s+SCENE\s*(?:#+)?$', stripped, re.IGNORECASE):
            return ''
        if re.search(r'^(?:#+\s*)?(?:BEGIN|BEGINNING)\s+(?:OF\s+)?SCENE\s*(?:#+)?$', stripped, re.IGNORECASE):
            return ''
        # "WHAT HAPPENS NEXT" instruction echo
        if re.search(r'^(?:#+\s*)?WHAT\s+HAPPENS\s+NEXT\s*(?:#+)?$', stripped, re.IGNORECASE):
            return ''

    # Markdown scene headers with numbers: "### SCENE 113 ###" (most specific first)
    if stripped.startswith('#'):
        if re.match(r'^#{1,6}\s*SCENE\s+\d+', stripped, re.IGNORECASE):
            cleaned = re.sub(r'^#{1,6}\s*SCENE\s+\d+\s*#{1,6}\s*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned
        if re.match(r'^#{1,6}\s*Scene\s+\d+', stripped, re.IGNORECASE):
            cleaned = re.sub(r'^#{1,6}\s*Scene\s+\d+[^#\n]*#{0,6}\s*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned

    # Scene number patterns at start of chunk: "Scene 123:", "SCENE 42"
    if stripped.startswith(('Scene ', 'SCENE ', 'scene ')):
        if re.match(r'^Scene\s+\d+[:\-\s]', chunk, re.IGNORECASE):
            cleaned = re.sub(r'^Scene\s+\d+[:\-\s]*[^\n]*\n?', '', chunk, flags=re.IGNORECASE)
            return cleaned

    # Scene response markers: "=== SCENE RESPONSE ==="
    if 'SCENE RESPONSE' in stripped.upper():
        cleaned = re.sub(r'^[#=\-\*]{2,}\s*SCENE\s+RESPONSE\s*[#=\-\*]*\s*\n?', '', chunk, flags=re.IGNORECASE)
        return cleaned

    # Scene expansion markers and regenerated variants
    if any(marker in stripped.upper() for marker in ['SCENE EXPANSION', 'SCENE CONTINUATION', 'REGENERATED SCENE', 'REGNERATED SCENE', 'REVISED SCENE']):
        cleaned = re.sub(r'^[#=\-\*]{2,}\s*(?:REGE?NERATED|REVISED|SCENE)\s*(?:EXPANSION|CONTINUATION)?[^#=\-\*\n]*[#=\-\*]*\s*\n?', '', chunk, flags=re.IGNORECASE)
        return cleaned

    # "Continue scene" prefix
    if stripped.lower().startswith(('continue scene', 'continuing the scene', 'continued scene')):
        cleaned = re.sub(r'^(?:Continue|Continuing|Continued)\s+(?:the\s+)?scene[:\s]*\n?', '', chunk, flags=re.IGNORECASE)
        return cleaned

    # "Here is" prefix
    if stripped.lower().startswith(("here's the scene", "here is the scene", "here's the continuation")):
        cleaned = re.sub(r'^Here(?:\'s|\s+is)\s+(?:the\s+)?(?:scene|continuation)[:\s]*\n?', '', chunk, flags=re.IGNORECASE)
        return cleaned

    return chunk
