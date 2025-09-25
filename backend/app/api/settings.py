from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from ..database import get_db
from ..models import User, UserSettings
from ..dependencies import get_current_user
import logging
from ..services.llm_functions import invalidate_user_llm_cache

logger = logging.getLogger(__name__)

router = APIRouter()

class LLMSettingsUpdate(BaseModel):
    temperature: float = Field(ge=0.0, le=2.0, default=0.7)
    top_p: float = Field(ge=0.0, le=1.0, default=1.0)
    top_k: int = Field(ge=1, le=100, default=50)
    repetition_penalty: float = Field(ge=1.0, le=2.0, default=1.1)
    max_tokens: int = Field(ge=100, le=4096, default=2048)
    api_url: Optional[str] = None  # No default - user must provide
    api_key: Optional[str] = None
    api_type: Optional[str] = Field(default="openai_compatible")
    model_name: Optional[str] = None

class ContextSettingsUpdate(BaseModel):
    max_tokens: int = Field(ge=1000, le=1000000, default=4000)
    keep_recent_scenes: int = Field(ge=1, le=10, default=3)
    summary_threshold: int = Field(ge=3, le=20, default=5)
    summary_threshold_tokens: int = Field(ge=1000, le=50000, default=8000)
    enable_summarization: bool = True

class GenerationPreferencesUpdate(BaseModel):
    default_genre: Optional[str] = None
    default_tone: Optional[str] = None
    scene_length: str = Field(pattern="^(short|medium|long)$", default="medium")
    auto_choices: Optional[bool] = None
    choices_count: Optional[int] = Field(ge=2, le=6, default=3)

class UIPreferencesUpdate(BaseModel):
    theme: str = Field(pattern="^(dark|light|auto)$", default="dark")
    font_size: str = Field(pattern="^(small|medium|large)$", default="medium")
    show_token_info: Optional[bool] = None
    show_context_info: Optional[bool] = None
    notifications: Optional[bool] = None
    scene_display_format: str = Field(pattern="^(default|bubble|card|minimal)$", default="default")
    show_scene_titles: Optional[bool] = None
    auto_open_last_story: Optional[bool] = None

class ExportSettingsUpdate(BaseModel):
    format: str = Field(pattern="^(markdown|pdf|txt)$", default="markdown")
    include_metadata: Optional[bool] = None
    include_choices: Optional[bool] = None

class AdvancedSettingsUpdate(BaseModel):
    custom_system_prompt: str = Field(max_length=2000, default="")
    experimental_features: bool = False

class UserSettingsUpdate(BaseModel):
    llm_settings: LLMSettingsUpdate = None
    context_settings: ContextSettingsUpdate = None
    generation_preferences: GenerationPreferencesUpdate = None
    ui_preferences: UIPreferencesUpdate = None
    export_settings: ExportSettingsUpdate = None
    advanced: AdvancedSettingsUpdate = None

@router.get("/")
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's current settings"""
    
    # Get or create user settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings:
        # Create default settings for new user
        user_settings = UserSettings(user_id=current_user.id)
        db.add(user_settings)
        db.commit()
        db.refresh(user_settings)
    
    return {
        "settings": user_settings.to_dict(),
        "message": "Settings retrieved successfully"
    }

@router.put("/")
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user settings"""
    
    # Get or create user settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings:
        user_settings = UserSettings(user_id=current_user.id)
        db.add(user_settings)
    
    # Update LLM settings
    if settings_update.llm_settings:
        llm = settings_update.llm_settings
        user_settings.llm_temperature = llm.temperature
        user_settings.llm_top_p = llm.top_p
        user_settings.llm_top_k = llm.top_k
        user_settings.llm_repetition_penalty = llm.repetition_penalty
        user_settings.llm_max_tokens = llm.max_tokens
        # Update API configuration fields
        if llm.api_url is not None:
            user_settings.llm_api_url = llm.api_url
        if llm.api_key is not None:
            user_settings.llm_api_key = llm.api_key
        if llm.api_type is not None:
            user_settings.llm_api_type = llm.api_type
        if llm.model_name is not None:
            user_settings.llm_model_name = llm.model_name
    
    # Update context settings
    if settings_update.context_settings:
        ctx = settings_update.context_settings
        user_settings.context_max_tokens = ctx.max_tokens
        user_settings.context_keep_recent_scenes = ctx.keep_recent_scenes
        user_settings.context_summary_threshold = ctx.summary_threshold
        user_settings.context_summary_threshold_tokens = ctx.summary_threshold_tokens
        user_settings.enable_context_summarization = ctx.enable_summarization
    
    # Update generation preferences
    if settings_update.generation_preferences:
        gen = settings_update.generation_preferences
        user_settings.default_genre = gen.default_genre
        user_settings.default_tone = gen.default_tone
        user_settings.preferred_scene_length = gen.scene_length
        user_settings.enable_auto_choices = gen.auto_choices
        user_settings.choices_count = gen.choices_count
    
    # Update UI preferences
    if settings_update.ui_preferences:
        ui = settings_update.ui_preferences
        user_settings.theme = ui.theme
        user_settings.font_size = ui.font_size
        user_settings.show_token_info = ui.show_token_info
        user_settings.show_context_info = ui.show_context_info
        user_settings.enable_notifications = ui.notifications
        user_settings.scene_display_format = ui.scene_display_format
        if ui.show_scene_titles is not None:
            user_settings.show_scene_titles = ui.show_scene_titles
        if ui.auto_open_last_story is not None:
            user_settings.auto_open_last_story = ui.auto_open_last_story
    
    # Update export settings
    if settings_update.export_settings:
        exp = settings_update.export_settings
        user_settings.default_export_format = exp.format
        user_settings.include_metadata = exp.include_metadata
        user_settings.include_choices = exp.include_choices
    
    # Update advanced settings
    if settings_update.advanced:
        adv = settings_update.advanced
        user_settings.custom_system_prompt = adv.custom_system_prompt
        user_settings.enable_experimental_features = adv.experimental_features
    
    try:
        db.commit()
        db.refresh(user_settings)
        
        # Invalidate LLM cache if LLM settings were updated
        if settings_update.llm_settings:
            invalidate_user_llm_cache(current_user.id)
            logger.info(f"Invalidated LLM cache for user {current_user.id} due to settings update")
        
        return {
            "settings": user_settings.to_dict(),
            "message": "Settings updated successfully"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update user settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )

@router.post("/reset")
async def reset_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset user settings to defaults"""
    
    # Get existing settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if user_settings:
        # Delete existing settings
        db.delete(user_settings)
    
    # Create new default settings
    user_settings = UserSettings(user_id=current_user.id)
    db.add(user_settings)
    
    try:
        db.commit()
        db.refresh(user_settings)
        
        return {
            "settings": user_settings.to_dict(),
            "message": "Settings reset to defaults successfully"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reset user settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset settings"
        )

@router.get("/defaults")
async def get_default_settings():
    """Get default settings configuration"""
    
    return {
        "defaults": UserSettings.get_defaults(),
        "validation_rules": {
            "llm_settings": {
                "temperature": {"min": 0.0, "max": 2.0, "description": "Controls randomness. Lower = more focused, higher = more creative"},
                "top_p": {"min": 0.0, "max": 1.0, "description": "Nucleus sampling. Controls diversity of word choices"},
                "top_k": {"min": 1, "max": 100, "description": "Limits vocabulary to top K words"},
                "repetition_penalty": {"min": 1.0, "max": 2.0, "description": "Penalizes repetition. Higher = less repetitive"},
                "max_tokens": {"min": 100, "max": 4096, "description": "Maximum tokens per generation"}
            },
            "context_settings": {
                "max_tokens": {"min": 1000, "max": 8000, "description": "Total context budget sent to LLM"},
                "keep_recent_scenes": {"min": 1, "max": 10, "description": "Always preserve this many recent scenes"},
                "summary_threshold": {"min": 3, "max": 20, "description": "Start summarizing when story exceeds this length"},
                "enable_summarization": {"description": "Enable intelligent context summarization for long stories"}
            }
        },
        "message": "Default settings and validation rules"
    }

@router.get("/presets")
async def get_settings_presets():
    """Get predefined settings presets for different use cases"""
    
    presets = {
        "creative": {
            "name": "Creative Writing",
            "description": "Optimized for creative, diverse storytelling",
            "llm_settings": {
                "temperature": 0.9,
                "top_p": 0.9,
                "top_k": 40,
                "repetition_penalty": 1.1,
                "max_tokens": 2048
            }
        },
        "focused": {
            "name": "Focused Narrative",
            "description": "More structured and coherent storytelling",
            "llm_settings": {
                "temperature": 0.5,
                "top_p": 0.8,
                "top_k": 30,
                "repetition_penalty": 1.2,
                "max_tokens": 1536
            }
        },
        "experimental": {
            "name": "Experimental",
            "description": "High creativity for experimental storytelling",
            "llm_settings": {
                "temperature": 1.2,
                "top_p": 0.95,
                "top_k": 60,
                "repetition_penalty": 1.05,
                "max_tokens": 3072
            }
        },
        "efficient": {
            "name": "Efficient",
            "description": "Balanced settings for faster generation",
            "llm_settings": {
                "temperature": 0.7,
                "top_p": 0.85,
                "top_k": 35,
                "repetition_penalty": 1.15,
                "max_tokens": 1024
            },
            "context_settings": {
                "max_tokens": 3000,
                "keep_recent_scenes": 2,
                "summary_threshold": 4
            }
        }
    }
    
    return {
        "presets": presets,
        "message": "Available settings presets"
    }

@router.post("/test-api-connection")
async def test_api_connection(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test connection to the configured LLM API"""
    import httpx
    
    # Get user settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User settings not found"
        )
    
    api_url = user_settings.llm_api_url
    if not api_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM API URL not configured. Please provide your LLM endpoint URL first."
        )
    
    api_key = user_settings.llm_api_key
    api_type = user_settings.llm_api_type or "openai_compatible"
    
    try:
        # Configure request based on API type
        headers = {}
        
        if api_type == 'openai':
            test_url = f"{api_url}/models"
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
        elif api_type == 'koboldcpp':
            test_url = f"{api_url}/api/v1/model"
        elif api_type == 'ollama':
            test_url = f"{api_url}/api/tags"
        else:  # openai_compatible
            test_url = f"{api_url}/v1/models"
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            headers['Content-Type'] = 'application/json'
        
        # Make the request with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(test_url, headers=headers)
            
        if response.status_code == 200:
            return {
                "success": True,
                "message": "API connection successful",
                "status_code": response.status_code
            }
        else:
            return {
                "success": False,
                "message": f"Connection failed: {response.status_code} {response.reason_phrase}",
                "status_code": response.status_code
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "error": str(e)
        }

@router.get("/available-models")
async def get_available_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch available models from the configured LLM API"""
    import httpx
    
    # Get user settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User settings not found"
        )
    
    api_url = user_settings.llm_api_url
    if not api_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM API URL not configured. Please provide your LLM endpoint URL first."
        )
    
    api_key = user_settings.llm_api_key
    api_type = user_settings.llm_api_type or "openai_compatible"
    
    try:
        # Configure request based on API type
        headers = {}
        
        if api_type == 'openai':
            models_url = f"{api_url}/models"
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
        elif api_type == 'koboldcpp':
            models_url = f"{api_url}/api/v1/model"
        elif api_type == 'ollama':
            models_url = f"{api_url}/api/tags"
        else:  # openai_compatible
            models_url = f"{api_url}/v1/models"
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            headers['Content-Type'] = 'application/json'
        
        # Make the request with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(models_url, headers=headers)
            
        if response.status_code == 200:
            data = response.json()
            models = []
            
            # Parse response based on API type
            if api_type == 'ollama':
                # Ollama returns {"models": [{"name": "model_name", ...}, ...]}
                if 'models' in data:
                    models = [model['name'] for model in data['models']]
            elif api_type == 'koboldcpp':
                # KoboldCpp returns {"result": "model_name"}
                if 'result' in data:
                    models = [data['result']]
            else:  # openai, openai_compatible
                # OpenAI format returns {"data": [{"id": "model_id", ...}, ...]}
                if 'data' in data:
                    models = [model['id'] for model in data['data']]
            
            return {
                "success": True,
                "models": models,
                "message": f"Found {len(models)} available models"
            }
        else:
            return {
                "success": False,
                "models": [],
                "message": f"Failed to fetch models: {response.status_code} {response.reason_phrase}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "models": [],
            "message": f"Failed to fetch models: {str(e)}"
        }

@router.get("/last-story")
async def get_last_accessed_story(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the last accessed story ID and auto-open setting"""
    
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings:
        return {
            "auto_open_last_story": False,
            "last_accessed_story_id": None
        }
    
    return {
        "auto_open_last_story": user_settings.auto_open_last_story or False,
        "last_accessed_story_id": user_settings.last_accessed_story_id
    }