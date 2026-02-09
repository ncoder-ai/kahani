# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kahani ("story" in Hindi) is an AI-powered interactive storytelling platform with a FastAPI backend and Next.js frontend. Key features include LLM-powered story generation, character tracking, entity state management, semantic memory, brainstorming, and text-to-speech/speech-to-text capabilities.

## Development Commands

### Running the Application
```bash
# Docker (recommended)
docker compose up -d

# Baremetal
./install.sh      # First time setup
./start-dev.sh    # Start development server
```

### Database
```bash
cd backend && alembic upgrade head                    # Apply migrations
cd backend && alembic revision --autogenerate -m "description"  # Create migration from model changes
```

### Frontend
```bash
cd frontend && npm run dev      # Start dev server (port 6789)
cd frontend && npm run build    # Production build
cd frontend && npm run lint     # Run ESLint
```

### Docker Commands
**Important**: Use `docker compose` (V2, without hyphen), not `docker-compose` (legacy V1).
```bash
docker compose up -d          # Start services
docker compose down           # Stop services
docker compose logs -f        # View logs
docker compose logs backend   # View backend logs only
docker compose restart        # Restart services
docker compose up -d --build  # Rebuild and start
```

### Ports
- Frontend: 6789
- Backend: 9876
- PostgreSQL: 5432

## Architecture

### Backend (FastAPI) - `backend/app/`
- **Entry point**: `main.py` - App initialization, middleware, router registration
- **API routes**: `api/` - REST endpoints organized by domain
- **Services**: `services/` - Business logic layer
  - `llm/` - LLM module (decomposed into client, prompts, templates, parsers)
    - `service.py` - Main UnifiedLLMService orchestrating LLM operations
    - `client.py` - LiteLLM client wrapper
    - `prompts.py` - Prompt template management
    - `extraction_service.py` - Entity/character extraction from text
  - `context_manager.py` - Token counting and context window optimization
  - `semantic_memory.py` - ChromaDB vector store for semantic search
  - `entity_state_service.py` - Story world state (characters, locations, objects)
  - `brainstorm_service.py` / `chapter_brainstorm_service.py` - AI brainstorming
  - `branch_service.py` / `branch_cloner.py` - Story branching/forking
- **Models**: `models/` - SQLAlchemy ORM models with branch-aware support
- **Database**: SQLite (default) or PostgreSQL, Alembic migrations in `backend/alembic/`

### Frontend (Next.js 16 / React 19) - `frontend/src/`
- **Pages**: `app/` - Next.js App Router pages
- **State**: `store/index.ts` - Zustand store for auth and global state
- **API client**: `lib/api/` - Modular Axios client
  - `base.ts` - Axios instance with interceptors
  - `auth.ts`, `settings.ts`, `characters.ts`, etc. - Domain-specific modules
  - `index.ts` - Re-exports all API modules
- **Components**: `components/` - React components (require `'use client'` directive)

### Configuration
- `config.yaml.example` - Template for application settings (copy to `config.yaml`)
- `.env.example` - Template for secrets (copy to `.env`)
- Environment variables override config.yaml values

### Prompts
- `backend/prompts.yml` - All LLM prompts (prose styles, scene templates, extraction)
- `backend/interaction_presets.yml` - Character interaction presets

## Key Patterns

### API Routes
FastAPI routes use dependency injection. Routes in `app/api/*.py`, registered in `app/main.py`. Use `get_current_user` dependency for authenticated endpoints.

### Streaming Responses
LLM operations use `StreamingResponse` with `text/event-stream` for real-time output. Frontend consumes via `fetch` with response body reader.

### WebSocket
- `/ws/tts` - Text-to-speech streaming
- `/ws/stt` - Speech-to-text streaming

### Branch-Aware Models
Models with `branch_id` column support story branching. Register in `BranchCloneRegistry` (see `models/BRANCH_AWARE_GUIDE.md`).

### User Settings
Per-user LLM/TTS settings stored in `user_settings` table. Access via `get_user_llm_settings()` dependency.

## Common Tasks

### Adding a new API endpoint
1. Create or edit route file in `backend/app/api/`
2. Add business logic in `backend/app/services/`
3. Register router in `backend/app/main.py` if new file
4. Add frontend API call in `frontend/src/lib/api/` (appropriate module)

### Adding a database model
1. Create model in `backend/app/models/`
2. Export in `backend/app/models/__init__.py`
3. Create migration: `cd backend && alembic revision --autogenerate -m "description"`
4. Apply migration: `cd backend && alembic upgrade head`
5. If branch-aware, register in `BranchCloneRegistry`

### Modifying LLM prompts
Edit `backend/prompts.yml` - changes take effect on next request (hot reload).
