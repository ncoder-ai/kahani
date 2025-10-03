from pydantic_settings import BaseSettings
from typing import List, Optional
import os

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
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:8080"]
    
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
    log_level: str = "INFO"
    log_file: str = "./logs/kahani.log"
    
    class Config:
        env_file = "/Users/nishant/apps/kahani/.env"
        case_sensitive = False

# Create global settings instance
settings = Settings()