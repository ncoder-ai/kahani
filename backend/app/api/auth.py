from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import User, SystemSettings
from ..utils.security import verify_password, get_password_hash, create_access_token, create_refresh_token, verify_token
from ..config import settings
from ..dependencies import get_current_user
from datetime import timedelta, datetime
import logging

logger = logging.getLogger(__name__)

# Pydantic models for request bodies
class UserRegister(BaseModel):
    email: str
    username: str
    password: str
    display_name: Optional[str] = None
    
    class Config:
        # Don't include password in response representations
        extra = "forbid"

class UserLogin(BaseModel):
    email: str
    password: str
    remember_me: Optional[bool] = False
    
    class Config:
        # Don't include password in response representations  
        extra = "forbid"

router = APIRouter()

def get_system_settings(db: Session) -> SystemSettings:
    """Get system settings singleton (creates if not exists)"""
    system_settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    
    if not system_settings:
        # Create default system settings if none exist
        system_settings = SystemSettings(
            id=1,
            default_allow_nsfw=False,
            default_can_change_llm_provider=True,
            default_can_change_tts_settings=True,
            default_can_use_stt=True,
            default_can_use_image_generation=True,
            default_can_export_stories=True,
            default_can_import_stories=True,
            default_llm_temperature=0.7,
            registration_requires_approval=True,
        )
        db.add(system_settings)
        db.commit()
        db.refresh(system_settings)
        logger.info("Created default system settings")
    
    return system_settings

@router.post("/register")
async def register(
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """Register a new user"""
    
    if not settings.enable_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled"
        )
    
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
    
    # Check if this is the first user (becomes admin automatically)
    user_count = db.query(User).count()
    is_first_user = (user_count == 0)
    
    # Get system settings for default permissions
    system_settings = get_system_settings(db)
    
    # Create user with appropriate permissions
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        display_name=user_data.display_name or user_data.username,
        hashed_password=hashed_password,
        # First user becomes admin and is auto-approved
        is_admin=is_first_user,
        is_approved=is_first_user,
        approved_at=datetime.utcnow() if is_first_user else None,
        # Apply permissions based on whether this is first user (admin) or regular user
        allow_nsfw=True if is_first_user else system_settings.default_allow_nsfw,
        can_change_llm_provider=system_settings.default_can_change_llm_provider,
        can_change_tts_settings=system_settings.default_can_change_tts_settings,
        can_use_stt=system_settings.default_can_use_stt,
        can_use_image_generation=system_settings.default_can_use_image_generation,
        can_export_stories=system_settings.default_can_export_stories,
        can_import_stories=system_settings.default_can_import_stories,
        # Apply default resource limits
        max_stories=system_settings.default_max_stories,
        max_images_per_story=system_settings.default_max_images_per_story,
        max_stt_minutes_per_month=system_settings.default_max_stt_minutes_per_month,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    if is_first_user:
        logger.info(f"First user registered as admin: {user.email}")
    else:
        logger.info(f"New user registered (approval required): {user.email}")
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
            "is_approved": user.is_approved,
            # Include permissions in response
            "allow_nsfw": user.allow_nsfw,
            "can_change_llm_provider": user.can_change_llm_provider,
            "can_change_tts_settings": user.can_change_tts_settings,
            "can_use_stt": user.can_use_stt,
            "can_use_image_generation": user.can_use_image_generation,
            "can_export_stories": user.can_export_stories,
            "can_import_stories": user.can_import_stories,
        },
        "message": "Admin account created" if is_first_user else "Account created, pending admin approval"
    }

@router.post("/login")
async def login(
    request: Request,
    user_data: UserLogin,
    db: Session = Depends(get_db)
):
    """Login user"""
    
    # Log the login attempt with client details
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    origin = request.headers.get("origin", "unknown")
    referer = request.headers.get("referer", "unknown")
    
    logger.info(f"=== LOGIN ATTEMPT ===")
    logger.info(f"Email: {user_data.email}")
    logger.info(f"Client IP: {client_host}")
    logger.info(f"User-Agent: {user_agent}")
    logger.info(f"Origin: {origin}")
    logger.info(f"Referer: {referer}")
    
    try:
        # Check if user exists
        user = db.query(User).filter(User.email == user_data.email).first()
        
        if not user:
            logger.warning(f"Login failed: User not found for email {user_data.email} from {client_host}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify password
        if not verify_password(user_data.password, user.hashed_password):
            logger.warning(f"Login failed: Invalid password for {user_data.email} from {client_host}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active
        if not user.is_active:
            logger.warning(f"Login failed: Inactive user {user_data.email} from {client_host}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Create access token
        logger.info(f"Creating access token for user {user.id} ({user.email})")
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": str(user.id)}, expires_delta=access_token_expires
        )
        
        # Create refresh token if remember_me is True
        refresh_token = None
        if user_data.remember_me:
            logger.info(f"Creating refresh token for user {user.id} ({user.email})")
            refresh_token = create_refresh_token(data={"sub": str(user.id)})
        
        logger.info(f"Login successful: User {user.id} ({user.email}) from {client_host}")
        logger.info(f"Token expires in {settings.access_token_expire_minutes} minutes")
        if refresh_token:
            logger.info(f"Refresh token created, expires in {settings.refresh_token_expire_days} days")
        
        response_data = {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "is_admin": user.is_admin,
                "is_approved": user.is_approved,
                # Include all permissions in response
                "allow_nsfw": user.allow_nsfw,
                "can_change_llm_provider": user.can_change_llm_provider,
                "can_change_tts_settings": user.can_change_tts_settings,
                "can_use_stt": user.can_use_stt,
                "can_use_image_generation": user.can_use_image_generation,
                "can_export_stories": user.can_export_stories,
                "can_import_stories": user.can_import_stories,
                # Include resource limits
                "max_stories": user.max_stories,
                "max_images_per_story": user.max_images_per_story,
                "max_stt_minutes_per_month": user.max_stt_minutes_per_month,
            }
        }
        
        # Add refresh token to response if remember_me is True
        if refresh_token:
            response_data["refresh_token"] = refresh_token
        
        logger.info(f"Returning response with token length: {len(access_token)}")
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Login error for {user_data.email} from {client_host}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "is_admin": current_user.is_admin,
        "is_approved": current_user.is_approved,
        "preferences": current_user.preferences,
        # Include all permissions
        "permissions": {
            "allow_nsfw": current_user.allow_nsfw,
            "can_change_llm_provider": current_user.can_change_llm_provider,
            "can_change_tts_settings": current_user.can_change_tts_settings,
            "can_use_stt": current_user.can_use_stt,
            "can_use_image_generation": current_user.can_use_image_generation,
            "can_export_stories": current_user.can_export_stories,
            "can_import_stories": current_user.can_import_stories,
        },
        # Include resource limits
        "limits": {
            "max_stories": current_user.max_stories,
            "max_images_per_story": current_user.max_images_per_story,
            "max_stt_minutes_per_month": current_user.max_stt_minutes_per_month,
        }
    }

class RefreshTokenRequest(BaseModel):
    refresh_token: str

@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    
    try:
        # Verify refresh token
        payload = verify_token(request.refresh_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Check if it's a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        # Get user ID from token
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        # Get user from database
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new access token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": str(user.id)}, expires_delta=access_token_expires
        )
        
        logger.info(f"Token refreshed for user {user.id} ({user.email})")
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )