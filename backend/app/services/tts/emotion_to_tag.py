"""Map LLM-generated emotion phrases to provider-specific inline TTS tags.

A few TTS providers — Bark, Orpheus, Chatterbox Turbo, CosyVoice 2 —
encode emotion / paralinguistics by inline markup tokens (`[laugh]`,
`<sigh>`, `[whispering]`, `[angry]`, etc.). Tag vocabularies and
bracket conventions differ wildly between providers, so a `"soft
whisper, breathless"` phrase that the LLM extractor produced has to
map differently per provider.

This module provides the shared half:
  1. A canonical INTENT vocabulary (whisper / shout / laugh / sigh /
     angry / sad / etc.) — provider-agnostic
  2. `detect_intents(phrase)` — substring-matches the phrase against
     trigger words and returns the set of intents present
  3. `select_tag(phrase, tag_table)` — picks the highest-priority tag
     whose intent appears in the phrase, given a provider-specific
     `{intent: tag_string}` table

The PROVIDER half is a small dict per provider that maps intents to
that provider's actual tag strings. Adding a new inline-tag provider
is then ~5 lines:

    PROVIDER_TAGS = {
        "whisper": "[whispering]",
        "laugh": "[laugh]",
        ...
    }

    # in _build_payload:
    from ..emotion_to_tag import select_tag
    tag = select_tag(per_req.get("instructions"), PROVIDER_TAGS)
    text = f"{tag} {request.text}".strip() if tag else request.text

The intent vocabulary is intentionally narrow (~20 intents). Anything
beyond what the model can actually deliver as a paralinguistic tag is
better expressed through the spoken text itself, not a tag.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set


# Canonical intent set. Each intent is a short stable identifier; the
# tuple of triggers is the lowercase substrings we look for in the
# emotion phrase (substring match — `"hushed whisper"` matches both
# `whisper` and `intimate`). Order within INTENT_TRIGGERS doesn't matter
# for detection — priority is set per-provider via the tag_table order
# passed to `select_tag`.
INTENT_TRIGGERS: Dict[str, Iterable[str]] = {
    # Paralinguistic (non-verbal sounds you can actually inject as a tag)
    "whisper":   ("whisper", "hushed", "muted", "low murmur", "breathy"),
    "shout":     ("shout", "yell", "scream", "bellow", "roar", "raised voice"),
    "laugh":     ("laugh", "chuckle", "giggle", "snicker", "amused"),
    "sigh":      ("sigh", "exhale"),
    "gasp":      ("gasp", "sharp inhale"),
    "groan":     ("groan", "moan"),
    "cough":     ("cough", "throat clear", "clear throat"),
    "sob":       ("sob", "weep", "crying"),
    "yawn":      ("yawn", "sleepy"),
    "sniffle":   ("sniff", "sniffle"),
    "stammer":   ("stammer", "stutter", "halting"),

    # Emotional / tonal (broader than a single sound)
    "angry":     ("angry", "furious", "rage", "harsh", "venomous", "snarl",
                  "growl", "irate"),
    "happy":     ("happy", "joy", "cheerful", "delighted", "warm smile"),
    "sad":       ("sad", "melancholy", "mournful", "weary", "broken",
                  "tearful", "heavy-hearted"),
    "fear":      ("fear", "afraid", "scared", "terrified", "panic",
                  "trembling"),
    "surprised": ("surprised", "shocked", "stunned", "astonished"),
    "sarcastic": ("sarcastic", "mocking", "snide", "sneering"),
    "dramatic":  ("dramatic", "theatrical", "intense"),
    "playful":   ("playful", "teasing", "flirty", "coy", "mischievous"),
    "intimate":  ("intimate", "soft", "tender", "low and warm"),
    "urgent":    ("urgent", "frantic", "desperate", "insistent"),
}


def detect_intents(phrase: Optional[str]) -> Set[str]:
    """Return all canonical intents whose triggers appear in `phrase`.

    Substring-based. `"breathless urgent"` returns `{"whisper", "urgent"}`
    because "breath" matches the whisper trigger and "urgent" matches
    the urgent trigger. Empty / None phrase → empty set.
    """
    if not phrase:
        return set()
    p = phrase.lower()
    out: Set[str] = set()
    for intent, triggers in INTENT_TRIGGERS.items():
        for trig in triggers:
            if trig in p:
                out.add(intent)
                break
    return out


def select_tag(phrase: Optional[str], tag_table: Dict[str, str]) -> str:
    """Pick the FIRST tag from `tag_table` whose intent is detected in
    `phrase`. Returns empty string when no detected intent has a tag.

    `tag_table` iteration order = priority. Put the most specific /
    most desired tags first (paralinguistic before broad emotional —
    `whisper` before `intimate` since both match "soft whisper").
    """
    intents = detect_intents(phrase)
    if not intents:
        return ""
    for intent, tag in tag_table.items():  # dict iteration = insertion order
        if intent in intents:
            return tag
    return ""


def select_all_tags(phrase: Optional[str], tag_table: Dict[str, str]) -> List[str]:
    """Return ALL tags whose intents are detected, in `tag_table` order.

    Useful when a provider tolerates multiple stacked tags per utterance
    (e.g. `[sigh][whispering] text`). Most providers do NOT — they
    interpret the first tag and ignore the rest, or worse, read them
    aloud as text. Use `select_tag` (singular) unless the provider
    docs explicitly say otherwise.
    """
    intents = detect_intents(phrase)
    return [tag for intent, tag in tag_table.items() if intent in intents]
