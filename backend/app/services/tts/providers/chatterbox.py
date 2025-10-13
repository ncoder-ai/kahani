"""
ChatterboxTTS Provider

Specialized provider for ChatterboxTTS with extended features:
- Voice library management
- Advanced TTS parameters (exaggeration, cfg_weight, temperature)
- SSE streaming support
- Long text TTS with job management
"""

import httpx
import logging
import json
import asyncio
from typing import List, AsyncIterator, Optional, Dict, Any
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


@TTSProviderRegistry.register("chatterbox")
class ChatterboxProvider(TTSProviderBase):
    """
    ChatterboxTTS-specific provider with extended features.
    
    Features:
    - Voice library management
    - Advanced TTS parameters
    - SSE streaming
    - Long text TTS jobs
    """
    
    @property
    def provider_name(self) -> str:
        return "chatterbox"
    
    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [AudioFormat.WAV, AudioFormat.MP3]
    
    @property
    def max_text_length(self) -> int:
        # ChatterboxTTS supports up to 3000 chars for standard, more for long text
        return self.config.extra_params.get("max_text_length", 3000)
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    @property
    def supports_pitch_control(self) -> bool:
        return False
    
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Synthesize speech using ChatterboxTTS"""
        logger.info(
            f"Synthesizing audio with ChatterboxTTS: voice={request.voice_id}, "
            f"text_length={len(request.text)}"
        )
        
        # If text is too long (>3000 chars), use long text endpoint
        if len(request.text) > 3000:
            return await self._synthesize_long_text(request)
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {"Content-Type": "application/json"}
                
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                # Build ChatterboxTTS payload with extended parameters
                payload = {
                    "input": request.text,
                    "voice": request.voice_id,
                    "response_format": request.format.value,
                }
                
                # Add ChatterboxTTS-specific parameters
                if hasattr(request, 'extra_params') and request.extra_params:
                    if 'exaggeration' in request.extra_params:
                        payload['exaggeration'] = request.extra_params['exaggeration']
                    if 'cfg_weight' in request.extra_params:
                        payload['cfg_weight'] = request.extra_params['cfg_weight']
                    if 'temperature' in request.extra_params:
                        payload['temperature'] = request.extra_params['temperature']
                
                # Make API request
                response = await client.post(
                    f"{self.config.api_url}/audio/speech",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_msg = f"ChatterboxTTS returned status {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise TTSProviderAPIError(error_msg)
                
                audio_data = response.content
                
                # Detect actual format (ChatterboxTTS often returns WAV regardless of request)
                actual_format = self._detect_audio_format(audio_data, request.format)
                
                logger.info(
                    f"Successfully generated audio: {len(audio_data)} bytes, "
                    f"format: {actual_format.value}"
                )
                
                return TTSResponse(
                    audio_data=audio_data,
                    format=actual_format,
                    duration=self._estimate_duration(len(audio_data), actual_format),
                    sample_rate=request.sample_rate,
                    file_size=len(audio_data),
                    metadata={
                        "provider": self.provider_name,
                        "voice": request.voice_id,
                        "requested_format": request.format.value,
                        "actual_format": actual_format.value,
                        "parameters": payload
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
        """Stream synthesized speech using ChatterboxTTS streaming endpoint"""
        logger.info(
            f"Starting streaming synthesis with ChatterboxTTS: voice={request.voice_id}"
        )
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {"Content-Type": "application/json"}
                
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                payload = {
                    "input": request.text,
                    "voice": request.voice_id,
                    "response_format": request.format.value,
                }
                
                # Add ChatterboxTTS-specific parameters
                if hasattr(request, 'extra_params') and request.extra_params:
                    if 'exaggeration' in request.extra_params:
                        payload['exaggeration'] = request.extra_params['exaggeration']
                    if 'cfg_weight' in request.extra_params:
                        payload['cfg_weight'] = request.extra_params['cfg_weight']
                    if 'temperature' in request.extra_params:
                        payload['temperature'] = request.extra_params['temperature']
                    if 'streaming_chunk_size' in request.extra_params:
                        payload['streaming_chunk_size'] = request.extra_params['streaming_chunk_size']
                    if 'streaming_strategy' in request.extra_params:
                        payload['streaming_strategy'] = request.extra_params['streaming_strategy']
                
                # Use ChatterboxTTS streaming endpoint
                async with client.stream(
                    "POST",
                    f"{self.config.api_url}/audio/speech/stream",
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
        """Get available voices from ChatterboxTTS voice library"""
        logger.info(f"Fetching voices from ChatterboxTTS library, language={language}")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                response = await client.get(
                    f"{self.config.api_url}/voices",
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch voices: {response.status_code}")
                    return []
                
                voices_data = response.json()
                
                # ChatterboxTTS returns a list of voice objects
                voices = []
                voice_list = voices_data if isinstance(voices_data, list) else voices_data.get("voices", [])
                
                for v in voice_list:
                    voice = Voice(
                        id=v.get("voice_name") or v.get("name") or v.get("id"),
                        name=v.get("voice_name") or v.get("name") or v.get("id"),
                        language=v.get("language", "en"),
                        gender=v.get("gender"),
                        description=v.get("description"),
                        preview_url=v.get("preview_url"),
                        tags=v.get("tags", [])
                    )
                    voices.append(voice)
                
                if language:
                    voices = [v for v in voices if v.language == language]
                
                logger.info(f"Found {len(voices)} voices from ChatterboxTTS")
                return voices
                
        except Exception as e:
            logger.error(f"Failed to fetch voices from ChatterboxTTS: {e}")
            return []
    
    async def validate_voice(self, voice_id: str) -> bool:
        """Validate voice ID exists in ChatterboxTTS library"""
        try:
            voices = await self.get_voices()
            is_valid = any(v.id == voice_id for v in voices)
            logger.info(f"Voice '{voice_id}' validation: {is_valid}")
            return is_valid
        except Exception as e:
            logger.error(f"Voice validation failed: {e}")
            return False
    
    # ChatterboxTTS-specific methods
    
    async def get_supported_languages(self) -> List[Dict[str, str]]:
        """Get supported languages from ChatterboxTTS"""
        logger.info("Fetching supported languages from ChatterboxTTS")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                response = await client.get(
                    f"{self.config.api_url}/languages",
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch languages: {response.status_code}")
                    return []
                
                data = response.json()
                languages = data.get("languages", [])
                
                logger.info(f"Found {len(languages)} supported languages")
                return languages
                
        except Exception as e:
            logger.error(f"Failed to fetch languages: {e}")
            return []
    
    async def get_default_voice(self) -> Optional[Dict[str, Any]]:
        """Get the current default voice"""
        logger.info("Fetching default voice from ChatterboxTTS")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                response = await client.get(
                    f"{self.config.api_url}/voices/default",
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch default voice: {response.status_code}")
                    return None
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to fetch default voice: {e}")
            return None
    
    async def set_default_voice(self, voice_name: str) -> bool:
        """Set a voice as the default"""
        logger.info(f"Setting default voice to: {voice_name}")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                response = await client.post(
                    f"{self.config.api_url}/voices/default",
                    headers=headers,
                    data={"voice_name": voice_name}
                )
                
                if response.status_code == 200:
                    logger.info(f"Default voice set to: {voice_name}")
                    return True
                else:
                    logger.error(f"Failed to set default voice: {response.status_code}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to set default voice: {e}")
            return False
    
    async def upload_voice(
        self,
        voice_name: str,
        voice_file: bytes,
        language: str = "en"
    ) -> bool:
        """Upload a new voice to the library"""
        logger.info(f"Uploading voice: {voice_name}, language: {language}")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    # Don't add Content-Type for multipart
                    headers.update({k: v for k, v in self.config.custom_headers.items() 
                                   if k.lower() != 'content-type'})
                
                files = {
                    "voice_file": (f"{voice_name}.wav", voice_file, "audio/wav")
                }
                data = {
                    "voice_name": voice_name,
                    "language": language
                }
                
                response = await client.post(
                    f"{self.config.api_url}/voices",
                    headers=headers,
                    files=files,
                    data=data
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"Voice uploaded successfully: {voice_name}")
                    return True
                else:
                    logger.error(f"Failed to upload voice: {response.status_code} - {response.text}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to upload voice: {e}")
            return False
    
    async def delete_voice(self, voice_name: str) -> bool:
        """Delete a voice from the library"""
        logger.info(f"Deleting voice: {voice_name}")
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                response = await client.delete(
                    f"{self.config.api_url}/voices/{voice_name}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    logger.info(f"Voice deleted successfully: {voice_name}")
                    return True
                else:
                    logger.error(f"Failed to delete voice: {response.status_code}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to delete voice: {e}")
            return False
    
    async def _synthesize_long_text(self, request: TTSRequest) -> TTSResponse:
        """
        Handle long text (>3000 chars) using ChatterboxTTS job system.
        Note: This is a simplified implementation. For production, you'd want
        to implement proper job polling and status tracking.
        """
        logger.info(f"Synthesizing long text: {len(request.text)} characters")
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # Longer timeout for long text
                headers = {"Content-Type": "application/json"}
                
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                if self.config.custom_headers:
                    headers.update(self.config.custom_headers)
                
                payload = {
                    "input": request.text,
                    "voice": request.voice_id,
                    "response_format": request.format.value,
                }
                
                # Add ChatterboxTTS-specific parameters
                if hasattr(request, 'extra_params') and request.extra_params:
                    for param in ['exaggeration', 'cfg_weight', 'temperature']:
                        if param in request.extra_params:
                            payload[param] = request.extra_params[param]
                
                # Create long text job
                response = await client.post(
                    f"{self.config.api_url}/audio/speech/long",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    error_msg = f"Failed to create long text job: {response.status_code}"
                    logger.error(error_msg)
                    raise TTSProviderAPIError(error_msg)
                
                job_data = response.json()
                job_id = job_data["job_id"]
                
                logger.info(f"Created long text job: {job_id}")
                
                # Poll for completion
                while True:
                    await asyncio.sleep(2)  # Poll every 2 seconds
                    
                    status_response = await client.get(
                        f"{self.config.api_url}/audio/speech/long/{job_id}",
                        headers=headers
                    )
                    
                    if status_response.status_code != 200:
                        raise TTSProviderAPIError("Failed to check job status")
                    
                    status_data = status_response.json()
                    status = status_data["status"]
                    
                    if status == "completed":
                        # Download audio
                        download_response = await client.get(
                            f"{self.config.api_url}/audio/speech/long/{job_id}/download",
                            headers=headers
                        )
                        
                        if download_response.status_code != 200:
                            raise TTSProviderAPIError("Failed to download audio")
                        
                        audio_data = download_response.content
                        actual_format = self._detect_audio_format(audio_data, request.format)
                        
                        logger.info(f"Long text job completed: {len(audio_data)} bytes")
                        
                        return TTSResponse(
                            audio_data=audio_data,
                            format=actual_format,
                            duration=self._estimate_duration(len(audio_data), actual_format),
                            sample_rate=request.sample_rate,
                            file_size=len(audio_data),
                            metadata={
                                "provider": self.provider_name,
                                "voice": request.voice_id,
                                "job_id": job_id,
                                "long_text": True
                            }
                        )
                    
                    elif status == "failed":
                        error = status_data.get("error", "Unknown error")
                        raise TTSProviderAPIError(f"Long text job failed: {error}")
                    
                    # Continue polling for pending/processing
                    
        except Exception as e:
            logger.error(f"Long text synthesis failed: {e}")
            raise TTSProviderAPIError(str(e))
    
    def _detect_audio_format(self, audio_data: bytes, requested_format: AudioFormat) -> AudioFormat:
        """Detect actual audio format from data"""
        if len(audio_data) < 12:
            return requested_format
        
        # Check for WAV format (RIFF header)
        if audio_data[:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
            return AudioFormat.WAV
        
        # Check for MP3 format (ID3 tag or MPEG sync)
        if audio_data[:3] == b'ID3' or (audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0):
            return AudioFormat.MP3
        
        # Default to requested format
        return requested_format
    
    def _estimate_duration(self, file_size: int, format: AudioFormat) -> float:
        """Estimate audio duration from file size"""
        bitrates = {
            AudioFormat.MP3: 128000,   # 128 kbps
            AudioFormat.WAV: 256000,   # 256 kbps (uncompressed)
        }
        bitrate = bitrates.get(format, 128000)
        duration = (file_size * 8) / bitrate
        return duration
