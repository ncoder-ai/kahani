"""Tests for the multi-speaker script builder.

Focus: regression guard for the user-facing behavior that characters left
on "use default voice" in the per-story voice map must NOT bail the builder
to chunked fallback. They should be silently coerced to the narrator slot
(and thus narrator voice) so a single multi-speaker call handles the
whole scene.

Previously, any speaker missing from `voice_map` made `build_script`
return None, which sent the dispatcher down a 27-call-per-scene path that
took ~25s per chunk on VibeVoice.
"""
import importlib.util
import sys
from pathlib import Path

# Import the module directly from its file path. Going through
# `from app.services.tts...` triggers `app.services.__init__` → LLM stack
# → pydantic Settings → JWT_SECRET_KEY env var requirement, which we
# don't need for a pure-Python AST/string test.
_MODULE_PATH = Path(__file__).resolve().parent.parent / "app" / "services" / "tts" / "multi_speaker_script.py"
_spec = importlib.util.spec_from_file_location("multi_speaker_script", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
# Register BEFORE exec_module so @dataclass(frozen=True) can find the module
# via cls.__module__ → sys.modules lookup during decoration.
sys.modules["multi_speaker_script"] = _module
_spec.loader.exec_module(_module)

build_vibevoice_script = _module.build_vibevoice_script
_collapse_unmapped_to_narrator = _module._collapse_unmapped_to_narrator
NARRATOR_KEY = _module.NARRATOR_KEY


def _segs(*pairs):
    return [{"speaker": sp, "text": t, "kind": "narrator" if sp == NARRATOR_KEY else "dialogue"} for sp, t in pairs]


def test_unmapped_speakers_collapse_to_narrator():
    segments = _segs(
        ("narrator", "Mira walked in."),
        ("Mira", "Hello."),
        ("Caleb", "Hi back."),
        ("Eve", "And me."),
    )
    voice_map = {"narrator": "v_narr", "Mira": "v_mira"}  # Caleb + Eve unmapped
    out, collapsed = _collapse_unmapped_to_narrator(segments, voice_map)
    assert collapsed == ["Caleb", "Eve"]
    assert [s["speaker"] for s in out] == ["narrator", "Mira", "narrator", "narrator"]
    # original list untouched
    assert segments[2]["speaker"] == "Caleb"


def test_fully_mapped_no_collapse():
    segments = _segs(("narrator", "X."), ("Mira", "Y."))
    voice_map = {"narrator": "vn", "Mira": "vm"}
    out, collapsed = _collapse_unmapped_to_narrator(segments, voice_map)
    assert collapsed == []
    assert out == segments  # identity-preserving when nothing to do


def test_voicemap_lookup_is_case_insensitive():
    segments = _segs(("narrator", "X."), ("Caleb", "Hello."))
    voice_map = {"narrator": "vn", "caleb": "vc"}  # lowercase, like dispatcher passes
    _, collapsed = _collapse_unmapped_to_narrator(segments, voice_map)
    assert collapsed == []  # Caleb matches voice_map["caleb"]


def test_build_vibevoice_script_partial_voices_no_bail():
    """The regression case: user leaves some characters on default in UI.
    Must NOT return None; must produce a working script."""
    segments = _segs(
        ("narrator", "Mira looked at Caleb."),
        ("Caleb", "Why don't you join us?"),
        ("Mira", "Okay."),
        ("Eve", "Just do it."),  # Eve has no voice
    )
    voice_map = {
        "narrator": "stephen_fry",
        "mira": "voice_a",
        # caleb, eve intentionally absent
    }
    result = build_vibevoice_script(segments=segments, voice_map=voice_map, max_speakers=4)
    assert result is not None, "must NOT fall back to chunked when voices are missing"
    script_text, payload, slot_map, overflow = result
    # Mira keeps her own slot; Caleb + Eve share narrator's slot
    assert "Mira" in slot_map
    assert slot_map.get("Caleb", slot_map["narrator"]) == slot_map["narrator"]
    assert slot_map.get("Eve", slot_map["narrator"]) == slot_map["narrator"]
    # overflow is for cap-exceeded speakers, not default-voice ones
    assert overflow == []
    # payload has 2 distinct speakers (narrator + Mira), Caleb/Eve voices not declared
    voices_in_payload = {s["voice_preset"] for s in payload}
    assert voices_in_payload == {"stephen_fry", "voice_a"}


def test_build_vibevoice_script_all_mapped_unchanged():
    segments = _segs(("narrator", "X."), ("Mira", "Hi."), ("Caleb", "Hi back."))
    voice_map = {"narrator": "vn", "mira": "vm", "caleb": "vc"}
    result = build_vibevoice_script(segments=segments, voice_map=voice_map, max_speakers=4)
    assert result is not None
    script, payload, slot_map, overflow = result
    assert overflow == []
    assert set(slot_map) == {"narrator", "Mira", "Caleb"}
    assert len(payload) == 3


def test_build_vibevoice_script_returns_none_only_on_empty():
    """Sanity: with empty segments, still None."""
    assert build_vibevoice_script(segments=[], voice_map={"narrator": "vn"}) is None
