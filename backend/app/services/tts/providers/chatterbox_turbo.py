"""Chatterbox Turbo provider — OpenAI-compatible TTS with inline bracket tags.

Resemble AI's Chatterbox Turbo (rsxdalv/chatterbox-turbo / `ResembleAI/
chatterbox-turbo` on HuggingFace) supports inline emotion + paralinguistic
markers via 19 special tokens defined in the model's `added_tokens.json`:

  Paralinguistic: [chuckle] [clear throat] [cough] [gasp] [groan]
                  [laugh] [shush] [sigh] [sniff] [whispering]
  Emotion:        [angry] [crying] [fear] [happy] [sarcastic]
                  [surprised] [dramatic]
  Style:          [narration] [advertisement]

Tags are tokenized as single tokens by the model — placing one inline
at the start of the input text shapes the delivery of that utterance.
We use the shared `emotion_to_tag` utility to map the LLM's emotion
phrases (e.g. "soft whisper, breathless") to the highest-priority tag
in our table.

API surface: OpenAI-compatible POST /v1/audio/speech, same as the
original Chatterbox provider but routed through the per-utterance
chunked dispatch with inline-tag emotion injection. Supports PCM
streaming on the same endpoint when the underlying server is built
with streaming enabled (recent chatterbox-tts versions).
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional

import httpx

from ..base import (
    AudioFormat,
    PcmFormat,
    TTSProviderAPIError,
    TTSProviderBase,
    TTSRequest,
    TTSResponse,
    Voice,
)
from ..emotion_to_tag import select_tag
from ..registry import TTSProviderRegistry

logger = logging.getLogger(__name__)


# Per-provider tag table — order = priority. Paralinguistic sounds
# (whisper, laugh, sigh, gasp, etc.) come before broad emotional tags
# (angry, sad, dramatic) so a phrase like "soft whisper, intimate" maps
# to [whispering], not [happy] or [dramatic].
TURBO_TAGS: Dict[str, str] = {
    # Paralinguistic — most specific, highest priority
    "whisper":   "[whispering]",
    "laugh":     "[laugh]",
    "sigh":      "[sigh]",
    "gasp":      "[gasp]",
    "groan":     "[groan]",
    "cough":     "[cough]",
    "sniffle":   "[sniff]",
    # Emotional — broader, lower priority
    "angry":     "[angry]",
    "sad":       "[crying]",
    "fear":      "[fear]",
    "surprised": "[surprised]",
    "happy":     "[happy]",
    "sarcastic": "[sarcastic]",
    "dramatic":  "[dramatic]",
}

# Server output shape (chatterbox-tts emits 24 kHz mono signed 16-bit PCM
# when streaming with response_format=pcm).
SAMPLE_RATE = 24000


@TTSProviderRegistry.register("chatterbox-turbo")
class ChatterboxTurboProvider(TTSProviderBase):
    """Tier 3: per-utterance chunked + PCM streaming + inline-tag emotion."""

    @property
    def provider_name(self) -> str:
        return "chatterbox-turbo"

    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.MP3, AudioFormat.WAV, AudioFormat.PCM]

    @property
    def max_text_length(self) -> int:
        return (self.config.extra_params or {}).get("max_text_length", 3000)

    @property
    def supports_streaming(self) -> bool:
        # Wrapper does "fake streaming" — generates the full utterance
        # blocking, then yields it as PCM chunks over chunked transfer.
        # No TTFB benefit, but lets the dispatch use the WebSocket frame
        # path uniformly (raw PCM vs base64 MP3). When upstream adds a
        # native generator we get real streaming for free.
        return True

    @property
    def streaming_pcm_format(self) -> Optional[PcmFormat]:
        return PcmFormat(sample_rate=SAMPLE_RATE, channels=1, bits_per_sample=16)

    @property
    def supports_pitch_control(self) -> bool:
        return False

    # -------- helpers --------

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.config.api_key:
            h["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.custom_headers:
            h.update(self.config.custom_headers)
        return h

    def _input_with_tag(self, text: str, instructions: Optional[str]) -> str:
        """Prepend an emotion tag inline if the LLM phrase maps to one
        of the 19 supported Turbo tags. Returns the original text if
        no intent detected — the dialogue plays unstyled, which is the
        right fallback (no need to fail the call).
        """
        tag = select_tag(instructions, TURBO_TAGS)
        if tag:
            return f"{tag} {text}".strip()
        return text

    def _build_payload(self, request: TTSRequest, stream: bool) -> dict:
        per_req = request.extra_params or {}
        defaults = self.config.extra_params or {}
        text = self._input_with_tag(request.text, per_req.get("instructions"))
        return {
            "model": per_req.get("model") or defaults.get("model", "tts-1"),
            "input": text,
            "voice": request.voice_id,
            "speed": request.speed,
            # PCM for streaming (browser-friendly, no decoder); request.format for blocking.
            "response_format": ("pcm" if stream else request.format.value),
            "stream": stream,
            # Pass through Chatterbox sampling knobs if configured.
            **{
                k: per_req.get(k, defaults.get(k))
                for k in ("exaggeration", "cfg_weight", "temperature")
                if (per_req.get(k, defaults.get(k)) is not None)
            },
        }

    # -------- synthesis --------

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = self._build_payload(request, stream=False)
        url = self.config.api_url.rstrip("/") + "/v1/audio/speech"
        logger.info(
            "ChatterboxTurbo synthesize: voice=%s text_len=%d format=%s instructions=%r tag=%s",
            request.voice_id, len(request.text), payload["response_format"],
            (request.extra_params or {}).get("instructions", ""),
            payload["input"][: payload["input"].find("]") + 1] if "]" in payload["input"] else "",
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                r = await client.post(url, headers=self._headers(), json=payload)
                if r.status_code != 200:
                    raise TTSProviderAPIError(
                        f"ChatterboxTurbo {r.status_code}: {r.text[:300]}"
                    )
                audio = r.content
            return TTSResponse(
                audio_data=audio,
                format=request.format,
                duration=0.0,
                sample_rate=SAMPLE_RATE,
                file_size=len(audio),
                metadata={"provider": self.provider_name, "voice": request.voice_id},
            )
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"ChatterboxTurbo request failed: {e}")

    async def synthesize_stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        payload = self._build_payload(request, stream=True)
        url = self.config.api_url.rstrip("/") + "/v1/audio/speech"
        logger.info(
            "ChatterboxTurbo stream: voice=%s text_len=%d (forcing pcm)",
            request.voice_id, len(request.text),
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout * 5) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise TTSProviderAPIError(
                            f"ChatterboxTurbo stream {resp.status_code}: {body[:300]!r}"
                        )
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("ChatterboxTurbo stream cancelled — closing httpx connection")
            raise
        except TTSProviderAPIError:
            raise
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"ChatterboxTurbo stream failed: {e}")

    # -------- voice listing --------

    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        url = self.config.api_url.rstrip("/") + "/v1/audio/voices"
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                r = await client.get(url, headers=self._headers())
                if r.status_code != 200:
                    logger.warning("ChatterboxTurbo /v1/audio/voices %s", r.status_code)
                    return []
                data = r.json()
        except Exception as e:
            logger.warning("ChatterboxTurbo voice list failed: %s", e)
            return []
        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = data.get("voices") if isinstance(data, dict) else []
        out: List[Voice] = []
        for v in items or []:
            if isinstance(v, str):
                vid, name = v, v
            else:
                vid = v.get("id") or v.get("name") or ""
                name = v.get("name") or vid
            if not vid:
                continue
            lang = "en"
            if "-" in vid and len(vid.split("-", 1)[0]) == 2:
                lang = vid.split("-", 1)[0]
            out.append(Voice(id=vid, name=name, language=lang,
                             description=f"ChatterboxTurbo voice: {vid}"))
        if language:
            out = [v for v in out if v.language.lower() == language.lower()]
        return out

    async def validate_voice(self, voice_id: str) -> bool:
        try:
            voices = await self.get_voices()
            return any(v.id == voice_id for v in voices)
        except Exception:
            return False

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    self.config.api_url.rstrip("/") + "/health",
                    headers=self._headers(),
                )
                return r.status_code == 200
        except Exception:
            return False
