"""Curate the canonical SPEECH_TAG_VERBS + CONTEXTUAL_TAG_VERBS lists used
by the TTS segment-attribution pipeline (`segment_extraction_v2.py`).

PHILOSOPHY
----------
Speech-tag verb attribution depends on a definitive list of verbs that
function as `<subject> <verb>` tags adjacent to quoted dialogue:

    "Yes," she said.            ← `said` is a TIER-1 (always-speech) verb
    "No," he gasped.            ← `gasped` is a TIER-2 (contextual) verb:
                                   in pure narration it's an action, but
                                   adjacent to a quote it's a speech tag
    "Hmm," she scratched.       ← `scratched` is NEITHER — never a tag

If we maintain the lists by hand, every new verb in fiction ("intoned",
"rejoined", "expostulated", "drawled", "rasped", "snipped", ...) is a
silent miss. Curating from WordNet gives a one-time exhaustive sweep
plus a reproducible pipeline for re-curation.

PROCESS
-------
1. Seed: WordNet hyponyms of the canonical "say" sense (`say.v.07` —
   "express in words"), `speak.v.01`, `tell.v.02`, plus a few high-recall
   adjacent senses.
2. Filter: drop multi-word entries, archaic-only entries, and synsets
   whose primary meaning is non-communicative.
3. Tier classification:
   - TIER 1 (always speech tag): the lemma's PRIMARY WordNet sense is
     communicative. Examples: said, asked, whispered, shouted, replied.
   - TIER 2 (contextual): the lemma has a communicative sense AND a
     vocalization/action sense. The action sense usually ranks first
     in WordNet. Examples: gasped, grunted, laughed, cried, sighed.
4. Inflect: generate -ed / -ing / -s forms (catching common irregulars
   like said/says/saying, told/tells/telling, etc).
5. Dedupe + sort.

The output is two Python list literals (TIER_1, TIER_2) printed to stdout.
Paste them into `backend/app/services/tts/segment_extraction_v2.py`,
replacing the existing `SPEECH_TAG_VERBS` and `CONTEXTUAL_TAG_VERBS`
literals.

USAGE
-----
    python backend/tools/curate_speech_verbs.py > /tmp/verbs.py

REQUIREMENTS (dev-only, NOT a runtime dep)
------------------------------------------
    pip install nltk
    python -c "import nltk; nltk.download('wordnet')"
"""

from __future__ import annotations

import re
import sys
from typing import Iterable, Set, Tuple

try:
    from nltk.corpus import wordnet as wn
except ImportError as e:
    print("ERROR: install nltk and download wordnet first.\n"
          "  pip install nltk\n"
          "  python -c \"import nltk; nltk.download('wordnet')\"",
          file=sys.stderr)
    raise SystemExit(1) from e


# ===========================================================================
# Seed synsets — the broadest reasonable communicative roots in WordNet.
# `say.v.07` is the "express in words" sense (vs say.v.01 which is "state");
# both are useful. `speak.v.01`, `tell.v.02`, `cry.v.02` (call out / shout)
# cover more ground.
# ===========================================================================
# Highest signal-to-noise seed: `speak.v.01` ("express in speech") and a
# few near-relatives. Avoid `say.v.01` / `tell.v.02` / `communicate.v.02`
# — they pull in non-spoken communication verbs (write, transmit, present,
# propagandize, etc.) which are NOT fiction dialogue tags.
SEED_SYNSETS = [
    "speak.v.01",     # use language
    "speak.v.02",     # express orally
    "express.v.02",   # express verbally
    "answer.v.01",    # react verbally
    "ask.v.01",       # inquire
]

# Words that, if present in the synset's GLOSS, indicate the verb is a
# speaking action (vs writing, gesturing, signalling, etc.). Used as a
# secondary filter to drop any noisy hyponyms that slipped through.
SPOKEN_GLOSS_HINTS = re.compile(
    r"\b(speak|spoken|say|said|saying|utter|uttered|voice|voiced|aloud|"
    r"vocally|tone|tones|whisper|whispered|shout|shouted|talk|talked|"
    r"murmur|mumble|cry|cried|exclaim|reply|replied|respond|responded)\b",
    re.IGNORECASE,
)

# Verbs whose communicative sense is too marginal or whose primary sense
# is non-speech in fiction. Manual exclude list — keeps the noise out
# without compromising recall on legitimate speech tags.
EXCLUDE = {
    # too-broad communication verbs (rarely actual dialogue tags)
    "communicate", "transmit", "convey", "relate", "render", "deliver",
    "present", "submit", "report", "publish", "announce",
    # body-language / non-speech
    "gesture", "signal", "motion", "wave", "nod", "shake", "shrug",
    "point", "wink", "smile", "frown", "scowl", "grin", "smirk",
    "stare", "glare", "glance", "look", "watch", "see",
    # cognition / thinking (handled by inner-thought logic, not speech tags)
    "think", "wonder", "imagine", "ponder", "consider", "reason",
    "believe", "know", "realize", "remember", "recall", "decide",
    # writing / composing (not spoken)
    "write", "compose", "draft", "scribble", "type", "print",
    # too generic to be useful as a tag
    "do", "act", "make", "give", "take", "have", "get", "go",
    # archaic / specialized
    "asseverate", "vouchsafe", "obtest", "philosophize", "pontificate",
    "theologize", "syllogize",
    # foreign / liturgical
    "namaste", "ditto",
    # mistaken hyponyms (WordNet quirks)
    "babble", "burble",  # often non-speech (water/babbling)
}

# Verbs that have BOTH a communicative sense AND a strong physical/vocal
# action sense — these need quote-adjacency to function as speech tags.
# Pure WordNet classification can't reliably tell them apart, so we curate
# this set explicitly.
TIER_2_VERBS = {
    # vocalizations (also describe non-speech sounds)
    "gasp", "cry", "breathe", "growl", "snarl", "grunt", "pant", "moan",
    "groan", "rumble", "wheeze", "hiss", "snort", "snicker", "chuckle",
    "giggle", "laugh", "sigh", "sniff", "snuffle", "snivel", "weep",
    "sob", "shriek", "squeal", "squawk", "squeak", "huff", "puff",
    "purr", "coo", "croak", "gulp", "splutter", "sputter",
    # facial / body actions that sometimes attribute speech
    "smile", "smirk", "snort", "snap",
    # other ambiguous physical/expressive actions
    "exhale", "inhale", "spit", "spat",
}


# ===========================================================================
# Hand-curated supplements — verbs that ARE speech tags in fiction but
# WordNet either misses them or buries them under non-canonical synsets.
# ===========================================================================
TIER_1_SUPPLEMENT = {
    # core saying verbs
    "say", "ask", "reply", "respond", "answer", "state", "remark",
    "add", "note", "tell", "speak", "talk",
    # continuation
    "continue", "repeat", "interject", "interrupt", "resume",
    # contextual completion
    "explain", "agree", "concede", "admit", "warn", "insist", "offer",
    "begin", "start", "finish", "conclude",
    # whispered/quieted speech
    "whisper", "murmur", "mutter", "mouth", "breathe", "drawl",
    # raised speech
    "shout", "yell", "scream", "call", "bellow", "roar", "thunder",
    # urgent / commanding
    "urge", "beg", "plead", "demand", "command", "order", "bark",
    "bid", "snap",
    # mumbled / halting
    "mumble", "stammer", "stutter", "falter",
    # dismissive / dark
    "sneer", "scoff", "drawl", "intone",
    # narrative / formal
    "declare", "pronounce", "proclaim", "assert", "aver", "avow",
    "affirm", "confirm", "deny", "object", "protest", "complain",
    "exclaim", "blurt", "venture", "volunteer", "remark", "muse",
    "reflect", "comment", "observe", "note", "mention", "suggest",
    "propose", "recommend", "advise", "counsel", "caution",
    # query
    "query", "inquire", "enquire", "wonder", "puzzle", "press",
    # answer / acknowledgment
    "rejoin", "retort", "riposte", "snap", "shoot", "fire",
    # greet / address
    "greet", "address", "hail",
    # promise / commit
    "promise", "vow", "swear", "pledge",
    # accusation / disagreement
    "accuse", "challenge", "rebuke", "scold", "chide", "reprimand",
    "berate", "lecture", "preach",
    # fictional dialect-y verbs
    "drone", "rattle", "ramble", "whine", "grizzle", "moan",
    # fiction-specific
    "explained", "expostulated", "ejaculated",  # (legacy fiction usage)
}

# Pre-decline tier-2 supplements (action verbs that attach to dialogue
# only when adjacent to a quote)
TIER_2_SUPPLEMENT = {
    "huff", "puff", "blow", "exhale", "inhale", "swallow", "gulp",
    "scoff", "tut", "tsk", "harrumph",
}


# ===========================================================================
# Inflection: regular and known irregulars
# ===========================================================================

# Known irregulars (base → past, past_participle, 3rd-person-sing, present-participle)
IRREGULARS = {
    "say":     ("said",   "said",   "says",    "saying"),
    "tell":    ("told",   "told",   "tells",   "telling"),
    "speak":   ("spoke",  "spoken", "speaks",  "speaking"),
    "cry":     ("cried",  "cried",  "cries",   "crying"),
    "spit":    ("spat",   "spat",   "spits",   "spitting"),
    "swear":   ("swore",  "sworn",  "swears",  "swearing"),
    "shoot":   ("shot",   "shot",   "shoots",  "shooting"),
    "rise":    ("rose",   "risen",  "rises",   "rising"),
    "begin":   ("began",  "begun",  "begins",  "beginning"),
    "do":      ("did",    "done",   "does",    "doing"),
    "go":      ("went",   "gone",   "goes",    "going"),
    "come":    ("came",   "come",   "comes",   "coming"),
    "give":    ("gave",   "given",  "gives",   "giving"),
    "take":    ("took",   "taken",  "takes",   "taking"),
    "make":    ("made",   "made",   "makes",   "making"),
    "have":    ("had",    "had",    "has",     "having"),
    "get":     ("got",    "gotten", "gets",    "getting"),
    # speech-tag specific
    "drawl":   ("drawled", "drawled", "drawls", "drawling"),
    "intone":  ("intoned", "intoned", "intones", "intoning"),
    "blurt":   ("blurted", "blurted", "blurts", "blurting"),
    "ejaculate": ("ejaculated", "ejaculated", "ejaculates", "ejaculating"),
    "expostulate": ("expostulated", "expostulated", "expostulates", "expostulating"),
    # Stress-on-final-syllable verbs that DOUBLE despite >4 chars:
    "aver":    ("averred", "averred", "avers", "averring"),
    "confer":  ("conferred", "conferred", "confers", "conferring"),
    "occur":   ("occurred", "occurred", "occurs", "occurring"),
    "prefer":  ("preferred", "preferred", "prefers", "preferring"),
    "concur":  ("concurred", "concurred", "concurs", "concurring"),
    "demur":   ("demurred", "demurred", "demurs", "demurring"),
    "rebut":   ("rebutted", "rebutted", "rebuts", "rebutting"),
    "regret":  ("regretted", "regretted", "regrets", "regretting"),
    "submit":  ("submitted", "submitted", "submits", "submitting"),
    "commit":  ("committed", "committed", "commits", "committing"),
    "permit":  ("permitted", "permitted", "permits", "permitting"),
    "control": ("controlled", "controlled", "controls", "controlling"),
}


def regular_inflect(base: str) -> Tuple[str, str, str]:
    """Return (past, third_singular, present_participle) for a regular verb.
    Naive but covers most of English correctly."""
    base = base.lower()
    # CVC consonant-doubling: applies to MONOSYLLABIC + DISYLLABIC-with-
    # stress-on-last-syllable verbs. We can't detect stress without a
    # pronunciation dict, so we approximate: double if word ≤6 chars and
    # ends in CVC. Catches admit→admitted, aver→averred, rebut→rebutted
    # while leaving enter→entered (7 chars) alone. Edge cases handled by
    # the IRREGULARS table.
    def _should_double(w: str) -> bool:
        if len(w) > 5:
            # ≥6-char verbs are usually polysyllabic with first-syllable
            # stress (enter, answer, falter, slither) — no doubling.
            # Edge cases (admit at 5 chars: doubles correctly; commit at
            # 6: would be wrong but uncommon as a speech tag).
            return False
        if not re.search(r"[bcdfghjklmnpqrstvwxz][aeiou][bcdfghjklmnpqrstvwxz]$", w):
            return False
        if w[-1] in "wxy":
            return False
        # Common -er, -en endings on multi-syllable verbs don't double.
        if w.endswith(("er", "en", "el")):
            return False
        return True

    # past tense
    if base.endswith("e"):
        past = base + "d"
    elif _should_double(base):
        past = base + base[-1] + "ed"
    elif base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        past = base[:-1] + "ied"
    else:
        past = base + "ed"
    # 3rd person singular
    if base.endswith(("s", "x", "z", "ch", "sh", "o")):
        third = base + "es"
    elif base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        third = base[:-1] + "ies"
    else:
        third = base + "s"
    # present participle
    if base.endswith("e") and not base.endswith("ee"):
        ing = base[:-1] + "ing"
    elif _should_double(base):
        ing = base + base[-1] + "ing"
    else:
        ing = base + "ing"
    return past, third, ing


def all_forms(base: str) -> Set[str]:
    """Return the set of inflected forms for `base`."""
    base = base.lower().strip()
    # Skip if the base looks like an already-inflected form. WordNet's
    # synsets occasionally include both the lemma AND a past-tense form
    # as separate lemmas; if we re-inflect those we get junk like
    # "explaineds" / "expostulateded".
    if base.endswith(("ed", "ing", "ies")) and len(base) > 4:
        # Heuristic: only accept as base if the inflection is plausibly
        # an actual base verb (some bases legitimately end in 'ed'/'ing',
        # like "wed" or "ring", but those are <=4 chars handled above).
        return set()
    forms = {base}
    if base in IRREGULARS:
        forms.update(IRREGULARS[base])
    else:
        past, third, ing = regular_inflect(base)
        forms.update({past, third, ing})
    return {f for f in forms if f}


# ===========================================================================
# WordNet harvest
# ===========================================================================

def harvest_from_wordnet() -> Set[str]:
    """Walk hyponym chains from each seed synset; collect verb lemmas
    whose synset GLOSS mentions speaking. The gloss filter drops noisy
    hyponyms (e.g. "summarize", "present") that are technically forms of
    communication but never appear as fiction dialogue tags."""
    bases: Set[str] = set()
    visited: Set[str] = set()

    def walk(syn):
        if syn.name() in visited:
            return
        visited.add(syn.name())
        # Only collect lemmas if the gloss looks spoken-y. The filter
        # is permissive — it just drops the obvious non-speech ones.
        gloss = syn.definition() or ""
        if SPOKEN_GLOSS_HINTS.search(gloss):
            for lemma in syn.lemmas():
                name = lemma.name().lower()
                if "_" in name or "-" in name:
                    continue
                if any(c.isdigit() for c in name):
                    continue
                if len(name) < 3:
                    continue
                bases.add(name)
        for hypo in syn.hyponyms():
            walk(hypo)

    for seed in SEED_SYNSETS:
        try:
            syn = wn.synset(seed)
        except Exception:
            print(f"WARN: missing synset {seed}", file=sys.stderr)
            continue
        walk(syn)
    return bases


# ===========================================================================
# Tier classification
# ===========================================================================

def is_tier_2(base: str) -> bool:
    """A base verb is Tier 2 if it's in the explicit Tier-2 set OR if
    its primary WordNet sense is a vocalization/action rather than speech.

    Heuristic: if synset(base, pos='v')[0] is NOT a hyponym of `say.v.07`
    or `speak.v.01`, but DOES have a communicative descendant somewhere
    in its synset list, it's contextual — speech tag only when adjacent.
    """
    if base in TIER_2_VERBS:
        return True
    # Check WordNet
    synsets = wn.synsets(base, pos="v")
    if not synsets:
        return False
    primary = synsets[0]
    primary_name = primary.name()
    # Is the primary sense a clear communicative one?
    say_synsets = {"say.v.07", "say.v.01", "speak.v.01", "tell.v.02"}
    if primary_name in say_synsets:
        return False
    # Walk hypernym chain of primary; if it leads to communication, still
    # tier 1 (most likely)
    for hyper in primary.closure(lambda s: s.hypernyms()):
        if hyper.name() in say_synsets or "communicate" in hyper.name():
            return False
    return True  # Has communicative descendant only via secondary sense


# ===========================================================================
# Main
# ===========================================================================

def main():
    bases = harvest_from_wordnet()
    bases |= TIER_1_SUPPLEMENT
    bases |= TIER_2_VERBS
    bases |= TIER_2_SUPPLEMENT
    bases -= EXCLUDE

    tier_1: Set[str] = set()
    tier_2: Set[str] = set()
    for b in bases:
        # TIER_2 explicit sets WIN over everything (these are curated as
        # contextual — needs quote-adjacency to function as speech tag).
        # Then TIER_1_SUPPLEMENT (curated always-speech).
        # Then WordNet heuristic for anything left.
        if b in TIER_2_VERBS or b in TIER_2_SUPPLEMENT:
            tier_2.add(b)
        elif b in TIER_1_SUPPLEMENT:
            tier_1.add(b)
        elif is_tier_2(b):
            tier_2.add(b)
        else:
            tier_1.add(b)

    # Inflect each base into all its forms.
    tier_1_forms: Set[str] = set()
    for b in tier_1:
        tier_1_forms |= all_forms(b)
    tier_2_forms: Set[str] = set()
    for b in tier_2:
        tier_2_forms |= all_forms(b)

    # Drop forms that are too short (<3 chars) or contain non-letters.
    tier_1_forms = {v for v in tier_1_forms if len(v) >= 3 and v.isalpha()}
    tier_2_forms = {v for v in tier_2_forms if len(v) >= 3 and v.isalpha()}

    # Don't double-list a form that's in both tiers (Tier 1 wins).
    tier_2_forms -= tier_1_forms

    print(f"# Auto-generated by backend/tools/curate_speech_verbs.py")
    print(f"# {len(tier_1)} tier-1 base verbs → {len(tier_1_forms)} inflected forms")
    print(f"# {len(tier_2)} tier-2 base verbs → {len(tier_2_forms)} inflected forms")
    print()

    print("SPEECH_TAG_VERBS = [")
    for v in sorted(tier_1_forms):
        print(f'    "{v}",')
    print("]")
    print()
    print("CONTEXTUAL_TAG_VERBS = [")
    for v in sorted(tier_2_forms):
        print(f'    "{v}",')
    print("]")


if __name__ == "__main__":
    main()
