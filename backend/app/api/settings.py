from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import json
from ..database import get_db
from ..models import User, UserSettings
from ..dependencies import get_current_user
from ..config import settings
import logging
from ..services.llm.service import UnifiedLLMService

llm_service = UnifiedLLMService()

logger = logging.getLogger(__name__)

router = APIRouter()

# Provider registry for all supported LLM providers
# Cloud providers: LiteLLM routes natively, user only provides API key + model
# Local providers: User provides URL + optional key + model
PROVIDER_REGISTRY = {
    # Cloud providers - LiteLLM routes natively
    "openai": {"label": "OpenAI", "category": "cloud", "base_url": "https://api.openai.com/v1", "models_path": "/models"},
    "anthropic": {"label": "Anthropic", "category": "cloud", "base_url": "https://api.anthropic.com/v1", "models_path": "/models"},
    "groq": {"label": "Groq", "category": "cloud", "base_url": "https://api.groq.com/openai/v1", "models_path": "/models"},
    "mistral": {"label": "Mistral AI", "category": "cloud", "base_url": "https://api.mistral.ai/v1", "models_path": "/models"},
    "deepseek": {"label": "DeepSeek", "category": "cloud", "base_url": "https://api.deepseek.com", "models_path": "/models"},
    "together_ai": {"label": "Together AI", "category": "cloud", "base_url": "https://api.together.xyz/v1", "models_path": "/models"},
    "fireworks_ai": {"label": "Fireworks AI", "category": "cloud", "base_url": "https://api.fireworks.ai/inference/v1", "models_path": "/models"},
    "openrouter": {"label": "OpenRouter", "category": "cloud", "base_url": "https://openrouter.ai/api/v1", "models_path": "/models"},
    "perplexity": {"label": "Perplexity", "category": "cloud", "base_url": "https://api.perplexity.ai", "models_path": "/models"},
    "deepinfra": {"label": "DeepInfra", "category": "cloud", "base_url": "https://api.deepinfra.com/v1/openai", "models_path": "/models"},
    "gemini": {"label": "Google Gemini", "category": "cloud", "base_url": None, "models_path": None},
    "cohere": {"label": "Cohere", "category": "cloud", "base_url": None, "models_path": None},
    "xai": {"label": "xAI (Grok)", "category": "cloud", "base_url": "https://api.x.ai/v1", "models_path": "/models"},
    "cerebras": {"label": "Cerebras", "category": "cloud", "base_url": "https://api.cerebras.ai/v1", "models_path": "/models"},
    "sambanova": {"label": "SambaNova", "category": "cloud", "base_url": "https://api.sambanova.ai/v1", "models_path": "/models"},
    "ai21": {"label": "AI21 Labs", "category": "cloud", "base_url": None, "models_path": None},
    "novita": {"label": "Novita AI", "category": "cloud", "base_url": "https://api.novita.ai/v3/openai", "models_path": "/models"},
    # Local/self-hosted providers - user provides URL
    "openai-compatible": {"label": "OpenAI Compatible", "category": "local", "base_url": None, "models_path": "/v1/models"},
    "ollama": {"label": "Ollama", "category": "local", "base_url": None, "models_path": "/api/tags"},
    "koboldcpp": {"label": "KoboldCpp", "category": "local", "base_url": None, "models_path": "/api/v1/model"},
    "tabbyapi": {"label": "TabbyAPI", "category": "local", "base_url": None, "models_path": "/v1/models"},
    "vllm": {"label": "vLLM", "category": "local", "base_url": None, "models_path": "/v1/models"},
    "lm_studio": {"label": "LM Studio", "category": "local", "base_url": None, "models_path": "/v1/models"},
}

def is_cloud_provider(api_type: str) -> bool:
    """Check if a provider is a cloud provider (LiteLLM routes natively)"""
    provider = PROVIDER_REGISTRY.get(api_type)
    return provider is not None and provider["category"] == "cloud"

def get_provider_base_url(api_type: str) -> Optional[str]:
    """Get the base URL for a cloud provider from the registry"""
    provider = PROVIDER_REGISTRY.get(api_type)
    if provider and provider["category"] == "cloud":
        return provider.get("base_url")
    return None

class LLMSettingsUpdate(BaseModel):
    temperature: float = Field(ge=0.0, le=2.0, default=0.7)
    top_p: float = Field(ge=0.0, le=1.0, default=1.0)
    top_k: int = Field(ge=1, le=100, default=50)
    repetition_penalty: float = Field(ge=1.0, le=2.0, default=1.1)
    max_tokens: int = Field(ge=100, le=32000, default=2048)
    timeout_total: Optional[float] = Field(ge=30.0, le=600.0, default=None)
    api_url: Optional[str] = None  # No default - user must provide
    api_key: Optional[str] = None
    api_type: Optional[str] = Field(default="openai_compatible")
    model_name: Optional[str] = None
    completion_mode: Optional[str] = Field(default=None, pattern="^(chat|text)$")
    text_completion_template: Optional[str] = None  # JSON string
    text_completion_preset: Optional[str] = None
    # Reasoning/Thinking Settings
    reasoning_effort: Optional[str] = Field(default=None, pattern="^(disabled|low|medium|high)$")  # None = auto
    show_thinking_content: Optional[bool] = None  # Whether to display thinking text in UI
    # Local thinking model settings (for Qwen3, DeepSeek, etc.)
    thinking_model_type: Optional[str] = Field(default=None, pattern="^(none|qwen3|deepseek|mistral|gemini|openai|kimi|glm|custom)$")
    thinking_model_custom_pattern: Optional[str] = None
    thinking_enabled_generation: Optional[bool] = None

class ContextSettingsUpdate(BaseModel):
    max_tokens: int = Field(ge=1000, le=1000000, default=4000)
    keep_recent_scenes: int = Field(ge=1, le=10, default=3)
    summary_threshold: int = Field(ge=3, le=20, default=5)
    summary_threshold_tokens: int = Field(ge=1000, le=50000, default=8000)
    enable_summarization: bool = True
    character_extraction_threshold: Optional[int] = Field(default=None, ge=1, le=20)
    scene_batch_size: Optional[int] = Field(default=None, ge=5, le=50)  # Batch size for scene caching
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
    plot_event_extraction_threshold: Optional[int] = Field(default=None, ge=1, le=50)
    fill_remaining_context: Optional[bool] = None  # Fill remaining context with older scenes
    # Memory & Continuity Settings
    enable_working_memory: Optional[bool] = None  # Track scene-to-scene focus and pending items
    enable_relationship_graph: Optional[bool] = None  # Track character relationship arcs
    # Contradiction Settings
    enable_contradiction_detection: Optional[bool] = None  # Detect continuity errors
    enable_contradiction_injection: Optional[bool] = None  # Inject warnings into prompt
    enable_inline_contradiction_check: Optional[bool] = None  # Run extraction + check every scene

class GenerationPreferencesUpdate(BaseModel):
    default_genre: Optional[str] = None
    default_tone: Optional[str] = None
    scene_length: str = Field(pattern="^(short|medium|long)$", default="medium")
    auto_choices: Optional[bool] = None
    choices_count: Optional[int] = Field(ge=2, le=6, default=3)
    enable_streaming: Optional[bool] = None  # Enable streaming generation
    alert_on_high_context: Optional[bool] = None
    use_extraction_llm_for_summary: Optional[bool] = None
    separate_choice_generation: Optional[bool] = None
    use_cache_friendly_prompts: Optional[bool] = None  # Preserve KV cache across LLM calls
    enable_chapter_plot_tracking: Optional[bool] = None  # Track plot progress and guide LLM pacing
    default_plot_check_mode: Optional[str] = Field(default=None, pattern="^(1|3|all)$")  # How many events to check: "1" (strict), "3", "all"

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
    show_scene_images: Optional[bool] = None
    scene_edit_mode: Optional[str] = Field(default=None, pattern="^(textarea|contenteditable)$")
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

class ExtractionModelSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    api_type: Optional[str] = None  # Provider type (e.g., "openai-compatible", "groq")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=100, le=5000)
    fallback_to_main: Optional[bool] = None
    enable_combined_extraction: Optional[bool] = None  # Enable combined extraction (default: True)
    use_context_aware_extraction: Optional[bool] = None  # Use main LLM with full scene context for better extraction
    use_main_llm_for_plot_extraction: Optional[bool] = None  # Use main LLM for plot event extraction
    use_main_llm_for_decomposition: Optional[bool] = None  # Use main LLM for query decomposition
    # Advanced sampling settings
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    repetition_penalty: Optional[float] = Field(default=None, ge=0.0, le=3.0)  # 0 or 1.0 = disabled
    min_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # Thinking disable settings
    # Methods: "none", "qwen3", "deepseek", "mistral", "gemini", "openai", "kimi", "glm", "custom"
    thinking_disable_method: Optional[str] = Field(
        default=None,
        pattern="^(none|qwen3|deepseek|mistral|gemini|openai|kimi|glm|custom)$"
    )
    thinking_disable_custom: Optional[str] = None  # Custom tag pattern for "custom" method
    # Per-task thinking toggles
    thinking_enabled_extractions: Optional[bool] = None
    thinking_enabled_memory: Optional[bool] = None

class ExtractionEngineSettingsUpdate(BaseModel):
    extraction_engine_settings: Optional[Dict[str, Any]] = None
    current_extraction_engine: Optional[str] = None


class SamplerSettingValue(BaseModel):
    """Individual sampler configuration with enabled flag and value"""
    enabled: bool = False
    value: Any = None


class SamplerSettingsUpdate(BaseModel):
    """Advanced sampler settings for TabbyAPI and OpenAI-compatible APIs.
    
    Each sampler can be individually enabled/disabled. Only enabled samplers
    are sent to the API via extra_body.
    """
    # Basic Sampling
    temperature_last: Optional[SamplerSettingValue] = None
    smoothing_factor: Optional[SamplerSettingValue] = None
    min_p: Optional[SamplerSettingValue] = None
    top_a: Optional[SamplerSettingValue] = None
    
    # Token Control
    min_tokens: Optional[SamplerSettingValue] = None
    token_healing: Optional[SamplerSettingValue] = None
    add_bos_token: Optional[SamplerSettingValue] = None
    ban_eos_token: Optional[SamplerSettingValue] = None
    
    # Penalties
    frequency_penalty: Optional[SamplerSettingValue] = None
    presence_penalty: Optional[SamplerSettingValue] = None
    penalty_range: Optional[SamplerSettingValue] = None
    repetition_decay: Optional[SamplerSettingValue] = None
    
    # Advanced Sampling
    tfs: Optional[SamplerSettingValue] = None
    typical: Optional[SamplerSettingValue] = None
    skew: Optional[SamplerSettingValue] = None
    
    # XTC (Exclude Top Choices)
    xtc_probability: Optional[SamplerSettingValue] = None
    xtc_threshold: Optional[SamplerSettingValue] = None
    
    # DRY (Don't Repeat Yourself)
    dry_multiplier: Optional[SamplerSettingValue] = None
    dry_base: Optional[SamplerSettingValue] = None
    dry_allowed_length: Optional[SamplerSettingValue] = None
    dry_range: Optional[SamplerSettingValue] = None
    dry_sequence_breakers: Optional[SamplerSettingValue] = None
    
    # Mirostat
    mirostat_mode: Optional[SamplerSettingValue] = None
    mirostat_tau: Optional[SamplerSettingValue] = None
    mirostat_eta: Optional[SamplerSettingValue] = None
    
    # Dynamic Temperature
    max_temp: Optional[SamplerSettingValue] = None
    min_temp: Optional[SamplerSettingValue] = None
    temp_exponent: Optional[SamplerSettingValue] = None
    
    # Constraints
    banned_strings: Optional[SamplerSettingValue] = None
    banned_tokens: Optional[SamplerSettingValue] = None
    allowed_tokens: Optional[SamplerSettingValue] = None
    stop: Optional[SamplerSettingValue] = None
    
    # Other
    cfg_scale: Optional[SamplerSettingValue] = None
    negative_prompt: Optional[SamplerSettingValue] = None
    speculative_ngram: Optional[SamplerSettingValue] = None
    
    # Multi-generation
    n: Optional[SamplerSettingValue] = None  # Number of completions to generate (1-5)


class ImageGenerationSettingsUpdate(BaseModel):
    """Settings for AI image generation"""
    enabled: Optional[bool] = None
    comfyui_server_url: Optional[str] = None
    comfyui_api_key: Optional[str] = None
    comfyui_checkpoint: Optional[str] = None
    comfyui_model_type: Optional[str] = None
    width: Optional[int] = Field(default=None, ge=256, le=2048)
    height: Optional[int] = Field(default=None, ge=256, le=2048)
    steps: Optional[int] = Field(default=None, ge=1, le=100)
    cfg_scale: Optional[float] = Field(default=None, ge=1.0, le=20.0)
    default_style: Optional[str] = None
    use_extraction_llm_for_prompts: Optional[bool] = None


class UserSettingsUpdate(BaseModel):
    llm_settings: LLMSettingsUpdate = None
    context_settings: ContextSettingsUpdate = None
    generation_preferences: GenerationPreferencesUpdate = None
    ui_preferences: UIPreferencesUpdate = None
    engine_settings: EngineSettingsUpdate = None
    export_settings: ExportSettingsUpdate = None
    stt_settings: STTSettingsUpdate = None
    extraction_model_settings: ExtractionModelSettingsUpdate = None
    extraction_engine_settings: Optional[ExtractionEngineSettingsUpdate] = None
    advanced: AdvancedSettingsUpdate = None
    character_assistant_settings: CharacterAssistantSettingsUpdate = None
    sampler_settings: Optional[SamplerSettingsUpdate] = None
    image_generation_settings: Optional[ImageGenerationSettingsUpdate] = None

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
            # Populate with defaults from config.yaml
            user_settings.populate_from_defaults()
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
            detail="Failed to retrieve settings"
        )

@router.put("/")
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user settings"""

    # Debug: Log received context_settings for contradiction fields
    if settings_update.context_settings:
        ctx = settings_update.context_settings
        logger.info(f"[SETTINGS UPDATE] Received contradiction settings: "
                   f"detection={ctx.enable_contradiction_detection}, "
                   f"injection={ctx.enable_contradiction_injection}, "
                   f"inline={ctx.enable_inline_contradiction_check}")

    # Get or create user settings
    user_settings = db.query(UserSettings).filter(
        UserSettings.user_id == current_user.id
    ).first()
    
    if not user_settings:
        user_settings = UserSettings(user_id=current_user.id)
        # Populate with defaults from config.yaml
        user_settings.populate_from_defaults()
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
        if llm.timeout_total is not None:
            user_settings.llm_timeout_total = llm.timeout_total
        
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
        
        # Update reasoning/thinking settings
        if llm.reasoning_effort is not None:
            user_settings.reasoning_effort = llm.reasoning_effort if llm.reasoning_effort else None
        if llm.show_thinking_content is not None:
            user_settings.show_thinking_content = llm.show_thinking_content
        # Local thinking model settings
        if llm.thinking_model_type is not None:
            user_settings.thinking_model_type = llm.thinking_model_type if llm.thinking_model_type != 'none' else None
        if llm.thinking_model_custom_pattern is not None:
            user_settings.thinking_model_custom_pattern = llm.thinking_model_custom_pattern or None
        if llm.thinking_enabled_generation is not None:
            user_settings.thinking_enabled_generation = llm.thinking_enabled_generation

    # Update context settings
    if settings_update.context_settings:
        ctx = settings_update.context_settings
        # Add defensive checks for None values
        if ctx.max_tokens is not None:
            user_settings.context_max_tokens = ctx.max_tokens
        if ctx.keep_recent_scenes is not None:
            user_settings.context_keep_recent_scenes = ctx.keep_recent_scenes
        if ctx.summary_threshold is not None:
            user_settings.context_summary_threshold = ctx.summary_threshold
        if ctx.summary_threshold_tokens is not None:
            user_settings.context_summary_threshold_tokens = ctx.summary_threshold_tokens
        if ctx.enable_summarization is not None:
            user_settings.enable_context_summarization = ctx.enable_summarization
        if ctx.character_extraction_threshold is not None:
            user_settings.character_extraction_threshold = ctx.character_extraction_threshold
        if ctx.scene_batch_size is not None:
            user_settings.scene_batch_size = ctx.scene_batch_size
        
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
        if ctx.plot_event_extraction_threshold is not None:
            user_settings.plot_event_extraction_threshold = ctx.plot_event_extraction_threshold
        if ctx.fill_remaining_context is not None:
            user_settings.fill_remaining_context = ctx.fill_remaining_context
        # Memory & Continuity settings
        if ctx.enable_working_memory is not None:
            user_settings.enable_working_memory = ctx.enable_working_memory
        if ctx.enable_relationship_graph is not None:
            user_settings.enable_relationship_graph = ctx.enable_relationship_graph
        # Contradiction settings
        if ctx.enable_contradiction_detection is not None:
            user_settings.enable_contradiction_detection = ctx.enable_contradiction_detection
        if ctx.enable_contradiction_injection is not None:
            user_settings.enable_contradiction_injection = ctx.enable_contradiction_injection
        if ctx.enable_inline_contradiction_check is not None:
            user_settings.enable_inline_contradiction_check = ctx.enable_inline_contradiction_check

    # Update generation preferences
    if settings_update.generation_preferences:
        gen = settings_update.generation_preferences
        logger.info(f"[SETTINGS UPDATE] Received generation_preferences: "
                   f"enable_chapter_plot_tracking={gen.enable_chapter_plot_tracking}, "
                   f"default_plot_check_mode={gen.default_plot_check_mode}")
        if gen.default_genre is not None:
            user_settings.default_genre = gen.default_genre
        if gen.default_tone is not None:
            user_settings.default_tone = gen.default_tone
        if gen.scene_length is not None:
            user_settings.preferred_scene_length = gen.scene_length
        if gen.auto_choices is not None:
            user_settings.enable_auto_choices = gen.auto_choices
        if gen.choices_count is not None:
            user_settings.choices_count = gen.choices_count
        if gen.alert_on_high_context is not None:
            user_settings.alert_on_high_context = gen.alert_on_high_context
        if gen.use_extraction_llm_for_summary is not None:
            user_settings.use_extraction_llm_for_summary = gen.use_extraction_llm_for_summary
        if gen.separate_choice_generation is not None:
            user_settings.separate_choice_generation = gen.separate_choice_generation
        if gen.use_cache_friendly_prompts is not None:
            user_settings.use_cache_friendly_prompts = gen.use_cache_friendly_prompts
        if gen.enable_chapter_plot_tracking is not None:
            user_settings.enable_chapter_plot_tracking = gen.enable_chapter_plot_tracking
        if gen.default_plot_check_mode is not None:
            user_settings.default_plot_check_mode = gen.default_plot_check_mode
        if gen.enable_streaming is not None:
            user_settings.enable_streaming = gen.enable_streaming

    # Update UI preferences
    if settings_update.ui_preferences:
        ui = settings_update.ui_preferences
        if ui.color_theme is not None:
            user_settings.color_theme = ui.color_theme
        if ui.font_size is not None:
            user_settings.font_size = ui.font_size
        if ui.show_token_info is not None:
            user_settings.show_token_info = ui.show_token_info
        if ui.show_context_info is not None:
            user_settings.show_context_info = ui.show_context_info
        if ui.notifications is not None:
            user_settings.enable_notifications = ui.notifications
        if ui.scene_display_format is not None:
            user_settings.scene_display_format = ui.scene_display_format
        if ui.show_scene_titles is not None:
            user_settings.show_scene_titles = ui.show_scene_titles
        if ui.show_scene_images is not None:
            user_settings.show_scene_images = ui.show_scene_images
        if ui.scene_edit_mode is not None:
            user_settings.scene_edit_mode = ui.scene_edit_mode
        if ui.auto_open_last_story is not None:
            user_settings.auto_open_last_story = ui.auto_open_last_story
    
    # Update export settings
    if settings_update.export_settings:
        exp = settings_update.export_settings
        if exp.format is not None:
            user_settings.default_export_format = exp.format
        if exp.include_metadata is not None:
            user_settings.include_metadata = exp.include_metadata
        if exp.include_choices is not None:
            user_settings.include_choices = exp.include_choices
    
    # Update advanced settings
    if settings_update.advanced:
        adv = settings_update.advanced
        if adv.custom_system_prompt is not None:
            user_settings.custom_system_prompt = adv.custom_system_prompt
        if adv.experimental_features is not None:
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
    
    # Update extraction model settings
    if settings_update.extraction_model_settings:
        ext = settings_update.extraction_model_settings
        if ext.enabled is not None:
            user_settings.extraction_model_enabled = ext.enabled
        if ext.url is not None:
            ext_defaults = settings._yaml_config.get('extraction_model', {})
            user_settings.extraction_model_url = ext.url if ext.url else ext_defaults.get('url')
        if ext.api_key is not None:
            user_settings.extraction_model_api_key = ext.api_key if ext.api_key else ""
        if ext.model_name is not None:
            ext_defaults = settings._yaml_config.get('extraction_model', {})
            user_settings.extraction_model_name = ext.model_name if ext.model_name else ext_defaults.get('model_name')
        if ext.temperature is not None:
            user_settings.extraction_model_temperature = ext.temperature
        if ext.max_tokens is not None:
            user_settings.extraction_model_max_tokens = ext.max_tokens
        if ext.fallback_to_main is not None:
            user_settings.extraction_fallback_to_main = ext.fallback_to_main
        if ext.use_context_aware_extraction is not None:
            user_settings.use_context_aware_extraction = ext.use_context_aware_extraction
        if ext.use_main_llm_for_plot_extraction is not None:
            user_settings.use_main_llm_for_plot_extraction = ext.use_main_llm_for_plot_extraction
        if ext.use_main_llm_for_decomposition is not None:
            user_settings.use_main_llm_for_decomposition = ext.use_main_llm_for_decomposition
        # Advanced sampling settings
        if ext.top_p is not None:
            user_settings.extraction_model_top_p = ext.top_p
        if ext.repetition_penalty is not None:
            user_settings.extraction_model_repetition_penalty = ext.repetition_penalty
        if ext.min_p is not None:
            user_settings.extraction_model_min_p = ext.min_p
        # Thinking disable settings
        if ext.thinking_disable_method is not None:
            user_settings.extraction_model_thinking_disable_method = ext.thinking_disable_method
        if ext.thinking_disable_custom is not None:
            user_settings.extraction_model_thinking_disable_custom = ext.thinking_disable_custom
        # Per-task thinking toggles
        if ext.thinking_enabled_extractions is not None:
            user_settings.extraction_model_thinking_enabled_extractions = ext.thinking_enabled_extractions
        if ext.thinking_enabled_memory is not None:
            user_settings.extraction_model_thinking_enabled_memory = ext.thinking_enabled_memory

    # Update extraction engine settings (per-engine persistence, mirrors main engine_settings)
    if settings_update.extraction_engine_settings:
        ext_eng = settings_update.extraction_engine_settings
        if ext_eng.extraction_engine_settings is not None:
            user_settings.extraction_engine_settings = json.dumps(ext_eng.extraction_engine_settings)
        if ext_eng.current_extraction_engine is not None:
            user_settings.current_extraction_engine = ext_eng.current_extraction_engine

    # Save extraction api_type from extraction_model_settings
    if settings_update.extraction_model_settings:
        ext = settings_update.extraction_model_settings
        if ext.api_type is not None:
            user_settings.extraction_model_api_type = ext.api_type if ext.api_type else None

    # Update sampler settings
    if settings_update.sampler_settings:
        sampler = settings_update.sampler_settings
        # Get existing sampler settings or start with defaults
        existing_samplers = {}
        if user_settings.sampler_settings:
            try:
                existing_samplers = json.loads(user_settings.sampler_settings)
            except (json.JSONDecodeError, TypeError):
                existing_samplers = {}
        
        # Update only the samplers that were provided
        sampler_dict = sampler.model_dump(exclude_none=True)
        for key, value in sampler_dict.items():
            if value is not None:
                existing_samplers[key] = value
        
        # Save as JSON string
        user_settings.sampler_settings = json.dumps(existing_samplers)

    # Update image generation settings
    if settings_update.image_generation_settings:
        img = settings_update.image_generation_settings
        if img.enabled is not None:
            user_settings.image_gen_enabled = img.enabled
        if img.comfyui_server_url is not None:
            user_settings.comfyui_server_url = img.comfyui_server_url
        if img.comfyui_api_key is not None:
            user_settings.comfyui_api_key = img.comfyui_api_key
        if img.comfyui_checkpoint is not None:
            user_settings.comfyui_checkpoint = img.comfyui_checkpoint
        if img.comfyui_model_type is not None:
            user_settings.comfyui_model_type = img.comfyui_model_type
        if img.width is not None:
            user_settings.image_gen_width = img.width
        if img.height is not None:
            user_settings.image_gen_height = img.height
        if img.steps is not None:
            user_settings.image_gen_steps = img.steps
        if img.cfg_scale is not None:
            user_settings.image_gen_cfg_scale = img.cfg_scale
        if img.default_style is not None:
            user_settings.image_gen_default_style = img.default_style
        if img.use_extraction_llm_for_prompts is not None:
            user_settings.use_extraction_llm_for_image_prompts = img.use_extraction_llm_for_prompts

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
        logger.error(f"Failed to update user settings for user {current_user.id}: {e}", exc_info=True)
        
        # Provide more detailed error information
        error_detail = f"Failed to update settings: {str(e)}"
        if "NOT NULL constraint" in str(e) or "constraint" in str(e).lower():
            error_detail = f"Database constraint violation: {str(e)}. Please check that all required fields are provided."
        elif "IntegrityError" in str(type(e).__name__):
            error_detail = f"Database integrity error: {str(e)}. This may indicate a data conflict."
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
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
    # Populate with defaults from config.yaml
    user_settings.populate_from_defaults()
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
                "max_tokens": {"min": 100, "max": 32000, "description": "Maximum tokens per generation (increase for reasoning models)"}
            },
            "context_settings": {
                "max_tokens": {"min": 1000, "max": 8000, "description": "Total context budget sent to LLM"},
                "keep_recent_scenes": {"min": 1, "max": 10, "description": "Always preserve this many recent scenes"},
                "summary_threshold": {"min": 3, "max": 20, "description": "Start summarizing when story exceeds this length"},
                "enable_summarization": {"description": "Enable intelligent context summarization for long stories"},
                "scene_batch_size": {"min": 5, "max": 50, "default": 10, "description": "Batch size for scene caching - scenes are grouped into batches for better LLM cache hit rates"}
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

@router.get("/llm-providers")
async def get_llm_providers():
    """Get available LLM providers with metadata"""
    providers = []
    for key, info in PROVIDER_REGISTRY.items():
        providers.append({
            "id": key,
            "label": info["label"],
            "category": info["category"],
            "needs_url": info["category"] == "local",
            "needs_api_key": info["category"] == "cloud",
        })
    return {"providers": providers}


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
    api_key = request.api_key or ""
    api_type = request.api_type or "openai_compatible"

    # For cloud providers, resolve URL from registry
    if is_cloud_provider(api_type):
        cloud_base = get_provider_base_url(api_type)
        if cloud_base:
            api_url = cloud_base
        else:
            # Provider without base_url (gemini, cohere, ai21) — can't HTTP test
            return {
                "success": True,
                "message": f"Cloud provider '{api_type}' uses LiteLLM native routing. Connection will be tested on first use.",
                "status_code": 200
            }
    elif request.api_url:
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

    try:
        # Configure request based on API type
        headers = {}

        if is_cloud_provider(api_type):
            # Cloud providers: use base_url + /models
            provider_info = PROVIDER_REGISTRY[api_type]
            test_url = f"{api_url.rstrip('/')}{provider_info.get('models_path', '/models')}"
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
        elif api_type == 'koboldcpp':
            test_url = f"{api_url}/api/v1/model"
        elif api_type == 'ollama':
            test_url = f"{api_url}/api/tags"
        else:  # openai_compatible, tabbyapi, vllm, lm_studio
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

    api_key = request.api_key or ""
    api_type = request.api_type or "openai_compatible"

    # For cloud providers, resolve URL from registry
    if is_cloud_provider(api_type):
        cloud_base = get_provider_base_url(api_type)
        if cloud_base:
            api_url = cloud_base
        else:
            # Provider without base_url (gemini, cohere, ai21) — use litellm static list
            try:
                import litellm
                provider_models = litellm.models_by_provider.get(api_type, [])
                return {
                    "success": True,
                    "models": list(provider_models),
                    "message": f"Found {len(provider_models)} models for {api_type}"
                }
            except Exception:
                return {
                    "success": False,
                    "models": [],
                    "message": f"Could not fetch models for {api_type}"
                }
    elif request.api_url:
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

    try:
        # Configure request based on API type
        headers = {}

        if is_cloud_provider(api_type):
            # Cloud providers: use base_url + /models
            provider_info = PROVIDER_REGISTRY[api_type]
            models_url = f"{api_url.rstrip('/')}{provider_info.get('models_path', '/models')}"
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
        elif api_type == 'koboldcpp':
            models_url = f"{api_url}/api/v1/model"
        elif api_type == 'ollama':
            models_url = f"{api_url}/api/tags"
        else:  # openai_compatible, tabbyapi, vllm, lm_studio
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
            else:  # openai, openai_compatible, cloud providers
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
            detail="Failed to download STT models"
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
        "last_accessed_story_id": user_settings.last_accessed_story_id,
        "story_mode": story.story_mode or "dynamic",
    }

# Extraction Model Endpoints

@router.get("/extraction-model/presets")
async def get_extraction_model_presets():
    """Get predefined extraction model configurations"""
    from ..config import settings
    
    presets = {
        "lm_studio": {
            "name": "LM Studio",
            "description": "GUI-based, easy setup (recommended for beginners)",
            "url": settings._yaml_config.get('extraction_model', {}).get('url', 'http://localhost:1234/v1'),
            "api_key": "",
            "model_name": settings._yaml_config.get('extraction_model', {}).get('model_name', 'qwen2.5-3b-instruct')
        },
        "ollama": {
            "name": "Ollama",
            "description": "CLI-based, lightweight, auto-installs models",
            "url": "http://localhost:11434/v1",
            "api_key": "",
            "model_name": "qwen2.5:3b"
        },
        "llama_cpp": {
            "name": "llama.cpp Server",
            "description": "Minimal, direct model loading",
            "url": "http://localhost:8080/v1",
            "api_key": "",
            "model_name": settings._yaml_config.get('extraction_model', {}).get('model_name', 'qwen2.5-3b-instruct')
        },
        "custom": {
            "name": "Custom",
            "description": "User-specified endpoint",
            "url": "",
            "api_key": "",
            "model_name": ""
        }
    }
    
    return {
        "presets": presets,
        "recommended_models": settings.recommended_extraction_models,
        "message": "Available extraction model presets"
    }

class ExtractionModelTestRequest(BaseModel):
    url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    api_type: Optional[str] = None  # Provider type (e.g., "openai-compatible", "groq")

@router.post("/extraction-model/test")
async def test_extraction_model_connection(
    request: Optional[ExtractionModelTestRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test connection to extraction model endpoint"""
    from ..services.llm.extraction_service import ExtractionLLMService
    from ..config import settings

    # Use provided values or fall back to saved settings
    if request:
        url = request.url
        api_key = request.api_key
        model_name = request.model_name
        api_type = request.api_type
    else:
        url = None
        api_key = None
        model_name = None
        api_type = None

    if not model_name:
        user_settings = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()

        if not user_settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Extraction model not configured. Please configure settings first."
            )

        url = url or user_settings.extraction_model_url or settings.extraction_model_url
        api_key = api_key if api_key is not None else (user_settings.extraction_model_api_key or "")
        model_name = model_name or user_settings.extraction_model_name or "qwen2.5-3b-instruct"
        api_type = api_type or user_settings.extraction_model_api_type or "openai-compatible"

    api_type = api_type or "openai-compatible"

    # For cloud providers without a URL, resolve from registry
    if is_cloud_provider(api_type) and not url:
        cloud_base = get_provider_base_url(api_type)
        if not cloud_base:
            return {
                "success": True,
                "message": f"Cloud provider '{api_type}' uses LiteLLM native routing. Connection will be tested on first use.",
                "response_time_ms": 0,
                "url": None,
                "model": model_name
            }
        url = cloud_base

    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Extraction model URL not configured. Please provide a URL or select a cloud provider."
        )

    try:
        # Create extraction service
        extraction_service = ExtractionLLMService(
            url=url,
            model=model_name,
            api_key=api_key or "",
            temperature=0.3,
            max_tokens=1000,
            api_type=api_type
        )
        
        # Test connection
        success, message, response_time = await extraction_service.test_connection()
        
        return {
            "success": success,
            "message": message,
            "response_time_ms": round(response_time * 1000, 2),
            "url": url,
            "model": model_name
        }
        
    except Exception as e:
        logger.error(f"Failed to test extraction model connection: {e}")
        return {
            "success": False,
            "message": f"Connection test failed: {str(e)}",
            "response_time_ms": 0,
            "url": url,
            "model": model_name
        }

@router.post("/extraction-model/available-models")
async def get_extraction_available_models(
    request: Optional[ExtractionModelTestRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch available models from extraction endpoint"""
    import httpx
    from ..config import settings

    # Use provided values or fall back to saved settings
    if request:
        url = request.url
        api_key = request.api_key
        api_type = request.api_type
    else:
        url = None
        api_key = None
        api_type = None

    if not url and not (api_type and is_cloud_provider(api_type)):
        user_settings = db.query(UserSettings).filter(
            UserSettings.user_id == current_user.id
        ).first()

        if not user_settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Extraction model URL not configured. Please configure settings first."
            )

        url = user_settings.extraction_model_url or settings.extraction_model_url
        api_key = api_key if api_key is not None else (user_settings.extraction_model_api_key or "")
        api_type = api_type or user_settings.extraction_model_api_type or "openai-compatible"

    api_type = api_type or "openai-compatible"

    # For cloud providers, resolve URL from registry
    if is_cloud_provider(api_type):
        cloud_base = get_provider_base_url(api_type)
        if cloud_base:
            url = cloud_base
        else:
            # Provider without base_url — use litellm static list
            try:
                import litellm
                provider_models = litellm.models_by_provider.get(api_type, [])
                return {
                    "success": True,
                    "models": list(provider_models),
                    "message": f"Found {len(provider_models)} models for {api_type}"
                }
            except Exception:
                return {
                    "success": False,
                    "models": [],
                    "message": f"Could not fetch models for {api_type}"
                }

    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Extraction model URL not configured."
        )

    try:
        # Determine models URL based on provider type
        if is_cloud_provider(api_type):
            provider_info = PROVIDER_REGISTRY[api_type]
            models_url = f"{url.rstrip('/')}{provider_info.get('models_path', '/models')}"
        else:
            # Ensure URL ends with /v1 for OpenAI-compatible endpoints
            base_url = url.rstrip('/')
            if not base_url.endswith('/v1'):
                base_url = f"{base_url}/v1"
            models_url = f"{base_url}/models"

        # Configure headers
        headers = {
            'Content-Type': 'application/json'
        }
        if api_key and api_key.strip():
            headers['Authorization'] = f'Bearer {api_key}'
        else:
            # For local servers, use dummy key
            headers['Authorization'] = 'Bearer not-needed'
        
        # Make the request with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(models_url, headers=headers)
            
        if response.status_code == 200:
            data = response.json()
            models = []
            
            # Parse OpenAI-compatible response format
            # OpenAI format returns {"data": [{"id": "model_id", ...}, ...]}
            if 'data' in data:
                models = [model['id'] for model in data['data'] if 'id' in model]
            elif isinstance(data, list):
                # Some servers return array directly
                models = [model.get('id', model) if isinstance(model, dict) else model for model in data]
            
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
        logger.error(f"Failed to fetch extraction models: {e}")
        return {
            "success": False,
            "models": [],
            "message": f"Failed to fetch models: {str(e)}"
        }