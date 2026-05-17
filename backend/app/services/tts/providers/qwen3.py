"""
Qwen3-TTS Provider

OpenAI-compatible TTS provider tailored for Qwen3-TTS servers
(e.g. groxaxo/Qwen3-TTS-Openai-Fastapi). Adds first-class support for the
`instructions` field — a free-form natural-language emotion/style prompt
the model conditions on per utterance — and for voice-library clones via
the `clone:` voice prefix.

Endpoint: POST /v1/audio/speech
Built-in voices: GET /v1/voices  (NOTE: voice-library clones are not
listed by upstream — call them by `clone:<ProfileName>`)
"""

import asyncio
import logging
from typing import AsyncIterator, List, Optional

import httpx

from ..base import (
    AudioFormat,
    PcmFormat,
    TTSProviderAPIError,
    TTSProviderBase,
    TTSProviderConfig,
    TTSRequest,
    TTSResponse,
    Voice,
)
from ..registry import TTSProviderRegistry
from app.utils.circuit_breaker import CircuitBreakerOpenError, get_circuit_breaker

logger = logging.getLogger(__name__)


# OpenAI alias voices Qwen exposes for compat — they map to the same 6 of
# the 9 Qwen built-ins, so listing both clutters the picker. We hide the
# OpenAI aliases and surface the Qwen names.
_OPENAI_ALIAS_VOICES = {"alloy", "echo", "fable", "nova", "onyx", "shimmer"}


@TTSProviderRegistry.register("qwen3-tts")
class Qwen3TTSProvider(TTSProviderBase):
    """Qwen3-TTS provider with emotion-prompt and voice-clone support."""

    @property
    def provider_name(self) -> str:
        return "qwen3-tts"

    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [
            AudioFormat.MP3,
            AudioFormat.WAV,
            AudioFormat.OPUS,
            AudioFormat.AAC,
            AudioFormat.FLAC,
            AudioFormat.PCM,
        ]

    @property
    def max_text_length(self) -> int:
        return (self.config.extra_params or {}).get("max_text_length", 2000)

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def streaming_pcm_format(self) -> Optional[PcmFormat]:
        # Qwen3-TTS-12Hz emits 24 kHz mono signed 16-bit PCM; the optimized
        # backend's `streaming` config flushes every ~6 frames (~50 ms),
        # giving sub-second time-to-first-byte (verified ~360 ms in Phase 0).
        return PcmFormat(sample_rate=24000, channels=1, bits_per_sample=16)

    @property
    def supports_pitch_control(self) -> bool:
        return False

    def __init__(self, config: TTSProviderConfig):
        super().__init__(config)
        extras = config.extra_params or {}
        # Qwen accepts "tts-1", "tts-1-hd", "qwen3-tts" interchangeably.
        self._model_name = extras.get("model", "tts-1")
        # Default emotion/style applied when the per-request value is empty.
        # Useful for e.g. a global "warm storyteller cadence" baseline.
        self._default_instructions = extras.get("instructions") or ""
        # Optional language hint passed to the server (else "Auto").
        self._default_language = extras.get("language", "Auto")

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _build_payload(self, request: TTSRequest, stream: bool) -> dict:
        per_req = request.extra_params or {}
        instructions = per_req.get("instructions") or self._default_instructions
        language = per_req.get("language") or self._default_language
        model = per_req.get("model") or self._model_name

        payload: dict = {
            "model": model,
            "input": request.text,
            "voice": request.voice_id,
            "speed": request.speed,
            "response_format": request.format.value,
            "stream": stream,
        }
        if instructions:
            # IMPORTANT: the groxaxo wrapper's Pydantic schema names the
            # field `instruct` (singular), NOT OpenAI's canonical
            # `instructions`. Without `extra="allow"` configured upstream,
            # any field named `instructions` is silently dropped — that
            # was the entire reason "Qwen3 sounds flat" — every emotion
            # we sent was discarded at the wire boundary.
            # See: https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi
            # api/structures/schemas.py field `instruct: Optional[str]`.
            payload["instruct"] = instructions
        if language and language != "Auto":
            payload["language"] = language
        return payload

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.custom_headers:
            headers.update(self.config.custom_headers)
        return headers

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = self._build_payload(request, stream=False)
        logger.info(
            "Qwen3-TTS synthesize: voice=%s instruct=%r format=%s text_len=%d",
            payload["voice"],
            payload.get("instruct", ""),
            payload["response_format"],
            len(request.text),
        )

        circuit = get_circuit_breaker(
            name=f"tts-{self.config.api_url}",
            failure_threshold=3,
            recovery_timeout=30,
            timeout=self.config.timeout,
        )

        async def _make_request():
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(
                    f"{self.config.api_url.rstrip('/')}/v1/audio/speech",
                    headers=self._headers(),
                    json=payload,
                )
                if resp.status_code != 200:
                    raise TTSProviderAPIError(
                        f"Qwen3-TTS API status {resp.status_code}: {resp.text[:300]}"
                    )
                audio = resp.content
                actual_format = self._sniff_format(audio, request.format)
                return TTSResponse(
                    audio_data=audio,
                    format=actual_format,
                    duration=self._estimate_duration(len(audio), actual_format),
                    sample_rate=request.sample_rate,
                    file_size=len(audio),
                    metadata={
                        "provider": self.provider_name,
                        "voice": request.voice_id,
                        "instruct": payload.get("instruct"),
                        "model": payload["model"],
                    },
                )

        try:
            return await circuit.call(_make_request)
        except CircuitBreakerOpenError as e:
            raise TTSProviderAPIError(f"Qwen3-TTS temporarily unavailable: {e}")
        except httpx.TimeoutException:
            raise TTSProviderAPIError(
                f"Qwen3-TTS timeout after {self.config.timeout}s"
            )
        except httpx.RequestError as e:
            raise TTSProviderAPIError(f"Qwen3-TTS request failed: {e}")
        except TTSProviderAPIError:
            raise
        except Exception as e:
            raise TTSProviderAPIError(f"Qwen3-TTS unexpected error: {e}")

    async def synthesize_stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        # Streaming contract from `streaming_pcm_format`: yield raw PCM
        # bytes regardless of `request.format`. Force PCM in the payload —
        # any other response_format would be a complete container that
        # can't be played frame-by-frame.
        payload = self._build_payload(request, stream=True)
        payload["response_format"] = "pcm"
        logger.info(
            "Qwen3-TTS stream: voice=%s instruct=%r format=pcm (forced)",
            payload["voice"],
            payload.get("instruct", ""),
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.config.api_url.rstrip('/')}/v1/audio/speech",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise TTSProviderAPIError(
                            f"Qwen3-TTS stream status {resp.status_code}: "
                            f"{body[:300]!r}"
                        )
                    # 4096-byte PCM batches at 24 kHz mono 16-bit ≈ 85 ms
                    # of audio per WebSocket frame — low enough TTFA, large
                    # enough to keep frame rate sane (~12 frames/sec).
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("Qwen3-TTS stream cancelled — closing httpx connection")
            raise
        except TTSProviderAPIError:
            raise
        except Exception as e:
            raise TTSProviderAPIError(f"Qwen3-TTS streaming failed: {e}")

    # ------------------------------------------------------------------
    # Voice listing / validation
    # ------------------------------------------------------------------

    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        """List available voices from the Qwen3-TTS server.

        Surfaces the built-in Qwen speakers plus any voice-library clones
        listed under `extra_params.clone_voices` (since the upstream
        `/v1/voices` endpoint does not include clones in this build).
        """
        voices: List[Voice] = []
        url = f"{self.config.api_url.rstrip('/')}/v1/voices"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    raw_list = (
                        data.get("voices", []) if isinstance(data, dict) else data
                    )
                    for entry in raw_list:
                        if isinstance(entry, str):
                            vid, name, lang, desc = entry, entry, "en", None
                        else:
                            vid = entry.get("id") or entry.get("name", "")
                            name = entry.get("name", vid)
                            lang = entry.get("language", "en")
                            desc = entry.get("description")
                        if not vid or vid.lower() in _OPENAI_ALIAS_VOICES:
                            continue
                        voices.append(
                            Voice(id=vid, name=name, language=lang, description=desc)
                        )
                else:
                    logger.warning(
                        "Qwen3-TTS /v1/voices returned %s", resp.status_code
                    )
        except Exception as e:
            logger.warning("Qwen3-TTS voice fetch failed: %s", e)

        # Manually configured voice-library clones — only added when the
        # upstream /v1/voices listing didn't already include them. (Newer
        # builds of the optimized backend do list `clone:Foo` entries.)
        existing_ids = {v.id for v in voices}
        for clone in (self.config.extra_params or {}).get("clone_voices", []) or []:
            cid = clone if clone.startswith("clone:") else f"clone:{clone}"
            if cid in existing_ids:
                continue
            voices.append(
                Voice(
                    id=cid,
                    name=cid,
                    language="en",
                    description=f"Voice library clone: {cid[6:]}",
                )
            )

        if language:
            voices = [v for v in voices if language.lower() in (v.language or "").lower()]
        return voices

    async def validate_voice(self, voice_id: str) -> bool:
        # Always accept clone:* — the server resolves them lazily and the
        # clone list isn't reliably enumerable via /v1/voices.
        if voice_id.startswith("clone:"):
            return True
        voices = await self.get_voices()
        return any(v.id == voice_id for v in voices)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.config.api_url.rstrip('/')}/health",
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return False
                data = resp.json()
                return data.get("status") == "healthy"
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sniff_format(audio: bytes, requested: AudioFormat) -> AudioFormat:
        if len(audio) < 12:
            return requested
        if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
            return AudioFormat.WAV
        if audio[:3] == b"ID3" or (audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0):
            return AudioFormat.MP3
        if audio[:4] == b"OggS":
            return AudioFormat.OGG
        if audio[4:8] == b"ftyp":
            return AudioFormat.AAC
        if audio[:4] == b"fLaC":
            return AudioFormat.FLAC
        return requested

    @staticmethod
    def _estimate_duration(file_size: int, fmt: AudioFormat) -> float:
        # Qwen3-TTS produces 24kHz mono. MP3 default ~160kbps; PCM is 16-bit.
        bitrates = {
            AudioFormat.MP3: 160000,
            AudioFormat.AAC: 96000,
            AudioFormat.OPUS: 64000,
            AudioFormat.FLAC: 384000,
            AudioFormat.WAV: 384000,
            AudioFormat.PCM: 384000,
            AudioFormat.OGG: 96000,
        }
        return (file_size * 8) / bitrates.get(fmt, 160000)
