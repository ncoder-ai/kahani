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
    
    # LLM API Configuration
    llm_api_url = Column(String(500), nullable=True)  # No default URL - user must provide
    llm_api_key = Column(String(500), nullable=True)
    llm_api_type = Column(String(50), nullable=True)
    llm_model_name = Column(String(200), nullable=True)
    
    # Text Completion Settings
    completion_mode = Column(String(20), nullable=True)
    text_completion_template = Column(Text, nullable=True)
    text_completion_preset = Column(String(50), nullable=True)
    
    # Context Management Settings
    context_max_tokens = Column(Integer, nullable=True)
    context_keep_recent_scenes = Column(Integer, nullable=True)
    context_summary_threshold = Column(Integer, nullable=True)
    context_summary_threshold_tokens = Column(Integer, nullable=True)
    enable_context_summarization = Column(Boolean, nullable=True)
    auto_generate_summaries = Column(Boolean, nullable=True)
    character_extraction_threshold = Column(Integer, nullable=True)
    
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
    
    # Story Generation Preferences
    default_genre = Column(String(100), nullable=True)
    default_tone = Column(String(100), nullable=True)
    preferred_scene_length = Column(String(50), nullable=True)
    enable_auto_choices = Column(Boolean, nullable=True)
    choices_count = Column(Integer, nullable=True)
    
    # UI Preferences
    color_theme = Column(String(30), nullable=True)
    font_size = Column(String(20), nullable=True)
    show_token_info = Column(Boolean, nullable=True)
    show_context_info = Column(Boolean, nullable=True)
    enable_notifications = Column(Boolean, nullable=True)
    scene_display_format = Column(String(20), nullable=True)
    show_scene_titles = Column(Boolean, nullable=True)
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
    
    # Advanced Settings
    custom_system_prompt = Column(Text, nullable=True)
    enable_experimental_features = Column(Boolean, nullable=True)
    
    # Engine-Specific Settings
    engine_settings = Column(Text, nullable=True)
    current_engine = Column(String(50), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="settings")
    
    def to_dict(self):
        """Convert settings to dictionary for API responses"""
        return {
            "llm_settings": {
                "temperature": self.llm_temperature,
                "top_p": self.llm_top_p,
                "top_k": self.llm_top_k,
                "repetition_penalty": self.llm_repetition_penalty,
                "max_tokens": self.llm_max_tokens,
                "api_url": self.llm_api_url or "",
                "api_key": self.llm_api_key or "",
                "api_type": self.llm_api_type or "",
                "model_name": self.llm_model_name or "",
                "completion_mode": self.completion_mode or "chat",
                "text_completion_template": self.text_completion_template or "",
                "text_completion_preset": self.text_completion_preset or "llama3"
            },
            "context_settings": {
                "max_tokens": self.context_max_tokens,
                "keep_recent_scenes": self.context_keep_recent_scenes,
                "summary_threshold": self.context_summary_threshold,
                "summary_threshold_tokens": self.context_summary_threshold_tokens,
                "enable_summarization": self.enable_context_summarization,
                "character_extraction_threshold": self.character_extraction_threshold,
                # Semantic Memory Settings
                "enable_semantic_memory": self.enable_semantic_memory,
                "context_strategy": self.context_strategy,
                "semantic_search_top_k": self.semantic_search_top_k,
                "semantic_scenes_in_context": self.semantic_scenes_in_context,
                "semantic_context_weight": self.semantic_context_weight,
                "character_moments_in_context": self.character_moments_in_context,
                "auto_extract_character_moments": self.auto_extract_character_moments,
                "auto_extract_plot_events": self.auto_extract_plot_events,
                "extraction_confidence_threshold": self.extraction_confidence_threshold
            },
            "generation_preferences": {
                "default_genre": self.default_genre or "",
                "default_tone": self.default_tone or "",
                "scene_length": self.preferred_scene_length,
                "auto_choices": self.enable_auto_choices,
                "choices_count": self.choices_count
            },
            "ui_preferences": {
                "color_theme": self.color_theme,
                "font_size": self.font_size,
                "show_token_info": self.show_token_info,
                "show_context_info": self.show_context_info,
                "notifications": self.enable_notifications,
                "scene_display_format": self.scene_display_format,
                "show_scene_titles": self.show_scene_titles,
                "scene_edit_mode": self.scene_edit_mode,
                "auto_open_last_story": self.auto_open_last_story,
                "last_accessed_story_id": self.last_accessed_story_id
            },
            "export_settings": {
                "format": self.default_export_format,
                "include_metadata": self.include_metadata,
                "include_choices": self.include_choices
            },
            "character_assistant_settings": {
                "enable_suggestions": self.enable_character_suggestions,
                "importance_threshold": self.character_importance_threshold,
                "mention_threshold": self.character_mention_threshold
            },
            "stt_settings": {
                "enabled": self.stt_enabled if self.stt_enabled is not None else True,
                "model": self.stt_model if self.stt_model is not None else "small"
            },
            "extraction_model_settings": {
                "enabled": self.extraction_model_enabled if self.extraction_model_enabled is not None else False,
                "url": self.extraction_model_url or "http://localhost:1234/v1",
                "api_key": self.extraction_model_api_key or "",
                "model_name": self.extraction_model_name or "qwen2.5-3b-instruct",
                "temperature": self.extraction_model_temperature if self.extraction_model_temperature is not None else 0.3,
                "max_tokens": self.extraction_model_max_tokens if self.extraction_model_max_tokens is not None else 1000,
                "fallback_to_main": self.extraction_fallback_to_main if self.extraction_fallback_to_main is not None else True,
                "enable_combined_extraction": True  # Default: enabled, combines all extractions in one LLM call
            },
            "advanced": {
                "custom_system_prompt": self.custom_system_prompt,
                "experimental_features": self.enable_experimental_features
            },
            "engine_settings": self._parse_engine_settings(),
            "current_engine": self.current_engine or ""
        }
    
    def _parse_engine_settings(self):
        """Parse engine_settings JSON string to dictionary"""
        try:
            return json.loads(self.engine_settings) if self.engine_settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
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
            "extraction_model_settings": user_defaults.get("extraction_model_settings", {})
        }