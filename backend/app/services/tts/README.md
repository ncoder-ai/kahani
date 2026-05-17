# Kahani TTS Subsystem — Architecture & Provider Authoring Guide

This subsystem turns a generated scene into spoken audio with optional
per-character voices and per-utterance emotion. It's designed for
**modularity**: adding a new TTS provider should be a single new file
in `providers/`, not a refactor.

---

## File map

```
backend/app/services/tts/
├── base.py                       # TTSProviderBase + capability flags + abstract methods
├── registry.py                   # @TTSProviderRegistry.register decorator
├── factory.py                    # build provider instances from user TTSSettings
├── tts_service.py                # high-level helpers
├── text_chunker.py               # legacy single-voice chunker (used when no extraction)
├── multi_speaker_script.py       # generic Speaker N: script builder + per-format config
├── emotion_to_tag.py             # phrase → inline tag dispatcher (Bark/Orpheus/Turbo)
├── segment_extraction_v2.py      # deterministic regex spans + LLM polish
└── providers/
    ├── __init__.py               # imports all providers (registers them)
    ├── openai_compatible.py
    ├── chatterbox.py
    ├── kokoro.py
    ├── orpheus.py
    ├── vibevoice.py              # multi-speaker streaming exemplar
    ├── qwen3.py                  # PCM streaming exemplar
    └── indextts.py               # natural-language emotion exemplar
```

The dispatcher lives in `backend/app/routers/tts.py` (`generate_and_stream_chunks`).

---

## What the subsystem already does for you

Every provider gets these for free:

| Concern | Where it lives | Notes |
|---|---|---|
| Scene → segments (`{speaker, text, emotion}`) | `segment_extraction_v2.py` | Cached on `SceneVariant.tts_segments` per variant; only re-runs on cache miss |
| Per-character voice mapping | `Story.tts_character_voices[provider_type]` | Looked up at dispatch time by lowercased speaker name |
| Decision tree (multi-speaker → streaming → block → chunked) | `routers/tts.py` | Branches purely on capability flags |
| WebSocket frame protocol (`stream_start` / `frame` / `stream_end`) | `routers/tts.py:_consume_pcm_stream` | Reused unchanged |
| Asterisk / quote stripping for chunked dispatch | `routers/tts.py` (chunked path) | So providers don't read markup aloud |
| User toggles (use_streaming, use_whole_scene, use_multi_speaker) | Frontend Voice Settings | Flow through automatically |
| Voice list endpoint (`GET /api/tts/voices`) | `routers/tts.py` | Calls provider's `get_voices()` |

**You should never re-implement any of these in a provider.** If you need to,
flag it — it's probably a sign the abstraction needs adjustment.

---

## Capability tiers

Most providers fit one of four tiers. Pick the one that matches the
underlying model's capabilities and override only the relevant flags +
methods.

### Tier 1 — Single-utterance, no streaming, no emotion (e.g. Kokoro)

The simplest provider. Just synthesize text → audio file, return it.
Used when the underlying model has no streaming endpoint and no emotion
control beyond voice selection.

**Flags:** all defaults False. No overrides needed.
**Methods:** `synthesize()`.

### Tier 2 — PCM streaming (e.g. Qwen3-TTS, IndexTTS)

The model can emit PCM audio frames as it generates. Sub-second TTFB
when the user has `use_streaming` on. Falls through to chunked when off.

**Flags:** `supports_streaming=True`, `streaming_pcm_format=PcmFormat(...)`.
**Methods:** `synthesize()`, `synthesize_stream()` (yields raw PCM bytes
matching `streaming_pcm_format`).

### Tier 3 — Inline-tag emotion (e.g. Chatterbox Turbo, Orpheus, Bark)

The model takes inline markup tokens (`[laugh]`, `<sigh>`, `[whispering]`)
within the input text. Use the shared `emotion_to_tag` utility to map
LLM emotion phrases to your provider's tag vocabulary.

**Flags:** Tier 2 + nothing extra.
**Methods:** Tier 2, with `_build_payload` injecting tag prefix.

### Tier 4 — Native multi-speaker script (e.g. VibeVoice, F5-TTS)

The model accepts a multi-speaker script (`Speaker 0: ...\nSpeaker 1: ...`)
and produces a single cohesive audio stream with seamless turn-taking.
Use the shared `multi_speaker_script` utility.

**Flags:** Tier 2 + `supports_multi_speaker_script=True`,
`supports_multi_speaker_streaming=True` (if the multi-speaker call can
also stream), `max_speakers_per_call=N`.
**Methods:** Tier 2 + `synthesize_multi_speaker_block()`,
`synthesize_multi_speaker_stream()`.

---

## Dispatch decision tree

When the user plays a scene, the dispatcher in `routers/tts.py` decides
which provider method to call based on user settings + provider flags:

```
1. is_progressive (user toggle "Progressive narration"):
   ├─ False → Tier 1 path: provider.synthesize() over whole scene → block
   └─ True  → continue
2. use_streaming AND provider.supports_streaming:
   └─ Tier 2 path: provider.synthesize_stream() over whole scene
      ├─ success → return
      └─ fail → fall through to step 3
3. use_whole_scene AND not multi_speaker_taking_priority:
   └─ Tier 1-as-block path: synthesize() over whole scene → return
4. use_multi_speaker AND provider.supports_multi_speaker_streaming
   AND scene has segments AND voice map covers speakers:
   └─ Tier 4 path: provider.synthesize_multi_speaker_stream() with
      build_script(segments, voice_map, FORMAT)
      ├─ success → return
      └─ fail → fall through to chunked
5. Else → CHUNKED path: walk segments, one synthesize_stream() call per
   segment with extra_params["instructions"] = segment["emotion"].
   This is where Tier 3 inline-tag mapping kicks in (in _build_payload).
```

Multi-speaker takes priority over `use_streaming` whenever both are on
and the provider supports both — multi-speaker IS streaming, plus per-
character voices.

---

## Recipe: add a new provider in 4 steps

1. **Create the provider file** at `backend/app/services/tts/providers/myprovider.py`
2. **Implement the methods** appropriate for your tier (see worked
   examples below)
3. **Add the import** to `providers/__init__.py`:
   ```python
   from .myprovider import MyProvider
   __all__ = [..., "MyProvider"]
   ```
4. **Test** — see the testing section at the end

That's it. The dispatcher, segment extraction, voice mapping, frontend
toggles, settings persistence — all of it just works because the
provider declared its capability flags. **No changes outside `providers/`.**

---

## Capability flag reference

All declared on `TTSProviderBase` with safe defaults. Override only the
ones that apply to your provider.

| Flag | Default | Override when |
|---|---|---|
| `supports_streaming` | False | Provider can yield PCM frames during generation |
| `streaming_pcm_format` | None | Set to `PcmFormat(sample_rate, channels, bits_per_sample)` when streaming |
| `supports_multi_speaker_script` | False | Provider takes a script with multiple speaker turns in one call |
| `supports_multi_speaker_streaming` | False | The multi-speaker call also streams (implies `supports_multi_speaker_script`) |
| `max_speakers_per_call` | 1 | Hard cap on distinct speakers in one multi-speaker call (VibeVoice = 4) |
| `supports_pitch_control` | (abstract) | Required to declare; usually False |
| `supported_formats` | (abstract) | List of `AudioFormat` enums the provider accepts |
| `max_text_length` | (abstract) | Provider's per-call text cap (used for warnings, not enforcement) |

---

## Shared utilities

### `emotion_to_tag.py` — for Tier 3 inline-tag providers

Maps LLM emotion phrases (e.g. `"soft whisper, breathless"`) to provider-
native inline tags via a small per-provider mapping table.

**Canonical intents** (provider-agnostic, defined once in `INTENT_TRIGGERS`):
`whisper, shout, laugh, sigh, gasp, groan, cough, sob, yawn, sniffle,
stammer, angry, happy, sad, fear, surprised, sarcastic, dramatic,
playful, intimate, urgent`.

**Usage in provider's `_build_payload`:**
```python
from ..emotion_to_tag import select_tag

# Provider-specific tag table — declare at module level. Order = priority.
MY_TAGS = {
    "whisper":   "[whispering]",
    "laugh":     "[laugh]",
    "sigh":      "[sigh]",
    "angry":     "[angry]",
    "happy":     "[happy]",
    "sad":       "[crying]",
    "surprised": "[surprised]",
}

def _build_payload(self, request):
    tag = select_tag(
        (request.extra_params or {}).get("instructions"),
        MY_TAGS,
    )
    text = f"{tag} {request.text}".strip() if tag else request.text
    return {"input": text, "voice": request.voice_id, ...}
```

The phrase parser does substring matching against `INTENT_TRIGGERS`. If
no detected intent has a tag in your table, `select_tag` returns `""`
and the dialogue plays without markup — which is correct fallback.

### `multi_speaker_script.py` — for Tier 4 native-script providers

Generic script builder driven by a per-provider `ScriptFormat` config.

**Define your provider's format** at the top of the provider module:
```python
from ..multi_speaker_script import ScriptFormat, passthrough_text_formatter

MY_FORMAT = ScriptFormat(
    name="my-provider",
    line_template="Speaker {slot}: {text}",   # or "[{slot}] {text}", etc.
    text_formatter=passthrough_text_formatter, # or your own (text, kind) → str
    payload_builder=lambda pairs: [
        {"id": s, "voice": v} for s, v in pairs
    ],  # whatever JSON shape your API expects
    slot_namer=None,                           # numeric slots (default)
)
```

For named-slot providers (F5-TTS uses `[main]`, `[town]`, etc.), set
`slot_namer=lambda slot_int, speaker_name: speaker_name.lower().replace(" ", "_")`.

**Use in `synthesize_multi_speaker_stream`:**
```python
from ..multi_speaker_script import build_script

async def synthesize_multi_speaker_stream(self, request):
    # Caller (dispatcher) passes pre-built script + payload via extra_params
    # — see VibeVoiceProvider for the pattern. Or build it here from
    # `request.segments` if the request object carries them.
    script = (request.extra_params or {}).get("script", "")
    speakers = (request.extra_params or {}).get("speakers", [])
    # ... POST to your API, parse response, yield PCM frames
```

The dispatcher in `routers/tts.py` is the one that calls
`build_script(...)` — your provider just consumes the resulting script.
See `VibeVoiceProvider._multi_speaker_payload` for the canonical pattern.

### `segment_extraction_v2.py` — provider-agnostic, called by dispatcher

You don't call this directly from a provider. The dispatcher runs it
once per scene and caches the result on `SceneVariant.tts_segments`.
Your provider receives segments via `request.extra_params` (multi-speaker
path) or one-segment-at-a-time as `request.text` (chunked path).

#### Why segment extraction has scheduling priority

The same kobold/llama.cpp instance that serves Ministral-class extraction
LLMs processes ONE HTTP request at a time. When a scene finishes, several
post-scene tasks fire as `asyncio.create_task` (TTS segment polish, inline
contradiction check, plot extraction, chronicle, working memory, NPC
tracking). Without coordination, they all hit kobold concurrently and
queue serially — and TTS prep ends up sitting behind a slow extraction.
The user's first play tap goes silent until the queue drains.

`scene_endpoints.py` solves this with `_defer_until_tts_segment_done(variant_id, coro)`.
All non-TTS post-scene tasks are wrapped in this helper, which awaits the
TTS extraction's in-flight `asyncio.Event` (registered in
`_in_flight[variant_id]`) before letting the wrapped coroutine run.

When you add a new post-scene background task, **always** wrap it:

```python
asyncio.create_task(_defer_until_tts_segment_done(
    variant.id,
    my_new_extraction_in_background(...),
))
```

The wait is bounded (90s timeout) and zero-cost when no TTS extraction
is registered (e.g. TTS disabled).

---

## Worked examples

### Tier 1 — Kokoro pattern

```python
@TTSProviderRegistry.register("kokoro")
class KokoroProvider(TTSProviderBase):
    @property
    def provider_name(self): return "kokoro"
    @property
    def supported_formats(self): return [AudioFormat.MP3, AudioFormat.WAV]
    @property
    def max_text_length(self): return 5000
    @property
    def supports_streaming(self): return False
    @property
    def supports_pitch_control(self): return False

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        # POST to your TTS endpoint, return TTSResponse
        ...

    async def synthesize_stream(self, request):
        # Required by abstract base but won't be called when supports_streaming=False.
        # Default impl yields the full audio as one chunk.
        response = await self.synthesize(request)
        yield response.audio_data

    async def get_voices(self, language=None): ...
    async def validate_voice(self, voice_id): ...
```

### Tier 2 — Qwen3 / IndexTTS pattern (PCM streaming)

```python
@TTSProviderRegistry.register("myprovider")
class MyProvider(TTSProviderBase):
    @property
    def supports_streaming(self): return True
    @property
    def streaming_pcm_format(self):
        return PcmFormat(sample_rate=24000, channels=1, bits_per_sample=16)

    async def synthesize_stream(self, request) -> AsyncIterator[bytes]:
        payload = self._build_payload(request, stream=True)
        async with httpx.AsyncClient(timeout=self.config.timeout * 5) as client:
            async with client.stream("POST", url, json=payload) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk   # raw PCM s16le bytes
```

### Tier 3 — Chatterbox Turbo pattern (inline tags)

```python
from ..emotion_to_tag import select_tag

TURBO_TAGS = {
    "whisper":   "[whispering]",
    "laugh":     "[laugh]",
    "sigh":      "[sigh]",
    "gasp":      "[gasp]",
    "angry":     "[angry]",
    "happy":     "[happy]",
    "sad":       "[crying]",
    "surprised": "[surprised]",
    "sarcastic": "[sarcastic]",
    "dramatic":  "[dramatic]",
}

class TurboProvider(TTSProviderBase):
    # Tier 2 flags...
    def _build_payload(self, request, stream):
        tag = select_tag(
            (request.extra_params or {}).get("instructions"),
            TURBO_TAGS,
        )
        text = f"{tag} {request.text}".strip() if tag else request.text
        return {"input": text, "voice": request.voice_id, ...}
```

### Tier 4 — VibeVoice pattern (native multi-speaker streaming)

```python
from ..multi_speaker_script import (
    ScriptFormat, vibevoice_text_formatter, vibevoice_payload_builder
)

VIBEVOICE_FORMAT = ScriptFormat(
    name="vibevoice",
    line_template="Speaker {slot}: {text}",
    text_formatter=vibevoice_text_formatter,
    payload_builder=vibevoice_payload_builder,
)

class VibeVoiceProvider(TTSProviderBase):
    @property
    def supports_multi_speaker_script(self): return True
    @property
    def supports_multi_speaker_streaming(self): return True
    @property
    def max_speakers_per_call(self): return 4

    async def synthesize_multi_speaker_stream(self, request):
        # The dispatcher pre-built the script via build_script(VIBEVOICE_FORMAT)
        # and passed it via extra_params:
        script = (request.extra_params or {}).get("script", "")
        speakers = (request.extra_params or {}).get("speakers", [])
        # POST to your multi-speaker endpoint, stream PCM, yield bytes
```

---

## Testing a new provider

Five-step smoke test:

1. **Provider registers**:
   ```bash
   docker exec kahani-backend python3 -c "
   from app.services.tts.registry import TTSProviderRegistry
   print(TTSProviderRegistry.list_providers())
   "
   ```
   Your name should appear.

2. **Voice listing works**:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     'http://localhost:9876/api/tts/voices?provider_type=myprovider&api_url=...'
   ```

3. **Direct synthesis** (smoke test from inside backend container):
   ```python
   from app.services.tts.providers import MyProvider
   from app.services.tts.base import TTSProviderConfig, TTSRequest, AudioFormat
   p = MyProvider(TTSProviderConfig(api_url='...', api_key=''))
   req = TTSRequest(text='Hello', voice_id='...', format=AudioFormat.MP3)
   resp = await p.synthesize(req)
   print(resp.file_size, resp.duration)
   ```

4. **Streaming test** (Tier 2+):
   ```python
   t0 = time.monotonic(); ttfb = None; total = 0
   async for chunk in p.synthesize_stream(req):
       if ttfb is None: ttfb = time.monotonic() - t0
       total += len(chunk)
   print(f"ttfb={ttfb:.2f}s, bytes={total}")
   ```
   For Tier 2, expect TTFB < 5s. If close to total elapsed, the streaming
   isn't actually frame-by-frame.

5. **End-to-end via Kahani**: configure your provider in Settings → Voice,
   pick a scene, hit play. Check backend logs for the dispatch path
   (`[GEN]` lines). Verify audio plays.

---

## Common gotchas

- **Provider auto-registers via `@TTSProviderRegistry.register("name")`** but
  ONLY if the module is imported. Always add the `from .myprovider import ...`
  line to `providers/__init__.py`.
- **`extra_params` on `TTSRequest` carries per-segment data:** the
  dispatcher puts `extra_params["instructions"] = segment["emotion"]`
  for chunked path. Your provider's `_build_payload` should pick this up
  and route to the provider's emotion channel (inline tag, instruct field,
  emo_text field, etc.).
- **`response_format` for streaming should always be `pcm`** — providers
  reject streaming MP3/Opus because per-chunk container headers don't
  concatenate cleanly. The dispatcher knows this; just make sure your
  `_build_payload(stream=True)` forces `response_format="pcm"`.
- **Voice mapping is per-provider** under `Story.tts_character_voices[provider_type]`.
  Voice IDs differ between servers (Qwen uses `clone:Name`, VibeVoice
  uses bare names). Don't try to share voice IDs across providers.
- **`api_key` is required (even if empty)** in `TTSProviderConfig` — pass
  `api_key=""` for self-hosted servers without auth.
- **Don't try to enforce `max_text_length` in the provider.** The
  segmenter has already chunked the scene appropriately. Your `max_text_length`
  is informational only.
- **Streaming response timeout:** multi-segment scenes can take minutes
  to render end-to-end. Use `max(self.config.timeout * 5, 240)` for the
  httpx client when streaming.
- **In-flight slot registration must come before any `await sleep` in
  `extract_and_cache_for_variant()`.** That function opens with a 300ms
  delay so the SceneVariant insert becomes visible across DB sessions; if
  the slot is registered AFTER that sleep, deferred non-TTS tasks (see
  segment_extraction_v2 section above) call `wait_for_in_flight` while
  the slot doesn't exist yet, return immediately, and race past the gate.
  Register first, sleep second.

---

## When you need to extend the framework itself

If your new provider doesn't fit any of the four tiers cleanly, the
abstraction needs adjustment, not a workaround. Likely places to touch:

- **New capability**: add a flag on `base.py` with a sensible default,
  add the dispatch branch in `routers/tts.py`.
- **New emotion channel**: extend `INTENT_TRIGGERS` in `emotion_to_tag.py`
  if the new intent applies generally; or add a custom `text_formatter`
  in `multi_speaker_script.py` for provider-specific text munging.
- **New script format**: add a constant `ScriptFormat` to your provider
  module; the generic `build_script()` will work as long as
  `line_template`, `text_formatter`, and `payload_builder` are supplied.

Don't add provider-specific logic to the dispatcher or to shared utilities
unless the same pattern appears in two or more providers. Keep the
shared layer narrow.
