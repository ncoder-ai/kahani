"""Deterministic-spans + targeted-LLM-polish scene segment extractor.

This is the v2 pipeline that replaces the single-pass Ministral extraction
in `scene_segment_extraction_service.extract_scene_segments`. The old
flow asked the LLM to do BOTH verbatim text splitting AND semantic
classification in one call — which produced ~50% of the scene dropped,
hallucinated text, and wrong attributions in production.

This pipeline splits responsibilities:

  Stage 1 (code, deterministic, ~1ms):
    - Regex-extract dialogue spans ("...", curly + straight) and inner
      thought spans (*...*) from the source — 100% verbatim integrity
      guaranteed by construction.
    - Build narrator/dialogue/thought segments covering every character
      of the source. Whitespace-only narrator gaps (e.g. \\n\\n between
      back-to-back dialogues) are preserved so concat reconstructs
      exactly; the multi-speaker formatter strips them out at TTS time.
    - Detect tag-name speakers ("Mira said") and pronoun-tag speakers
      ("she said", resolved via gender_map).
    - Detect emotion from verb cues ("whispered", "breathed", etc.) and
      adverb modifiers ("said urgently").
    - Score POV character from internal-state + perception verbs.
    - Infer per-cast gender from sentence-bounded pronoun proximity,
      with 2-character-scene complement-by-elimination fallback.

  Stage 2 (LLM, single call, ~3-12s):
    - Send full scene + numbered list of dialogue/thought items + code's
      hints (speaker + emotion guesses where available).
    - LLM treats hints as starting points and overrides where scene
      context disagrees. Returns indexed verdicts + scene_mood for
      narrator default.

  Stage 3 (code merge, <10ms):
    - Apply LLM verdicts (preferred) to segments.
    - Apply scene_mood to all narrator segments without an emotion.
    - Fall back to code verdicts where LLM omitted.

Returns the same shape as the old service: List[{speaker, text, emotion}].
On any failure, returns a single-narrator fallback covering the whole
scene — never silently truncates content.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# Regex patterns
# ============================================================

# Dialogue spans — straight + smart double quotes. Single quotes are
# excluded (too easy to false-positive on apostrophes like `don't`).
RE_DIALOGUE = re.compile(
    r'("[^"]+?")'
    r'|'
    r'(“[^”]*?”)'  # smart double: " ... "
)

# Inner thought spans — text wrapped in single asterisks. Any non-empty
# match counts (single-word thoughts like *Harder,* are valid; the old
# filter that required >=2 words OR sentence-ending punctuation
# swallowed legitimate gesture/thought tags).
RE_THOUGHT = re.compile(r'\*([^*\n]+)\*')

# Tag verbs grouped by the style hint they imply. Used both for emotion
# extraction AND to know "this verb is a SAID verb so the surrounding
# subject is the speaker of the adjacent dialogue."
VERB_STYLE = {
    "whisper":   ["whispered", "whispers", "whispering", "murmured", "murmuring",
                  "muttered", "mouthed", "hissed", "hissing"],
    "shout":     ["shouted", "shouting", "yelled", "yelling", "screamed",
                  "screaming", "cried", "called", "bellowed", "roared"],
    "sigh":      ["sighed", "sighing", "exhaled"],
    "breathy":   ["breathed", "breathing", "panted", "panting", "gasped", "gasping"],
    "low growl": ["growled", "snarled", "rumbled"],
    "urgent":    ["urged", "urging", "begged", "begging", "pleaded", "pleading",
                  "demanded", "demanding"],
    "mumbled":   ["mumbled", "mumbling", "stammered", "stuttered"],
    "amused":    ["laughed", "chuckled", "giggled", "snickered"],
    "soft":      ["purred", "cooed", "soothed"],
    "trembling": ["trembled", "wavered", "quavered", "faltered"],
    "sneering":  ["sneered", "scoffed", "smirked"],
    "weary":     ["groaned", "moaned"],
    # "grunt" is a common speech tag in coarse fiction
    # ("Harder," he grunted) — keep it discoverable as a tag verb.
    "grunt":     ["grunted", "grunting"],
    "level":     ["replied", "responded", "answered", "stated", "remarked",
                  "added", "noted", "said", "says", "asked", "asks", "told"],
}
VERB_TO_STYLE = {v: style for style, verbs in VERB_STYLE.items() for v in verbs}
ALL_VERBS = sorted(VERB_TO_STYLE.keys(), key=len, reverse=True)
VERB_PATTERN = re.compile(r"\b(" + "|".join(ALL_VERBS) + r")\b", re.IGNORECASE)

ADVERB_PATTERN = re.compile(
    r"\b(angrily|softly|quietly|loudly|urgently|harshly|gently|slowly|quickly|"
    r"sharply|sweetly|coldly|warmly|hoarsely|breathlessly|sleepily|dryly|"
    r"flatly|firmly|tenderly|coyly|playfully|nervously|bitterly|wearily|"
    r"sarcastically|teasingly|mockingly|gravely|earnestly|hopefully)\b",
    re.IGNORECASE,
)

# Internal-state and perception verbs used for POV detection. Includes
# both purely-internal (felt/thought/wondered) AND perception verbs
# (watched/saw/looked) — the latter strongly indicate whose POV the
# scene is filmed from.
POV_VERBS = re.compile(
    r"\b(felt|feels|thought|thinks|wondered|wonders|realized|realizes|knew|"
    r"knows|noticed|notices|remembered|remembers|imagined|imagines|"
    r"understood|understands|sensed|senses|"
    r"watched|watches|saw|sees|looked|looks|observed|observes|"
    r"glanced|glances|listened|listens|heard|hears|spotted|spots)\b",
    re.IGNORECASE,
)

POSSESSIVE_SENSATION = re.compile(r"\b(her|his|their)\s+(\w+)\b", re.IGNORECASE)
PROXIMITY_PRONOUN = re.compile(
    r"\b(he|she|him|her|his|hers|himself|herself|they|them|their|themselves)\b",
    re.IGNORECASE,
)
PRONOUN_GENDER = {
    "he": "m", "him": "m", "his": "m", "himself": "m",
    "she": "f", "her": "f", "hers": "f", "herself": "f",
    "they": "n", "them": "n", "their": "n", "themselves": "n",
}
SENTENCE_BOUNDARY = re.compile(r'[.!?](?:\s|$)|\n\n')
WORD = re.compile(r"\w[\w'-]*")

# Bare third-person `she said` style tag — used for pronoun-based speaker
# attribution after dialogue. Reuses the verb vocabulary above.
BARE_PRONOUN_TAG = re.compile(
    r"\b(he|she|they)\s+(?:" + "|".join(ALL_VERBS) + r")\b",
    re.IGNORECASE,
)


# ============================================================
# Data shapes
# ============================================================

@dataclass
class _Span:
    kind: str  # 'dialogue' | 'thought'
    start: int
    end: int
    text: str  # full match including delimiters


@dataclass
class _Segment:
    kind: str  # 'narrator' | 'dialogue' | 'thought'
    text: str
    speaker: Optional[str] = None
    emotion: Optional[str] = None
    speaker_source: Optional[str] = None
    emotion_source: Optional[str] = None


# ============================================================
# Stage 1: code-only extraction
# ============================================================

def _name_index(cast: List[str]) -> Dict[str, str]:
    """Lowercased lookup: full / first / last name → canonical full name.
    Drops first-or-last-name aliases that collide between two cast members."""
    idx: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    canon: List[str] = []
    for name in cast:
        n = (name or "").strip()
        if not n or n.lower() in {x.lower() for x in canon}:
            continue
        canon.append(n)
        idx[n.lower()] = n
        toks = n.split()
        if len(toks) >= 2:
            for v in (toks[0], toks[-1]):
                k = v.lower()
                if k == n.lower():
                    continue
                counts[k] = counts.get(k, 0) + 1
                if k not in idx:
                    idx[k] = n
    for alias, c in counts.items():
        if c > 1 and alias in idx and idx[alias].lower() != alias:
            del idx[alias]
    return idx


def _find_spans(scene: str) -> List[_Span]:
    spans: List[_Span] = []
    for m in RE_DIALOGUE.finditer(scene):
        spans.append(_Span("dialogue", m.start(), m.end(), m.group(0)))
    for m in RE_THOUGHT.finditer(scene):
        if m.group(1).strip():
            spans.append(_Span("thought", m.start(), m.end(), m.group(0)))
    spans.sort(key=lambda s: s.start)
    cleaned: List[_Span] = []
    for s in spans:
        # Drop overlapping spans (e.g. a thought regex matching inside a quote)
        if cleaned and s.start < cleaned[-1].end:
            continue
        cleaned.append(s)
    return cleaned


def _build_segments(scene: str, spans: List[_Span]) -> List[_Segment]:
    """Emit segments covering EVERY character of `scene` for 100% concat
    integrity. Whitespace-only narrator gaps are kept as-is — TTS dispatch
    skips them later."""
    out: List[_Segment] = []
    cursor = 0
    for sp in spans:
        if sp.start > cursor:
            out.append(_Segment("narrator", scene[cursor:sp.start]))
        out.append(_Segment(sp.kind, sp.text))
        cursor = sp.end
    if cursor < len(scene):
        out.append(_Segment("narrator", scene[cursor:]))
    return out


def _infer_gender_map(scene: str, name_idx: Dict[str, str]) -> Dict[str, str]:
    """Bounded sentence-window gender inference + 2-char complement fix."""
    canon = set(name_idx.values())
    counts: Dict[str, Dict[str, int]] = {n: {"m": 0, "f": 0, "n": 0} for n in canon}
    boundaries = [0] + [m.end() for m in SENTENCE_BOUNDARY.finditer(scene)] + [len(scene)]
    for m in WORD.finditer(scene):
        full = name_idx.get(m.group(0).lower())
        if not full:
            continue
        i_start = next(b for b in reversed(boundaries) if b <= m.start())
        try:
            i_end_idx = next(i for i, b in enumerate(boundaries) if b > m.end())
            i_end = boundaries[min(i_end_idx + 1, len(boundaries) - 1)]
        except StopIteration:
            i_end = len(scene)
        region = scene[i_start:i_end]
        for pm in PROXIMITY_PRONOUN.finditer(region):
            g = PRONOUN_GENDER[pm.group(0).lower()]
            if g != "n":
                counts[full][g] += 1
    out: Dict[str, str] = {}
    for name, c in counts.items():
        ranked = sorted(c.items(), key=lambda kv: kv[1], reverse=True)
        if ranked[0][1] == 0:
            out[name] = "n"
        elif len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            out[name] = "n"
        else:
            out[name] = ranked[0][0]
    # 2-character complement: most intimate fiction has exactly 2 cast
    # members of opposite genders. If both inferred the same OR one
    # gendered + one unknown, flip the weaker / unknown one.
    if len(out) == 2:
        m_count = len(re.findall(r"\b(he|his|him|himself)\b", scene, re.IGNORECASE))
        f_count = len(re.findall(r"\b(she|her|hers|herself)\b", scene, re.IGNORECASE))
        names = list(out.keys())
        g0, g1 = out[names[0]], out[names[1]]
        c0 = max(counts[names[0]].values())
        c1 = max(counts[names[1]].values())
        if g0 == g1 and g0 != "n":
            opposite = "f" if g0 == "m" else "m"
            opposite_used = (m_count if opposite == "m" else f_count) > 0
            if opposite_used:
                weaker = names[0] if c0 < c1 else names[1]
                out[weaker] = opposite
        else:
            for nm in names:
                if out[nm] == "n":
                    other_g = out[next(x for x in names if x != nm)]
                    if other_g != "n":
                        opposite = "f" if other_g == "m" else "m"
                        if (m_count if opposite == "m" else f_count) > 0:
                            out[nm] = opposite
    return out


def _score_pov(scene: str, name_idx: Dict[str, str],
               gender_map: Dict[str, str]
               ) -> Tuple[Optional[str], Dict[str, int]]:
    scores: Dict[str, int] = {n: 0 for n in set(name_idx.values())}
    if not scores:
        return None, scores
    name_positions: List[Tuple[int, str]] = []
    for m in WORD.finditer(scene):
        full = name_idx.get(m.group(0).lower())
        if full:
            name_positions.append((m.start(), full))

    def nearest_preceding(pos: int) -> Optional[str]:
        last = None
        for p, n in name_positions:
            if p >= pos:
                break
            last = n
        return last

    PRONOUN_BEFORE = re.compile(r"\b(he|she|they)\s*$", re.IGNORECASE)
    # Only trust gender-based pronoun resolution for 2-character scenes,
    # where complement-by-elimination keeps gender_map accurate. For 3+
    # cast, gender inference often mis-tags male characters as female
    # (their names appear next to "her/she" pronouns describing the POV
    # woman's actions on them) — falling back to nearest preceding name
    # is more reliable in those cases.
    use_gender_resolution = len(scores) <= 2
    for m in POV_VERBS.finditer(scene):
        before = scene[max(0, m.start() - 30): m.start()]
        pm = PRONOUN_BEFORE.search(before)
        attributed = None
        if pm and gender_map and use_gender_resolution:
            g = PRONOUN_GENDER[pm.group(1).lower()]
            cands = [n for n, gg in gender_map.items() if gg == g]
            if len(cands) == 1:
                attributed = cands[0]
        if attributed is None:
            attributed = nearest_preceding(m.start())
        if attributed:
            scores[attributed] += 2

    for m in POSSESSIVE_SENSATION.finditer(scene):
        word = m.group(2).lower()
        if word in {"name", "house", "car", "phone", "voice", "hand", "hands",
                    "mother", "father", "friend", "wife", "husband"}:
            continue
        n = nearest_preceding(m.start())
        if n:
            scores[n] += 1

    if not scores:
        return None, scores
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
        return (ranked[0][0] if ranked[0][1] > 0 else None), scores
    return None, scores


def _detect_tag(scene: str, span: _Span, name_idx: Dict[str, str],
                window: int = 80
                ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Look ±window chars around span for `<name>? <verb> <adverb>?` tag.
    Returns (speaker, style, source)."""
    after = scene[span.end: span.end + window]
    before = scene[max(0, span.start - window): span.start]
    for region in (after, before):
        cut = re.search(r"[.!?]\s|\n\n", region)
        if cut and region is after:
            region = region[:cut.end()]
        elif cut and region is before:
            cuts = list(re.finditer(r"[.!?]\s|\n\n", region))
            if cuts:
                region = region[cuts[-1].end():]
        v = VERB_PATTERN.search(region)
        if not v:
            continue
        verb = v.group(1).lower()
        style = VERB_TO_STYLE.get(verb)
        adverb_window = region[max(0, v.start() - 30): v.end() + 30]
        adv = ADVERB_PATTERN.search(adverb_window)
        if adv:
            adv_word = adv.group(1).lower()
            if style and style != "level":
                style = f"{adv_word} {style}"
            else:
                style = adv_word
            source = "tag-adverb-verb"
        elif style == "level":
            style = None
            source = None
        else:
            source = "tag-verb"
        speaker_name: Optional[str] = None
        for nm in WORD.finditer(region):
            full = name_idx.get(nm.group(0).lower())
            if full:
                speaker_name = full
                break
        return speaker_name, style, source
    return None, None, None


def _detect_pronoun_tag(scene: str, span: _Span, gender_map: Dict[str, str],
                        window: int = 80) -> Optional[str]:
    """`"...," she said` resolution via gender_map. Only fires when
    exactly ONE cast member matches the pronoun's gender."""
    after = scene[span.end: span.end + window]
    before = scene[max(0, span.start - window): span.start]
    for region in (after, before):
        cut = re.search(r"[.!?]\s|\n\n", region)
        if cut:
            region = region[:cut.end()]
        m = BARE_PRONOUN_TAG.search(region)
        if not m:
            continue
        gender = PRONOUN_GENDER[m.group(1).lower()]
        cands = [n for n, g in gender_map.items() if g == gender]
        if len(cands) == 1:
            return cands[0]
    return None


# ============================================================
# Pipeline orchestration
# ============================================================

def _dedupe_cast(cast: List[str]) -> List[str]:
    """Drop duplicate cast names while preserving first-seen order.
    Story characters can be joined from a possibly-duplicated table —
    sending duplicates to the LLM (cast indexed 0..5 with two of the
    same name) confuses speaker_index decisions and inflates the
    `-1` (NPC) hedge."""
    seen_lower = set()
    out: List[str] = []
    for c in cast or []:
        n = (c or "").strip()
        if not n:
            continue
        k = n.lower()
        if k in seen_lower:
            continue
        seen_lower.add(k)
        out.append(n)
    return out


def run_code_stage(scene: str, cast: List[str]
                   ) -> Tuple[List[Dict[str, Any]], Dict[str, str], Optional[str], List[int]]:
    """Stage 1 — pure deterministic extraction. Returns:
        (segments, gender_map, pov, item_indices)
    where `item_indices[i]` is the segments-index for LLM item number i+1
    (1-based). `segments` are dicts ready for JSON serialization.
    """
    cast = _dedupe_cast(cast)
    name_idx = _name_index(cast)
    spans = _find_spans(scene)
    raw_segments = _build_segments(scene, spans)

    gender_map = _infer_gender_map(scene, name_idx)
    pov, _pov_scores = _score_pov(scene, name_idx, gender_map)

    # Pass 1: tag-name + verb-style on dialogues; thought defaults to POV.
    cursor = 0
    for seg in raw_segments:
        idx = scene.find(seg.text, cursor)
        if idx < 0:
            continue
        seg_start, seg_end = idx, idx + len(seg.text)
        cursor = seg_end
        if seg.kind == "dialogue":
            sp_name, style, src = _detect_tag(
                scene, _Span("dialogue", seg_start, seg_end, seg.text), name_idx,
            )
            seg.speaker = sp_name
            seg.speaker_source = "tag-name" if sp_name else None
            seg.emotion = style
            seg.emotion_source = src
        elif seg.kind == "thought":
            seg.speaker = pov
            seg.speaker_source = "pov" if pov else None
            seg.emotion = "inner thought"
            seg.emotion_source = "rule"
        else:
            seg.speaker = "narrator"
            seg.speaker_source = "rule"
            seg.emotion = None

    # Pass 2: pronoun-tag for unresolved dialogues.
    # SKIPPED for 3+ character scenes — gender_map gets confused when a
    # POV character interacts with multiple other characters (their names
    # appear next to pronouns describing the POV character's actions on
    # them, which mis-credits the wrong gender). When that happens every
    # `"she said"` / `"he said"` resolves to the wrong speaker. The
    # 2-character complement-by-elimination rule only fixes this for
    # exactly 2 cast members; for 3+ we'd need stronger evidence
    # (anatomy patterns, etc.) to be safe. For now, leave such scenes
    # unresolved at this stage and let the LLM polish handle attribution
    # from full scene context — empirically much more reliable.
    if len(name_idx.values()) <= 2:
        cursor = 0
        for seg in raw_segments:
            idx = scene.find(seg.text, cursor)
            if idx < 0:
                continue
            seg_start, seg_end = idx, idx + len(seg.text)
            cursor = seg_end
            if seg.kind != "dialogue" or seg.speaker:
                continue
            guess = _detect_pronoun_tag(
                scene, _Span("dialogue", seg_start, seg_end, seg.text), gender_map,
            )
            if guess:
                seg.speaker = guess
                seg.speaker_source = "tag-pronoun"

    # Convert dataclasses → dicts and collect indices of items needing LLM.
    segments_dicts: List[Dict[str, Any]] = [asdict(s) for s in raw_segments]
    item_indices: List[int] = [
        i for i, s in enumerate(segments_dicts)
        if s["kind"] in ("dialogue", "thought")
    ]
    return segments_dicts, gender_map, pov, item_indices


# ============================================================
# Stage 2: LLM polish prompt + parsing
# ============================================================

PROMPT_TEMPLATE = """You are classifying speakers and emotional delivery for spoken dialogue and inner thoughts in a story scene.

CAST (only these can speak with their own voice, indexed 0-based):
{cast_indexed}

The scene has been split into ordered items. Each item is DIALOGUE (in quotes) or INNER THOUGHT (in *asterisks*). Each has a code-derived guess [code: speaker=X emotion=Y]. Verify against the scene context and OVERRIDE if needed.

IMPORTANT — speakers NOT in the cast (minor NPCs like a shopkeeper, a librarian, a passing guard, etc. who appear in the scene but aren't in the cast list above): use speaker_index = -1. These lines will be read by the narrator voice. NEVER force-fit a non-cast speaker into a cast slot.

OUTPUT FORMAT — JSON object with exactly these keys, no other commentary:
- "pov": cast index (integer) for whose perspective the scene is from (used for inner-thought attribution)
- "mood": short phrase 2-6 words (default emotion for narrator segments, e.g. "tense and accusatory", "intimate hushed")
- "i": JSON array, one entry per item in order. Each entry: [speaker_index, "1-3 word emotion phrase"]
  - speaker_index is the cast member's index, OR -1 if the speaker is a minor NPC not in the cast
  - For inner thought, speaker is the cast member whose POV the thought is from
  - emotion is delivery style: "calm", "soft whisper", "sharp angry", "playful tease", "low intimate", "breathless urgent", "amused", "weary", etc.

EXAMPLE INPUT:
CAST:
0=Mira (female)
1=Caleb (male)
SCENE:
\"\"\"Mira walked in. "I told you," she said, voice tight. He shrugged. "And I didn't believe you." The waiter approached. "More wine?" he asked.\"\"\"
ITEMS:
1. dialogue: "I told you," [code: speaker=Mira emotion=null]
2. dialogue: "And I didn't believe you." [code: no guess]
3. dialogue: "More wine?" [code: no guess]

EXAMPLE OUTPUT:
{{"pov":0,"mood":"tense, accusatory","i":[[0,"firm tight"],[1,"casual dismissive"],[-1,"polite"]]}}

NOW DO THE SAME FOR THIS SCENE.

CAST:
{cast_indexed}

SCENE:
\"\"\"
{scene}
\"\"\"

ITEMS:
{items_block}

Output JSON only. No commentary, no markdown fences."""


def build_polish_prompt(scene: str, cast: List[str], gender_map: Dict[str, str],
                        segments: List[Dict[str, Any]],
                        item_indices: List[int]) -> str:
    gender_label = {"m": "male", "f": "female", "n": "unknown"}
    # Cast block uses 0-based indices (matched in `merge_verdicts` to map
    # speaker_index back to a name). Compact format trades readability for
    # ~3-4x smaller LLM output → ~2x faster polish on 8B-class models.
    cast_indexed = "\n".join(
        f"{i}={c} ({gender_label.get(gender_map.get(c, 'n'), 'unknown')})"
        for i, c in enumerate(cast)
    )
    lines: List[str] = []
    for n, seg_idx in enumerate(item_indices, start=1):
        seg = segments[seg_idx]
        sp = seg.get("speaker") or None
        emo = seg.get("emotion") or None
        if seg["kind"] == "thought":
            hint = f"[code: speaker={sp or 'unknown'} emotion=inner thought (POV)]"
        else:
            sp_str = sp if sp else "null"
            emo_str = emo if emo else "null"
            if sp is None and emo is None:
                hint = "[code: no guess]"
            else:
                hint = f"[code: speaker={sp_str} emotion={emo_str}]"
        text_clean = seg["text"].strip().replace("\n", " ")
        lines.append(f"{n}. {seg['kind']}: {text_clean}  {hint}")
    return PROMPT_TEMPLATE.format(
        cast_indexed=cast_indexed,
        scene=scene,
        items_block="\n".join(lines),
    )


def parse_polish_response(raw: str) -> Optional[Dict[str, Any]]:
    """Robust JSON extraction. Strips think tags, markdown fences, prose."""
    if not raw:
        return None
    txt = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", txt, re.DOTALL)
    if fence:
        txt = fence.group(1).strip()
    s, e = txt.find("{"), txt.rfind("}")
    if s >= 0 and e > s:
        txt = txt[s:e + 1]
    try:
        return json.loads(txt)
    except Exception:
        return None


# ============================================================
# Stage 3: merge LLM verdicts into segments
# ============================================================

def merge_verdicts(segments: List[Dict[str, Any]], item_indices: List[int],
                   llm_obj: Optional[Dict[str, Any]],
                   code_pov: Optional[str],
                   cast: Optional[List[str]] = None) -> Dict[str, Any]:
    """Apply LLM verdicts to segments in place. Returns telemetry dict.

    Compact-format input shape (current production):
        {"pov": <int idx>, "mood": "...", "i": [[<int idx | -1>, "<emotion>"], ...]}
    Speaker index -1 means "minor NPC, not in cast" — those lines are
    rerouted to the narrator voice (kind switched to "narrator", speaker
    cleared) so the TTS dispatcher reads them in the narrator's voice
    instead of force-fitting an unrelated cast member.

    Legacy input shape (kept for any cached/in-flight runs):
        {"pov_character": "Name", "scene_mood": "...", "items": {"1": {"speaker": "Name", "emotion": "..."}, ...}}
    """
    obj = llm_obj or {}
    cast = cast or []

    # ---- Detect format and normalize to (pov_name, mood, per-item dict) ----
    compact_items = obj.get("i")
    if isinstance(compact_items, list):
        # Compact format
        pov_idx = obj.get("pov")
        if isinstance(pov_idx, int) and 0 <= pov_idx < len(cast):
            pov = cast[pov_idx]
        else:
            pov = code_pov
        scene_mood = (obj.get("mood") or "").strip() or "neutral"

        # Convert array → dict keyed by 1-based item number, with speaker as
        # cast name OR sentinel "__narrator__" for index -1.
        normalized: Dict[int, Dict[str, Any]] = {}
        for n, entry in enumerate(compact_items, start=1):
            if not isinstance(entry, list) or len(entry) < 1:
                continue
            sp_idx = entry[0]
            emo = entry[1] if len(entry) >= 2 else None
            if isinstance(sp_idx, int) and 0 <= sp_idx < len(cast):
                normalized[n] = {"speaker": cast[sp_idx], "emotion": emo}
            elif isinstance(sp_idx, int) and sp_idx == -1:
                normalized[n] = {"speaker": "__narrator__", "emotion": emo}
            # ignore malformed entries
    else:
        # Legacy verbose format
        pov = obj.get("pov_character") or code_pov
        scene_mood = (obj.get("scene_mood") or "").strip() or "neutral"
        legacy_items = obj.get("items") or {}
        normalized = {}
        if isinstance(legacy_items, dict):
            for k, v in legacy_items.items():
                try:
                    n = int(k)
                except (TypeError, ValueError):
                    continue
                if isinstance(v, dict):
                    normalized[n] = v

    overrides_speaker = 0
    overrides_emotion = 0
    fills_speaker = 0
    fills_emotion = 0
    routed_to_narrator = 0

    for n, seg_idx in enumerate(item_indices, start=1):
        seg = segments[seg_idx]
        verdict = normalized.get(n)
        if not isinstance(verdict, dict):
            continue
        new_sp = (verdict.get("speaker") or "").strip() or None
        new_emo = (verdict.get("emotion") or "").strip() or None

        if new_sp == "__narrator__":
            # The LLM hedged on this dialogue with -1 ("not in cast").
            # Don't clobber `kind` — the segment IS still a quoted
            # dialogue span. Mark uncertain and let `fix_split_quotes`
            # try to recover from surrounding tag context (most -1
            # routings on split-quote closers are recoverable from the
            # preceding `"... X said. "..."` tag clause). If recovery
            # fails, the segment stays speaker=None and the TTS
            # dispatcher falls back to the narrator voice anyway.
            seg["speaker"] = None
            seg["speaker_source"] = "llm_narrator_uncertain"
            routed_to_narrator += 1
        elif new_sp:
            if seg.get("speaker") and new_sp != seg["speaker"]:
                overrides_speaker += 1
            elif not seg.get("speaker"):
                fills_speaker += 1
            seg["speaker"] = new_sp
            seg["speaker_source"] = "llm"

        if new_emo:
            if seg.get("emotion") and new_emo != seg["emotion"]:
                overrides_emotion += 1
            elif not seg.get("emotion"):
                fills_emotion += 1
            seg["emotion"] = new_emo
            seg["emotion_source"] = "llm"

    for seg in segments:
        if seg["kind"] == "narrator" and not seg.get("emotion"):
            seg["emotion"] = scene_mood
            seg["emotion_source"] = "scene_mood"

    return {
        "pov_character": pov,
        "scene_mood": scene_mood,
        "overrides_speaker": overrides_speaker,
        "overrides_emotion": overrides_emotion,
        "fills_speaker": fills_speaker,
        "fills_emotion": fills_emotion,
        "routed_to_narrator": routed_to_narrator,
    }


# ============================================================
# Post-merge: split-quote tag-following pass
# ============================================================
#
# Catches cases where the LLM mis-attributed short dialogue fragments that
# are part of a "split quote": `"X," he said. "Y."` — both X and Y belong
# to the speaker named in the middle clause's tag, but the LLM (especially
# small models like Ministral-3B/8B) sometimes flips the OPENER to the
# wrong character based on alternation heuristics.
#
# Pattern detected (after merge_verdicts has produced final speaker
# assignments):
#
#   [i-1] kind=dialogue, speaker=??
#   [i]   kind=narrator, text starts with "<NAME> said" / "he said" / etc.
#   [i+1] kind=dialogue, speaker=??   (optional — split-quote second half)
#
# When [i]'s tag resolves to a cast member Y, [i-1] AND [i+1] (if dialogue)
# are forced to speaker=Y. Tag resolution accepts:
#   - exact cast-name prefix ("Marcus said", "Mira Chen replied")
#   - bare pronoun ("he said") IFF exactly one cast member of that gender


# TIGHT speech-tag verb list for split-quote detection.
#
# Deliberately excludes ambiguous action verbs from VERB_STYLE that often
# describe physical actions, NOT speech: chuckled, laughed, smiled, sighed,
# growled, snarled, breathed, panted, gasped, smirked, etc. These create
# false positives when a narrator says "Mira chuckled. Her hands slid..."
# — the chuckle isn't a speech tag for the surrounding dialogue.
#
# Includes only verbs where the dominant interpretation is "<subject> spoke":
# Speech-tag verbs (TIER 1): always function as speech tags adjacent
# to dialogue. CONTEXTUAL_TAG_VERBS (TIER 2): action verbs that ALSO
# function as speech tags ONLY when adjacent to a quote. Both lists are
# WordNet-curated, regenerated by `backend/tools/curate_speech_verbs.py`.
from .speech_verbs import SPEECH_TAG_VERBS, CONTEXTUAL_TAG_VERBS

# Sort for regex match-priority (longest first → "responded" matches
# before "respond" so the regex doesn't truncate at "respond").
SPEECH_TAG_VERBS = sorted(set(SPEECH_TAG_VERBS), key=len, reverse=True)
CONTEXTUAL_TAG_VERBS = sorted(set(CONTEXTUAL_TAG_VERBS), key=len, reverse=True)
ALL_TAG_VERBS_CTX = sorted(set(SPEECH_TAG_VERBS) | set(CONTEXTUAL_TAG_VERBS),
                           key=len, reverse=True)


def _has_other_cast_name(text: str, cast: List[str], exclude: str) -> bool:
    """Return True if `text` mentions any cast member other than `exclude`
    AS A SUBJECT (not as the object of a preposition).

    Cast names appearing in object position (preceded by `to`/`at`/`with`
    etc) are addressees, NOT subject-change signals. This fixes the
    common pattern `"X," Y said to Z. "..."` where Z is who Y is
    addressing — without this guard, P2 in `fix_split_quotes` wrongly
    bails on every `Y said to Z` tag.

    Used to detect a "subject change" inside a narrator clause:
      "Mira said. Her voice softened further."       → no other cast → safe
      "Mira said. Then Caleb walked in."             → mentions Caleb → unsafe
      "Mira said to Caleb. Her tone darkened."       → Caleb in object pos → safe
    """
    if not text:
        return False
    excl_lower = (exclude or "").lower()
    for c in cast:
        if not c or c == exclude:
            continue
        if c.lower() == excl_lower:
            continue
        for m in re.finditer(r"\b" + re.escape(c.lower()) + r"\b",
                             text, re.IGNORECASE):
            before = text[max(0, m.start() - 40):m.start()].rstrip(" \t,;:")
            words = before.split()
            if words:
                last = words[-1].lower().strip(".!?,:;\"'`")
                if last in OBJECT_PREPOSITIONS:
                    continue
            return True
    return False


def _named_subject_of_gender(
    text: str,
    cast: List[str],
    gender_map: Dict[str, str],
    gender: str,
) -> Optional[str]:
    """Return the cast name (matching gender) most likely to be the SUBJECT
    in a narrator clause. Used to disambiguate `he said` / `she said` when
    multiple cast members share the gender.

    Heuristic: find cast names of the requested gender that appear in the
    text. If exactly one, return it. If multiple, return None (ambiguous).
    """
    if not text or gender == "n":
        return None
    matches = set()
    cast_by_len = sorted({c for c in cast if c}, key=len, reverse=True)
    matched_spans: List[Tuple[int, int]] = []
    for cast_full in cast_by_len:
        if gender_map.get(cast_full) != gender:
            continue
        for m in re.finditer(r"\b" + re.escape(cast_full) + r"(?:'s)?\b",
                             text, re.IGNORECASE):
            if any(m.start() >= s and m.end() <= e for s, e in matched_spans):
                continue
            matches.add(cast_full)
            matched_spans.append((m.start(), m.end()))
        first = cast_full.split()[0]
        if first.lower() != cast_full.lower():
            for m in re.finditer(r"\b" + re.escape(first) + r"(?:'s)?\b",
                                 text, re.IGNORECASE):
                if any(m.start() >= s and m.end() <= e for s, e in matched_spans):
                    continue
                matches.add(cast_full)
                matched_spans.append((m.start(), m.end()))
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _resolve_tag_speaker(
    narrator_text: str,
    cast: List[str],
    gender_map: Dict[str, str],
    surrounding_speakers: Optional[List[str]] = None,
    preceding_narrator: Optional[str] = None,
) -> Optional[str]:
    """Backwards-compat shim that returns just the speaker (no confidence).
    New callers should use `_resolve_tag_speaker_with_conf`."""
    res = _resolve_tag_speaker_with_conf(
        narrator_text, cast, gender_map, surrounding_speakers, preceding_narrator,
    )
    return res[0] if res else None


def _resolve_tag_speaker_with_conf(
    narrator_text: str,
    cast: List[str],
    gender_map: Dict[str, str],
    surrounding_speakers: Optional[List[str]] = None,
    preceding_narrator: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """Return `(canonical_cast_name, confidence)` where confidence is:
        "high" — direct cast-name+verb tag match (e.g. "Mira said")
        "low"  — pronoun+verb tag match (gender-disambiguated)
    Or None if no resolution.

    Callers in `fix_split_quotes` use the confidence flag to decide
    whether to override an already-set speaker. Pronoun resolution
    must NEVER override an existing LLM-set name — gender_map can be
    wrong (cross-character anatomical references pollute it), and the
    LLM had full scene context.

    Uses ALL_TAG_VERBS_CTX (includes gasped/cried/grunted/etc) because
    this resolver only runs on quote-adjacent narrators, where those
    verbs unambiguously function as speech tags.
    """
    text = narrator_text.lstrip()
    if not text:
        return None
    sb = SENTENCE_BOUNDARY.search(text)
    head = text[:sb.start()] if sb else text[:120]

    # 1. Direct cast-name tag (longest first; "Mira Chen" should beat "Mira").
    cast_by_len = sorted({c for c in cast if c}, key=len, reverse=True)
    for cast_full in cast_by_len:
        if head.lower().startswith(cast_full.lower()):
            after = head[len(cast_full):].lstrip()
            if re.match(r"^(?:" + "|".join(ALL_TAG_VERBS_CTX) + r")\b", after, re.IGNORECASE):
                return (cast_full, "high")

    # 2. Pronoun tag — needs gender disambiguation.
    pm = re.match(r"^(he|she|they)\s+(?:" + "|".join(ALL_TAG_VERBS_CTX) + r")\b",
                  head, re.IGNORECASE)
    if pm:
        pronoun = pm.group(1).lower()
        gender = {"he": "m", "she": "f", "they": "n"}[pronoun]
        if gender == "n":
            return None

        # Disambiguation strategy ordered by reliability:
        #   (a) preceding narrator names ONE same-gender cast → use that
        #   (b) preceding narrator names MULTIPLE same-gender cast → ambiguous, bail
        #   (c) no preceding-narrator hint AND surrounding dialogue agrees on
        #       a single same-gender speaker → use that (split-quote case)
        #   (d) only one cast member of that gender → use it
        if preceding_narrator:
            preceding_same = _all_cast_of_gender_in(
                preceding_narrator, cast, gender_map, gender)
            if len(preceding_same) == 1:
                return (preceding_same[0], "low")
            if len(preceding_same) > 1:
                return None  # ambiguous — multiple same-gender subjects

        if surrounding_speakers:
            matches = [
                s for s in surrounding_speakers
                if s and s in gender_map and gender_map[s] == gender
            ]
            if matches and len(set(matches)) == 1:
                return (matches[0], "low")

        all_candidates = [n for n, g in gender_map.items() if g == gender]
        if len(all_candidates) == 1:
            return (all_candidates[0], "low")
    return None


# Prepositions that signal the following noun is an OBJECT, not a subject.
# Used by beat-leadin to skip cast names appearing as objects:
#   "He turned to Caleb."          → Caleb is object → don't trigger beat
#   "His fingers brushed Mira's"   → Mira is object → don't trigger beat
OBJECT_PREPOSITIONS = {
    "to", "at", "with", "for", "toward", "towards", "past", "behind",
    "before", "after", "into", "onto", "from", "of", "about", "around",
    "by", "near", "beside", "between", "among", "against", "under", "over",
    "across", "through", "without", "alongside", "besides",
}


def _resolve_beat_leadin(narrator_text: str, cast: List[str]) -> Optional[str]:
    """Detect a 'beat-leadin' narrator: a short clause naming exactly ONE
    cast member as the SUBJECT (not as an object) that immediately precedes
    a dialogue line.

    Examples that trigger:
      "Mira smiled."                         → Mira
      "Sara's eyes squeezed shut."           → Sara Chen (matches "Sara")
      "Marcus turned away."                  → Marcus

    Examples that do NOT trigger:
      "Mira turned to Caleb."                → Mira subject + Caleb object → returns Mira
      "He turned to Caleb."                  → Caleb is object (after `to`) → no subject named
      "He gestured at the door."             → no cast name → None
      "Mira smiled. He thought about ..."    → multi-sentence; ambiguous → None
      "Mira sat. She stared at the water."   → multi-sentence narrative; the
                                                next dialogue may be from a
                                                DIFFERENT character. Bail.

    Conservative: capped at 60 chars + at most ONE sentence terminator
    (single beat clause). Multi-sentence narratives often describe one
    character's action while the dialogue speaker is someone else.
    Skips cast names appearing as objects (preceded by a preposition).
    """
    if not narrator_text:
        return None
    text = narrator_text.strip()
    if len(text) > 60:
        return None
    if len(re.findall(r"[.!?]", text)) > 1:
        return None

    # Skip beats that start with a pronoun ("He/She/They" or "His/Her/Their"):
    # the pronoun is the subject and any cast name later is almost always an
    # OBJECT (e.g. "He looked Caleb up and down" — the speaker is whoever "he"
    # refers to, not Caleb).
    if re.match(r"^(?:he|she|they|his|her|hers|their|theirs)\s+",
                text, re.IGNORECASE):
        return None

    # Skip if any SPEECH tag verb appears in the beat. This narrator is a
    # speech tag (handled by P1/P2 with their stricter rules: paragraph-break
    # detection, subject-change detection, etc.). Beat-leadin is a fallback
    # for ACTION beats only ("Mira smiled.", "Sara's eyes squeezed shut.").
    # Bail on contextual tag verbs too (gasped/grunted/etc) — adjacent to
    # a quote those ARE speech tags and P2 should handle them.
    if re.search(r"\b(?:" + "|".join(ALL_TAG_VERBS_CTX) + r")\b",
                 text, re.IGNORECASE):
        return None

    cast_by_len = sorted({c for c in cast if c}, key=len, reverse=True)
    matched_spans: List[Tuple[int, int]] = []
    found_as_subject = set()

    def _is_object_position(start_offset: int) -> bool:
        """True if the cast name at `start_offset` is preceded by a preposition."""
        before = text[max(0, start_offset - 40):start_offset].rstrip(" \t,;:")
        words = before.split()
        if not words:
            return False
        last = words[-1].lower().strip(".!?,:;\"'`")
        return last in OBJECT_PREPOSITIONS

    for cast_full in cast_by_len:
        candidates = [(m.start(), m.end(), cast_full)
                      for m in re.finditer(r"\b" + re.escape(cast_full) + r"(?:'s)?\b",
                                           text, re.IGNORECASE)]
        first = cast_full.split()[0]
        if first.lower() != cast_full.lower():
            candidates.extend(
                (m.start(), m.end(), cast_full)
                for m in re.finditer(r"\b" + re.escape(first) + r"(?:'s)?\b",
                                     text, re.IGNORECASE)
            )
        for start, end, name in candidates:
            if any(start >= s and end <= e for s, e in matched_spans):
                continue
            matched_spans.append((start, end))
            if _is_object_position(start):
                continue  # cast name in object position — don't credit as subject
            found_as_subject.add(name)

    if len(found_as_subject) == 1:
        return next(iter(found_as_subject))
    return None


def _all_cast_of_gender_in(
    text: str, cast: List[str], gender_map: Dict[str, str], gender: str,
) -> List[str]:
    """List unique cast members of `gender` mentioned in `text` as subjects
    (skipping object-positioned mentions). Order preserved by first-mention.
    """
    if not text or gender == "n":
        return []
    seen = []
    matched_spans: List[Tuple[int, int]] = []
    cast_by_len = sorted({c for c in cast if c}, key=len, reverse=True)
    for cast_full in cast_by_len:
        if gender_map.get(cast_full) != gender:
            continue
        candidates = [(m.start(), m.end()) for m in re.finditer(
            r"\b" + re.escape(cast_full) + r"(?:'s)?\b", text, re.IGNORECASE)]
        first = cast_full.split()[0]
        if first.lower() != cast_full.lower():
            candidates.extend((m.start(), m.end()) for m in re.finditer(
                r"\b" + re.escape(first) + r"(?:'s)?\b", text, re.IGNORECASE))
        for start, end in candidates:
            if any(start >= s and end <= e for s, e in matched_spans):
                continue
            matched_spans.append((start, end))
            # Object position check
            before = text[max(0, start - 40):start].rstrip(" \t,;:")
            words = before.split()
            if words:
                last = words[-1].lower().strip(".!?,:;\"'`")
                if last in OBJECT_PREPOSITIONS:
                    continue
            if cast_full not in seen:
                seen.append(cast_full)
    return seen


def _adjacent_pronoun_tag(segments: List[Dict[str, Any]], i: int) -> Optional[str]:
    """If segment `i` (a dialogue) has a clear `<pronoun> <speech_verb>`
    in its IMMEDIATE following or preceding narrator, return the pronoun
    ('he', 'she', 'they'). Else None.

    Used by `gender_consistency_unset` to detect impossible-gender
    speaker assignments — e.g. existing speaker is male but the adjacent
    narrator says "she gasped".
    """
    pron_pat = re.compile(
        r"^\s*(he|she|they)\s+(?:" + "|".join(ALL_TAG_VERBS_CTX) + r")\b",
        re.IGNORECASE,
    )
    for offset in (1, -1):
        j = i + offset
        if not (0 <= j < len(segments)):
            continue
        if segments[j].get("kind") != "narrator":
            continue
        text = segments[j].get("text") or ""
        # FOLLOWING narrator: skip if it starts with paragraph break.
        if offset == 1 and text.lstrip(" \t").startswith("\n\n"):
            continue
        # PRECEDING narrator: skip if it ends with paragraph break.
        if offset == -1 and text.rstrip(" \t").endswith("\n\n"):
            continue
        m = pron_pat.match(text)
        if m:
            return m.group(1).lower()
    return None


def gender_consistency_unset(
    segments: List[Dict[str, Any]],
    cast: List[str],
    gender_map: Dict[str, str],
    confident_genders: Optional[set] = None,
) -> int:
    """For each dialogue with an existing speaker, if the immediately-
    adjacent narrator has a `<pronoun> <speech_verb>` tag and the
    pronoun's gender does NOT match the existing speaker's gender, the
    existing speaker is impossible. Unset it (speaker=None,
    speaker_source="gender_mismatch_unset") so `fix_split_quotes` can
    try to re-resolve from surrounding context.

    `confident_genders` is the set of cast names whose gender label is
    HIGH confidence (e.g. authoritative DB source). When provided,
    Layer F only fires when the speaker's gender label is in this set —
    pronoun-window inference is too unreliable to act on, since
    cross-character anatomical references can pollute the per-scene map.

    Returns the number of unsets applied.
    """
    pron_to_gender = {"he": "m", "she": "f", "they": "n"}
    unsets = 0
    for i, seg in enumerate(segments):
        if seg.get("kind") != "dialogue":
            continue
        spk = seg.get("speaker")
        if not spk or spk == "narrator":
            continue
        spk_g = gender_map.get(spk)
        if spk_g not in ("m", "f"):
            continue
        if confident_genders is not None and spk not in confident_genders:
            continue
        pron = _adjacent_pronoun_tag(segments, i)
        if not pron:
            continue
        pron_g = pron_to_gender.get(pron)
        if pron_g not in ("m", "f"):
            continue
        if pron_g != spk_g:
            seg["speaker"] = None
            seg["speaker_source"] = "gender_mismatch_unset"
            unsets += 1
    return unsets


def fix_split_quotes(
    segments: List[Dict[str, Any]],
    cast: List[str],
    gender_map: Dict[str, str],
) -> int:
    """Post-process: correct speaker attribution for dialogue segments
    using surrounding narrator clues. Three priorities:

      P1 (strongest): the FOLLOWING narrator starts with `<speaker> said`.
          This is the canonical attribution form: `"X" Y said.` — Y owns X.

      P2 (medium): the PRECEDING narrator starts with `<speaker> said`.
          This is the split-quote-closer form: `"X" Y said. "Z"` — Y also
          owns Z, BUT only when the preceding narrator doesn't introduce a
          subject change (i.e., doesn't mention another cast member).

      P3 (weakest): the PRECEDING narrator is a short BEAT naming exactly
          one cast member without a speech tag (e.g. "Mira smiled.",
          "Sara's eyes squeezed shut."). Conservative: only fires when
          the beat names exactly one character.

    Mutates `segments` in place. Returns total corrections applied.
    """
    if not cast:
        return 0
    corrections = 0
    for i, seg in enumerate(segments):
        if seg.get("kind") != "dialogue":
            continue
        original_speaker = seg.get("speaker")

        # Build "surrounding speakers" hint for pronoun-tag disambiguation:
        # adjacent dialogue's already-attributed speakers (within ±2 positions).
        surrounding: List[str] = []
        for j in (i - 2, i - 1, i + 1, i + 2):
            if 0 <= j < len(segments):
                if segments[j].get("kind") == "dialogue" and segments[j].get("speaker"):
                    surrounding.append(segments[j]["speaker"])

        new_speaker: Optional[str] = None
        new_confidence: str = "low"
        source = ""

        preceding_narr = (
            segments[i - 1].get("text") or ""
            if i - 1 >= 0 and segments[i - 1].get("kind") == "narrator"
            else None
        )

        # P1: FOLLOWING narrator's speech tag → attributes THIS dialogue.
        # SKIP P1 when the following narrator starts with a paragraph break (`\n\n`):
        # that signals a new scene beat / turn-taking, not a tag continuation.
        if i + 1 < len(segments) and segments[i + 1].get("kind") == "narrator":
            following = segments[i + 1].get("text") or ""
            is_paragraph_break = following.lstrip(" \t").startswith("\n\n")
            if not is_paragraph_break:
                res = _resolve_tag_speaker_with_conf(
                    following, cast, gender_map, surrounding,
                    preceding_narrator=preceding_narr,
                )
                if res:
                    new_speaker, new_confidence = res
                    source = "post_p1_following_tag"

        # P2: PRECEDING narrator's speech tag, with subject-change check.
        # SKIP P2 when the preceding narrator ENDS with a paragraph break (`\n\n`):
        # that signals turn-taking (next dialogue is a NEW speaker), not a
        # split-quote continuation.
        if not new_speaker and preceding_narr is not None:
            preceding_ends_with_break = preceding_narr.rstrip(" \t").endswith("\n\n")
            if not preceding_ends_with_break:
                res = _resolve_tag_speaker_with_conf(
                    preceding_narr, cast, gender_map, surrounding)
                if res:
                    cand, cand_conf = res
                    if not _has_other_cast_name(preceding_narr, cast, exclude=cand):
                        new_speaker = cand
                        new_confidence = cand_conf
                        source = "post_p2_preceding_tag"

        # P3: BEAT-LEADIN — short single-character beat in PRECEDING narrator.
        # Mark as LOW confidence: the named subject is the ACTOR, not
        # necessarily the SPEAKER (e.g. "Mira looked at him." precedes
        # Caleb's reply). Confidence guard below ensures this never
        # overrides an existing LLM-set speaker — only fills empties.
        if not new_speaker and preceding_narr is not None:
            beat = _resolve_beat_leadin(preceding_narr, cast)
            if beat:
                new_speaker = beat
                new_confidence = "low"
                source = "post_p3_beat_leadin"

        if new_speaker and new_speaker != original_speaker:
            # NEVER override an existing LLM-set speaker via low-
            # confidence (pronoun- or beat-based) resolution. Pronoun
            # resolution depends on gender_map which can be wrong
            # (cross-character anatomical references); the LLM had
            # full scene context — trust its choice unless we have a
            # high-confidence (direct cast-name) tag saying otherwise.
            if original_speaker and new_confidence != "high":
                continue
            seg["speaker"] = new_speaker
            seg["speaker_source"] = source
            corrections += 1

    return corrections


def to_canonical_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip provenance fields (`speaker_source`, `emotion_source`, `kind`)
    so the cached segments exactly match the legacy shape consumed by
    the TTS dispatcher: [{speaker, text, emotion}, ...].
    """
    out: List[Dict[str, Any]] = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            # Whitespace-only segments are TTS no-ops — safe to drop now
            # that integrity has already been verified upstream.
            continue
        out.append({
            "speaker": s.get("speaker") or "narrator",
            "text": s["text"],   # KEEP original (with leading/trailing whitespace)
            "emotion": s.get("emotion") or "neutral",
        })
    return out
