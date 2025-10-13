from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import User
from ..utils.security import verify_password, get_password_hash, create_access_token
from ..config import settings
from ..dependencies import get_current_user
from datetime import timedelta
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
    
    class Config:
        # Don't include password in response representations  
        extra = "forbid"

router = APIRouter()

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
    
    # Create user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        username=user_data.username,
        display_name=user_data.display_name or user_data.username,
        hashed_password=hashed_password
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
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
            "display_name": user.display_name
        }
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
        
        logger.info(f"Login successful: User {user.id} ({user.email}) from {client_host}")
        logger.info(f"Token expires in {settings.access_token_expire_minutes} minutes")
        
        response_data = {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "is_admin": user.is_admin
            }
        }
        
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
        "preferences": current_user.preferences
    }