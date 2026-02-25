"""
Admin API endpoints for user management, permissions, and system settings.
All endpoints require admin privileges.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import asyncio
import uuid

from ..database import get_db
from ..models import User, SystemSettings, Story, Scene
from ..dependencies import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin privileges"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def get_system_settings(db: Session) -> SystemSettings:
    """Get system settings singleton"""
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if not settings:
        # Create default if not exists
        settings = SystemSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


# ============================================================
# PYDANTIC MODELS
# ============================================================

class UserPermissionsUpdate(BaseModel):
    """Model for updating user permissions"""
    allow_nsfw: Optional[bool] = None
    can_change_llm_provider: Optional[bool] = None
    can_change_tts_settings: Optional[bool] = None
    can_use_stt: Optional[bool] = None
    can_use_image_generation: Optional[bool] = None
    can_export_stories: Optional[bool] = None
    can_import_stories: Optional[bool] = None
    max_stories: Optional[int] = None
    max_images_per_story: Optional[int] = None
    max_stt_minutes_per_month: Optional[int] = None


class UserUpdate(BaseModel):
    """Model for updating user details and permissions
    
    Accepts both flat and nested structure for backwards compatibility:
    - Flat: { is_admin: true, allow_nsfw: true, ... }
    - Nested: { is_admin: true, permissions: { allow_nsfw: true, ... } }
    """
    # Core fields
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    is_approved: Optional[bool] = None
    
    # Nested permissions (preferred)
    permissions: Optional[UserPermissionsUpdate] = None
    
    # Flat permission fields (for backwards compatibility)
    allow_nsfw: Optional[bool] = None
    can_change_llm_provider: Optional[bool] = None
    can_change_tts_settings: Optional[bool] = None
    can_use_stt: Optional[bool] = None
    can_use_image_generation: Optional[bool] = None
    can_export_stories: Optional[bool] = None
    can_import_stories: Optional[bool] = None
    max_stories: Optional[int] = None
    max_images_per_story: Optional[int] = None
    max_stt_minutes_per_month: Optional[int] = None


class UserCreate(BaseModel):
    """Model for admin creating a new user"""
    email: str
    username: str
    password: str
    display_name: Optional[str] = None
    is_admin: bool = False
    is_approved: bool = True  # Admin-created users are pre-approved
    permissions: Optional[UserPermissionsUpdate] = None


class SystemSettingsUpdate(BaseModel):
    """Model for updating system settings"""
    # Default permissions
    default_allow_nsfw: Optional[bool] = None
    default_can_change_llm_provider: Optional[bool] = None
    default_can_change_tts_settings: Optional[bool] = None
    default_can_use_stt: Optional[bool] = None
    default_can_use_image_generation: Optional[bool] = None
    default_can_export_stories: Optional[bool] = None
    default_can_import_stories: Optional[bool] = None
    
    # Default limits
    default_max_stories: Optional[int] = None
    default_max_images_per_story: Optional[int] = None
    default_max_stt_minutes_per_month: Optional[int] = None
    
    # Default LLM settings
    default_llm_api_url: Optional[str] = None
    default_llm_api_key: Optional[str] = None
    default_llm_model_name: Optional[str] = None
    default_llm_temperature: Optional[float] = None
    
    # Registration settings
    registration_requires_approval: Optional[bool] = None


# ============================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================

@router.get("/users")
async def list_users(
    status_filter: Optional[str] = Query(None, description="Filter by status: all, approved, pending, admins"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all users with filtering options.
    Requires admin privileges.
    """
    query = db.query(User)
    
    # Apply status filter
    if status_filter == "approved":
        query = query.filter(User.is_approved == True)
    elif status_filter == "pending":
        query = query.filter(User.is_approved == False)
    elif status_filter == "admins":
        query = query.filter(User.is_admin == True)
    # "all" or None returns all users
    
    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.username.like(search_pattern),
                User.email.like(search_pattern),
                User.display_name.like(search_pattern)
            )
        )
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "display_name": user.display_name,
                "is_admin": user.is_admin,
                "is_active": user.is_active,
                "is_approved": user.is_approved,
                "approved_at": user.approved_at.isoformat() if user.approved_at else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                # Flat permission fields for easy frontend access
                "allow_nsfw": user.allow_nsfw,
                "can_change_llm_provider": user.can_change_llm_provider,
                "can_change_tts_settings": user.can_change_tts_settings,
                "can_use_stt": user.can_use_stt,
                "can_use_image_generation": user.can_use_image_generation,
                "can_export_stories": user.can_export_stories,
                "can_import_stories": user.can_import_stories,
                "max_stories": user.max_stories,
                "max_images_per_story": user.max_images_per_story,
                "max_stt_minutes_per_month": user.max_stt_minutes_per_month,
            }
            for user in users
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific user.
    Requires admin privileges.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get user statistics
    story_count = db.query(Story).filter(Story.owner_id == user_id).count()
    
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "is_approved": user.is_approved,
        "approved_at": user.approved_at.isoformat() if user.approved_at else None,
        "approved_by_id": user.approved_by_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "permissions": {
            "allow_nsfw": user.allow_nsfw,
            "can_change_llm_provider": user.can_change_llm_provider,
            "can_change_tts_settings": user.can_change_tts_settings,
            "can_use_stt": user.can_use_stt,
            "can_use_image_generation": user.can_use_image_generation,
            "can_export_stories": user.can_export_stories,
            "can_import_stories": user.can_import_stories,
        },
        "limits": {
            "max_stories": user.max_stories,
            "max_images_per_story": user.max_images_per_story,
            "max_stt_minutes_per_month": user.max_stt_minutes_per_month,
        },
        "statistics": {
            "story_count": story_count,
        }
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    updates: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update user details and permissions.
    Requires admin privileges.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent admin from modifying themselves in dangerous ways
    if user.id == current_user.id:
        if updates.is_admin is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove admin privileges from yourself"
            )
        if updates.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate yourself"
            )
    
    # Check if trying to demote the last admin
    if updates.is_admin is False and user.is_admin:
        admin_count = db.query(User).filter(User.is_admin == True).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last admin. Promote another user first."
            )
    
    # Update basic fields
    if updates.is_admin is not None:
        user.is_admin = updates.is_admin
        logger.info(f"Admin {current_user.id} set user {user_id} admin status to {updates.is_admin}")
    
    if updates.is_active is not None:
        user.is_active = updates.is_active
        logger.info(f"Admin {current_user.id} set user {user_id} active status to {updates.is_active}")
    
    if updates.is_approved is not None:
        user.is_approved = updates.is_approved
        if updates.is_approved:
            user.approved_at = datetime.now(timezone.utc)
            user.approved_by_id = current_user.id
        logger.info(f"Admin {current_user.id} set user {user_id} approval status to {updates.is_approved}")
    
    # Update permissions - support both nested and flat structure
    # Priority: nested permissions > flat fields
    perms_to_apply = updates.permissions if updates.permissions else updates
    
    # Get dict of fields that were actually sent in the request
    # Using model_dump with exclude_unset to only get fields that were explicitly set
    update_dict = updates.model_dump(exclude_unset=True)
    if updates.permissions:
        perm_dict = updates.permissions.model_dump(exclude_unset=True)
    else:
        perm_dict = update_dict
    
    # Update permissions (only if field was explicitly sent)
    if 'allow_nsfw' in perm_dict:
        user.allow_nsfw = perms_to_apply.allow_nsfw
    if 'can_change_llm_provider' in perm_dict:
        user.can_change_llm_provider = perms_to_apply.can_change_llm_provider
    if 'can_change_tts_settings' in perm_dict:
        user.can_change_tts_settings = perms_to_apply.can_change_tts_settings
    if 'can_use_stt' in perm_dict:
        user.can_use_stt = perms_to_apply.can_use_stt
    if 'can_use_image_generation' in perm_dict:
        user.can_use_image_generation = perms_to_apply.can_use_image_generation
    if 'can_export_stories' in perm_dict:
        user.can_export_stories = perms_to_apply.can_export_stories
    if 'can_import_stories' in perm_dict:
        user.can_import_stories = perms_to_apply.can_import_stories
    
    # Update limits (allow null to set unlimited)
    if 'max_stories' in perm_dict:
        user.max_stories = perms_to_apply.max_stories  # Can be None for unlimited
    if 'max_images_per_story' in perm_dict:
        user.max_images_per_story = perms_to_apply.max_images_per_story  # Can be None
    if 'max_stt_minutes_per_month' in perm_dict:
        user.max_stt_minutes_per_month = perms_to_apply.max_stt_minutes_per_month  # Can be None
    
    logger.info(f"Admin {current_user.id} updated user {user_id}")
    
    # Clear LLM cache if permissions were changed
    if 'allow_nsfw' in perm_dict or 'can_change_llm_provider' in perm_dict:
        from ..services.llm.service import UnifiedLLMService
        llm_service = UnifiedLLMService()
        llm_service.invalidate_user_client(user_id)
        logger.info(f"Invalidated LLM client cache for user {user_id} due to permission changes")
    
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User updated successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "is_approved": user.is_approved
        }
    }


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Approve a pending user.
    Requires admin privileges.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_approved:
        return {
            "message": "User is already approved",
            "user_id": user.id
        }
    
    user.is_approved = True
    user.approved_at = datetime.now(timezone.utc)
    user.approved_by_id = current_user.id
    
    db.commit()
    db.refresh(user)
    
    logger.info(f"Admin {current_user.id} approved user {user_id}")
    
    return {
        "message": "User approved successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_approved": user.is_approved,
            "approved_at": user.approved_at.isoformat()
        }
    }


@router.post("/users/{user_id}/revoke")
async def revoke_approval(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Revoke approval for a user (mark as unapproved).
    Requires admin privileges.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Cannot revoke approval from admins
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke approval from admin users"
        )
    
    # Cannot revoke yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke approval from yourself"
        )
    
    user.is_approved = False
    user.approved_at = None
    user.approved_by_id = None
    
    db.commit()
    db.refresh(user)
    
    logger.info(f"Admin {current_user.id} revoked approval for user {user_id}")
    
    return {
        "message": "User approval revoked successfully",
        "user_id": user.id
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a user permanently.
    Requires admin privileges.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Cannot delete yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )
    
    # Check if trying to delete the last admin
    if user.is_admin:
        admin_count = db.query(User).filter(User.is_admin == True).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last admin"
            )
    
    username = user.username
    db.delete(user)
    db.commit()
    
    logger.info(f"Admin {current_user.id} deleted user {user_id} ({username})")
    
    return {
        "message": f"User '{username}' deleted successfully",
        "user_id": user_id
    }


@router.post("/users")
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new user (admin action).
    Requires admin privileges.
    """
    from ..utils.security import get_password_hash
    
    # Check if user already exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Get system settings for defaults
    system_settings = get_system_settings(db)
    
    # Create user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        display_name=user_data.display_name or user_data.username,
        hashed_password=hashed_password,
        is_admin=user_data.is_admin,
        is_approved=user_data.is_approved,
        approved_at=datetime.now(timezone.utc) if user_data.is_approved else None,
        approved_by_id=current_user.id if user_data.is_approved else None,
    )
    
    # Apply permissions
    if user_data.permissions:
        perms = user_data.permissions
        user.allow_nsfw = perms.allow_nsfw if perms.allow_nsfw is not None else system_settings.default_allow_nsfw
        user.can_change_llm_provider = perms.can_change_llm_provider if perms.can_change_llm_provider is not None else system_settings.default_can_change_llm_provider
        user.can_change_tts_settings = perms.can_change_tts_settings if perms.can_change_tts_settings is not None else system_settings.default_can_change_tts_settings
        user.can_use_stt = perms.can_use_stt if perms.can_use_stt is not None else system_settings.default_can_use_stt
        user.can_use_image_generation = perms.can_use_image_generation if perms.can_use_image_generation is not None else system_settings.default_can_use_image_generation
        user.can_export_stories = perms.can_export_stories if perms.can_export_stories is not None else system_settings.default_can_export_stories
        user.can_import_stories = perms.can_import_stories if perms.can_import_stories is not None else system_settings.default_can_import_stories
        user.max_stories = perms.max_stories
        user.max_images_per_story = perms.max_images_per_story
        user.max_stt_minutes_per_month = perms.max_stt_minutes_per_month
    else:
        # Apply defaults from system settings
        user.allow_nsfw = system_settings.default_allow_nsfw
        user.can_change_llm_provider = system_settings.default_can_change_llm_provider
        user.can_change_tts_settings = system_settings.default_can_change_tts_settings
        user.can_use_stt = system_settings.default_can_use_stt
        user.can_use_image_generation = system_settings.default_can_use_image_generation
        user.can_export_stories = system_settings.default_can_export_stories
        user.can_import_stories = system_settings.default_can_import_stories
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create UserSettings with defaults from config.yaml
    from ..models.user_settings import UserSettings
    user_settings = UserSettings(user_id=user.id)
    user_settings.populate_from_defaults()
    db.add(user_settings)
    db.commit()
    logger.info(f"Created UserSettings with defaults for user {user.id}")
    
    logger.info(f"Admin {current_user.id} created new user {user.id} ({user.username})")
    
    return {
        "message": "User created successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_approved": user.is_approved
        }
    }


# ============================================================
# SYSTEM SETTINGS ENDPOINTS
# ============================================================

@router.get("/settings")
async def get_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get system-wide settings.
    Requires admin privileges.
    """
    settings = get_system_settings(db)
    
    # Return flat settings object for frontend compatibility
    return {
        "settings": {
            "default_allow_nsfw": settings.default_allow_nsfw,
            "default_can_change_llm_provider": settings.default_can_change_llm_provider,
            "default_can_change_tts_settings": settings.default_can_change_tts_settings,
            "default_can_use_stt": settings.default_can_use_stt,
            "default_can_use_image_generation": settings.default_can_use_image_generation,
            "default_can_export_stories": settings.default_can_export_stories,
            "default_can_import_stories": settings.default_can_import_stories,
            "default_max_stories": settings.default_max_stories,
            "default_max_images_per_story": settings.default_max_images_per_story,
            "default_max_stt_minutes_per_month": settings.default_max_stt_minutes_per_month,
            "default_llm_api_url": settings.default_llm_api_url,
            "default_llm_api_key": settings.default_llm_api_key,
            "default_llm_model_name": settings.default_llm_model_name,
            "default_llm_temperature": settings.default_llm_temperature,
            "registration_requires_approval": settings.registration_requires_approval,
        }
    }


@router.put("/settings")
async def update_settings(
    updates: SystemSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update system-wide settings.
    Requires admin privileges.
    """
    settings = get_system_settings(db)
    
    # Update default permissions
    if updates.default_allow_nsfw is not None:
        settings.default_allow_nsfw = updates.default_allow_nsfw
    if updates.default_can_change_llm_provider is not None:
        settings.default_can_change_llm_provider = updates.default_can_change_llm_provider
    if updates.default_can_change_tts_settings is not None:
        settings.default_can_change_tts_settings = updates.default_can_change_tts_settings
    if updates.default_can_use_stt is not None:
        settings.default_can_use_stt = updates.default_can_use_stt
    if updates.default_can_use_image_generation is not None:
        settings.default_can_use_image_generation = updates.default_can_use_image_generation
    if updates.default_can_export_stories is not None:
        settings.default_can_export_stories = updates.default_can_export_stories
    if updates.default_can_import_stories is not None:
        settings.default_can_import_stories = updates.default_can_import_stories
    
    # Update default limits
    if updates.default_max_stories is not None:
        settings.default_max_stories = updates.default_max_stories
    if updates.default_max_images_per_story is not None:
        settings.default_max_images_per_story = updates.default_max_images_per_story
    if updates.default_max_stt_minutes_per_month is not None:
        settings.default_max_stt_minutes_per_month = updates.default_max_stt_minutes_per_month
    
    # Update default LLM settings
    if updates.default_llm_api_url is not None:
        settings.default_llm_api_url = updates.default_llm_api_url
    if updates.default_llm_api_key is not None:
        settings.default_llm_api_key = updates.default_llm_api_key
    if updates.default_llm_model_name is not None:
        settings.default_llm_model_name = updates.default_llm_model_name
    if updates.default_llm_temperature is not None:
        settings.default_llm_temperature = updates.default_llm_temperature
    
    # Update registration settings
    if updates.registration_requires_approval is not None:
        settings.registration_requires_approval = updates.registration_requires_approval
    
    # Update metadata
    settings.updated_at = datetime.now(timezone.utc)
    settings.updated_by_id = current_user.id
    
    db.commit()
    db.refresh(settings)
    
    logger.info(f"Admin {current_user.id} updated system settings")
    
    return {
        "message": "System settings updated successfully",
        "updated_at": settings.updated_at.isoformat()
    }


# ============================================================
# STATISTICS ENDPOINTS
# ============================================================

@router.post("/stories/{story_id}/reprocess-extractions")
async def reprocess_story_extractions(
    story_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Trigger retroactive NPC and entity extraction for all scenes in a story.
    This resets extraction counters and processes all chapters.
    Requires admin privileges.
    """
    from ..models import Chapter, UserSettings
    
    # Verify story exists
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get all chapters for the story
    chapters = db.query(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.chapter_number).all()
    if not chapters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Story has no chapters"
        )
    
    # Reset last_extraction_scene_count to 0 for all chapters to force reprocessing
    chapters_reset = 0
    for chapter in chapters:
        if chapter.last_extraction_scene_count and chapter.last_extraction_scene_count > 0:
            chapter.last_extraction_scene_count = 0
            chapters_reset += 1
    
    db.commit()
    
    # Get user settings for extraction
    user_settings_obj = db.query(UserSettings).filter(
        UserSettings.user_id == story.owner_id
    ).first()
    
    user_settings = {}
    if user_settings_obj:
        user_settings = user_settings_obj.to_dict()
    
    # Schedule background extraction for each chapter
    trace_id = f"reprocess-{uuid.uuid4()}"
    
    async def run_extractions():
        """Run extractions for all chapters in sequence"""
        from ..database import SessionLocal
        from ..services.semantic_integration import batch_process_scene_extractions
        from ..models import Scene
        from sqlalchemy import func
        
        extraction_db = SessionLocal()
        try:
            for chapter in chapters:
                # Get scene range for this chapter
                scene_stats = extraction_db.query(
                    func.min(Scene.sequence_number).label('min_seq'),
                    func.max(Scene.sequence_number).label('max_seq')
                ).filter(
                    Scene.story_id == story_id,
                    Scene.chapter_id == chapter.id,
                    Scene.is_deleted == False
                ).first()
                
                if not scene_stats or not scene_stats.max_seq:
                    logger.info(f"[REPROCESS] trace_id={trace_id} chapter_id={chapter.id} skipped (no scenes)")
                    continue
                
                from_seq = scene_stats.min_seq - 1  # Exclusive start
                to_seq = scene_stats.max_seq
                
                logger.info(f"[REPROCESS] trace_id={trace_id} chapter_id={chapter.id} processing scenes {from_seq+1} to {to_seq}")
                
                try:
                    results = await batch_process_scene_extractions(
                        story_id=story_id,
                        chapter_id=chapter.id,
                        from_sequence=from_seq,
                        to_sequence=to_seq,
                        user_id=story.owner_id,
                        user_settings=user_settings,
                        db=extraction_db
                    )
                    
                    # Update extraction counter
                    chapter_obj = extraction_db.query(Chapter).filter(Chapter.id == chapter.id).first()
                    if chapter_obj:
                        chapter_obj.last_extraction_scene_count = to_seq
                        extraction_db.commit()
                    
                    logger.info(f"[REPROCESS] trace_id={trace_id} chapter_id={chapter.id} complete: {results}")
                except Exception as e:
                    logger.error(f"[REPROCESS] trace_id={trace_id} chapter_id={chapter.id} failed: {e}")
                    import traceback
                    logger.error(f"[REPROCESS] Traceback: {traceback.format_exc()}")
        finally:
            extraction_db.close()
    
    background_tasks.add_task(run_extractions)
    
    logger.info(f"[REPROCESS] trace_id={trace_id} story_id={story_id} scheduled by admin {current_user.id}, {chapters_reset} chapters reset")
    
    return {
        "message": f"Extraction reprocessing scheduled for story {story_id}",
        "trace_id": trace_id,
        "chapters_to_process": len(chapters),
        "chapters_reset": chapters_reset
    }


@router.get("/stats")
async def get_statistics(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get system statistics for admin dashboard.
    Requires admin privileges.
    """
    # User statistics
    total_users = db.query(User).count()
    approved_users = db.query(User).filter(User.is_approved == True).count()
    pending_users = db.query(User).filter(User.is_approved == False).count()
    admin_users = db.query(User).filter(User.is_admin == True).count()
    
    # Permission statistics
    nsfw_enabled_users = db.query(User).filter(User.allow_nsfw == True).count()
    users_with_llm_access = db.query(User).filter(User.can_change_llm_provider == True).count()
    users_with_tts_access = db.query(User).filter(User.can_change_tts_settings == True).count()
    
    # Content statistics
    from ..models.story import StoryStatus
    total_stories = db.query(Story).count()
    active_stories = db.query(Story).filter(Story.status == StoryStatus.ACTIVE).count()
    draft_stories = db.query(Story).filter(Story.status == StoryStatus.DRAFT).count()
    archived_stories = db.query(Story).filter(Story.status == StoryStatus.ARCHIVED).count()
    
    # Return flat structure for frontend compatibility
    return {
        "total_users": total_users,
        "approved_users": approved_users,
        "pending_users": pending_users,
        "admin_users": admin_users,
        "total_stories": total_stories,
        "active_stories": active_stories,
        "draft_stories": draft_stories,
        "archived_stories": archived_stories,
        "nsfw_enabled_users": nsfw_enabled_users,
        "users_with_llm_access": users_with_llm_access,
        "users_with_tts_access": users_with_tts_access,
    }


# ============================================================
# EMBEDDING MANAGEMENT ENDPOINTS
# ============================================================

@router.get("/embeddings/status")
async def get_embedding_status(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get embedding status and compatibility info.
    Checks if existing embeddings are compatible with current model dimension.
    """
    try:
        from ..services.semantic_memory import get_semantic_memory_service
        semantic_memory = get_semantic_memory_service()

        compatibility = await semantic_memory.check_embedding_dimension_compatibility()
        stats = await semantic_memory.get_collection_stats()

        return {
            "compatibility": compatibility,
            "collection_stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting embedding status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting embedding status"
        )


@router.post("/embeddings/reembed-story/{story_id}")
async def reembed_story(
    story_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Re-embed all scenes for a specific story.
    Clears existing embeddings and regenerates them with the current model.
    """
    # Verify story exists
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story {story_id} not found"
        )

    trace_id = str(uuid.uuid4())[:8]
    # Capture user_id for background task
    reembed_user_id = current_user.id
    logger.info(f"[REEMBED] trace_id={trace_id} Starting re-embed for story {story_id}")

    def run_reembed():
        """Sync wrapper for background task - uses asyncio.run() internally"""
        import asyncio

        async def _do_reembed():
            from ..database import SessionLocal
            from ..services.semantic_memory import get_semantic_memory_service
            from ..services.llm.service import UnifiedLLMService
            from ..models import Scene, UserSettings
            from ..models.semantic_memory import SceneEmbedding
            import hashlib

            reembed_db = SessionLocal()
            try:
                semantic_memory = get_semantic_memory_service()
                llm_service = UnifiedLLMService()

                # Get user settings for LLM summary calls
                user_settings_db = reembed_db.query(UserSettings).filter(
                    UserSettings.user_id == reembed_user_id
                ).first()
                user_settings = user_settings_db.to_dict() if user_settings_db else {}

                # Clear existing embedding vectors (keeps rows, sets embedding=NULL)
                deleted_count = await semantic_memory.clear_story_embeddings(story_id)
                logger.info(f"[REEMBED] trace_id={trace_id} Cleared {deleted_count} existing embeddings")

                # Get all scenes for this story
                scenes = reembed_db.query(Scene).filter(
                    Scene.story_id == story_id,
                    Scene.is_deleted == False
                ).order_by(Scene.sequence_number).all()

                logger.info(f"[REEMBED] trace_id={trace_id} Found {len(scenes)} scenes to re-embed (with LLM summaries)")

                success_count = 0
                summary_count = 0
                error_count = 0

                for scene in scenes:
                    try:
                        # Get content from the first variant
                        content = ""
                        if scene.variants:
                            content = scene.variants[0].content or ""
                        if not content.strip():
                            logger.warning(f"[REEMBED] trace_id={trace_id} Scene {scene.id} has no content, skipping")
                            continue

                        variant_id = scene.variants[0].id if scene.variants else 0

                        # Step 1: Generate LLM summary (matches normal pipeline)
                        embed_content = content[:1000]  # fallback: truncated raw content
                        try:
                            summary_result = await llm_service.generate_scene_summary_cache_friendly(
                                scene_content=content,
                                context={},
                                user_id=reembed_user_id,
                                user_settings=user_settings,
                                db=reembed_db
                            )
                            if summary_result and summary_result.get("summary"):
                                embed_content = summary_result["summary"]
                                summary_count += 1
                            else:
                                logger.warning(f"[REEMBED] trace_id={trace_id} Scene {scene.id}: summary returned None, using truncated content")
                        except Exception as e:
                            logger.warning(f"[REEMBED] trace_id={trace_id} Scene {scene.id}: summary failed ({e}), using truncated content")

                        # Step 2: Generate embedding from summary
                        embedding_id, embedding_vector = await semantic_memory.add_scene_embedding(
                            scene_id=scene.id,
                            variant_id=variant_id,
                            story_id=story_id,
                            content=embed_content,
                            metadata={
                                "sequence": scene.sequence_number,
                                "chapter_id": scene.chapter_id or 0,
                                "branch_id": scene.branch_id or 0,
                                "timestamp": scene.created_at.isoformat() if scene.created_at else None,
                                "characters": []
                            }
                        )

                        # Step 3: Store embedding vector in database
                        content_hash = hashlib.sha256(embed_content.encode('utf-8')).hexdigest()
                        existing = reembed_db.query(SceneEmbedding).filter(
                            SceneEmbedding.embedding_id == embedding_id
                        ).first()
                        if existing:
                            existing.embedding = embedding_vector
                            existing.embedding_text = embed_content
                            existing.content_hash = content_hash
                            existing.content_length = len(embed_content)
                        else:
                            new_embedding = SceneEmbedding(
                                embedding_id=embedding_id,
                                story_id=story_id,
                                branch_id=scene.branch_id,
                                scene_id=scene.id,
                                variant_id=variant_id,
                                sequence_order=scene.sequence_number,
                                chapter_id=scene.chapter_id,
                                content_length=len(embed_content),
                                content_hash=content_hash,
                                embedding=embedding_vector,
                                embedding_text=embed_content,
                            )
                            reembed_db.add(new_embedding)

                        success_count += 1

                        # Commit in batches of 10
                        if success_count % 10 == 0:
                            reembed_db.commit()
                            logger.info(f"[REEMBED] trace_id={trace_id} Progress: {success_count}/{len(scenes)} ({summary_count} with LLM summaries)")

                    except Exception as e:
                        logger.error(f"[REEMBED] trace_id={trace_id} Failed to embed scene {scene.id}: {e}")
                        error_count += 1

                # Final commit
                reembed_db.commit()

                logger.info(f"[REEMBED] trace_id={trace_id} Complete: {success_count} success ({summary_count} with LLM summaries), {error_count} errors")

            except Exception as e:
                logger.error(f"[REEMBED] trace_id={trace_id} Failed: {e}")
                import traceback
                logger.error(f"[REEMBED] Traceback: {traceback.format_exc()}")
            finally:
                reembed_db.close()

        # Run the async function in a new event loop
        asyncio.run(_do_reembed())

    background_tasks.add_task(run_reembed)

    # Get scene count for response
    scene_count = db.query(Scene).filter(
        Scene.story_id == story_id,
        Scene.is_deleted == False
    ).count()

    return {
        "message": f"Re-embedding scheduled for story {story_id}",
        "trace_id": trace_id,
        "story_id": story_id,
        "scenes_to_process": scene_count
    }


@router.post("/embeddings/clear-all")
async def clear_all_embeddings(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Clear ALL scene embeddings and recreate the collection.
    Use this when upgrading embedding models with different dimensions.
    WARNING: This clears all embeddings. Use reembed-all to regenerate them.
    """
    try:
        from ..services.semantic_memory import get_semantic_memory_service
        semantic_memory = get_semantic_memory_service()

        deleted_count = await semantic_memory.clear_all_scene_embeddings()

        return {
            "message": "All scene embeddings cleared",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Error clearing embeddings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error clearing embeddings"
        )


@router.post("/embeddings/reembed-all")
async def reembed_all_stories(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Re-embed ALL scenes across all stories.
    Clears existing embeddings and regenerates them with the current model.
    Use this after upgrading the embedding model.
    """
    trace_id = str(uuid.uuid4())[:8]

    # Get all story IDs
    story_ids = [s.id for s in db.query(Story.id).all()]
    total_scenes = db.query(Scene).filter(Scene.is_deleted == False).count()

    reembed_user_id = current_user.id
    logger.info(f"[REEMBED-ALL] trace_id={trace_id} Starting re-embed for {len(story_ids)} stories, {total_scenes} scenes")

    def run_reembed_all():
        """Sync wrapper for background task - uses asyncio.run() internally"""
        import asyncio

        async def _do_reembed_all():
            from ..database import SessionLocal
            from ..services.semantic_memory import get_semantic_memory_service
            from ..services.llm.service import UnifiedLLMService
            from ..models import Scene, UserSettings
            from ..models.semantic_memory import SceneEmbedding
            import hashlib

            reembed_db = SessionLocal()
            try:
                semantic_memory = get_semantic_memory_service()
                llm_service = UnifiedLLMService()

                # Get user settings for LLM summary calls
                user_settings_db = reembed_db.query(UserSettings).filter(
                    UserSettings.user_id == reembed_user_id
                ).first()
                user_settings = user_settings_db.to_dict() if user_settings_db else {}

                # Clear all embeddings first
                await semantic_memory.clear_all_scene_embeddings()
                logger.info(f"[REEMBED-ALL] trace_id={trace_id} Cleared all existing embeddings")

                # Get all active scenes
                scenes = reembed_db.query(Scene).filter(
                    Scene.is_deleted == False
                ).order_by(Scene.story_id, Scene.sequence_number).all()

                logger.info(f"[REEMBED-ALL] trace_id={trace_id} Found {len(scenes)} scenes to re-embed (with LLM summaries)")

                success_count = 0
                summary_count = 0
                error_count = 0

                for i, scene in enumerate(scenes):
                    try:
                        # Get content from the first variant
                        content = ""
                        if scene.variants:
                            content = scene.variants[0].content or ""
                        if not content.strip():
                            continue

                        variant_id = scene.variants[0].id if scene.variants else 0

                        # Step 1: Generate LLM summary (matches normal pipeline)
                        embed_content = content[:1000]  # fallback: truncated raw content
                        try:
                            summary_result = await llm_service.generate_scene_summary_cache_friendly(
                                scene_content=content,
                                context={},
                                user_id=reembed_user_id,
                                user_settings=user_settings,
                                db=reembed_db
                            )
                            if summary_result and summary_result.get("summary"):
                                embed_content = summary_result["summary"]
                                summary_count += 1
                        except Exception as e:
                            logger.warning(f"[REEMBED-ALL] trace_id={trace_id} Scene {scene.id}: summary failed ({e}), using truncated content")

                        # Step 2: Generate embedding from summary
                        embedding_id, embedding_vector = await semantic_memory.add_scene_embedding(
                            scene_id=scene.id,
                            variant_id=variant_id,
                            story_id=scene.story_id,
                            content=embed_content,
                            metadata={
                                "sequence": scene.sequence_number,
                                "chapter_id": scene.chapter_id or 0,
                                "branch_id": scene.branch_id or 0,
                                "timestamp": scene.created_at.isoformat() if scene.created_at else None,
                                "characters": []
                            }
                        )

                        # Step 3: Store embedding vector in database
                        content_hash = hashlib.sha256(embed_content.encode('utf-8')).hexdigest()
                        existing = reembed_db.query(SceneEmbedding).filter(
                            SceneEmbedding.embedding_id == embedding_id
                        ).first()
                        if existing:
                            existing.embedding = embedding_vector
                            existing.embedding_text = embed_content
                            existing.content_hash = content_hash
                            existing.content_length = len(embed_content)
                        else:
                            new_embedding = SceneEmbedding(
                                embedding_id=embedding_id,
                                story_id=scene.story_id,
                                branch_id=scene.branch_id,
                                scene_id=scene.id,
                                variant_id=variant_id,
                                sequence_order=scene.sequence_number,
                                chapter_id=scene.chapter_id,
                                content_length=len(embed_content),
                                content_hash=content_hash,
                                embedding=embedding_vector,
                                embedding_text=embed_content,
                            )
                            reembed_db.add(new_embedding)

                        success_count += 1

                        # Commit in batches of 10
                        if (i + 1) % 10 == 0:
                            reembed_db.commit()
                            logger.info(f"[REEMBED-ALL] trace_id={trace_id} Progress: {i + 1}/{len(scenes)} ({summary_count} with LLM summaries)")

                    except Exception as e:
                        logger.error(f"[REEMBED-ALL] trace_id={trace_id} Failed to embed scene {scene.id}: {e}")
                        error_count += 1

                # Final commit
                reembed_db.commit()
                logger.info(f"[REEMBED-ALL] trace_id={trace_id} Complete: {success_count} success ({summary_count} with LLM summaries), {error_count} errors")

            except Exception as e:
                logger.error(f"[REEMBED-ALL] trace_id={trace_id} Failed: {e}")
                import traceback
                logger.error(f"[REEMBED-ALL] Traceback: {traceback.format_exc()}")
            finally:
                reembed_db.close()

        # Run the async function in a new event loop
        asyncio.run(_do_reembed_all())

    background_tasks.add_task(run_reembed_all)

    return {
        "message": f"Re-embedding scheduled for all stories",
        "trace_id": trace_id,
        "stories_to_process": len(story_ids),
        "scenes_to_process": total_scenes
    }


@router.post("/embeddings/backfill-event-embeddings")
async def backfill_event_embeddings(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Backfill embeddings for scene_events rows that have NULL embedding.
    One-time operation — new events get embedded at extraction time.
    Runs in background; ~100 events/second with local embedding model.
    """
    from ..models.scene_event import SceneEvent

    total = db.query(func.count(SceneEvent.id)).filter(
        SceneEvent.embedding.is_(None)
    ).scalar()

    if total == 0:
        return {"message": "All scene events already have embeddings", "total": 0}

    def run_backfill():
        async def _do_backfill():
            from ..database import SessionLocal
            from ..services.semantic_memory import get_semantic_memory_service

            semantic_memory = get_semantic_memory_service()
            backfill_db = SessionLocal()
            batch_size = 100
            processed = 0
            errors = 0

            try:
                while True:
                    events = (
                        backfill_db.query(SceneEvent)
                        .filter(SceneEvent.embedding.is_(None))
                        .order_by(SceneEvent.id)
                        .limit(batch_size)
                        .all()
                    )
                    if not events:
                        break

                    texts = [e.event_text for e in events]
                    try:
                        embeddings = await semantic_memory.encode_texts(texts)
                        for event, emb in zip(events, embeddings):
                            event.embedding = emb.tolist()
                        backfill_db.commit()
                        processed += len(events)
                    except Exception as e:
                        logger.error(f"[BACKFILL] Batch failed: {e}")
                        backfill_db.rollback()
                        errors += len(events)

                logger.info(f"[BACKFILL] Event embeddings complete: {processed} processed, {errors} errors")
            finally:
                backfill_db.close()

        asyncio.run(_do_backfill())

    background_tasks.add_task(run_backfill)

    return {
        "message": f"Backfilling {total} event embeddings in background",
        "total": total,
    }

