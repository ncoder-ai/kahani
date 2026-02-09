"""
OpenAI-Compatible TTS Provider

Supports OpenAI TTS API format and compatible services like:
- Kokoro FastAPI
- ChatterboxTTS
- OpenAI TTS
- LM Studio TTS
"""

import httpx
import logging
from typing import List, AsyncIterator, Optional
from ..base import (
    TTSProviderBase,
    TTSRequest,
    TTSResponse,
    Voice,
    AudioFormat,
    TTSProviderAPIError
)
from ..registry import TTSProviderRegistry
from app.utils.circuit_breaker import get_circuit_breaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)


@TTSProviderRegistry.register("openai-compatible")
class OpenAICompatibleProvider(TTSProviderBase):
    """
    OpenAI-compatible TTS provider.
    
    Works with OpenAI API, Kokoro FastAPI, ChatterboxTTS, and other
    OpenAI-compatible endpoints.
    """
    
    @property
    def provider_name(self) -> str:
        return "openai-compatible"
    
    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.MP3, AudioFormat.OPUS, AudioFormat.AAC, AudioFormat.WAV]
    
    @property
    def max_text_length(self) -> int:
        return self.config.extra_params.get("max_text_length", 280)
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    @property
    def supports_pitch_control(self) -> bool:
        return False
    
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Synthesize speech using OpenAI-compatible API"""
        logger.info(
            f"Synthesizing audio: voice={request.voice_id}, "
            f"speed={request.speed}, format={request.format.value}, "
            f"text_length={len(request.text)}"
        )
        
        # Get circuit breaker for this TTS provider
        circuit_breaker = get_circuit_breaker(
            name=f"tts-{self.config.api_url}",
            failure_threshold=3,      # Open after 3 failures
            recovery_timeout=30,      # Try again after 30s
            timeout=self.config.timeout
        )
        
        async def _make_request():
            """Inner function to make the actual HTTP request"""
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {
                    "Content-Type": "application/json",
                }
                
                # Add API key if provided
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                # Add custom headers
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                # Build request payload
                payload = {
                    "input": request.text,
                    "voice": request.voice_id,
                    "speed": request.speed,
                    "response_format": request.format.value
                }
                
                # Make API request
                response = await client.post(
                    f"{self.config.api_url}/v1/audio/speech",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_msg = f"API returned status {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise TTSProviderAPIError(error_msg)
                
                audio_data = response.content
                
                # Detect actual format from audio data (ChatterboxTTS may return different format)
                actual_format = self._detect_audio_format(audio_data, request.format)
                
                logger.info(
                    f"Successfully generated audio: {len(audio_data)} bytes, "
                    f"requested format: {request.format.value}, actual format: {actual_format.value}"
                )
                
                return TTSResponse(
                    audio_data=audio_data,
                    format=actual_format,  # Use detected format instead of requested
                    duration=self._estimate_duration(len(audio_data), actual_format),
                    sample_rate=request.sample_rate,
                    file_size=len(audio_data),
                    metadata={
                        "provider": self.provider_name,
                        "voice": request.voice_id,
                        "speed": request.speed,
                        "requested_format": request.format.value,
                        "actual_format": actual_format.value
                    }
                )
        
        # Execute request through circuit breaker
        try:
            return await circuit_breaker.call(_make_request)
        except CircuitBreakerOpenError as e:
            # Circuit is open - TTS service is down
            error_msg = f"TTS service temporarily unavailable: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except httpx.TimeoutException:
            error_msg = f"Request timed out after {self.config.timeout} seconds"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except TTSProviderAPIError:
            # Re-raise TTS errors as-is
            raise
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
    
    async def synthesize_stream(
        self,
        request: TTSRequest
    ) -> AsyncIterator[bytes]:
        """Stream synthesized speech"""
        logger.info(f"Starting streaming synthesis for voice={request.voice_id}")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {
                    "Content-Type": "application/json",
                }
                
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                payload = {
                    "input": request.text,
                    "voice": request.voice_id,
                    "speed": request.speed,
                    "response_format": request.format.value,
                    "stream": True
                }
                
                async with client.stream(
                    "POST",
                    f"{self.config.api_url}/v1/audio/speech",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        error_msg = f"Stream API returned status {response.status_code}"
                        logger.error(error_msg)
                        raise TTSProviderAPIError(error_msg)
                    
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            yield chunk
                    
                    logger.info("Streaming synthesis completed")
                    
        except Exception as e:
            error_msg = f"Streaming failed: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
    
    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        """Get available voices"""
        logger.info(f"Fetching voices for language={language}")
        
        # Try multiple endpoint formats for compatibility
        endpoints_to_try = [
            "/v1/audio/voices",  # Orpheus, some OpenAI-compatible APIs
            "/v1/voices",        # OpenAI standard format
        ]
        
        for endpoint in endpoints_to_try:
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    headers = {}
                    if self.config.api_key:
                        headers["Authorization"] = f"Bearer {self.config.api_key}"
                    
                    url = f"{self.config.api_url}{endpoint}"
                    logger.debug(f"Trying endpoint: {url}")
                    response = await client.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        voices_data = response.json()
                        
                        # Handle different response formats:
                        # 1. Direct array: ["tara", "leah", ...] or [{"id": "...", ...}, ...]
                        # 2. OpenAI standard format: {"object": "list", "data": [...]}
                        # 3. Alternative format: {"voices": [...]}
                        if isinstance(voices_data, list):
                            voices_list = voices_data
                        elif isinstance(voices_data, dict):
                            # Check for OpenAI standard format first
                            if voices_data.get("object") == "list" and "data" in voices_data:
                                voices_list = voices_data.get("data", [])
                            else:
                                # Fall back to "voices" key for backward compatibility
                                voices_list = voices_data.get("voices", [])
                        else:
                            voices_list = []
                        
                        # Handle different voice item formats:
                        # 1. Array of strings: ["tara", "leah", ...]
                        # 2. Array of objects: [{"id": "...", "name": "...", ...}]
                        voices = []
                        for v in voices_list:
                            if isinstance(v, str):
                                # Simple string format - create Voice object
                                voices.append(Voice(
                                    id=v,
                                    name=v,
                                    language="en",
                                    description=f"Voice: {v}"
                                ))
                            else:
                                # Object format - extract fields
                                voices.append(Voice(
                                    id=v.get("id", v.get("voice_id", "")),
                                    name=v.get("name", v.get("id", "")),
                                    language=v.get("language", "en"),
                                    gender=v.get("gender"),
                                    description=v.get("description"),
                                    preview_url=v.get("preview_url"),
                                    tags=v.get("tags")
                                ))
                        
                        if language:
                            voices = [v for v in voices if v.language == language]
                        
                        logger.info(f"Found {len(voices)} voices from API endpoint {endpoint}")
                        return voices
                    else:
                        logger.debug(f"Endpoint {endpoint} returned status {response.status_code}")
            except Exception as e:
                logger.debug(f"Could not fetch voices from {endpoint}: {e}")
                continue
        
        # If all endpoints failed, log warning
        logger.warning(f"Could not fetch voices from any API endpoint")
        
        # Fallback to default voices from config
        default_voices = self.config.extra_params.get("voices", ["Sara"])
        voices = [
            Voice(
                id=voice_id,
                name=voice_id,
                language="en",
                description=f"Default voice: {voice_id}"
            )
            for voice_id in default_voices
        ]
        
        logger.info(f"Using {len(voices)} default voices")
        return voices
    
    async def validate_voice(self, voice_id: str) -> bool:
        """Validate voice ID"""
        try:
            voices = await self.get_voices()
            is_valid = any(v.id == voice_id for v in voices)
            logger.info(f"Voice '{voice_id}' validation: {is_valid}")
            return is_valid
        except Exception as e:
            logger.error(f"Voice validation failed: {e}")
            return False
    
    def _detect_audio_format(self, audio_data: bytes, requested_format: AudioFormat) -> AudioFormat:
        """
        Detect actual audio format from data.
        Some TTS APIs return different formats than requested.
        """
        if len(audio_data) < 12:
            return requested_format
        
        # Check for WAV format (RIFF header)
        if audio_data[:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
            return AudioFormat.WAV
        
        # Check for MP3 format (ID3 tag or MPEG sync)
        if audio_data[:3] == b'ID3' or (audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0):
            return AudioFormat.MP3
        
        # Check for OGG format
        if audio_data[:4] == b'OggS':
            return AudioFormat.OGG
        
        # Check for AAC/M4A format (ftyp box)
        if audio_data[4:8] == b'ftyp':
            return AudioFormat.AAC
        
        # Default to requested format if we can't detect
        logger.warning(f"Could not detect audio format, using requested: {requested_format.value}")
        return requested_format
    
    def _estimate_duration(self, file_size: int, format: AudioFormat) -> float:
        """Estimate audio duration from file size"""
        # Rough estimation based on bitrate
        bitrates = {
            AudioFormat.MP3: 128000,   # 128 kbps
            AudioFormat.AAC: 96000,    # 96 kbps
            AudioFormat.OPUS: 64000,   # 64 kbps
            AudioFormat.WAV: 256000,   # 256 kbps (uncompressed)
            AudioFormat.OGG: 96000     # 96 kbps
        }
        bitrate = bitrates.get(format, 128000)
        duration = (file_size * 8) / bitrate
        return duration
