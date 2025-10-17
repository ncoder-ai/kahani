"""
TTS API Endpoints

Provides REST API for text-to-speech functionality.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging
import os
import base64
import asyncio

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.scene import Scene
from app.models.tts_settings import TTSSettings
from app.models.tts_provider_config import TTSProviderConfig as TTSProviderConfigModel
from app.services.tts import TTSService, TTSProviderRegistry
from app.services.tts_session_manager import tts_session_manager
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/tts", tags=["TTS"])
logger = logging.getLogger(__name__)


# Request/Response Models
class TTSSettingsRequest(BaseModel):
    """Request model for updating TTS settings"""
    provider_type: str = Field(..., description="TTS provider type (e.g., 'openai-compatible')")
    api_url: str = Field(..., description="Provider API URL")
    api_key: Optional[str] = Field(None, description="API key (if required)")
    voice_id: Optional[str] = Field("default", description="Voice ID to use")
    speed: Optional[float] = Field(1.0, ge=0.25, le=4.0, description="Speech speed (0.25-4.0)")
    timeout: Optional[int] = Field(30, ge=5, le=120, description="Request timeout in seconds")
    extra_params: Optional[dict] = Field(None, description="Provider-specific parameters")
    # Behavior settings
    tts_enabled: Optional[bool] = Field(True, description="Enable/disable TTS globally")
    progressive_narration: Optional[bool] = Field(False, description="Split scenes into chunks for progressive playback")
    chunk_size: Optional[int] = Field(280, ge=100, le=500, description="Chunk size for progressive narration (100=sentence, 500=paragraph)")
    stream_audio: Optional[bool] = Field(True, description="Future: Use provider streaming (SSE) when available")
    auto_play_last_scene: Optional[bool] = Field(False, description="Auto-play TTS after scene generation completes")


class TTSSettingsResponse(BaseModel):
    """Response model for TTS settings"""
    id: int
    user_id: int
    provider_type: Optional[str] = None
    api_url: Optional[str] = None
    voice_id: Optional[str] = None
    speed: Optional[float] = None
    timeout: Optional[int] = None
    extra_params: Optional[dict] = None
    # Behavior settings
    tts_enabled: Optional[bool] = None
    progressive_narration: Optional[bool] = None
    chunk_size: Optional[int] = None
    stream_audio: Optional[bool] = None
    auto_play_last_scene: Optional[bool] = None

    class Config:
        from_attributes = True
        
    @classmethod
    def from_db_model(cls, db_model: TTSSettings):
        """Convert database model to response model"""
        return cls(
            id=db_model.id,
            user_id=db_model.user_id,
            provider_type=db_model.tts_provider_type,
            api_url=db_model.tts_api_url,
            voice_id=db_model.default_voice,
            speed=db_model.speech_speed,
            timeout=db_model.tts_timeout,
            extra_params=db_model.tts_extra_params,
            tts_enabled=db_model.tts_enabled,
            progressive_narration=db_model.progressive_narration,
            chunk_size=db_model.chunk_size,
            stream_audio=db_model.stream_audio,
            auto_play_last_scene=db_model.auto_play_last_scene
        )


class TTSTestRequest(BaseModel):
    """Request model for testing TTS"""
    text: str = Field(..., max_length=500, description="Text to synthesize (max 500 chars)")
    voice_id: Optional[str] = Field(None, description="Voice ID (uses settings default if not provided)")
    speed: Optional[float] = Field(None, ge=0.25, le=4.0, description="Speech speed override")


class GenerateAudioRequest(BaseModel):
    """Request model for generating scene audio"""
    force_regenerate: bool = Field(False, description="Force regeneration even if cached")


class AudioInfoResponse(BaseModel):
    """Response model for audio info"""
    scene_id: int
    voice_id: str
    provider_type: str
    file_size: int
    duration: float
    format: str
    generated_at: str
    cached: bool
    progressive: bool = Field(False, description="Whether audio is chunked for progressive playback")
    chunk_count: int = Field(1, description="Number of chunks (1 if not progressive)")


class TTSSessionResponse(BaseModel):
    """Response model for WebSocket TTS session"""
    session_id: str
    scene_id: int
    websocket_url: str
    message: str


class ChunkMetadata(BaseModel):
    """Metadata for an audio chunk"""
    chunk_number: int
    text_preview: str
    estimated_duration: float


class VoiceInfo(BaseModel):
    """Voice information"""
    id: str
    name: str
    language: Optional[str]
    description: Optional[str]


class ProviderInfo(BaseModel):
    """Provider information"""
    type: str
    name: str
    supports_streaming: bool


# Endpoints
@router.get("/settings", response_model=TTSSettingsResponse)
async def get_tts_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's TTS settings"""
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    if not tts_settings:
        # Create default settings
        tts_settings = TTSSettings(user_id=current_user.id)
        db.add(tts_settings)
        db.commit()
        db.refresh(tts_settings)
    
    return TTSSettingsResponse.from_db_model(tts_settings)


@router.put("/settings", response_model=TTSSettingsResponse)
async def update_tts_settings(
    settings_request: TTSSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's TTS settings"""
    
    # Validate provider type
    if not TTSProviderRegistry.is_registered(settings_request.provider_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider type: {settings_request.provider_type}"
        )
    
    # Get or create settings
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    if not tts_settings:
        tts_settings = TTSSettings(user_id=current_user.id)
        db.add(tts_settings)
    
    # Update settings
    tts_settings.tts_provider_type = settings_request.provider_type
    tts_settings.tts_api_url = settings_request.api_url
    tts_settings.tts_api_key = settings_request.api_key
    tts_settings.default_voice = settings_request.voice_id
    tts_settings.speech_speed = settings_request.speed
    tts_settings.tts_timeout = settings_request.timeout
    tts_settings.tts_extra_params = settings_request.extra_params or {}
    
    # Update behavior settings
    if settings_request.tts_enabled is not None:
        tts_settings.tts_enabled = settings_request.tts_enabled
    if settings_request.progressive_narration is not None:
        tts_settings.progressive_narration = settings_request.progressive_narration
    if settings_request.chunk_size is not None:
        tts_settings.chunk_size = settings_request.chunk_size
    if settings_request.stream_audio is not None:
        tts_settings.stream_audio = settings_request.stream_audio
    if settings_request.auto_play_last_scene is not None:
        tts_settings.auto_play_last_scene = settings_request.auto_play_last_scene
    
    db.commit()
    db.refresh(tts_settings)
    
    logger.info(f"Updated TTS settings for user {current_user.id}")
    
    return TTSSettingsResponse.from_db_model(tts_settings)


@router.get("/provider-configs", response_model=list[TTSSettingsResponse])
async def get_all_provider_configs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all saved provider configurations for the user"""
    configs = db.query(TTSProviderConfigModel).filter(
        TTSProviderConfigModel.user_id == current_user.id
    ).all()
    
    return [
        TTSSettingsResponse(
            id=config.id,
            user_id=config.user_id,
            provider_type=config.provider_type,
            api_url=config.api_url,
            voice_id=config.voice_id,
            speed=config.speed,
            timeout=config.timeout,
            extra_params=config.extra_params
        )
        for config in configs
    ]


@router.get("/provider-configs/{provider_type}", response_model=TTSSettingsResponse)
async def get_provider_config(
    provider_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get saved configuration for a specific provider"""
    config = db.query(TTSProviderConfigModel).filter(
        TTSProviderConfigModel.user_id == current_user.id,
        TTSProviderConfigModel.provider_type == provider_type
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved configuration found for provider: {provider_type}"
        )
    
    return TTSSettingsResponse(
        id=config.id,
        user_id=config.user_id,
        provider_type=config.provider_type,
        api_url=config.api_url,
        voice_id=config.voice_id,
        speed=config.speed,
        timeout=config.timeout,
        extra_params=config.extra_params
    )


@router.put("/provider-configs/{provider_type}", response_model=TTSSettingsResponse)
async def save_provider_config(
    provider_type: str,
    settings_request: TTSSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save configuration for a specific provider"""
    
    # Validate provider type
    if not TTSProviderRegistry.is_registered(provider_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider type: {provider_type}"
        )
    
    # Get or create provider config
    config = db.query(TTSProviderConfigModel).filter(
        TTSProviderConfigModel.user_id == current_user.id,
        TTSProviderConfigModel.provider_type == provider_type
    ).first()
    
    if not config:
        config = TTSProviderConfigModel(
            user_id=current_user.id,
            provider_type=provider_type
        )
        db.add(config)
    
    # Update config
    config.api_url = settings_request.api_url
    config.api_key = settings_request.api_key or ""
    config.voice_id = settings_request.voice_id or ""
    config.speed = settings_request.speed or 1.0
    config.timeout = settings_request.timeout or 30
    config.extra_params = settings_request.extra_params or {}
    
    db.commit()
    db.refresh(config)
    
    logger.info(f"Saved provider config for user {current_user.id}, provider {provider_type}")
    
    return TTSSettingsResponse(
        id=config.id,
        user_id=config.user_id,
        provider_type=config.provider_type,
        api_url=config.api_url,
        voice_id=config.voice_id,
        speed=config.speed,
        timeout=config.timeout,
        extra_params=config.extra_params
    )


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers():
    """List available TTS providers"""
    providers = TTSProviderRegistry.list_providers()
    
    result = []
    for provider_type in providers:
        provider_class = TTSProviderRegistry.get_provider(provider_type)
        if provider_class:
            # Create dummy instance to get info
            try:
                from app.services.tts import TTSProviderConfig
                # Use a dummy URL - actual URL comes from user settings
                dummy_config = TTSProviderConfig(
                    api_url="http://dummy-url-for-provider-info",
                    api_key="dummy"
                )
                instance = provider_class(config=dummy_config)
                result.append(ProviderInfo(
                    type=provider_type,
                    name=instance.provider_name,
                    supports_streaming=instance.supports_streaming
                ))
            except Exception as e:
                logger.warning(f"Could not instantiate provider {provider_type}: {e}")
    
    return result


@router.post("/test-connection")
async def test_connection(
    settings_request: TTSSettingsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test connection to TTS provider and return health status.
    Returns voices if connection is successful.
    """
    
    # Validate provider type
    if not TTSProviderRegistry.is_registered(settings_request.provider_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider type: {settings_request.provider_type}"
        )
    
    try:
        from app.services.tts import TTSProviderFactory, TTSProviderConfig
        
        # Create provider config
        config = TTSProviderConfig(
            api_url=settings_request.api_url,
            api_key=settings_request.api_key or "",
            timeout=settings_request.timeout or 30,
            extra_params=settings_request.extra_params or {}
        )
        
        provider = TTSProviderFactory.create_provider(
            provider_type=settings_request.provider_type,
            api_url=settings_request.api_url,
            api_key=settings_request.api_key or "",
            timeout=settings_request.timeout or 30,
            extra_params=settings_request.extra_params or {}
        )
        
        # Perform health check
        is_healthy = await provider.health_check()
        
        if not is_healthy:
            return {
                "success": False,
                "message": "Provider is not responding or no voices available",
                "voices": []
            }
        
        # Get voices if healthy
        voices = await provider.get_voices()
        
        return {
            "success": True,
            "message": f"Successfully connected to {settings_request.provider_type}",
            "voices": [
                {
                    "id": voice.id if voice.id else voice.name,
                    "name": voice.name,
                    "language": voice.language,
                    "description": voice.description
                }
                for voice in voices
            ]
        }
        
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "voices": []
        }


@router.get("/voices", response_model=list[VoiceInfo])
async def list_voices(
    language: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available voices from configured TTS provider"""
    
    # Get user's TTS settings
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    if not tts_settings or not tts_settings.tts_provider_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS not configured. Please configure TTS settings first."
        )
    
    try:
        from app.services.tts import TTSProviderFactory
        
        provider = TTSProviderFactory.create_provider(
            provider_type=tts_settings.tts_provider_type,
            api_url=tts_settings.tts_api_url,
            api_key=tts_settings.tts_api_key or "",
            timeout=tts_settings.tts_timeout or 30,
            extra_params=tts_settings.tts_extra_params or {}
        )
        
        voices = await provider.get_voices(language)
        
        return [
            VoiceInfo(
                id=voice.id if voice.id else voice.name,
                name=voice.name,
                language=voice.language,
                description=voice.description
            )
            for voice in voices
        ]
        
    except Exception as e:
        logger.error(f"Failed to fetch voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch voices: {str(e)}"
        )


@router.post("/test")
async def test_tts(
    request: TTSTestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test TTS with sample text and return audio"""
    
    # Get user's TTS settings
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    if not tts_settings or not tts_settings.tts_provider_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS not configured. Please configure TTS settings first."
        )
    
    try:
        from app.services.tts import TTSProviderFactory, TTSRequest, AudioFormat
        
        provider = TTSProviderFactory.create_provider(
            provider_type=tts_settings.tts_provider_type,
            api_url=tts_settings.tts_api_url,
            api_key=tts_settings.tts_api_key or "",
            timeout=tts_settings.tts_timeout or 30,
            extra_params=tts_settings.tts_extra_params or {}
        )
        
        # Use provided voice_id or fall back to settings
        voice_id = request.voice_id or tts_settings.default_voice or "default"
        speed = request.speed or tts_settings.speech_speed or 1.0
        
        tts_request = TTSRequest(
            text=request.text,
            voice_id=voice_id,
            speed=speed,
            format=AudioFormat.MP3
        )
        
        response = await provider.synthesize(tts_request)
        
        logger.info(f"Generated test audio for user {current_user.id}: {len(response.audio_data)} bytes")
        
        # Determine content type based on format
        content_type_map = {
            AudioFormat.MP3: "audio/mpeg",
            AudioFormat.WAV: "audio/wav",
            AudioFormat.OGG: "audio/ogg",
            AudioFormat.OPUS: "audio/opus",
            AudioFormat.AAC: "audio/aac"
        }
        
        content_type = content_type_map.get(response.format, "audio/wav")
        
        return Response(
            content=response.audio_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=test.{response.format.value}",
                "X-Audio-Duration": str(response.duration),
                "X-Audio-Format": response.format.value
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to generate test audio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate audio: {str(e)}"
        )


@router.post("/test-voice")
async def test_voice_preview(
    settings_request: TTSSettingsRequest,
    text: str = "Hello, this is a test of my voice.",
    voice_id: Optional[str] = None,
    speed: Optional[float] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Test TTS with custom settings (for voice previews before saving).
    Accepts provider settings directly instead of using saved settings.
    """
    
    # Validate provider type
    if not TTSProviderRegistry.is_registered(settings_request.provider_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider type: {settings_request.provider_type}"
        )
    
    try:
        from app.services.tts import TTSProviderFactory, TTSRequest, AudioFormat
        
        provider = TTSProviderFactory.create_provider(
            provider_type=settings_request.provider_type,
            api_url=settings_request.api_url,
            api_key=settings_request.api_key or "",
            timeout=settings_request.timeout or 30,
            extra_params=settings_request.extra_params or {}
        )
        
        # Use provided voice_id or default from settings
        final_voice_id = voice_id or settings_request.voice_id or "default"
        final_speed = speed if speed is not None else (settings_request.speed or 1.0)
        
        tts_request = TTSRequest(
            text=text,
            voice_id=final_voice_id,
            speed=final_speed,
            format=AudioFormat.MP3
        )
        
        response = await provider.synthesize(tts_request)
        
        logger.info(f"Generated voice preview for user {current_user.id}: voice={final_voice_id}, {len(response.audio_data)} bytes")
        
        # Determine content type based on format
        content_type_map = {
            AudioFormat.MP3: "audio/mpeg",
            AudioFormat.WAV: "audio/wav",
            AudioFormat.OGG: "audio/ogg",
            AudioFormat.OPUS: "audio/opus",
            AudioFormat.AAC: "audio/aac"
        }
        
        content_type = content_type_map.get(response.format, "audio/wav")
        
        return Response(
            content=response.audio_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=preview_{final_voice_id}.{response.format.value}",
                "X-Audio-Duration": str(response.duration),
                "X-Audio-Format": response.format.value,
                "X-Voice-ID": final_voice_id
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to generate voice preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate audio: {str(e)}"
        )


@router.post("/generate/{scene_id}", response_model=AudioInfoResponse)
async def generate_scene_audio(
    scene_id: int,
    request: GenerateAudioRequest = GenerateAudioRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate fresh audio for a scene (always regenerate, no caching)"""
    
    # Get scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Check user has access to this scene's story
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        # Get TTS settings to check if progressive narration is enabled
        tts_settings = db.query(TTSSettings).filter(
            TTSSettings.user_id == current_user.id
        ).first()
        
        tts_service = TTSService(db)
        # Always force regenerate (no caching)
        scene_audio = await tts_service.get_or_generate_scene_audio(
            scene=scene,
            user_id=current_user.id,
            force_regenerate=True  # Always regenerate
        )
        
        if not scene_audio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TTS not configured"
            )
        
        # Check if progressive narration is enabled
        is_progressive = tts_settings and tts_settings.progressive_narration
        
        return AudioInfoResponse(
            scene_id=scene_audio.scene_id,
            voice_id=scene_audio.voice_used,
            provider_type=scene_audio.provider_used,
            file_size=scene_audio.file_size,
            duration=scene_audio.duration,
            format=scene_audio.audio_format,
            generated_at=scene_audio.created_at.isoformat(),
            cached=False,  # Never cached
            progressive=is_progressive,
            chunk_count=scene_audio.chunk_count
        )
        
    except Exception as e:
        logger.error(f"Failed to generate scene audio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate audio: {str(e)}"
        )


@router.post("/generate-ws/{scene_id}", response_model=TTSSessionResponse)
async def generate_scene_audio_websocket(
    scene_id: int,
    request: GenerateAudioRequest = GenerateAudioRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate audio for a scene with WebSocket streaming.
    
    This endpoint creates a TTS generation session and returns a session ID
    and WebSocket URL. The client should:
    
    1. Call this endpoint to get session_id
    2. Connect to the WebSocket at websocket_url
    3. Receive audio chunks as they're generated via WebSocket messages
    
    Message types sent via WebSocket:
    - chunk_ready: Audio chunk is ready (includes base64 audio data)
    - progress: Generation progress update
    - complete: All chunks generated
    - error: An error occurred
    
    This approach eliminates polling and provides instant chunk delivery.
    """
    
    # Get scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Check user has access to this scene's story
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        # Create TTS session
        session_id = tts_session_manager.create_session(
            scene_id=scene_id,
            user_id=current_user.id
        )
        
        logger.info(f"Created TTS session {session_id} for scene {scene_id}")
        
        # Trigger background generation task
        # Note: Pass scene_id instead of scene object to avoid DB session issues
        background_tasks.add_task(
            generate_and_stream_chunks,
            session_id=session_id,
            scene_id=scene_id,
            user_id=current_user.id
        )
        
        # Return session info
        return TTSSessionResponse(
            session_id=session_id,
            scene_id=scene_id,
            websocket_url=f"/ws/tts/{session_id}",
            message="Connect to WebSocket to receive audio chunks"
        )
        
    except Exception as e:
        logger.error(f"Failed to create TTS session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


async def generate_and_stream_chunks(
    session_id: str,
    scene_id: int,
    user_id: int
):
    """
    Background task that generates TTS audio chunks and streams them via WebSocket.
    
    This function:
    1. Creates its own DB session (background tasks can't share sessions)
    2. Waits for WebSocket connection
    3. Generates audio chunks for the scene text
    4. Sends each chunk via WebSocket as soon as it's ready
    5. Sends progress updates
    6. Handles errors gracefully
    """
    # Create a new DB session for this background task
    db = next(get_db())
    
    try:
        # Get the scene
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            logger.error(f"Scene {scene_id} not found")
            return
        
        # Get the active variant content from story flow (same as working TTS code)
        from app.models.story_flow import StoryFlow
        from app.models.scene_variant import SceneVariant
        
        flow_entry = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene_id,
            StoryFlow.is_active == True
        ).first()
        
        if not flow_entry or not flow_entry.scene_variant_id:
            logger.error(f"No active variant found for scene {scene_id}")
            await tts_session_manager.send_message(session_id, {
                "type": "error",
                "message": "No active scene variant found"
            })
            return
        
        variant = db.query(SceneVariant).filter(
            SceneVariant.id == flow_entry.scene_variant_id
        ).first()
        
        if not variant or not variant.content:
            logger.error(f"Variant {flow_entry.scene_variant_id} has no content")
            await tts_session_manager.send_message(session_id, {
                "type": "error",
                "message": "Scene variant has no content"
            })
            return
        
        # Use variant.content instead of scene.content!
        scene_content = variant.content
        
        # Check if this is an auto-play session
        session = tts_session_manager.get_session(session_id)
        is_auto_play = session and session.auto_play
        
        if is_auto_play:
            # For auto-play: Start generating immediately, don't wait for WebSocket
            # Audio chunks will be buffered and sent when WebSocket connects
            logger.info(f"[AUTO-PLAY] Starting TTS generation immediately for session {session_id} (no WebSocket wait)")
        else:
            # For manual TTS: Wait for WebSocket to connect (up to 10 seconds)
            logger.info(f"Waiting for WebSocket connection for session {session_id}")
            for i in range(20):  # 20 attempts × 0.5s = 10 seconds max
                session = tts_session_manager.get_session(session_id)
                if session and session.websocket:
                    logger.info(f"WebSocket connected for session {session_id}")
                    break
                await asyncio.sleep(0.5)
            else:
                logger.error(f"WebSocket never connected for session {session_id}")
                return
        
        # Mark session as generating
        tts_session_manager.set_generating(session_id, True)
        
        # Get TTS service
        tts_service = TTSService(db)
        
        # Get TTS settings
        tts_settings = db.query(TTSSettings).filter(
            TTSSettings.user_id == user_id
        ).first()
        
        if not tts_settings or not tts_settings.tts_enabled:
            await tts_session_manager.send_message(session_id, {
                "type": "error",
                "message": "TTS not configured or disabled"
            })
            return
        
        # Check if progressive narration is enabled
        is_progressive = tts_settings.progressive_narration
        
        if is_progressive:
            # Generate chunks and stream them
            # Use text chunker to split scene text
            from app.services.tts.text_chunker import TextChunker
            chunker = TextChunker(max_chunk_size=tts_settings.chunk_size or 280)
            
            logger.info(f"Scene content length: {len(scene_content)} chars")
            text_chunks = chunker.chunk_text(scene_content)
            
            total_chunks = len(text_chunks)
            tts_session_manager.set_total_chunks(session_id, total_chunks)
            
            logger.info(f"Generating {total_chunks} chunks for session {session_id}")
            
            if total_chunks == 0:
                logger.warning(f"No chunks generated for scene {scene_id}, scene content: '{scene.content[:100]}...'")
                await tts_session_manager.send_message(session_id, {
                    "type": "error",
                    "message": "No text to generate audio for"
                })
                return
            
            # Get TTS provider
            from app.services.tts.factory import TTSProviderFactory
            from app.services.tts.base import TTSRequest, AudioFormat
            
            provider = TTSProviderFactory.create_provider(
                provider_type=tts_settings.tts_provider_type,
                api_url=tts_settings.tts_api_url,
                api_key=tts_settings.tts_api_key or "",
                timeout=tts_settings.tts_timeout or 30,
                extra_params=tts_settings.tts_extra_params or {}
            )
            
            # Get audio format
            format = AudioFormat.MP3
            if tts_settings.tts_extra_params:
                format_str = tts_settings.tts_extra_params.get("format", "mp3")
                try:
                    format = AudioFormat(format_str)
                except ValueError:
                    pass
            
            # Generate each chunk and stream immediately
            for i, text_chunk in enumerate(text_chunks, start=1):
                try:
                    # Extract text from TextChunk object
                    chunk_text = text_chunk.text
                    
                    # Generate audio for this chunk using provider directly
                    request = TTSRequest(
                        text=chunk_text,
                        voice_id=tts_settings.default_voice or "default",
                        speed=tts_settings.speech_speed or 1.0,
                        format=format
                    )
                    
                    response = await provider.synthesize(request)
                    audio_data = response.audio_data
                    
                    if not audio_data:
                        raise Exception(f"Failed to generate audio for chunk {i}")
                    
                    # Convert to base64 for WebSocket transmission
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    
                    # Send chunk via WebSocket
                    await tts_session_manager.send_message(session_id, {
                        "type": "chunk_ready",
                        "chunk_number": i,
                        "total_chunks": total_chunks,
                        "audio_base64": audio_base64,
                        "text_preview": chunk_text[:50] + "..." if len(chunk_text) > 50 else chunk_text,
                        "size_bytes": len(audio_data)
                    })
                    
                    tts_session_manager.increment_chunks_sent(session_id)
                    
                    logger.info(f"Sent chunk {i}/{total_chunks} for session {session_id}")
                    
                    # Send progress update
                    progress_percent = int((i / total_chunks) * 100)
                    await tts_session_manager.send_message(session_id, {
                        "type": "progress",
                        "chunks_ready": i,
                        "total_chunks": total_chunks,
                        "progress_percent": progress_percent
                    })
                    
                except Exception as chunk_error:
                    logger.error(f"Error generating chunk {i}: {chunk_error}")
                    await tts_session_manager.send_message(session_id, {
                        "type": "error",
                        "message": f"Failed to generate chunk {i}",
                        "chunk_number": i
                    })
                    # Continue with other chunks
                    continue
            
            # Send completion message
            await tts_session_manager.send_message(session_id, {
                "type": "complete",
                "total_chunks": total_chunks,
                "message": "All chunks generated successfully"
            })
            
        else:
            # Generate single audio file
            scene_audio = await tts_service.get_or_generate_scene_audio(
                scene=scene,
                user_id=user_id,
                force_regenerate=True
            )
            
            if not scene_audio or not scene_audio.file_path:
                await tts_session_manager.send_message(session_id, {
                    "type": "error",
                    "message": "Failed to generate audio"
                })
                return
            
            # Read audio file and send as single chunk
            with open(scene_audio.file_path, 'rb') as f:
                audio_data = f.read()
            
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            await tts_session_manager.send_message(session_id, {
                "type": "chunk_ready",
                "chunk_number": 1,
                "total_chunks": 1,
                "audio_base64": audio_base64,
                "size_bytes": len(audio_data),
                "duration": scene_audio.duration
            })
            
            await tts_session_manager.send_message(session_id, {
                "type": "complete",
                "total_chunks": 1,
                "message": "Audio generated successfully"
            })
        
    except Exception as e:
        logger.error(f"Error in generate_and_stream_chunks: {e}", exc_info=True)
        await tts_session_manager.send_message(session_id, {
            "type": "error",
            "message": str(e)
        })
        tts_session_manager.set_error(session_id, str(e))
    
    finally:
        # Clean up
        tts_session_manager.set_generating(session_id, False)
        logger.info(f"Completed generation for session {session_id}")
        # Close DB session
        db.close()


@router.post("/stream/{scene_id}")
async def stream_scene_audio(
    scene_id: int,
    request: GenerateAudioRequest = GenerateAudioRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream scene audio chunks as they're generated.
    
    Returns audio chunks sequentially - frontend can play each chunk
    as it arrives for instant playback while generation continues.
    """
    
    # Get scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Check user has access to this scene's story
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    async def generate_chunks():
        """Generator that yields audio chunks as they're created"""
        try:
            tts_service = TTSService(db)
            
            # Stream chunks as they're generated
            async for chunk_data in tts_service.stream_scene_audio_chunks(
                scene=scene,
                user_id=current_user.id,
                force_regenerate=request.force_regenerate
            ):
                yield chunk_data
                
        except Exception as e:
            logger.error(f"Failed to stream scene audio: {e}")
            # Send error as last chunk
            import json
            error_data = json.dumps({"error": str(e)}).encode()
            yield error_data
    
    return StreamingResponse(
        generate_chunks(),
        media_type="application/octet-stream",
        headers={
            "X-Scene-ID": str(scene_id),
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff"
        }
    )


@router.get("/audio/{scene_id}")
async def get_scene_audio(
    scene_id: int,
    stream: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get audio file for a scene (no caching - audio is deleted after serving)"""
    
    # Get scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Check access
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    tts_service = TTSService(db)
    
    if stream:
        # Stream audio
        async def audio_generator():
            async for chunk in tts_service.stream_scene_audio(scene, current_user.id):
                yield chunk
        
        return StreamingResponse(
            audio_generator(),
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"inline; filename=scene_{scene_id}.wav",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    else:
        # Get cached audio
        from app.models.tts_settings import SceneAudio
        from sqlalchemy import and_
        
        tts_settings = db.query(TTSSettings).filter(
            TTSSettings.user_id == current_user.id
        ).first()
        
        if not tts_settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TTS not configured"
            )
        
        scene_audio = db.query(SceneAudio).filter(
            and_(
                SceneAudio.scene_id == scene_id,
                SceneAudio.voice_used == tts_settings.default_voice
            )
        ).first()
        
        if not scene_audio or not scene_audio.audio_url or not os.path.exists(scene_audio.audio_url):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio not found. Generate it first using POST /api/tts/generate/{scene_id}"
            )
        
        # Determine content type
        content_type = "audio/wav"
        if scene_audio.audio_format == "mp3":
            content_type = "audio/mpeg"
        elif scene_audio.audio_format == "ogg":
            content_type = "audio/ogg"
        
        # Read file into memory
        file_path = scene_audio.audio_url
        with open(file_path, "rb") as f:
            audio_data = f.read()
        
        # Delete the file immediately after reading
        try:
            os.remove(file_path)
            logger.info(f"Deleted audio file after serving: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete audio file {file_path}: {e}")
        
        # Delete database entry
        db.delete(scene_audio)
        db.commit()
        logger.info(f"Deleted audio cache entry for scene {scene_id}")
        
        # Return audio data from memory
        from fastapi.responses import Response
        return Response(
            content=audio_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=scene_{scene_id}.{scene_audio.audio_format}",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )


@router.get("/audio/{scene_id}/status")
async def get_audio_generation_status(
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current status of audio generation for a scene.
    Returns information about how many chunks are ready and total expected chunks.
    """
    # Get scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Check access
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        # Get scene audio metadata (get most recent entry)
        from app.models.tts_settings import SceneAudio
        scene_audio = db.query(SceneAudio).filter(
            SceneAudio.scene_id == scene_id,
            SceneAudio.user_id == current_user.id
        ).order_by(SceneAudio.id.desc()).first()
        
        if not scene_audio:
            return {
                "scene_id": scene_id,
                "status": "not_started",
                "chunks_ready": 0,
                "total_chunks": 0,
                "is_progressive": False
            }
        
        # Check how many chunk files actually exist
        from pathlib import Path
        import os
        
        audio_base_path = Path(scene_audio.audio_url)
        if not audio_base_path.is_absolute():
            cwd = Path(os.getcwd())
            audio_base_path = cwd / audio_base_path
        
        # Get TTS settings for voice info
        tts_settings = db.query(TTSSettings).filter(
            TTSSettings.user_id == current_user.id
        ).first()
        
        chunks_ready = 0
        if scene_audio.chunk_count > 1:
            # Progressive mode - count existing chunk files
            for chunk_num in range(scene_audio.chunk_count):
                chunk_filename = f"scene_{scene_id}_chunk_{chunk_num}_{tts_settings.default_voice or 'default'}.{scene_audio.audio_format}"
                chunk_path = audio_base_path / chunk_filename
                if chunk_path.exists():
                    chunks_ready += 1
        else:
            # Single file mode
            chunks_ready = 1 if audio_base_path.exists() else 0
        
        status_str = "complete" if chunks_ready == scene_audio.chunk_count else "generating"
        
        return {
            "scene_id": scene_id,
            "status": status_str,
            "chunks_ready": chunks_ready,
            "total_chunks": scene_audio.chunk_count,
            "is_progressive": scene_audio.chunk_count > 1,
            "duration": scene_audio.duration
        }
        
    except Exception as e:
        logger.error(f"Failed to get status for scene {scene_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audio status: {str(e)}"
        )


@router.get("/audio/{scene_id}/chunk/{chunk_number}")
async def get_scene_audio_chunk(
    scene_id: int,
    chunk_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific audio chunk for progressive playback.
    Generates the chunk on-demand and returns it immediately (no caching).
    """
    # Get scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # Check access
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Get TTS settings
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    if not tts_settings or not tts_settings.tts_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS not configured"
        )
    
    # Get scene variant content
    from app.models.story_flow import StoryFlow
    from app.models.scene_variant import SceneVariant
    
    flow_entry = db.query(StoryFlow).filter(
        StoryFlow.scene_id == scene.id,
        StoryFlow.is_active == True
    ).first()
    
    if not flow_entry or not flow_entry.scene_variant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active variant found for scene"
        )
    
    variant = db.query(SceneVariant).filter(
        SceneVariant.id == flow_entry.scene_variant_id
    ).first()
    
    if not variant or not variant.content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene content not found"
        )
    
    try:
        # Get TTS settings
        tts_settings = db.query(TTSSettings).filter(
            TTSSettings.user_id == current_user.id
        ).first()
        
        if not tts_settings or not tts_settings.tts_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TTS not configured"
            )
        
        # Get scene audio metadata (get most recent entry)
        from app.models.tts_settings import SceneAudio
        scene_audio = db.query(SceneAudio).filter(
            SceneAudio.scene_id == scene_id,
            SceneAudio.user_id == current_user.id
        ).order_by(SceneAudio.id.desc()).first()
        
        if not scene_audio or chunk_number >= scene_audio.chunk_count:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk {chunk_number} not found. Scene has {scene_audio.chunk_count if scene_audio else 0} chunks."
            )
        
        # Build chunk file path
        from pathlib import Path
        import os
        
        # Resolve audio directory path (stored as relative path in DB)
        audio_base_path = Path(scene_audio.audio_url)
        if not audio_base_path.is_absolute():
            # Resolve relative to current working directory
            cwd = Path(os.getcwd())
            audio_base_path = cwd / audio_base_path
        
        chunk_filename = f"scene_{scene_id}_chunk_{chunk_number}_{tts_settings.default_voice or 'default'}.{scene_audio.audio_format}"
        chunk_path = audio_base_path / chunk_filename
        
        if not chunk_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk file not found: {chunk_filename}"
            )
        
        # Read chunk file
        with open(chunk_path, "rb") as f:
            audio_data = f.read()
        
        # Get duration from file metadata if possible
        import wave
        duration = 0.0
        try:
            if scene_audio.audio_format == "wav":
                with wave.open(str(chunk_path), 'rb') as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    duration = frames / float(rate)
        except Exception:
            # If we can't get duration, estimate it
            duration = len(audio_data) / 32000.0  # Rough estimate
        
        # Determine content type
        content_type = "audio/mpeg" if scene_audio.audio_format == "mp3" else f"audio/{scene_audio.audio_format}"
        
        logger.info(f"Serving chunk {chunk_number} for scene {scene_id}: {len(audio_data)} bytes, {duration:.2f}s")
        
        # Return audio immediately
        from fastapi.responses import Response
        return Response(
            content=audio_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=scene_{scene_id}_chunk_{chunk_number}.{scene_audio.audio_format}",
                "X-Chunk-Number": str(chunk_number),
                "X-Total-Chunks": str(scene_audio.chunk_count),
                "X-Chunk-Duration": str(duration),
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to serve chunk {chunk_number} for scene {scene_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to serve audio chunk: {str(e)}"
        )


@router.delete("/audio/{scene_id}/chunks")
async def delete_scene_audio_chunks(
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete all audio chunks for a scene after playback is complete.
    Called by frontend when progressive playback finishes.
    """
    # Get scene and verify access
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    try:
        # Get scene audio metadata (get most recent entry)
        from app.models.tts_settings import SceneAudio
        scene_audio = db.query(SceneAudio).filter(
            SceneAudio.scene_id == scene_id,
            SceneAudio.user_id == current_user.id
        ).order_by(SceneAudio.id.desc()).first()
        
        if not scene_audio:
            # Already deleted or never existed
            return {"message": "No audio chunks to delete"}
        
        # Delete all chunk files
        from pathlib import Path
        import glob
        import os
        
        # Resolve audio directory path
        audio_base_path = Path(scene_audio.audio_url)
        if not audio_base_path.is_absolute():
            cwd = Path(os.getcwd())
            audio_base_path = cwd / audio_base_path
        
        chunk_pattern = str(audio_base_path / f"scene_{scene_id}_chunk_*")
        chunk_files = glob.glob(chunk_pattern)
        
        deleted_count = 0
        for chunk_file in chunk_files:
            try:
                os.remove(chunk_file)
                deleted_count += 1
                logger.info(f"Deleted chunk file: {chunk_file}")
            except Exception as e:
                logger.warning(f"Could not delete chunk file {chunk_file}: {e}")
        
        # Delete database entry
        db.delete(scene_audio)
        db.commit()
        
        logger.info(f"Deleted {deleted_count} chunk files and database entry for scene {scene_id}")
        
        return {
            "message": f"Deleted {deleted_count} audio chunks",
            "scene_id": scene_id
        }
        
    except Exception as e:
        logger.error(f"Failed to delete audio chunks for scene {scene_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete audio chunks: {str(e)}"
        )


@router.delete("/audio/{scene_id}")
async def delete_scene_audio(
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete cached audio for a scene"""
    
    # Get scene and verify access
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    tts_service = TTSService(db)
    deleted_count = tts_service.delete_scene_audio(scene_id)
    
    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} audio file(s)"
    }
