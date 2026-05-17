"""
IndexTTS2 Provider

OpenAI-compatible TTS provider for an IndexTTS2 server (the FastAPI
wrapper at /v1/audio/speech). IndexTTS2's strength is decoupled timbre
+ emotion: the `voice` clip controls who's speaking, and a separate
emotion signal — natural-language `instructions` text, or an emotion
reference clip, or an 8-dim mood vector — controls how they say it.

Endpoint: POST /v1/audio/speech
Voice listing: GET /v1/voices  (returns clips found in the server's
voice library mount; no built-in speaker presets).

Voices are referenced by bare name (`morgan_freeman_cc3`) or `clone:`
prefix (`clone:morgan_freeman_cc3`) — both resolve to the same file on
the server. Streaming: when `stream:true, response_format:"pcm"` is
sent, the wrapper uses `tts.infer_generator(stream_return=True)` and
chunked-transfers raw int16 PCM (22050 Hz mono) as each text segment
finishes decoding. Per-segment latency, not per-frame — TTFB is roughly
single-segment-render time, ~5-15s for typical scene text.
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


@TTSProviderRegistry.register("indextts")
class IndexTTSProvider(TTSProviderBase):
    """IndexTTS2 provider with decoupled voice + emotion control."""

    @property
    def provider_name(self) -> str:
        return "indextts"

    @property
    def supported_formats(self) -> List[AudioFormat]:
        # The wrapper currently re-encodes wav → mp3/flac via ffmpeg.
        return [AudioFormat.MP3, AudioFormat.WAV, AudioFormat.FLAC]

    @property
    def max_text_length(self) -> int:
        return (self.config.extra_params or {}).get("max_text_length", 2000)

    @property
    def supports_streaming(self) -> bool:
        # The wrapper exposes `stream:true, response_format:pcm` on
        # /v1/audio/speech which uses IndexTTS's `infer_generator(
        # stream_return=True)` to yield raw PCM as each text segment is
        # decoded. NOT frame-by-frame — IndexTTS yields per-segment, so
        # TTFB is one-segment-render time (~5-15s for typical scene
        # text), not sub-second like Qwen3/VibeVoice. Better than waiting
        # for the whole file but worse than true frame streaming.
        return True

    @property
    def streaming_pcm_format(self) -> Optional[PcmFormat]:
        # IndexTTS produces 22050 Hz mono int16 (hardcoded in
        # indextts/infer_v2.py:527). Wrapper streams it as raw bytes.
        return PcmFormat(sample_rate=22050, channels=1, bits_per_sample=16)

    @property
    def supports_pitch_control(self) -> bool:
        return False

    def __init__(self, config: TTSProviderConfig):
        super().__init__(config)
        extras = config.extra_params or {}
        # Server accepts any model string; included for OpenAI-compat clients.
        self._model_name = extras.get("model", "tts-1")
        # Default natural-language emotion applied when per-request `instructions`
        # is empty. e.g. "warm storyteller cadence, neutral tone".
        self._default_instructions = extras.get("instructions") or ""
        # Optional default emotion-reference clip name (looked up in the same
        # /voices mount as the speaker clip).
        self._default_emo_voice = extras.get("emo_voice") or None
        # Default emotion intensity (0..1). The IndexTTS Python `infer()`
        # method's own default is 1.0, BUT the upstream README explicitly
        # recommends 0.6-0.65 for natural delivery in text-emotion mode
        # (use_emo_text=True). The webui slider also defaults to 0.65.
        # 1.0 + a strong text reading is the recipe for "shouted everything"
        # — exactly what we observed in our earlier A/B tests.
        self._default_emo_alpha = extras.get("emo_alpha", 0.65)

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _build_payload(self, request: TTSRequest) -> dict:
        per_req = request.extra_params or {}
        instructions = per_req.get("instructions") or self._default_instructions
        emo_voice = per_req.get("emo_voice") or self._default_emo_voice
        emo_alpha = per_req.get("emo_alpha", self._default_emo_alpha)
        emo_vector = per_req.get("emo_vector")
        model = per_req.get("model") or self._model_name

        payload: dict = {
            "model": model,
            "input": request.text,
            "voice": request.voice_id,
            "speed": request.speed,
            "response_format": request.format.value,
        }
        if instructions:
            payload["instructions"] = instructions
        if emo_voice:
            payload["emo_voice"] = emo_voice
        if emo_alpha is not None:
            payload["emo_alpha"] = float(emo_alpha)
        if emo_vector and len(emo_vector) == 8:
            payload["emo_vector"] = list(emo_vector)
        return payload

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.custom_headers:
            headers.update(self.config.custom_headers)
        return headers

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = self._build_payload(request)
        logger.info(
            "IndexTTS synthesize: voice=%s instructions=%r emo_voice=%s alpha=%s "
            "format=%s text_len=%d",
            payload["voice"],
            payload.get("instructions", ""),
            payload.get("emo_voice"),
            payload.get("emo_alpha"),
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
                        f"IndexTTS API status {resp.status_code}: {resp.text[:300]}"
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
                        "instructions": payload.get("instructions"),
                        "emo_voice": payload.get("emo_voice"),
                        "emo_alpha": payload.get("emo_alpha"),
                        "model": payload["model"],
                    },
                )

        try:
            return await circuit.call(_make_request)
        except CircuitBreakerOpenError as e:
            raise TTSProviderAPIError(f"IndexTTS temporarily unavailable: {e}")
        except httpx.TimeoutException:
            raise TTSProviderAPIError(
                f"IndexTTS timeout after {self.config.timeout}s"
            )
        except httpx.RequestError as e:
            raise TTSProviderAPIError(f"IndexTTS request failed: {e}")
        except TTSProviderAPIError:
            raise
        except Exception as e:
            raise TTSProviderAPIError(f"IndexTTS unexpected error: {e}")

    async def synthesize_stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """Stream raw PCM bytes from the wrapper's streaming endpoint.

        Builds the same payload as `synthesize` but adds `stream:true`
        and forces `response_format:pcm` (the wrapper rejects compressed
        formats for streaming since concatenating per-chunk MP3/FLAC
        frames isn't valid). The server uses
        `tts.infer_generator(stream_return=True)` and yields each
        decoded segment's audio as raw int16 LE bytes via chunked
        transfer encoding. PCM bytes concatenate cleanly so the WS
        frame consumer can forward them as-is.
        """
        payload = self._build_payload(request)
        # Force PCM + streaming on the wire — the WebSocket frame
        # protocol expects raw int16 PCM regardless of caller's request.format.
        payload["response_format"] = "pcm"
        payload["stream"] = True
        url = self.config.api_url.rstrip("/") + "/v1/audio/speech"
        logger.info(
            "IndexTTS stream: voice=%s text_len=%d emo_text=%r",
            request.voice_id, len(request.text),
            payload.get("instructions", ""),
        )
        # Generous timeout — IndexTTS yields per-segment, so for a 2k-char
        # scene the whole stream can take 30-60s end-to-end. The per-byte
        # idle timeout matters more than the total here.
        timeout = max(self.config.timeout * 5, 240)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise TTSProviderAPIError(
                            f"IndexTTS stream {resp.status_code}: {body[:300]!r}"
                        )
                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("IndexTTS stream cancelled — closing httpx connection")
            raise
        except TTSProviderAPIError:
            raise
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"IndexTTS stream failed: {e}")

    # ------------------------------------------------------------------
    # Voice listing / validation
    # ------------------------------------------------------------------

    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
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
                        if not vid:
                            continue
                        voices.append(
                            Voice(id=vid, name=name, language=lang, description=desc)
                        )
                else:
                    logger.warning(
                        "IndexTTS /v1/voices returned %s", resp.status_code
                    )
        except Exception as e:
            logger.warning("IndexTTS voice fetch failed: %s", e)

        if language:
            voices = [v for v in voices if language.lower() in (v.language or "").lower()]
        return voices

    async def validate_voice(self, voice_id: str) -> bool:
        # `clone:` prefix is valid by convention even if not listed (server
        # resolves lazily). Bare names get checked against /v1/voices.
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
                # The IndexTTS server lazy-loads the model on first synth call,
                # so /health reports "starting" until something triggers a load.
                # The server is reachable in either state — a "starting" server
                # accepts voice listing and queues synth requests behind the
                # cold load. Treat "healthy" and "starting" both as up; only
                # "load_error" or anything else as failure.
                status = data.get("status")
                return status in ("healthy", "starting")
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
        if audio[:4] == b"fLaC":
            return AudioFormat.FLAC
        return requested

    @staticmethod
    def _estimate_duration(file_size: int, fmt: AudioFormat) -> float:
        # IndexTTS produces 22.05kHz mono. MP3 default 160kbps, FLAC ~352kbps,
        # WAV is 16-bit PCM at 22.05kHz mono = 352800 bps.
        bitrates = {
            AudioFormat.MP3: 160000,
            AudioFormat.FLAC: 352800,
            AudioFormat.WAV: 352800,
        }
        return (file_size * 8) / bitrates.get(fmt, 160000)
