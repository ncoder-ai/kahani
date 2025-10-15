# 📚 Kahani - Interactive Storytelling Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Node.js-18+-green.svg" alt="Node.js Version">
  <img src="https://img.shields.io/badge/FastAPI-Latest-teal.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-14-black.svg" alt="Next.js">
  <img src="https://img.shields.io/badge/Docker-Supported-blue.svg" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

Kahani (meaning "story" in Hindi) is a modern interactive storytelling platform that combines the power of AI with intuitive story management. Create, organize, and evolve your stories with AI assistance, configurable prompts, and a beautiful, responsive interface.

> **🚀 New here?** Check out the [5-Minute Quick Start Guide](QUICK_START.md) to get up and running fast!

## ✨ Features

- **🤖 AI-Powered Story Generation**: Integrate with multiple LLM providers (LM Studio, Ollama, OpenAI, Anthropic)
- **📝 Three-Tier Summary System**: Chapter summaries, story-so-far, and overall narrative summaries
- **�️ Text-to-Speech**: Optional audio narration with smart retry logic and progressive streaming
- **📱 Responsive Design**: Works seamlessly on desktop and mobile
- **🔐 User Authentication**: Secure JWT-based authentication system
- **💾 Auto-Save**: Automatic story and scene persistence
- **🎨 Context Management**: Track story context and token usage
- **🔄 Auto-Resume**: Automatically opens your last worked-on story
- **🐳 Docker Ready**: Easy deployment with Docker and Docker Compose
- **⌨️ Keyboard Navigation**: Navigate scenes with arrow keys (← previous, → regenerate)
- **🔄 Scene Regeneration**: Regenerate scenes you don't like with a single keypress
- **🎨 Customizable UI**: Toggle scene titles and customize display preferences
- **📜 Scene History**: Navigate back through scene versions with full history tracking

## 🚀 Quick Start

Choose your preferred installation method:

### 🐳 Docker Deployment (Recommended for Production)

**Fastest way to get started:**

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Copy environment template
cp .env.example .env
# Edit .env with your configuration (see Configuration section below)

# Start with SQLite (simplest)
docker-compose up -d

# OR: Start with PostgreSQL (production)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Access the application**: http://localhost:3000

📖 **Complete Docker guides**: 
- [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md) - Complete setup walkthrough
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Detailed deployment scenarios
- [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md) - Command reference

### 🔧 Native Installation (Recommended for Development)

**Automated installation script:**

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Run the installation script
chmod +x install.sh
./install.sh

# Start the application
./start-dev.sh
```

**That's it!** The installation script will:
- ✅ Install all system dependencies
- ✅ Set up Python 3.11 and Node.js 18+
- ✅ Create database with default users
- ✅ Generate secure configuration files
- ✅ Verify the installation

**Access the application**: http://localhost:3000

**Default login**: `test@test.com` / `test`

### � Installation Documentation

Choose the guide that fits your needs:

| Guide | Best For | Contents |
|-------|----------|----------|
| [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md) | **Overview & Quick Start** | All methods compared, success criteria, troubleshooting |
| [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md) | **Docker Users** | Complete Docker walkthrough with examples |
| [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) | **Production Deployment** | Detailed deployment scenarios, security, maintenance |
| [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md) | **Quick Commands** | Docker command reference, one-liners |

### Prerequisites

- **OS**: Linux (Ubuntu 20.04+), macOS (10.15+), or Windows 10+ with WSL2
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 2GB free space
- **Docker**: 20.10+ with Docker Compose 2.0+ (for Docker deployment)
- **LLM Server** (optional): [LM Studio](https://lmstudio.ai/) or [Ollama](https://ollama.ai/) for local AI

#### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

#### Backend Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/kahani.git
cd kahani

# Set up Python environment
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set up environment
cp ../.env.template ../.env
# Edit .env with your configuration

# Initialize database
python -c "from app.database import init_db; init_db()"

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup

```bash
# In a new terminal, navigate to frontend
cd frontend
npm install

# Start the development server
npm run dev
```

## 🔧 Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Database Configuration
DATABASE_URL=sqlite:///./data/kahani.db  # Or use PostgreSQL

# Security
SECRET_KEY=your-very-secure-secret-key-here-please-change
JWT_SECRET_KEY=your-super-secret-jwt-key-here-please-change-in-production

# LLM Configuration (LM Studio example)
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL=local-model

# TTS Configuration (Optional)
TTS_PROVIDER=openai  # or elevenlabs, azure
TTS_API_URL=https://api.openai.com/v1
TTS_API_KEY=your-tts-api-key

# Frontend Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### LLM Providers

Kahani supports multiple LLM providers:

#### LM Studio (Default - Local)
```bash
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL=local-model
```

#### Ollama (Local)
```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=llama2
```

#### OpenAI (Cloud)
```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-openai-api-key
LLM_MODEL=gpt-3.5-turbo
```

#### Anthropic Claude (Cloud)
```bash
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_API_KEY=your-anthropic-api-key
LLM_MODEL=claude-3-sonnet
```

### TTS Providers (Optional)

Enable text-to-speech narration:

#### OpenAI TTS
```bash
TTS_PROVIDER=openai
TTS_API_URL=https://api.openai.com/v1
TTS_API_KEY=your-openai-api-key
TTS_VOICE=alloy
```

#### ElevenLabs TTS
```bash
TTS_PROVIDER=elevenlabs
TTS_API_URL=https://api.elevenlabs.io/v1
TTS_API_KEY=your-elevenlabs-api-key
TTS_VOICE=your-voice-id
```

For complete configuration options, see [.env.example](.env.example)
```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=llama2
```

#### OpenAI
```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-openai-api-key
LLM_MODEL=gpt-3.5-turbo
```

#### Anthropic Claude
```bash
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_API_KEY=your-anthropic-api-key
LLM_MODEL=claude-3-sonnet
```

## 🐳 Docker Deployment

### Quick Start

```bash
# Standard deployment (SQLite)
docker-compose up -d

# Production deployment (PostgreSQL)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Development with hot reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Docker Services

| Service | Port | Description | Profile |
|---------|------|-------------|---------|
| **kahani-backend** | 8000 | FastAPI application server | default |
| **kahani-frontend** | 3000 | Next.js web application | default |
| **postgres** | 5432 | PostgreSQL database | default |
| **ollama** | 11434 | Ollama LLM service | llm |
| **redis** | 6379 | Redis cache | redis |
| **nginx** | 80, 443 | Nginx reverse proxy | proxy |

### Deployment Modes

#### 1. Development Mode (Hot Reload)
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```
- SQLite database
- Source code mounted as volumes
- Auto-reload on code changes
- Debug port exposed (5678)

#### 2. Standard Mode (SQLite)
```bash
docker-compose up -d
```
- SQLite database (in volume)
- Suitable for single-user or testing
- No additional services required

#### 3. Production Mode (PostgreSQL)
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
- PostgreSQL database
- Resource limits configured
- Non-root users
- Health checks enabled

#### 4. Full Stack (with Optional Services)
```bash
docker-compose --profile llm --profile redis --profile proxy up -d
```
- Includes Ollama for local LLM
- Includes Redis for caching
- Includes Nginx as reverse proxy

### Docker Documentation

📖 **Complete Docker guides**:
- [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md) - Complete setup walkthrough
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Detailed deployment guide with TTS, security, troubleshooting
- [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md) - Command reference and one-liners
- [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md) - Compare all installation methods

### Docker Commands Quick Reference

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f kahani-backend
docker-compose logs -f kahani-frontend

# Stop services
docker-compose down

# Rebuild after changes
docker-compose up -d --build

# Clean up everything
docker-compose down -v  # Warning: Removes volumes (data loss!)
```

For more commands and troubleshooting, see [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md)

## 📚 Usage

### Creating Your First Story

1. **Register/Login**: Create an account or log in with `test@test.com` / `test`
2. **New Story**: Click "New Story" to create your first story
3. **Configure Story**: Set genre, title, and initial context
4. **Add Scenes**: Click "Generate Scene" to create chapters with AI
5. **Navigate**: Use arrow keys (← previous, → regenerate) or click buttons
6. **Auto-Save**: All changes are automatically saved

### AI Features

#### Three-Tier Summary System
- **Chapter Summary**: Each chapter has its own AI-generated summary
- **Story So Far**: Cascading summary combining all previous chapters
- **Story Summary**: Overall narrative for the dashboard

Generate summaries:
- **Auto**: Automatically every N scenes (configurable in settings)
- **Manual**: Click "Generate Chapter Summary" or "Generate Story Summary" buttons in the sidebar

#### Scene Generation & Regeneration
- **New Scene**: Generate next chapter based on story context
- **Regenerate**: Don't like a scene? Press → or click "Regenerate" to try again
- **Scene History**: Navigate through all scene versions with ← →

#### Text-to-Speech (Optional)
- Enable TTS in settings (requires TTS provider configuration)
- Listen to scenes narrated with natural voices
- Progressive audio streaming for faster playback
- Smart retry logic handles network issues automatically

### Keyboard Shortcuts

- **← (Left Arrow)**: Previous scene or scene variant
- **→ (Right Arrow)**: Regenerate current scene
- **Escape**: Close modals/panels

### Settings & Customization

#### User Preferences
- **Auto-Open Last Story**: Automatically resume your last worked-on story
- **Show Scene Titles**: Toggle scene title visibility in the UI
- **Auto-Summary**: Configure automatic summary generation frequency

#### Prompt Templates
Create custom AI prompts for different story types:
1. Go to Settings → Prompt Templates
2. Click "New Prompt Template"
3. Name your template (e.g., "Sci-Fi Adventure", "Mystery Novel")
4. Write your prompt with context variables
5. Set as default for new stories

#### LLM Settings
- **Model Selection**: Choose your AI model
- **Temperature**: Control creativity (0.0 = focused, 1.0 = creative)
- **Max Tokens**: Set response length limits
- **Context Window**: Manage token usage tracking
## 🏗️ Development

### Project Structure

```
kahani/
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── api/         # API route handlers
│   │   ├── models/      # SQLAlchemy database models
│   │   ├── routers/     # API routers (stories, scenes, auth, TTS)
│   │   ├── services/    # Business logic services
│   │   └── utils/       # Utility functions
│   ├── requirements.txt # Python dependencies
│   └── Dockerfile       # Backend container image
├── frontend/             # Next.js application
│   ├── src/
│   │   ├── app/         # Next.js app router pages
│   │   ├── components/  # React components
│   │   ├── hooks/       # Custom React hooks (useTTS, etc.)
│   │   ├── lib/         # Utilities and API client
│   │   └── store/       # State management (Zustand)
│   ├── package.json     # Node.js dependencies
│   └── Dockerfile       # Frontend container image
├── docs/                 # Documentation
│   ├── context-management.md
│   ├── user-settings-guide.md
│   └── ...
├── docker-compose.yml    # Main Docker composition
├── docker-compose.prod.yml   # Production overrides
├── docker-compose.dev.yml    # Development overrides
├── .env.example         # Environment template
└── install.sh           # Automated installation script
```

### Development Workflow

#### Native Development

```bash
# Backend (auto-reload enabled)
cd backend
source ../.venv/bin/activate  # Or your virtualenv
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (hot reload enabled)
cd frontend
npm run dev

# View API docs
open http://localhost:8000/docs
```

#### Docker Development (with hot reload)

```bash
# Start with development overrides
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f

# Code changes will auto-reload!
```

### Running Tests

```bash
# Frontend tests
cd frontend
npm test
npm run test:watch  # Watch mode

# Backend tests
cd backend
source ../.venv/bin/activate
python -m pytest
python -m pytest -v  # Verbose
python -m pytest tests/test_api.py  # Specific file

# Coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Frontend
cd frontend
npm run lint          # ESLint
npm run lint:fix      # Auto-fix issues
npm run format        # Prettier formatting
npm run type-check    # TypeScript checking

# Backend
cd backend
black .               # Format Python code
flake8 .             # Linting
mypy app/            # Type checking
```

### API Documentation

When the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs - Interactive API testing
- **ReDoc**: http://localhost:8000/redoc - Beautiful API documentation
- **OpenAPI JSON**: http://localhost:8000/openapi.json - Raw API schema

### Database Management

```bash
# Initialize database
cd backend
python init_database.py

# Create backup
python backup_database.py

# Run migrations
python safe_migrate.py

# Check schema
python check_schema.py

# Reset database (WARNING: Data loss!)
python reset_database.py
```

For more database management, see [DATABASE_MANAGEMENT.md](backend/DATABASE_MANAGEMENT.md)

### VS Code Tasks

Use the built-in tasks for common operations:

1. **Start Backend Server** - Launch backend with auto-reload
2. **Start Frontend Server** - Launch frontend with hot reload
3. **Build Frontend** - Build production frontend
4. **Install Dependencies** - Install all dependencies

Access via: `Terminal → Run Task...` or `Cmd+Shift+P` → "Run Task"

### Adding New Features

1. **Backend API Endpoint**:
   - Add route in `backend/app/routers/`
   - Add model in `backend/app/models/`
   - Add business logic in `backend/app/services/`
   - Test in Swagger UI at `/docs`

2. **Frontend Component**:
   - Add component in `frontend/src/components/`
   - Add API call in `frontend/src/lib/api.ts`
   - Use custom hooks like `useTTS` for complex logic
   - Update Zustand store if needed in `frontend/src/store/`

3. **Database Model**:
   - Add model in `backend/app/models/`
   - Create migration script in `backend/alembic/versions/`
   - Run migration with `safe_migrate.py`
   - Update API endpoints to use new model

### Documentation

When adding features, update:
- This README for user-facing features
- API docstrings for backend changes
- Component comments for frontend changes
- Create/update docs in `docs/` for complex features

### Performance Optimization

See these guides for optimization tips:
- [TTS_RETRY_IMPROVEMENTS.md](TTS_RETRY_IMPROVEMENTS.md) - TTS performance details
- [CONTEXT_FIXES_SUMMARY.md](CONTEXT_FIXES_SUMMARY.md) - Context management
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Production optimization

## 🔍 Troubleshooting

### Common Issues

#### 1. LLM Connection Issues
**Symptom**: "Failed to connect to LLM server"
```bash
# Check if LM Studio/Ollama is running
curl http://localhost:1234/v1/models  # LM Studio
curl http://localhost:11434/api/tags   # Ollama

# Verify LLM_BASE_URL in .env matches your service
```

#### 2. Database Issues
**Symptom**: "Database locked" or connection errors
```bash
# For SQLite (development)
cd backend
python init_database.py

# For PostgreSQL (production)
docker-compose exec postgres psql -U kahani -d kahani -c "\dt"
```

#### 3. Port Conflicts
**Symptom**: "Address already in use"
```bash
# Check what's using the ports
lsof -i :3000  # Frontend
lsof -i :8000  # Backend

# Change ports in docker-compose.yml or .env if needed
```

#### 4. Docker Issues
**Symptom**: Container fails to start
```bash
# View detailed logs
docker-compose logs -f kahani-backend
docker-compose logs -f kahani-frontend

# Rebuild containers
docker-compose down
docker-compose up -d --build

# Check disk space
docker system df
docker system prune  # Clean up if needed
```

#### 5. TTS Issues
**Symptom**: Audio not playing or "chunk not found" errors
```bash
# Check TTS configuration in .env
TTS_PROVIDER=openai  # or elevenlabs
TTS_API_KEY=your-key-here

# Verify audio volume exists
docker-compose exec kahani-backend ls -la /app/data/audio

# Check logs for TTS errors
docker-compose logs -f kahani-backend | grep -i tts
```

### Docker-Specific Troubleshooting

See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md#troubleshooting) for:
- Database initialization issues
- Permission problems
- Network connectivity
- Volume mounting issues
- Performance optimization

### Installation Troubleshooting

See [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md#troubleshooting-matrix) for:
- Installation script errors
- Dependency conflicts
- Environment setup issues
- Platform-specific problems

### Getting Help

1. **Check Logs**:
   ```bash
   # Docker
   docker-compose logs -f
   
   # Native
   tail -f logs/kahani.log
   tail -f backend/logs/backend.log
   ```

2. **Enable Debug Mode**:
   ```bash
   # Add to .env
   DEBUG=true
   LOG_LEVEL=DEBUG
   ```

3. **API Documentation**: http://localhost:8000/docs (when backend is running)

4. **Community Support**:
   - [GitHub Issues](https://github.com/yourusername/kahani/issues) - Report bugs
   - [GitHub Discussions](https://github.com/yourusername/kahani/discussions) - Ask questions
   - Check existing issues for solutions

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### Development Setup

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/kahani.git`
3. Create a feature branch: `git checkout -b feature/amazing-feature`
4. Set up development environment (see Development section)
5. Make your changes
6. Run tests and linting
7. Commit your changes: `git commit -m 'Add amazing feature'`
8. Push to the branch: `git push origin feature/amazing-feature`
9. Open a Pull Request

### Contribution Guidelines

- **Code Style**: Follow existing code style (ESLint for TS/JS, Black for Python)
- **Tests**: Add tests for new features
- **Documentation**: Update relevant documentation
- **Commits**: Use clear, descriptive commit messages
- **Issues**: Reference related issues in PR description

For detailed guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md)

## 📖 Documentation

### Complete Documentation Index

| Document | Description |
|----------|-------------|
| **Installation & Setup** |
| [INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md) | Overview of all installation methods |
| [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md) | Complete Docker setup walkthrough |
| [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) | Detailed deployment scenarios |
| [DOCKER_QUICK_REFERENCE.md](DOCKER_QUICK_REFERENCE.md) | Docker command reference |
| **Features & Guides** |
| [docs/user-settings-guide.md](docs/user-settings-guide.md) | User preferences and settings |
| [docs/context-management.md](docs/context-management.md) | Story context and token usage |
| [docs/context-manager-explained.md](docs/context-manager-explained.md) | Context manager internals |
| **Technical Documentation** |
| [TTS_RETRY_IMPROVEMENTS.md](TTS_RETRY_IMPROVEMENTS.md) | TTS retry logic details |
| [CONTEXT_FIXES_SUMMARY.md](CONTEXT_FIXES_SUMMARY.md) | Context management fixes |
| [FEATURE_SUMMARY.md](FEATURE_SUMMARY.md) | Feature implementation summary |
| [backend/DATABASE_MANAGEMENT.md](backend/DATABASE_MANAGEMENT.md) | Database operations guide |
| **Development** |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |

## � License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Next.js](https://nextjs.org/) - React framework for production
- [LM Studio](https://lmstudio.ai/) - Local LLM hosting
- [Ollama](https://ollama.ai/) - Run large language models locally
- [Tailwind CSS](https://tailwindcss.com/) - Utility-first CSS framework
- [SQLAlchemy](https://sqlalchemy.org/) - Python SQL toolkit and ORM
- [Zustand](https://github.com/pmndrs/zustand) - State management for React

## 💬 Support & Community

- **Issues**: [GitHub Issues](https://github.com/yourusername/kahani/issues) - Report bugs or request features
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kahani/discussions) - Ask questions, share ideas
- **Documentation**: Check the [docs/](docs/) directory for guides
- **API Docs**: http://localhost:8000/docs (when running)

---

<p align="center">
  <strong>Kahani</strong> - Where stories come alive through AI collaboration! 🎭📚✨
</p>

<p align="center">
  Made with ❤️ for storytellers everywhere
</p>
