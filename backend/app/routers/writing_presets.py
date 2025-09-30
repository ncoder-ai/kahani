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
from ..services.llm_functions import invalidate_user_llm_cache

router = APIRouter(prefix="/api/writing-presets", tags=["writing-presets"])


# Pydantic models for request/response
class WritingStylePresetCreate(BaseModel):
    """Request model for creating a new preset"""
    name: str = Field(..., min_length=1, max_length=100, description="Name of the preset")
    description: Optional[str] = Field(None, description="Optional description of the writing style")
    system_prompt: str = Field(..., min_length=10, description="System prompt that controls AI writing style")
    summary_system_prompt: Optional[str] = Field(None, description="Optional override for story summaries")


class WritingStylePresetUpdate(BaseModel):
    """Request model for updating a preset"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = Field(None, min_length=10)
    summary_system_prompt: Optional[str] = None


class WritingStylePresetResponse(BaseModel):
    """Response model for a preset"""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    system_prompt: str
    summary_system_prompt: Optional[str]
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
    # Create new preset (inactive by default)
    new_preset = WritingStylePreset(
        user_id=current_user.id,
        name=preset_data.name,
        description=preset_data.description,
        system_prompt=preset_data.system_prompt,
        summary_system_prompt=preset_data.summary_system_prompt,
        is_active=False
    )
    
    db.add(new_preset)
    db.commit()
    db.refresh(new_preset)
    
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
    for field, value in update_data.items():
        setattr(preset, field, value)
    
    preset.updated_at = datetime.now()
    
    db.commit()
    db.refresh(preset)
    
    # Invalidate LLM cache if this is the active preset
    if preset.is_active:
        invalidate_user_llm_cache(current_user.id)
    
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
            invalidate_user_llm_cache(current_user.id)
    
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
    invalidate_user_llm_cache(current_user.id)
    
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
        is_active=False
    )
    
    db.add(duplicate)
    db.commit()
    db.refresh(duplicate)
    
    return duplicate


@router.get("/default/template", response_model=dict)
async def get_default_template():
    """Get the default system prompt template for new presets"""
    default_template = """You are a creative storytelling assistant. Write in an engaging narrative style that:
- Uses vivid, descriptive language to paint clear mental images
- Creates immersive scenes that draw readers into the story world
- Develops characters naturally through their actions, dialogue, and decisions
- Maintains appropriate pacing to keep the story moving forward
- Respects the genre, tone, and themes specified by the user

Keep content appropriate for general audiences unless explicitly told otherwise by the user. Write in second person ("you") for interactive stories to create an immersive experience."""
    
    return {
        "name": "New Preset",
        "description": "Customize this preset to match your preferred writing style",
        "system_prompt": default_template,
        "summary_system_prompt": None
    }

