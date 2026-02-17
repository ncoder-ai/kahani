"""
VibeVoice TTS Provider

Supports VibeVoice real-time TTS via WebSocket streaming.
VibeVoice uses WebSocket for streaming audio and returns PCM16 format.
"""

import httpx
import logging
import struct
import asyncio
from typing import List, AsyncIterator, Optional, Dict, Any
from urllib.parse import urlparse, urlunparse
import websockets
from websockets.exceptions import WebSocketException

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

# VibeVoice constants
VIBEVOICE_SAMPLE_RATE = 24000
VIBEVOICE_BITS_PER_SAMPLE = 16
VIBEVOICE_CHANNELS = 1


@TTSProviderRegistry.register("vibevoice")
class VibeVoiceProvider(TTSProviderBase):
    """
    VibeVoice TTS provider.
    
    Uses WebSocket for real-time streaming TTS.
    Converts PCM16 audio to WAV format for compatibility.
    """
    
    @property
    def provider_name(self) -> str:
        return "vibevoice"
    
    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.WAV, AudioFormat.MP3]
    
    @property
    def max_text_length(self) -> int:
        # VibeVoice can handle long text, but we'll use a reasonable limit
        return self.config.extra_params.get("max_text_length", 5000)
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    @property
    def supports_pitch_control(self) -> bool:
        return False
    
    def _convert_ws_url(self, http_url: str) -> str:
        """Convert HTTP URL to WebSocket URL"""
        parsed = urlparse(http_url)
        scheme = "ws" if parsed.scheme == "http" else "wss"
        return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    
    def _pcm16_to_wav(self, pcm_data: bytes, sample_rate: int = VIBEVOICE_SAMPLE_RATE) -> bytes:
        """
        Convert PCM16 audio data to WAV format.
        
        Args:
            pcm_data: Raw PCM16 audio bytes
            sample_rate: Sample rate in Hz (default: 24000)
            
        Returns:
            WAV format audio bytes
        """
        if not pcm_data:
            return b''
        
        num_samples = len(pcm_data) // 2  # 16-bit = 2 bytes per sample
        num_channels = VIBEVOICE_CHANNELS
        bits_per_sample = VIBEVOICE_BITS_PER_SAMPLE
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = num_samples * block_align
        
        # WAV header structure
        wav_header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + data_size,  # File size - 8
            b'WAVE',
            b'fmt ',
            16,  # fmt chunk size
            1,   # Audio format (1 = PCM)
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b'data',
            data_size
        )
        
        return wav_header + pcm_data
    
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Synthesize speech using VibeVoice WebSocket API"""
        logger.info(
            f"Synthesizing audio with VibeVoice: voice={request.voice_id}, "
            f"text_length={len(request.text)}"
        )
        
        # Collect all audio chunks
        audio_chunks = []
        
        try:
            # Convert HTTP URL to WebSocket URL
            ws_url = self._convert_ws_url(self.config.api_url)
            stream_url = f"{ws_url}/stream"
            
            # Build query parameters
            params = {
                "text": request.text,
                "voice": request.voice_id or "default"
            }
            
            # Add VibeVoice-specific parameters from extra_params
            if request.extra_params:
                if "cfg_scale" in request.extra_params:
                    params["cfg"] = str(request.extra_params["cfg_scale"])
                if "inference_steps" in request.extra_params:
                    params["steps"] = str(request.extra_params["inference_steps"])
            
            # Add cfg_scale from config if not in request
            if self.config.extra_params:
                if "cfg_scale" in self.config.extra_params and "cfg" not in params:
                    params["cfg"] = str(self.config.extra_params["cfg_scale"])
                if "inference_steps" in self.config.extra_params and "steps" not in params:
                    params["steps"] = str(self.config.extra_params["inference_steps"])
            
            # Default values if not provided
            if "cfg" not in params:
                params["cfg"] = "1.5"
            if "steps" not in params:
                params["steps"] = "5"
            
            # Build query string
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{stream_url}?{query_string}"
            
            logger.debug(f"Connecting to VibeVoice WebSocket: {full_url}")
            
            # Connect to WebSocket and receive audio chunks
            async with websockets.connect(
                full_url,
                timeout=self.config.timeout
            ) as websocket:
                async for message in websocket:
                    if isinstance(message, bytes):
                        audio_chunks.append(message)
                    elif isinstance(message, str):
                        # VibeVoice may send JSON log messages
                        try:
                            import json
                            log_data = json.loads(message)
                            if log_data.get("type") == "log":
                                logger.debug(f"VibeVoice log: {log_data.get('event')}")
                        except:
                            pass
            
            # Combine all PCM16 chunks
            pcm_data = b''.join(audio_chunks)
            
            if not pcm_data:
                raise TTSProviderAPIError("No audio data received from VibeVoice")
            
            # Convert PCM16 to WAV
            wav_data = self._pcm16_to_wav(pcm_data, VIBEVOICE_SAMPLE_RATE)
            
            # Calculate duration
            num_samples = len(pcm_data) // 2
            duration = num_samples / VIBEVOICE_SAMPLE_RATE
            
            logger.info(
                f"Successfully generated audio: {len(wav_data)} bytes (WAV), "
                f"{len(pcm_data)} bytes (PCM16), duration: {duration:.2f}s"
            )
            
            return TTSResponse(
                audio_data=wav_data,
                format=AudioFormat.WAV,
                duration=duration,
                sample_rate=VIBEVOICE_SAMPLE_RATE,
                file_size=len(wav_data),
                metadata={
                    "provider": self.provider_name,
                    "voice": request.voice_id,
                    "pcm_size": len(pcm_data),
                    "wav_size": len(wav_data),
                    "cfg_scale": params.get("cfg"),
                    "inference_steps": params.get("steps")
                }
            )
            
        except websockets.exceptions.InvalidURI as e:
            error_msg = f"Invalid WebSocket URL: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except websockets.exceptions.ConnectionClosed as e:
            error_msg = f"WebSocket connection closed: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except asyncio.TimeoutError:
            error_msg = f"Request timed out after {self.config.timeout} seconds"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
        except Exception as e:
            error_msg = f"VibeVoice synthesis failed: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
    
    async def synthesize_stream(
        self,
        request: TTSRequest
    ) -> AsyncIterator[bytes]:
        """Stream synthesized speech using VibeVoice WebSocket"""
        logger.info(f"Starting streaming synthesis with VibeVoice: voice={request.voice_id}")
        
        try:
            # Convert HTTP URL to WebSocket URL
            ws_url = self._convert_ws_url(self.config.api_url)
            stream_url = f"{ws_url}/stream"
            
            # Build query parameters
            params = {
                "text": request.text,
                "voice": request.voice_id or "default"
            }
            
            # Add VibeVoice-specific parameters
            if request.extra_params:
                if "cfg_scale" in request.extra_params:
                    params["cfg"] = str(request.extra_params["cfg_scale"])
                if "inference_steps" in request.extra_params:
                    params["steps"] = str(request.extra_params["inference_steps"])
            
            if self.config.extra_params:
                if "cfg_scale" in self.config.extra_params and "cfg" not in params:
                    params["cfg"] = str(self.config.extra_params["cfg_scale"])
                if "inference_steps" in self.config.extra_params and "steps" not in params:
                    params["steps"] = str(self.config.extra_params["inference_steps"])
            
            # Default values
            if "cfg" not in params:
                params["cfg"] = "1.5"
            if "steps" not in params:
                params["steps"] = "5"
            
            # Build query string
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{stream_url}?{query_string}"
            
            logger.debug(f"Connecting to VibeVoice WebSocket stream: {full_url}")
            
            # Connect and stream audio chunks
            async with websockets.connect(
                full_url,
                timeout=self.config.timeout
            ) as websocket:
                async for message in websocket:
                    if isinstance(message, bytes):
                        # Convert PCM16 chunk to WAV and yield
                        # For streaming, we'll yield WAV chunks
                        # Note: This creates a WAV header for each chunk which isn't ideal
                        # but works for streaming. For better performance, you might want
                        # to yield raw PCM16 and handle conversion on the client side.
                        wav_chunk = self._pcm16_to_wav(message, VIBEVOICE_SAMPLE_RATE)
                        yield wav_chunk
                    elif isinstance(message, str):
                        # Log messages
                        try:
                            import json
                            log_data = json.loads(message)
                            if log_data.get("type") == "log":
                                logger.debug(f"VibeVoice log: {log_data.get('event')}")
                        except:
                            pass
            
            logger.info("Streaming synthesis completed")
            
        except Exception as e:
            error_msg = f"VibeVoice streaming failed: {str(e)}"
            logger.error(error_msg)
            raise TTSProviderAPIError(error_msg)
    
    async def get_voices(self, language: Optional[str] = None) -> List[Voice]:
        """Get available voices from VibeVoice /config endpoint"""
        logger.info(f"Fetching voices from VibeVoice, language={language}")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                response = await client.get(
                    f"{self.config.api_url}/config",
                    headers=headers
                )
                
                if response.status_code != 200:
                    error_msg = f"Failed to fetch voices: {response.status_code}"
                    logger.error(error_msg)
                    # Return default voices on error
                    return self._get_default_voices()
                
                config_data = response.json()
                voices_list = config_data.get("voices", [])
                
                voices = []
                for voice_id in voices_list:
                    # Extract language from voice ID (e.g., "en-Emma_woman" -> "en")
                    lang = "en"
                    if "-" in voice_id:
                        lang = voice_id.split("-")[0]
                    
                    # Extract gender from voice ID (e.g., "en-Emma_woman" -> "woman")
                    gender = None
                    if "_" in voice_id:
                        gender_part = voice_id.split("_")[-1]
                        gender = "female" if "woman" in gender_part.lower() or "female" in gender_part.lower() else "male"
                    
                    voices.append(Voice(
                        id=voice_id,
                        name=voice_id,
                        language=lang,
                        gender=gender,
                        description=f"VibeVoice voice: {voice_id}"
                    ))
                
                # Filter by language if requested
                if language:
                    voices = [v for v in voices if v.language.lower() == language.lower()]
                
                logger.info(f"Found {len(voices)} voices from VibeVoice")
                return voices
                
        except Exception as e:
            logger.error(f"Failed to fetch voices from VibeVoice: {e}")
            return self._get_default_voices()
    
    def _get_default_voices(self) -> List[Voice]:
        """Return default VibeVoice voices"""
        default_voices = [
            "en-Emma_woman",
            "en-Carter_man",
            "en-Davis_man",
            "en-Frank_man",
            "en-Grace_woman",
            "en-Mike_man"
        ]
        
        voices = []
        for voice_id in default_voices:
            lang = "en"
            if "-" in voice_id:
                lang = voice_id.split("-")[0]
            
            gender = None
            if "_" in voice_id:
                gender_part = voice_id.split("_")[-1]
                gender = "female" if "woman" in gender_part.lower() else "male"
            
            voices.append(Voice(
                id=voice_id,
                name=voice_id,
                language=lang,
                gender=gender,
                description=f"VibeVoice voice: {voice_id}"
            ))
        
        return voices
    
    async def validate_voice(self, voice_id: str) -> bool:
        """Validate voice ID exists"""
        try:
            voices = await self.get_voices()
            is_valid = any(v.id == voice_id for v in voices)
            logger.info(f"Voice '{voice_id}' validation: {is_valid}")
            return is_valid
        except Exception as e:
            logger.error(f"Voice validation failed: {e}")
            return False
