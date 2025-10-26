# Import LiteLLM logging configuration FIRST to suppress debug output
from .utils.litellm_logging import configure_litellm_logging, suppress_httpcore_logging

# Set logging level to ERROR immediately to suppress debug messages
import logging
import os

# Suppress excessive logging from various libraries
logging.getLogger('LiteLLM').setLevel(logging.ERROR)
logging.getLogger('litellm').setLevel(logging.ERROR)
logging.getLogger('multipart').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
logging.getLogger('chromadb').setLevel(logging.ERROR)
logging.getLogger('chromadb.auth').setLevel(logging.ERROR)
logging.getLogger('chromadb.telemetry').setLevel(logging.ERROR)
logging.getLogger('chromadb.config').setLevel(logging.ERROR)
logging.getLogger('chromadb.segment').setLevel(logging.ERROR)
logging.getLogger('sentence_transformers').setLevel(logging.ERROR)
logging.getLogger('transformers').setLevel(logging.ERROR)

# Set environment variables to reduce logging
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .config import settings
from .database import engine, get_db
from .models import Base
from .dependencies import get_current_user
import logging
import os

# Configure logging
os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Create tables if they don't exist (safe - only creates missing tables, never modifies existing ones)
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

# Initialize semantic memory service on startup
@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup"""
    logger.info("Initializing services...")
    
    # Configure LiteLLM to suppress cost calculation warnings
    try:
        import litellm
        import os
        
        # Disable verbose logging and cost calculation warnings
        litellm.set_verbose = False
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        
        # Set environment variables to suppress warnings
        os.environ["LITELLM_LOG"] = "ERROR"
        os.environ["LITELLM_LOG_LEVEL"] = "ERROR"
        os.environ["LITELLM_SUPPRESS_DEBUG_INFO"] = "true"
        os.environ["LITELLM_DROP_PARAMS"] = "true"
        
        # Disable cost calculation completely
        litellm.cost_calculator = None
        
        # Additional suppression
        try:
            litellm.set_verbose = False
            litellm.suppress_debug_info = True
            litellm.drop_params = True
        except:
            pass
        
        logger.info("LiteLLM configured to suppress cost calculation warnings")
    except Exception as e:
        logger.warning(f"Failed to configure LiteLLM warnings suppression: {e}")
    
    # Initialize semantic memory service if enabled (lazy-loaded, won't download models yet)
    if settings.enable_semantic_memory:
        try:
            from .services.semantic_memory import initialize_semantic_memory_service
            initialize_semantic_memory_service(
                persist_directory=settings.semantic_db_path,
                embedding_model=settings.semantic_embedding_model
            )
            logger.info("Semantic memory service initialized (models will load on first use)")
        except Exception as e:
            logger.error(f"Failed to initialize semantic memory service: {e}")
            logger.warning("Continuing without semantic memory features")
    else:
        logger.info("Semantic memory disabled in configuration")
    
    logger.info("Application startup complete")

# Configure network settings
from .utils.network_config import NetworkConfig
network_config = NetworkConfig.get_deployment_config()

# Update CORS origins based on deployment environment
settings.cors_origins = network_config['cors_origins']

# Add CORS middleware
logger.info(f"CORS Origins: {settings.cors_origins}")
logger.info(f"API URL: {network_config['api_url']}")
logger.info(f"Frontend URL: {network_config['frontend_url']}")
logger.info(f"Network IP: {network_config['network_ip']}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add authentication and approval middleware
# Order matters: Auth middleware runs first to populate request.state.user
# Then approval middleware checks if user is approved
from .middleware.auth_middleware import AuthMiddleware
from .middleware.approval_check import ApprovalCheckMiddleware

app.add_middleware(ApprovalCheckMiddleware)  # Check approval status
app.add_middleware(AuthMiddleware)  # Extract and set user (runs first)

# Security
security = HTTPBearer()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from .services.llm.service import UnifiedLLMService
    
    # Simple health check
    llm_status = "available"
    
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_connected": llm_status
    }

# Import and include routers
from .api import auth, stories, characters, summaries, chapters, websocket, semantic_search, admin
from .api import settings as settings_router
from .routers import prompt_templates, writing_presets, tts

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(stories.router, prefix="/api/stories", tags=["stories"])
app.include_router(chapters.router, prefix="/api/stories", tags=["chapters"])
app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(summaries.router, prefix="/api", tags=["summaries"])
app.include_router(semantic_search.router, prefix="/api", tags=["semantic-search"])
app.include_router(prompt_templates.router, prefix="/api/prompt-templates", tags=["prompt-templates"])
app.include_router(writing_presets.router)
app.include_router(tts.router)
app.include_router(websocket.router)  # WebSocket endpoints

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9876"))
    uvicorn.run(app, host="0.0.0.0", port=port)