"""
TTS Text Splitter for Roleplay

Parses AI roleplay responses into per-character segments so each
character's dialogue can be voiced with a different TTS voice.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """A segment of text attributed to a specific character or narration."""
    character_name: Optional[str]  # None for narration
    text: str
    is_narration: bool = False


@dataclass
class VoicedSegment:
    """A segment mapped to a specific TTS voice."""
    character_name: Optional[str]
    text: str
    voice_id: str
    speed: float = 1.0
    is_narration: bool = False


def split_by_speaker(
    text: str,
    character_names: list[str],
) -> list[SpeakerSegment]:
    """
    Parse roleplay AI response into per-character segments.

    Handles two patterns:
    1. **Character Name** headers (markdown bold at line start)
    2. Character Name: prefix (colon-delimited at line start)

    Text not attributed to any character is marked as narration.

    Args:
        text: The AI-generated roleplay response
        character_names: List of known character names

    Returns:
        List of SpeakerSegment in order of appearance
    """
    if not text or not text.strip():
        return []

    if not character_names:
        return [SpeakerSegment(character_name=None, text=text.strip(), is_narration=True)]

    # Escape names for regex, sort longest first to avoid partial matches
    sorted_names = sorted(character_names, key=len, reverse=True)
    escaped = [re.escape(n) for n in sorted_names]
    name_alt = "|".join(escaped)

    # Match **Name** or Name: at the start of a line
    # Group 1: name from **Name**, Group 2: name from Name:
    pattern = re.compile(
        rf"^(?:\*\*({name_alt})\*\*|({name_alt})\s*:)\s*",
        re.MULTILINE | re.IGNORECASE,
    )

    segments: list[SpeakerSegment] = []
    last_end = 0
    current_speaker: Optional[str] = None

    for match in pattern.finditer(text):
        # Text before this header
        before = text[last_end:match.start()].strip()
        if before:
            if current_speaker:
                segments.append(SpeakerSegment(
                    character_name=current_speaker,
                    text=before,
                ))
            else:
                segments.append(SpeakerSegment(
                    character_name=None,
                    text=before,
                    is_narration=True,
                ))

        # Determine which name matched
        current_speaker = match.group(1) or match.group(2)
        # Normalize to canonical name (case-insensitive match)
        for name in character_names:
            if name.lower() == current_speaker.lower():
                current_speaker = name
                break

        last_end = match.end()

    # Remaining text after last header
    remaining = text[last_end:].strip()
    if remaining:
        if current_speaker:
            segments.append(SpeakerSegment(
                character_name=current_speaker,
                text=remaining,
            ))
        else:
            segments.append(SpeakerSegment(
                character_name=None,
                text=remaining,
                is_narration=True,
            ))

    # If no headers found at all, treat entire text as single character or narration
    if not segments:
        # If only one AI character, attribute to them
        if len(character_names) == 1:
            return [SpeakerSegment(
                character_name=character_names[0],
                text=text.strip(),
            )]
        return [SpeakerSegment(character_name=None, text=text.strip(), is_narration=True)]

    return segments


def map_voices(
    segments: list[SpeakerSegment],
    voice_mapping: dict[str, dict],
    default_voice_id: str = "default",
    default_speed: float = 1.0,
) -> list[VoicedSegment]:
    """
    Map speaker segments to TTS voice configurations.

    Args:
        segments: Output of split_by_speaker()
        voice_mapping: Dict of character_name -> {voice_id, speed}
            Example: {"Jack": {"voice_id": "alloy", "speed": 1.0}}
        default_voice_id: Fallback voice for narration and unmapped characters
        default_speed: Fallback speed

    Returns:
        List of VoicedSegment ready for TTS generation
    """
    voiced: list[VoicedSegment] = []

    for seg in segments:
        if seg.is_narration or seg.character_name is None:
            voiced.append(VoicedSegment(
                character_name=None,
                text=seg.text,
                voice_id=voice_mapping.get("__narrator__", {}).get("voice_id", default_voice_id),
                speed=voice_mapping.get("__narrator__", {}).get("speed", default_speed),
                is_narration=True,
            ))
        else:
            char_config = voice_mapping.get(seg.character_name, {})
            voiced.append(VoicedSegment(
                character_name=seg.character_name,
                text=seg.text,
                voice_id=char_config.get("voice_id", default_voice_id),
                speed=char_config.get("speed", default_speed),
                is_narration=False,
            ))

    return voiced
