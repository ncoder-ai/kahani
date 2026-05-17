"""
Configuration API endpoint for frontend
Returns frontend-relevant configuration values (no secrets)
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
import yaml
from pathlib import Path
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for config values
_config_cache: Dict[str, Any] = None

def load_config_yaml() -> Dict[str, Any]:
    """Load config.yaml file"""
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    # Try multiple locations for config.yaml:
    # 1. Project root (four levels up from backend/app/api/) - for local development
    # 2. /app/config.yaml - for Docker (mounted from project root)
    # 3. Current directory - fallback
    
    backend_dir = Path(__file__).parent.parent.parent.parent
    possible_locations = [
        backend_dir / "config.yaml",  # Project root (local dev)
        Path("/app/config.yaml"),     # Docker mount location
        Path("config.yaml"),           # Current directory fallback
    ]
    
    config_file = None
    for location in possible_locations:
        if location.exists():
            config_file = location
            break
    
    if not config_file:
        locations_str = ", ".join([str(loc) for loc in possible_locations])
        logger.error(f"config.yaml not found in any of these locations: {locations_str}")
        return {}
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        _config_cache = config
        return config
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        return {}

@router.get("/frontend")
async def get_frontend_config():
    """
    Get frontend configuration
    Returns only frontend-relevant settings (no secrets)
    """
    config = load_config_yaml()
    
    if not config:
        return JSONResponse(
            status_code=500,
            content={"error": "Configuration file not found or invalid"}
        )
    
    # Extract only frontend-relevant config
    # Note: frontend.api section removed - backend port is available via server.backend.port
    frontend_config = {
        "tts": config.get("frontend", {}).get("tts", {}),
        "extraction": config.get("frontend", {}).get("extraction", {}),
        "websocket": config.get("frontend", {}).get("websocket", {}),
        "server": config.get("server", {}),
    }
    
    return frontend_config

