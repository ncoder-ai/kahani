"""
Writing Style Presets API Router

Provides endpoints for managing user writing style presets.
These presets control how the AI writes stories (tone, style, NSFW settings, etc.)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from ..dependencies import get_current_user, get_db
from ..models.user import User
from ..models.writing_style_preset import WritingStylePreset
from ..services.llm.service import UnifiedLLMService

llm_service = UnifiedLLMService()

router = APIRouter(prefix="/api/writing-presets", tags=["writing-presets"])


# Pydantic models for request/response
class WritingStylePresetCreate(BaseModel):
    """Request model for creating a new preset"""
    name: str = Field(..., min_length=1, max_length=100, description="Name of the preset")
    description: Optional[str] = Field(None, description="Optional description of the writing style")
    system_prompt: str = Field(..., min_length=10, description="System prompt that controls AI writing style")
    summary_system_prompt: Optional[str] = Field(None, description="Optional override for story summaries")
    pov: Optional[str] = Field(None, description="Point of view: 'first', 'second', or 'third'")
    prose_style: Optional[str] = Field('balanced', description="Prose style: balanced, dialogue_forward, internal_monologue, action_driven, description_driven, stream_of_consciousness, free_indirect, poetic_lyrical")
    is_active: Optional[bool] = Field(False, description="Whether to set this preset as the active one")


class WritingStylePresetUpdate(BaseModel):
    """Request model for updating a preset"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = Field(None, min_length=10)
    summary_system_prompt: Optional[str] = None
    pov: Optional[str] = Field(None, description="Point of view: 'first', 'second', or 'third'")
    prose_style: Optional[str] = Field(None, description="Prose style: balanced, dialogue_forward, internal_monologue, action_driven, description_driven, stream_of_consciousness, free_indirect, poetic_lyrical")
    is_active: Optional[bool] = Field(None, description="Whether to set this preset as the active one")


class WritingStylePresetResponse(BaseModel):
    """Response model for a preset"""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    system_prompt: str
    summary_system_prompt: Optional[str]
    pov: Optional[str]
    prose_style: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# Helper functions
def get_preset_or_404(preset_id: int, user_id: int, db: Session) -> WritingStylePreset:
    """Get a preset by ID, ensuring it belongs to the user"""
    preset = db.query(WritingStylePreset).filter(
        WritingStylePreset.id == preset_id,
        WritingStylePreset.user_id == user_id
    ).first()
    
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing style preset not found"
        )
    
    return preset


def deactivate_all_presets(user_id: int, db: Session):
    """Deactivate all presets for a user"""
    db.query(WritingStylePreset).filter(
        WritingStylePreset.user_id == user_id
    ).update({"is_active": False})


# API Endpoints

# Static routes MUST come before dynamic routes like /{preset_id}
# Otherwise FastAPI will try to match "prose-styles" as a preset_id

@router.get("/prose-styles", response_model=list)
async def get_prose_styles(
    current_user: User = Depends(get_current_user)
):
    """Get all available prose styles from prompts.yml
    
    Returns the prose style definitions including name, description, and example
    for display in the frontend. This ensures the frontend always matches
    the backend configuration.
    """
    from ..services.llm.prompts import prompt_manager
    
    return prompt_manager.get_all_prose_styles()


@router.get("/default/template", response_model=dict)
async def get_default_template(
    current_user: User = Depends(get_current_user)
):
    """Get the default system prompt template for new presets
    
    Extracts the style portion from prompts.yml to show users what they're actually customizing.
    Technical requirements (formatting, choices) are automatically appended at runtime.
    """
    from ..services.llm.prompts import prompt_manager
    
    # Get the full scene generation prompt from YAML
    yaml_full_prompt = prompt_manager._get_yaml_prompt("scene_generation", "system")
    
    if yaml_full_prompt:
        # Extract just the style portion (everything before technical requirements)
        default_template = prompt_manager._extract_style_portion(yaml_full_prompt)
    else:
        # Fallback if YAML not available
        default_template = """You are a skilled interactive fiction writer. Create engaging, immersive story scenes that:
1. Advance the plot meaningfully using specific story context and established details
2. Develop characters through action and dialogue, referencing their existing traits and relationships
3. Maintain strict consistency with established story elements, characters, and world-building
4. Create dramatic tension and forward momentum appropriate to the established genre and tone
5. End at a natural stopping point that leaves the reader wanting more
6. Use vivid, descriptive language that draws readers into the specific world of this story
7. Keep appropriate pacing for the story moment and genre"""
    
    return {
        "name": "New Preset",
        "description": "Customize this preset to match your preferred writing style. Formatting and choices requirements are automatically added.",
        "system_prompt": default_template,
        "summary_system_prompt": None,
        "pov": "third",  # Default to third person
        "prose_style": "balanced"  # Default prose style
    }


@router.get("/", response_model=List[WritingStylePresetResponse])
async def list_presets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all writing style presets for the current user"""
    presets = db.query(WritingStylePreset).filter(
        WritingStylePreset.user_id == current_user.id
    ).order_by(WritingStylePreset.is_active.desc(), WritingStylePreset.created_at.desc()).all()
    
    return presets


@router.get("/{preset_id}", response_model=WritingStylePresetResponse)
async def get_preset(
    preset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific writing style preset"""
    preset = get_preset_or_404(preset_id, current_user.id, db)
    return preset


@router.post("/", response_model=WritingStylePresetResponse, status_code=status.HTTP_201_CREATED)
async def create_preset(
    preset_data: WritingStylePresetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new writing style preset"""
    make_active = preset_data.is_active or False

    # If activating, deactivate all other presets first
    if make_active:
        deactivate_all_presets(current_user.id, db)

    new_preset = WritingStylePreset(
        user_id=current_user.id,
        name=preset_data.name,
        description=preset_data.description,
        system_prompt=preset_data.system_prompt,
        summary_system_prompt=preset_data.summary_system_prompt,
        pov=preset_data.pov,
        prose_style=preset_data.prose_style or 'balanced',
        is_active=make_active,
    )

    db.add(new_preset)
    db.commit()
    db.refresh(new_preset)

    if make_active:
        llm_service.invalidate_user_client(current_user.id)

    return new_preset


@router.put("/{preset_id}", response_model=WritingStylePresetResponse)
async def update_preset(
    preset_id: int,
    preset_data: WritingStylePresetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a writing style preset"""
    preset = get_preset_or_404(preset_id, current_user.id, db)
    
    # Update fields if provided
    update_data = preset_data.model_dump(exclude_unset=True)
    
    # If setting is_active to True, deactivate all other presets first
    if update_data.get('is_active') is True:
        deactivate_all_presets(current_user.id, db)
    
    for field, value in update_data.items():
        setattr(preset, field, value)
    
    preset.updated_at = datetime.now()
    
    db.commit()
    db.refresh(preset)
    
    # Invalidate LLM cache if this is the active preset
    if preset.is_active:
        llm_service.invalidate_user_client(current_user.id)
    
    return preset


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(
    preset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a writing style preset"""
    preset = get_preset_or_404(preset_id, current_user.id, db)
    
    # Don't allow deleting the last preset
    preset_count = db.query(WritingStylePreset).filter(
        WritingStylePreset.user_id == current_user.id
    ).count()
    
    if preset_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your last preset. Create a new one first."
        )
    
    was_active = preset.is_active
    
    db.delete(preset)
    db.commit()
    
    # If we deleted the active preset, activate another one
    if was_active:
        first_preset = db.query(WritingStylePreset).filter(
            WritingStylePreset.user_id == current_user.id
        ).first()
        
        if first_preset:
            first_preset.is_active = True
            db.commit()
            llm_service.invalidate_user_client(current_user.id)
    
    return None


@router.post("/{preset_id}/activate", response_model=WritingStylePresetResponse)
async def activate_preset(
    preset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set a preset as the active one (deactivates all others)"""
    preset = get_preset_or_404(preset_id, current_user.id, db)
    
    # Deactivate all other presets
    deactivate_all_presets(current_user.id, db)
    
    # Activate this one
    preset.is_active = True
    preset.updated_at = datetime.now()
    
    db.commit()
    db.refresh(preset)
    
    # Invalidate LLM cache to use new preset
    llm_service.invalidate_user_client(current_user.id)
    
    return preset


@router.post("/{preset_id}/duplicate", response_model=WritingStylePresetResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_preset(
    preset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a copy of an existing preset"""
    original = get_preset_or_404(preset_id, current_user.id, db)
    
    # Create duplicate with "(Copy)" suffix
    duplicate = WritingStylePreset(
        user_id=current_user.id,
        name=f"{original.name} (Copy)",
        description=original.description,
        system_prompt=original.system_prompt,
        summary_system_prompt=original.summary_system_prompt,
        pov=original.pov,
        prose_style=original.prose_style,
        is_active=False
    )
    
    db.add(duplicate)
    db.commit()
    db.refresh(duplicate)
    
    return duplicate

