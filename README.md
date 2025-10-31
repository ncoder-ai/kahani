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

> **🔒 Production Deployment?** Review the [Security Setup Guide](docs/SECURITY_SETUP.md) and [Security Checklist](docs/SECURITY_CHECKLIST.md) before deploying.

> **⚙️ Configuration Issues?** See the [Configuration Guide](CONFIGURATION_GUIDE.md) for setup and troubleshooting.

## ✨ Features

### 🤖 **AI-Powered Story Generation**
- **Multiple LLM Providers**: LM Studio, Ollama, OpenAI, Anthropic, and more
- **Local AI Support**: Run completely offline with local models
- **Smart Context Management**: Automatic context optimization and token management
- **Semantic Memory**: AI-powered story memory and character tracking
- **Hybrid Context Strategies**: Combine recent scenes with semantically relevant moments
- **Character-Aware Context**: Intelligent retrieval based on character relationships
- **Plot Thread Continuity**: Track and maintain consistency across multiple storylines

### 📝 **Advanced Story Management**
- **Three-Tier Summary System**: Chapter summaries, story-so-far, and overall narrative summaries
- **Character Management**: Create, edit, and track characters throughout your story
- **Plot Thread Tracking**: Follow multiple storylines and plot developments
- **Entity State Management**: Track character relationships and story world consistency
- **Scene History**: Navigate back through scene versions with full history tracking
- **Auto-Save**: Automatic story and scene persistence
- **Auto-Resume**: Automatically opens your last worked-on story

### 🎭 **Character Generation Wizard**
- **AI Character Suggestions**: Automatically detect and suggest characters from your story
- **Intelligent Character Analysis**: AI-powered character detail extraction with personality traits, background, goals, and fears
- **Role-Based Organization**: Assign character roles (protagonist, antagonist, mentor, etc.) with visual indicators
- **Character Wizard Interface**: Step-by-step guided character creation process
- **Character Memory Service**: Track character development and relationships across scenes
- **Character Importance Detection**: Automatically identify significant characters worth tracking

### 🎵 **Text-to-Speech Integration**
- **Multiple TTS Providers**: OpenAI, Kokoro, Chatterbox, and custom providers
- **Progressive Streaming**: Real-time audio generation and playback
- **Voice Persistence**: Remember character voices across sessions
- **WebSocket Support**: Real-time audio streaming with retry logic
- **Auto-Narration**: Automatically narrate newly generated scenes
- **Smart Text Chunking**: Intelligent paragraph-aware chunking for natural narration
- **Audio Caching**: Efficient storage and playback of generated audio

### 🎤 **Speech-to-Text Integration**
- **Real-time Transcription**: Whisper-based STT with faster-whisper engine
- **GPU/CPU Auto-Detection**: Automatic device selection with CPU fallback
- **WebSocket Streaming**: Low-latency audio processing via WebSocket
- **Voice Activity Detection**: Automatic speech detection with Silero VAD
- **Performance Metrics**: Real-time latency, accuracy, and throughput tracking
- **Dynamic Buffering**: Intelligent buffering with silence detection
- **Sentence Boundary Detection**: Natural text segmentation for better transcription quality

### 🧠 **Semantic Context & Memory**
- **Semantic Search**: Find relevant scenes and moments using natural language queries
- **Hybrid Context Assembly**: Combine recent scenes with semantically relevant moments
- **Character Moment Extraction**: Automatically extract and track significant character moments
- **Plot Event Tracking**: Identify and track important plot developments
- **Context Strategy Options**: Choose between linear, hybrid, or semantic-only context strategies
- **Token-Efficient Context**: Intelligent context selection to maximize relevant information
- **Embedding-Based Retrieval**: Vector search for finding related story elements

### 🎨 **User Experience**
- **Responsive Design**: Works seamlessly on desktop and mobile
- **Keyboard Navigation**: Navigate scenes with arrow keys (← previous, → regenerate)
- **Scene Regeneration**: Regenerate scenes you don't like with a single keypress
- **Theme Customization**: Dark/Light/Auto themes with customizable color schemes
- **Customizable Settings**: LLM parameters, context management, generation preferences
- **Writing Style Presets**: Pre-configured settings for different writing styles
- **Comprehensive Settings Modal**: Single unified interface for all configuration options

### 🔐 **Security & Authentication**
- **JWT Authentication**: Secure token-based authentication with configurable expiration
- **User Management**: Registration, login, and user settings
- **Admin Panel**: User management, permissions, and system configuration
- **CORS Protection**: Configurable cross-origin resource sharing
- **Production Ready**: Security best practices and deployment guides
- **📖 See [Security Setup Guide](docs/SECURITY_SETUP.md) for production deployment**

### 🐳 **Deployment**
- **Docker Ready**: Easy deployment with Docker and Docker Compose
- **Network Configuration**: Automatic network detection for local development
- **Environment Management**: Template-based configuration system
- **Production Ready**: Nginx configuration and production optimizations

## 🚀 Quick Start

### **Option 1: Automated Setup (Recommended)**

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Install dependencies and set up environment
./install.sh

# Start the development server
./start-dev.sh
```

**That's it!** The setup script will:
- ✅ Create Python virtual environment
- ✅ Install backend and frontend dependencies
- ✅ Create environment configuration with secure secrets
- ✅ Download AI models (one-time setup)
- ✅ Set up database
- ✅ Start both frontend and backend servers

**Access the application**: http://localhost:6789

### **Option 2: Docker Deployment**

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Create .env file with secrets (required for Docker)
# Generate secrets:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Create .env file (if .env.example exists, copy it first)
# Then add the generated secrets above to your .env file
# Or manually create .env with:
# SECRET_KEY=your-generated-secret-key-here
# JWT_SECRET_KEY=your-generated-jwt-secret-key-here

# Start with Docker
docker-compose up -d
```

**Note:** Docker Compose requires `SECRET_KEY` and `JWT_SECRET_KEY` environment variables. See [Security Setup Guide](docs/SECURITY_SETUP.md) for details.

**Access the application**: http://localhost:6789

### **Option 3: Manual Setup**

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Create Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install backend dependencies
cd backend && pip install -r requirements.txt && cd ..

# Install frontend dependencies
cd frontend && npm install && cd ..

# Set up environment (creates .env from .env.example if it exists)
# Or manually create .env with required variables
# Generate secrets if needed:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Initialize database
cd backend && alembic upgrade head && cd ..

# Start backend (keep virtual environment activated)
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 9876

# Start frontend (in another terminal)
cd frontend && npm run dev
```

## ⚙️ Configuration

### **Environment Setup**

The application uses a template-based configuration system:

```bash
# For baremetal: install.sh creates .env automatically with secure secrets
# For Docker: You need to create .env manually with secrets (see Docker section above)

# Validate configuration
./validate-config.sh
```

**Note:** The `setup-env.sh` script creates a basic `.env` file from `.env.example` template, but doesn't generate secure secrets. For production use, always generate your own secrets using:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"
```

### **Network Configuration**

Kahani automatically detects network configuration for different deployment scenarios:

- **Development**: Auto-detects network IP for local network access
- **Docker**: Uses container networking
- **Production**: Uses environment variables

### **LLM Configuration**

Configure your AI model in `.env`:

```bash
# Local LLM Server (Ollama, LM Studio, etc.)
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=local-model

# Or use cloud providers
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4
```

### **TTS Configuration**

Configure text-to-speech in the application settings:

- **OpenAI TTS**: High-quality voices with API key
- **Kokoro TTS**: Ultrafast TTS
- **Chatterbox**: Local TTS with custom voices
- **Custom Providers**: Add your own TTS providers

## 📁 Project Structure

```
kahani/
├── README.md                    # This file
├── QUICK_START.md              # Quick start guide
├── CONFIGURATION_GUIDE.md      # Configuration documentation
├── NETWORK_CONFIGURATION.md    # Network setup guide
├── config.yaml                 # Main application configuration
├── .env.example                # Environment variables template
├── setup-env.sh               # Environment setup script
├── validate-config.sh         # Configuration validation
├── start-dev.sh               # Development server
├── start-prod.sh              # Production server
├── install.sh                 # Installation script
├── backend/                   # Backend API (FastAPI)
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   ├── models/           # Database models
│   │   ├── services/         # Business logic
│   │   └── utils/            # Utilities
│   └── requirements.txt       # Python dependencies
├── frontend/                  # Frontend (Next.js)
│   ├── src/
│   │   ├── app/             # Next.js app router
│   │   ├── components/      # React components
│   │   └── lib/             # Utilities
│   └── package.json         # Node.js dependencies
├── docs/                     # Documentation
└── docker-compose.yml        # Docker configuration
```

## 🔧 Development

### **Prerequisites**

- **Python 3.11+**
- **Node.js 18+**
- **Git**
- **LLM Server** (optional): [LM Studio](https://lmstudio.ai/) or [Ollama](https://ollama.ai/)

### **Development Workflow**

```bash
# Start development server
./start-dev.sh

# Validate configuration
./validate-config.sh

# Check logs
tail -f logs/kahani.log
```

### **Database Management**

```bash

# Initialize database
cd backend && python init_database.py

# Upgrade database schema (run Alembic migrations)
cd backend && alembic upgrade head

# Backup database
cd backend && python backup_database.py
```

## 🐳 Docker Deployment

### **Development**

```bash
# Start with Docker
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### **Production**

```bash
# Start production services
docker-compose -f docker-compose.network.yml up -d

# With custom configuration
KAHANI_ENV=production docker-compose -f docker-compose.network.yml up -d
```

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [QUICK_START.md](QUICK_START.md) | 5-minute setup guide |
| [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) | Production deployment guide |
| [docs/SECURITY_SETUP.md](docs/SECURITY_SETUP.md) | 🔒 Security configuration and secrets |
| [docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) | 🔒 Pre/post-deployment security checklist |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | Complete configuration guide |
| [NETWORK_CONFIGURATION.md](NETWORK_CONFIGURATION.md) | Network setup and troubleshooting |
| [docs/REVERSE_PROXY_GUIDE.md](docs/REVERSE_PROXY_GUIDE.md) | Nginx, Caddy, and NPM configuration |
| [docs/database-migration-troubleshooting.md](docs/database-migration-troubleshooting.md) | Database migration issues and fixes |
| [docs/](docs/) | Detailed feature documentation |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **FastAPI** for the excellent Python web framework
- **Next.js** for the React framework
- **Tailwind CSS** for styling
- **ChromaDB** for vector storage
- **LiteLLM** for LLM provider abstraction
- **All the AI model providers** for making this possible

---

**Made with ❤️ for storytellers everywhere**