from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base

class UserSettings(Base):
    """User-specific configuration settings"""
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # LLM Generation Settings
    llm_temperature = Column(Float, default=0.7)  # 0.0 - 2.0
    llm_top_p = Column(Float, default=1.0)  # 0.0 - 1.0
    llm_top_k = Column(Integer, default=50)  # 1 - 100
    llm_repetition_penalty = Column(Float, default=1.1)  # 1.0 - 2.0
    llm_max_tokens = Column(Integer, default=2048)  # 100 - 4096
    
    # LLM API Configuration
    llm_api_url = Column(String(500), default=None)  # No default URL - user must provide
    llm_api_key = Column(String(500), default="")
    llm_api_type = Column(String(50), default="openai-compatible")  # openai, openai-compatible, koboldcpp, ollama
    llm_model_name = Column(String(200), default="")
    
    # Context Management Settings
    context_max_tokens = Column(Integer, default=4000)  # 1000 - 1M
    context_keep_recent_scenes = Column(Integer, default=3)  # 1 - 10
    context_summary_threshold = Column(Integer, default=5)  # 3 - 20 scenes (auto-generate chapter summary every N scenes)
    context_summary_threshold_tokens = Column(Integer, default=8000)  # 1000 - 50000 tokens
    enable_context_summarization = Column(Boolean, default=True)
    auto_generate_summaries = Column(Boolean, default=True)  # Auto-generate summaries based on threshold
    
    # Semantic Memory Settings
    enable_semantic_memory = Column(Boolean, default=True)  # Per-user semantic memory toggle
    context_strategy = Column(String(20), default="hybrid")  # "linear" or "hybrid"
    semantic_search_top_k = Column(Integer, default=5)  # Number of semantically similar scenes to retrieve
    semantic_scenes_in_context = Column(Integer, default=5)  # Max semantic scenes to include in context
    semantic_context_weight = Column(Float, default=0.4)  # Weight for semantic vs recent scenes (0.0-1.0)
    character_moments_in_context = Column(Integer, default=3)  # Max character moments to include
    auto_extract_character_moments = Column(Boolean, default=True)  # Auto-extract character moments from scenes
    auto_extract_plot_events = Column(Boolean, default=True)  # Auto-extract plot events from scenes
    extraction_confidence_threshold = Column(Integer, default=70)  # Minimum confidence for auto-extraction (0-100)
    
    # Story Generation Preferences
    default_genre = Column(String(100), default="")
    default_tone = Column(String(100), default="")
    preferred_scene_length = Column(String(50), default="medium")  # short, medium, long
    enable_auto_choices = Column(Boolean, default=True)
    choices_count = Column(Integer, default=4)  # 2 - 6
    
    # UI Preferences
    theme = Column(String(20), default="dark")  # dark, light, auto
    font_size = Column(String(20), default="medium")  # small, medium, large
    show_token_info = Column(Boolean, default=False)
    show_context_info = Column(Boolean, default=False)
    enable_notifications = Column(Boolean, default=True)
    scene_display_format = Column(String(20), default="default")  # default, bubble, card, minimal
    show_scene_titles = Column(Boolean, default=True)
    auto_open_last_story = Column(Boolean, default=False)  # Auto-redirect to last story on login
    last_accessed_story_id = Column(Integer, default=None)  # Last story the user worked on
    
    # Export Settings
    default_export_format = Column(String(20), default="markdown")  # markdown, pdf, txt
    include_metadata = Column(Boolean, default=True)
    include_choices = Column(Boolean, default=True)
    
    # Advanced Settings
    custom_system_prompt = Column(Text, default="")
    enable_experimental_features = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="settings")
    
    def to_dict(self):
        """Convert settings to dictionary for API responses"""
        # Get user permissions from the related User model
        user_permissions = {}
        if self.user:
            user_permissions = {
                "allow_nsfw": self.user.allow_nsfw,
                "can_change_llm_provider": self.user.can_change_llm_provider,
                "is_admin": self.user.is_admin
            }
        
        return {
            "llm_settings": {
                "temperature": self.llm_temperature,
                "top_p": self.llm_top_p,
                "top_k": self.llm_top_k,
                "repetition_penalty": self.llm_repetition_penalty,
                "max_tokens": self.llm_max_tokens,
                "api_url": self.llm_api_url,
                "api_key": self.llm_api_key,
                "api_type": self.llm_api_type,
                "model_name": self.llm_model_name
            },
            "context_settings": {
                "max_tokens": self.context_max_tokens,
                "keep_recent_scenes": self.context_keep_recent_scenes,
                "summary_threshold": self.context_summary_threshold,
                "summary_threshold_tokens": self.context_summary_threshold_tokens,
                "enable_summarization": self.enable_context_summarization,
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
                "default_genre": self.default_genre,
                "default_tone": self.default_tone,
                "scene_length": self.preferred_scene_length,
                "auto_choices": self.enable_auto_choices,
                "choices_count": self.choices_count
            },
            "ui_preferences": {
                "theme": self.theme,
                "font_size": self.font_size,
                "show_token_info": self.show_token_info,
                "show_context_info": self.show_context_info,
                "notifications": self.enable_notifications,
                "scene_display_format": self.scene_display_format,
                "show_scene_titles": self.show_scene_titles,
                "auto_open_last_story": self.auto_open_last_story,
                "last_accessed_story_id": self.last_accessed_story_id
            },
            "export_settings": {
                "format": self.default_export_format,
                "include_metadata": self.include_metadata,
                "include_choices": self.include_choices
            },
            "advanced": {
                "custom_system_prompt": self.custom_system_prompt,
                "experimental_features": self.enable_experimental_features
            },
            # Include user permissions
            **user_permissions
        }
    
    @classmethod
    def get_defaults(cls):
        """Get default settings as dictionary"""
        return {
            "llm_settings": {
                "temperature": 0.7,
                "top_p": 1.0,
                "top_k": 50,
                "repetition_penalty": 1.1,
                "max_tokens": 2048
            },
            "context_settings": {
                "max_tokens": 4000,
                "keep_recent_scenes": 3,
                "summary_threshold": 5,
                "summary_threshold_tokens": 8000,
                "enable_summarization": True,
                # Semantic Memory Settings
                "enable_semantic_memory": True,
                "context_strategy": "hybrid",
                "semantic_search_top_k": 5,
                "semantic_scenes_in_context": 5,
                "semantic_context_weight": 0.4,
                "character_moments_in_context": 3,
                "auto_extract_character_moments": True,
                "auto_extract_plot_events": True,
                "extraction_confidence_threshold": 70
            },
            "generation_preferences": {
                "default_genre": "",
                "default_tone": "",
                "scene_length": "medium",
                "auto_choices": True,
                "choices_count": 4
            },
            "ui_preferences": {
                "theme": "dark",
                "font_size": "medium",
                "show_token_info": False,
                "show_context_info": False,
                "notifications": True,
                "scene_display_format": "default",
                "show_scene_titles": False,
                "auto_open_last_story": False
            },
            "export_settings": {
                "format": "markdown",
                "include_metadata": True,
                "include_choices": True
            },
            "advanced": {
                "custom_system_prompt": "",
                "experimental_features": False
            }
        }