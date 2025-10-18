# Kahani - Application Architecture

> **Last Updated**: October 18, 2025  
> **Version**: 1.0  
> **Branch**: tts_global

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [System Architecture](#system-architecture)
4. [Backend Architecture](#backend-architecture)
5. [Frontend Architecture](#frontend-architecture)
6. [Key Features & Components](#key-features--components)
7. [Data Flow](#data-flow)
8. [API Architecture](#api-architecture)
9. [Database Schema](#database-schema)
10. [Authentication & Security](#authentication--security)
11. [Development & Deployment](#development--deployment)

---

## Overview

**Kahani** is an interactive storytelling platform that uses AI to generate dynamic, branching narratives with text-to-speech narration. Users create stories by selecting choices, and the AI continues the narrative based on their decisions.

### Core Capabilities
- **AI-Powered Story Generation**: Uses LM Studio (OpenAI-compatible) for scene and choice generation
- **Interactive Branching**: Multiple choices per scene with dynamic continuation
- **Scene Variants**: Generate alternative versions of any scene
- **Chapter Management**: Organize stories into chapters with automatic summaries
- **Text-to-Speech**: Real-time narration using Kokoro TTS via WebSocket streaming
- **Context Management**: Intelligent token management to fit LLM context windows
- **Character System**: Track and integrate characters throughout the story

---

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: SQLite (dev), PostgreSQL (production-ready)
- **ORM**: SQLAlchemy with Alembic migrations
- **Authentication**: JWT tokens with bcrypt password hashing
- **LLM Integration**: LiteLLM (supports OpenAI-compatible APIs)
- **TTS**: Kokoro TTS provider
- **Real-time**: WebSocket for audio streaming, SSE for scene streaming

### Frontend
- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Icons**: Heroicons, Lucide React
- **HTTP Client**: Custom API client with fetch

### Infrastructure
- **Development**: Local LM Studio + Kokoro TTS servers
- **Containerization**: Docker & Docker Compose
- **Reverse Proxy**: Nginx (production)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Story Page  │  │  Dashboard   │  │    Auth      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                  │
│                            │                                     │
│                  ┌─────────▼─────────┐                          │
│                  │   API Client      │                          │
│                  │  (HTTP/WebSocket) │                          │
│                  └─────────┬─────────┘                          │
└────────────────────────────┼─────────────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   NGINX (prod)   │
                    └────────┬─────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                      BACKEND (FastAPI)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   REST API   │  │  WebSocket   │  │  SSE Stream  │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                  │
│  ┌──────▼──────────────────▼──────────────────▼───────┐         │
│  │              Service Layer                          │         │
│  │  • Story Service  • LLM Service  • TTS Service     │         │
│  │  • Context Manager • Variant Service               │         │
│  └──────┬─────────────────────────────────────────────┘         │
│         │                                                        │
│  ┌──────▼──────────────────────────────────────────┐           │
│  │           Database Layer (SQLAlchemy)            │           │
│  └──────┬───────────────────────────────────────────┘           │
└─────────┼─────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  LM Studio   │  │  Kokoro TTS  │  │  SQLite/PG   │          │
│  │  (LLM API)   │  │  (Audio Gen) │  │  (Database)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└───────────────────────────────────────────────────────────────────┘
```

---

## Backend Architecture

### Directory Structure
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py              # Configuration management
│   ├── database.py            # Database connection & session
│   ├── dependencies.py        # Dependency injection
│   │
│   ├── api/                   # API endpoints
│   │   ├── stories.py         # Story CRUD, generation
│   │   ├── websocket.py       # WebSocket handlers (TTS)
│   │   └── __init__.py
│   │
│   ├── routers/               # Additional routers
│   │   ├── auth.py            # Authentication endpoints
│   │   ├── characters.py      # Character management
│   │   ├── chapters.py        # Chapter management
│   │   ├── tts.py            # TTS generation & streaming
│   │   └── lorebook.py       # Lorebook (unused)
│   │
│   ├── models/                # SQLAlchemy models
│   │   ├── user.py           # User model
│   │   ├── story.py          # Story, Scene models
│   │   ├── scene.py          # Scene, SceneChoice models
│   │   ├── scene_variant.py  # Variant system
│   │   ├── chapter.py        # Chapter model
│   │   ├── character.py      # Character model
│   │   └── tts_settings.py   # TTS user settings
│   │
│   ├── services/              # Business logic layer
│   │   ├── llm/              # LLM integration
│   │   │   ├── client.py     # LiteLLM wrapper
│   │   │   ├── service.py    # Scene/choice generation
│   │   │   └── prompts.py    # Prompt management
│   │   │
│   │   ├── tts/              # TTS integration
│   │   │   ├── base.py       # TTS provider interface
│   │   │   ├── manager.py    # Provider management
│   │   │   └── providers/
│   │   │       └── kokoro.py # Kokoro TTS implementation
│   │   │
│   │   ├── context/          # Context management
│   │   │   ├── manager.py    # Context window management
│   │   │   └── optimizer.py  # Context optimization
│   │   │
│   │   └── tts_session_manager.py  # TTS session state
│   │
│   └── utils/                # Utilities
│       ├── auth.py           # JWT & password hashing
│       └── text.py           # Text processing
│
├── alembic/                  # Database migrations
├── data/                     # SQLite database files
├── logs/                     # Application logs
└── requirements.txt          # Python dependencies
```

### Key Backend Components

#### 1. **Story Service** (`services/llm/service.py`)
- Scene generation with streaming support
- Choice generation (4 options per scene)
- Chapter summary generation
- Context building from story history

#### 2. **Context Manager** (`services/context/manager.py`)
- Tracks token usage per chapter
- Automatically triggers chapter summaries at 80% capacity
- Intelligent scene selection for context
- Supports multiple context strategies

#### 3. **TTS Session Manager** (`services/tts_session_manager.py`)
- Manages active TTS sessions
- Handles WebSocket connections
- Buffers audio chunks for auto-play
- Prevents duplicate generation

#### 4. **Scene Variant Service** (`models/scene_variant.py`)
- Each scene can have multiple variants
- Tracks which variant is active
- Supports rating and favoriting
- Generation methods: original, regenerate, branch

#### 5. **Authentication** (`utils/auth.py`)
- JWT token generation and verification
- bcrypt password hashing
- Dependency injection for protected routes

---

## Frontend Architecture

### Directory Structure
```
frontend/
├── src/
│   ├── app/                   # Next.js App Router
│   │   ├── layout.tsx        # Root layout (TTS Provider)
│   │   ├── page.tsx          # Landing page
│   │   ├── dashboard/        # Story list
│   │   ├── login/            # Authentication
│   │   ├── register/         # User registration
│   │   └── story/[id]/       # Story viewer/editor
│   │       └── page.tsx      # Main story page
│   │
│   ├── components/            # React components
│   │   ├── GlobalTTSWidget.tsx      # TTS player widget
│   │   ├── SceneTTSButton.tsx       # Scene narration trigger
│   │   ├── SceneDisplay.tsx         # Scene renderer
│   │   ├── SceneVariantDisplay.tsx  # Variant switcher
│   │   ├── ChapterSidebar.tsx       # Chapter navigation
│   │   ├── ContextInfo.tsx          # Context usage display
│   │   ├── FormattedText.tsx        # Text formatting
│   │   └── TTSSettingsModal.tsx     # TTS configuration
│   │
│   ├── contexts/              # React Context providers
│   │   └── GlobalTTSContext.tsx     # Global TTS state
│   │
│   ├── hooks/                 # Custom React hooks
│   │   └── useTTSWebSocket.ts       # (Legacy - unused)
│   │
│   ├── lib/                   # Utilities
│   │   └── api.ts            # API client
│   │
│   └── store/                 # Zustand stores
│       └── index.ts          # Auth & story stores
│
├── public/                    # Static assets
├── tailwind.config.js        # Tailwind configuration
└── package.json              # Dependencies
```

### Key Frontend Components

#### 1. **Story Page** (`app/story/[id]/page.tsx`)
**Purpose**: Main story interaction interface

**Key Features**:
- Scene display with streaming support
- Choice selection and generation
- Variant management
- Chapter navigation
- Director mode for custom prompts
- Context usage monitoring

**State Management**:
- Local state for UI interactions
- Zustand for auth/story data
- Global TTS context for audio

#### 2. **Global TTS Architecture**

**GlobalTTSContext** (`contexts/GlobalTTSContext.tsx`):
```typescript
interface GlobalTTSContextType {
  // State
  isPlaying: boolean;
  isGenerating: boolean;
  currentSceneId: number | null;
  currentSessionId: string | null;
  error: string | null;
  
  // Actions
  playScene: (sceneId: number) => Promise<void>;
  connectToSession: (sessionId: string, sceneId: number) => Promise<void>;
  stop: () => void;
  pause: () => void;
  resume: () => void;
}
```

**Benefits**:
- Centralized audio state
- Survives page navigation
- Prevents duplicate connections
- Automatic WebSocket management

**GlobalTTSWidget** (`components/GlobalTTSWidget.tsx`):
- Minimal UI (status + controls)
- Located in story page menu
- Shows only when audio is active
- Play/Pause and Stop controls

**SceneTTSButton** (`components/SceneTTSButton.tsx`):
- Per-scene narration trigger
- Shows "Playing..." when active
- Shows "Generating..." during audio creation
- Disabled when playing

#### 3. **Scene Variant System**

**SceneVariantDisplay** (`components/SceneVariantDisplay.tsx`):
- Displays scene content
- Variant navigation (prev/next)
- Variant generation options:
  - Regenerate (new version)
  - Branch (different direction)
  - Continue (extend scene)
- Rating and favorites
- TTS integration

**Flow Entry System**:
- Tracks active variant per scene
- Determines story flow path
- Enables non-linear narratives

#### 4. **API Client** (`lib/api.ts`)

**Features**:
- Automatic JWT token injection
- Error handling
- Streaming support (SSE)
- WebSocket management
- TypeScript typed endpoints

**Example**:
```typescript
const apiClient = {
  // Stories
  getStories: () => Promise<Story[]>
  getStory: (id: number) => Promise<Story>
  createStory: (data: StoryCreate) => Promise<Story>
  
  // Scenes (with streaming)
  generateScene: (storyId: number, prompt: string) => Promise<Scene>
  generateSceneStreaming: (
    storyId: number, 
    prompt: string,
    onChunk: (chunk: string) => void,
    onComplete: (sceneId: number, choices: any[]) => void
  ) => Promise<void>
  
  // Variants
  createSceneVariant: (storyId: number, sceneId: number) => Promise<Variant>
  activateSceneVariant: (storyId: number, sceneId: number, variantId: number) => Promise<void>
  
  // TTS
  generateTTS: (sceneId: number) => Promise<{ session_id: string }>
}
```

---

## Key Features & Components

### 1. Story Generation Flow

```
User selects choice
       ↓
Frontend sends choice to backend
       ↓
Backend builds context (recent scenes + chapter summary)
       ↓
LLM generates new scene (streaming)
       ↓
Backend creates Scene + SceneVariant
       ↓
Backend generates 4 choices
       ↓
[Optional] Auto-play TTS setup
       ↓
Frontend receives streaming content
       ↓
Frontend displays scene + choices
```

### 2. TTS Auto-Play Flow

```
Scene generation complete
       ↓
Backend creates TTS session (auto_play=true)
       ↓
Backend sends auto_play_ready event (SSE)
       ↓
Frontend connects WebSocket to session
       ↓
WebSocket connection triggers TTS generation
       ↓
TTS provider generates audio chunks
       ↓
Chunks streamed via WebSocket (base64)
       ↓
Frontend decodes and plays sequentially
       ↓
Global TTS widget shows playback state
```

**Key Insight**: TTS generation starts AFTER WebSocket connects, ensuring the displayed text matches the narrated text.

### 3. Context Management System

**Token Tracking**:
- Each chapter tracks token usage
- Warning at 80% capacity
- Auto-summary generation at threshold

**Context Building**:
```python
def build_context(story, chapter):
    context = {
        "genre": story.genre,
        "tone": story.tone,
        "world_setting": story.world_setting,
        
        # Chapter summary (compressed history)
        "chapter_summary": chapter.auto_summary,
        
        # Recent scenes (full detail)
        "recent_scenes": last_5_scenes,
        
        # Character info
        "characters": active_characters
    }
    return context
```

**Benefits**:
- Fits within LLM context window
- Maintains story coherence
- Efficient token usage

### 4. Chapter System

**Purpose**: Organize long stories into manageable chunks

**Features**:
- Auto-creation of first chapter
- Manual chapter creation
- Automatic summaries (AI-generated)
- Chapter status: active, completed
- Chapter-specific context tracking

**Flow**:
```
Chapter reaches 80% token capacity
       ↓
User creates new chapter
       ↓
AI generates summary of completed chapter
       ↓
New chapter starts with summary as context
       ↓
Token counter resets
```

### 5. Scene Variant System

**Use Cases**:
- User doesn't like generated scene → regenerate
- Want different story direction → create branch
- Scene too short → continue/extend

**Variant Types**:
- **Original**: First generation
- **Regenerate**: New version of same scene
- **Branch**: Different direction
- **Continue**: Extend existing scene

**Implementation**:
- Each scene has multiple variants (SceneVariant table)
- Flow entry tracks active variant
- Variants can have different choices
- Rating/favorite system for comparison

---

## Data Flow

### Request Flow (Scene Generation)

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP POST /api/stories/{id}/scenes/generate
       ↓
┌──────────────┐
│   API Layer  │ (stories.py)
└──────┬───────┘
       │ 1. Validate request
       │ 2. Check auth
       ↓
┌──────────────┐
│Context Mgr   │ (context/manager.py)
└──────┬───────┘
       │ Build context from story history
       ↓
┌──────────────┐
│  LLM Service │ (services/llm/service.py)
└──────┬───────┘
       │ Generate scene via LiteLLM
       ↓
┌──────────────┐
│   Database   │
└──────┬───────┘
       │ Save Scene + SceneVariant
       ↓
┌──────────────┐
│ Choice Gen   │
└──────┬───────┘
       │ Generate 4 choices
       ↓
┌──────────────┐
│  TTS Setup   │ (optional)
└──────┬───────┘
       │ Create session, start generation
       ↓
┌──────────────┐
│   Response   │
└──────┬───────┘
       │ Return Scene + Choices + TTS session
       ↓
┌─────────────┐
│   Browser   │
└─────────────┘
```

### WebSocket Flow (TTS Streaming)

```
┌─────────────┐
│   Browser   │ Connect WS: /ws/tts/{session_id}
└──────┬──────┘
       │
┌──────▼───────┐
│   WebSocket  │ (websocket.py)
│   Handler    │
└──────┬───────┘
       │ 1. Validate session
       │ 2. Attach WebSocket
       │ 3. Trigger generation (if not started)
       ↓
┌──────────────┐
│TTS Generator │ (tts.py: generate_and_stream_chunks)
└──────┬───────┘
       │ 1. Get scene content from DB
       │ 2. Split into chunks (~150 chars)
       │ 3. For each chunk:
       ↓
┌──────────────┐
│ TTS Provider │ (providers/kokoro.py)
└──────┬───────┘
       │ Generate audio (MP3)
       ↓
┌──────────────┐
│   Session    │ Send via WebSocket
│   Manager    │ { type: "chunk_ready", audio_base64: "..." }
└──────┬───────┘
       │
┌──────▼───────┐
│   Browser    │ 
│   - Decode   │
│   - Queue    │
│   - Play     │
└──────────────┘
```

---

## API Architecture

### REST Endpoints

#### Authentication
```
POST   /api/auth/register          # Create user
POST   /api/auth/login             # Get JWT token
GET    /api/auth/me                # Get current user
```

#### Stories
```
GET    /api/stories                # List user stories
POST   /api/stories                # Create story
GET    /api/stories/{id}           # Get story with scenes
DELETE /api/stories/{id}           # Delete story
PUT    /api/stories/{id}           # Update story
```

#### Scene Generation
```
POST   /api/stories/{id}/scenes/generate          # Generate new scene
POST   /api/stories/{id}/scenes/generate/stream   # Generate with SSE streaming
GET    /api/stories/{id}/scenes                   # List scenes
```

#### Scene Variants
```
POST   /api/stories/{story_id}/scenes/{scene_id}/variants        # Create variant
GET    /api/stories/{story_id}/scenes/{scene_id}/variants         # List variants
PUT    /api/stories/{story_id}/scenes/{scene_id}/variants/{vid}/activate  # Set active
```

#### Chapters
```
GET    /api/stories/{id}/chapters              # List chapters
POST   /api/stories/{id}/chapters              # Create chapter
GET    /api/stories/{id}/active-chapter        # Get active chapter
GET    /api/stories/{id}/chapters/{cid}/context-status  # Token usage
```

#### TTS
```
POST   /api/tts/generate/{scene_id}            # Create TTS session
WS     /ws/tts/{session_id}                    # Stream audio chunks
```

### WebSocket Messages

#### TTS Streaming
```typescript
// Client → Server: (none, just connect)

// Server → Client:
{
  type: "chunk_ready",
  audio_base64: string,
  chunk_number: number
}

{
  type: "progress",
  progress_percent: number,
  total_chunks: number
}

{
  type: "complete"
}

{
  type: "error",
  message: string
}
```

### Server-Sent Events (SSE)

#### Scene Streaming
```typescript
// Event types:
{ type: "start", sequence: number }
{ type: "content", chunk: string }
{ type: "auto_play_ready", session_id: string, scene_id: number }
{ type: "complete", scene_id: number, choices: Choice[] }
{ type: "error", error: string }
```

---

## Database Schema

### Core Tables

#### users
```sql
id          INTEGER PRIMARY KEY
username    VARCHAR UNIQUE NOT NULL
email       VARCHAR UNIQUE NOT NULL
password    VARCHAR NOT NULL  -- bcrypt hashed
created_at  TIMESTAMP
```

#### stories
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER FOREIGN KEY → users
title           VARCHAR NOT NULL
description     TEXT
genre           VARCHAR
tone            VARCHAR
world_setting   TEXT
status          VARCHAR DEFAULT 'active'
created_at      TIMESTAMP
```

#### chapters
```sql
id                  INTEGER PRIMARY KEY
story_id            INTEGER FOREIGN KEY → stories
chapter_number      INTEGER
title               VARCHAR
status              VARCHAR DEFAULT 'active'
auto_summary        TEXT  -- AI-generated summary
context_tokens      INTEGER DEFAULT 0
scenes_since_summary INTEGER DEFAULT 0
created_at          TIMESTAMP
```

#### scenes
```sql
id              INTEGER PRIMARY KEY
story_id        INTEGER FOREIGN KEY → stories
chapter_id      INTEGER FOREIGN KEY → chapters
sequence_number INTEGER
title           VARCHAR
location        VARCHAR
created_at      TIMESTAMP

-- Cached from active variant:
content         TEXT
characters_present JSON
```

#### scene_variants
```sql
id                  INTEGER PRIMARY KEY
scene_id            INTEGER FOREIGN KEY → scenes
variant_number      INTEGER
content             TEXT NOT NULL
title               VARCHAR
is_original         BOOLEAN
generation_method   VARCHAR  -- 'original', 'regenerate', 'branch'
user_rating         INTEGER
is_favorite         BOOLEAN
created_at          TIMESTAMP
custom_prompt       TEXT
```

#### scene_flow_entries
```sql
id                  INTEGER PRIMARY KEY
scene_id            INTEGER FOREIGN KEY → scenes
scene_variant_id    INTEGER FOREIGN KEY → scene_variants
is_active           BOOLEAN
created_at          TIMESTAMP

-- Tracks which variant is currently active for story flow
```

#### scene_choices
```sql
id                  INTEGER PRIMARY KEY
scene_id            INTEGER FOREIGN KEY → scenes
scene_variant_id    INTEGER FOREIGN KEY → scene_variants
choice_text         TEXT NOT NULL
choice_order        INTEGER
description         TEXT
```

#### characters
```sql
id          INTEGER PRIMARY KEY
story_id    INTEGER FOREIGN KEY → stories
name        VARCHAR NOT NULL
role        VARCHAR
description TEXT
created_at  TIMESTAMP
```

#### tts_settings
```sql
id                      INTEGER PRIMARY KEY
user_id                 INTEGER FOREIGN KEY → users
tts_enabled             BOOLEAN DEFAULT true
auto_play_last_scene    BOOLEAN DEFAULT true
voice_id                VARCHAR DEFAULT 'af_alloy'
speed                   FLOAT DEFAULT 1.0
```

### Relationships

```
users (1) ──→ (many) stories
stories (1) ──→ (many) chapters
chapters (1) ──→ (many) scenes
scenes (1) ──→ (many) scene_variants
scene_variants (1) ──→ (many) scene_choices
scenes (1) ──→ (1) scene_flow_entries (active variant)
stories (1) ──→ (many) characters
```

---

## Authentication & Security

### JWT Authentication

**Token Structure**:
```python
{
  "sub": user_id,
  "exp": expiration_timestamp
}
```

**Flow**:
1. User logs in with username/password
2. Backend verifies credentials
3. Backend generates JWT token
4. Frontend stores token in localStorage
5. Frontend sends token in `Authorization: Bearer {token}` header
6. Backend validates token on protected routes

**Implementation** (`utils/auth.py`):
```python
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # Decode token, verify expiration, fetch user
    ...
```

### Password Security
- bcrypt hashing with automatic salt
- No plain-text passwords stored
- Password validation on registration

### CORS Configuration
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Development & Deployment

### Local Development

**Prerequisites**:
- Python 3.11+
- Node.js 18+
- LM Studio running on `localhost:1234`
- Kokoro TTS running on `localhost:8880`

**Backend Setup**:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 9876
```

**Frontend Setup**:
```bash
cd frontend
npm install
npm run dev  # Runs on http://localhost:3000
```

### Environment Variables

**Backend** (`.env` or environment):
```bash
JWT_SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///./data/kahani.db  # Or PostgreSQL URL
LLM_API_BASE=http://localhost:1234/v1
LLM_API_KEY=not-needed
TTS_PROVIDER=kokoro
KOKORO_API_BASE=http://localhost:8880
```

**Frontend** (`frontend/.env.local`):
```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:9876
```

### Docker Deployment

**Development**:
```bash
docker-compose up
```

**Production**:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

**Services**:
- Backend: `http://localhost:9876`
- Frontend: `http://localhost:3000` (dev) or `http://localhost` (prod)
- PostgreSQL: `localhost:5432` (prod only)

### Database Migrations

**Create Migration**:
```bash
cd backend
alembic revision --autogenerate -m "Description"
```

**Apply Migrations**:
```bash
alembic upgrade head
```

**Rollback**:
```bash
alembic downgrade -1
```

---

## Performance Considerations

### Backend Optimizations

1. **Context Management**
   - Automatic chapter summaries reduce token usage
   - Only recent scenes in full detail
   - Character info summarized

2. **TTS Streaming**
   - Chunks generated in parallel with scene generation
   - WebSocket streaming prevents memory buildup
   - Session cleanup after completion

3. **Database Queries**
   - Eager loading for related objects
   - Indexed foreign keys
   - Pagination for large story lists

### Frontend Optimizations

1. **Code Splitting**
   - Next.js automatic route-based splitting
   - Dynamic imports for heavy components

2. **State Management**
   - Zustand for minimal re-renders
   - Local state for UI-only changes
   - Global context only for shared state

3. **Audio Playback**
   - Sequential chunk playback
   - Automatic URL cleanup
   - Queue-based buffering

---

## Future Enhancements

### Planned Features
- Image generation per scene
- Voice selection for TTS
- Story export (PDF, EPUB)
- Collaborative storytelling
- Story templates
- Advanced context strategies
- Multi-language support

### Technical Debt
- Remove unused `lorebook` router
- Delete old `SceneAudioControlsWS` component
- Migrate to PostgreSQL for production
- Add comprehensive error boundaries
- Implement rate limiting
- Add telemetry/analytics

---

## Troubleshooting

### Common Issues

**TTS not playing**:
- Check Kokoro TTS server is running
- Verify `KOKORO_API_BASE` environment variable
- Check browser console for WebSocket errors
- Ensure auto-play permission granted

**Scene not appearing**:
- Check browser console for errors
- Verify backend is generating correctly (check logs)
- Clear frontend state (refresh page)
- Check database for scene entry

**Context overflow**:
- Create new chapter
- AI will generate summary automatically
- Chapter token counter resets

**LLM generation slow**:
- Check LM Studio performance
- Reduce max_tokens setting
- Use smaller model
- Enable streaming for better UX

---

## Additional Resources

- **Backend API Docs**: `http://localhost:9876/docs` (FastAPI Swagger UI)
- **Frontend Docs**: See `frontend/README.md`
- **Database Management**: See `backend/DATABASE_MANAGEMENT.md`
- **Context Management**: See `docs/context-management.md`

---

## Contributing

When making changes:

1. **Backend**: Follow existing service layer pattern
2. **Frontend**: Use TypeScript, keep components focused
3. **Database**: Always create migrations with Alembic
4. **API**: Update Swagger docs via Pydantic models
5. **Testing**: Test locally with LM Studio before committing

---

## Architecture Decisions

### Why FastAPI?
- Automatic OpenAPI docs
- Native async support
- Type hints for better DX
- Fast performance

### Why Next.js?
- Server-side rendering capability
- App Router for better routing
- Built-in optimization
- Great developer experience

### Why SQLite → PostgreSQL?
- SQLite for simple development setup
- PostgreSQL for production (JSONB, better concurrency)
- Same SQLAlchemy models work with both

### Why Global TTS Architecture?
- Survives page navigation
- Prevents duplicate connections
- Simpler state management
- Better UX (no audio interruption)

### Why Chapter System?
- LLMs have context window limits
- Summaries maintain coherence
- Enables very long stories
- Clear narrative structure

---

**Version History**:
- v1.0 (Oct 2025): Initial architecture with global TTS
- v0.9 (Sep 2025): Scene variant system
- v0.8 (Sep 2025): Chapter system with context management
- v0.7 (Aug 2025): TTS integration
- v0.6 (Aug 2025): Streaming generation
- v0.5 (Jul 2025): Basic story generation

---

*This architecture document is a living document. Update it when making significant architectural changes.*
