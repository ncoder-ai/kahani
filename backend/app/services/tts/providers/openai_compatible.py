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
        
        try:
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
                    f"{self.config.api_url}/audio/speech",
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
                
        except httpx.TimeoutException:
            error_msg = f"Request timed out after {self.config.timeout} seconds"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
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
                    f"{self.config.api_url}/audio/speech",
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
        
        # Try to fetch from API first
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                response = await client.get(
                    f"{self.config.api_url}/voices",
                    headers=headers
                )
                
                if response.status_code == 200:
                    voices_data = response.json()
                    voices = [
                        Voice(
                            id=v.get("id", v.get("voice_id")),
                            name=v.get("name", v.get("id")),
                            language=v.get("language", "en"),
                            gender=v.get("gender"),
                            description=v.get("description"),
                            preview_url=v.get("preview_url"),
                            tags=v.get("tags")
                        )
                        for v in voices_data.get("voices", [])
                    ]
                    
                    if language:
                        voices = [v for v in voices if v.language == language]
                    
                    logger.info(f"Found {len(voices)} voices from API")
                    return voices
        except Exception as e:
            logger.warning(f"Could not fetch voices from API: {e}")
        
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
