import os
import asyncio
import logging
import re
import time
from typing import Optional, Callable
from collections import deque

import numpy as np
import torch
from faster_whisper import WhisperModel
from app.config import settings

logger = logging.getLogger(__name__)


class ProfessionalSTTService:
    """
    Professional-grade Speech-to-Text service with:
    - Dynamic buffering with silence detection
    - Silero VAD for accurate voice activity detection
    - Sentence boundary detection
    - Sliding window with overlap for context continuity
    - Post-processing for natural output
    """
    
    _instance: Optional["ProfessionalSTTService"] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            # Core models
            self.whisper_model: Optional[WhisperModel] = None
            self.silero_vad_model = None
            self.is_initialized = False
            self._initialization_lock = asyncio.Lock()
            
            # Dynamic buffering for sentence-aware transcription
            self.audio_buffer = np.array([], dtype=np.float32)
            self.sample_rate = 16000
            
            # Silence detection state
            self.speech_timestamps = []  # List of (start, end) speech segments
            self.is_speaking = False
            self.speech_start_time = None
            self.last_speech_time = None
            
            # Sliding window for context continuity
            self.window_size_ms = 1500  # 1.5 second overlap
            self.last_window_audio = np.array([], dtype=np.float32)
            
            # Sentence accumulation
            self.accumulated_sentence = ""
            self.last_transcription_time = 0
            
            # Audio position tracking (for deduplication)
            self.total_audio_processed = 0
            
            # Processing state
            self.is_processing = False
            self.processing_lock = asyncio.Lock()
            
            # Callbacks
            self._on_partial_callback: Optional[Callable[[str], None]] = None
            self._on_final_callback: Optional[Callable[[str], None]] = None
            self._on_error_callback: Optional[Callable[[Exception], None]] = None
            
            logger.info("Professional STT Service initialized")

    async def initialize(self, model: str = None):
        """Initialize Whisper and Silero VAD models."""
        async with self._initialization_lock:
            if self.is_initialized:
                return

            model_to_use = model or settings.stt_model
            logger.info(f"Initializing STT with Whisper model: {model_to_use}")
            
            try:
                await asyncio.to_thread(self._initialize_models, model_to_use)
                self.is_initialized = True
                logger.info("STT initialization complete")
                
            except Exception as e:
                logger.error(f"Failed to initialize STT: {e}", exc_info=True)
                raise
    
    def _initialize_models(self, model: str):
        """Load models in background thread."""
        # Initialize Whisper
        device, compute_type = self._get_device_config()
        self.whisper_model = WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
            download_root=os.path.join(settings.data_dir, "whisper_models")
        )
        logger.info(f"Whisper '{model}' loaded on {device} with {compute_type}")
        
        # Initialize Silero VAD
        if settings.stt_use_silero_vad:
            try:
                # Set TORCH_HOME to use data directory (consistent with download location)
                vad_dir = os.path.join(settings.data_dir, "vad_models")
                os.makedirs(vad_dir, exist_ok=True)
                os.environ['TORCH_HOME'] = vad_dir
                
                self.silero_vad_model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=False,
                    onnx=False
                )
                logger.info("Silero VAD model loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load Silero VAD, will use simpler detection: {e}")
                self.silero_vad_model = None

    def _get_device_config(self):
        """Determine optimal device and compute type."""
        device = settings.stt_device
        compute_type = settings.stt_compute_type

        if device == "auto":
            try:
                if torch.cuda.is_available():
                    device = "cuda"
                    if compute_type not in ["float16", "int8_float16", "int8"]:
                        compute_type = "float16"
                    logger.info(f"Using CUDA GPU with {compute_type}")
                else:
                    device = "cpu"
                    compute_type = "int8"
                    logger.info(f"Using CPU with {compute_type}")
            except Exception:
                device = "cpu"
                compute_type = "int8"
                logger.info(f"Fallback to CPU with {compute_type}")
        
        return device, compute_type

    async def start_transcription(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        model: str = None
    ):
        """Start real-time transcription with professional quality."""
        await self.initialize(model)
        
        if not self.whisper_model:
            raise RuntimeError("Whisper model not initialized")
        
        # Set callbacks
        self._on_partial_callback = on_partial
        self._on_final_callback = on_final
        self._on_error_callback = on_error
        
        # Reset state
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_window_audio = np.array([], dtype=np.float32)
        self.accumulated_sentence = ""
        self.is_speaking = False
        self.speech_start_time = None
        self.last_speech_time = None
        self.speech_timestamps = []
        self.total_audio_processed = 0
        
        logger.info("Professional STT transcription started")

    async def stop_transcription(self):
        """Stop transcription and process any remaining audio."""
        # Process any remaining audio in buffer
        if len(self.audio_buffer) > 0:
            await self._process_final_buffer()
        
        # Send final transcript
        if self.accumulated_sentence and self._on_final_callback:
            await self._on_final_callback(self.accumulated_sentence)
        
        # NOW reset
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_window_audio = np.array([], dtype=np.float32)
        self.accumulated_sentence = ""
        self.is_speaking = False
        self.total_audio_processed = 0
        
        logger.info("STT transcription stopped")

    async def feed_audio_data(self, audio_data: bytes, sample_rate: int = 16000):
        """
        Feed audio data with intelligent buffering and silence detection.
        """
        if not self.whisper_model:
            logger.warning("Whisper model not initialized")
            return
        
        try:
            # Convert bytes to float32
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Add to buffer
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_float])
            
            # Detect speech/silence using Silero VAD
            is_speech = await self._detect_speech(audio_float)
            current_time = time.time()
            
            # Update speech state
            if is_speech:
                if not self.is_speaking:
                    # Speech started
                    self.is_speaking = True
                    self.speech_start_time = current_time
                    logger.debug("Speech detected - started buffering")
                
                self.last_speech_time = current_time
            
            # Check if we should process the buffer
            should_process = False
            reason = ""
            
            if self.is_speaking:
                buffer_duration = len(self.audio_buffer) / self.sample_rate
                
                # Silence detected after speech
                if self.last_speech_time and (current_time - self.last_speech_time) > (settings.stt_min_silence_duration_ms / 1000.0):
                    should_process = True
                    reason = "silence after speech (sentence boundary)"
                    self.is_speaking = False
                
                # Maximum speech duration reached
                elif buffer_duration >= settings.stt_max_speech_duration_s:
                    should_process = True
                    reason = "maximum duration reached"
            
            # Process buffer if conditions met
            if should_process and len(self.audio_buffer) > 0 and not self.is_processing:
                logger.debug(f"Processing buffer: {reason}")
                asyncio.create_task(self._process_buffer_with_context())
                
        except Exception as e:
            logger.error(f"Error feeding audio: {e}", exc_info=True)
            if self._on_error_callback:
                await self._on_error_callback(e)

    async def _detect_speech(self, audio_chunk: np.ndarray) -> bool:
        """Detect speech in audio chunk using Silero VAD."""
        if not self.silero_vad_model:
            # Fallback: simple energy-based detection
            energy = np.sqrt(np.mean(audio_chunk ** 2))
            return energy > 0.01
        
        try:
            # Silero VAD needs exactly 512 samples for 16kHz
            required_samples = 512
            
            # Process audio in 512-sample chunks
            is_speech = False
            for i in range(0, len(audio_chunk), required_samples):
                chunk = audio_chunk[i:i+required_samples]
                if len(chunk) == required_samples:
                    audio_tensor = torch.from_numpy(chunk).float()
                    speech_prob = await asyncio.to_thread(
                        self.silero_vad_model,
                        audio_tensor,
                        self.sample_rate
                    )
                    if float(speech_prob) > settings.stt_vad_threshold:
                        is_speech = True
                        break
            
            return is_speech
            
        except Exception as e:
            logger.warning(f"VAD error: {e}")
            # Fallback to energy detection
            energy = np.sqrt(np.mean(audio_chunk ** 2))
            return energy > 0.01

    def _is_duplicate_text(self, new_text: str, existing_text: str) -> bool:
        """Check if new_text is already in existing_text (with fuzzy matching)."""
        if not existing_text:
            return False
        
        # Check if new text is substring of existing (allowing for minor variations)
        new_words = new_text.lower().split()
        existing_words = existing_text.lower().split()
        
        # If first 5 words of new text match last 5-10 words of existing, it's duplicate
        if len(new_words) >= 5 and len(existing_words) >= 5:
            new_start = ' '.join(new_words[:5])
            existing_end = ' '.join(existing_words[-10:])
            
            if new_start in existing_end:
                logger.debug(f"Detected duplicate: '{new_start}' found in '{existing_end}'")
                return True
        
        return False

    async def _process_buffer_with_context(self):
        """Process buffer with sliding window for context continuity."""
        if self.is_processing or len(self.audio_buffer) == 0:
            return
        
        async with self.processing_lock:
            self.is_processing = True
            
            try:
                # No overlap - process sequential chunks for reliability
                audio_to_process = self.audio_buffer.copy()
                
                # Track audio position to prevent re-processing
                audio_start_pos = self.total_audio_processed
                self.total_audio_processed += len(audio_to_process)
                
                # Clear buffer for new audio
                self.audio_buffer = np.array([], dtype=np.float32)
                
                logger.debug(f"Processing audio from {audio_start_pos} to {self.total_audio_processed}")
                
                # Transcribe with optimized parameters
                text = await asyncio.to_thread(self._transcribe_with_quality, audio_to_process)
                
                if text and text.strip():
                    # Post-process for natural output
                    processed_text = self._post_process_text(text.strip())
                    
                    # Check for duplicate before appending
                    if not self._is_duplicate_text(processed_text, self.accumulated_sentence):
                        # ALWAYS append during recording session - NEVER reset
                        if self.accumulated_sentence:
                            # Add space between chunks
                            self.accumulated_sentence += " " + processed_text
                        else:
                            self.accumulated_sentence = processed_text
                        
                        # Send the FULL accumulated sentence as partial
                        if self._on_partial_callback:
                            await self._on_partial_callback(self.accumulated_sentence)
                        
                        logger.info(f"[STT] New chunk: '{processed_text[:50]}...'")
                        logger.info(f"[STT] Accumulated: '{self.accumulated_sentence[:100]}...' (length: {len(self.accumulated_sentence)})")
                    else:
                        logger.info(f"[STT] Skipped duplicate: '{processed_text[:50]}...'")
                    
            except Exception as e:
                logger.error(f"Error processing buffer: {e}", exc_info=True)
                if self._on_error_callback:
                    await self._on_error_callback(e)
            finally:
                self.is_processing = False

    async def _process_final_buffer(self):
        """Process remaining buffer when stopping."""
        if len(self.audio_buffer) > 0:
            try:
                text = await asyncio.to_thread(self._transcribe_with_quality, self.audio_buffer)
                if text and text.strip():
                    processed_text = self._post_process_text(text.strip())
                    
                    # Append to accumulated sentence (same logic as main processing)
                    if self.accumulated_sentence:
                        self.accumulated_sentence += " " + processed_text
                    else:
                        self.accumulated_sentence = processed_text
                    
                    logger.debug(f"Final buffer processed: {processed_text[:50]}... (Full: {self.accumulated_sentence[:100]}...)")
                    
            except Exception as e:
                logger.error(f"Error processing final buffer: {e}", exc_info=True)

    def _transcribe_with_quality(self, audio_data: np.ndarray) -> str:
        """
        Transcribe audio with optimized parameters for quality.
        """
        try:
            # Optimized Whisper parameters for quality and speed
            segments, info = self.whisper_model.transcribe(
                audio_data,
                language=settings.stt_language,
                
                # Quality settings
                beam_size=5,  # Beam search for better accuracy
                best_of=5,  # Consider multiple hypotheses
                temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],  # Temperature fallback for difficult audio
                
                # Context and flow
                condition_on_previous_text=True,  # Use context from previous segments
                initial_prompt="Transcribe the following conversational speech naturally with proper punctuation and capitalization.",
                
                # Efficiency
                word_timestamps=False,
                vad_filter=False,  # We handle VAD ourselves
                
                # Thresholds
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,  # More permissive
                no_speech_threshold=0.6,  # Standard threshold
                
                # Prevent hallucinations
                repetition_penalty=1.2,
                no_repeat_ngram_size=3
            )
            
            # Combine segments with natural spacing
            full_text = ""
            for segment in segments:
                text = segment.text.strip()
                if text:
                    if full_text and not full_text.endswith(('.', '!', '?', ',')):
                        full_text += " "
                    full_text += text
            
            return full_text.strip()
            
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            raise

    def _post_process_text(self, text: str) -> str:
        """
        Post-process transcription for natural output:
        - Fix capitalization
        - Clean up spacing
        - Fix common transcription errors
        - Remove Whisper hallucination patterns (attribution text)
        """
        if not text:
            return text
        
        # Remove Whisper hallucination patterns (attribution text)
        # Patterns like "Transcribed by ESO, translated by –" or "Transcribed by..." etc.
        hallucination_patterns = [
            r'\s*\.\s*[Tt]ranscribed\s+by\s+[^\.]+',
            r'\s*\.\s*[Tt]ranslated\s+by\s+[^\.]+',
            r'\s*\.\s*[Tt]ranscribed\s+by\s+[^\.]+,\s*[Tt]ranslated\s+by\s+[^\.]+',
            r'\s*\.\s*[Tt]ranslated\s+by\s+[^\.]+,\s*[Tt]ranscribed\s+by\s+[^\.]+',
            r'\s*\.\s*[Tt]ranscribed\s+and\s+[Tt]ranslated\s+by\s+[^\.]+',
            r'\s*–\s*$',  # Trailing em-dash or hyphen
            r'\s*—\s*$',  # Trailing em-dash (Unicode)
        ]
        
        for pattern in hallucination_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Remove any trailing periods that might be left after removing hallucinations
        text = re.sub(r'\.+$', '', text)
        
        # Ensure first letter is capitalized
        text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
        
        # Fix spacing around punctuation
        text = text.replace(" ,", ",")
        text = text.replace(" .", ".")
        text = text.replace(" !", "!")
        text = text.replace(" ?", "?")
        text = text.replace(" '", "'")
        
        # Fix common transcription artifacts
        text = text.replace("  ", " ")
        text = text.strip()
        
        # Capitalize after sentence endings
        for punct in ['. ', '! ', '? ']:
            parts = text.split(punct)
            text = punct.join(p[0].upper() + p[1:] if len(p) > 0 else p for p in parts)
        
        return text

    async def transcribe_audio_file(self, audio_file_path: str) -> str:
        """Transcribe a complete audio file."""
        await self.initialize()
        if not self.whisper_model:
            raise RuntimeError("Whisper model not initialized")
        
        text = await asyncio.to_thread(self._transcribe_file, audio_file_path)
        return text
    
    def _transcribe_file(self, audio_file_path: str) -> str:
        """Transcribe file in background thread."""
        segments, info = self.whisper_model.transcribe(
            audio_file_path,
            language=settings.stt_language,
            beam_size=5,
            best_of=5,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            condition_on_previous_text=True
        )
        
        full_text = ""
        for segment in segments:
            text = segment.text.strip()
            if text:
                if full_text and not full_text.endswith(('.', '!', '?', ',')):
                    full_text += " "
                full_text += text
        
        return self._post_process_text(full_text.strip())


# Singleton instance
stt_service = ProfessionalSTTService()
