# 📚 Kahani - Interactive Storytelling Platform

[![GitHub Container Registry](https://img.shields.io/badge/ghcr-kahani-blue)](https://github.com/ncoder-ai/kahani/pkgs/container/kahani-backend)
[![Docker Build](https://github.com/ncoder-ai/kahani/actions/workflows/docker.yml/badge.svg)](https://github.com/ncoder-ai/kahani/actions/workflows/docker.yml)
[![License](https://img.shields.io/github/license/ncoder-ai/kahani)](LICENSE)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Node.js-22+-green.svg" alt="Node.js Version">
  <img src="https://img.shields.io/badge/FastAPI-Latest-teal.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-14-black.svg" alt="Next.js">
  <img src="https://img.shields.io/badge/Docker-Supported-blue.svg" alt="Docker">
</p>

Kahani (meaning "story" in Hindi) is a modern interactive storytelling platform that combines the power of AI with intuitive story management. Create, organize, and evolve your stories with AI assistance, configurable prompts, and a beautiful, responsive interface.

## 🐳 Quick Start with Pre-built Images (Recommended)

The fastest way to get started - no building required!

### Using Pre-built Images from GitHub Container Registry

```bash
# Download the pre-built docker-compose file
curl -O https://raw.githubusercontent.com/ncoder-ai/kahani/main/docker-compose.prebuilt.yml

# Start Kahani
docker-compose -f docker-compose.prebuilt.yml up -d
```

**Access the application**: http://localhost:6789

For more details, see [DOCKER_IMAGES.md](DOCKER_IMAGES.md).

---

> **🚀 New here?** Check out the [5-Minute Quick Start Guide](QUICK_START.md) to get up and running fast!

> **⚙️ Configuration Issues?** See the [Configuration Guide](CONFIGURATION_GUIDE.md) for setup and troubleshooting.

## ✨ Features

### 🤖 **AI-Powered Story Generation**
- **Multiple LLM Providers**: LM Studio, Ollama, OpenAI, Anthropic, and more
- **Local AI Support**: Run completely offline with local models
- **Smart Context Management**: Automatic context optimization and token management
- **Semantic Memory**: AI-powered story memory and character tracking

### 📝 **Advanced Story Management**
- **Three-Tier Summary System**: Chapter summaries, story-so-far, and overall narrative summaries
- **Character Management**: Create, edit, and track characters throughout your story
- **Plot Thread Tracking**: Follow multiple storylines and plot developments
- **Entity State Management**: Track character relationships and story world consistency

### 🎵 **Text-to-Speech Integration**
- **Multiple TTS Providers**: OpenAI, Kokoro, Chatterbox, and custom providers
- **Progressive Streaming**: Real-time audio generation and playback
- **Voice Persistence**: Remember character voices across sessions
- **WebSocket Support**: Real-time audio streaming with retry logic

### 🎨 **User Experience**
- **Responsive Design**: Works seamlessly on desktop and mobile
- **Keyboard Navigation**: Navigate scenes with arrow keys (← previous, → regenerate)
- **Scene Regeneration**: Regenerate scenes you don't like with a single keypress
- **Scene History**: Navigate back through scene versions with full history tracking
- **Auto-Save**: Automatic story and scene persistence
- **Auto-Resume**: Automatically opens your last worked-on story

### 🔐 **Security & Authentication**
- **JWT Authentication**: Secure token-based authentication
- **User Management**: Registration, login, and user settings
- **Admin Panel**: User management and system configuration

### 🐳 **Deployment**
- **Docker Ready**: Easy deployment with Docker and Docker Compose
- **Network Configuration**: Automatic network detection for local development
- **Environment Management**: Template-based configuration system
- **Production Ready**: Nginx configuration and production optimizations

## 🚀 Quick Start

### **🐳 Docker Deployment (Recommended)**

The easiest way to get started with Kahani is using Docker:

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Start with Docker
docker-compose up -d
```

**That's it!** Docker will:
- ✅ Automatically build and start all services
- ✅ Handle networking between frontend and backend
- ✅ Download AI models during first build
- ✅ Set up the database automatically

**Access the application**: http://localhost:6789

### **🖥️ Baremetal Installation (Advanced)**

For development or custom deployments:

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Install the application
./install.sh

# Start the development server
./start-dev.sh
```

**That's it!** The setup script will:
- ✅ Create environment configuration from template
- ✅ Auto-detect network configuration
- ✅ Download AI models (one-time setup)
- ✅ Start both frontend and backend servers

**Access the application**: http://localhost:6789

### **⚙️ Manual Setup (Expert)**

```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Install the application
./install.sh

# Start backend
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 9876

# Start frontend (in another terminal)
cd frontend && npm run dev
```

## ⚙️ Configuration

### **Environment Setup**

The application uses a template-based configuration system:

```bash
# Install the application (creates .env from .env.example)
./install.sh

# Validate configuration
./validate-config.sh
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

# Run migrations
cd backend && alembic upgrade head

# Backup database
cd backend && python backup_database.py
```

## 🐳 Docker Deployment

### **Why Docker?**

Docker is the **recommended** way to run Kahani because it:
- 🚀 **Zero Configuration**: No need to install Python, Node.js, or manage dependencies
- 🔒 **Isolated Environment**: Prevents conflicts with your system packages
- 🌐 **Network Ready**: Automatically handles frontend-backend communication
- 📦 **Self-Contained**: Includes all AI models and dependencies
- 🔄 **Easy Updates**: Simple `git pull` and `docker-compose up` to update

### **Quick Start with Docker**

```bash
# Clone and start
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### **Production Deployment**

```bash
# For production with custom domain
# Edit .env file with your domain
docker-compose up -d

# Check status
docker-compose ps
```

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [QUICK_START.md](QUICK_START.md) | 5-minute setup guide |
| [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) | Complete configuration guide |
| [NETWORK_CONFIGURATION.md](NETWORK_CONFIGURATION.md) | Network setup and troubleshooting |
| [docs/](docs/) | Detailed feature documentation |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License - see the [LICENSE](LICENSE) file for details.

**Important:** This license prohibits commercial use. You may use, share, and modify the software for non-commercial purposes only.

## 🙏 Acknowledgments

- **FastAPI** for the excellent Python web framework
- **Next.js** for the React framework
- **Tailwind CSS** for styling
- **ChromaDB** for vector storage
- **LiteLLM** for LLM provider abstraction
- **All the AI model providers** for making this possible

---

**Made with ❤️ for storytellers everywhere**