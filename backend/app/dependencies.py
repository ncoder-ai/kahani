from fastapi import Depends, HTTPException, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .utils.security import verify_token
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current authenticated user"""
    from .models import User
    import logging
    
    logger = logging.getLogger(__name__)
    # logger.info(f"Auth attempt - Token received: {credentials.credentials[:20]}...")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = verify_token(credentials.credentials)
        # logger.info(f"Token verification result: {payload}")
        
        if payload is None:
            logger.error("Token verification failed - payload is None")
            raise credentials_exception
        
        user_id: int = payload.get("sub")
        # logger.info(f"Extracted user_id: {user_id}")
        
        if user_id is None:
            logger.error("No user_id in token payload")
            raise credentials_exception
        
        # Convert string user_id back to int
        try:
            user_id = int(user_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid user_id format: {user_id}, error: {e}")
            raise credentials_exception
            
    except Exception as e:
        logger.error(f"Exception during auth: {str(e)}")
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    # logger.info(f"User lookup result: {user}")
    
    if user is None:
        logger.error(f"No user found with id: {user_id}")
        raise credentials_exception
    
    # logger.info(f"Authentication successful for user: {user.email}")
    return user

async def get_current_user_websocket(
    websocket: WebSocket,
    token: str,
    db: Session = Depends(get_db)
):
    """Get current authenticated user for WebSocket connections"""
    from .models import User
    
    logger.info(f"WebSocket auth attempt - Token: {token[:20]}...")
    
    try:
        payload = verify_token(token)
        logger.info(f"WebSocket token verification result: {payload}")
        
        if payload is None:
            logger.error("WebSocket token verification failed")
            await websocket.close(code=1008, reason="Could not validate credentials")
            return None
        
        user_id: int = payload.get("sub")
        logger.info(f"WebSocket extracted user_id: {user_id}")
        
        if user_id is None:
            logger.error("No user_id in WebSocket token payload")
            await websocket.close(code=1008, reason="Invalid token payload")
            return None
        
        # Convert string user_id back to int
        try:
            user_id = int(user_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid user_id format: {user_id}, error: {e}")
            await websocket.close(code=1008, reason="Invalid user ID")
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        logger.info(f"WebSocket user lookup result: {user}")
        
        if user is None:
            logger.error(f"No user found with id: {user_id}")
            await websocket.close(code=1008, reason="User not found")
            return None
        
        logger.info(f"WebSocket authentication successful for user: {user.email}")
        return user
        
    except Exception as e:
        logger.error(f"Exception during WebSocket auth: {str(e)}")
        await websocket.close(code=1011, reason="Authentication error")
        return None