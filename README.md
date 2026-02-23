# Kahani - Interactive Storytelling Platform

Kahani (meaning "story" in Hindi) is an AI-powered interactive storytelling platform that combines advanced LLM integration with sophisticated story management, character tracking, and audio capabilities.

## Features

### AI-Powered Story Generation
- **Multiple LLM Providers** - OpenAI, Anthropic, Ollama, LM Studio, and any OpenAI-compatible API
- **Streaming Generation** - Real-time scene generation with live text streaming
- **Prose Style Selection** - Balanced, dialogue-heavy, description-driven, stream of consciousness, minimalist, and more
- **Smart Context Management** - Automatic context window optimization with three-tier summarization
- **Extended Thinking** - Support for Claude's extended thinking with configurable reasoning effort

### Story & Chapter Management
- **Story Modes** - Dynamic (AI-guided) or Structured (chapter-based) storytelling
- **Chapter Organization** - Create, edit, and manage chapters with summaries and metadata
- **Scene Variants** - Generate multiple versions of scenes and compare alternatives
- **Story Branching** - Fork stories at any point to explore alternative timelines
- **Interactive Choices** - AI-generated narrative choices for reader-driven stories
- **Auto-Save** - Automatic story and scene persistence

### AI Brainstorming System
- **Brainstorm Sessions** - Multi-turn chat conversations with AI to develop story ideas
- **Chapter Brainstorming** - Plan individual chapters with plot guidance
- **Story Arc Generation** - Automatic three-act structure creation
- **Element Extraction** - Auto-extract characters, plot points, and story elements from brainstorm
- **Plot Event Tracking** - Track key events and milestones per chapter

### Character System
- **Character Library** - Create reusable character templates with detailed profiles
- **Character Profiles** - Name, personality, background, goals, fears, appearance, and custom traits
- **Story Characters** - Link characters to stories with specific roles
- **AI Character Generation** - Create characters from text descriptions
- **Character Suggestions** - AI-suggested characters based on story context

### Entity & State Tracking
- **Character States** - Track location, emotional state, possessions, knowledge, relationships, and arc progress
- **Location States** - Monitor atmosphere, occupants, environmental conditions
- **Object States** - Track significant items, ownership, and history
- **Automatic Extraction** - AI extracts entity states from scenes
- **Relationship Mapping** - Track character-to-character relationships

### Semantic Memory & Context
- **Semantic Search** - Find similar scenes, character moments, and plot events by meaning
- **Character Arc Tracking** - View complete character journeys chronologically
- **Plot Thread Tracking** - Identify and track unresolved story threads
- **Smart Context Selection** - Intelligent inclusion of relevant context for generation
- **Character Moment Extraction** - Automatically identify important character development moments

### Text-to-Speech (TTS)
- **Multiple Providers** - OpenAI TTS, Kokoro, Chatterbox, VibeVoice, and custom providers
- **Character Voices** - Assign different voices to different characters
- **Progressive Streaming** - Real-time audio generation and playback
- **Voice Browser** - Browse and preview available voices
- **Global TTS Widget** - Unified audio controls

### Speech-to-Text (STT)
- **Whisper Integration** - Local speech recognition using faster-whisper
- **Multiple Models** - Choose from tiny, base, small, medium, or large models
- **Real-time Streaming** - WebSocket-based live transcription
- **Voice Activity Detection** - Automatic speech detection with Silero VAD

### Writing Customization
- **Writing Presets** - Save custom system prompts and generation configurations
- **Prose Styles** - Multiple built-in styles with detailed instructions
- **POV Selection** - First, second, or third person perspective
- **Custom Templates** - Define custom text completion templates with variables

### User & Admin Features
- **User Management** - Registration, approval workflow, and permissions
- **Per-User Settings** - Each user configures their own LLM and TTS settings
- **Permission System** - Control access to NSFW content, provider changes, exports, etc.
- **Admin Panel** - User management, approvals, and system statistics

## Quick Start

**Docker (Recommended):**
```bash
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
cp .env.example .env
cp config.yaml.example config.yaml
cp docker-compose.yml.example docker-compose.yml
# Edit .env and set SECRET_KEY and JWT_SECRET_KEY (see .env.example for instructions)
docker compose up -d
```

Access the app at http://localhost:6789

**Baremetal:**
```bash
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
./install.sh
./start-dev.sh
```

See [QUICK_START.md](QUICK_START.md) for detailed setup instructions.

## Configuration

Kahani uses a two-file configuration system:
- **`config.yaml`** - All application settings (copy from `config.yaml.example`)
- **`.env`** - Secrets only (copy from `.env.example`)

LLM and TTS settings are configured per-user through the web interface Settings panel.

See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) for details.

## Requirements

- **Docker** (recommended) OR Python 3.11+ and Node.js 20.9.0+
- **LLM Provider** - Local (Ollama, LM Studio) or cloud (OpenAI, Anthropic)

## Documentation

| Document | Description |
|----------|-------------|
| [QUICK_START.md](QUICK_START.md) | Setup and installation guide |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | Configuration reference |
| [docs/EXTRACTION_MODEL_SETUP.md](docs/EXTRACTION_MODEL_SETUP.md) | Local extraction model setup |
| [docs/tts-quick-start.md](docs/tts-quick-start.md) | TTS provider configuration |

## Tech Stack

**Backend:** FastAPI, SQLAlchemy, Alembic, LiteLLM, pgvector, faster-whisper

**Frontend:** Next.js 16, React 19, Tailwind CSS, Zustand

**Database:** PostgreSQL with pgvector

## License

AGPL-3.0 License - see [LICENSE](LICENSE) for details.
