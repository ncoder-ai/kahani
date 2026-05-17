"""
Turn Resolver for Group Roleplay

Determines which AI characters should respond to the user's input
based on turn mode (natural, round-robin, manual) and per-character
talkativeness settings.
"""

import random
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_active_characters(
    user_message: str,
    characters: list[dict],
    turn_mode: str = "natural",
    manual_selection: Optional[list[int]] = None,
    last_responder_idx: int = -1,
) -> tuple[list[dict], int]:
    """
    Determine which AI characters should respond this turn.

    Args:
        user_message: The user's input text (used for name-mention detection)
        characters: List of character dicts from context builder. Each has:
            story_character_id, name, talkativeness, is_player, is_active (if present)
        turn_mode: "natural" | "round_robin" | "manual"
        manual_selection: List of story_character_ids for manual mode
        last_responder_idx: Index of last responder in round-robin (stored in story_context)

    Returns:
        (active_characters, new_last_responder_idx)
        active_characters: Ordered list of character dicts that should respond
        new_last_responder_idx: Updated index for round-robin tracking
    """
    # Filter to AI characters only (not the player)
    ai_characters = [c for c in characters if not c.get("is_player", False)]
    if not ai_characters:
        return [], last_responder_idx

    if turn_mode == "manual":
        return _resolve_manual(ai_characters, manual_selection), last_responder_idx

    if turn_mode == "round_robin":
        active, new_idx = _resolve_round_robin(ai_characters, last_responder_idx)
        return active, new_idx

    # Default: natural mode
    return _resolve_natural(user_message, ai_characters), last_responder_idx


def resolve_auto_continue_characters(
    characters: list[dict],
    turn_mode: str = "natural",
    last_responder_idx: int = -1,
) -> tuple[list[dict], int]:
    """
    Resolve characters for auto-continue (no user message).
    Characters are selected purely by talkativeness probability.

    Returns:
        (active_characters, new_last_responder_idx)
    """
    ai_characters = [c for c in characters if not c.get("is_player", False)]
    if not ai_characters:
        return [], last_responder_idx

    if turn_mode == "round_robin":
        return _resolve_round_robin(ai_characters, last_responder_idx)

    # Natural mode without user message — purely talkativeness-based
    active = []
    for char in ai_characters:
        talk = char.get("talkativeness", 0.5)
        if random.random() < talk:
            active.append(char)

    # Guarantee at least one character speaks
    if not active:
        active = [max(ai_characters, key=lambda c: c.get("talkativeness", 0.5))]

    # Order by talkativeness descending (most talkative first)
    active.sort(key=lambda c: c.get("talkativeness", 0.5), reverse=True)
    return active, last_responder_idx


def _resolve_natural(user_message: str, ai_characters: list[dict]) -> list[dict]:
    """
    Natural turn mode: name-mention + talkativeness probability.

    1. Characters mentioned by name → always active
    2. Unmentioned characters → active if random() < talkativeness
    3. If nobody active → pick the highest-talkativeness character
    4. Sort: mentioned first (by mention position), then by talkativeness desc
    """
    msg_lower = user_message.lower()
    mentioned = []
    unmentioned_active = []

    for char in ai_characters:
        name = char.get("name", "")
        name_lower = name.lower()

        # Check if character is mentioned in the message
        # Match full name or first name (for multi-word names like "Robert Miller")
        is_mentioned = False
        mention_pos = len(user_message)  # Default: end (for sorting)

        # Check full name
        pos = msg_lower.find(name_lower)
        if pos >= 0:
            is_mentioned = True
            mention_pos = pos
        else:
            # Check first name only (if multi-word)
            first_name = name.split()[0].lower() if name else ""
            if first_name and len(first_name) >= 3:
                # Use word boundary matching to avoid false positives
                pattern = r'\b' + re.escape(first_name) + r'\b'
                match = re.search(pattern, msg_lower)
                if match:
                    is_mentioned = True
                    mention_pos = match.start()

        if is_mentioned:
            mentioned.append((mention_pos, char))
        else:
            # Talkativeness roll
            talk = char.get("talkativeness", 0.5)
            if random.random() < talk:
                unmentioned_active.append(char)

    # Sort mentioned by position in message (earliest mention first)
    mentioned.sort(key=lambda x: x[0])
    mentioned_chars = [c for _, c in mentioned]

    # Combine: mentioned first, then unmentioned active sorted by talkativeness
    unmentioned_active.sort(key=lambda c: c.get("talkativeness", 0.5), reverse=True)
    active = mentioned_chars + unmentioned_active

    # Guarantee at least one character
    if not active:
        active = [max(ai_characters, key=lambda c: c.get("talkativeness", 0.5))]

    return active


def _resolve_round_robin(
    ai_characters: list[dict],
    last_idx: int,
) -> tuple[list[dict], int]:
    """
    Round-robin: cycle through characters in roster order.
    Returns the next character and updated index.
    """
    if not ai_characters:
        return [], last_idx

    next_idx = (last_idx + 1) % len(ai_characters)
    return [ai_characters[next_idx]], next_idx


def _resolve_manual(
    ai_characters: list[dict],
    selection: Optional[list[int]],
) -> list[dict]:
    """
    Manual mode: return only the explicitly selected characters.
    Falls back to all AI characters if selection is empty/None.
    """
    if not selection:
        return ai_characters

    selected_ids = set(selection)
    active = [c for c in ai_characters if c.get("story_character_id") in selected_ids]

    if not active:
        logger.warning(f"Manual selection {selection} matched no AI characters, falling back to all")
        return ai_characters

    return active
