"""
Admin API endpoints for user management, permissions, and system settings.
All endpoints require admin privileges.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

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
            user.approved_at = datetime.utcnow()
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
    user.approved_at = datetime.utcnow()
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
        approved_at=datetime.utcnow() if user_data.is_approved else None,
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
    settings.updated_at = datetime.utcnow()
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

