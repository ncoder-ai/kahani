# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kahani ("story" in Hindi) is an AI-powered interactive storytelling platform with a FastAPI backend and Next.js frontend. Key features include LLM-powered story generation, character tracking, entity state management, semantic memory with long-term recall, brainstorming, and text-to-speech/speech-to-text capabilities.

## Development Commands

### Running the Application
```bash
# Docker (recommended)
docker compose up -d

# Baremetal
./install.sh      # First time setup
./start-dev.sh    # Start development server
```

### After Code Changes
```bash
docker compose up -d --build backend   # Rebuild backend container (required after Python changes)
docker compose up -d --build frontend  # Rebuild frontend container (required after frontend changes)
```
**Docker runs production builds** — neither frontend nor backend hot-reload in containers. ALL code changes (Python, TypeScript, prompts.yml) require rebuilding the relevant container.
In baremetal dev (`./start-dev.sh`), frontend hot-reloads and prompts.yml hot-reloads. Backend Python still requires restart.

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

### Docker
**Important**: Use `docker compose` (V2, without hyphen), not `docker-compose` (legacy V1).
```bash
docker compose up -d              # Start services
docker compose down               # Stop services
docker compose logs backend       # View backend logs
docker compose logs backend -f    # Follow backend logs
```

### Ports
- Frontend: 6789, Backend: 9876, PostgreSQL: 5432

## Architecture

### Backend (FastAPI) - `backend/app/`
- **Entry point**: `main.py` - App initialization, middleware, router registration
- **API routes**: `api/` - REST endpoints organized by domain
- **Services**: `services/` - Business logic layer (see Key Subsystems below)
- **Models**: `models/` - SQLAlchemy ORM models with branch-aware support
- **Database**: PostgreSQL (default) or SQLite, Alembic migrations in `backend/alembic/`
- **Config**: `backend/app/config.py` - Pydantic Settings; priority: env vars > `config.yaml` > defaults. Secrets only from `.env`.

### Frontend (Next.js 16 / React 19) - `frontend/src/`
- **Pages**: `app/` - Next.js App Router
- **State**: `store/index.ts` - Zustand stores (auth with persistence, story/character without)
- **API client**: `lib/api/base.ts` - BaseApiClient with circuit breaker (5 failures → 30s block), retry, streaming. Domain clients extend it.
- **Components**: `components/` - React components (require `'use client'` directive)

### Configuration
- `config.yaml.example` / `.env.example` / `docker-compose.yml.example` - Templates; copy to local versions (gitignored)
- `install.sh` and `start-dev.sh` auto-copy `.example` files if missing

### Prompts
- `backend/prompts.yml` - All LLM prompt templates (hot-reloaded in baremetal dev; requires `docker compose up -d --build backend` in Docker)
- `backend/interaction_presets.yml` - Character interaction presets
- **Syntax**: Uses Python `.format()` — use `{{` and `}}` for literal braces in templates

### Debug Logs
- `logs/prompt_sent.json` - Full scene generation prompt
- `logs/prompt_sent_choices.json` - Full choice generation prompt
- `logs/prompt_plot_extraction.json` - Plot extraction prompt

## Key Subsystems

### LLM Pipeline (the core system)
**Flow**: API endpoint → `context_manager.py` builds context dict → `llm/service.py` builds multi-message prompt → LiteLLM → streaming response → `extraction_service.py` extracts entities

**Cache-Optimized Message Ordering** (`_build_cache_friendly_message_prefix()` in `service.py`):
Messages ordered stable-to-dynamic so LLM provider caches maximize hits:
1. STORY FOUNDATION (stable per story)
2. CHARACTER DIALOGUE STYLES (stable per story)
3. STORY HISTORY (stable per chapter)
4. CURRENT CHAPTER (location, time, scenario)
5. CHAPTER DIRECTION (milestones — static per chapter)
6. Scene batches, interaction history, character states/relationships, story focus (stable within session)
7. **--- cache break point ---**
8. RECENT SCENES (changes every scene)
9. RELEVANT CONTEXT (semantic search results)
10. RELATED PAST SCENES (multi-query semantic search — see Scene Discovery below)
11. PACING GUIDANCE (adaptive nudge — last before task)
12. TASK MESSAGE (appended by each caller — scene vs choice vs extraction)

Scene generation and variant regeneration share the same prefix for cache hits.

### Scene Discovery & Long-Term Memory Recall

This is the core innovation for maintaining story coherency across hundreds of scenes. The system uses a multi-layered retrieval pipeline to find relevant past scenes from anywhere in the story's history.

#### Three pgvector Tables (`semantic_memory.py`)
- **`scene_embeddings`**: Scene-level embeddings for semantic search
- **`character_memories`**: Character development milestones (action, dialogue, relationship)
- **`plot_events`**: Key plot events and story threads

Vectors stored as `Vector(768)` columns directly on the SQL tables with HNSW indexes for cosine similarity search. Embedding model: `sentence-transformers/all-mpnet-base-v2` (768d), lazy-loaded on first use. All blocking model ops wrapped in `asyncio.to_thread()`.

#### Contextual Retrieval (`semantic_integration.py`)
Before embedding a scene, a structured prefix is prepended to improve retrieval quality:
```
Chapter 3 'The Confrontation', Scene 47. Location: rooftop garden.
Characters: Alice, Bob.
[LLM-generated summary of what happened in this scene]
[Full scene content]
```
This enriched document is what gets embedded via pgvector, so searches match on chapter context, location, characters, AND content — not just raw prose.

#### Single-Query Search Path (`_get_semantic_scenes()` in `context_manager.py`)
Used when no extraction LLM is available, or as the initial search:
1. **Query construction**: User intent (highest priority) + last 2-3 scene contents (truncated to 200 chars each to avoid drowning intent signal)
2. **Bi-encoder retrieval**: pgvector cosine similarity search (10x oversample for post-filtering)
3. **Keyword boosting with IDF**: Extracts significant words/phrases from user intent → counts doc frequency across candidate scenes → applies IDF-weighted boost (common words get negligible boost, rare terms like "sundress" get full boost). Capped at 0.80 total.
4. **Chapter affinity boost**: Same-chapter scenes get +0.15 similarity boost
5. **Age filtering**: Scenes >50 positions old require similarity >0.6
6. **Branch filtering**: Post-query filtering by `branch_id` (prevents cross-branch contamination)
7. **Token budget formatting**: Scenes sorted chronologically, content truncated to fit budget (800-2000 chars each, keyword-matched scenes get more content)

#### Multi-Query Search Path — Query Decomposition + RRF (`_maybe_improve_semantic_scenes()` in `service.py` → `search_and_format_multi_query()` in `context_manager.py`)
This is the advanced path that dramatically improves recall for complex user intents:

**Step 1 — Query Decomposition** (`service.py`):
The extraction LLM splits user intent into focused sub-queries. Example:
- Input: "She's wearing the red sundress from the rooftop party, and they're at the kitchen counter"
- Output: `["red sundress", "rooftop party", "at the kitchen counter"]`
- Each sub-query targets ONE attribute (clothing, event, location) — never combined
- Generic verbs (came, went, walked) are dropped
- Capped at 6 sub-queries

**Step 2 — Batch Bi-Encoder Search** (`semantic_memory.py`):
- Single `model.encode()` call for all sub-queries (one GPU pass)
- Single pgvector batch query
- Returns per-query result lists

**Step 3 — Reciprocal Rank Fusion (RRF)** (`_reciprocal_rank_fusion()`):
- Merges per-query ranked lists using RRF formula: `score = Σ(1 / (k + rank + 1))` with k=60
- Normalizes to [0, 1]
- Scenes appearing in multiple query results get boosted naturally

**Step 4 — Hybrid Keyword Search**:
- Extracts 2-word phrases and distinctive single words from sub-queries
- Filters out high-frequency character names (protagonists appearing in >30% of scenes are noise; rare character names are kept as valuable keywords)
- IDF filter: drops keywords matching >15% of scenes (no discriminative power)
- DB `LIKE` query finds exact keyword matches that bi-encoder missed
- Results merged with bi-encoder pool via second RRF pass

**Step 5 — Temporal Anchoring**:
- Finds WHEN recalled events happened by keyword-matching scene content against sub-queries
- Computes recency-weighted anchor points (weighted average of last 5 occurrences per keyword)
- Confidence-weighted proximity boost: `boost = max(0, 0.50 - 0.005 * distance) * confidence`
- Wide-spread keywords (>100 scenes apart) get per-sub-query anchors
- Confidence saturates at 15 occurrences (min 0.15 for any qualifying keyword)

**Step 6 — Phrase-Level Boost**:
- Extracts 2-word phrases from sub-queries (excluding character name bigrams)
- Boosts scenes containing exact phrases by +0.15 each, capped at +0.30

**Step 7 — Filter & Format**: Min similarity threshold, branch filtering, chronological sort, token budget truncation (same as single-query path but NO chapter affinity boost — multi-query targets cross-chapter retrieval)

#### How the Two Paths Connect
In `service.py`, after building the initial prompt with single-query semantic scenes, `_maybe_improve_semantic_scenes()` attempts the multi-query path. If successful, it replaces the `RELATED PAST SCENES` message in the prompt. If decomposition fails, the single-query results remain. This is a graceful enhancement — the system always has a baseline.

### Context Manager (`context_manager.py`)
- **Token budget**: `max_tokens * 0.85` effective limit, allocated between base context, recent scenes, and semantic results
- **Two strategies**: `linear` (recency only) or `hybrid` (recency + pgvector semantic search)
- **Scene batching**: Groups scenes aligned to extraction intervals for cache optimization
- Passes `_semantic_search_state` and `_context_manager_ref` in the context dict so `service.py` can trigger multi-query search without re-querying parameters

### Extraction Pipeline (`llm/extraction_service.py`)
- Uses a separate small/fast LLM (e.g., Ministral-3B, Qwen-2.5-3B) for entity extraction after scene generation
- **Plot event tracking**: Sends numbered event list, LLM returns indexed true/false dict (`{"1": true, "2": false}`), parsed by index — no string matching
- **JSON parsing**: `extract_json_robust()` handles markdown fences, thinking tags, and brace matching
- Few-shot prompt pattern: brief rules (5-7 lines) + 1-2 realistic examples + "NOT extracted" callouts

### Chapter Progress & Plot (`chapter_progress_service.py`)
- **Plot guidance goes to choices, not scenes** — scenes follow user directives; choices steer toward plot milestones
- `plot_check_mode`: `"1"` (next event only), `"3"` (next 3), `"all"` (adaptive by progress %)
- When all `key_events` completed, falls back to climax/resolution guidance

### Branch System
- Models with `branch_id` support story branching via `@branch_clone_config` decorator
- See `models/BRANCH_AWARE_GUIDE.md` for how to make new models branch-aware
- `BranchCloneRegistry` validates at startup — missing registrations cause errors

## Key Patterns

### API Routes
FastAPI dependency injection. Routes in `app/api/*.py`, registered in `app/main.py`. Use `get_current_user` for auth.

### Streaming
LLM operations use `StreamingResponse` with `text/event-stream`. Frontend consumes via `fetch` with body reader.

### WebSocket
- `/ws/tts` - Text-to-speech streaming
- `/ws/stt` - Speech-to-text streaming

### User Settings
Per-user LLM/TTS settings in `user_settings` table. Access via `get_user_llm_settings()` dependency.

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
5. If branch-aware, add `branch_id` column and `@branch_clone_config` decorator

### Modifying LLM prompts
Edit `backend/prompts.yml`. In baremetal dev, changes take effect on next request (hot reload via mtime check). In Docker, requires `docker compose up -d --build backend` since the file is baked into the image.

## Gotchas
- Chapter model uses `location_name` (not `location`), `status` enum (no `is_completed` field)
- `prompts.yml` uses `{{`/`}}` for literal braces (Python `.format()` escaping)
- Check both `prompt_sent.json` AND `prompt_sent_choices.json` when debugging prompt issues
- Variant regeneration uses saved `context_snapshot` to match original context
- Token refresh is proactive (scheduled before expiry), not reactive (after 401)
