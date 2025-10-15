# Changelog

All notable changes to Kahani will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-XX

### Added

#### Features
- **Three-Tier Summary System**: Implemented cascading summary architecture
  - Chapter-level summaries (`auto_summary`)
  - Story-so-far summaries (`story_so_far`) using summary-of-summaries approach
  - Overall story summaries for dashboard (`summary`)
  - Configurable auto-generation frequency
  - Manual generation buttons always visible in sidebar
  - Dashboard display with one-click generation
- **Text-to-Speech (TTS)**: Audio narration support
  - Multiple provider support (OpenAI TTS, ElevenLabs, Azure)
  - Progressive audio streaming for faster playback
  - Smart linear retry logic with 15 retries
  - Status polling for generation progress
  - Chunk-based audio delivery
- **Enhanced Keyboard Navigation**: 
  - ← (Left Arrow) for previous scene/variant
  - → (Right Arrow) for scene regeneration
  - Esc for closing modals/panels
- **Scene History**: Navigate through all scene versions
- **Auto-Resume**: Automatically opens last worked-on story
- **User Preferences**:
  - Show/hide scene titles
  - Configure auto-summary frequency
  - Set auto-open story behavior

#### Infrastructure
- **Docker Support**: Complete containerization
  - Multi-stage Dockerfiles for backend and frontend
  - docker-compose.yml for standard deployment
  - docker-compose.prod.yml for production with PostgreSQL
  - docker-compose.dev.yml for development with hot reload
  - Health checks and auto-restart policies
  - Resource limits in production mode
  - Optional services via profiles (Ollama, Redis, Nginx)
- **Environment Configuration**: Comprehensive .env.example template
  - Database configuration (SQLite/PostgreSQL)
  - LLM provider configuration (LM Studio, Ollama, OpenAI, Anthropic)
  - TTS provider configuration (optional)
  - Security settings (SECRET_KEY, JWT_SECRET_KEY)
  - Frontend and backend URLs
- **Enhanced Docker Entrypoint**:
  - Service waiting with timeout
  - Database initialization
  - Automatic migrations
  - TTS provider health checks
  - Better error handling and logging
- **Build Optimization**: .dockerignore for faster Docker builds
- **VS Code Tasks**: Pre-configured tasks for common operations

#### Documentation
Created comprehensive documentation suite (15+ files):

**Installation & Setup**:
- QUICK_START.md - 5-minute quick start guide
- INSTALLATION_SUMMARY.md - Overview of all installation methods
- DOCKER_SETUP_GUIDE.md - Complete Docker setup walkthrough
- DOCKER_DEPLOYMENT.md - Detailed deployment scenarios
- DOCKER_QUICK_REFERENCE.md - Docker command reference

**Feature Documentation**:
- docs/user-settings-guide.md - User preferences and settings
- docs/context-management.md - Story context and token usage
- docs/context-manager-explained.md - Context manager internals

**Technical Documentation**:
- TTS_RETRY_IMPROVEMENTS.md - TTS retry logic technical details
- TTS_RETRY_COMPARISON.md - Before/after performance comparison
- TTS_RETRY_VISUAL_GUIDE.md - Visual walkthrough of TTS improvements
- TTS_RETRY_FIX_SUMMARY.md - Quick reference for TTS fixes
- TTS_RETRY_COMPLETE.md - Complete TTS implementation summary
- TTS_RETRY_TLDR.md - 30-second TTS summary
- CONTEXT_FIXES_SUMMARY.md - Context management fixes
- FEATURE_SUMMARY.md - Feature implementation summary
- backend/DATABASE_MANAGEMENT.md - Database operations guide

**Project Documentation**:
- COMPLETE_PROJECT_SUMMARY.md - Comprehensive project overview
- CONTRIBUTING.md - Contribution guidelines
- README.md - Enhanced main documentation

### Changed

#### Performance
- **TTS Retry Logic**: Overhauled from exponential to smart linear backoff
  - OLD: 2s, 4s, 8s, 16s delays (4 retries, 30s total)
  - NEW: 500ms, 650ms, 800ms... 3s max (15 retries, 37s total)
  - Result: 4-17x faster retries, 3.75x more attempts
- **Summary Generation**: Optimized with summary-of-summaries approach
  - Reduces token usage by using chapter summaries instead of full content
  - Cascading architecture for efficient context management

#### UI/UX
- **Summary Buttons**: Moved from modal-only to always-visible sidebar
  - "Generate Story Summary" button (green)
  - "Generate Chapter Summary" button (blue)
  - Summary display in sidebar
- **Dashboard**: Added story summary display with generation capability
- **ChapterSidebar**: Added "Summary Actions" section for better discoverability

#### Backend
- **API Endpoints**: Added new endpoints
  - `/api/tts/audio/{scene_id}/status` - Check TTS generation status
  - `/api/chapters/{chapter_id}/generate-story-so-far` - Generate story-so-far
  - `/api/stories/{story_id}/summary` - Generate/retrieve story summary
- **Database Models**: Enhanced models
  - Added `context_tokens` to Chapter model for tracking
  - Added `ui_display_columns` for UI preferences
  - Added scene variant support

#### Frontend
- **useTTS Hook**: Completely rewritten with smart retry logic
  - Status polling before retries
  - Linear backoff with cap
  - Enhanced error handling and logging
- **API Client**: Added new API methods for summaries and TTS status
- **State Management**: Added summary fields to Zustand store

### Fixed

- **Summary System Bugs**:
  - Fixed dictionary access bug in stories.py
  - Fixed auto-summary not triggering on scene creation
  - Fixed "Story so far" field not populating
- **TTS Issues**:
  - Fixed aggressive exponential backoff causing long delays
  - Fixed insufficient retry attempts (4 → 15)
  - Fixed "chunk not found" errors with better retry logic
  - Fixed no visibility into generation progress (added status endpoint)
- **Context Management**:
  - Fixed token tracking accuracy
  - Fixed context window calculations
- **Docker Issues**:
  - Fixed missing TTS audio volume
  - Fixed entrypoint script not waiting for services
  - Fixed missing environment variables for TTS

### Security

- Enhanced security configuration in docker-compose.prod.yml
  - Non-root users in containers
  - Read-only root filesystem where possible
  - No new privileges
  - Resource limits to prevent DoS
  - Drop unnecessary capabilities
- Comprehensive security checklist in DOCKER_DEPLOYMENT.md
- Environment variable templates with security notes

### Infrastructure

- **Python**: 3.11+
- **Node.js**: 18+
- **Docker**: 20.10+ with Docker Compose 2.0+
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Supported LLM Providers**:
  - LM Studio (local)
  - Ollama (local)
  - OpenAI (cloud)
  - Anthropic Claude (cloud)
- **Supported TTS Providers**:
  - OpenAI TTS
  - ElevenLabs
  - Azure TTS

## [0.9.0] - 2024-XX-XX (Pre-Release)

### Added
- Initial FastAPI backend implementation
- Initial Next.js frontend implementation
- Basic story and scene management
- JWT authentication
- LLM integration (LM Studio)
- SQLite database
- Basic Docker support

### Changed
- N/A (initial release)

### Deprecated
- N/A (initial release)

### Removed
- N/A (initial release)

### Fixed
- N/A (initial release)

### Security
- JWT-based authentication
- Password hashing with bcrypt

---

## Version History Summary

| Version | Date | Description |
|---------|------|-------------|
| **1.0.0** | 2025-01-XX | Production release with three-tier summaries, TTS, complete Docker support, comprehensive documentation |
| **0.9.0** | 2024-XX-XX | Pre-release with basic features |

---

## Migration Guide

### From 0.9.0 to 1.0.0

#### Database Migrations

Run these migrations in order:

```bash
cd backend

# Add context tokens column
python add_context_tokens_column.py

# Add LLM API columns
python migrate_add_llm_api_columns.py

# Add prompt templates
python migrate_add_prompt_templates.py

# Add UI display columns
python migrate_add_ui_display_columns.py

# Add auto-open last story
python migrate_add_auto_open_last_story.py

# Add scene variants
python migrate_scene_variants.py

# Create user settings table
python create_user_settings_table.py
```

Or use the safe migration script:

```bash
cd backend
python safe_migrate.py
```

#### Environment Variables

Update your `.env` file with new variables:

```bash
# Add TTS configuration (optional)
TTS_PROVIDER=openai
TTS_API_URL=https://api.openai.com/v1
TTS_API_KEY=your-api-key-here
TTS_VOICE=alloy

# Ensure JWT secret is set
JWT_SECRET_KEY=your-super-secret-jwt-key-here
```

#### Docker Users

If using Docker, update your configuration:

```bash
# Pull new images
docker-compose pull

# Recreate containers
docker-compose up -d --force-recreate

# Check logs
docker-compose logs -f
```

#### Breaking Changes

None. This release is fully backward compatible with 0.9.0 data.

---

## Roadmap

### Planned for 1.1.0
- [ ] Windows installation support
- [ ] Story export to EPUB/PDF
- [ ] Advanced prompt template variables
- [ ] Batch scene generation
- [ ] Story branching/alternate timelines

### Planned for 1.2.0
- [ ] Mobile apps (iOS/Android)
- [ ] Collaborative stories (multiple users)
- [ ] Story templates library
- [ ] Voice input for scenes
- [ ] Image generation for scenes

### Planned for 2.0.0
- [ ] Real-time collaboration
- [ ] Advanced context management with RAG
- [ ] Plugin system for extensions
- [ ] Advanced analytics and insights
- [ ] Story marketplace/sharing

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to Kahani.

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/kahani/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kahani/discussions)
- **Documentation**: See [COMPLETE_PROJECT_SUMMARY.md](COMPLETE_PROJECT_SUMMARY.md)

---

<p align="center">
  <strong>Kahani</strong> - Where stories come alive through AI collaboration!
</p>
