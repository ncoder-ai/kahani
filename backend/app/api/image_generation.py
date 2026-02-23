"""
Image Generation API Endpoints

Provides REST endpoints for AI-powered image generation using ComfyUI.
"""

import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import User, UserSettings, GeneratedImage, Character, Scene, Story, StoryCharacter
from ..config import settings
from ..services.image_generation import ComfyUIProvider, GenerationRequest, GenerationStatus

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ServerStatusResponse(BaseModel):
    """Response for server status check"""
    online: bool
    queue_running: int = 0
    queue_pending: int = 0
    gpu_memory: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class AvailableModelsResponse(BaseModel):
    """Response for available models"""
    checkpoints: List[str] = Field(default_factory=list)
    samplers: List[str] = Field(default_factory=list)
    schedulers: List[str] = Field(default_factory=list)


class StylePreset(BaseModel):
    """Style preset information"""
    name: str
    description: str
    prompt_suffix: str
    negative_prompt: str


class StylePresetsResponse(BaseModel):
    """Response for available style presets"""
    presets: Dict[str, StylePreset]


class GeneratePortraitRequest(BaseModel):
    """Request to generate a character portrait"""
    style: str = "illustrated"
    checkpoint: Optional[str] = None
    width: int = 1024
    height: int = 1024
    steps: int = 4
    cfg_scale: float = 1.5


class GenerateSceneImageRequest(BaseModel):
    """Request to generate an image for a scene"""
    style: str = "illustrated"
    checkpoint: Optional[str] = None
    width: int = 1024
    height: int = 1024
    steps: int = 4
    cfg_scale: float = 1.5
    custom_prompt: Optional[str] = None  # Override auto-generated prompt


class GenerateCharacterImageRequest(BaseModel):
    """Request to generate an in-context image for a character in a scene"""
    character_id: int
    style: str = "illustrated"
    checkpoint: Optional[str] = None
    width: int = 1024
    height: int = 1024
    steps: int = 4
    cfg_scale: float = 1.5
    custom_prompt: Optional[str] = None


class GenerationJobResponse(BaseModel):
    """Response for a generation job"""
    job_id: str
    status: str
    progress: float = 0.0
    image_id: Optional[int] = None
    error: Optional[str] = None
    prompt: Optional[str] = None


class ImageResponse(BaseModel):
    """Response for a generated image"""
    id: int
    story_id: int
    branch_id: Optional[int]
    scene_id: Optional[int]
    character_id: Optional[int]
    image_type: str
    file_path: str
    thumbnail_path: Optional[str]
    prompt: Optional[str]
    width: Optional[int]
    height: Optional[int]
    created_at: str


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_settings(db: Session, user_id: int) -> UserSettings:
    """Get or create user settings for the given user"""
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == user_id
    ).first()

    if not user_settings:
        user_settings = UserSettings(user_id=user_id)
        user_settings.populate_from_defaults()
        db.add(user_settings)
        db.commit()
        db.refresh(user_settings)

    return user_settings


def get_comfyui_provider(user_settings: UserSettings) -> ComfyUIProvider:
    """Get a ComfyUI provider configured for the user"""
    img_settings = user_settings._get_image_generation_settings()

    server_url = img_settings.get("comfyui_server_url")
    if not server_url:
        # Fall back to config defaults
        server_url = settings.image_generation.get("comfyui", {}).get("server_url", "")

    if not server_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ComfyUI server URL not configured. Please configure it in settings."
        )

    api_key = img_settings.get("comfyui_api_key") or settings.image_generation.get("comfyui", {}).get("api_key", "")
    timeout = settings.image_generation.get("comfyui", {}).get("timeout", 300)

    return ComfyUIProvider(
        server_url=server_url,
        api_key=api_key if api_key else None,
        timeout=timeout,
    )


def get_style_preset(style_name: str) -> Dict[str, str]:
    """Get style preset configuration"""
    presets = settings.image_generation.get("style_presets", {})
    preset = presets.get(style_name, presets.get("illustrated", {}))
    return {
        "prompt_suffix": preset.get("prompt_suffix", ""),
        "negative_prompt": preset.get("negative_prompt", ""),
    }


def get_storage_path() -> str:
    """Get the image storage path, creating it if necessary"""
    storage_path = settings.image_generation.get("storage_path", "./data/images")
    os.makedirs(storage_path, exist_ok=True)
    return storage_path


async def save_generated_image(
    image_data: bytes,
    story_id: Optional[int],
    image_type: str,
    prompt: str,
    generation_params: Dict[str, Any],
    db: Session,
    branch_id: Optional[int] = None,
    scene_id: Optional[int] = None,
    character_id: Optional[int] = None,
) -> GeneratedImage:
    """Save a generated image to disk and database"""
    storage_path = get_storage_path()

    # Create subdirectory - use "portraits" for character portraits without a story
    if story_id is None:
        subdir = "portraits"
    else:
        subdir = f"story_{story_id}"
    image_dir = os.path.join(storage_path, subdir)
    os.makedirs(image_dir, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename = f"{image_type}_{timestamp}_{unique_id}.png"
    file_path = os.path.join(image_dir, filename)

    # Write image to disk
    with open(file_path, "wb") as f:
        f.write(image_data)

    # Create relative path for database
    relative_path = f"{subdir}/{filename}"

    # Create database record
    generated_image = GeneratedImage(
        story_id=story_id,
        branch_id=branch_id,
        scene_id=scene_id,
        character_id=character_id,
        image_type=image_type,
        file_path=relative_path,
        prompt=prompt,
        negative_prompt=generation_params.get("negative_prompt", ""),
        generation_params=generation_params,
        width=generation_params.get("width"),
        height=generation_params.get("height"),
        provider="comfyui",
    )

    db.add(generated_image)
    db.commit()
    db.refresh(generated_image)

    return generated_image


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/server-status", response_model=ServerStatusResponse)
async def get_server_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check if the user's ComfyUI server is reachable and get status info.
    """
    try:
        user_settings = get_user_settings(db, current_user.id)
        provider = get_comfyui_provider(user_settings)
        status_info = await provider.get_server_status()
        await provider.close()

        return ServerStatusResponse(
            online=status_info.get("online", False),
            queue_running=status_info.get("queue_running", 0),
            queue_pending=status_info.get("queue_pending", 0),
            gpu_memory=status_info.get("gpu_memory", {}),
            error=status_info.get("error"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking server status: {e}")
        return ServerStatusResponse(online=False, error=str(e))


@router.get("/available-models", response_model=AvailableModelsResponse)
async def get_available_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get list of available checkpoints and samplers from the user's ComfyUI server.
    """
    try:
        user_settings = get_user_settings(db, current_user.id)
        provider = get_comfyui_provider(user_settings)

        checkpoints = await provider.get_available_checkpoints()
        samplers = await provider.get_available_samplers()
        schedulers = await provider.get_available_schedulers()

        await provider.close()

        return AvailableModelsResponse(
            checkpoints=checkpoints,
            samplers=samplers,
            schedulers=schedulers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to get available models"
        )


@router.get("/style-presets", response_model=StylePresetsResponse)
async def get_style_presets(
    current_user: User = Depends(get_current_user),
):
    """
    Get available style presets for image generation.
    """
    presets_config = settings.image_generation.get("style_presets", {})
    presets = {}

    for key, config in presets_config.items():
        presets[key] = StylePreset(
            name=config.get("name", key.title()),
            description=config.get("description", ""),
            prompt_suffix=config.get("prompt_suffix", ""),
            negative_prompt=config.get("negative_prompt", ""),
        )

    return StylePresetsResponse(presets=presets)


# In-memory job tracking (simple implementation for now)
# In production, this should use Redis or database
_generation_jobs: Dict[str, Dict[str, Any]] = {}


@router.get("/status/{job_id}", response_model=GenerationJobResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the status of a generation job.

    Note: The current implementation uses synchronous generation,
    so jobs complete immediately. This endpoint is provided for
    API compatibility and future async implementation.
    """
    # Check in-memory job store
    if job_id in _generation_jobs:
        job = _generation_jobs[job_id]
        return GenerationJobResponse(
            job_id=job_id,
            status=job.get("status", "unknown"),
            progress=job.get("progress", 0.0),
            image_id=job.get("image_id"),
            error=job.get("error"),
        )

    # Job not found - may have already completed or never existed
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Job not found or already completed"
    )


@router.post("/character/{character_id}/portrait", response_model=GenerationJobResponse)
async def generate_character_portrait(
    character_id: int,
    request: GeneratePortraitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a portrait image for a character based on their appearance description.
    """
    user_settings = get_user_settings(db, current_user.id)

    # Get the character
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )

    # Get the character's appearance for the prompt
    appearance = character.appearance or character.description or ""
    if not appearance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Character has no appearance description"
        )

    # Build the prompt
    style_preset = get_style_preset(request.style)
    prompt = f"portrait of {character.name}, {appearance}, {style_preset['prompt_suffix']}"
    negative_prompt = style_preset["negative_prompt"]

    # Get user's checkpoint preference or use request
    img_settings = user_settings._get_image_generation_settings()
    checkpoint = request.checkpoint or img_settings.get("comfyui_checkpoint") or None

    try:
        provider = get_comfyui_provider(user_settings)

        # Create generation request
        gen_request = GenerationRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            checkpoint=checkpoint,
        )

        # Generate and wait for result
        result = await provider.generate_and_wait(gen_request)
        await provider.close()

        if not result.success or result.status != GenerationStatus.COMPLETED:
            # Ensure error is a string or None
            error_msg = str(result.error_message) if result.error_message else None
            logger.warning(f"Portrait generation failed: status={result.status}, error={error_msg}")
            return GenerationJobResponse(
                job_id=result.job_id or "",
                status=result.status.value,
                error=error_msg,
            )

        # Save the portrait as a default (no story_id)
        # This makes it available across all stories the character is in
        generation_params = {
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "checkpoint": checkpoint,
            "style": request.style,
            "negative_prompt": negative_prompt,
        }

        generated_image = await save_generated_image(
            image_data=result.image_data,
            story_id=None,  # Default portrait, not tied to a specific story
            image_type="character_portrait",
            prompt=prompt,
            generation_params=generation_params,
            db=db,
            branch_id=None,
            character_id=character_id,
        )

        # Update character with portrait
        character.portrait_image_id = generated_image.id
        db.commit()

        return GenerationJobResponse(
            job_id=result.job_id or "",
            status="completed",
            progress=1.0,
            image_id=generated_image.id,
            prompt=prompt,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating character portrait: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate portrait"
        )


@router.post("/character/{character_id}/portrait/upload")
async def upload_character_portrait(
    character_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload an existing image as a character's portrait.
    """
    # Get the character
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )

    # Read file content
    image_data = await file.read()

    # Save the uploaded image as a default portrait (no story_id)
    storage_path = get_storage_path()
    portrait_dir = os.path.join(storage_path, "portraits")
    os.makedirs(portrait_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
    filename = f"character_portrait_{timestamp}_{unique_id}{ext}"
    file_path = os.path.join(portrait_dir, filename)

    with open(file_path, "wb") as f:
        f.write(image_data)

    relative_path = f"portraits/{filename}"

    # Create database record - no story_id for default portraits
    generated_image = GeneratedImage(
        story_id=None,
        branch_id=None,
        character_id=character_id,
        image_type="character_portrait",
        file_path=relative_path,
        prompt="Uploaded image",
        provider="upload",
    )

    db.add(generated_image)
    db.commit()
    db.refresh(generated_image)

    # Update character with portrait
    character.portrait_image_id = generated_image.id
    db.commit()

    return {
        "id": generated_image.id,
        "file_path": relative_path,
        "message": "Portrait uploaded successfully"
    }


@router.delete("/character/{character_id}/portrait")
async def delete_character_portrait(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove a character's portrait.
    """
    # Get the character
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )

    if not character.portrait_image_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character has no portrait"
        )

    # Get the image
    image = db.query(GeneratedImage).filter(
        GeneratedImage.id == character.portrait_image_id
    ).first()

    # Clear the character's portrait reference
    character.portrait_image_id = None
    db.commit()

    # Optionally delete the image file and record
    if image:
        storage_path = get_storage_path()
        file_path = os.path.join(storage_path, image.file_path)
        if os.path.exists(file_path):
            os.remove(file_path)

        db.delete(image)
        db.commit()

    return {"message": "Portrait removed successfully"}


# ============================================================================
# Scene Image Generation
# ============================================================================

@router.post("/scene/{scene_id}", response_model=GenerationJobResponse)
async def generate_scene_image(
    scene_id: int,
    request: GenerateSceneImageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate an image for a scene.

    Uses the scene content, characters present, and location to generate
    an appropriate image. If characters have portraits, IP-Adapter will
    be used for consistency (SDXL models only).
    """
    user_settings = get_user_settings(db, current_user.id)

    # Get the scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()

    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )

    # Verify user owns the story
    story = db.query(Story).filter(
        Story.id == scene.story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Get scene content from variants (content is stored in SceneVariant, not Scene)
    from ..models.scene_variant import SceneVariant

    # Get the most recent variant for this scene
    variant = db.query(SceneVariant).filter(
        SceneVariant.scene_id == scene_id
    ).order_by(SceneVariant.created_at.desc()).first()

    scene_content = variant.content if variant else ""
    if not scene_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scene has no content"
        )

    # Build the prompt
    style_preset = get_style_preset(request.style)

    if request.custom_prompt:
        prompt = f"{request.custom_prompt}, {style_preset['prompt_suffix']}"
    else:
        # Use LLM to generate an optimized image prompt from scene content
        try:
            from ..services.image_generation.prompt_generator import ImagePromptGenerator
            from ..services.llm.service import UnifiedLLMService
            from ..services.llm.prompts import PromptManager
            from .story_helpers import get_or_create_user_settings

            llm_service = UnifiedLLMService()
            prompt_manager = PromptManager()
            llm_user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
            prompt_gen = ImagePromptGenerator(current_user.id, llm_user_settings, llm_service, prompt_manager)

            # Get characters with appearances + background for richer prompt
            characters = []
            if variant and variant.characters_present:
                for char_name in variant.characters_present:
                    sc = db.query(StoryCharacter).join(Character).filter(
                        StoryCharacter.story_id == scene.story_id,
                        Character.name == char_name
                    ).first()
                    if sc:
                        char = db.query(Character).filter(Character.id == sc.character_id).first()
                        if char:
                            # Combine appearance + background for gender/ethnicity inference
                            appearance_parts = []
                            if char.background:
                                appearance_parts.append(char.background)
                            if char.appearance:
                                appearance_parts.append(char.appearance)
                            elif char.description:
                                appearance_parts.append(char.description)
                            characters.append({
                                "name": char.name,
                                "appearance": ". ".join(appearance_parts) if appearance_parts else "no description"
                            })

            generated = await prompt_gen.generate_scene_prompt(
                scene_content=scene_content,
                characters=characters,
                style_preset=request.style,
            )
            prompt = f"{generated}, {style_preset['prompt_suffix']}"
            logger.info(f"[IMAGE_GEN] LLM-generated scene prompt: {prompt[:200]}...")
        except Exception as e:
            logger.warning(f"[IMAGE_GEN] LLM prompt generation failed, using fallback: {e}")
            scene_summary = scene_content[:200].strip()
            if scene_summary and not scene_summary.endswith('.'):
                scene_summary = scene_summary.rsplit(' ', 1)[0] + '...'
            prompt = f"{scene_summary}, {style_preset['prompt_suffix']}"

    negative_prompt = style_preset["negative_prompt"]

    # Get user's checkpoint preference or use request
    img_settings = user_settings._get_image_generation_settings()
    checkpoint = request.checkpoint or img_settings.get("comfyui_checkpoint") or None

    try:
        provider = get_comfyui_provider(user_settings)

        # Create generation request
        from ..services.image_generation import GenerationRequest as GenRequest
        gen_request = GenRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            checkpoint=checkpoint,
        )

        # Generate and wait for result
        result = await provider.generate_and_wait(gen_request)
        await provider.close()

        if not result.success or result.status != GenerationStatus.COMPLETED:
            error_msg = str(result.error_message) if result.error_message else None
            logger.warning(f"Scene image generation failed: status={result.status}, error={error_msg}")
            return GenerationJobResponse(
                job_id=result.job_id or "",
                status=result.status.value,
                error=error_msg,
            )

        # Save the image
        generation_params = {
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "checkpoint": checkpoint,
            "style": request.style,
            "negative_prompt": negative_prompt,
        }

        generated_image = await save_generated_image(
            image_data=result.image_data,
            story_id=scene.story_id,
            image_type="scene",
            prompt=prompt,
            generation_params=generation_params,
            db=db,
            branch_id=scene.branch_id,
            scene_id=scene_id,
        )

        return GenerationJobResponse(
            job_id=result.job_id or "",
            status="completed",
            progress=1.0,
            image_id=generated_image.id,
            prompt=prompt,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating scene image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate scene image"
        )


@router.post("/scene/{scene_id}/character", response_model=GenerationJobResponse)
async def generate_character_image(
    scene_id: int,
    request: GenerateCharacterImageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate an in-context image for a character based on their current state in the story.

    Uses the character's base appearance combined with their dynamic state
    (location, emotions, attire, items held) to generate a contextual image.
    """
    user_settings = get_user_settings(db, current_user.id)

    # Get the scene
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )

    # Verify user owns the story
    story = db.query(Story).filter(
        Story.id == scene.story_id,
        Story.owner_id == current_user.id
    ).first()
    if not story:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Load the character
    character = db.query(Character).filter(
        Character.id == request.character_id
    ).first()
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )

    # Always prioritize the physical appearance from the character card
    base_appearance = character.appearance or ""
    character_description = character.description or ""
    if not base_appearance and not character_description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Character has no appearance description"
        )
    # If no dedicated appearance field, fall back to general description
    if not base_appearance:
        base_appearance = character_description

    # Get scene content for atmospheric context
    from ..models.scene_variant import SceneVariant
    variant = db.query(SceneVariant).filter(
        SceneVariant.scene_id == scene_id
    ).order_by(SceneVariant.created_at.desc()).first()
    scene_content = variant.content if variant else ""

    # Build the prompt
    style_preset = get_style_preset(request.style)

    if request.custom_prompt:
        prompt = f"{request.custom_prompt}, {style_preset['prompt_suffix']}"
    else:
        # Load character state for dynamic context
        from ..services.entity_state_service import EntityStateService
        from .story_helpers import get_or_create_user_settings
        llm_user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
        entity_service = EntityStateService(current_user.id, llm_user_settings)

        # Try batch snapshot for historical scene state
        char_state_dict = entity_service.get_character_state_at_scene(
            db, request.character_id, scene.story_id, scene.branch_id, scene.sequence_number
        )

        current_state = {}
        if char_state_dict:
            current_state = {
                "appearance": char_state_dict.get("appearance"),
                "current_location": char_state_dict.get("current_location"),
                "current_position": char_state_dict.get("current_position"),
                "emotional_state": char_state_dict.get("emotional_state"),
                "physical_condition": char_state_dict.get("physical_condition"),
                "items_in_hand": char_state_dict.get("items_in_hand"),
            }
        else:
            # Fall back to live state (correct for latest scene or when no batches exist)
            char_state = entity_service.get_character_state(
                db, request.character_id, scene.story_id, scene.branch_id
            )
            if char_state:
                current_state = {
                    "appearance": char_state.appearance,
                    "current_location": char_state.current_location,
                    "current_position": char_state.current_position,
                    "emotional_state": char_state.emotional_state,
                    "physical_condition": char_state.physical_condition,
                    "items_in_hand": char_state.items_in_hand,
                }

        # Use LLM to generate optimized prompt with scene atmosphere
        try:
            from ..services.image_generation.prompt_generator import ImagePromptGenerator
            from ..services.llm.service import UnifiedLLMService
            from ..services.llm.prompts import PromptManager
            from .story_helpers import get_or_create_user_settings

            llm_service = UnifiedLLMService()
            prompt_manager = PromptManager()
            llm_user_settings = get_or_create_user_settings(current_user.id, db, current_user, story)
            prompt_gen = ImagePromptGenerator(current_user.id, llm_user_settings, llm_service, prompt_manager)

            # Build background context for ethnicity/origin
            bg_parts = []
            if character_description and character_description != base_appearance:
                bg_parts.append(character_description)
            if character.background:
                bg_parts.append(character.background)
            character_background = ". ".join(bg_parts) if bg_parts else None

            generated = await prompt_gen.generate_character_in_context_prompt(
                character_name=character.name,
                base_appearance=base_appearance,
                current_state=current_state,
                style_preset=request.style,
                scene_content=scene_content,
                character_background=character_background,
            )
            prompt = f"{generated}, {style_preset['prompt_suffix']}"
            logger.info(f"[IMAGE_GEN] LLM-generated character prompt: {prompt[:200]}...")
        except Exception as e:
            logger.warning(f"[IMAGE_GEN] LLM prompt generation failed, using fallback: {e}")
            appearance = current_state.get("appearance") or base_appearance
            location = current_state.get("current_location") or ""
            emotional = current_state.get("emotional_state") or ""
            parts = [f"portrait of {character.name}", appearance]
            if location:
                parts.append(f"in {location}")
            if emotional:
                parts.append(f"{emotional} expression")
            parts.append(style_preset["prompt_suffix"])
            prompt = ", ".join(parts)

    negative_prompt = style_preset["negative_prompt"]

    # Get checkpoint
    img_settings = user_settings._get_image_generation_settings()
    checkpoint = request.checkpoint or img_settings.get("comfyui_checkpoint") or None

    try:
        provider = get_comfyui_provider(user_settings)

        from ..services.image_generation import GenerationRequest as GenRequest
        gen_request = GenRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            checkpoint=checkpoint,
        )

        result = await provider.generate_and_wait(gen_request)
        await provider.close()

        if not result.success or result.status != GenerationStatus.COMPLETED:
            error_msg = str(result.error_message) if result.error_message else None
            logger.warning(f"Character image generation failed: status={result.status}, error={error_msg}")
            return GenerationJobResponse(
                job_id=result.job_id or "",
                status=result.status.value,
                error=error_msg,
            )

        generation_params = {
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "checkpoint": checkpoint,
            "style": request.style,
            "negative_prompt": negative_prompt,
        }

        generated_image = await save_generated_image(
            image_data=result.image_data,
            story_id=scene.story_id,
            image_type="character_scene",
            prompt=prompt,
            generation_params=generation_params,
            db=db,
            branch_id=scene.branch_id,
            scene_id=scene_id,
            character_id=request.character_id,
        )

        return GenerationJobResponse(
            job_id=result.job_id or "",
            status="completed",
            progress=1.0,
            image_id=generated_image.id,
            prompt=prompt,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating character image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate character image"
        )


@router.get("/story/{story_id}/images", response_model=List[ImageResponse])
async def get_story_images(
    story_id: int,
    scene_id: Optional[int] = None,
    character_id: Optional[int] = None,
    image_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all generated images for a story, with optional filters.
    """
    # Verify user owns the story
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )

    # Build query
    query = db.query(GeneratedImage).filter(GeneratedImage.story_id == story_id)

    if scene_id:
        query = query.filter(GeneratedImage.scene_id == scene_id)
    if character_id:
        query = query.filter(GeneratedImage.character_id == character_id)
    if image_type:
        query = query.filter(GeneratedImage.image_type == image_type)

    images = query.order_by(GeneratedImage.created_at.desc()).all()

    return [
        ImageResponse(
            id=img.id,
            story_id=img.story_id,
            branch_id=img.branch_id,
            scene_id=img.scene_id,
            character_id=img.character_id,
            image_type=img.image_type,
            file_path=img.file_path,
            thumbnail_path=img.thumbnail_path,
            prompt=img.prompt,
            width=img.width,
            height=img.height,
            created_at=img.created_at.isoformat() if img.created_at else "",
        )
        for img in images
    ]


@router.get("/story/{story_id}/portraits", response_model=List[ImageResponse])
async def get_story_character_portraits(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get character portraits for all characters in a story.
    This fetches portraits regardless of which story_id they were saved under.
    """
    # Verify user owns the story
    story = db.query(Story).filter(
        Story.id == story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )

    # Get all characters in this story
    story_chars = db.query(StoryCharacter).filter(
        StoryCharacter.story_id == story_id
    ).all()

    character_ids = [sc.character_id for sc in story_chars]

    if not character_ids:
        return []

    # Get ALL portraits for these characters:
    # 1. Default portraits (story_id=NULL)
    # 2. Story-specific portraits (story_id=current story)
    from sqlalchemy import or_
    images = db.query(GeneratedImage).filter(
        GeneratedImage.character_id.in_(character_ids),
        GeneratedImage.image_type == "character_portrait",
        or_(
            GeneratedImage.story_id.is_(None),  # Default portraits
            GeneratedImage.story_id == story_id  # Story-specific portraits
        )
    ).order_by(GeneratedImage.created_at.desc()).all()

    return [
        ImageResponse(
            id=img.id,
            story_id=img.story_id,
            branch_id=img.branch_id,
            scene_id=img.scene_id,
            character_id=img.character_id,
            image_type=img.image_type,
            file_path=img.file_path,
            thumbnail_path=img.thumbnail_path,
            prompt=img.prompt,
            width=img.width,
            height=img.height,
            created_at=img.created_at.isoformat() if img.created_at else "",
        )
        for img in images
    ]


@router.get("/images/{image_id}", response_model=ImageResponse)
async def get_image_details(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get image metadata by ID.
    """
    # Get the image record
    image = db.query(GeneratedImage).filter(GeneratedImage.id == image_id).first()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    # Verify access - either through story ownership or character ownership
    has_access = False

    if image.story_id:
        # Story-based image - verify user owns the story
        story = db.query(Story).filter(
            Story.id == image.story_id,
            Story.owner_id == current_user.id
        ).first()
        has_access = story is not None

    if not has_access and image.character_id:
        # Character portrait - verify user owns the character
        character = db.query(Character).filter(
            Character.id == image.character_id,
            Character.creator_id == current_user.id
        ).first()
        has_access = character is not None

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return ImageResponse(
        id=image.id,
        story_id=image.story_id,
        branch_id=image.branch_id,
        scene_id=image.scene_id,
        character_id=image.character_id,
        image_type=image.image_type,
        file_path=image.file_path,
        thumbnail_path=image.thumbnail_path,
        prompt=image.prompt,
        width=image.width,
        height=image.height,
        created_at=image.created_at.isoformat() if image.created_at else "",
    )


@router.get("/images/{image_id}/file")
async def get_image_file(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get an image file by ID. Requires authentication.
    """
    # Get the image record
    image = db.query(GeneratedImage).filter(GeneratedImage.id == image_id).first()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    # Verify access - either through story ownership or character ownership
    has_access = False

    if image.story_id:
        story = db.query(Story).filter(
            Story.id == image.story_id,
            Story.owner_id == current_user.id
        ).first()
        has_access = story is not None

    if not has_access and image.character_id:
        character = db.query(Character).filter(
            Character.id == image.character_id,
            Character.creator_id == current_user.id
        ).first()
        has_access = character is not None

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Get the file path
    storage_path = get_storage_path()
    file_path = os.path.join(storage_path, image.file_path)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found"
        )

    return FileResponse(file_path, media_type="image/png")


@router.delete("/images/{image_id}")
async def delete_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a generated image.
    """
    # Get the image record
    image = db.query(GeneratedImage).filter(GeneratedImage.id == image_id).first()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    # Verify user owns the story
    story = db.query(Story).filter(
        Story.id == image.story_id,
        Story.owner_id == current_user.id
    ).first()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # If this is a character portrait, clear the reference
    if image.character_id and image.image_type == "character_portrait":
        character = db.query(Character).filter(
            Character.id == image.character_id,
            Character.portrait_image_id == image_id
        ).first()
        if character:
            character.portrait_image_id = None

    # Delete the file
    storage_path = get_storage_path()
    file_path = os.path.join(storage_path, image.file_path)
    if os.path.exists(file_path):
        os.remove(file_path)

    if image.thumbnail_path:
        thumb_path = os.path.join(storage_path, image.thumbnail_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

    # Delete the database record
    db.delete(image)
    db.commit()

    return {"message": "Image deleted successfully"}
