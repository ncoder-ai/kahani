"""VibeVoice TTS provider — talks to the VibeVoice-FastAPI wrapper.

Endpoints used (https://github.com/microsoft/VibeVoice + the
VibeVoice-FastAPI fork):
  POST /v1/audio/speech         — OpenAI-compatible single-speaker
  POST /v1/vibevoice/generate   — native multi-speaker script with
                                  positional voice slots (max 4)
  GET  /v1/audio/voices         — voice list
  GET  /v1/vibevoice/health     — readiness + model_loaded flag

The multi-speaker endpoint is what makes this provider special: pass a
`Speaker 0: ...\\nSpeaker 1: ...` script + an array of
`{speaker_id, voice_preset}` mappings, and the model returns a single
cohesive audio stream with seamless turn-taking — no per-utterance
chunking, no concat seams. Streaming variant emits PCM frames as
generation progresses, so time-to-first-audio stays sub-second even
for long scenes (tested: 0.5s TTFB on 36-segment scene).

Streaming wire format: the wrapper wraps PCM frames in Server-Sent
Events as `data: {"chunk_id", "audio": <base64>, "format", "sample_rate"}\\n\\n`.
This provider parses the SSE envelope and yields raw PCM bytes that
match `streaming_pcm_format`, so kahani's WebSocket frame protocol
works unchanged — just one big stream instead of N chunks.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from ..base import (
    AudioFormat,
    MultiSpeakerRequest,
    PcmFormat,
    TTSProviderAPIError,
    TTSProviderBase,
    TTSResponse,
    TTSRequest,
    Voice,
)
from ..registry import TTSProviderRegistry

logger = logging.getLogger(__name__)


# VibeVoice's audio output is fixed: 24kHz mono 16-bit PCM.
SAMPLE_RATE = 24000
BITS_PER_SAMPLE = 16
CHANNELS = 1


@TTSProviderRegistry.register("vibevoice")
class VibeVoiceProvider(TTSProviderBase):
    """VibeVoice with native multi-speaker + true streaming support."""

    @property
    def provider_name(self) -> str:
        return "vibevoice"

    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.MP3, AudioFormat.WAV, AudioFormat.PCM]

    @property
    def max_text_length(self) -> int:
        return (self.config.extra_params or {}).get("max_text_length", 5000)

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def streaming_pcm_format(self) -> Optional[PcmFormat]:
        return PcmFormat(
            sample_rate=SAMPLE_RATE,
            channels=CHANNELS,
            bits_per_sample=BITS_PER_SAMPLE,
        )

    @property
    def supports_pitch_control(self) -> bool:
        return False

    # -------- multi-speaker capabilities --------

    @property
    def supports_multi_speaker_script(self) -> bool:
        return True

    @property
    def supports_multi_speaker_streaming(self) -> bool:
        return True

    @property
    def max_speakers_per_call(self) -> int:
        return 4

    # -------- helpers --------

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.config.api_key:
            h["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.custom_headers:
            h.update(self.config.custom_headers)
        return h

    def _params(self) -> Dict[str, Any]:
        """Pull cfg_scale / inference_steps from provider extra_params."""
        extras = self.config.extra_params or {}
        return {
            "cfg_scale": float(extras.get("cfg_scale", 1.3)),
            "inference_steps": int(extras.get("inference_steps", 10)),
        }

    @staticmethod
    async def _decode_sse_pcm(resp: httpx.Response) -> AsyncIterator[bytes]:
        """Parse VibeVoice's SSE-wrapped PCM stream and yield raw PCM bytes.

        Wire shape: `data: {"chunk_id", "audio": <b64-pcm>, ...}\\n\\n`,
        terminated by `data: {"done": true}\\n\\n` or
        `data: {"error": "..."}\\n\\n`.
        """
        buf = ""
        async for chunk in resp.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                event, buf = buf.split("\n\n", 1)
                event = event.strip()
                if not event.startswith("data:"):
                    continue
                payload = event[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("VibeVoice SSE non-JSON payload: %r", payload[:120])
                    continue
                if data.get("done"):
                    return
                if data.get("error"):
                    raise TTSProviderAPIError(f"VibeVoice stream error: {data['error']}")
                b64 = data.get("audio")
                if not b64:
                    continue
                try:
                    yield base64.b64decode(b64)
                except Exception as e:
                    logger.warning("VibeVoice SSE base64 decode failed: %s", e)

    # -------- single-speaker (OpenAI-compatible endpoint) --------

    def _speech_payload(self, request: TTSRequest, stream: bool) -> Dict[str, Any]:
        per_req = request.extra_params or {}
        defaults = self._params()
        return {
            "model": per_req.get("model") or "tts-1",
            "input": request.text,
            "voice": request.voice_id,
            "speed": request.speed,
            # PCM for streaming (browser-friendly, no decoder needed),
            # MP3 for blocking calls (smaller payload, easy to cache).
            "response_format": ("pcm" if stream else request.format.value),
            "stream": stream,
            "cfg_scale": per_req.get("cfg_scale", defaults["cfg_scale"]),
            "inference_steps": per_req.get("inference_steps", defaults["inference_steps"]),
        }

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = self._speech_payload(request, stream=False)
        url = self.config.api_url.rstrip("/") + "/v1/audio/speech"
        logger.info(
            "VibeVoice synthesize: voice=%s text_len=%d format=%s",
            request.voice_id, len(request.text), payload["response_format"],
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                r = await client.post(url, headers=self._headers(), json=payload)
                if r.status_code != 200:
                    raise TTSProviderAPIError(
                        f"VibeVoice {r.status_code}: {r.text[:300]}"
                    )
                audio = r.content
            return TTSResponse(
                audio_data=audio,
                format=request.format,
                duration=len(audio) / max(1, SAMPLE_RATE * 2)
                if request.format == AudioFormat.PCM
                else 0.0,
                sample_rate=SAMPLE_RATE,
                file_size=len(audio),
                metadata={"provider": self.provider_name, "voice": request.voice_id},
            )
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"VibeVoice request failed: {e}")

    async def synthesize_stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """Stream PCM bytes for a single utterance.

        Forces `response_format=pcm` regardless of caller preference —
        the WebSocket frame protocol wants raw PCM. Falls back gracefully
        if the wrapper returns a non-streaming response (treats it as
        one big chunk).
        """
        payload = self._speech_payload(request, stream=True)
        url = self.config.api_url.rstrip("/") + "/v1/audio/speech"
        logger.info(
            "VibeVoice stream: voice=%s text_len=%d (forcing pcm)",
            request.voice_id, len(request.text),
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise TTSProviderAPIError(
                            f"VibeVoice stream {resp.status_code}: {body[:300]!r}"
                        )
                    ctype = resp.headers.get("content-type", "")
                    if ctype.startswith("text/event-stream"):
                        async for pcm in self._decode_sse_pcm(resp):
                            yield pcm
                    else:
                        # Wrapper returned chunked raw bytes (older path) —
                        # forward as-is.
                        async for chunk in resp.aiter_bytes(chunk_size=4096):
                            if chunk:
                                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            # Re-raise so the async with blocks above run their __aexit__
            # and close the httpx connection — that TCP FIN is what tells
            # the upstream server to free its GPU resources.
            logger.info("VibeVoice stream cancelled — closing httpx connection")
            raise
        except TTSProviderAPIError:
            raise
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"VibeVoice stream failed: {e}")

    # -------- multi-speaker (native) --------

    def _multi_speaker_payload(
        self, request: MultiSpeakerRequest, stream: bool
    ) -> Dict[str, Any]:
        per_req = request.extra_params or {}
        defaults = self._params()
        # Build the script body. Caller hands us segments already in the
        # canonical format; we delegate the actual line-level formatting
        # to multi_speaker_script.build_vibevoice_script (called above us)
        # — but for safety this method also accepts a pre-built `script`
        # in extra_params.
        script = (per_req.get("script") or "").strip()
        speakers = per_req.get("speakers")  # [{speaker_id, voice_preset}, ...]
        if not script or not speakers:
            raise TTSProviderAPIError(
                "VibeVoice multi-speaker call missing pre-built script/speakers"
            )
        return {
            "script": script,
            "speakers": speakers,
            "cfg_scale": float(per_req.get("cfg_scale", defaults["cfg_scale"])),
            "inference_steps": int(per_req.get("inference_steps", defaults["inference_steps"])),
            "response_format": ("pcm" if stream else request.format.value),
            "stream": stream,
        }

    async def synthesize_multi_speaker_block(
        self, request: MultiSpeakerRequest
    ) -> TTSResponse:
        payload = self._multi_speaker_payload(request, stream=False)
        url = self.config.api_url.rstrip("/") + "/v1/vibevoice/generate"
        n_speakers = len(payload["speakers"])
        logger.info(
            "VibeVoice multi-speaker block: speakers=%d script_chars=%d",
            n_speakers, len(payload["script"]),
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout * 5) as client:
                r = await client.post(url, headers=self._headers(), json=payload)
                if r.status_code != 200:
                    raise TTSProviderAPIError(
                        f"VibeVoice multi-speaker {r.status_code}: {r.text[:300]}"
                    )
                audio = r.content
            return TTSResponse(
                audio_data=audio,
                format=request.format,
                duration=0.0,
                sample_rate=SAMPLE_RATE,
                file_size=len(audio),
                metadata={
                    "provider": self.provider_name,
                    "speakers": n_speakers,
                    "script_chars": len(payload["script"]),
                },
            )
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"VibeVoice multi-speaker request failed: {e}")

    async def synthesize_multi_speaker_stream(
        self, request: MultiSpeakerRequest
    ) -> AsyncIterator[bytes]:
        payload = self._multi_speaker_payload(request, stream=True)
        url = self.config.api_url.rstrip("/") + "/v1/vibevoice/generate"
        n_speakers = len(payload["speakers"])
        logger.info(
            "VibeVoice multi-speaker stream: speakers=%d script_chars=%d",
            n_speakers, len(payload["script"]),
        )
        # 5x the configured timeout — multi-speaker scenes take longer
        # than single utterances and the user's per-request timeout
        # default (30s) is too tight for a 2-min scene render.
        timeout = max(self.config.timeout * 5, 300)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise TTSProviderAPIError(
                            f"VibeVoice multi-speaker stream {resp.status_code}: "
                            f"{body[:300]!r}"
                        )
                    ctype = resp.headers.get("content-type", "")
                    if ctype.startswith("text/event-stream"):
                        async for pcm in self._decode_sse_pcm(resp):
                            yield pcm
                    else:
                        async for chunk in resp.aiter_bytes(chunk_size=4096):
                            if chunk:
                                yield chunk
        except TTSProviderAPIError:
            raise
        except httpx.HTTPError as e:
            raise TTSProviderAPIError(f"VibeVoice multi-speaker stream failed: {e}")

    # -------- voice listing --------

    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        url = self.config.api_url.rstrip("/") + "/v1/audio/voices"
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                # `show_all=true` surfaces custom voices the user dropped
                # into the wrapper's voices/ directory in addition to the
                # 9 built-in presets.
                r = await client.get(
                    url, headers=self._headers(),
                    params={"show_all": "true"},
                )
                if r.status_code != 200:
                    logger.warning("VibeVoice /v1/audio/voices %s", r.status_code)
                    return []
                data = r.json()
        except Exception as e:
            logger.warning("VibeVoice voice list failed: %s", e)
            return []

        # Wrapper response shapes seen across versions:
        #   - {"object":"list","data":[{"id":..,"name":..}, ...]}  (OpenAI-style)
        #   - {"voices":[ ... ]}
        #   - [ ... ]  (raw list)
        # Try each in order.
        if isinstance(data, dict):
            items = data.get("data") or data.get("voices") or []
        else:
            items = data
        if not isinstance(items, list):
            return []
        out: List[Voice] = []
        for v in items:
            if isinstance(v, str):
                vid, name = v, v
            else:
                vid = v.get("id") or v.get("name") or ""
                name = v.get("name") or vid
            if not vid:
                continue
            # Heuristic language tag from the conventional `xx-` prefix.
            lang = "en"
            if "-" in vid and len(vid.split("-", 1)[0]) == 2:
                lang = vid.split("-", 1)[0]
            out.append(Voice(id=vid, name=name, language=lang,
                             description=f"VibeVoice voice: {vid}"))

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
                    self.config.api_url.rstrip("/") + "/v1/vibevoice/health",
                    headers=self._headers(),
                )
                if r.status_code != 200:
                    return False
                return bool((r.json() or {}).get("model_loaded"))
        except Exception:
            return False
