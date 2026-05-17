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
from datetime import timedelta, datetime, timezone
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
    identifier: str  # Can be email or username
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
        system_defaults = settings.system_defaults
        
        system_settings = SystemSettings(
            id=1,
            default_allow_nsfw=system_defaults.get('permissions', {}).get('default_allow_nsfw'),
            default_can_change_llm_provider=system_defaults.get('permissions', {}).get('default_can_change_llm_provider'),
            default_can_change_tts_settings=system_defaults.get('permissions', {}).get('default_can_change_tts_settings'),
            default_can_use_stt=system_defaults.get('permissions', {}).get('default_can_use_stt'),
            default_can_use_image_generation=system_defaults.get('permissions', {}).get('default_can_use_image_generation'),
            default_can_export_stories=system_defaults.get('permissions', {}).get('default_can_export_stories'),
            default_can_import_stories=system_defaults.get('permissions', {}).get('default_can_import_stories'),
            default_llm_temperature=system_defaults.get('llm_defaults', {}).get('default_llm_temperature'),
            registration_requires_approval=system_defaults.get('registration', {}).get('registration_requires_approval'),
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
        approved_at=datetime.now(timezone.utc) if is_first_user else None,
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
    
    # Create UserSettings with defaults from config.yaml
    from ..models.user_settings import UserSettings
    user_settings = UserSettings(user_id=user.id)
    user_settings.populate_from_defaults()
    db.add(user_settings)
    db.commit()
    logger.info(f"Created UserSettings with defaults for user {user.id}")
    
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

    logger.debug(f"Login attempt: identifier={user_data.identifier} client_ip={client_host} user_agent={user_agent} origin={origin}")

    try:
        # Check if user exists by email or username
        from sqlalchemy import or_
        user = db.query(User).filter(
            or_(
                User.email == user_data.identifier,
                User.username == user_data.identifier
            )
        ).first()

        if not user:
            logger.warning(f"Login failed: User not found for identifier {user_data.identifier} from {client_host}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email/username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify password
        if not verify_password(user_data.password, user.hashed_password):
            logger.warning(f"Login failed: Invalid password for {user_data.identifier} from {client_host}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email/username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user.is_active:
            logger.warning(f"Login failed: Inactive user {user_data.identifier} from {client_host}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Create access token
        logger.debug(f"Creating access token for user {user.id} ({user.email})")
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": str(user.id)}, expires_delta=access_token_expires
        )
        
        # Create refresh token if remember_me is True
        refresh_token = None
        if user_data.remember_me:
            logger.debug(f"Creating refresh token for user {user.id} ({user.email})")
            refresh_token = create_refresh_token(data={"sub": str(user.id)})
        
        logger.info(f"Login successful: User {user.id} ({user.email}) from {client_host}")
        logger.debug(f"Token expires in {settings.access_token_expire_minutes} minutes")
        if refresh_token:
            logger.debug(f"Refresh token created, expires in {settings.refresh_token_expire_days} days")
        
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
        
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Login error for {user_data.identifier} from {client_host}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to an internal error"
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


@router.get("/sso-check")
async def sso_check(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Check for SSO headers from reverse proxy (e.g., Authelia).
    If valid headers are present and match a Kahani user, return a JWT token.
    """
    sso_config = settings.sso_config

    # Check if SSO is enabled
    if not sso_config.get('enabled', False):
        return {"sso_enabled": False, "message": "SSO is not enabled"}

    # Check if auto_login is enabled
    if not sso_config.get('auto_login', True):
        return {"sso_enabled": True, "auto_login": False, "message": "SSO auto-login is disabled"}

    # Get header names from config
    header_username = sso_config.get('header_username', 'Remote-User')
    header_email = sso_config.get('header_email', 'Remote-Email')

    # Read headers (case-insensitive)
    remote_user = request.headers.get(header_username)
    remote_email = request.headers.get(header_email)

    client_host = request.client.host if request.client else "unknown"

    # Check trusted proxies if configured
    trusted_proxies = sso_config.get('trusted_proxies', [])
    if trusted_proxies and client_host not in trusted_proxies:
        logger.warning(f"SSO check from untrusted proxy {client_host}")
        return {"sso_enabled": True, "authenticated": False, "message": "Request not from trusted proxy"}

    if not remote_user:
        # Log all headers for debugging
        all_headers = dict(request.headers)
        logger.info(f"SSO check: No {header_username} header. Client: {client_host}. Headers: {list(all_headers.keys())}")
        return {"sso_enabled": True, "authenticated": False, "message": "No SSO headers present"}

    logger.info(f"=== SSO CHECK ===")
    logger.info(f"Remote-User: {remote_user}")
    logger.info(f"Remote-Email: {remote_email}")
    logger.info(f"Client IP: {client_host}")

    # Look up user by username
    user = db.query(User).filter(User.username == remote_user).first()

    if not user:
        logger.info(f"SSO: No Kahani user found with username '{remote_user}'")
        return {
            "sso_enabled": True,
            "authenticated": True,
            "user_exists": False,
            "message": f"No Kahani account found for username '{remote_user}'"
        }

    # Check if user is active
    if not user.is_active:
        logger.warning(f"SSO: User {remote_user} is inactive")
        return {
            "sso_enabled": True,
            "authenticated": True,
            "user_exists": True,
            "active": False,
            "message": "User account is inactive"
        }

    # Check if user is approved
    if not user.is_approved and not user.is_admin:
        logger.info(f"SSO: User {remote_user} is pending approval")
        return {
            "sso_enabled": True,
            "authenticated": True,
            "user_exists": True,
            "active": True,
            "approved": False,
            "message": "User account is pending approval"
        }

    # Generate JWT token for the user
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    logger.info(f"SSO: Auto-login successful for user {user.id} ({user.username})")

    return {
        "sso_enabled": True,
        "authenticated": True,
        "user_exists": True,
        "active": True,
        "approved": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
            "is_approved": user.is_approved,
            "allow_nsfw": user.allow_nsfw,
            "can_change_llm_provider": user.can_change_llm_provider,
            "can_change_tts_settings": user.can_change_tts_settings,
            "can_use_stt": user.can_use_stt,
            "can_use_image_generation": user.can_use_image_generation,
            "can_export_stories": user.can_export_stories,
            "can_import_stories": user.can_import_stories,
        }
    }


@router.get("/sso-status")
async def sso_status():
    """Return SSO configuration status (for frontend to know if SSO is available)"""
    sso_config = settings.sso_config
    return {
        "sso_enabled": sso_config.get('enabled', False),
        "auto_login": sso_config.get('auto_login', True),
    }