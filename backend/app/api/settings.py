from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from ..database import get_db
from ..models import User, UserSettings
from ..dependencies import get_current_user
import logging
from ..services.llm.service import UnifiedLLMService

llm_service = UnifiedLLMService()

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
    completion_mode: Optional[str] = Field(default=None, pattern="^(chat|text)$")
    text_completion_template: Optional[str] = None  # JSON string
    text_completion_preset: Optional[str] = None

class ContextSettingsUpdate(BaseModel):
    max_tokens: int = Field(ge=1000, le=1000000, default=4000)
    keep_recent_scenes: int = Field(ge=1, le=10, default=3)
    summary_threshold: int = Field(ge=3, le=20, default=5)
    summary_threshold_tokens: int = Field(ge=1000, le=50000, default=8000)
    enable_summarization: bool = True
    # Semantic Memory Settings
    enable_semantic_memory: Optional[bool] = None
    context_strategy: Optional[str] = Field(default=None, pattern="^(linear|hybrid)$")
    semantic_search_top_k: Optional[int] = Field(default=None, ge=1, le=20)
    semantic_scenes_in_context: Optional[int] = Field(default=None, ge=0, le=10)
    semantic_context_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    character_moments_in_context: Optional[int] = Field(default=None, ge=0, le=10)
    auto_extract_character_moments: Optional[bool] = None
    auto_extract_plot_events: Optional[bool] = None
    extraction_confidence_threshold: Optional[int] = Field(default=None, ge=0, le=100)

class GenerationPreferencesUpdate(BaseModel):
    default_genre: Optional[str] = None
    default_tone: Optional[str] = None
    scene_length: str = Field(pattern="^(short|medium|long)$", default="medium")
    auto_choices: Optional[bool] = None
    choices_count: Optional[int] = Field(ge=2, le=6, default=3)

class UIPreferencesUpdate(BaseModel):
    color_theme: Optional[str] = Field(
        default=None,
        pattern="^(pure-dark|midnight-blue|forest-night|crimson-noir|amber-dusk|purple-dream)$"
    )
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

class CharacterAssistantSettingsUpdate(BaseModel):
    enable_suggestions: Optional[bool] = None
    importance_threshold: Optional[int] = Field(default=None, ge=0, le=100)
    mention_threshold: Optional[int] = Field(default=None, ge=1, le=100)

class EngineSettingsUpdate(BaseModel):
    engine_settings: Optional[Dict[str, Any]] = None
    current_engine: Optional[str] = None

class STTSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    model: Optional[str] = Field(default=None, pattern="^(base|small|medium)$")

class UserSettingsUpdate(BaseModel):
    llm_settings: LLMSettingsUpdate = None
    context_settings: ContextSettingsUpdate = None
    generation_preferences: GenerationPreferencesUpdate = None
    ui_preferences: UIPreferencesUpdate = None
    engine_settings: EngineSettingsUpdate = None
    export_settings: ExportSettingsUpdate = None
    stt_settings: STTSettingsUpdate = None
    advanced: AdvancedSettingsUpdate = None
    character_assistant_settings: CharacterAssistantSettingsUpdate = None

@router.get("/")
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's current settings"""
    try:
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
    except Exception as e:
        logger.error(f"Error retrieving user settings for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve settings: {str(e)}"
        )

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
        
        # Check if user is trying to change provider settings
        is_changing_provider = (
            llm.api_url is not None or 
            llm.api_key is not None or 
            llm.api_type is not None or 
            llm.model_name is not None
        )
        
        # Verify permission if changing provider configuration
        if is_changing_provider and not current_user.can_change_llm_provider:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to change LLM provider settings. Please contact an administrator."
            )
        
        # Update generation parameters (always allowed)
        user_settings.llm_temperature = llm.temperature
        user_settings.llm_top_p = llm.top_p
        user_settings.llm_top_k = llm.top_k
        user_settings.llm_repetition_penalty = llm.repetition_penalty
        user_settings.llm_max_tokens = llm.max_tokens
        
        # Update API configuration fields (only if permitted)
        # Handle empty strings as valid values (to clear fields)
        if llm.api_url is not None:
            user_settings.llm_api_url = llm.api_url if llm.api_url else None
        if llm.api_key is not None:
            user_settings.llm_api_key = llm.api_key if llm.api_key else ""
        if llm.api_type is not None:
            user_settings.llm_api_type = llm.api_type if llm.api_type else ""
        if llm.model_name is not None:
            user_settings.llm_model_name = llm.model_name if llm.model_name else ""
        
        # Update text completion settings
        if llm.completion_mode is not None:
            user_settings.completion_mode = llm.completion_mode
        if llm.text_completion_template is not None:
            user_settings.text_completion_template = llm.text_completion_template if llm.text_completion_template else None
        if llm.text_completion_preset is not None:
            user_settings.text_completion_preset = llm.text_completion_preset if llm.text_completion_preset else "llama3"
    
    # Update context settings
    if settings_update.context_settings:
        ctx = settings_update.context_settings
        user_settings.context_max_tokens = ctx.max_tokens
        user_settings.context_keep_recent_scenes = ctx.keep_recent_scenes
        user_settings.context_summary_threshold = ctx.summary_threshold
        user_settings.context_summary_threshold_tokens = ctx.summary_threshold_tokens
        user_settings.enable_context_summarization = ctx.enable_summarization
        
        # Update semantic memory settings (if provided)
        if ctx.enable_semantic_memory is not None:
            user_settings.enable_semantic_memory = ctx.enable_semantic_memory
        if ctx.context_strategy is not None:
            user_settings.context_strategy = ctx.context_strategy
        if ctx.semantic_search_top_k is not None:
            user_settings.semantic_search_top_k = ctx.semantic_search_top_k
        if ctx.semantic_scenes_in_context is not None:
            user_settings.semantic_scenes_in_context = ctx.semantic_scenes_in_context
        if ctx.semantic_context_weight is not None:
            user_settings.semantic_context_weight = ctx.semantic_context_weight
        if ctx.character_moments_in_context is not None:
            user_settings.character_moments_in_context = ctx.character_moments_in_context
        if ctx.auto_extract_character_moments is not None:
            user_settings.auto_extract_character_moments = ctx.auto_extract_character_moments
        if ctx.auto_extract_plot_events is not None:
            user_settings.auto_extract_plot_events = ctx.auto_extract_plot_events
        if ctx.extraction_confidence_threshold is not None:
            user_settings.extraction_confidence_threshold = ctx.extraction_confidence_threshold
    
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
        if ui.color_theme is not None:
            user_settings.color_theme = ui.color_theme
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
    
    # Update character assistant settings
    if settings_update.character_assistant_settings:
        char_assist = settings_update.character_assistant_settings
        if char_assist.enable_suggestions is not None:
            user_settings.enable_character_suggestions = char_assist.enable_suggestions
        if char_assist.importance_threshold is not None:
            user_settings.character_importance_threshold = char_assist.importance_threshold
        if char_assist.mention_threshold is not None:
            user_settings.character_mention_threshold = char_assist.mention_threshold
    
    # Update engine settings
    if settings_update.engine_settings:
        eng = settings_update.engine_settings
        if eng.engine_settings is not None:
            import json
            user_settings.engine_settings = json.dumps(eng.engine_settings)
        if eng.current_engine is not None:
            user_settings.current_engine = eng.current_engine
    
    # Update STT settings
    if settings_update.stt_settings:
        stt = settings_update.stt_settings
        if stt.enabled is not None:
            user_settings.stt_enabled = stt.enabled
        if stt.model is not None:
            user_settings.stt_model = stt.model
    
    try:
        db.commit()
        db.refresh(user_settings)
        
        # Invalidate LLM cache if LLM settings were updated
        if settings_update.llm_settings:
            llm_service.invalidate_user_client(current_user.id)
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

class TestConnectionRequest(BaseModel):
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    api_type: Optional[str] = None
    model_name: Optional[str] = None

class DownloadSTTModelRequest(BaseModel):
    model_name: Optional[str] = None

@router.post("/test-api-connection")
async def test_api_connection(
    request: TestConnectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test connection to the configured LLM API"""
    import httpx
    
    # Verify user has permission to manage LLM provider settings
    if not current_user.can_change_llm_provider:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to test LLM provider connections. Please contact an administrator."
        )
    
    # Use provided values or fall back to saved settings
    if request.api_url:
        api_url = request.api_url
    else:
        # Get user settings
        user_settings = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        if not user_settings or not user_settings.llm_api_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LLM API URL not configured. Please provide your LLM endpoint URL first."
            )
        api_url = user_settings.llm_api_url
    
    api_key = request.api_key or ""
    api_type = request.api_type or "openai_compatible"
    
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
        else:  # openai_compatible, tabbyapi
            # Always add /v1 for these providers
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

@router.post("/available-models")
async def get_available_models(
    request: TestConnectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch available models from the configured LLM API"""
    import httpx
    
    # Verify user has permission to manage LLM provider settings
    if not current_user.can_change_llm_provider:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view available LLM models. Please contact an administrator."
        )
    
    # Use provided values or fall back to saved settings
    if request.api_url:
        api_url = request.api_url
    else:
        # Get user settings
        user_settings = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()
        
        if not user_settings or not user_settings.llm_api_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LLM API URL not configured. Please provide your LLM endpoint URL first."
            )
        api_url = user_settings.llm_api_url
    
    api_key = request.api_key or ""
    api_type = request.api_type or "openai_compatible"
    
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
        else:  # openai_compatible, tabbyapi
            # Always add /v1 for these providers
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

@router.get("/stt-model-status")
async def get_stt_model_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if STT models (Whisper and VAD) are downloaded and available"""
    import os
    from pathlib import Path
    from ..config import settings
    
    # Get user's STT settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings or not user_settings.stt_enabled:
        return {
            "enabled": False,
            "whisper": None,
            "vad": None,
            "all_ready": False,
            "message": "STT is not enabled"
        }
    
    model_name = user_settings.stt_model or settings.stt_model
    download_root = os.path.join(settings.data_dir, "whisper_models")
    
    # Resolve to absolute path to avoid relative path issues
    download_root = os.path.abspath(download_root)
    model_path = os.path.abspath(os.path.join(download_root, model_name))
    
    # Check Whisper model status
    whisper_downloaded = False
    whisper_size = 0
    whisper_path = model_path
    debug_info = {
        "checked_path": model_path,
        "exists": False,
        "is_dir": False,
        "file_count": 0,
        "size_bytes": 0,
        "items": []
    }
    
    try:
        debug_info["exists"] = os.path.exists(model_path)
        debug_info["is_dir"] = os.path.isdir(model_path) if os.path.exists(model_path) else False
        
        if os.path.exists(model_path) and os.path.isdir(model_path):
            try:
                # Get all files recursively
                all_files = []
                for root, dirs, files in os.walk(model_path):
                    for file in files:
                        all_files.append(os.path.join(root, file))
                
                debug_info["file_count"] = len(all_files)
                debug_info["items"] = [os.path.relpath(f, model_path) for f in all_files[:10]]  # First 10 files for debugging
                
                # Calculate total size
                whisper_size = sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(model_path)
                    for filename in filenames
                )
                debug_info["size_bytes"] = whisper_size
                
                # Check if directory has substantial content
                # Models are substantial - even tiny model is > 75MB
                # Use a conservative threshold of 1MB to account for partial downloads
                if whisper_size > 1024 * 1024:  # 1MB threshold
                    whisper_downloaded = True
                elif len(all_files) > 0:
                    # If we have files but size is small, check for common model files
                    # faster-whisper uses CTranslate2 format with specific files
                    model_indicators = [
                        'config.json', 'tokenizer.json', 'model.bin',
                        'vocabulary.txt', '.bin', '.onnx'
                    ]
                    has_model_files = any(
                        any(indicator in f.lower() for indicator in model_indicators)
                        for f in all_files
                    )
                    if has_model_files:
                        whisper_downloaded = True
                        logger.info(f"Found Whisper model files in {model_path} (size: {whisper_size} bytes)")
            except (OSError, PermissionError) as e:
                logger.debug(f"Error calculating Whisper directory size: {e}")
                debug_info["error"] = str(e)
                # Fallback: check if directory has content
                try:
                    items = os.listdir(model_path)
                    debug_info["items"] = items[:10]
                    debug_info["file_count"] = len(items)
                    has_content = len(items) > 0
                    if has_content:
                        whisper_downloaded = True
                        logger.info(f"Found Whisper model directory with {len(items)} items")
                except Exception as e2:
                    logger.debug(f"Error listing directory: {e2}")
                    debug_info["list_error"] = str(e2)
                    whisper_downloaded = False
    except Exception as e:
        logger.error(f"Error checking Whisper model path: {e}", exc_info=True)
        debug_info["error"] = str(e)
        whisper_downloaded = False
    
    # Also check if download_root exists (in case model is in a different location)
    if not whisper_downloaded and os.path.exists(download_root):
        try:
            # Check if model might be stored differently by faster-whisper
            # faster-whisper might store models with compute type suffix or in subdirectories
            root_items = os.listdir(download_root)
            logger.debug(f"Contents of download_root {download_root}: {root_items}")
            
            # Look for model name variations
            model_variants = [
                model_name,
                f"{model_name}-int8",
                f"{model_name}-float16",
                f"{model_name}-float32",
            ]
            
            for variant in model_variants:
                variant_path = os.path.join(download_root, variant)
                if os.path.exists(variant_path) and os.path.isdir(variant_path):
                    logger.info(f"Found Whisper model at variant path: {variant_path}")
                    # Check size
                    try:
                        variant_size = sum(
                            os.path.getsize(os.path.join(dirpath, filename))
                            for dirpath, dirnames, filenames in os.walk(variant_path)
                            for filename in filenames
                        )
                        if variant_size > 1024 * 1024:
                            whisper_downloaded = True
                            whisper_path = variant_path
                            whisper_size = variant_size
                            debug_info["found_variant"] = variant
                            break
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Error checking download_root variants: {e}")
    
    # Check Silero VAD model status
    vad_downloaded = False
    vad_size = 0
    vad_path = None
    
    try:
        import torch
        # VAD models are now stored in data/vad_models (consistent with Whisper)
        vad_dir = os.path.join(settings.data_dir, "vad_models")
        hub_dir = os.path.join(vad_dir, 'hub')
        checkpoint_dir = os.path.join(hub_dir, 'checkpoints')
        model_cache_path = os.path.join(hub_dir, 'snakers4_silero-vad_master')
        
        # Check new location first (data directory)
        vad_path_candidates = [
            checkpoint_dir,
            model_cache_path,
            vad_dir,
        ]
        
        # Also check old cache location for backward compatibility
        cache_dir = os.path.expanduser('~/.cache/torch/hub')
        old_cache_paths = [
            os.path.join(cache_dir, 'snakers4_silero-vad_master'),
            os.path.join(cache_dir, 'snakers4_silero-vad'),
        ]
        vad_path_candidates.extend(old_cache_paths)
        
        # Check all possible paths
        for vad_path_candidate in vad_path_candidates:
            if os.path.exists(vad_path_candidate):
                if os.path.isdir(vad_path_candidate):
                    try:
                        vad_size = sum(
                            os.path.getsize(os.path.join(dirpath, filename))
                            for dirpath, dirnames, filenames in os.walk(vad_path_candidate)
                            for filename in filenames
                        )
                        if vad_size > 0:
                            vad_downloaded = True
                            vad_path = vad_path_candidate
                            break
                    except Exception:
                        # Check if directory has files
                        try:
                            items = os.listdir(vad_path_candidate)
                            if len(items) > 0:
                                vad_downloaded = True
                                vad_path = vad_path_candidate
                                break
                        except Exception:
                            pass
                elif os.path.isfile(vad_path_candidate):
                    vad_downloaded = True
                    vad_path = vad_path_candidate
                    vad_size = os.path.getsize(vad_path_candidate)
                    break
        
        # If not found in standard locations, try to check via torch.hub
        if not vad_downloaded:
            try:
                # Try to list available models
                hub_models = torch.hub.list('snakers4/silero-vad')
                if hub_models:
                    # Model repo is accessible, check if cached in data directory
                    if os.path.exists(vad_dir):
                        for root, dirs, files in os.walk(vad_dir):
                            for file in files:
                                if 'silero' in file.lower() or 'vad' in file.lower():
                                    vad_size = sum(
                                        os.path.getsize(os.path.join(dirpath, filename))
                                        for dirpath, dirnames, filenames in os.walk(vad_dir)
                                        for filename in filenames
                                    )
                                    if vad_size > 0:
                                        vad_downloaded = True
                                        vad_path = vad_dir
                                        break
                            if vad_downloaded:
                                break
            except Exception:
                pass
    except ImportError:
        # torch not available
        logger.debug("torch not available for VAD check")
    except Exception as e:
        logger.debug(f"Error checking VAD model: {e}")
    
    all_ready = whisper_downloaded and vad_downloaded
    
    return {
        "enabled": True,
        "whisper": {
            "model": model_name,
            "downloaded": whisper_downloaded,
            "path": whisper_path,
            "size_mb": round(whisper_size / (1024 * 1024), 2) if whisper_size > 0 else 0,
            "debug": debug_info  # Include debug info for troubleshooting
        },
        "vad": {
            "downloaded": vad_downloaded,
            "path": vad_path,
            "size_mb": round(vad_size / (1024 * 1024), 2) if vad_size > 0 else 0
        },
        "all_ready": all_ready,
        "message": f"STT models: Whisper {'ready' if whisper_downloaded else 'not downloaded'}, VAD {'ready' if vad_downloaded else 'not downloaded'}"
    }


@router.post("/download-stt-model")
async def download_stt_model_endpoint(
    request: Optional[DownloadSTTModelRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Trigger STT model download (Whisper + VAD) in the background"""
    import asyncio
    from ..config import settings
    
    # Get user's STT settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings or not user_settings.stt_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="STT is not enabled. Please enable STT first."
        )
    
    model_to_download = (request.model_name if request else None) or user_settings.stt_model or settings.stt_model
    
    # Import download functions
    import sys
    import os
    backend_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    sys.path.insert(0, backend_path)
    
    try:
        from download_models import download_stt_model, download_silero_vad_model
        
        download_root = os.path.join(settings.data_dir, "whisper_models")
        
        # Download both models sequentially
        def download_all():
            results = {}
            
            # Download Whisper model
            results['whisper'] = download_stt_model(model_to_download, download_root)
            
            # Download VAD model (use same data_dir as Whisper)
            data_dir = os.path.dirname(download_root)  # Get parent directory (data_dir)
            results['vad'] = download_silero_vad_model(data_dir)
            
            return results
        
        # Start download in background
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, download_all)
        
        whisper_success = results.get('whisper', False)
        vad_success = results.get('vad', False)
        
        if whisper_success and vad_success:
            return {
                "success": True,
                "message": f"STT models downloaded successfully (Whisper: {model_to_download}, VAD: ready)",
                "whisper": {"success": True, "model": model_to_download},
                "vad": {"success": True}
            }
        elif whisper_success or vad_success:
            # Partial success
            error_msg = "Partially downloaded: "
            if whisper_success:
                error_msg += "Whisper ✓, "
            else:
                error_msg += "Whisper ✗, "
            if vad_success:
                error_msg += "VAD ✓"
            else:
                error_msg += "VAD ✗"
            
            raise HTTPException(
                status_code=status.HTTP_207_MULTI_STATUS,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download STT models (Whisper: {model_to_download}, VAD)"
            )
    except ImportError as e:
        logger.error(f"Failed to import download_models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Download functionality not available"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download STT models: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download STT models: {str(e)}"
        )


@router.get("/last-story")
async def get_last_accessed_story(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the last accessed story ID and auto-open setting - validates story exists and is active"""
    
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings or not user_settings.last_accessed_story_id:
        return {
            "auto_open_last_story": False,
            "last_accessed_story_id": None
        }
    
    # Validate that the story still exists and is active
    from ..models import Story, StoryStatus
    story = db.query(Story).filter(
        Story.id == user_settings.last_accessed_story_id,
        Story.owner_id == current_user.id,
        Story.status != StoryStatus.ARCHIVED
    ).first()
    
    # If story doesn't exist or is archived, clear the setting
    if not story:
        logger.info(f"Clearing invalid last_accessed_story_id {user_settings.last_accessed_story_id} for user {current_user.id}")
        user_settings.last_accessed_story_id = None
        db.commit()
        return {
            "auto_open_last_story": user_settings.auto_open_last_story or False,
            "last_accessed_story_id": None
        }
    
    return {
        "auto_open_last_story": user_settings.auto_open_last_story or False,
        "last_accessed_story_id": user_settings.last_accessed_story_id
    }


# Text Completion Template Endpoints

@router.get("/text-completion/presets")
async def get_text_completion_presets(
    current_user: User = Depends(get_current_user)
):
    """
    Get list of available text completion template presets.
    
    Returns metadata about each preset including name, description,
    and compatible models.
    """
    from ..services.llm.templates import TextCompletionTemplateManager
    
    try:
        presets = TextCompletionTemplateManager.get_available_presets()
        return {
            "presets": presets,
            "message": "Text completion presets retrieved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to get text completion presets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve text completion presets"
        )


@router.get("/text-completion/template/{preset_name}")
async def get_preset_template(
    preset_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the full template configuration for a specific preset.
    
    Args:
        preset_name: Name of the preset (e.g., "llama3", "mistral", "qwen", "glm", "generic")
    
    Returns:
        Template configuration dictionary with all formatting tokens
    """
    from ..services.llm.templates import TextCompletionTemplateManager
    
    try:
        template = TextCompletionTemplateManager.get_preset_template(preset_name)
        
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preset '{preset_name}' not found"
            )
        
        return {
            "template": template,
            "message": f"Template for '{preset_name}' retrieved successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get preset template '{preset_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve preset template"
        )


class TemplateRenderRequest(BaseModel):
    """Request model for testing template rendering"""
    template: Dict[str, str]
    test_system: str = Field(default="You are a helpful assistant.")
    test_user: str = Field(default="Hello, how are you?")


@router.post("/text-completion/test-render")
async def test_template_render(
    request: TemplateRenderRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test rendering a template with sample prompts.
    
    This endpoint validates the template structure and shows how it will
    be assembled without making an actual LLM API call.
    
    Args:
        request: Template configuration and test prompts
    
    Returns:
        Rendered prompt string and validation status
    """
    from ..services.llm.templates import TextCompletionTemplateManager
    
    try:
        # Validate template structure
        is_valid, error_msg = TextCompletionTemplateManager.validate_template(request.template)
        
        if not is_valid:
            return {
                "valid": False,
                "error": error_msg,
                "rendered_prompt": None
            }
        
        # Render the template
        rendered_prompt = TextCompletionTemplateManager.render_template(
            request.template,
            system_prompt=request.test_system,
            user_prompt=request.test_user
        )
        
        return {
            "valid": True,
            "error": None,
            "rendered_prompt": rendered_prompt,
            "prompt_length": len(rendered_prompt),
            "message": "Template rendered successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to render template: {e}")
        return {
            "valid": False,
            "error": str(e),
            "rendered_prompt": None
        }