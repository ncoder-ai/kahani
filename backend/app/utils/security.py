from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from ..config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.
    Bcrypt limits inputs to 72 bytes; truncate to avoid backend errors while keeping UX lenient.
    """
    try:
        truncated = plain_password[:72]
        return pwd_context.verify(truncated, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Hash a password (truncate to bcrypt's 72-byte input limit)."""
    truncated = password[:72]
    return pwd_context.hash(truncated)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Verifying token: {token[:20]}...")
        logger.info(f"Using secret: {settings.jwt_secret_key[:10]}...")
        logger.info(f"Using algorithm: {settings.jwt_algorithm}")
        
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        logger.info(f"Token decoded successfully: {payload}")
        return payload
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in token verification: {str(e)}")
        return None