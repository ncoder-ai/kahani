import os
import asyncio
import logging
import time
from typing import Optional, Callable
import numpy as np

from faster_whisper import WhisperModel
import webrtcvad
from app.config import settings

logger = logging.getLogger(__name__)

class STTService:
    """
    Real-time Speech-to-Text service using faster-whisper with VAD.
    
    This service provides real-time transcription with Voice Activity Detection
    using faster-whisper for fast inference and webrtcvad for speech detection.
    """
    
    _instance: Optional["STTService"] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize STT service with model configuration."""
        if not hasattr(self, '_initialized'):
            self.model: Optional[WhisperModel] = None
            self.vad: Optional[webrtcvad.Vad] = None
            self.is_initialized = False
            self._initialization_lock = asyncio.Lock()
            
            # Audio buffering for real-time processing
            self.audio_buffer = np.array([], dtype=np.float32)
            self.buffer_duration = 2.0  # Process every 2 seconds for continuous transcription
            self.sample_rate = 16000
            self.last_processing_time = 0
            self.min_speech_duration = 0.5  # Minimum 0.5s of speech to transcribe
            self.is_processing = False  # Prevent concurrent processing
            
            # Callbacks
            self._on_final_callback: Optional[Callable[[str], None]] = None
            self._on_partial_callback: Optional[Callable[[str], None]] = None
            self._on_vad_start_callback: Optional[Callable[[], None]] = None
            self._on_vad_stop_callback: Optional[Callable[[], None]] = None
            self._on_processing_start_callback: Optional[Callable[[], None]] = None
            self._on_processing_stop_callback: Optional[Callable[[], None]] = None
            self._on_error_callback: Optional[Callable[[Exception], None]] = None
            
            logger.info("STTService initialized (models will be loaded on first use)")


    async def initialize(self, model: str = None):
        """
        Initialize the STT model and VAD.
        Runs in background thread to avoid blocking event loop.
        
        Args:
            model: Whisper model to use (base, small, medium). If None, uses global config.
        """
        async with self._initialization_lock:
            if self.is_initialized:
                return

            # Use provided model or fall back to global config
            model_to_use = model or settings.stt_model
            logger.info(f"Initializing STT service with model: {model_to_use}")
            
            try:
                # Run initialization in thread pool
                await asyncio.to_thread(self._initialize_models, model_to_use)
                
                logger.info(f"STT service initialized successfully")
                self.is_initialized = True
                
            except Exception as e:
                logger.error(f"Failed to initialize STT service: {e}")
                self.model = None
                self.vad = None
                raise
    
    def _initialize_models(self, model: str = None):
        """Blocking initialization runs in separate thread."""
        # Get device configuration
        device, compute_type = self._get_device_config()
        
        # Use provided model or fall back to global config
        model_to_use = model or settings.stt_model
        
        # Initialize faster-whisper model
        self.model = WhisperModel(
            model_to_use,
            device=device,
            compute_type=compute_type,
            download_root=os.path.join(settings.data_dir, "whisper_models")
        )
        
        # Initialize VAD if enabled
        if settings.stt_vad_enabled:
            self.vad = webrtcvad.Vad(settings.stt_vad_sensitivity)
            logger.info(f"WebRTC VAD enabled with sensitivity {settings.stt_vad_sensitivity}")
        
        logger.info(f"Faster-Whisper model '{model_to_use}' loaded on {device} with {compute_type}")

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
                    logger.info(f"No CUDA GPU detected. Falling back to device='cpu', compute_type='int8'")
            except ImportError:
                device = "cpu"
                compute_type = "int8"
                logger.info(f"PyTorch not available. Using device='cpu', compute_type='int8'")
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
        on_error: Optional[Callable[[Exception], None]] = None,
        model: str = None
    ):
        """Start real-time transcription with callbacks."""
        await self.initialize(model)
        
        if not self.model:
            raise RuntimeError("STT service not initialized")
        
        # Set up callbacks
        self._on_final_callback = on_final
        self._on_partial_callback = on_partial
        self._on_vad_start_callback = on_vad_start
        self._on_vad_stop_callback = on_vad_stop
        self._on_processing_start_callback = on_processing_start
        self._on_processing_stop_callback = on_processing_stop
        self._on_error_callback = on_error
        
        # Reset buffer
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_processing_time = time.time()
        
        logger.info("STT transcription started")

    async def stop_transcription(self):
        """Stop real-time transcription."""
        # Clear buffer
        self.audio_buffer = np.array([], dtype=np.float32)
        logger.info("STT transcription stopped")

    async def feed_audio_data(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Feed audio data to the STT processor with buffering.
        
        Args:
            audio_data: Raw audio data (PCM format)
            sample_rate: Sample rate of the audio (default 16000)
        """
        if not self.is_initialized or not self.model:
            logger.warning("STT service not initialized")
            return
            
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize to float32 range [-1, 1]
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Add to buffer
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_float])
            
            # Check if we have enough audio to process
            buffer_duration = len(self.audio_buffer) / sample_rate
            current_time = time.time()
            
            # Process every 2 seconds for continuous real-time transcription
            # OR if we have a lot of audio buffered (>5s means user is speaking continuously)
            should_process = (
                buffer_duration >= self.buffer_duration or 
                buffer_duration >= 5.0
            ) and not self.is_processing
            
            if should_process and len(self.audio_buffer) > 0:
                # Process in background thread
                asyncio.create_task(self._process_buffer())
            
        except Exception as e:
            logger.error(f"Error feeding audio data: {e}")
            if self._on_error_callback:
                await self._on_error_callback(e)

    async def _process_buffer(self):
        """Process accumulated audio buffer for continuous transcription."""
        if len(self.audio_buffer) == 0 or self.is_processing:
            return
        
        self.is_processing = True
        
        try:
            # Process current buffer and clear it completely
            audio_to_process = self.audio_buffer.copy()
            self.audio_buffer = np.array([], dtype=np.float32)
            
            self.last_processing_time = time.time()
            
            if self._on_processing_start_callback:
                await self._on_processing_start_callback()
            
            # Check VAD if enabled (permissive for continuous speech)
            if self.vad and not await self._check_vad(audio_to_process):
                if self._on_processing_stop_callback:
                    await self._on_processing_stop_callback()
                return
            
            # Transcribe in background thread
            text = await asyncio.to_thread(self._transcribe, audio_to_process)
            
            if text and text.strip():
                # Send transcribed text directly (no deduplication needed)
                if self._on_partial_callback:
                    await self._on_partial_callback(text.strip())
            
            if self._on_processing_stop_callback:
                await self._on_processing_stop_callback()
                
        except Exception as e:
            logger.error(f"Error processing buffer: {e}")
            if self._on_error_callback:
                await self._on_error_callback(e)
        finally:
            self.is_processing = False

    async def _check_vad(self, audio_data: np.ndarray) -> bool:
        """Check if audio contains speech using VAD."""
        if not self.vad:
            return True
            
        try:
            # Convert to 16-bit PCM
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            # Check 30ms frames
            frame_length = int(self.sample_rate * 0.03)
            speech_frames = 0
            total_frames = 0
            
            for i in range(0, len(audio_int16), frame_length):
                frame = audio_int16[i:i+frame_length]
                if len(frame) == frame_length:
                    total_frames += 1
                    if self.vad.is_speech(frame.tobytes(), self.sample_rate):
                        speech_frames += 1
            
            # Consider speech if >30% of frames contain speech (permissive for continuous speech)
            return total_frames > 0 and (speech_frames / total_frames) > 0.3
            
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return True  # Continue processing if VAD fails

    def _transcribe(self, audio_data: np.ndarray) -> str:
        """Transcribe audio using faster-whisper (runs in thread)."""
        try:
            segments, info = self.model.transcribe(
                audio_data,
                language=settings.stt_language,
                beam_size=5,  # Better quality
                word_timestamps=False,
                vad_filter=False,  # We handle VAD ourselves
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=None,  # Disable - was rejecting valid speech
                no_speech_threshold=0.95  # Very permissive
            )
            
            # Combine segments
            full_text = ""
            for segment in segments:
                text = segment.text.strip()
                if text:
                    full_text += text + " "
            
            return full_text.strip()
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

    async def transcribe_audio_file(self, audio_file_path: str) -> str:
        """Transcribe an audio file (for testing)."""
        await self.initialize()
        
        if not self.model:
            raise RuntimeError("STT service not initialized")
        
        try:
            text = await asyncio.to_thread(self._transcribe_file, audio_file_path)
            return text
        except Exception as e:
            logger.error(f"Error transcribing audio file: {e}")
            raise
    
    def _transcribe_file(self, audio_file_path: str) -> str:
        """Transcribe file in thread."""
        segments, info = self.model.transcribe(
            audio_file_path,
            language=settings.stt_language,
            beam_size=5,
            word_timestamps=False,
            vad_filter=False,
            temperature=0.0,
            log_prob_threshold=None,
            no_speech_threshold=0.95
        )
        
        full_text = ""
        for segment in segments:
            text = segment.text.strip()
            if text:
                full_text += text + " "
        
        return full_text.strip()

# Global instance
stt_service = STTService()
