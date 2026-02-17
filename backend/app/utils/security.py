from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
import bcrypt as bcrypt_lib
from ..config import settings

logger = logging.getLogger(__name__)

# Password hashing - use pbkdf2_sha256 for new passwords
# We handle bcrypt legacy passwords manually due to passlib/bcrypt version incompatibility
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.
    Supports both pbkdf2_sha256 (new) and bcrypt (legacy) hashes.
    """
    try:
        truncated = plain_password[:72]
        
        # Check if it's a bcrypt hash (starts with $2a$, $2b$, or $2y$)
        if hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
            # Use bcrypt library directly for bcrypt hashes
            return bcrypt_lib.checkpw(truncated.encode('utf-8'), hashed_password.encode('utf-8'))
        else:
            # Use passlib for pbkdf2_sha256 hashes
            return pwd_context.verify(truncated, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Hash a password using pbkdf2_sha256 (truncate to 72 bytes for compatibility)."""
    truncated = password[:72]
    return pwd_context.hash(truncated)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with longer expiration"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # logger.info(f"Verifying token: {token[:20]}...")
        # logger.info(f"Using secret: {settings.jwt_secret_key[:10]}...")
        # logger.info(f"Using algorithm: {settings.jwt_algorithm}")
        
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        # logger.info(f"Token decoded successfully: {payload}")
        return payload
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in token verification: {str(e)}")
        return None