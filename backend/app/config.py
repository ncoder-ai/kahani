from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import field_validator
import os
import json

class Settings(BaseSettings):
    # Application
    app_name: str = "Kahani"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # Database
    database_url: str = "sqlite:///./data/kahani.db"
    
    # Security
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120  # 2 hours for normal sessions
    refresh_token_expire_days: int = 30  # 30 days for remember me sessions
    
    # Admin user
    admin_email: str = "admin@localhost"
    admin_password: str = "changeme123"
    
    # Context Management Configuration
    context_max_tokens: int = 4000  # Maximum tokens to send to LLM
    context_keep_recent_scenes: int = 3  # Always keep this many recent scenes
    context_summary_threshold: int = 5  # Summarize when story has more than this many scenes
    context_summary_threshold_tokens: int = 10000  # Summarize when total tokens exceed this threshold
    context_token_buffer: float = 0.9  # Use 90% of max tokens as safety margin
    DEFAULT_CHARACTER_EXTRACTION_THRESHOLD: int = 5  # Default threshold for character/NPC extraction (scenes since last extraction)
    
    # Semantic Memory Configuration
    enable_semantic_memory: bool = True  # Enable semantic search and vector embeddings
    semantic_db_path: str = "./data/chromadb"  # ChromaDB persistence directory
    semantic_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"  # Embedding model
    semantic_search_top_k: int = 5  # Number of semantically similar scenes to retrieve
    semantic_context_weight: float = 0.4  # Weight for semantic scenes vs recent scenes (0-1)
    
    # Context Assembly Strategy
    context_strategy: str = "hybrid"  # "linear" (old) or "hybrid" (semantic + linear)
    semantic_scenes_in_context: int = 5  # Number of semantically relevant scenes to include
    character_moments_in_context: int = 3  # Number of character moments to include
    
    # Auto-extraction Settings
    auto_extract_character_moments: bool = True  # Automatically extract character moments
    auto_extract_plot_events: bool = True  # Automatically extract plot events
    extraction_confidence_threshold: int = 70  # Minimum confidence (0-100) for auto-extraction
    
    # Extraction Model Configuration
    extraction_model_enabled: bool = False  # Enable local extraction model by default
    extraction_model_url: str = "http://localhost:1234/v1"  # LM Studio default, works with any OpenAI-compatible endpoint
    recommended_extraction_models: List[str] = ["qwen2.5-3b-instruct", "ministral-3b-instruct", "phi-3-mini"]  # Recommended small uncensored models
    
    # NPC Tracking Configuration
    npc_tracking_enabled: bool = True  # Enable automatic NPC tracking from scenes
    npc_importance_threshold: float = 1.0  # Importance score threshold for including NPCs in context
    npc_auto_extract_profile: bool = True  # Automatically extract full character profile when threshold crossed
    npc_prompt_user: bool = False  # Prompt user to add NPCs as explicit characters (can enable later)
    
    # CORS - Will be auto-configured based on deployment environment
    cors_origins: str = "*"  # Default, will be overridden by network config
    
    @field_validator('cors_origins', mode='after')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from environment variable"""
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            try:
                # Try to parse as JSON array
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                # If not JSON, treat as comma-separated string
                return [origin.strip() for origin in v.split(',')]
        return v
    
    # File storage
    data_dir: str = "./data"
    export_dir: str = "./exports"
    max_story_size_mb: int = 10
    max_users: int = 100
    
    # Features
    enable_registration: bool = True
    enable_story_sharing: bool = True
    enable_public_stories: bool = False
    
    # Logging
    log_level: str = "WARNING"  # Set to WARNING to reduce logging noise (only warnings and errors)
    log_file: str = "./logs/kahani.log"
    
    # STT Configuration
    stt_model: str = "small"  # Options: tiny, base, small, medium, large-v2
    # Model comparison:
    # - small: Good quality, fast, recommended (iPhone-quality)
    # - medium: Very good quality, slower
    # - large-v2: Best quality, slowest
    stt_device: str = "auto"  # auto (try GPU, fallback CPU), cuda, or cpu
    stt_compute_type: str = "int8"  # int8, int8_float16, float16 for GPU; int8 for CPU
    stt_language: str = "en"  # Language code
    
    # Advanced STT Settings
    stt_use_silero_vad: bool = True  # Use Silero VAD (better than webrtcvad)
    stt_vad_threshold: float = 0.5  # Silero VAD threshold (0.0-1.0, higher = more aggressive)
    stt_min_speech_duration_ms: int = 250  # Minimum speech duration to process
    stt_min_silence_duration_ms: int = 1000  # 1 second silence to mark end of sentence (prevents fragmentation)
    stt_max_speech_duration_s: int = 60  # 60 seconds to allow longer speeches without cuts
    stt_speech_pad_ms: int = 300  # Padding around detected speech
    
    class Config:
        env_file = "../.env"
        case_sensitive = False
        extra = "ignore"  # Ignore frontend-specific and other extra env vars

# Create global settings instance
settings = Settings()