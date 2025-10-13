"""
Kokoro FastAPI TTS Provider

Implements TTS provider for Kokoro FastAPI service.
API Documentation: OpenAPI 3.1.0 compatible

Key Features:
- OpenAI-compatible endpoints (/v1/audio/speech)
- Voice combining (combine multiple voices into one)
- Streaming support with sentence-level chunks
- Multiple audio formats (mp3, opus, flac, wav, pcm)
- Speed control (0.25 - 4.0)
- Volume multiplier
- Advanced text normalization options
- Phoneme-based generation
- Word-level timestamps support
"""

import logging
import httpx
from typing import List, Optional, AsyncIterator, Dict, Any
from dataclasses import dataclass

from ..base import (
    TTSProviderBase,
    TTSProviderConfig,
    TTSRequest,
    TTSResponse,
    Voice,
    AudioFormat
)

logger = logging.getLogger(__name__)


@dataclass
class KokoroVoice:
    """Kokoro voice information"""
    id: str
    name: str
    language: str
    is_combined: bool = False
    source_voices: Optional[List[str]] = None


class KokoroProvider(TTSProviderBase):
    """
    Kokoro FastAPI TTS Provider
    
    Supports OpenAI-compatible API with Kokoro-specific extensions:
    - Voice combining
    - Advanced normalization
    - Phoneme-based generation
    - Word-level timestamps
    """
    
    @property
    def provider_name(self) -> str:
        return "kokoro"
    
    @property
    def supported_formats(self) -> List[AudioFormat]:
        return [
            AudioFormat.MP3,
            AudioFormat.WAV,
            AudioFormat.FLAC,
            AudioFormat.OPUS,
            AudioFormat.PCM
        ]
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    @property
    def supports_pitch_control(self) -> bool:
        return False  # Kokoro doesn't support pitch control
    
    @property
    def max_text_length(self) -> int:
        return self._max_text_length
    
    def __init__(self, config: TTSProviderConfig):
        super().__init__(config)
        self.client = httpx.AsyncClient(timeout=config.timeout)
        self._max_text_length = config.extra_params.get("max_text_length", 5000) if config.extra_params else 5000
        
        logger.info(f"Initialized Kokoro provider: {config.api_url}")
    
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize speech using Kokoro API
        
        Args:
            request: TTS request with text and voice settings
            
        Returns:
            TTSResponse with generated audio data
        """
        logger.info(
            f"Synthesizing audio with Kokoro: voice={request.voice_id}, "
            f"text_length={len(request.text)}"
        )
        
        # Map our AudioFormat to Kokoro's response_format
        format_map = {
            AudioFormat.MP3: "mp3",
            AudioFormat.WAV: "wav",
            AudioFormat.FLAC: "flac",
            AudioFormat.OPUS: "opus",
            AudioFormat.PCM: "pcm"
        }
        
        response_format = format_map.get(request.format, "wav")
        
        # Build request payload
        payload = {
            "model": "kokoro",
            "input": request.text,
            "voice": request.voice_id,
            "response_format": response_format,
            "speed": request.speed,
            "stream": False  # Non-streaming for synthesize
        }
        
        # Add extra parameters if provided
        if request.extra_params:
            # Volume multiplier
            if "volume_multiplier" in request.extra_params:
                payload["volume_multiplier"] = request.extra_params["volume_multiplier"]
            
            # Language code
            if "lang_code" in request.extra_params:
                payload["lang_code"] = request.extra_params["lang_code"]
            
            # Normalization options
            if "normalization_options" in request.extra_params:
                payload["normalization_options"] = request.extra_params["normalization_options"]
        
        try:
            response = await self.client.post(
                f"{self.config.api_url}/v1/audio/speech",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            audio_data = response.content
            file_size = len(audio_data)
            
            # Estimate duration (rough approximation)
            # For WAV: ~176400 bytes per second (44.1kHz, 16-bit, stereo)
            # For MP3: ~16000 bytes per second at 128kbps
            bytes_per_second = 16000 if response_format == "mp3" else 176400
            duration = file_size / bytes_per_second
            
            logger.info(f"Successfully generated audio: {file_size} bytes, format: {response_format}")
            
            return TTSResponse(
                audio_data=audio_data,
                format=request.format,
                sample_rate=request.sample_rate,
                duration=duration,
                file_size=file_size
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Kokoro API error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Kokoro synthesis failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Kokoro synthesis error: {str(e)}")
            raise
    
    async def synthesize_stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """
        Stream speech synthesis from Kokoro API
        
        Kokoro streams complete sentences as they're generated.
        
        Args:
            request: TTS request with text and voice settings
            
        Yields:
            Audio data chunks (complete sentences)
        """
        logger.info(f"Starting streaming synthesis with Kokoro: voice={request.voice_id}")
        
        # Map our AudioFormat to Kokoro's response_format
        format_map = {
            AudioFormat.MP3: "mp3",
            AudioFormat.WAV: "wav",
            AudioFormat.FLAC: "flac",
            AudioFormat.OPUS: "opus",
            AudioFormat.PCM: "pcm"
        }
        
        response_format = format_map.get(request.format, "wav")
        
        # Build request payload
        payload = {
            "model": "kokoro",
            "input": request.text,
            "voice": request.voice_id,
            "response_format": response_format,
            "speed": request.speed,
            "stream": True  # Enable streaming
        }
        
        # Add extra parameters if provided
        if request.extra_params:
            if "volume_multiplier" in request.extra_params:
                payload["volume_multiplier"] = request.extra_params["volume_multiplier"]
            
            if "lang_code" in request.extra_params:
                payload["lang_code"] = request.extra_params["lang_code"]
            
            if "normalization_options" in request.extra_params:
                payload["normalization_options"] = request.extra_params["normalization_options"]
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.config.api_url}/v1/audio/speech",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
            
            logger.info("Streaming synthesis completed")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Kokoro streaming error: {e.response.status_code}")
            raise Exception(f"Kokoro streaming failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Kokoro streaming error: {str(e)}")
            raise
    
    async def get_voices(self) -> List[Voice]:
        """
        Get list of available voices from Kokoro API
        
        Returns:
            List of available voices
        """
        logger.info("Fetching voices from Kokoro")
        
        try:
            response = await self.client.get(
                f"{self.config.api_url}/v1/audio/voices"
            )
            response.raise_for_status()
            
            voices_data = response.json()
            
            voices = []
            # Kokoro returns voice list - structure may vary
            if isinstance(voices_data, list):
                for voice_id in voices_data:
                    if isinstance(voice_id, str):
                        # Extract language code from voice name (first letter)
                        lang_code = voice_id[0] if voice_id else "a"
                        
                        voices.append(Voice(
                            id=voice_id,
                            name=voice_id,
                            language=self._map_lang_code(lang_code),
                            gender="unknown"
                        ))
            elif isinstance(voices_data, dict):
                # If it's a dict, iterate through keys or 'voices' field
                voice_list = voices_data.get("voices", voices_data.keys())
                for voice_id in voice_list:
                    if isinstance(voice_id, str):
                        lang_code = voice_id[0] if voice_id else "a"
                        
                        voices.append(Voice(
                            id=voice_id,
                            name=voice_id,
                            language=self._map_lang_code(lang_code),
                            gender="unknown"
                        ))
            
            logger.info(f"Found {len(voices)} voices from Kokoro")
            return voices
            
        except Exception as e:
            logger.error(f"Failed to fetch Kokoro voices: {str(e)}")
            # Return default voices if API fails
            return self._get_default_voices()
    
    def _map_lang_code(self, code: str) -> str:
        """Map Kokoro language code to full language name"""
        lang_map = {
            "a": "American English",
            "b": "British English",
            "j": "Japanese",
            "k": "Korean"
        }
        return lang_map.get(code.lower(), "Unknown")
    
    def _get_default_voices(self) -> List[Voice]:
        """Return default Kokoro voices"""
        default_voices = [
            "af_heart", "af_bella", "af_sarah", "af_nicole",
            "am_adam", "am_michael",
            "bf_emma", "bf_isabella",
            "bm_george", "bm_lewis"
        ]
        
        voices = []
        for voice_id in default_voices:
            lang_code = voice_id[0]
            voices.append(Voice(
                id=voice_id,
                name=voice_id,
                language=self._map_lang_code(lang_code),
                gender="female" if voice_id[1] == "f" else "male"
            ))
        
        return voices
    
    async def validate_voice(self, voice_id: str) -> bool:
        """
        Validate if a voice ID exists
        
        Args:
            voice_id: Voice ID to validate
            
        Returns:
            True if voice exists, False otherwise
        """
        voices = await self.get_voices()
        return any(v.id == voice_id for v in voices)
    
    # Kokoro-specific methods
    
    async def combine_voices(self, voice_ids: List[str]) -> bytes:
        """
        Combine multiple voices into a new voice
        
        Args:
            voice_ids: List of voice IDs to combine (2-4 voices)
            
        Returns:
            Combined voice .pt file data
        """
        logger.info(f"Combining voices: {voice_ids}")
        
        if len(voice_ids) < 2 or len(voice_ids) > 4:
            raise ValueError("Must provide 2-4 voices to combine")
        
        try:
            response = await self.client.post(
                f"{self.config.api_url}/v1/audio/voices/combine",
                json=voice_ids,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            logger.info(f"Successfully combined voices: {len(response.content)} bytes")
            return response.content
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Voice combination failed: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Voice combination failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Voice combination error: {str(e)}")
            raise
    
    async def phonemize_text(self, text: str, language: str = "a") -> Dict[str, Any]:
        """
        Convert text to phonemes
        
        Args:
            text: Text to convert
            language: Language code (default: "a" for American English)
            
        Returns:
            Dict with phonemes and token IDs
        """
        logger.info(f"Phonemizing text: {len(text)} chars, language={language}")
        
        try:
            response = await self.client.post(
                f"{self.config.api_url}/dev/phonemize",
                json={"text": text, "language": language},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Phonemized successfully: {len(result.get('phonemes', ''))} phonemes")
            return result
            
        except Exception as e:
            logger.error(f"Phonemization error: {str(e)}")
            raise
    
    async def generate_from_phonemes(
        self,
        phonemes: str,
        voice_id: str,
        response_format: str = "wav"
    ) -> bytes:
        """
        Generate audio directly from phonemes
        
        Args:
            phonemes: Phoneme string
            voice_id: Voice to use
            response_format: Audio format (default: "wav")
            
        Returns:
            Audio data
        """
        logger.info(f"Generating from phonemes: voice={voice_id}, phoneme_length={len(phonemes)}")
        
        try:
            response = await self.client.post(
                f"{self.config.api_url}/dev/generate_from_phonemes",
                json={"phonemes": phonemes, "voice": voice_id},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            audio_data = response.content
            logger.info(f"Generated from phonemes: {len(audio_data)} bytes")
            return audio_data
            
        except Exception as e:
            logger.error(f"Phoneme generation error: {str(e)}")
            raise
    
    async def generate_with_timestamps(
        self,
        text: str,
        voice_id: str,
        response_format: str = "wav",
        speed: float = 1.0
    ) -> AsyncIterator[bytes]:
        """
        Generate audio with word-level timestamps
        
        Uses the captioned_speech endpoint which returns streaming audio
        with timestamp information in headers/metadata.
        
        Args:
            text: Text to synthesize
            voice_id: Voice to use
            response_format: Audio format
            speed: Playback speed
            
        Yields:
            Audio chunks with timestamp metadata
        """
        logger.info(f"Generating captioned speech: voice={voice_id}")
        
        payload = {
            "model": "kokoro",
            "input": text,
            "voice": voice_id,
            "response_format": response_format,
            "speed": speed,
            "stream": True,
            "return_timestamps": True
        }
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.config.api_url}/dev/captioned_speech",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
            
            logger.info("Captioned speech generation completed")
            
        except Exception as e:
            logger.error(f"Captioned speech error: {str(e)}")
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
