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
    access_token_expire_minutes: int = 120  # 2 hours for better user experience
    
    # Admin user
    admin_email: str = "admin@localhost"
    admin_password: str = "changeme123"
    
    # LLM Configuration
    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: str = "not-needed-for-local"
    llm_model: str = "local-model"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7
    
    # Context Management Configuration
    context_max_tokens: int = 4000  # Maximum tokens to send to LLM
    context_keep_recent_scenes: int = 3  # Always keep this many recent scenes
    context_summary_threshold: int = 5  # Summarize when story has more than this many scenes
    context_summary_threshold_tokens: int = 10000  # Summarize when total tokens exceed this threshold
    context_token_buffer: float = 0.9  # Use 90% of max tokens as safety margin
    
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
    log_level: str = "DEBUG"  # Changed to DEBUG to see semantic operations
    log_file: str = "./logs/kahani.log"
    
    class Config:
        env_file = "../.env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env that aren't in the model

# Create global settings instance
settings = Settings()