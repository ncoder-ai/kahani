"""
Middleware to extract and set current user in request.state
This runs before the approval check middleware
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts the auth token and sets the current user in request.state.
    This allows other middleware to check user properties.
    """
    
    async def dispatch(self, request: Request, call_next):
        """Extract user from token and set in request.state"""
        
        # Initialize user as None
        request.state.user = None
        
        # Try to extract token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            try:
                # Import here to avoid circular imports
                from ..utils.security import verify_token
                from ..models import User
                from ..database import SessionLocal
                
                # Verify token
                payload = verify_token(token)
                
                if payload:
                    user_id = payload.get("sub")
                    
                    if user_id:
                        # Get user from database
                        db = SessionLocal()
                        try:
                            user = db.query(User).filter(User.id == int(user_id)).first()
                            if user:
                                request.state.user = user
                        finally:
                            db.close()
                            
            except Exception as e:
                # Log but don't fail - let route handlers deal with authentication
                logger.debug(f"Auth middleware: Failed to extract user: {e}")
        
        # Continue with request
        response = await call_next(request)
        return response

