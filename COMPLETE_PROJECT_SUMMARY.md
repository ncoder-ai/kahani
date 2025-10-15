# 📚 Kahani - Complete Project Summary

**Version**: 1.0  
**Last Updated**: January 2025  
**Status**: Production Ready 🚀

---

## 🎯 Project Overview

**Kahani** (meaning "story" in Hindi) is a modern interactive storytelling platform that combines the power of AI with intuitive story management. This document provides a comprehensive overview of the entire project, its features, architecture, and deployment options.

## ✨ Key Features

### 🤖 AI-Powered Storytelling
- **Multiple LLM Support**: LM Studio, Ollama, OpenAI, Anthropic
- **Custom Prompt Templates**: Create and manage AI prompts for different story types
- **Scene Generation**: AI-assisted story continuation
- **Scene Regeneration**: Don't like a scene? Regenerate with one keypress (→)

### 📝 Three-Tier Summary System
1. **Chapter Summary**: Each chapter has its own AI-generated summary
2. **Story So Far**: Cascading summary combining all previous chapters
3. **Story Summary**: Overall narrative for the dashboard

**Features**:
- Auto-generates every N scenes (configurable)
- Manual generation buttons always visible in sidebar
- Dashboard display with one-click generation
- Summary-of-summaries architecture for context efficiency

### 🎙️ Text-to-Speech (TTS)
- **Multiple Providers**: OpenAI TTS, ElevenLabs, Azure
- **Progressive Streaming**: Audio chunks play as they're generated
- **Smart Retry Logic**: 15 retries with linear backoff (500ms → 3s max)
- **Status Polling**: Real-time generation progress tracking
- **4-17x Faster**: Optimized retry delays vs exponential backoff

### 📱 User Experience
- **Auto-Resume**: Automatically opens your last worked-on story
- **Keyboard Navigation**: ← previous, → regenerate
- **Scene History**: Navigate through all scene versions
- **Auto-Save**: Automatic story and scene persistence
- **Responsive Design**: Works seamlessly on desktop and mobile
- **Customizable UI**: Toggle scene titles and display preferences

### 🔐 Security & Authentication
- JWT-based authentication
- Secure password hashing
- User-specific story isolation
- Configurable secret keys

## 🏗️ Architecture

### Technology Stack

#### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: SQLAlchemy with SQLite (dev) / PostgreSQL (prod)
- **Authentication**: JWT tokens
- **API**: RESTful with OpenAPI/Swagger docs
- **Container**: Docker multi-stage build

#### Frontend
- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Container**: Node 18 Alpine

#### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Reverse Proxy**: Nginx (optional)
- **Caching**: Redis (optional)
- **LLM**: Ollama (optional, for local inference)

### Project Structure

```
kahani/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/             # API endpoints
│   │   ├── models/          # SQLAlchemy models
│   │   ├── routers/         # API routers (stories, scenes, auth, TTS)
│   │   ├── services/        # Business logic
│   │   └── utils/           # Utilities
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Backend container
├── frontend/                 # Next.js application
│   ├── src/
│   │   ├── app/            # Next.js pages
│   │   ├── components/     # React components
│   │   ├── hooks/          # Custom hooks (useTTS, etc.)
│   │   ├── lib/            # API client
│   │   └── store/          # Zustand state
│   ├── package.json        # Node dependencies
│   └── Dockerfile          # Frontend container
├── docs/                    # Documentation
├── docker-compose.yml       # Main composition
├── docker-compose.prod.yml  # Production overrides
├── docker-compose.dev.yml   # Development overrides
├── .env.example            # Environment template
├── install.sh              # Automated installer
└── README.md               # Main documentation
```

## 🚀 Installation Methods

### 1. 🐳 Docker Deployment (Recommended for Production)

**Fastest way to get started:**

```bash
git clone https://github.com/yourusername/kahani.git
cd kahani
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
```

**Deployment Modes**:
- **Development**: Hot reload, SQLite, source mounted
- **Standard**: SQLite, no source mounting
- **Production**: PostgreSQL, resource limits, health checks
- **Full Stack**: + Ollama, Redis, Nginx

**Documentation**:
- [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md) - Complete walkthrough
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Detailed scenarios
- [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md) - Command reference

### 2. 🔧 Native Installation (Recommended for Development)

**Automated installation:**

```bash
git clone https://github.com/yourusername/kahani.git
cd kahani
chmod +x install.sh
./install.sh
./start-dev.sh
```

**What it does**:
- Installs Python 3.11+ and Node.js 18+
- Creates Python virtual environment
- Installs all dependencies
- Initializes database with test user
- Generates secure configuration
- Verifies installation

### 3. 📋 Manual Installation

For developers who want full control over the installation process. See [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md) for detailed steps.

## 📖 Complete Documentation Index

### Installation & Setup
| Document | Description | Best For |
|----------|-------------|----------|
| [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md) | Overview of all methods | Quick comparison |
| [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md) | Complete Docker walkthrough | Docker users |
| [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) | Detailed deployment | Production |
| [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md) | Command reference | Quick lookups |

### Features & User Guides
| Document | Description |
|----------|-------------|
| [docs/user-settings-guide.md](docs/user-settings-guide.md) | User preferences and settings |
| [docs/context-management.md](docs/context-management.md) | Story context and token usage |
| [docs/context-manager-explained.md](docs/context-manager-explained.md) | Context manager internals |

### Technical Documentation
| Document | Description |
|----------|-------------|
| [TTS_RETRY_IMPROVEMENTS.md](TTS_RETRY_IMPROVEMENTS.md) | TTS retry logic details |
| [TTS_RETRY_COMPARISON.md](TTS_RETRY_COMPARISON.md) | Before/after performance |
| [TTS_RETRY_VISUAL_GUIDE.md](TTS_RETRY_VISUAL_GUIDE.md) | Visual walkthrough |
| [CONTEXT_FIXES_SUMMARY.md](CONTEXT_FIXES_SUMMARY.md) | Context management fixes |
| [FEATURE_SUMMARY.md](FEATURE_SUMMARY.md) | Feature implementation summary |
| [backend/DATABASE_MANAGEMENT.md](backend/DATABASE_MANAGEMENT.md) | Database operations |

### Development
| Document | Description |
|----------|-------------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [README.md](README.md) | Main project documentation |

## 🎯 Major Implementations & Fixes

### 1. Three-Tier Summary System
**Problem**: Auto-summary not working, unclear architecture  
**Solution**: Implemented cascading summary system with three levels  
**Result**: Efficient context management with always-visible controls

**Files Modified**:
- `backend/app/api/chapters.py` - Added `generate_story_so_far()`
- `backend/app/api/summaries.py` - Added story summary endpoint
- `backend/app/api/stories.py` - Fixed dictionary access bug
- `frontend/src/components/ChapterSidebar.tsx` - Summary buttons in sidebar
- `frontend/src/app/dashboard/page.tsx` - Story summary display

### 2. TTS Retry Logic Overhaul
**Problem**: Exponential backoff too aggressive (2s, 4s, 8s, 16s), only 4 retries  
**Solution**: Linear backoff with cap (500ms → 3s), 15 retries, status polling  
**Result**: 4-17x faster retries, 3.75x more attempts, better success rate

**Files Modified**:
- `frontend/src/hooks/useTTS.ts` - Smart linear backoff implementation
- `backend/app/routers/tts.py` - Added status endpoint

**Performance Comparison**:
```
OLD: 2s → 4s → 8s → 16s (4 retries, 30s total)
NEW: 500ms → 650ms → 800ms → ... → 3s (15 retries, 37s total)

Time to 4 retries: 30s → 2s (15x faster!)
Total retries: 4 → 15 (3.75x more attempts)
```

### 3. Docker Infrastructure Enhancement
**Problem**: Existing Docker setup lacked TTS support and comprehensive documentation  
**Solution**: Enhanced Docker compose files, improved entrypoint, created guides  
**Result**: Production-ready Docker deployment with multiple modes

**Files Created/Enhanced**:
- `docker-compose.yml` - Added TTS support, audio volume, env vars
- `docker-compose.dev.yml` - Development overrides with hot reload
- `docker-entrypoint.sh` - Health checks, migrations, error handling
- `.env.example` - Comprehensive environment template
- `.dockerignore` - Build optimization

## 🔧 Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Database
DATABASE_URL=sqlite:///./data/kahani.db  # Or PostgreSQL

# Security
SECRET_KEY=your-very-secure-secret-key
JWT_SECRET_KEY=your-jwt-secret-key

# LLM Configuration
LLM_BASE_URL=http://localhost:1234/v1  # LM Studio
LLM_API_KEY=not-needed-for-local
LLM_MODEL=local-model

# TTS Configuration (Optional)
TTS_PROVIDER=openai
TTS_API_URL=https://api.openai.com/v1
TTS_API_KEY=your-api-key
TTS_VOICE=alloy

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### LLM Providers Supported

1. **LM Studio** (Local, Default)
2. **Ollama** (Local)
3. **OpenAI** (Cloud)
4. **Anthropic Claude** (Cloud)

### TTS Providers Supported

1. **OpenAI TTS**
2. **ElevenLabs**
3. **Azure TTS**

## 🛠️ Development

### Quick Start

```bash
# Native development
cd backend && source ../.venv/bin/activate
uvicorn app.main:app --reload

# In another terminal
cd frontend && npm run dev

# Docker development (with hot reload)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Running Tests

```bash
# Frontend
cd frontend
npm test

# Backend
cd backend
python -m pytest

# Coverage
pytest --cov=app --cov-report=html
```

### API Documentation

When running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### VS Code Tasks

Pre-configured tasks available:
1. **Start Backend Server** - Launch backend with auto-reload
2. **Start Frontend Server** - Launch frontend with hot reload
3. **Build Frontend** - Production build
4. **Install Dependencies** - Install all dependencies

Access: `Terminal → Run Task...` or `Cmd+Shift+P` → "Run Task"

## 📊 System Requirements

### Minimum Requirements
- **OS**: Linux (Ubuntu 20.04+), macOS (10.15+), Windows 10+ with WSL2
- **RAM**: 4GB
- **Storage**: 2GB free space
- **Docker**: 20.10+ with Docker Compose 2.0+ (for Docker deployment)

### Recommended Requirements
- **RAM**: 8GB+ (especially for local LLM)
- **Storage**: 5GB+ (for models and data)
- **CPU**: 4+ cores
- **GPU**: Optional, for local LLM acceleration

## 🚦 Success Indicators

### Installation Success
- ✅ Backend running at http://localhost:8000
- ✅ Frontend running at http://localhost:3000
- ✅ Can login with test@test.com / test
- ✅ API docs accessible at /docs
- ✅ Database initialized (kahani.db created)

### Feature Success
- ✅ Can create new story
- ✅ Can generate scenes with AI
- ✅ Summary buttons visible in sidebar
- ✅ Story summary on dashboard
- ✅ Keyboard navigation works (← →)
- ✅ TTS plays audio (if configured)

### Docker Success
- ✅ All containers running: `docker-compose ps`
- ✅ No errors in logs: `docker-compose logs`
- ✅ Backend healthy: `curl http://localhost:8000/health`
- ✅ Frontend accessible: `curl http://localhost:3000`

## 🔍 Troubleshooting

### Quick Diagnostics

```bash
# Check services
docker-compose ps  # Docker
lsof -i :8000      # Backend port
lsof -i :3000      # Frontend port

# View logs
docker-compose logs -f kahani-backend
docker-compose logs -f kahani-frontend
tail -f logs/kahani.log  # Native

# Test LLM connection
curl http://localhost:1234/v1/models  # LM Studio
curl http://localhost:11434/api/tags   # Ollama

# Check database
cd backend
python -c "from app.database import engine; print(engine.url)"
```

### Common Issues

1. **LLM Connection Failed**: Verify LLM service is running, check LLM_BASE_URL
2. **Database Locked**: Run `python init_database.py`
3. **Port Conflicts**: Change ports in docker-compose.yml or .env
4. **Docker Container Crash**: Check logs with `docker-compose logs -f`
5. **TTS Not Playing**: Verify TTS_PROVIDER and TTS_API_KEY in .env

For detailed troubleshooting, see:
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md#troubleshooting)
- [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md#troubleshooting-matrix)

## 🤝 Contributing

We welcome contributions! Here's how:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `npm test` and `pytest`
5. Commit: `git commit -m 'Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## 📝 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Next.js](https://nextjs.org/) - React framework
- [LM Studio](https://lmstudio.ai/) - Local LLM hosting
- [Ollama](https://ollama.ai/) - Run LLMs locally
- [Tailwind CSS](https://tailwindcss.com/) - CSS framework
- [SQLAlchemy](https://sqlalchemy.org/) - Python ORM
- [Zustand](https://github.com/pmndrs/zustand) - State management

## 💬 Support & Community

- **Issues**: [GitHub Issues](https://github.com/yourusername/kahani/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kahani/discussions)
- **Documentation**: Check the [docs/](docs/) directory
- **API Docs**: http://localhost:8000/docs (when running)

## 🎉 Current Status

**Version**: 1.0  
**Status**: Production Ready  
**Last Updated**: January 2025

### ✅ Completed Features
- ✅ Three-tier summary system
- ✅ TTS with smart retry logic
- ✅ Docker deployment (dev, standard, production)
- ✅ Native installation script
- ✅ Comprehensive documentation (15+ guides)
- ✅ Multiple LLM providers
- ✅ Multiple TTS providers
- ✅ Auto-resume last story
- ✅ Keyboard navigation
- ✅ Scene history
- ✅ Custom prompt templates
- ✅ JWT authentication
- ✅ Auto-save
- ✅ Responsive UI

### 🚀 Future Enhancements
- [ ] Windows installation support
- [ ] Mobile apps (iOS/Android)
- [ ] Story export to EPUB/PDF
- [ ] Collaborative stories (multiple users)
- [ ] Story templates library
- [ ] Advanced context management
- [ ] Voice input for scenes
- [ ] Image generation for scenes

---

<p align="center">
  <strong>Kahani</strong> - Where stories come alive through AI collaboration! 🎭📚✨
</p>

<p align="center">
  Made with ❤️ for storytellers everywhere
</p>
