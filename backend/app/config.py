from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import field_validator
import os
import json
import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def load_yaml_config() -> dict:
    """Load configuration from config.yaml file"""
    # Try multiple locations for config.yaml:
    # 1. Project root (two levels up from backend/app/) - for local development
    # 2. /app/config.yaml - for Docker (mounted from project root)
    # 3. Current directory - fallback
    
    backend_dir = Path(__file__).parent.parent.parent
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
        raise FileNotFoundError(
            f"config.yaml not found in any of these locations: {locations_str}. "
            "Please create config.yaml in the project root with all required settings."
        )
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if config is None:
            raise ValueError("config.yaml is empty")
        logger.info(f"Loaded configuration from {config_file}")
        return config
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing config.yaml: {e}")
    except Exception as e:
        raise ValueError(f"Error loading config.yaml: {e}")

def flatten_yaml_config(yaml_config: dict) -> dict:
    """Flatten nested YAML structure to match Settings class attributes"""
    flattened = {}
    
    # Application settings
    app = yaml_config.get('application', {})
    flattened['app_name'] = app.get('app_name')
    flattened['app_version'] = app.get('app_version')
    flattened['debug'] = app.get('debug')
    
    # Database
    # DATABASE_URL environment variable takes priority over YAML config
    # This allows easy switching between SQLite and PostgreSQL via environment
    db = yaml_config.get('database', {})
    env_database_url = os.environ.get('DATABASE_URL')
    if env_database_url:
        flattened['database_url'] = env_database_url
        logger.info(f"Using DATABASE_URL from environment: {env_database_url.split('@')[0]}@...")  # Log without password
    else:
        flattened['database_url'] = db.get('database_url')
    
    # Database connection pool settings (PostgreSQL only)
    flattened['db_pool_size'] = db.get('pool_size', 20)
    flattened['db_max_overflow'] = db.get('max_overflow', 40)
    flattened['db_pool_timeout'] = db.get('pool_timeout', 30)
    
    # Security
    security = yaml_config.get('security', {})
    flattened['jwt_algorithm'] = security.get('jwt_algorithm')
    flattened['access_token_expire_minutes'] = security.get('access_token_expire_minutes')
    flattened['refresh_token_expire_days'] = security.get('refresh_token_expire_days')
    # jwt_secret_key and secret_key are NOT loaded from YAML - must come from environment variables
    
    # Note: Admin credentials removed - first user to register becomes admin automatically
    
    # Context
    context = yaml_config.get('context', {})
    flattened['context_max_tokens'] = context.get('max_tokens')
    flattened['context_keep_recent_scenes'] = context.get('keep_recent_scenes')
    flattened['context_summary_threshold'] = context.get('summary_threshold')
    flattened['context_summary_threshold_tokens'] = context.get('summary_threshold_tokens')
    flattened['context_token_buffer'] = context.get('token_buffer')
    flattened['DEFAULT_CHARACTER_EXTRACTION_THRESHOLD'] = context.get('default_character_extraction_threshold')
    
    # Semantic Memory
    semantic = yaml_config.get('semantic_memory', {})
    flattened['enable_semantic_memory'] = semantic.get('enabled')
    flattened['semantic_embedding_model'] = semantic.get('embedding_model')
    flattened['semantic_search_top_k'] = semantic.get('search_top_k')
    flattened['semantic_context_weight'] = semantic.get('context_weight')
    flattened['semantic_enable_reranking'] = semantic.get('enable_reranking', True)
    flattened['semantic_reranker_model'] = semantic.get('reranker_model')

    # Context Strategy
    strategy = yaml_config.get('context_strategy', {})
    flattened['context_strategy'] = strategy.get('strategy')
    flattened['semantic_scenes_in_context'] = strategy.get('semantic_scenes_in_context')
    flattened['character_moments_in_context'] = strategy.get('character_moments_in_context')
    flattened['semantic_min_similarity'] = strategy.get('semantic_min_similarity')
    flattened['location_recency_window'] = strategy.get('location_recency_window')
    
    # Extraction
    extraction = yaml_config.get('extraction', {})
    flattened['auto_extract_character_moments'] = extraction.get('auto_extract_character_moments')
    flattened['auto_extract_plot_events'] = extraction.get('auto_extract_plot_events')
    flattened['extraction_confidence_threshold'] = extraction.get('confidence_threshold')
    
    # Extraction Model
    ext_model = yaml_config.get('extraction_model', {})
    flattened['extraction_model_enabled'] = ext_model.get('enabled')
    flattened['extraction_model_url'] = ext_model.get('url')
    flattened['recommended_extraction_models'] = ext_model.get('recommended_models', [])
    
    # NPC Tracking
    npc = yaml_config.get('npc_tracking', {})
    flattened['npc_tracking_enabled'] = npc.get('enabled')
    flattened['npc_importance_threshold'] = npc.get('importance_threshold')
    flattened['npc_auto_extract_profile'] = npc.get('auto_extract_profile')
    flattened['npc_prompt_user'] = npc.get('prompt_user')
    flattened['npc_active_recency_window'] = npc.get('active_recency_window', 5)
    flattened['npc_inactive_recency_window'] = npc.get('inactive_recency_window', 15)
    flattened['npc_use_chapter_awareness'] = npc.get('use_chapter_awareness', True)
    
    # CORS
    cors = yaml_config.get('cors', {})
    flattened['cors_origins'] = cors.get('origins')
    
    # Storage
    storage = yaml_config.get('storage', {})
    flattened['data_dir'] = storage.get('data_dir')
    flattened['export_dir'] = storage.get('export_dir')
    flattened['logs_dir'] = storage.get('logs_dir')
    flattened['max_story_size_mb'] = storage.get('max_story_size_mb')
    flattened['max_users'] = storage.get('max_users')
    
    # Features
    features = yaml_config.get('features', {})
    flattened['enable_registration'] = features.get('enable_registration')
    flattened['enable_story_sharing'] = features.get('enable_story_sharing')
    flattened['enable_public_stories'] = features.get('enable_public_stories')
    
    # Logging
    logging_config = yaml_config.get('logging', {})
    flattened['log_level'] = logging_config.get('log_level')
    flattened['log_file'] = logging_config.get('log_file')
    
    # STT
    stt = yaml_config.get('stt', {})
    flattened['stt_model'] = stt.get('model')
    flattened['stt_device'] = stt.get('device')
    flattened['stt_compute_type'] = stt.get('compute_type')
    flattened['stt_language'] = stt.get('language')
    flattened['stt_use_silero_vad'] = stt.get('use_silero_vad')
    flattened['stt_vad_threshold'] = stt.get('vad_threshold')
    flattened['stt_min_speech_duration_ms'] = stt.get('min_speech_duration_ms')
    flattened['stt_min_silence_duration_ms'] = stt.get('min_silence_duration_ms')
    flattened['stt_max_speech_duration_s'] = stt.get('max_speech_duration_s')
    flattened['stt_speech_pad_ms'] = stt.get('speech_pad_ms')
    
    # Debug
    debug = yaml_config.get('debug', {})
    flattened['prompt_debug'] = debug.get('prompt_debug')
    
    # Server
    server = yaml_config.get('server', {})
    backend_server = server.get('backend', {})
    frontend_server = server.get('frontend', {})
    flattened['backend_port'] = backend_server.get('port')
    flattened['backend_host'] = backend_server.get('host')
    flattened['frontend_port'] = frontend_server.get('port')
    
    # TTS (for frontend config API)
    frontend_config = yaml_config.get('frontend', {})
    tts_config = frontend_config.get('tts', {})
    flattened['tts_provider_urls'] = tts_config.get('default_providers', {})
    websocket_config = frontend_config.get('websocket', {})
    flattened['tts_websocket_path'] = websocket_config.get('tts_path', '/ws/tts')
    flattened['stt_websocket_path'] = websocket_config.get('stt_path', '/ws/stt')
    
    # Store full nested configs for access via properties
    flattened['_yaml_config'] = yaml_config
    
    return flattened

# Load YAML config
try:
    yaml_config = load_yaml_config()
    yaml_flattened = flatten_yaml_config(yaml_config)
except Exception as e:
    logger.error(f"Failed to load config.yaml: {e}")
    raise

class Settings(BaseSettings):
    # Application - NO DEFAULTS, must come from YAML or env
    app_name: str
    app_version: str
    debug: bool
    
    # Database
    database_url: str
    # Connection pool settings (PostgreSQL only)
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_timeout: int = 30
    
    # Security
    jwt_secret_key: str  # Required, must be set via env var
    jwt_algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    
    # Note: Admin credentials removed - first user to register becomes admin automatically
    
    # Context Management Configuration
    context_max_tokens: int
    context_keep_recent_scenes: int
    context_summary_threshold: int
    context_summary_threshold_tokens: int
    context_token_buffer: float
    DEFAULT_CHARACTER_EXTRACTION_THRESHOLD: int
    
    # Semantic Memory Configuration
    enable_semantic_memory: bool
    semantic_embedding_model: str
    semantic_search_top_k: int
    semantic_context_weight: float
    semantic_enable_reranking: bool = True
    semantic_reranker_model: Optional[str] = None

    # Context Assembly Strategy
    context_strategy: str
    semantic_scenes_in_context: int
    character_moments_in_context: int
    semantic_min_similarity: Optional[float] = None
    location_recency_window: Optional[int] = None
    
    # Auto-extraction Settings
    auto_extract_character_moments: bool
    auto_extract_plot_events: bool
    extraction_confidence_threshold: int
    
    # Extraction Model Configuration
    extraction_model_enabled: bool
    extraction_model_url: str
    recommended_extraction_models: List[str]
    
    # NPC Tracking Configuration
    npc_tracking_enabled: bool
    npc_importance_threshold: float
    npc_auto_extract_profile: bool
    npc_prompt_user: bool
    npc_active_recency_window: int  # Scenes for Tier 1 (full details)
    npc_inactive_recency_window: int  # Scenes for Tier 2 (brief mention)
    npc_use_chapter_awareness: bool  # NPCs in current chapter always active
    
    # CORS
    cors_origins: str
    
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
    data_dir: str
    export_dir: str
    logs_dir: str
    max_story_size_mb: int
    max_users: int
    
    # Features
    enable_registration: bool
    enable_story_sharing: bool
    enable_public_stories: bool
    
    # Logging
    log_level: str
    log_file: str
    
    # STT Configuration
    stt_model: str
    stt_device: str
    stt_compute_type: str
    stt_language: str
    
    # Advanced STT Settings
    stt_use_silero_vad: bool
    stt_vad_threshold: float
    stt_min_speech_duration_ms: int
    stt_min_silence_duration_ms: int
    stt_max_speech_duration_s: int
    stt_speech_pad_ms: int
    
    # Debug
    prompt_debug: bool
    
    # Server
    backend_port: int
    backend_host: str
    frontend_port: int
    
    # Frontend config (for API)
    tts_provider_urls: dict
    tts_websocket_path: str
    stt_websocket_path: str
    extraction_model_url: str
    
    # Store full YAML config for nested access
    _yaml_config: dict
    
    @property
    def user_defaults(self) -> dict:
        """Get user default settings from config.yaml"""
        return self._yaml_config.get('user_defaults', {})
    
    @property
    def system_defaults(self) -> dict:
        """Get system default settings from config.yaml"""
        return self._yaml_config.get('system_defaults', {})
    
    @property
    def service_defaults(self) -> dict:
        """Get service-specific defaults from config.yaml"""
        return self._yaml_config.get('service_defaults', {})
    
    @property
    def llm_timeout_total(self) -> float:
        """Get LLM HTTP request total timeout in seconds"""
        return self.service_defaults.get('llm_client', {}).get('timeout_total', 180.0)
    
    @property
    def llm_timeout_connect(self) -> float:
        """Get LLM HTTP request connection timeout in seconds"""
        return self.service_defaults.get('llm_client', {}).get('timeout_connect', 30.0)
    
    @property
    def llm_timeout_read(self) -> float:
        """Get LLM HTTP request read timeout in seconds"""
        return self.service_defaults.get('llm_client', {}).get('timeout_read', 150.0)
    
    @property
    def llm_timeout_write(self) -> float:
        """Get LLM HTTP request write timeout in seconds"""
        return self.service_defaults.get('llm_client', {}).get('timeout_write', 150.0)
    
    @property
    def llm_max_retries(self) -> int:
        """Get maximum number of retry attempts for LLM requests"""
        return self.service_defaults.get('llm_client', {}).get('max_retries', 3)
    
    @property
    def llm_retry_base_delay(self) -> float:
        """Get base delay in seconds for exponential backoff retries"""
        return self.service_defaults.get('llm_client', {}).get('retry_base_delay', 2.0)
    
    @property
    def chapter_context_threshold_percentage(self) -> int:
        """Get chapter context threshold percentage from config.yaml"""
        return self._yaml_config.get('context', {}).get('chapter_context_threshold_percentage', 80)

    @property
    def sso_config(self) -> dict:
        """Get SSO configuration from config.yaml"""
        defaults = {
            'enabled': False,
            'header_username': 'Remote-User',
            'header_email': 'Remote-Email',
            'header_groups': 'Remote-Groups',
            'auto_login': True,
            'create_users': False,
            'trusted_proxies': [],
        }
        sso = self._yaml_config.get('sso', {})
        return {**defaults, **sso}

    @property
    def image_generation(self) -> dict:
        """Get image generation configuration from config.yaml"""
        defaults = {
            'enabled': True,
            'storage_path': './data/images',
            'comfyui': {
                'server_url': 'http://localhost:8188',
                'api_key': '',
                'timeout': 300,
                'websocket_fallback_to_polling': True,
                'polling_interval': 2,
            },
            'defaults': {
                'width': 1024,
                'height': 1024,
                'steps': 4,
                'cfg_scale': 1.5,
                'sampler': 'euler',
                'prompt_llm': 'main',
            },
            'style_presets': {},
            'consistency': {
                'sdxl': {'method': 'ip_adapter', 'weight': 0.7},
                'flux': {'method': 'pulid', 'weight': 0.8},
            },
        }
        config = self._yaml_config.get('image_generation', {})
        # Deep merge defaults with config
        result = {**defaults}
        for key, value in config.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
        return result

    class Config:
        env_file = "../.env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields like _yaml_config

# Create global settings instance
# Pass YAML values as initial values, env vars will override
# Ensure _yaml_config is included
settings = Settings(**yaml_flattened)
# Verify _yaml_config is set
if not hasattr(settings, '_yaml_config') or settings._yaml_config is None:
    # Fallback: set it directly
    object.__setattr__(settings, '_yaml_config', yaml_config)
