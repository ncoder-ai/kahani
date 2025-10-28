"""
STT Service - Real-time Speech-to-Text using faster-whisper

Handles:
- Real-time audio transcription
- Voice Activity Detection (VAD)
- Audio format conversion
- Model initialization and management
"""

import os
import asyncio
import logging
import io
import wave
import tempfile
from typing import Optional, Callable, Dict, Any
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
from app.config import settings

logger = logging.getLogger(__name__)


class STTService:
    """
    Real-time Speech-to-Text service using faster-whisper.
    """
    
    def __init__(self):
        """
        Initialize STT service with model configuration.
        """
        self.model = None
        self.is_initialized = False
        self._initialization_lock = asyncio.Lock()
        
        # Callbacks
        self._on_final_callback: Optional[Callable[[str], None]] = None
        self._on_partial_callback: Optional[Callable[[str], None]] = None
        self._on_vad_start_callback: Optional[Callable[[], None]] = None
        self._on_vad_stop_callback: Optional[Callable[[], None]] = None
        self._on_processing_start_callback: Optional[Callable[[], None]] = None
        self._on_processing_stop_callback: Optional[Callable[[], None]] = None
        self._on_error_callback: Optional[Callable[[Exception], None]] = None
        
    async def initialize(self):
        """
        Initialize the STT model.
        This is called lazily on first use to avoid startup delays.
        """
        if self.is_initialized:
            return
            
        async with self._initialization_lock:
            if self.is_initialized:
                return
                
            try:
                logger.info(f"Initializing STT service with model: {settings.stt_model}")
                
                # Determine device and compute type
                device, compute_type = self._get_device_config()
                
                # Initialize faster-whisper model
                self.model = WhisperModel(
                    model_size_or_path=settings.stt_model,
                    device=device,
                    compute_type=compute_type
                )
                
                logger.info(f"STT model loaded: {settings.stt_model} on {device} with {compute_type}")
                self.is_initialized = True
                
            except Exception as e:
                logger.error(f"Failed to initialize STT service: {e}")
                raise
    
    def _get_device_config(self) -> tuple[str, str]:
        """
        Determine device and compute type based on configuration.
        """
        if settings.stt_device == "auto":
            # Try CUDA first, fallback to CPU
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = settings.stt_compute_type
                    logger.info("Using CUDA for STT")
                else:
                    device = "cpu"
                    compute_type = "int8"  # Only int8 works well on CPU
                    logger.info("CUDA not available, using CPU for STT")
            except ImportError:
                device = "cpu"
                compute_type = "int8"
                logger.info("PyTorch not available, using CPU for STT")
        elif settings.stt_device == "cuda":
            device = "cuda"
            compute_type = settings.stt_compute_type
        else:  # cpu
            device = "cpu"
            compute_type = "int8"
            
        return device, compute_type
    
    async def start_transcription(
        self,
        on_final: Optional[Callable[[str], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        on_vad_start: Optional[Callable[[], None]] = None,
        on_vad_stop: Optional[Callable[[], None]] = None,
        on_processing_start: Optional[Callable[[], None]] = None,
        on_processing_stop: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        Start real-time transcription with callbacks.
        
        Args:
            on_final: Called when transcription is finalized
            on_partial: Called during live transcription updates
            on_vad_start: Called when voice activity starts
            on_vad_stop: Called when voice activity stops
            on_processing_start: Called when processing starts
            on_processing_stop: Called when processing stops
            on_error: Called on processing errors
        """
        await self.initialize()
        
        # Set up callbacks
        self._on_final_callback = on_final
        self._on_partial_callback = on_partial
        self._on_vad_start_callback = on_vad_start
        self._on_vad_stop_callback = on_vad_stop
        self._on_processing_start_callback = on_processing_start
        self._on_processing_stop_callback = on_processing_stop
        self._on_error_callback = on_error
        
        logger.info("STT transcription started")
    
    async def stop_transcription(self):
        """Stop real-time transcription."""
        logger.info("STT transcription stopped")
    
    async def feed_audio_data(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Feed audio data to the STT processor.
        
        Args:
            audio_data: Raw audio data (PCM format)
            sample_rate: Sample rate of the audio (default 16000)
        """
        if not self.model:
            logger.warning("STT model not initialized")
            return
            
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize to float32 range [-1, 1]
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # For now, we'll process the entire audio chunk at once
            # In a real implementation, you'd want to buffer and process in chunks
            await self._process_audio_chunk(audio_float, sample_rate)
            
        except Exception as e:
            logger.error(f"Error feeding audio data: {e}")
            if self._on_error_callback:
                self._on_error_callback(e)
    
    async def _process_audio_chunk(self, audio_data: np.ndarray, sample_rate: int):
        """
        Process a chunk of audio data.
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate of the audio
        """
        try:
            if self._on_processing_start_callback:
                self._on_processing_start_callback()
            
            # Use faster-whisper to transcribe the audio
            segments, info = self.model.transcribe(
                audio_data,
                language=settings.stt_language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=settings.stt_vad_enabled,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Process segments
            full_text = ""
            for segment in segments:
                text = segment.text.strip()
                if text:
                    full_text += text + " "
                    
                    # Send partial updates
                    if self._on_partial_callback:
                        self._on_partial_callback(text)
            
            # Send final result
            if full_text.strip() and self._on_final_callback:
                self._on_final_callback(full_text.strip())
            
            if self._on_processing_stop_callback:
                self._on_processing_stop_callback()
                
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            if self._on_error_callback:
                self._on_error_callback(e)
    
    async def transcribe_audio_file(self, audio_file_path: str) -> str:
        """
        Transcribe a single audio file (for testing purposes).
        
        Args:
            audio_file_path: Path to audio file
            
        Returns:
            Transcribed text
        """
        await self.initialize()
        
        if not self.model:
            raise RuntimeError("STT model not initialized")
        
        try:
            # Use faster-whisper directly for file transcription
            segments, info = self.model.transcribe(
                audio_file_path,
                language=settings.stt_language,
                beam_size=5,
                word_timestamps=True
            )
            
            # Combine all segments
            text = " ".join([segment.text for segment in segments])
            return text.strip()
            
        except Exception as e:
            logger.error(f"Error transcribing audio file: {e}")
            raise
    
    def cleanup(self):
        """Clean up resources."""
        self.model = None
        self.is_initialized = False
        logger.info("STT service cleaned up")


# Global STT service instance
stt_service = STTService()