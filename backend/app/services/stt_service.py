"""
STT Service - Real-time Speech-to-Text using RealtimeSTT

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
from RealtimeSTT import AudioToTextRecorder
from faster_whisper import WhisperModel
from app.config import settings

logger = logging.getLogger(__name__)


class STTService:
    """
    Real-time Speech-to-Text service using RealtimeSTT and faster-whisper.
    """
    
    def __init__(self):
        """
        Initialize STT service with model configuration.
        """
        self.model = None
        self.recorder = None
        self.is_initialized = False
        self._initialization_lock = asyncio.Lock()
        
    async def initialize(self):
        """
        Initialize the STT model and recorder.
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
                
                # Initialize RealtimeSTT recorder
                self.recorder = AudioToTextRecorder(
                    model=settings.stt_model,
                    language=settings.stt_language,
                    use_microphone=False,  # We'll feed audio manually
                    enable_realtime_transcription=True,
                    level=settings.stt_vad_sensitivity,
                    spinner=False,
                    use_microphone_device_index=None,
                    on_realtime_transcription_stabilized=self._on_transcription_stabilized,
                    on_realtime_transcription_update=self._on_transcription_update,
                    on_vad_detect_start=self._on_vad_start,
                    on_vad_detect_stop=self._on_vad_stop,
                    on_processing_started=self._on_processing_started,
                    on_processing_stopped=self._on_processing_stopped,
                    on_processing_error=self._on_processing_error,
                )
                
                self.is_initialized = True
                logger.info("STT service initialized successfully")
                
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
    
    def _on_transcription_stabilized(self, text: str):
        """Called when a transcription is finalized."""
        logger.debug(f"STT Final: {text}")
        if hasattr(self, '_on_final_callback') and self._on_final_callback:
            self._on_final_callback(text)
    
    def _on_transcription_update(self, text: str):
        """Called during live transcription updates."""
        logger.debug(f"STT Partial: {text}")
        if hasattr(self, '_on_partial_callback') and self._on_partial_callback:
            self._on_partial_callback(text)
    
    def _on_vad_start(self):
        """Called when voice activity is detected."""
        logger.debug("STT VAD: Speech started")
        if hasattr(self, '_on_vad_start_callback') and self._on_vad_start_callback:
            self._on_vad_start_callback()
    
    def _on_vad_stop(self):
        """Called when voice activity stops."""
        logger.debug("STT VAD: Speech stopped")
        if hasattr(self, '_on_vad_stop_callback') and self._on_vad_stop_callback:
            self._on_vad_stop_callback()
    
    def _on_processing_started(self):
        """Called when processing starts."""
        logger.debug("STT: Processing started")
        if hasattr(self, '_on_processing_start_callback') and self._on_processing_start_callback:
            self._on_processing_start_callback()
    
    def _on_processing_stopped(self):
        """Called when processing stops."""
        logger.debug("STT: Processing stopped")
        if hasattr(self, '_on_processing_stop_callback') and self._on_processing_stop_callback:
            self._on_processing_stop_callback()
    
    def _on_processing_error(self, error: Exception):
        """Called when processing encounters an error."""
        logger.error(f"STT Processing error: {error}")
        if hasattr(self, '_on_error_callback') and self._on_error_callback:
            self._on_error_callback(error)
    
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
        
        # Start the recorder
        if self.recorder:
            self.recorder.start()
            logger.info("STT transcription started")
    
    async def stop_transcription(self):
        """Stop real-time transcription."""
        if self.recorder:
            self.recorder.stop()
            logger.info("STT transcription stopped")
    
    async def feed_audio_data(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Feed audio data to the STT processor.
        
        Args:
            audio_data: Raw audio data (PCM format)
            sample_rate: Sample rate of the audio (default 16000)
        """
        if not self.recorder:
            logger.warning("STT recorder not initialized")
            return
            
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize to float32 range [-1, 1]
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Feed to recorder
            self.recorder.feed_audio(audio_float)
            
        except Exception as e:
            logger.error(f"Error feeding audio data: {e}")
            if hasattr(self, '_on_error_callback') and self._on_error_callback:
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
        if self.recorder:
            try:
                self.recorder.stop()
            except:
                pass
            self.recorder = None
        
        self.model = None
        self.is_initialized = False
        logger.info("STT service cleaned up")


# Global STT service instance
stt_service = STTService()
