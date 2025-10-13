"""
TTS Service - Main orchestration layer

Handles:
- Scene text to audio conversion
- Audio caching
- Text chunking
- Audio streaming (chunk by chunk)
- File management
"""

import os
import asyncio
import logging
import struct
from pathlib import Path
from typing import Optional, AsyncIterator, List, Tuple
from datetime import datetime
from io import BytesIO

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.tts_settings import TTSSettings, SceneAudio
from app.models.scene import Scene
from app.models.scene_variant import SceneVariant
from app.models.story_flow import StoryFlow
from app.services.tts.factory import TTSProviderFactory
from app.services.tts.base import (
    TTSRequest,
    TTSResponse,
    AudioFormat,
    TTSProviderError
)
from app.services.tts.text_chunker import TextChunker, TextChunk
from app.config import settings

logger = logging.getLogger(__name__)


class TTSService:
    """
    Main TTS service for generating and managing scene narration audio.
    """
    
    def __init__(self, db: Session):
        """
        Initialize TTS service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.audio_dir = Path(settings.data_dir) / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_user_audio_dir(self, user_id: int) -> Path:
        """Get or create user's audio directory."""
        user_dir = self.audio_dir / f"user_{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def _get_audio_filename(self, scene_id: int, voice_id: str, format: AudioFormat) -> str:
        """Generate audio filename."""
        # Use scene_id and voice_id to create unique filename
        safe_voice = voice_id.replace("/", "_").replace("\\", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        return f"scene_{scene_id}_{safe_voice}_{timestamp}.{format.value}"
    
    async def get_or_generate_scene_audio(
        self,
        scene: Scene,
        user_id: int,
        tts_settings: Optional[TTSSettings] = None,
        force_regenerate: bool = False
    ) -> Optional[SceneAudio]:
        """
        Get cached audio or generate new audio for a scene.
        
        Args:
            scene: The scene to narrate
            user_id: User ID for audio directory
            tts_settings: User's TTS settings (will fetch if not provided)
            force_regenerate: Force regeneration even if cached
            
        Returns:
            SceneAudio object or None if TTS not configured
        """
        # Get TTS settings if not provided
        if tts_settings is None:
            tts_settings = self.db.query(TTSSettings).filter(
                TTSSettings.user_id == user_id
            ).first()
        
        if not tts_settings or not tts_settings.tts_provider_type:
            logger.warning(f"No TTS settings found for user {user_id}")
            return None
        
        # Check for cached audio
        if not force_regenerate:
            cached_audio = self.db.query(SceneAudio).filter(
                and_(
                    SceneAudio.scene_id == scene.id,
                    SceneAudio.voice_used == tts_settings.default_voice,
                    SceneAudio.provider_used == tts_settings.tts_provider_type
                )
            ).first()
            
            if cached_audio and cached_audio.file_path:
                # Check if file still exists
                if os.path.exists(cached_audio.file_path):
                    logger.info(f"Using cached audio for scene {scene.id}")
                    return cached_audio
                else:
                    logger.warning(f"Cached audio file not found: {cached_audio.file_path}")
                    # Delete invalid cache entry
                    self.db.delete(cached_audio)
                    self.db.commit()
        
        # Generate new audio
        logger.info(f"Generating audio for scene {scene.id}")
        
        # Get the active variant content from story flow
        flow_entry = self.db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene.id,
            StoryFlow.is_active == True
        ).first()
        
        if not flow_entry or not flow_entry.scene_variant_id:
            logger.error(f"No active variant found for scene {scene.id}")
            return None
        
        variant = self.db.query(SceneVariant).filter(
            SceneVariant.id == flow_entry.scene_variant_id
        ).first()
        
        if not variant or not variant.content:
            logger.error(f"Variant {flow_entry.scene_variant_id} has no content")
            return None
        
        try:
            audio_data, duration, format = await self._generate_scene_audio(
                variant.content,  # Use variant content instead of scene.content
                tts_settings
            )
            
            # Save audio file
            user_dir = self._get_user_audio_dir(user_id)
            filename = self._get_audio_filename(
                scene.id,
                tts_settings.default_voice or "default",
                format
            )
            file_path = user_dir / filename
            
            with open(file_path, "wb") as f:
                f.write(audio_data)
            
            logger.info(f"Saved audio to {file_path}")
            
            # Create or update cache entry
            if force_regenerate:
                # Update existing entry if it exists
                scene_audio = self.db.query(SceneAudio).filter(
                    and_(
                        SceneAudio.scene_id == scene.id,
                        SceneAudio.voice_used == tts_settings.default_voice,
                        SceneAudio.provider_used == tts_settings.tts_provider_type
                    )
                ).first()
                
                if scene_audio:
                    # Delete old file if different
                    if scene_audio.audio_url and scene_audio.audio_url != str(file_path):
                        try:
                            os.remove(scene_audio.audio_url)
                        except Exception as e:
                            logger.warning(f"Could not delete old audio file: {e}")
                    
                    scene_audio.audio_url = str(file_path)
                    scene_audio.file_size = len(audio_data)
                    scene_audio.duration = duration
                    scene_audio.audio_format = format.value
                    scene_audio.created_at = datetime.utcnow()
                else:
                    scene_audio = self._create_scene_audio_entry(
                        scene.id,
                        user_id,
                        str(file_path),
                        len(audio_data),
                        duration,
                        format,
                        tts_settings
                    )
                    self.db.add(scene_audio)
            else:
                scene_audio = self._create_scene_audio_entry(
                    scene.id,
                    user_id,
                    str(file_path),
                    len(audio_data),
                    duration,
                    format,
                    tts_settings
                )
                self.db.add(scene_audio)
            
            self.db.commit()
            self.db.refresh(scene_audio)
            
            logger.info(f"Audio cached for scene {scene.id}")
            return scene_audio
            
        except Exception as e:
            logger.error(f"Failed to generate audio for scene {scene.id}: {e}")
            self.db.rollback()
            raise
    
    async def stream_scene_audio_chunks(
        self,
        scene: Scene,
        user_id: int,
        tts_settings: Optional[TTSSettings] = None,
        force_regenerate: bool = False
    ) -> AsyncIterator[bytes]:
        """
        Stream scene audio chunks as they're generated.
        
        Yields each audio chunk immediately after generation,
        allowing frontend to start playback before all chunks are complete.
        
        Args:
            scene: The scene to narrate
            user_id: User ID for settings
            tts_settings: User's TTS settings (will fetch if not provided)
            force_regenerate: Force regeneration even if cached
            
        Yields:
            Audio chunk bytes (complete WAV files)
        """
        # Get TTS settings if not provided
        if tts_settings is None:
            tts_settings = self.db.query(TTSSettings).filter(
                TTSSettings.user_id == user_id
            ).first()
        
        if not tts_settings or not tts_settings.tts_provider_type:
            logger.warning(f"No TTS settings found for user {user_id}")
            return
        
        # Get scene content from active variant
        story_flow = self.db.query(StoryFlow).filter(
            and_(
                StoryFlow.scene_id == scene.id,
                StoryFlow.is_active == True
            )
        ).first()
        
        if not story_flow:
            logger.error(f"No active variant found for scene {scene.id}")
            return
        
        variant = self.db.query(SceneVariant).filter(
            SceneVariant.id == story_flow.scene_variant_id
        ).first()
        
        if not variant or not variant.content:
            logger.error(f"No content found for scene {scene.id}")
            return
        
        text = variant.content.strip()
        if not text:
            logger.warning(f"Scene {scene.id} has empty content")
            return
        
        logger.info(f"Streaming audio chunks for scene {scene.id}, text length: {len(text)}")
        
        try:
            # Create TTS provider
            provider = TTSProviderFactory.create_provider(
                provider_type=tts_settings.tts_provider_type,
                api_url=tts_settings.tts_api_url,
                api_key=tts_settings.tts_api_key or "",
                timeout=tts_settings.tts_timeout or 30,
                extra_params=tts_settings.tts_extra_params or {}
            )
            
            # Determine if we need to chunk the text
            max_length = provider.max_text_length
            needs_chunking = len(text) > max_length
            
            if not needs_chunking:
                # Generate single chunk
                logger.info(f"Text fits in single request ({len(text)} <= {max_length})")
                
                tts_request = TTSRequest(
                    text=text,
                    voice_id=tts_settings.default_voice or "default",
                    speed=tts_settings.speech_speed,
                    format=AudioFormat.WAV,
                    sample_rate=22050
                )
                
                response = await provider.synthesize(tts_request)
                yield response.audio_data
            else:
                # Chunk the text and generate each chunk
                logger.info(f"Text needs chunking: {len(text)} > {max_length}")
                
                chunker = TextChunker(max_chunk_size=max_length)
                chunks = chunker.chunk_text(text)
                
                logger.info(f"Split into {len(chunks)} chunks")
                
                for i, chunk in enumerate(chunks, 1):
                    logger.info(f"Generating chunk {i}/{len(chunks)}: {len(chunk.text)} chars")
                    
                    tts_request = TTSRequest(
                        text=chunk.text,
                        voice_id=tts_settings.default_voice or "default",
                        speed=tts_settings.speech_speed,
                        format=AudioFormat.WAV,
                        sample_rate=22050
                    )
                    
                    response = await provider.synthesize(tts_request)
                    
                    logger.info(f"Chunk {i} generated: {len(response.audio_data)} bytes")
                    
                    # Yield chunk immediately
                    yield response.audio_data
                
                logger.info(f"All {len(chunks)} chunks streamed")
                
        except Exception as e:
            logger.error(f"Failed to stream audio chunks for scene {scene.id}: {e}")
            raise
    
    def _create_scene_audio_entry(
        self,
        scene_id: int,
        user_id: int,
        file_path: str,
        file_size: int,
        duration: float,
        format: AudioFormat,
        tts_settings: TTSSettings
    ) -> SceneAudio:
        """Create a new SceneAudio database entry."""
        return SceneAudio(
            scene_id=scene_id,
            user_id=user_id,
            audio_url=file_path,
            voice_used=tts_settings.default_voice or "default",
            speed_used=tts_settings.speech_speed,
            provider_used=tts_settings.tts_provider_type,
            file_size=file_size,
            duration=duration,
            audio_format=format.value
        )
    
    def _concatenate_wav_chunks(self, chunks: List[bytes]) -> bytes:
        """
        Concatenate WAV file chunks properly by combining audio data and updating headers.
        
        WAV file structure:
        - RIFF header (12 bytes): 'RIFF', file_size, 'WAVE'
        - fmt chunk (24+ bytes): 'fmt ', size, audio format info
        - data chunk (8+ bytes): 'data', data_size, audio_data
        
        Args:
            chunks: List of WAV file byte data
            
        Returns:
            Combined WAV file as bytes
        """
        if not chunks:
            return b""
        
        if len(chunks) == 1:
            return chunks[0]
        
        # Parse first chunk to get format info
        first_chunk = chunks[0]
        
        # Find 'data' chunk in first file
        data_pos = first_chunk.find(b'data')
        if data_pos == -1:
            raise ValueError("Invalid WAV file: 'data' chunk not found")
        
        # Extract header (everything up to and including 'data' chunk header)
        # data chunk header is: b'data' + 4 bytes for data size
        header = first_chunk[:data_pos + 8]
        
        # Collect all audio data (skip headers from each chunk)
        all_audio_data = []
        
        for i, chunk in enumerate(chunks):
            chunk_data_pos = chunk.find(b'data')
            if chunk_data_pos == -1:
                logger.warning(f"Chunk {i} missing 'data' marker, skipping")
                continue
            
            # Skip 'data' + 4-byte size header
            audio_start = chunk_data_pos + 8
            audio_data = chunk[audio_start:]
            all_audio_data.append(audio_data)
        
        # Combine all audio data
        combined_audio = b"".join(all_audio_data)
        total_audio_size = len(combined_audio)
        
        # Update the data chunk size in header (bytes 4-7 after 'data')
        header_list = bytearray(header)
        struct.pack_into('<I', header_list, data_pos + 4, total_audio_size)
        
        # Update the RIFF chunk size (bytes 4-7 from start)
        # RIFF size = total file size - 8 (for 'RIFF' and size field itself)
        total_file_size = len(header_list) + total_audio_size
        struct.pack_into('<I', header_list, 4, total_file_size - 8)
        
        # Combine header and audio
        result = bytes(header_list) + combined_audio
        
        logger.debug(f"Concatenated {len(chunks)} WAV chunks: {len(result)} bytes total")
        
        return result
    
    async def _generate_scene_audio(
        self,
        text: str,
        tts_settings: TTSSettings
    ) -> Tuple[bytes, float, AudioFormat]:
        """
        Generate audio for text using TTS provider.
        
        Args:
            text: Text to synthesize
            tts_settings: TTS configuration
            
        Returns:
            Tuple of (audio_data, duration, format)
        """
        # Create provider
        provider = TTSProviderFactory.create_provider(
            provider_type=tts_settings.tts_provider_type,
            api_url=tts_settings.tts_api_url,
            api_key=tts_settings.tts_api_key or "",
            timeout=tts_settings.tts_timeout or 120,  # Increased default to 120s for long scenes
            extra_params=tts_settings.tts_extra_params or {}
        )
        
        # Get max text length from provider
        max_length = provider.max_text_length
        
        # Determine format
        format = AudioFormat.MP3
        if tts_settings.tts_extra_params:
            format_str = tts_settings.tts_extra_params.get("format", "mp3")
            try:
                format = AudioFormat(format_str)
            except ValueError:
                logger.warning(f"Invalid format '{format_str}', using MP3")
        
        # Check if text needs chunking
        logger.info(f"Text length: {len(text)}, max_length: {max_length}, needs chunking: {len(text) > max_length}")
        
        if len(text) <= max_length:
            # Single request
            logger.info("Using single TTS request (no chunking)")
            request = TTSRequest(
                text=text,
                voice_id=tts_settings.default_voice or "default",
                speed=tts_settings.speech_speed or 1.0,
                format=format
            )
            
            response = await provider.synthesize(request)
            return response.audio_data, response.duration, response.format
        else:
            # Need to chunk - generate all chunks and concatenate properly
            logger.info(f"Text needs chunking ({len(text)} > {max_length})")
            audio_chunks, duration, format = await self._generate_chunked_audio(
                text,
                provider,
                tts_settings,
                format,
                max_length
            )
            
            # Properly concatenate audio chunks
            logger.info(f"Concatenating {len(audio_chunks)} chunks, format: {format.value}")
            if format == AudioFormat.WAV and len(audio_chunks) > 1:
                logger.info(f"Concatenating {len(audio_chunks)} WAV chunks")
                try:
                    concatenated_audio = self._concatenate_wav_chunks(audio_chunks)
                    logger.info(f"Concatenated audio: {len(concatenated_audio)} bytes")
                except Exception as e:
                    logger.error(f"Failed to concatenate WAV files: {e}")
                    # Fallback to simple concatenation
                    concatenated_audio = b"".join(audio_chunks)
            else:
                # For non-WAV or single chunk, simple concatenation is fine
                concatenated_audio = b"".join(audio_chunks)
            
            return concatenated_audio, duration, format
    
    async def _generate_chunked_audio(
        self,
        text: str,
        provider,
        tts_settings: TTSSettings,
        format: AudioFormat,
        max_length: int
    ) -> Tuple[List[bytes], float, AudioFormat]:
        """
        Generate audio for long text by chunking.
        Returns list of audio chunks instead of concatenating them.
        
        Args:
            text: Text to synthesize
            provider: TTS provider instance
            tts_settings: TTS configuration
            format: Audio format
            max_length: Maximum text length per chunk
            
        Returns:
            Tuple of (list of audio_chunks, total_duration, format)
        """
        # Create text chunker
        chunker = TextChunker(
            max_chunk_size=max_length,
            min_chunk_size=50,
            respect_sentences=True,
            respect_paragraphs=True
        )
        
        chunks = chunker.chunk_text(text)
        chunk_summary = chunker.get_chunk_summary(chunks)
        
        logger.info(f"Chunked text into {chunk_summary['total_chunks']} chunks")
        logger.debug(f"Chunk summary: {chunk_summary}")
        
        # Generate audio for each chunk
        audio_chunks = []
        total_duration = 0.0
        
        for chunk in chunks:
            request = TTSRequest(
                text=chunk.text,
                voice_id=tts_settings.default_voice or "default",
                speed=tts_settings.speech_speed or 1.0,
                format=format
            )
            
            try:
                response = await provider.synthesize(request)
                audio_chunks.append(response.audio_data)
                total_duration += response.duration
                
                logger.debug(f"Generated chunk {chunk.index}: {len(response.audio_data)} bytes, {response.duration:.2f}s")
                
                # Small delay between requests to avoid rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Failed to generate audio for chunk {chunk.index}: {e}")
                raise TTSProviderError(f"Failed to generate chunk {chunk.index}: {e}")
        
        # Return list of chunks instead of concatenating
        logger.info(f"Generated {len(audio_chunks)} audio chunks, total duration: {total_duration:.2f}s")
        
        return audio_chunks, total_duration, format
    
    async def stream_scene_audio(
        self,
        scene: Scene,
        user_id: int,
        tts_settings: Optional[TTSSettings] = None
    ) -> AsyncIterator[bytes]:
        """
        Stream audio for a scene (for real-time playback).
        
        Args:
            scene: The scene to narrate
            user_id: User ID
            tts_settings: User's TTS settings
            
        Yields:
            Audio data chunks
        """
        # Get TTS settings if not provided
        if tts_settings is None:
            tts_settings = self.db.query(TTSSettings).filter(
                TTSSettings.user_id == user_id
            ).first()
        
        if not tts_settings or not tts_settings.tts_provider_type:
            logger.warning(f"No TTS settings found for user {user_id}")
            return
        
        # Check for cached audio first
        cached_audio = self.db.query(SceneAudio).filter(
            and_(
                SceneAudio.scene_id == scene.id,
                SceneAudio.voice_used == tts_settings.default_voice,
                SceneAudio.provider_used == tts_settings.tts_provider_type
            )
        ).first()
        
        if cached_audio and cached_audio.file_path and os.path.exists(cached_audio.file_path):
            # Stream from cached file
            logger.info(f"Streaming cached audio for scene {scene.id}")
            with open(cached_audio.file_path, "rb") as f:
                while True:
                    chunk = f.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    yield chunk
        else:
            # Generate and stream
            logger.info(f"Generating and streaming audio for scene {scene.id}")
            
            provider = TTSProviderFactory.create_provider(
                provider_type=tts_settings.tts_provider_type,
                api_url=tts_settings.tts_api_url,
                api_key=tts_settings.tts_api_key or "",
                timeout=tts_settings.tts_timeout or 120,  # Increased default to 120s for long scenes
                extra_params=tts_settings.tts_extra_params or {}
            )
            
            # Determine format
            format = AudioFormat.MP3
            if tts_settings.tts_extra_params:
                format_str = tts_settings.tts_extra_params.get("format", "mp3")
                try:
                    format = AudioFormat(format_str)
                except ValueError:
                    pass
            
            request = TTSRequest(
                text=scene.content,
                voice_id=tts_settings.default_voice or "default",
                speed=tts_settings.speech_speed or 1.0,
                format=format
            )
            
            async for chunk in provider.synthesize_stream(request):
                yield chunk
    
    def delete_scene_audio(self, scene_id: int, voice_id: Optional[str] = None) -> int:
        """
        Delete cached audio for a scene.
        
        Args:
            scene_id: Scene ID
            voice_id: Optional voice ID filter
            
        Returns:
            Number of audio files deleted
        """
        query = self.db.query(SceneAudio).filter(SceneAudio.scene_id == scene_id)
        
        if voice_id:
            query = query.filter(SceneAudio.voice_used == voice_id)
        
        scene_audios = query.all()
        deleted_count = 0
        
        for scene_audio in scene_audios:
            # Delete file
            if scene_audio.audio_url and os.path.exists(scene_audio.audio_url):
                try:
                    os.remove(scene_audio.audio_url)
                    logger.info(f"Deleted audio file: {scene_audio.audio_url}")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete audio file {scene_audio.audio_url}: {e}")
            
            # Delete database entry
            self.db.delete(scene_audio)
        
        self.db.commit()
        
        logger.info(f"Deleted {deleted_count} audio files for scene {scene_id}")
        return deleted_count
    
    def cleanup_orphaned_audio(self, user_id: Optional[int] = None) -> Tuple[int, int]:
        """
        Clean up orphaned audio files (files without database entries or entries without files).
        
        Args:
            user_id: Optional user ID to limit cleanup
            
        Returns:
            Tuple of (orphaned_files_deleted, orphaned_entries_deleted)
        """
        files_deleted = 0
        entries_deleted = 0
        
        # Find database entries without files
        query = self.db.query(SceneAudio)
        scene_audios = query.all()
        
        for scene_audio in scene_audios:
            if not scene_audio.audio_url or not os.path.exists(scene_audio.audio_url):
                logger.info(f"Removing orphaned database entry for scene {scene_audio.scene_id}")
                self.db.delete(scene_audio)
                entries_deleted += 1
        
        self.db.commit()
        
        # Find files without database entries
        if user_id:
            audio_dirs = [self._get_user_audio_dir(user_id)]
        else:
            audio_dirs = [d for d in self.audio_dir.iterdir() if d.is_dir() and d.name.startswith("user_")]
        
        for audio_dir in audio_dirs:
            for audio_file in audio_dir.glob("scene_*.wav") + audio_dir.glob("scene_*.mp3"):
                file_path = str(audio_file)
                
                # Check if file has database entry
                exists = self.db.query(SceneAudio).filter(
                    SceneAudio.file_path == file_path
                ).first()
                
                if not exists:
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted orphaned audio file: {file_path}")
                        files_deleted += 1
                    except Exception as e:
                        logger.error(f"Failed to delete orphaned file {file_path}: {e}")
        
        logger.info(f"Cleanup complete: {files_deleted} files, {entries_deleted} entries")
        return files_deleted, entries_deleted
