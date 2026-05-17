"""Build provider-specific multi-speaker scripts from extracted segments.

When a TTS provider supports multi-speaker scripts (VibeVoice, F5-TTS,
hypothetically others), this module converts the scene's ordered segment
list + per-story voice mapping into the single inline script the provider
expects, plus the slot→voice mapping the API call needs.

Architecture:

  - `assign_slots()` is shared across providers — assigns 0..N-1 by first
    appearance, coerces overflow to the narrator slot.
  - `ScriptFormat` is a per-provider config:
      * `line_template` — Python format string with `{slot}` and `{text}`
        placeholders. e.g. "Speaker {slot}: {text}" (VibeVoice) or
        "[{slot}] {text}" (F5-TTS).
      * `text_formatter` — callable `(text, kind) → str` that does any
        per-segment text munging (strip outer quotes/asterisks, wrap
        thoughts in parens, collapse whitespace, etc.).
      * `payload_builder` — callable `(slot_voice_pairs) → Any` that
        assembles the JSON-serializable speakers/voices structure the
        provider's API call requires.
      * `slot_namer` — optional callable `(slot_int, speaker_name) → str|int`
        for providers that key slots by name (F5's `[main]`/`[town]`)
        rather than by integer. Defaults to returning the integer.
  - `build_script(segments, voice_map, fmt)` is the generic builder.
  - `build_vibevoice_script(segments, voice_map)` is a thin alias for
    back-compat with the original VibeVoice-only API.

Adding a new multi-speaker provider:
  1. Define a `ScriptFormat` constant in your provider module
  2. Implement a `text_formatter` function (or reuse one from below)
  3. Call `build_script(segments, voice_map, MY_FORMAT)` from your
     `synthesize_multi_speaker_*` methods
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# Default narrator key — segments with kind="narrator" or no resolved speaker
# get coerced to this label so the slot assignment still works.
NARRATOR_KEY = "narrator"

_WHITESPACE_RUN = re.compile(r"\s+")

logger = logging.getLogger(__name__)


def _collapse_unmapped_to_narrator(
    segments: List[Dict[str, Any]], voice_map: Dict[str, str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Rewrite each segment whose speaker has no voice in `voice_map` so its
    speaker becomes `NARRATOR_KEY`.

    User intent: leaving a character on "default voice" in the UI means
    "use the narrator voice for that character." Without this collapse,
    the multi-speaker builder bails (returns None) and the dispatcher
    falls back to slow per-segment chunked generation — turning a single
    multi-speaker inference call into N sequential calls.

    Returns (new_segments, collapsed_speakers). The returned segments list
    is a fresh list; segments needing speaker rewrites are shallow-copied
    so the caller's data is not mutated. `collapsed_speakers` is the
    ordered list of distinct speaker names that were coerced, for logging.
    """
    out: List[Dict[str, Any]] = []
    collapsed: List[str] = []
    seen: set = set()
    for seg in segments:
        sp = (seg.get("speaker") or NARRATOR_KEY).strip() or NARRATOR_KEY
        if sp != NARRATOR_KEY and not (
            voice_map.get(sp.lower()) or voice_map.get(sp)
        ):
            if sp not in seen:
                collapsed.append(sp)
                seen.add(sp)
            seg = dict(seg)
            seg["speaker"] = NARRATOR_KEY
        out.append(seg)
    return out, collapsed


# ============================================================
# Slot assignment (shared across all formats)
# ============================================================

def assign_slots(
    segments: List[Dict[str, Any]], max_speakers: int
) -> Tuple[Dict[str, int], List[str]]:
    """Walk segments in order; assign slots 0..max_speakers-1 by first
    appearance. Speakers beyond the cap are coerced to the narrator slot
    so they still get audio (just in the narrator voice).

    Whitespace-only segments are skipped (integrity preservers).

    Returns:
        (slots, overflow):
          - slots: speaker → slot_index. Overflow speakers map to the
            narrator's slot (creating it if narrator hadn't appeared yet).
          - overflow: ordered list of speaker names that got collapsed —
            surfaced to the user so they know which characters to assign
            voices to (per-story voice picker UI).
    """
    slots: Dict[str, int] = {}
    overflow: List[str] = []
    for seg in segments:
        if not (seg.get("text") or "").strip():
            continue
        sp = (seg.get("speaker") or NARRATOR_KEY).strip() or NARRATOR_KEY
        if sp in slots:
            continue
        if len(slots) < max_speakers:
            slots[sp] = len(slots)
        else:
            # Cap reached — coerce this speaker to narrator's slot.
            # If narrator hasn't appeared yet (rare — scenes usually open
            # with narration), give it the next slot instead so we don't
            # lose the speaker entirely.
            if NARRATOR_KEY in slots:
                slots[sp] = slots[NARRATOR_KEY]
            else:
                slots[NARRATOR_KEY] = len(slots)
                slots[sp] = slots[NARRATOR_KEY]
            overflow.append(sp)
    return slots, overflow


# ============================================================
# Text formatters (per-provider, but composable)
# ============================================================

def vibevoice_text_formatter(text: str, kind: str) -> str:
    """VibeVoice: strip dialogue outer quotes, wrap thoughts in parens,
    drop stray asterisks in narration, collapse internal whitespace.

    Multi-line text inside one `Speaker N:` line confuses VibeVoice — the
    paragraph breaks get interpreted as turn boundaries and the model
    "forgets" which speaker is active, causing voice bleed across the
    seam (e.g. one character's tone continuing into the next narrator
    chunk). Hence the whitespace collapse.
    """
    text = text.strip()
    if kind == "dialogue":
        # Model would otherwise read `"quote..."` literally as the word "quote".
        text = text.strip('"').strip()
    elif kind == "thought":
        # Wrap in parens — community workaround since VibeVoice has no
        # native emotion API; the parens cue the model to read softer.
        text = text.strip("*").strip()
        text = f"({text})"
    else:  # narrator
        text = text.replace("*", "")  # strip orphan asterisks
    return _WHITESPACE_RUN.sub(" ", text).strip()


def passthrough_text_formatter(text: str, kind: str) -> str:
    """Minimal cleanup: strip whitespace, strip outer quote/asterisk
    markup so providers don't read them aloud. No paren-wrapping, no
    asterisk-stripping in narrator (no orphan-asterisk concern when
    spans came from regex extraction).

    Useful default for providers that don't need any special text shaping
    beyond not pronouncing the markup characters.
    """
    text = text.strip()
    if kind == "dialogue":
        text = text.strip('"').strip()
        # Smart quotes too
        text = text.strip("“”").strip()
    elif kind == "thought":
        text = text.strip("*").strip()
    return _WHITESPACE_RUN.sub(" ", text).strip()


# ============================================================
# Payload builders (per-provider)
# ============================================================

def vibevoice_payload_builder(
    slot_voice_pairs: List[Tuple[int, str]]
) -> List[Dict[str, Any]]:
    """VibeVoice native multi-speaker shape:
        [{"speaker_id": 0, "voice_preset": "..."}, ...]
    """
    return [
        {"speaker_id": slot, "voice_preset": voice}
        for slot, voice in slot_voice_pairs
    ]


# ============================================================
# ScriptFormat config
# ============================================================

@dataclass(frozen=True)
class ScriptFormat:
    """Per-provider configuration for multi-speaker script generation.

    Most providers fit one of two shapes:
      - Numeric slots: `Speaker 0: ...` (VibeVoice). slot_namer left None.
      - Named slots: `[main] ...` (F5-TTS). slot_namer returns a string
        derived from the speaker's canonical name.
    """
    name: str
    line_template: str
    text_formatter: Callable[[str, str], str]
    payload_builder: Callable[[List[Tuple[int, str]]], Any]
    # If set, this transforms (slot_int, canonical_speaker_name) into
    # the value substituted for `{slot}` in line_template. Default returns
    # slot_int directly (numeric-slot providers).
    slot_namer: Optional[Callable[[int, str], Any]] = None


# Built-in format definitions. New providers should DECLARE their own
# ScriptFormat in their provider module — these live here as canonical
# examples / defaults.

VIBEVOICE_FORMAT = ScriptFormat(
    name="vibevoice",
    line_template="Speaker {slot}: {text}",
    text_formatter=vibevoice_text_formatter,
    payload_builder=vibevoice_payload_builder,
    slot_namer=None,  # numeric slots
)


# ============================================================
# Generic script builder
# ============================================================

def build_script(
    segments: List[Dict[str, Any]],
    voice_map: Dict[str, str],
    fmt: ScriptFormat,
    max_speakers: int = 4,
) -> Optional[Tuple[str, Any, Dict[str, int], List[str]]]:
    """Build a multi-speaker script for ANY provider via its ScriptFormat.

    Args:
        segments: ordered list of `{kind, text, speaker}` dicts
            (from scene_segment_extraction_service v2).
        voice_map: lowercased speaker name → voice ID. The caller (TTS
            dispatcher) builds this from `Story.tts_character_voices`
            plus a default voice for narrator.
        fmt: provider-specific ScriptFormat config.
        max_speakers: hard cap on distinct slots for this provider.

    Returns:
        (script_text, payload, slot_map, overflow) on success, where:
            - script_text: assembled script per `fmt.line_template`
            - payload: provider-specific speakers/voices structure
              (whatever `fmt.payload_builder` returns)
            - slot_map: `{speaker_canonical_name: slot_int}` (overflow
              speakers share narrator's slot)
            - overflow: ordered list of speakers that exceeded the cap
              and got collapsed to narrator. UI should warn the user.
              Speakers that were intentionally left on "default voice"
              (i.e. no entry in `voice_map`) are silently coerced to the
              narrator voice and do NOT appear in `overflow`.
        OR None if:
            - no extractable segments
            - all formatted lines came out empty
    """
    # Collapse speakers with no voice mapping into narrator BEFORE slot
    # assignment, so the user's "use default voice" choice doesn't push
    # us into chunked fallback. Their lines will all share the narrator
    # slot (and thus the narrator voice).
    segments, default_collapsed = _collapse_unmapped_to_narrator(segments, voice_map)
    if default_collapsed:
        logger.info(
            f"[MULTI-SPEAKER] Coercing {len(default_collapsed)} speaker(s) without "
            f"a configured voice to narrator: {default_collapsed}"
        )

    slots, overflow = assign_slots(segments, max_speakers)
    if not slots:
        return None

    # Voice resolution. Only check the speakers that got their OWN slot —
    # overflow speakers will use the narrator's voice anyway, no need to
    # require a separate mapping for them. By this point, any speaker
    # without a voice mapping has already been coerced to narrator by
    # `_collapse_unmapped_to_narrator`, so every slot here is guaranteed
    # to have a voice — but we still skip on None as a defensive guard
    # in case `voice_map` is missing the narrator entry (caller bug).
    seen_slots: set = set()
    slot_voice_pairs: List[Tuple[int, str]] = []
    # Preserve slot-order iteration so payload_builder gets pairs in 0,1,2... order.
    for sp, slot in sorted(slots.items(), key=lambda kv: kv[1]):
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        voice = voice_map.get(sp.lower()) or voice_map.get(sp)
        if not voice:
            logger.warning(
                f"[MULTI-SPEAKER] No voice for speaker {sp!r} after collapse — "
                f"voice_map missing narrator? Aborting multi-speaker build."
            )
            return None
        slot_voice_pairs.append((slot, voice))

    payload = fmt.payload_builder(slot_voice_pairs)

    # Build the script lines.
    # For named-slot providers, we need a stable name per slot — derive
    # from the FIRST speaker that occupied each slot.
    slot_to_name: Dict[int, str] = {}
    for sp, slot in slots.items():
        slot_to_name.setdefault(slot, sp)

    lines: List[str] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        sp = (seg.get("speaker") or NARRATOR_KEY).strip() or NARRATOR_KEY
        slot = slots.get(sp, slots.get(NARRATOR_KEY, 0))
        formatted_text = fmt.text_formatter(text, seg.get("kind") or "narrator")
        if not formatted_text:
            continue
        slot_id = (
            fmt.slot_namer(slot, slot_to_name.get(slot, NARRATOR_KEY))
            if fmt.slot_namer is not None
            else slot
        )
        lines.append(fmt.line_template.format(slot=slot_id, text=formatted_text))

    if not lines:
        return None

    return "\n".join(lines), payload, slots, overflow


# ============================================================
# Back-compat alias
# ============================================================

def build_vibevoice_script(
    segments: List[Dict[str, Any]],
    voice_map: Dict[str, str],
    max_speakers: int = 4,
) -> Optional[Tuple[str, List[Dict[str, Any]], Dict[str, int], List[str]]]:
    """Thin alias kept for back-compat with the original VibeVoice-only API.

    New code should call `build_script(segments, voice_map, VIBEVOICE_FORMAT)`
    directly so the call site documents which format it's targeting.
    """
    return build_script(segments, voice_map, VIBEVOICE_FORMAT, max_speakers)
