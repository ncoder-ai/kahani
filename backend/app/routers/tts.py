"""
TTS API Endpoints

Provides REST API for text-to-speech functionality.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging
import os

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.scene import Scene
from app.models.tts_settings import TTSSettings
from app.services.tts import TTSService, TTSProviderRegistry
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
            extra_params=db_model.tts_extra_params
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
    
    db.commit()
    db.refresh(tts_settings)
    
    logger.info(f"Updated TTS settings for user {current_user.id}")
    
    return TTSSettingsResponse.from_db_model(tts_settings)


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
                instance = provider_class(api_url="", api_key="")
                result.append(ProviderInfo(
                    type=provider_type,
                    name=instance.provider_name,
                    supports_streaming=instance.supports_streaming
                ))
            except Exception as e:
                logger.warning(f"Could not instantiate provider {provider_type}: {e}")
    
    return result


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


@router.post("/generate/{scene_id}", response_model=AudioInfoResponse)
async def generate_scene_audio(
    scene_id: int,
    request: GenerateAudioRequest = GenerateAudioRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate or retrieve cached audio for a scene"""
    
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
        tts_service = TTSService(db)
        scene_audio = await tts_service.get_or_generate_scene_audio(
            scene=scene,
            user_id=current_user.id,
            force_regenerate=request.force_regenerate
        )
        
        if not scene_audio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TTS not configured"
            )
        
        return AudioInfoResponse(
            scene_id=scene_audio.scene_id,
            voice_id=scene_audio.voice_used,  # Fixed: voice_used not voice_id
            provider_type=scene_audio.provider_used,  # Fixed: provider_used not provider_type
            file_size=scene_audio.file_size,
            duration=scene_audio.duration,
            format=scene_audio.audio_format,  # Fixed: audio_format not format
            generated_at=scene_audio.created_at.isoformat(),  # Fixed: created_at not generated_at
            cached=not request.force_regenerate
        )
        
    except Exception as e:
        logger.error(f"Failed to generate scene audio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate audio: {str(e)}"
        )


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
    """Get audio file for a scene"""
    
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
                "Content-Disposition": f"inline; filename=scene_{scene_id}.wav"
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
                SceneAudio.voice_id == tts_settings.default_voice
            )
        ).first()
        
        if not scene_audio or not scene_audio.file_path or not os.path.exists(scene_audio.file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio not found. Generate it first using POST /api/tts/generate/{scene_id}"
            )
        
        # Determine content type
        content_type = "audio/wav"
        if scene_audio.format == "mp3":
            content_type = "audio/mpeg"
        elif scene_audio.format == "ogg":
            content_type = "audio/ogg"
        
        return FileResponse(
            scene_audio.file_path,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=scene_{scene_id}.{scene_audio.format}"
            }
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
