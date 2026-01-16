# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kahani ("story" in Hindi) is an AI-powered interactive storytelling platform with a FastAPI backend and Next.js frontend. Key features include LLM-powered story generation, character tracking, entity state management, semantic memory, brainstorming, and text-to-speech/speech-to-text capabilities.

## Development Commands

### Running the Application
```bash
# Docker (recommended)
docker-compose up -d

# Baremetal
./install.sh      # First time setup
./start-dev.sh    # Start development server
```

### Database
```bash
cd backend && alembic upgrade head              # Apply migrations
cd backend && alembic revision -m "description" # Create new migration
```

### Docker Commands
```bash
docker-compose up -d        # Start services
docker-compose down         # Stop services
docker-compose logs -f      # View logs
docker-compose logs backend # View backend logs only
docker-compose restart      # Restart services
docker-compose up -d --build  # Rebuild and start
```

### Ports
- Frontend: 6789
- Backend: 9876
- PostgreSQL: 5432

## Architecture

### Backend (FastAPI) - `backend/app/`
- **Entry point**: `main.py`
- **API routes**: `api/` - REST endpoints (stories, chapters, characters, brainstorm, etc.)
- **Services**: `services/` - Business logic layer
  - `llm/service.py` - Core LLM interaction via LiteLLM
  - `context_manager.py` - Token counting and context optimization
  - `semantic_integration.py` - ChromaDB-based memory and embeddings
  - `character_memory_service.py` - Character consistency tracking
  - `entity_state_service.py` - Story world state management
  - `brainstorm_service.py` - Story brainstorming sessions
  - `chapter_brainstorm_service.py` - Chapter planning
  - `npc_tracking_service.py` - NPC behavior tracking
- **Models**: `models/` - SQLAlchemy ORM models
- **Database**: SQLite (default) or PostgreSQL, migrations in `backend/alembic/`

### Frontend (Next.js) - `frontend/src/`
- **Pages**: `app/` - Next.js app router pages
- **State**: `store/index.ts` - Zustand store
- **API client**: `lib/api.ts` - Axios-based API calls
- **Components**: `components/` - React components with `'use client'` directives

### Configuration
- `config.yaml` - All application settings (ports, features, defaults)
- `.env` - Secrets only (SECRET_KEY, JWT_SECRET_KEY)
- Environment variables override config.yaml values

### Prompts
- `backend/prompts.yml` - All LLM prompts (prose styles, scene templates, extraction)
- `backend/interaction_presets.yml` - Character interaction presets

## Key Patterns

### API Routes
FastAPI routes use dependency injection. Routes in `app/api/*.py`, registered in `app/main.py`.

### Streaming
Long-running LLM operations use `StreamingResponse` for real-time output.

### WebSocket
Real-time audio at `/ws/tts` (text-to-speech) and `/ws/stt` (speech-to-text).

### CORS
CORS origins loaded from `config.yaml` (`cors.origins`), can be overridden with `CORS_ORIGINS` env var.

## Common Tasks

### Adding a new API endpoint
1. Create or edit route file in `backend/app/api/`
2. Add business logic in `backend/app/services/`
3. Register router in `backend/app/main.py` if new file

### Adding a database model
1. Create model in `backend/app/models/`
2. Create migration: `cd backend && alembic revision -m "description"`
3. Apply migration: `cd backend && alembic upgrade head`

### Modifying LLM prompts
Edit `backend/prompts.yml` - changes take effect on next request.
