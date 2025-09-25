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

## ✨ Features

- **🤖 AI-Powered Story Generation**: Integrate with multiple LLM providers (LM Studio, Ollama, OpenAI, Anthropic)
- **📝 Interactive Story Management**: Create, edit, and organize stories with scenes
- **🎯 Configurable AI Prompts**: Customize AI behavior with your own prompt templates
- **📱 Responsive Design**: Works seamlessly on desktop and mobile
- **🔐 User Authentication**: Secure JWT-based authentication system
- **💾 Auto-Save**: Automatic story and scene persistence
- **🎨 Context Management**: Track story context and token usage
- **🔄 Auto-Resume**: Automatically opens your last worked-on story
- **� Docker Ready**: Easy deployment with Docker and Docker Compose
- **⌨️ Keyboard Navigation**: Navigate scenes with arrow keys (← previous, → regenerate)
- **🔄 Scene Regeneration**: Regenerate scenes you don't like with a single keypress
- **🎨 Customizable UI**: Toggle scene titles and customize display preferences
- **📜 Scene History**: Navigate back through scene versions with full history tracking

## 🚀 Quick Start

### Option 1: One-Command Install (Linux/macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/kahani/main/install.sh | bash
```

### Option 2: Docker Compose (Recommended for Production)

```bash
git clone https://github.com/yourusername/kahani.git
cd kahani
cp .env.template .env
# Edit .env with your configuration
docker-compose up -d
```

### Option 3: Manual Installation

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

Copy `.env.template` to `.env` and customize:

```bash
# Core settings
SECRET_KEY=your-very-secure-secret-key-here
DATABASE_URL=sqlite:///./data/kahani.db

# LLM Configuration
LLM_BASE_URL=http://localhost:1234/v1  # LM Studio
LLM_API_KEY=not-needed-for-local
LLM_MODEL=local-model
```

### LLM Providers

Kahani supports multiple LLM providers:

#### LM Studio (Default)
```bash
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL=local-model
```

#### Ollama
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

### Basic Setup

```bash
git clone https://github.com/yourusername/kahani.git
cd kahani
cp .env.template .env
docker-compose up -d
```

### Production Setup with Optional Services

```bash
# Full stack with PostgreSQL, Ollama, Redis, and Nginx
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Docker Services

- **kahani-backend**: FastAPI application server
- **kahani-frontend**: Next.js application
- **postgres** (optional): PostgreSQL database
- **ollama** (optional): Ollama LLM service
- **redis** (optional): Redis cache
- **nginx** (optional): Nginx reverse proxy

## 📚 Usage

### Creating Your First Story

1. **Register/Login**: Create an account or log in
2. **New Story**: Click "New Story" to create your first story
3. **Add Scenes**: Use "New Scene" to add chapters to your story
4. **AI Assistance**: Use the "AI Summary" feature to generate summaries
5. **Customize Prompts**: Go to Settings to create custom AI prompt templates

### AI Features

- **Story Summaries**: Generate AI summaries of your scenes
- **Custom Prompts**: Create and manage your own AI prompt templates
- **Context Tracking**: Monitor token usage and story context
- **Auto-Generation**: Let AI help continue your stories

### Settings & Customization

- **Prompt Templates**: Create custom AI prompts for different story types
- **Auto-Open**: Configure which story opens automatically
- **Theme**: Customize the interface appearance
- **LLM Settings**: Adjust AI generation parameters
## 🏗️ Development

### Project Structure

```
kahani/
├── backend/           # FastAPI application
│   ├── app/
│   │   ├── api/      # API routes
│   │   ├── models/   # Database models
│   │   ├── services/ # Business logic
│   │   └── core/     # Core utilities
│   └── requirements.txt
├── frontend/          # Next.js application
│   ├── src/
│   │   ├── app/      # App router pages
│   │   ├── components/ # React components
│   │   └── lib/      # Utilities
│   └── package.json
├── docker-compose.yml # Docker configuration
└── install.sh        # Installation script
```

### Development Workflow

```bash
# Start backend in development mode
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start frontend in development mode
cd frontend
npm run dev

# Run tests
npm test                    # Frontend tests
cd backend && python -m pytest  # Backend tests
```

### API Documentation

When running, visit:
- **FastAPI Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔍 Troubleshooting

### Common Issues

1. **LLM Connection Issues**
   - Ensure your LLM service is running
   - Check the `LLM_BASE_URL` in your `.env` file
   - Verify API keys for cloud providers

2. **Database Issues**
   - Run database initialization: `python -c "from app.database import init_db; init_db()"`
   - Check database permissions
   - For PostgreSQL, ensure the service is running

3. **Port Conflicts**
   - Backend runs on port 8000
   - Frontend runs on port 3000
   - Change ports in docker-compose.yml if needed

4. **Docker Issues**
   - Ensure Docker and Docker Compose are installed
   - Check that ports 3000 and 8000 are available
   - Run `docker-compose logs` to see detailed logs

### Getting Help

- Check the [Issues](https://github.com/yourusername/kahani/issues) for known problems
- Review the API documentation at `/docs`
- Enable debug mode by setting `DEBUG=true` in `.env`

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Run tests: `npm test` and `python -m pytest`
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/) and [Next.js](https://nextjs.org/)
- AI integration powered by various LLM providers
- Inspired by the art of storytelling

## � Support

- **Documentation**: [Wiki](https://github.com/yourusername/kahani/wiki)
- **Issues**: [GitHub Issues](https://github.com/yourusername/kahani/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kahani/discussions)

---

<p align="center">Made with ❤️ for storytellers everywhere</p>


# Frontend
cd frontend
npm run lint
npm run format
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) for the excellent Python web framework
- [Next.js](https://nextjs.org/) for the React framework
- [LM Studio](https://lmstudio.ai/) for local LLM hosting
- [Tailwind CSS](https://tailwindcss.com/) for styling
- [SQLAlchemy](https://sqlalchemy.org/) for database ORM

## 🐛 Troubleshooting

### Common Issues

1. **Backend won't start**: Ensure JWT_SECRET_KEY environment variable is set
2. **Frontend build errors**: Check Node.js version (requires 18+)
3. **LM Studio connection failed**: Verify LM Studio is running on port 1234
4. **Database errors**: Ensure data directory exists and has write permissions

### Getting Help

- Check the [API documentation](http://localhost:8000/docs) when backend is running
- Review application logs in the terminal output
- Ensure all environment variables are properly set
- Verify LM Studio is running and accessible

---

**Kahani** - Where stories come alive through AI collaboration! 🎭📚✨