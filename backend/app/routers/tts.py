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

from app.database import get_db, get_background_db
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
    
    # Verify user has permission to change TTS settings
    if not current_user.can_change_tts_settings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to change TTS settings. Please contact an administrator."
        )
    
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
    
    logger.info(f"Updated TTS settings for user {current_user.id}: provider={settings_request.provider_type}, voice={settings_request.voice_id}")
    
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
    
    # Get global TTS settings to include in provider configs
    global_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    return [
        TTSSettingsResponse(
            id=config.id,
            user_id=config.user_id,
            provider_type=config.provider_type,
            api_url=config.api_url,
            voice_id=config.voice_id,
            speed=config.speed,
            timeout=config.timeout,
            extra_params=config.extra_params,
            # Include global TTS settings
            tts_enabled=global_settings.tts_enabled if global_settings else True,
            progressive_narration=global_settings.progressive_narration if global_settings else False,
            chunk_size=global_settings.chunk_size if global_settings else 280,
            stream_audio=global_settings.stream_audio if global_settings else True,
            auto_play_last_scene=global_settings.auto_play_last_scene if global_settings else False
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
    
    # Get global TTS settings to include in provider config
    global_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    return TTSSettingsResponse(
        id=config.id,
        user_id=config.user_id,
        provider_type=config.provider_type,
        api_url=config.api_url,
        voice_id=config.voice_id,
        speed=config.speed,
        timeout=config.timeout,
        extra_params=config.extra_params,
        # Include global TTS settings
        tts_enabled=global_settings.tts_enabled if global_settings else True,
        progressive_narration=global_settings.progressive_narration if global_settings else False,
        chunk_size=global_settings.chunk_size if global_settings else 280,
        stream_audio=global_settings.stream_audio if global_settings else True,
        auto_play_last_scene=global_settings.auto_play_last_scene if global_settings else False
    )


@router.put("/provider-configs/{provider_type}", response_model=TTSSettingsResponse)
async def save_provider_config(
    provider_type: str,
    settings_request: TTSSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save configuration for a specific provider"""
    
    # Verify user has permission to change TTS settings
    if not current_user.can_change_tts_settings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to save TTS provider configurations. Please contact an administrator."
        )
    
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
    
    logger.info(f"Saved provider config for user {current_user.id}, provider {provider_type}, voice={settings_request.voice_id}")
    
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


@router.get("/health-status")
async def get_tts_health_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get TTS provider health and circuit breaker status.
    
    Returns information about all circuit breakers for TTS providers,
    including their current state, failure counts, and last state change.
    
    This is useful for debugging TTS issues and understanding if the
    circuit breaker is preventing requests due to provider failures.
    """
    from app.utils.circuit_breaker import get_all_circuit_breakers
    
    # Get user's TTS settings to show their configured provider
    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    
    configured_provider = None
    configured_url = None
    if tts_settings:
        configured_provider = tts_settings.tts_provider_type
        configured_url = tts_settings.tts_api_url
    
    # Get all circuit breaker states
    all_breakers = get_all_circuit_breakers()
    
    # Filter to TTS-related circuit breakers
    tts_breakers = {
        name: state for name, state in all_breakers.items()
        if name.startswith("tts-")
    }
    
    return {
        "configured_provider": configured_provider,
        "configured_url": configured_url,
        "circuit_breakers": tts_breakers,
        "total_breakers": len(tts_breakers),
        "healthy": all(
            breaker["state"] == "closed" 
            for breaker in tts_breakers.values()
        ) if tts_breakers else True,
        "message": "All TTS providers healthy" if not tts_breakers or all(
            breaker["state"] == "closed" 
            for breaker in tts_breakers.values()
        ) else "Some TTS providers are experiencing issues"
    }


@router.post("/test-connection")
async def test_connection(
    settings_request: TTSSettingsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test connection to TTS provider and return health status.
    Returns voices if connection is successful.
    """
    
    # Verify user has permission to change TTS settings
    if not current_user.can_change_tts_settings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to test TTS provider connections. Please contact an administrator."
        )
    
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
            detail="Failed to fetch voices"
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
            detail="Failed to generate audio"
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
            detail="Failed to generate audio"
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
            detail="Failed to generate audio"
        )


class RoleplayTTSRequest(BaseModel):
    """Request for multi-voice roleplay TTS generation."""
    voice_mapping: dict = Field(..., description="Character name -> {voice_id, speed} mapping")
    character_names: list[str] = Field(..., description="List of character names in the scene")


@router.post("/generate-roleplay/{scene_id}")
async def generate_roleplay_audio(
    scene_id: int,
    request: RoleplayTTSRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate multi-voice audio for a roleplay turn.

    Splits the scene content by character, generates audio with
    different voices per character, and streams the concatenated result.
    """
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    from app.models.story import Story
    story = db.query(Story).filter(Story.id == scene.story_id).first()
    if not story or story.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    tts_settings = db.query(TTSSettings).filter(
        TTSSettings.user_id == current_user.id
    ).first()
    if not tts_settings or not tts_settings.tts_provider_type:
        raise HTTPException(status_code=400, detail="TTS not configured")

    # Get active variant content
    from app.models.story_flow import StoryFlow
    from app.models.scene_variant import SceneVariant

    branch_id = story.current_branch_id or scene.branch_id
    flow_query = db.query(StoryFlow).filter(
        StoryFlow.scene_id == scene.id,
        StoryFlow.is_active == True,
    )
    if branch_id is not None:
        flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
    flow_entry = flow_query.first()

    if not flow_entry or not flow_entry.scene_variant_id:
        raise HTTPException(status_code=404, detail="No active variant found")

    variant = db.query(SceneVariant).filter(
        SceneVariant.id == flow_entry.scene_variant_id
    ).first()
    if not variant or not variant.content:
        raise HTTPException(status_code=404, detail="Scene content not found")

    tts_service = TTSService(db)

    async def stream_multi_voice():
        try:
            async for chunk in tts_service.generate_multi_voice_audio(
                text=variant.content,
                character_names=request.character_names,
                voice_mapping=request.voice_mapping,
                tts_settings=tts_settings,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Multi-voice TTS failed for scene {scene_id}: {e}")

    return StreamingResponse(
        stream_multi_voice(),
        media_type="audio/wav",
        headers={
            "X-Scene-ID": str(scene_id),
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/generate-ws/{scene_id}", response_model=TTSSessionResponse)
async def generate_scene_audio_websocket(
    scene_id: int,
    background_tasks: BackgroundTasks,
    request: GenerateAudioRequest = GenerateAudioRequest(),
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
        logger.info(f"[MANUAL TTS] Step 1: Received request for scene {scene_id}, user {current_user.id}")
        
        # Clear any existing sessions for this scene/user before creating new one
        cleared_count = tts_session_manager.clear_sessions_for_scene(scene_id, current_user.id)
        if cleared_count > 0:
            logger.info(f"[MANUAL TTS] Cleared {cleared_count} old session(s) for scene {scene_id}")
        
        # Create TTS session
        session_id = tts_session_manager.create_session(
            scene_id=scene_id,
            user_id=current_user.id
        )
        
        logger.info(f"[MANUAL TTS] Step 2: Created TTS session {session_id}")
        logger.info(f"[MANUAL TTS] Step 3: Adding background task for generation")
        
        # Trigger background generation task
        # Note: Pass scene_id instead of scene object to avoid DB session issues
        background_tasks.add_task(
            generate_and_stream_chunks,
            session_id=session_id,
            scene_id=scene_id,
            user_id=current_user.id
        )
        
        logger.info(f"[MANUAL TTS] Step 4: Background task added, returning session info")
        
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
            detail="Failed to create session"
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
    # SAFETY CHECK: Prevent duplicate generation
    logger.info(f"[GEN] Step 1: generate_and_stream_chunks called for session {session_id}")
    
    session = tts_session_manager.get_session(session_id)
    if not session:
        logger.error(f"[GEN] Step 1 FAILED: Session {session_id} not found")
        return
    
    logger.info(f"[GEN] Step 2: Session found, is_generating={session.is_generating}, auto_play={session.auto_play}")
    
    if session.is_generating:
        logger.warning(f"[GEN] Step 2 EXIT: Session {session_id} is already generating - skipping duplicate call")
        return
    
    # IMMEDIATELY set flag to prevent race condition
    tts_session_manager.set_generating(session_id, True)
    logger.info(f"[GEN] Step 2b: Set is_generating=True to prevent race condition")
    
    logger.info(f"[GEN] Step 3: Querying database for all needed data")
    
    # Query all data upfront and close DB connection immediately
    # This prevents holding the connection during long-running TTS generation
    with get_background_db() as db:
        logger.info(f"[GEN] Step 4: Querying scene {scene_id}")
        
        # Get the scene
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if not scene:
            logger.error(f"[GEN] Step 4 FAILED: Scene {scene_id} not found")
            return
        
        logger.info(f"[GEN] Step 5: Scene found, querying active variant")
        
        # Get the story to determine branch_id
        from app.models.story import Story
        story = db.query(Story).filter(Story.id == scene.story_id).first()
        if not story:
            logger.error(f"[GEN] Step 5 FAILED: Story {scene.story_id} not found")
            await tts_session_manager.send_message(session_id, {
                "type": "error",
                "message": "Story not found"
            })
            return
        
        # Get branch_id (prefer story's current_branch_id, fallback to scene's branch_id)
        branch_id = story.current_branch_id if story.current_branch_id else scene.branch_id
        logger.info(f"[GEN] Step 5b: Using branch_id={branch_id} for scene {scene_id}")
        
        # Get the active variant content from story flow (filtered by branch_id)
        from app.models.story_flow import StoryFlow
        from app.models.scene_variant import SceneVariant
        
        flow_query = db.query(StoryFlow).filter(
            StoryFlow.scene_id == scene_id,
            StoryFlow.is_active == True
        )
        
        # Filter by branch_id if available
        if branch_id is not None:
            flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
        
        flow_entry = flow_query.first()
        
        if not flow_entry or not flow_entry.scene_variant_id:
            logger.error(f"[GEN] Step 5 FAILED: No active variant for scene {scene_id}")
            await tts_session_manager.send_message(session_id, {
                "type": "error",
                "message": "No active scene variant found"
            })
            return
        
        logger.info(f"[GEN] Step 6: Flow entry found, variant_id={flow_entry.scene_variant_id}")
        
        variant = db.query(SceneVariant).filter(
            SceneVariant.id == flow_entry.scene_variant_id
        ).first()
        
        if not variant or not variant.content:
            logger.error(f"[GEN] Step 6 FAILED: Variant {flow_entry.scene_variant_id} has no content")
            await tts_session_manager.send_message(session_id, {
                "type": "error",
                "message": "Scene variant has no content"
            })
            return
        
        logger.info(f"[GEN] Step 7: Variant found, content length={len(variant.content)}")
        
        # Extract scene content
        scene_content = variant.content
        
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
        
        # Extract all TTS settings we need
        is_progressive = tts_settings.progressive_narration
        provider_type = tts_settings.tts_provider_type
        api_url = tts_settings.tts_api_url
        api_key = tts_settings.tts_api_key or ""
        timeout = tts_settings.tts_timeout or 30
        extra_params = tts_settings.tts_extra_params or {}
        default_voice = tts_settings.default_voice or "default"
        speech_speed = tts_settings.speech_speed or 1.0
        chunk_size = tts_settings.chunk_size or 280
        
        logger.info(f"[GEN] TTS settings: provider={provider_type}, default_voice={default_voice}, from_db={tts_settings.default_voice}")
        
        # If voice is still "default", try to get it from provider-specific config or fetch first available voice
        if default_voice == "default":
            provider_config = db.query(TTSProviderConfigModel).filter(
                TTSProviderConfigModel.user_id == user_id,
                TTSProviderConfigModel.provider_type == provider_type
            ).first()
            if provider_config and provider_config.voice_id and provider_config.voice_id != "default":
                default_voice = provider_config.voice_id
                logger.info(f"[GEN] Using voice from provider config: {default_voice}")
            else:
                logger.warning(f"[GEN] Voice is 'default', attempting to fetch first available voice from provider")
                # Try to get first available voice from the provider
                try:
                    from app.services.tts.factory import TTSProviderFactory
                    temp_provider = TTSProviderFactory.create_provider(
                        provider_type=provider_type,
                        api_url=api_url,
                        api_key=api_key,
                        timeout=timeout,
                        extra_params=extra_params
                    )
                    voices = await temp_provider.get_voices()
                    if voices and len(voices) > 0:
                        default_voice = voices[0].id
                        logger.info(f"[GEN] Using first available voice: {default_voice}")
                    else:
                        logger.error(f"[GEN] No voices available from provider, keeping 'default'")
                except Exception as e:
                    logger.error(f"[GEN] Failed to fetch voices: {e}, keeping 'default'")
    
    # DB connection is now closed - proceed with TTS generation
    logger.info(f"[GEN] Step 7b: Database queries complete, connection closed")
    
    try:
        # Check if this is an auto-play session
        session = tts_session_manager.get_session(session_id)
        is_auto_play = session and session.auto_play
        
        logger.info(f"[GEN] Step 8: Checking WebSocket connection (auto_play={is_auto_play})")
        
        if is_auto_play:
            # For auto-play: Start generating immediately, don't wait for WebSocket
            # Audio chunks will be buffered and sent when WebSocket connects
            logger.info(f"[GEN] Step 9 (AUTO-PLAY): Starting immediately, no WebSocket wait")
        else:
            # For manual TTS: Wait for WebSocket to connect (up to 10 seconds)
            logger.info(f"[GEN] Step 9 (MANUAL): Waiting for WebSocket connection...")
            for i in range(20):  # 20 attempts × 0.5s = 10 seconds max
                session = tts_session_manager.get_session(session_id)
                if session and session.websocket:
                    logger.info(f"[GEN] Step 9 SUCCESS: WebSocket connected after {i*0.5}s")
                    break
                if i % 4 == 0:  # Log every 2 seconds
                    logger.info(f"[GEN] Step 9: Still waiting... ({i*0.5}s elapsed)")
                await asyncio.sleep(0.5)
            else:
                logger.error(f"[GEN] Step 9 TIMEOUT: WebSocket never connected after 10s")
                return
        
        logger.info(f"[GEN] Step 10: Setting is_generating=True")
        
        # Mark session as generating
        tts_session_manager.set_generating(session_id, True)
        
        logger.info(f"[GEN] Step 11: Starting TTS generation (no DB connection held)")
        
        if is_progressive:
            # Generate chunks and stream them
            # Use text chunker to split scene text
            from app.services.tts.text_chunker import TextChunker
            chunker = TextChunker(max_chunk_size=chunk_size)
            
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
                provider_type=provider_type,
                api_url=api_url,
                api_key=api_key,
                timeout=timeout,
                extra_params=extra_params
            )
            
            # Get audio format
            format = AudioFormat.MP3
            if extra_params:
                format_str = extra_params.get("format", "mp3")
                try:
                    format = AudioFormat(format_str)
                except ValueError:
                    pass
            
            # Track consecutive failures to abort early if provider is down
            consecutive_failures = 0
            max_consecutive_failures = 3
            
            # Generate each chunk and stream immediately
            for i, text_chunk in enumerate(text_chunks, start=1):
                # Check if session has been cancelled
                session = tts_session_manager.get_session(session_id)
                if not session or session.is_cancelled:
                    logger.info(f"[GEN] Generation cancelled for session {session_id} at chunk {i}/{total_chunks}")
                    break
                
                # Abort if too many consecutive failures (provider likely down)
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"[GEN] Aborting generation after {consecutive_failures} consecutive failures")
                    await tts_session_manager.send_message(session_id, {
                        "type": "error",
                        "message": f"TTS service is experiencing issues. Aborted after {consecutive_failures} consecutive failures.",
                        "is_provider_error": True
                    })
                    break
                
                try:
                    # Extract text from TextChunk object
                    chunk_text = text_chunk.text
                    
                    # Generate audio for this chunk using provider directly
                    logger.info(f"[GEN] Creating TTS request: voice_id={default_voice}, provider={provider_type}")
                    request = TTSRequest(
                        text=chunk_text,
                        voice_id=default_voice,
                        speed=speech_speed,
                        format=format
                    )
                    
                    # Use user's configured timeout with a reasonable multiplier for per-chunk timeout
                    # Add 50% buffer to user's timeout to account for network delays
                    chunk_timeout = int(timeout * 1.5)
                    chunk_timeout = max(chunk_timeout, 60)  # Minimum 60 seconds
                    chunk_timeout = min(chunk_timeout, 180)  # Maximum 180 seconds per chunk
                    
                    try:
                        response = await asyncio.wait_for(
                            provider.synthesize(request),
                            timeout=chunk_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"[GEN] Chunk {i} generation timed out after {chunk_timeout}s")
                        await tts_session_manager.send_message(session_id, {
                            "type": "error",
                            "message": f"Chunk {i} generation timed out after {chunk_timeout} seconds",
                            "chunk_number": i
                        })
                        # Continue with other chunks - don't fail entire generation
                        continue
                    
                    audio_data = response.audio_data
                    
                    if not audio_data:
                        raise Exception(f"Failed to generate audio for chunk {i}")
                    
                    # Success! Reset consecutive failure counter
                    consecutive_failures = 0
                    
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
                    consecutive_failures += 1
                    logger.error(f"Error generating chunk {i}: {chunk_error} (consecutive failures: {consecutive_failures})")
                    
                    # Check if this looks like a circuit breaker error
                    error_msg = str(chunk_error)
                    is_circuit_breaker_error = "circuit breaker" in error_msg.lower() or "temporarily unavailable" in error_msg.lower()
                    
                    await tts_session_manager.send_message(session_id, {
                        "type": "error",
                        "message": f"Failed to generate chunk {i}: {error_msg}",
                        "chunk_number": i,
                        "consecutive_failures": consecutive_failures,
                        "is_provider_error": is_circuit_breaker_error
                    })
                    
                    # If circuit breaker is open, abort immediately
                    if is_circuit_breaker_error:
                        logger.error(f"[GEN] Circuit breaker open, aborting generation")
                        break
                    
                    # Continue with other chunks for non-circuit-breaker errors
                    continue
            
            # Send completion message only if we got at least one chunk
            session = tts_session_manager.get_session(session_id)
            chunks_sent = session.chunks_sent if session else 0
            if chunks_sent > 0:
                await tts_session_manager.send_message(session_id, {
                    "type": "complete",
                    "total_chunks": total_chunks,
                    "chunks_sent": chunks_sent,
                    "message": f"Generation complete ({chunks_sent}/{total_chunks} chunks)"
                })
            else:
                await tts_session_manager.send_message(session_id, {
                    "type": "error",
                    "message": "Failed to generate any audio chunks"
                })
            
        else:
            # Generate single audio file (non-progressive mode)
            from app.services.tts.factory import TTSProviderFactory
            from app.services.tts.base import TTSRequest, AudioFormat
            
            provider = TTSProviderFactory.create_provider(
                provider_type=provider_type,
                api_url=api_url,
                api_key=api_key,
                timeout=timeout,
                extra_params=extra_params
            )
            
            # Get audio format
            format = AudioFormat.MP3
            if extra_params:
                format_str = extra_params.get("format", "mp3")
                try:
                    format = AudioFormat(format_str)
                except ValueError:
                    pass
            
            # Generate audio for entire scene
            request = TTSRequest(
                text=scene_content,
                voice_id=default_voice,
                speed=speech_speed,
                format=format
            )
            
            try:
                response = await provider.synthesize(request)
                audio_data = response.audio_data
                
                if not audio_data:
                    raise Exception("Failed to generate audio")
                
                # Convert to base64 for WebSocket transmission
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                
                # Send as single chunk
                await tts_session_manager.send_message(session_id, {
                    "type": "chunk_ready",
                    "chunk_number": 1,
                    "total_chunks": 1,
                    "audio_base64": audio_base64,
                    "size_bytes": len(audio_data),
                    "duration": response.duration
                })
                
                await tts_session_manager.send_message(session_id, {
                    "type": "complete",
                    "total_chunks": 1,
                    "message": "Audio generated successfully"
                })
            except Exception as e:
                logger.error(f"Failed to generate single audio file: {e}")
                await tts_session_manager.send_message(session_id, {
                    "type": "error",
                    "message": f"Failed to generate audio: {str(e)}"
                })
                return
        
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
        # DB connection already closed by context manager


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
            detail="Failed to get audio status"
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
    
    # Get scene variant content (filtered by branch_id)
    from app.models.story_flow import StoryFlow
    from app.models.scene_variant import SceneVariant
    
    # Get branch_id (prefer story's current_branch_id, fallback to scene's branch_id)
    branch_id = story.current_branch_id if story.current_branch_id else scene.branch_id
    
    flow_query = db.query(StoryFlow).filter(
        StoryFlow.scene_id == scene.id,
        StoryFlow.is_active == True
    )
    
    # Filter by branch_id if available
    if branch_id is not None:
        flow_query = flow_query.filter(StoryFlow.branch_id == branch_id)
    
    flow_entry = flow_query.first()
    
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
            detail="Failed to serve audio chunk"
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
            detail="Failed to delete audio chunks"
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
