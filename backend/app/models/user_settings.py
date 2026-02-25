from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import json
from ..database import Base
from ..config import settings

class UserSettings(Base):
    """User-specific configuration settings"""
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # LLM Generation Settings - NO DEFAULTS, must come from config.yaml
    llm_temperature = Column(Float, nullable=True)
    llm_top_p = Column(Float, nullable=True)
    llm_top_k = Column(Integer, nullable=True)
    llm_repetition_penalty = Column(Float, nullable=True)
    llm_max_tokens = Column(Integer, nullable=True)
    llm_timeout_total = Column(Float, nullable=True)
    
    # LLM API Configuration
    llm_api_url = Column(String(500), nullable=True)  # No default URL - user must provide
    llm_api_key = Column(String(500), nullable=True)
    llm_api_type = Column(String(100), nullable=True)
    llm_model_name = Column(String(200), nullable=True)
    
    # Text Completion Settings
    completion_mode = Column(String(20), nullable=True)
    text_completion_template = Column(Text, nullable=True)
    text_completion_preset = Column(String(100), nullable=True)
    
    # Reasoning/Thinking Settings
    reasoning_effort = Column(String(20), nullable=True)  # "disabled", "low", "medium", "high", or None (auto)
    show_thinking_content = Column(Boolean, nullable=True)  # Whether to display thinking text in UI
    thinking_model_type = Column(String(50), nullable=True)  # "none", "qwen3", "deepseek", etc. for local thinking models
    thinking_model_custom_pattern = Column(Text, nullable=True)  # Custom regex pattern for thinking tag removal
    thinking_enabled_generation = Column(Boolean, nullable=True)  # Per-task: allow thinking for story generation
    
    # Context Management Settings
    context_max_tokens = Column(Integer, nullable=True)
    context_keep_recent_scenes = Column(Integer, nullable=True)
    context_summary_threshold = Column(Integer, nullable=True)
    context_summary_threshold_tokens = Column(Integer, nullable=True)
    enable_context_summarization = Column(Boolean, nullable=True)
    auto_generate_summaries = Column(Boolean, nullable=True)
    character_extraction_threshold = Column(Integer, nullable=True)
    scene_batch_size = Column(Integer, nullable=True)  # Batch size for scene caching optimization
    
    # Semantic Memory Settings
    enable_semantic_memory = Column(Boolean, nullable=True)
    context_strategy = Column(String(20), nullable=True)
    semantic_search_top_k = Column(Integer, nullable=True)
    semantic_scenes_in_context = Column(Integer, nullable=True)
    semantic_context_weight = Column(Float, nullable=True)
    character_moments_in_context = Column(Integer, nullable=True)
    auto_extract_character_moments = Column(Boolean, nullable=True)
    auto_extract_plot_events = Column(Boolean, nullable=True)
    extraction_confidence_threshold = Column(Integer, nullable=True)
    plot_event_extraction_threshold = Column(Integer, nullable=True)
    fill_remaining_context = Column(Boolean, nullable=True)  # Fill remaining context with older scenes

    # Memory & Continuity Settings
    enable_working_memory = Column(Boolean, nullable=True)  # Track scene-to-scene focus and pending items
    enable_contradiction_detection = Column(Boolean, nullable=True)  # Detect continuity errors
    contradiction_severity_threshold = Column(String(20), nullable=True)  # "info", "warning", "error"
    enable_relationship_graph = Column(Boolean, nullable=True)  # Track character relationship arcs
    enable_contradiction_injection = Column(Boolean, nullable=True)  # Inject warnings into prompt
    enable_inline_contradiction_check = Column(Boolean, nullable=True)  # Run extraction + check every scene
    auto_regenerate_on_contradiction = Column(Boolean, nullable=True)  # Auto-regen once if contradiction found

    # Story Generation Preferences
    default_genre = Column(String(100), nullable=True)
    default_tone = Column(String(100), nullable=True)
    preferred_scene_length = Column(String(100), nullable=True)
    enable_auto_choices = Column(Boolean, nullable=True)
    choices_count = Column(Integer, nullable=True)
    alert_on_high_context = Column(Boolean, nullable=True)  # Alert user to create new chapter when context is high
    use_extraction_llm_for_summary = Column(Boolean, nullable=True)  # Use extraction LLM instead of main LLM for summaries
    separate_choice_generation = Column(Boolean, nullable=True)  # Generate choices in separate LLM call for higher quality
    use_cache_friendly_prompts = Column(Boolean, nullable=True)  # Preserve KV cache across LLM calls (extraction/summary)
    enable_chapter_plot_tracking = Column(Boolean, nullable=True)  # Track plot progress and guide LLM pacing
    default_plot_check_mode = Column(String(10), nullable=True)  # Default plot check mode for new stories: "1", "3", or "all"
    enable_streaming = Column(Boolean, nullable=True)  # Enable streaming generation (vs full response)

    # UI Preferences
    color_theme = Column(String(30), nullable=True)
    font_size = Column(String(20), nullable=True)
    show_token_info = Column(Boolean, nullable=True)
    show_context_info = Column(Boolean, nullable=True)
    enable_notifications = Column(Boolean, nullable=True)
    scene_display_format = Column(String(20), nullable=True)
    show_scene_titles = Column(Boolean, nullable=True)
    show_scene_images = Column(Boolean, nullable=True)  # Global toggle for scene images display
    scene_edit_mode = Column(String(20), nullable=True)
    auto_open_last_story = Column(Boolean, nullable=True)
    last_accessed_story_id = Column(Integer, nullable=True)
    
    # Export Settings
    default_export_format = Column(String(20), nullable=True)
    include_metadata = Column(Boolean, nullable=True)
    include_choices = Column(Boolean, nullable=True)
    
    # Character Assistant Settings
    enable_character_suggestions = Column(Boolean, nullable=True)
    character_importance_threshold = Column(Integer, nullable=True)
    character_mention_threshold = Column(Integer, nullable=True)
    
    # STT Settings
    stt_enabled = Column(Boolean, nullable=True)
    stt_model = Column(String(20), nullable=True)
    
    # Extraction Model Settings
    extraction_model_enabled = Column(Boolean, nullable=True)
    extraction_model_url = Column(String(500), nullable=True)
    extraction_model_api_key = Column(String(500), nullable=True)
    extraction_model_name = Column(String(200), nullable=True)
    extraction_model_temperature = Column(Float, nullable=True)
    extraction_model_max_tokens = Column(Integer, nullable=True)
    extraction_fallback_to_main = Column(Boolean, nullable=True)
    use_context_aware_extraction = Column(Boolean, nullable=True)  # Use main LLM with full context for extraction
    extraction_model_top_p = Column(Float, nullable=True)
    extraction_model_repetition_penalty = Column(Float, nullable=True)
    extraction_model_min_p = Column(Float, nullable=True)
    extraction_model_thinking_disable_method = Column(String(50), nullable=True)  # "none", "qwen3", "deepseek", "mistral", "gemini", "openai", "kimi", "custom"
    extraction_model_thinking_disable_custom = Column(Text, nullable=True)  # Custom tag pattern to strip
    extraction_model_thinking_enabled_extractions = Column(Boolean, nullable=True)  # Per-task: allow thinking for extractions
    extraction_model_thinking_enabled_memory = Column(Boolean, nullable=True)  # Per-task: allow thinking for memory/recall
    use_main_llm_for_plot_extraction = Column(Boolean, nullable=True)  # Use main LLM for plot event extraction (more accurate)
    use_main_llm_for_decomposition = Column(Boolean, nullable=True)  # Use main LLM for query decomposition (avoids extraction LLM contention)
    extraction_model_api_type = Column(String(100), nullable=True)  # Provider type for extraction model (e.g., "openai-compatible", "groq", "anthropic")

    # Extraction Engine-Specific Settings (mirrors main engine_settings pattern)
    extraction_engine_settings = Column(Text, nullable=True)  # JSON dict of per-engine extraction settings
    current_extraction_engine = Column(String(100), nullable=True)  # Currently selected extraction engine

    # Advanced Settings
    custom_system_prompt = Column(Text, nullable=True)
    enable_experimental_features = Column(Boolean, nullable=True)
    
    # Engine-Specific Settings
    engine_settings = Column(Text, nullable=True)
    current_engine = Column(String(100), nullable=True)
    
    # Advanced Sampler Settings (JSON blob)
    # Stores all TabbyAPI/OpenAI-compatible sampler configurations
    # Each sampler has an 'enabled' flag and a 'value' field
    sampler_settings = Column(Text, nullable=True)

    # Image Generation Settings
    image_gen_enabled = Column(Boolean, nullable=True)

    # ComfyUI Connection
    comfyui_server_url = Column(String(500), nullable=True)
    comfyui_api_key = Column(String(500), nullable=True)

    # Model Selection
    comfyui_checkpoint = Column(String(200), nullable=True)  # e.g., "sdxl_lightning_4step.safetensors"
    comfyui_model_type = Column(String(50), nullable=True)   # "sdxl", "flux", "sd15" - for workflow selection

    # Generation Defaults
    image_gen_width = Column(Integer, nullable=True)
    image_gen_height = Column(Integer, nullable=True)
    image_gen_steps = Column(Integer, nullable=True)
    image_gen_cfg_scale = Column(Float, nullable=True)
    image_gen_default_style = Column(String(50), nullable=True)  # "illustrated", "anime", etc.

    # LLM for Prompt Generation
    use_extraction_llm_for_image_prompts = Column(Boolean, nullable=True)  # True = extraction LLM, False = main LLM
    
    # Relationships
    user = relationship("User", back_populates="settings")
    
    def to_dict(self):
        """Convert settings to dictionary for API responses
        
        Returns defaults from config.yaml when fields are None for backward compatibility
        with existing empty UserSettings records.
        """
        user_defaults = settings.user_defaults
        llm_defaults = user_defaults.get("llm_settings", {})
        llm_api_defaults = user_defaults.get("llm_api", {})
        text_completion_defaults = user_defaults.get("text_completion", {})
        ctx_defaults = user_defaults.get("context_settings", {})
        gen_defaults = user_defaults.get("generation_preferences", {})
        ui_defaults = user_defaults.get("ui_preferences", {})
        exp_defaults = user_defaults.get("export_settings", {})
        char_assist_defaults = user_defaults.get("character_assistant_settings", {})
        stt_defaults = user_defaults.get("stt_settings", {})
        ext_model_defaults = user_defaults.get("extraction_model_settings", {})
        adv_defaults = user_defaults.get("advanced", {})
        
        return {
            "llm_settings": {
                "temperature": self.llm_temperature if self.llm_temperature is not None else llm_defaults.get("temperature", 0.7),
                "top_p": self.llm_top_p if self.llm_top_p is not None else llm_defaults.get("top_p", 1.0),
                "top_k": self.llm_top_k if self.llm_top_k is not None else llm_defaults.get("top_k", 50),
                "repetition_penalty": self.llm_repetition_penalty if self.llm_repetition_penalty is not None else llm_defaults.get("repetition_penalty", 1.1),
                "max_tokens": self.llm_max_tokens if self.llm_max_tokens is not None else llm_defaults.get("max_tokens", 2048),
                "timeout_total": self.llm_timeout_total if self.llm_timeout_total is not None else settings.llm_timeout_total,
                "api_url": self.llm_api_url or "",
                "api_key": self.llm_api_key or "",
                "api_type": self.llm_api_type if self.llm_api_type is not None else llm_api_defaults.get("api_type", "openai-compatible"),
                "model_name": self.llm_model_name or "",
                "completion_mode": self.completion_mode if self.completion_mode is not None else text_completion_defaults.get("mode", "chat"),
                "text_completion_template": self.text_completion_template or "",
                "text_completion_preset": self.text_completion_preset if self.text_completion_preset is not None else text_completion_defaults.get("preset", "llama3"),
                "reasoning_effort": self.reasoning_effort,  # None = auto, "disabled", "low", "medium", "high"
                "show_thinking_content": self.show_thinking_content if self.show_thinking_content is not None else True,
                "thinking_model_type": self.thinking_model_type if self.thinking_model_type is not None else None,
                "thinking_model_custom_pattern": self.thinking_model_custom_pattern or "",
                "thinking_enabled_generation": self.thinking_enabled_generation if self.thinking_enabled_generation is not None else False
            },
            "context_settings": {
                "max_tokens": self.context_max_tokens if self.context_max_tokens is not None else ctx_defaults.get("max_tokens", 4000),
                "keep_recent_scenes": self.context_keep_recent_scenes if self.context_keep_recent_scenes is not None else ctx_defaults.get("keep_recent_scenes", 3),
                "summary_threshold": self.context_summary_threshold if self.context_summary_threshold is not None else ctx_defaults.get("summary_threshold", 5),
                "summary_threshold_tokens": self.context_summary_threshold_tokens if self.context_summary_threshold_tokens is not None else ctx_defaults.get("summary_threshold_tokens", 8000),
                "enable_summarization": self.enable_context_summarization if self.enable_context_summarization is not None else ctx_defaults.get("enable_summarization", True),
                "character_extraction_threshold": self.character_extraction_threshold if self.character_extraction_threshold is not None else ctx_defaults.get("character_extraction_threshold", 5),
                "scene_batch_size": self.scene_batch_size if self.scene_batch_size is not None else ctx_defaults.get("scene_batch_size", 10),
                # Semantic Memory Settings
                "enable_semantic_memory": self.enable_semantic_memory if self.enable_semantic_memory is not None else ctx_defaults.get("enable_semantic_memory", True),
                "context_strategy": self.context_strategy if self.context_strategy is not None else ctx_defaults.get("context_strategy", "hybrid"),
                "semantic_search_top_k": self.semantic_search_top_k if self.semantic_search_top_k is not None else ctx_defaults.get("semantic_search_top_k", 5),
                "semantic_scenes_in_context": self.semantic_scenes_in_context if self.semantic_scenes_in_context is not None else ctx_defaults.get("semantic_scenes_in_context", 5),
                "semantic_context_weight": self.semantic_context_weight if self.semantic_context_weight is not None else ctx_defaults.get("semantic_context_weight", 0.4),
                "character_moments_in_context": self.character_moments_in_context if self.character_moments_in_context is not None else ctx_defaults.get("character_moments_in_context", 3),
                "auto_extract_character_moments": self.auto_extract_character_moments if self.auto_extract_character_moments is not None else ctx_defaults.get("auto_extract_character_moments", True),
                "auto_extract_plot_events": self.auto_extract_plot_events if self.auto_extract_plot_events is not None else ctx_defaults.get("auto_extract_plot_events", True),
                "extraction_confidence_threshold": self.extraction_confidence_threshold if self.extraction_confidence_threshold is not None else ctx_defaults.get("extraction_confidence_threshold", 70),
                "plot_event_extraction_threshold": self.plot_event_extraction_threshold if self.plot_event_extraction_threshold is not None else ctx_defaults.get("plot_event_extraction_threshold", 5),
                "fill_remaining_context": self.fill_remaining_context if self.fill_remaining_context is not None else ctx_defaults.get("fill_remaining_context", True),
                # Memory & Continuity Settings
                "enable_working_memory": self.enable_working_memory if self.enable_working_memory is not None else ctx_defaults.get("enable_working_memory", True),
                "enable_contradiction_detection": self.enable_contradiction_detection if self.enable_contradiction_detection is not None else ctx_defaults.get("enable_contradiction_detection", True),
                "contradiction_severity_threshold": self.contradiction_severity_threshold if self.contradiction_severity_threshold is not None else ctx_defaults.get("contradiction_severity_threshold", "info"),
                "enable_relationship_graph": self.enable_relationship_graph if self.enable_relationship_graph is not None else ctx_defaults.get("enable_relationship_graph", True),
                "enable_contradiction_injection": self.enable_contradiction_injection if self.enable_contradiction_injection is not None else ctx_defaults.get("enable_contradiction_injection", True),
                "enable_inline_contradiction_check": self.enable_inline_contradiction_check if self.enable_inline_contradiction_check is not None else ctx_defaults.get("enable_inline_contradiction_check", False),
                "auto_regenerate_on_contradiction": self.auto_regenerate_on_contradiction if self.auto_regenerate_on_contradiction is not None else ctx_defaults.get("auto_regenerate_on_contradiction", False)
            },
            "generation_preferences": {
                "default_genre": self.default_genre or "",
                "default_tone": self.default_tone or "",
                "scene_length": self.preferred_scene_length if self.preferred_scene_length is not None else gen_defaults.get("scene_length", "medium"),
                "auto_choices": self.enable_auto_choices if self.enable_auto_choices is not None else gen_defaults.get("auto_choices", True),
                "choices_count": self.choices_count if self.choices_count is not None else gen_defaults.get("choices_count", 4),
                "alert_on_high_context": self.alert_on_high_context if self.alert_on_high_context is not None else gen_defaults.get("alert_on_high_context", True),
                "use_extraction_llm_for_summary": self.use_extraction_llm_for_summary if self.use_extraction_llm_for_summary is not None else gen_defaults.get("use_extraction_llm_for_summary", False),
                "separate_choice_generation": self.separate_choice_generation if self.separate_choice_generation is not None else gen_defaults.get("separate_choice_generation", False),
                "use_cache_friendly_prompts": self.use_cache_friendly_prompts if self.use_cache_friendly_prompts is not None else gen_defaults.get("use_cache_friendly_prompts", True),
                "enable_chapter_plot_tracking": self.enable_chapter_plot_tracking if self.enable_chapter_plot_tracking is not None else gen_defaults.get("enable_chapter_plot_tracking", True),
                "default_plot_check_mode": self.default_plot_check_mode if self.default_plot_check_mode is not None else gen_defaults.get("default_plot_check_mode", "1"),
                "enable_streaming": self.enable_streaming if self.enable_streaming is not None else gen_defaults.get("enable_streaming", True)
            },
            "ui_preferences": {
                "color_theme": self.color_theme if self.color_theme is not None else ui_defaults.get("color_theme", "pure-dark"),
                "font_size": self.font_size if self.font_size is not None else ui_defaults.get("font_size", "medium"),
                "show_token_info": self.show_token_info if self.show_token_info is not None else ui_defaults.get("show_token_info", False),
                "show_context_info": self.show_context_info if self.show_context_info is not None else ui_defaults.get("show_context_info", False),
                "notifications": self.enable_notifications if self.enable_notifications is not None else ui_defaults.get("notifications", True),
                "scene_display_format": self.scene_display_format if self.scene_display_format is not None else ui_defaults.get("scene_display_format", "default"),
                "show_scene_titles": self.show_scene_titles if self.show_scene_titles is not None else ui_defaults.get("show_scene_titles", True),
                "show_scene_images": self.show_scene_images if self.show_scene_images is not None else ui_defaults.get("show_scene_images", True),
                "scene_edit_mode": self.scene_edit_mode if self.scene_edit_mode is not None else ui_defaults.get("scene_edit_mode", "textarea"),
                "auto_open_last_story": self.auto_open_last_story if self.auto_open_last_story is not None else ui_defaults.get("auto_open_last_story", False),
                "last_accessed_story_id": self.last_accessed_story_id
            },
            "export_settings": {
                "format": self.default_export_format if self.default_export_format is not None else exp_defaults.get("format", "markdown"),
                "include_metadata": self.include_metadata if self.include_metadata is not None else exp_defaults.get("include_metadata", True),
                "include_choices": self.include_choices if self.include_choices is not None else exp_defaults.get("include_choices", True)
            },
            "character_assistant_settings": {
                "enable_suggestions": self.enable_character_suggestions if self.enable_character_suggestions is not None else char_assist_defaults.get("enable_suggestions", True),
                "importance_threshold": self.character_importance_threshold if self.character_importance_threshold is not None else char_assist_defaults.get("importance_threshold", 70),
                "mention_threshold": self.character_mention_threshold if self.character_mention_threshold is not None else char_assist_defaults.get("mention_threshold", 5)
            },
            "stt_settings": {
                "enabled": self.stt_enabled if self.stt_enabled is not None else stt_defaults.get("enabled", True),
                "model": self.stt_model if self.stt_model is not None else stt_defaults.get("model", "small")
            },
            "extraction_model_settings": {
                "enabled": self.extraction_model_enabled if self.extraction_model_enabled is not None else ext_model_defaults.get("enabled", False),
                "url": self.extraction_model_url or ext_model_defaults.get("url", "http://localhost:1234/v1"),
                "api_key": self.extraction_model_api_key or "",
                "model_name": self.extraction_model_name or ext_model_defaults.get("model_name", "qwen2.5-3b-instruct"),
                "temperature": self.extraction_model_temperature if self.extraction_model_temperature is not None else ext_model_defaults.get("temperature", 0.3),
                "max_tokens": self.extraction_model_max_tokens if self.extraction_model_max_tokens is not None else ext_model_defaults.get("max_tokens", 1000),
                "fallback_to_main": self.extraction_fallback_to_main if self.extraction_fallback_to_main is not None else ext_model_defaults.get("fallback_to_main", True),
                "use_context_aware_extraction": self.use_context_aware_extraction if self.use_context_aware_extraction is not None else ext_model_defaults.get("use_context_aware_extraction", False),
                "top_p": self.extraction_model_top_p if self.extraction_model_top_p is not None else ext_model_defaults.get("top_p", 1.0),
                "repetition_penalty": self.extraction_model_repetition_penalty if self.extraction_model_repetition_penalty is not None else ext_model_defaults.get("repetition_penalty", 1.0),
                "min_p": self.extraction_model_min_p if self.extraction_model_min_p is not None else ext_model_defaults.get("min_p", 0.0),
                "thinking_disable_method": self.extraction_model_thinking_disable_method if self.extraction_model_thinking_disable_method is not None else ext_model_defaults.get("thinking_disable_method", "none"),
                "thinking_disable_custom": self.extraction_model_thinking_disable_custom or ext_model_defaults.get("thinking_disable_custom", ""),
                "thinking_enabled_extractions": self.extraction_model_thinking_enabled_extractions if self.extraction_model_thinking_enabled_extractions is not None else ext_model_defaults.get("thinking_enabled_extractions", False),
                "thinking_enabled_memory": self.extraction_model_thinking_enabled_memory if self.extraction_model_thinking_enabled_memory is not None else ext_model_defaults.get("thinking_enabled_memory", True),
                "enable_combined_extraction": True,  # Default: enabled, combines all extractions in one LLM call
                "use_main_llm_for_plot_extraction": self.use_main_llm_for_plot_extraction if self.use_main_llm_for_plot_extraction is not None else False,
                "use_main_llm_for_decomposition": self.use_main_llm_for_decomposition if self.use_main_llm_for_decomposition is not None else False,
                "api_type": self.extraction_model_api_type if self.extraction_model_api_type is not None else ext_model_defaults.get("api_type", "openai-compatible")
            },
            "extraction_engine_settings": self._parse_extraction_engine_settings(),
            "current_extraction_engine": self.current_extraction_engine or "",
            "advanced": {
                "custom_system_prompt": self.custom_system_prompt,
                "experimental_features": self.enable_experimental_features if self.enable_experimental_features is not None else adv_defaults.get("experimental_features", False)
            },
            "engine_settings": self._parse_engine_settings(),
            "current_engine": self.current_engine or "",
            "sampler_settings": self._get_merged_sampler_settings(),
            "image_generation_settings": self._get_image_generation_settings()
        }
    
    def _get_merged_sampler_settings(self):
        """Get sampler settings merged with defaults.

        User settings override defaults, but missing keys get default values.
        """
        defaults = self.get_default_sampler_settings()
        user_settings = self._parse_sampler_settings()

        # Merge user settings over defaults
        for key, value in user_settings.items():
            if key in defaults:
                defaults[key] = value

        return defaults

    def _get_image_generation_settings(self):
        """Get image generation settings merged with config defaults"""
        img_defaults = settings.user_defaults.get("image_generation_settings", {})

        return {
            "enabled": self.image_gen_enabled if self.image_gen_enabled is not None else img_defaults.get("enabled", False),
            "comfyui_server_url": self.comfyui_server_url or img_defaults.get("server_url", ""),
            "comfyui_api_key": self.comfyui_api_key or "",
            "comfyui_checkpoint": self.comfyui_checkpoint or img_defaults.get("checkpoint", ""),
            "comfyui_model_type": self.comfyui_model_type or img_defaults.get("model_type", "sdxl"),
            "width": self.image_gen_width if self.image_gen_width is not None else img_defaults.get("width", 1024),
            "height": self.image_gen_height if self.image_gen_height is not None else img_defaults.get("height", 1024),
            "steps": self.image_gen_steps if self.image_gen_steps is not None else img_defaults.get("steps", 4),
            "cfg_scale": self.image_gen_cfg_scale if self.image_gen_cfg_scale is not None else img_defaults.get("cfg_scale", 1.5),
            "default_style": self.image_gen_default_style if self.image_gen_default_style is not None else img_defaults.get("default_style", "illustrated"),
            "use_extraction_llm_for_prompts": self.use_extraction_llm_for_image_prompts if self.use_extraction_llm_for_image_prompts is not None else img_defaults.get("use_extraction_llm_for_prompts", False)
        }
    
    def _parse_engine_settings(self):
        """Parse engine_settings JSON string to dictionary"""
        try:
            return json.loads(self.engine_settings) if self.engine_settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _parse_extraction_engine_settings(self):
        """Parse extraction_engine_settings JSON string to dictionary"""
        try:
            return json.loads(self.extraction_engine_settings) if self.extraction_engine_settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def _parse_sampler_settings(self):
        """Parse sampler_settings JSON string to dictionary"""
        try:
            return json.loads(self.sampler_settings) if self.sampler_settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    @staticmethod
    def get_default_sampler_settings():
        """Get default sampler settings with all samplers disabled.
        
        Each sampler has:
        - enabled: bool - whether to include this sampler in API calls
        - value: the sampler value (type varies by sampler)
        
        Default values are set to common/safe defaults from TabbyAPI docs.
        """
        return {
            # Basic Sampling
            "temperature_last": {"enabled": False, "value": True},
            "smoothing_factor": {"enabled": False, "value": 0.0},
            "min_p": {"enabled": False, "value": 0.0},
            "top_a": {"enabled": False, "value": 0.0},
            
            # Token Control
            "min_tokens": {"enabled": False, "value": 0},
            "token_healing": {"enabled": False, "value": True},
            "add_bos_token": {"enabled": False, "value": True},
            "ban_eos_token": {"enabled": False, "value": False},
            
            # Penalties
            "frequency_penalty": {"enabled": False, "value": 0.0},
            "presence_penalty": {"enabled": False, "value": 0.0},
            "penalty_range": {"enabled": False, "value": 0},
            "repetition_decay": {"enabled": False, "value": 0},
            
            # Advanced Sampling
            "tfs": {"enabled": False, "value": 1.0},
            "typical": {"enabled": False, "value": 1.0},
            "skew": {"enabled": False, "value": 0.0},
            
            # XTC (Exclude Top Choices)
            "xtc_probability": {"enabled": False, "value": 0.0},
            "xtc_threshold": {"enabled": False, "value": 0.0},
            
            # DRY (Don't Repeat Yourself)
            "dry_multiplier": {"enabled": False, "value": 0.0},
            "dry_base": {"enabled": False, "value": 0.0},
            "dry_allowed_length": {"enabled": False, "value": 0},
            "dry_range": {"enabled": False, "value": 0},
            "dry_sequence_breakers": {"enabled": False, "value": ""},
            
            # Mirostat
            "mirostat_mode": {"enabled": False, "value": 0},
            "mirostat_tau": {"enabled": False, "value": 1.5},
            "mirostat_eta": {"enabled": False, "value": 0.3},
            
            # Dynamic Temperature
            "max_temp": {"enabled": False, "value": 1.0},
            "min_temp": {"enabled": False, "value": 1.0},
            "temp_exponent": {"enabled": False, "value": 1.0},
            
            # Constraints
            "banned_strings": {"enabled": False, "value": ""},
            "banned_tokens": {"enabled": False, "value": []},
            "allowed_tokens": {"enabled": False, "value": []},
            "stop": {"enabled": False, "value": ""},
            
            # Other
            "cfg_scale": {"enabled": False, "value": 1.0},
            "negative_prompt": {"enabled": False, "value": ""},
            "speculative_ngram": {"enabled": False, "value": True},
            
            # Multi-generation
            "n": {"enabled": False, "value": 1}  # Number of completions to generate (1-5)
        }
    
    def populate_from_defaults(self):
        """Populate UserSettings fields from config.yaml defaults
        
        This should be called when creating a new UserSettings instance
        to ensure all fields have proper default values instead of None.
        """
        user_defaults = settings.user_defaults
        
        # LLM Settings
        llm = user_defaults.get("llm_settings", {})
        if self.llm_temperature is None:
            self.llm_temperature = llm.get("temperature", 0.7)
        if self.llm_top_p is None:
            self.llm_top_p = llm.get("top_p", 1.0)
        if self.llm_top_k is None:
            self.llm_top_k = llm.get("top_k", 50)
        if self.llm_repetition_penalty is None:
            self.llm_repetition_penalty = llm.get("repetition_penalty", 1.1)
        if self.llm_max_tokens is None:
            self.llm_max_tokens = llm.get("max_tokens", 2048)
        
        # LLM API (from llm_api section)
        llm_api = user_defaults.get("llm_api", {})
        if self.llm_api_type is None:
            self.llm_api_type = llm_api.get("api_type", "openai-compatible")
        if self.llm_api_key is None:
            self.llm_api_key = llm_api.get("api_key", "")
        if self.llm_model_name is None:
            self.llm_model_name = llm_api.get("model_name", "")
        
        # Text Completion
        text_completion = user_defaults.get("text_completion", {})
        if self.completion_mode is None:
            self.completion_mode = text_completion.get("mode", "chat")
        if self.text_completion_preset is None:
            self.text_completion_preset = text_completion.get("preset", "llama3")
        
        # Reasoning/Thinking Settings
        reasoning = user_defaults.get("reasoning_settings", {})
        if self.reasoning_effort is None:
            self.reasoning_effort = reasoning.get("effort")  # None = auto
        if self.show_thinking_content is None:
            self.show_thinking_content = reasoning.get("show_thinking_content", True)
        if self.thinking_model_type is None:
            self.thinking_model_type = reasoning.get("thinking_model_type")
        if self.thinking_enabled_generation is None:
            self.thinking_enabled_generation = reasoning.get("thinking_enabled_generation", False)

        # Context Settings
        ctx = user_defaults.get("context_settings", {})
        if self.context_max_tokens is None:
            self.context_max_tokens = ctx.get("max_tokens", 4000)
        if self.context_keep_recent_scenes is None:
            self.context_keep_recent_scenes = ctx.get("keep_recent_scenes", 3)
        if self.context_summary_threshold is None:
            self.context_summary_threshold = ctx.get("summary_threshold", 5)
        if self.context_summary_threshold_tokens is None:
            self.context_summary_threshold_tokens = ctx.get("summary_threshold_tokens", 8000)
        if self.enable_context_summarization is None:
            self.enable_context_summarization = ctx.get("enable_summarization", True)
        if self.auto_generate_summaries is None:
            self.auto_generate_summaries = ctx.get("auto_generate_summaries", True)
        if self.character_extraction_threshold is None:
            self.character_extraction_threshold = ctx.get("character_extraction_threshold", 5)
        if self.scene_batch_size is None:
            self.scene_batch_size = ctx.get("scene_batch_size", 10)
        
        # Semantic Memory Settings
        if self.enable_semantic_memory is None:
            self.enable_semantic_memory = ctx.get("enable_semantic_memory", True)
        if self.context_strategy is None:
            self.context_strategy = ctx.get("context_strategy", "hybrid")
        if self.semantic_search_top_k is None:
            self.semantic_search_top_k = ctx.get("semantic_search_top_k", 5)
        if self.semantic_scenes_in_context is None:
            self.semantic_scenes_in_context = ctx.get("semantic_scenes_in_context", 5)
        if self.semantic_context_weight is None:
            self.semantic_context_weight = ctx.get("semantic_context_weight", 0.4)
        if self.character_moments_in_context is None:
            self.character_moments_in_context = ctx.get("character_moments_in_context", 3)
        if self.auto_extract_character_moments is None:
            self.auto_extract_character_moments = ctx.get("auto_extract_character_moments", True)
        if self.auto_extract_plot_events is None:
            self.auto_extract_plot_events = ctx.get("auto_extract_plot_events", True)
        if self.extraction_confidence_threshold is None:
            self.extraction_confidence_threshold = ctx.get("extraction_confidence_threshold", 70)
        if self.plot_event_extraction_threshold is None:
            self.plot_event_extraction_threshold = ctx.get("plot_event_extraction_threshold", 5)
        if self.fill_remaining_context is None:
            self.fill_remaining_context = ctx.get("fill_remaining_context", True)

        # Memory & Continuity Settings
        if self.enable_working_memory is None:
            self.enable_working_memory = ctx.get("enable_working_memory", True)
        if self.enable_contradiction_detection is None:
            self.enable_contradiction_detection = ctx.get("enable_contradiction_detection", True)
        if self.contradiction_severity_threshold is None:
            self.contradiction_severity_threshold = ctx.get("contradiction_severity_threshold", "info")
        if self.enable_relationship_graph is None:
            self.enable_relationship_graph = ctx.get("enable_relationship_graph", True)
        if self.enable_contradiction_injection is None:
            self.enable_contradiction_injection = ctx.get("enable_contradiction_injection", True)
        if self.enable_inline_contradiction_check is None:
            self.enable_inline_contradiction_check = ctx.get("enable_inline_contradiction_check", False)
        if self.auto_regenerate_on_contradiction is None:
            self.auto_regenerate_on_contradiction = ctx.get("auto_regenerate_on_contradiction", False)

        # Generation Preferences
        gen = user_defaults.get("generation_preferences", {})
        if self.default_genre is None:
            self.default_genre = gen.get("default_genre", "")
        if self.default_tone is None:
            self.default_tone = gen.get("default_tone", "")
        if self.preferred_scene_length is None:
            self.preferred_scene_length = gen.get("scene_length", "medium")
        if self.enable_auto_choices is None:
            self.enable_auto_choices = gen.get("auto_choices", True)
        if self.choices_count is None:
            self.choices_count = gen.get("choices_count", 4)
        if self.alert_on_high_context is None:
            self.alert_on_high_context = gen.get("alert_on_high_context", True)
        if self.use_extraction_llm_for_summary is None:
            self.use_extraction_llm_for_summary = gen.get("use_extraction_llm_for_summary", False)
        if self.separate_choice_generation is None:
            self.separate_choice_generation = gen.get("separate_choice_generation", False)
        if self.use_cache_friendly_prompts is None:
            self.use_cache_friendly_prompts = gen.get("use_cache_friendly_prompts", True)
        if self.enable_chapter_plot_tracking is None:
            self.enable_chapter_plot_tracking = gen.get("enable_chapter_plot_tracking", True)
        if self.default_plot_check_mode is None:
            self.default_plot_check_mode = gen.get("default_plot_check_mode", "1")
        if self.enable_streaming is None:
            self.enable_streaming = gen.get("enable_streaming", True)

        # UI Preferences
        ui = user_defaults.get("ui_preferences", {})
        if self.color_theme is None:
            self.color_theme = ui.get("color_theme", "pure-dark")
        if self.font_size is None:
            self.font_size = ui.get("font_size", "medium")
        if self.show_token_info is None:
            self.show_token_info = ui.get("show_token_info", False)
        if self.show_context_info is None:
            self.show_context_info = ui.get("show_context_info", False)
        if self.enable_notifications is None:
            self.enable_notifications = ui.get("notifications", True)
        if self.scene_display_format is None:
            self.scene_display_format = ui.get("scene_display_format", "default")
        if self.show_scene_titles is None:
            self.show_scene_titles = ui.get("show_scene_titles", True)
        if self.scene_edit_mode is None:
            self.scene_edit_mode = ui.get("scene_edit_mode", "textarea")
        if self.auto_open_last_story is None:
            self.auto_open_last_story = ui.get("auto_open_last_story", False)
        
        # Export Settings
        exp = user_defaults.get("export_settings", {})
        if self.default_export_format is None:
            self.default_export_format = exp.get("format", "markdown")
        if self.include_metadata is None:
            self.include_metadata = exp.get("include_metadata", True)
        if self.include_choices is None:
            self.include_choices = exp.get("include_choices", True)
        
        # Character Assistant Settings
        char_assist = user_defaults.get("character_assistant_settings", {})
        if self.enable_character_suggestions is None:
            self.enable_character_suggestions = char_assist.get("enable_suggestions", True)
        if self.character_importance_threshold is None:
            self.character_importance_threshold = char_assist.get("importance_threshold", 70)
        if self.character_mention_threshold is None:
            self.character_mention_threshold = char_assist.get("mention_threshold", 3)
        
        # STT Settings
        stt = user_defaults.get("stt_settings", {})
        if self.stt_enabled is None:
            self.stt_enabled = stt.get("enabled", True)
        if self.stt_model is None:
            self.stt_model = stt.get("model", "small")
        
        # Extraction Model Settings
        ext_model = user_defaults.get("extraction_model_settings", {})
        if self.extraction_model_enabled is None:
            self.extraction_model_enabled = ext_model.get("enabled", False)
        if self.extraction_model_url is None:
            self.extraction_model_url = ext_model.get("url", "http://localhost:1234/v1")
        if self.extraction_model_api_key is None:
            self.extraction_model_api_key = ext_model.get("api_key", "")
        if self.extraction_model_name is None:
            self.extraction_model_name = ext_model.get("model_name", "qwen2.5-3b-instruct")
        if self.extraction_model_temperature is None:
            self.extraction_model_temperature = ext_model.get("temperature", 0.3)
        if self.extraction_model_max_tokens is None:
            self.extraction_model_max_tokens = ext_model.get("max_tokens", 1000)
        if self.extraction_fallback_to_main is None:
            self.extraction_fallback_to_main = ext_model.get("fallback_to_main", True)
        if self.use_context_aware_extraction is None:
            self.use_context_aware_extraction = ext_model.get("use_context_aware_extraction", False)
        if self.extraction_model_top_p is None:
            self.extraction_model_top_p = ext_model.get("top_p", 1.0)
        if self.extraction_model_repetition_penalty is None:
            self.extraction_model_repetition_penalty = ext_model.get("repetition_penalty", 1.0)
        if self.extraction_model_min_p is None:
            self.extraction_model_min_p = ext_model.get("min_p", 0.0)
        if self.extraction_model_thinking_disable_method is None:
            self.extraction_model_thinking_disable_method = ext_model.get("thinking_disable_method", "none")
        if self.extraction_model_thinking_disable_custom is None:
            self.extraction_model_thinking_disable_custom = ext_model.get("thinking_disable_custom", "")
        if self.extraction_model_thinking_enabled_extractions is None:
            self.extraction_model_thinking_enabled_extractions = ext_model.get("thinking_enabled_extractions", False)
        if self.extraction_model_thinking_enabled_memory is None:
            self.extraction_model_thinking_enabled_memory = ext_model.get("thinking_enabled_memory", True)

        # Advanced Settings
        adv = user_defaults.get("advanced", {})
        if self.custom_system_prompt is None:
            self.custom_system_prompt = adv.get("custom_system_prompt")
        if self.enable_experimental_features is None:
            self.enable_experimental_features = adv.get("experimental_features", False)

        # Image Generation Settings
        img_gen = user_defaults.get("image_generation_settings", {})
        if self.image_gen_enabled is None:
            self.image_gen_enabled = img_gen.get("enabled", False)
        if self.comfyui_server_url is None:
            self.comfyui_server_url = img_gen.get("server_url", "")
        if self.comfyui_api_key is None:
            self.comfyui_api_key = img_gen.get("api_key", "")
        if self.comfyui_checkpoint is None:
            self.comfyui_checkpoint = img_gen.get("checkpoint", "")
        if self.comfyui_model_type is None:
            self.comfyui_model_type = img_gen.get("model_type", "sdxl")
        if self.image_gen_width is None:
            self.image_gen_width = img_gen.get("width", 1024)
        if self.image_gen_height is None:
            self.image_gen_height = img_gen.get("height", 1024)
        if self.image_gen_steps is None:
            self.image_gen_steps = img_gen.get("steps", 4)
        if self.image_gen_cfg_scale is None:
            self.image_gen_cfg_scale = img_gen.get("cfg_scale", 1.5)
        if self.image_gen_default_style is None:
            self.image_gen_default_style = img_gen.get("default_style", "illustrated")
        if self.use_extraction_llm_for_image_prompts is None:
            self.use_extraction_llm_for_image_prompts = img_gen.get("use_extraction_llm_for_prompts", False)
    
    @classmethod
    def get_defaults(cls):
        """Get default settings as dictionary from config.yaml"""
        user_defaults = settings.user_defaults
        
        # Map config.yaml structure to API response structure
        return {
            "llm_settings": user_defaults.get("llm_settings", {}),
            "context_settings": user_defaults.get("context_settings", {}),
            "generation_preferences": user_defaults.get("generation_preferences", {}),
            "ui_preferences": user_defaults.get("ui_preferences", {}),
            "export_settings": user_defaults.get("export_settings", {}),
            "character_assistant_settings": user_defaults.get("character_assistant_settings", {}),
            "advanced": user_defaults.get("advanced", {}),
            "extraction_model_settings": user_defaults.get("extraction_model_settings", {}),
            "sampler_settings": cls.get_default_sampler_settings(),
            "image_generation_settings": user_defaults.get("image_generation_settings", {})
        }