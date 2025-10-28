import os
import asyncio
import logging
import io
import wave
import tempfile
from typing import Optional, Callable, Dict, Any
import threading
import queue
import time

import numpy as np
from RealtimeSTT import AudioToTextRecorder
from app.config import settings

logger = logging.getLogger(__name__)

class STTService:
    """
    Real-time Speech-to-Text service using RealtimeSTT.
    
    This service provides true real-time transcription with VAD (Voice Activity Detection)
    and streaming audio processing using the RealtimeSTT library.
    """
    
    _instance: Optional["STTService"] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize STT service with model configuration.
        """
        if not hasattr(self, '_initialized'):
            self.recorder: Optional[AudioToTextRecorder] = None
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
            
            # Threading for RealtimeSTT
            self._recorder_thread: Optional[threading.Thread] = None
            self._stop_recording = threading.Event()
            self._audio_queue = queue.Queue()
            
            logger.info("STTService initialized (models will be loaded on first use)")

    async def initialize(self):
        """
        Initialize the STT model and RealtimeSTT recorder.
        This is called lazily on first use to avoid startup delays.
        """
        async with self._initialization_lock:
            if self.is_initialized:
                return

            logger.info(f"Initializing STT service with model: {settings.stt_model}")
            
            try:
                # Get device configuration
                device, compute_type = self._get_device_config()
                
                # Configure RealtimeSTT with faster-whisper backend
                self.recorder = AudioToTextRecorder(
                    model=f"faster-whisper:{settings.stt_model}",
                    language=settings.stt_language,
                    use_microphone=False,  # We'll feed audio manually
                    device=device,
                    compute_type=compute_type,
                    enable_realtime_transcription=True,
                    enable_realtime_audio=True,
                    enable_vad=settings.stt_vad_enabled,
                    vad_sensitivity=settings.stt_vad_sensitivity,
                    silence_duration=1.0,  # 1 second of silence to finalize
                    phrase_timeout=3.0,    # 3 seconds max phrase length
                    min_recognition_confidence=0.3,
                    min_audio_length=0.1,  # 100ms minimum audio length
                    max_audio_length=30.0, # 30 seconds maximum audio length
                    audio_padding_duration=0.2,  # 200ms padding
                    spinner=False,  # Disable spinner for server use
                    level=logging.WARNING,  # Reduce log verbosity
                    model_path=os.path.join(settings.data_dir, "whisper_models")
                )
                
                logger.info(f"RealtimeSTT initialized with model '{settings.stt_model}' on {device} with {compute_type} compute type")
                self.is_initialized = True
                
            except Exception as e:
                logger.error(f"Failed to initialize STT service: {e}")
                self.recorder = None
                raise

    def _get_device_config(self):
        """Get device and compute type configuration."""
        device = settings.stt_device
        compute_type = settings.stt_compute_type

        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    if compute_type not in ["float16", "int8_float16", "int8"]:
                        compute_type = "float16"
                    logger.info(f"Auto-detected CUDA GPU. Using device='cuda', compute_type='{compute_type}'")
                else:
                    device = "cpu"
                    if compute_type not in ["int8"]:
                        compute_type = "int8"
                    logger.info(f"No CUDA GPU detected. Falling back to device='cpu', compute_type='{compute_type}'")
            except ImportError:
                device = "cpu"
                if compute_type not in ["int8"]:
                    compute_type = "int8"
                logger.info(f"PyTorch not installed or CUDA not available. Falling back to device='cpu', compute_type='{compute_type}'")
        elif device == "cuda":
            if compute_type not in ["float16", "int8_float16", "int8"]:
                compute_type = "float16"
        elif device == "cpu":
            if compute_type not in ["int8"]:
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
        
        if not self.recorder:
            raise RuntimeError("STT service not initialized")
        
        # Set up callbacks
        self._on_final_callback = on_final
        self._on_partial_callback = on_partial
        self._on_vad_start_callback = on_vad_start
        self._on_vad_stop_callback = on_vad_stop
        self._on_processing_start_callback = on_processing_start
        self._on_processing_stop_callback = on_processing_stop
        self._on_error_callback = on_error
        
        # Start the recorder thread
        self._stop_recording.clear()
        self._recorder_thread = threading.Thread(target=self._recorder_worker, daemon=True)
        self._recorder_thread.start()
        
        logger.info("STT transcription started")

    def _recorder_worker(self):
        """Worker thread that processes audio and generates transcriptions."""
        try:
            while not self._stop_recording.is_set():
                try:
                    # Get audio data from queue (with timeout)
                    audio_data = self._audio_queue.get(timeout=0.1)
                    
                    if audio_data is None:  # Shutdown signal
                        break
                    
                    # Process audio with RealtimeSTT
                    if self._on_processing_start_callback:
                        asyncio.create_task(self._on_processing_start_callback())
                    
                    # Feed audio to recorder
                    self.recorder.feed_audio(audio_data)
                    
                    # Get transcription results
                    text = self.recorder.text()
                    if text and text.strip():
                        # Determine if this is partial or final
                        is_final = self.recorder.is_final()
                        
                        if is_final and self._on_final_callback:
                            asyncio.create_task(self._on_final_callback(text.strip()))
                        elif not is_final and self._on_partial_callback:
                            asyncio.create_task(self._on_partial_callback(text.strip()))
                    
                    # Check VAD status
                    if hasattr(self.recorder, 'is_speaking'):
                        is_speaking = self.recorder.is_speaking()
                        if is_speaking and self._on_vad_start_callback:
                            asyncio.create_task(self._on_vad_start_callback())
                        elif not is_speaking and self._on_vad_stop_callback:
                            asyncio.create_task(self._on_vad_stop_callback())
                    
                    if self._on_processing_stop_callback:
                        asyncio.create_task(self._on_processing_stop_callback())
                        
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error in recorder worker: {e}")
                    if self._on_error_callback:
                        asyncio.create_task(self._on_error_callback(e))
                        
        except Exception as e:
            logger.error(f"Fatal error in recorder worker: {e}")
            if self._on_error_callback:
                asyncio.create_task(self._on_error_callback(e))

    async def stop_transcription(self):
        """Stop real-time transcription."""
        if self._recorder_thread and self._recorder_thread.is_alive():
            self._stop_recording.set()
            self._audio_queue.put(None)  # Signal shutdown
            self._recorder_thread.join(timeout=5.0)
        
        logger.info("STT transcription stopped")

    async def feed_audio_data(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Feed audio data to the STT processor.
        
        Args:
            audio_data: Raw audio data (PCM format)
            sample_rate: Sample rate of the audio (default 16000)
        """
        if not self.is_initialized or not self.recorder:
            logger.warning("STT service not initialized")
            return
            
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize to float32 range [-1, 1]
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Add to processing queue
            self._audio_queue.put(audio_float)
            
        except Exception as e:
            logger.error(f"Error feeding audio data: {e}")
            if self._on_error_callback:
                asyncio.create_task(self._on_error_callback(e))

    async def transcribe_audio_file(self, audio_file_path: str) -> str:
        """
        Transcribe an audio file (for testing purposes).
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            Transcribed text
        """
        await self.initialize()
        
        if not self.recorder:
            raise RuntimeError("STT service not initialized")
        
        try:
            # Use RealtimeSTT to transcribe the file
            with open(audio_file_path, 'rb') as f:
                audio_data = f.read()
            
            # Convert to numpy array and normalize
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Feed audio in chunks
            chunk_size = 16000  # 1 second at 16kHz
            for i in range(0, len(audio_float), chunk_size):
                chunk = audio_float[i:i+chunk_size]
                self.recorder.feed_audio(chunk)
            
            # Get final transcription
            text = self.recorder.text()
            return text.strip() if text else ""
            
        except Exception as e:
            logger.error(f"Error transcribing audio file: {e}")
            raise

# Global instance
stt_service = STTService()