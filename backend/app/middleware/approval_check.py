"""
Middleware to check if users are approved before allowing access to protected routes.
Unapproved users can only access authentication endpoints.
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class ApprovalCheckMiddleware(BaseHTTPMiddleware):
    """
    Middleware that blocks unapproved users from accessing most endpoints.
    
    Allowed routes for unapproved users:
    - /api/auth/login
    - /api/auth/register
    - /api/auth/me
    - /api/auth/logout
    - /docs, /redoc, /openapi.json (API documentation)
    - Static files
    
    All other routes require is_approved=True
    """
    
    # Routes that don't require approval
    ALLOWED_PATHS = [
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/me",
        "/api/auth/logout",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]
    
    # Path prefixes that don't require approval
    ALLOWED_PREFIXES = [
        "/static/",
        "/favicon.ico",
    ]
    
    async def dispatch(self, request: Request, call_next):
        """Check if user is approved before allowing access"""
        
        # Get the request path
        path = request.url.path
        
        # Check if this path is allowed without approval
        if self._is_allowed_path(path):
            return await call_next(request)
        
        # Check if user is authenticated and approved
        user = request.state.user if hasattr(request.state, "user") else None
        
        if user:
            # Admins always have access
            if getattr(user, "is_admin", False):
                return await call_next(request)
            
            # Check if user is approved
            if not getattr(user, "is_approved", False):
                logger.warning(f"Unapproved user {user.id} attempted to access: {path}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": "Your account is pending admin approval. Please wait for an administrator to approve your account.",
                        "status": "pending_approval",
                        "user_id": user.id
                    }
                )
        
        # User is approved or not authenticated (let other middleware handle auth)
        return await call_next(request)
    
    def _is_allowed_path(self, path: str) -> bool:
        """Check if path is allowed without approval"""
        # Exact match
        if path in self.ALLOWED_PATHS:
            return True
        
        # Prefix match
        for prefix in self.ALLOWED_PREFIXES:
            if path.startswith(prefix):
                return True
        
        return False

