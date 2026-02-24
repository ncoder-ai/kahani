# Import LiteLLM logging configuration FIRST to suppress debug output
import os
from .utils.litellm_logging import configure_litellm_logging, suppress_httpcore_logging

# Set logging level to ERROR immediately to suppress debug messages
import logging

# Suppress excessive logging from various libraries
logging.getLogger('LiteLLM').setLevel(logging.ERROR)
logging.getLogger('litellm').setLevel(logging.ERROR)
logging.getLogger('multipart').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
logging.getLogger('sentence_transformers').setLevel(logging.ERROR)
logging.getLogger('transformers').setLevel(logging.ERROR)

# Set environment variables to reduce logging
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .config import settings
from .database import engine, get_db
from .models import Base
from .dependencies import get_current_user
import logging
import time
from datetime import datetime, timezone
import os

# Configure logging
os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
log_level = getattr(logging, settings.log_level.upper(), logging.ERROR)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ],
    force=True  # Force reconfiguration even if already configured
)

# Explicitly set root logger and all handlers to the configured level
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
for handler in root_logger.handlers:
    handler.setLevel(log_level)

logger = logging.getLogger(__name__)
logger.setLevel(log_level)

# Configure Uvicorn loggers to respect the configured log level
# Uvicorn uses 'uvicorn', 'uvicorn.access', and 'uvicorn.error' loggers
uvicorn_logger = logging.getLogger('uvicorn')
uvicorn_logger.setLevel(log_level)
uvicorn_access_logger = logging.getLogger('uvicorn.access')
uvicorn_access_logger.setLevel(log_level)
uvicorn_error_logger = logging.getLogger('uvicorn.error')
uvicorn_error_logger.setLevel(log_level)

# If log level is ERROR, disable access logs entirely
if log_level >= logging.ERROR:
    uvicorn_access_logger.disabled = True

# Track process start for health reporting
APP_START_TIME = time.time()
APP_START_ISO = datetime.fromtimestamp(APP_START_TIME, timezone.utc).isoformat()

# NOTE: We do NOT create tables here anymore! 
# Database schema is managed by Alembic migrations.
# Use: alembic upgrade head
# This prevents conflicts between SQLAlchemy's create_all() and Alembic migrations.

# Create FastAPI app
# Disable API documentation in production (when debug=False)
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None
)

# Log validation errors to see what's failing
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"[VALIDATION ERROR] {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
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
                embedding_model=settings.semantic_embedding_model,
                enable_reranking=settings.semantic_enable_reranking,
                reranker_model=settings.semantic_reranker_model,
            )
            logger.info(f"Semantic memory service initialized (reranking={'enabled' if settings.semantic_enable_reranking else 'disabled'}, models will load on first use)")
        except Exception as e:
            logger.error(f"Failed to initialize semantic memory service: {e}")
            logger.warning("Continuing without semantic memory features")
    else:
        logger.info("Semantic memory disabled in configuration")

    # Validate cascade relationships — catch missing cascades that would break story/scene deletion
    try:
        from .models.cascade_validator import validate_cascade_relationships
        cascade_errors = validate_cascade_relationships()
        if cascade_errors:
            for err in cascade_errors:
                logger.error(f"CASCADE VALIDATOR: {err}")
            raise RuntimeError(
                f"CASCADE VALIDATOR: {len(cascade_errors)} table(s) have NOT NULL FKs to "
                f"stories/scenes/chapters without cascade relationships. "
                f"This WILL break deletion. Fix the parent model relationships. "
                f"Errors: {cascade_errors}"
            )
        else:
            logger.info("Cascade validator passed: all NOT NULL FKs have cascade coverage")
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Failed to run cascade validator: {e}")

    # Validate branch-aware registry to catch missing registrations
    try:
        from .models import BranchCloneRegistry
        unregistered = BranchCloneRegistry.validate()
        if unregistered:
            error_msg = (
                f"BRANCH REGISTRY ERROR: The following tables have branch_id but are not registered "
                f"for branch cloning: {unregistered}. See models/BRANCH_AWARE_GUIDE.md for how to fix this."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            logger.info("Branch clone registry validated: all branch-aware tables registered")
    except RuntimeError:
        raise  # Re-raise validation errors
    except Exception as e:
        logger.error(f"Failed to validate branch clone registry: {e}")

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
    uptime_seconds = int(time.time() - APP_START_TIME)
    
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_connected": llm_status,
        "uptime_seconds": uptime_seconds,
        "last_restart": APP_START_ISO,
        "server_time": datetime.now(timezone.utc).isoformat()
    }

# Import and include routers
from .api import auth, stories, characters, summaries, chapters, websocket, semantic_search, admin, character_assistant, branches, brainstorm, entity_states, drafts, story_arc, interactions, story_generation, chapter_brainstorm, scene_endpoints, variant_endpoints, image_generation, contradictions, relationships, worlds, chronicles, roleplay
from .api import settings as settings_router, stt_websocket, config
from .routers import prompt_templates, writing_presets, tts

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
# IMPORTANT: interactions.router must be before stories.router to ensure
# /api/stories/interaction-presets matches before /{story_id} route
app.include_router(interactions.router, prefix="/api", tags=["interactions"])
app.include_router(stories.router, prefix="/api/stories", tags=["stories"])
app.include_router(scene_endpoints.router, prefix="/api/stories", tags=["scene-endpoints"])
app.include_router(variant_endpoints.router, prefix="/api/stories", tags=["variant-endpoints"])
app.include_router(entity_states.router, prefix="/api", tags=["entity-states"])
app.include_router(drafts.router, prefix="/api", tags=["drafts"])
app.include_router(story_arc.router, prefix="/api", tags=["story-arc"])
app.include_router(contradictions.router, prefix="/api", tags=["contradictions"])
app.include_router(relationships.router)  # Prefix already defined in router
app.include_router(story_generation.router, prefix="/api", tags=["story-generation"])
app.include_router(chapters.router, prefix="/api/stories", tags=["chapters"])
app.include_router(chapter_brainstorm.router, prefix="/api/stories", tags=["chapter-brainstorm"])
app.include_router(branches.router, prefix="/api", tags=["branches"])
app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(character_assistant.router, prefix="/api/stories", tags=["character-assistant"])
app.include_router(brainstorm.router, prefix="/api", tags=["brainstorm"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(summaries.router, prefix="/api", tags=["summaries"])
app.include_router(semantic_search.router, prefix="/api", tags=["semantic-search"])
app.include_router(prompt_templates.router, prefix="/api/prompt-templates", tags=["prompt-templates"])
app.include_router(writing_presets.router)
app.include_router(tts.router)
app.include_router(websocket.router)  # WebSocket endpoints
app.include_router(stt_websocket.router)  # STT WebSocket endpoints
app.include_router(image_generation.router, prefix="/api/image-generation", tags=["image-generation"])
app.include_router(worlds.router, prefix="/api/worlds", tags=["worlds"])
app.include_router(chronicles.router, prefix="/api", tags=["chronicles"])
app.include_router(roleplay.router, prefix="/api/roleplay", tags=["roleplay"])

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
    from .config import settings
    port = int(os.getenv("PORT", str(settings.backend_port)))
    # Convert log level to Uvicorn's expected format
    log_level_str = settings.log_level.lower()
    uvicorn.run(
        app, 
        host=settings.backend_host, 
        port=port,
        log_level=log_level_str,
        access_log=(log_level_str != "error")  # Disable access log when log level is ERROR
    )