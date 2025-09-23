# Kahani - Interactive Storytelling Platform

Kahani is an AI-powered interactive storytelling application that allows users to create, explore, and collaborate on branching narratives. Built with Python FastAPI backend and Next.js frontend, it integrates with local LLM instances via LM Studio for story generation.

## 🚀 Features

- **Interactive Story Creation**: Create stories with customizable genres, tones, and world settings
- **AI-Powered Scene Generation**: Generate scenes and story continuations using local LLMs
- **Smart Context Management**: Handles long stories with intelligent context summarization
- **Branching Narratives**: Multiple story paths and choices for dynamic storytelling
- **Character Management**: Create and manage character templates and personalities
- **User Authentication**: Secure JWT-based authentication system
- **Privacy Controls**: Public and private story visibility options
- **Real-time Editing**: Edit AI-generated content inline
- **Local LLM Integration**: Works with LM Studio and OpenAI-compatible APIs
- **Token-Aware Processing**: Automatic context optimization for long stories

## 🏗️ Architecture

### Backend (FastAPI)
- **Framework**: Python 3.11+ with FastAPI
- **Database**: SQLAlchemy with SQLite (development) / PostgreSQL (production)
- **Authentication**: JWT tokens with secure password hashing
- **LLM Integration**: OpenAI-compatible API client for LM Studio
- **API Documentation**: Automatic OpenAPI/Swagger documentation

### Frontend (Next.js)
- **Framework**: Next.js 14 with TypeScript
- **Styling**: Tailwind CSS for responsive design
- **State Management**: Zustand for client-side state
- **Authentication**: Persistent auth state with JWT tokens
- **PWA Ready**: Progressive Web App capabilities

## 📋 Prerequisites

- Python 3.11+
- Node.js 18+
- LM Studio (for local LLM) or OpenAI API key
- Virtual environment tool (venv, conda, etc.)

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd kahani
```

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create data directory
mkdir -p data

# Set environment variables
export JWT_SECRET_KEY="your-super-secret-jwt-key-here-please-change-in-production"
export DATABASE_URL="sqlite:///./data/kahani.db"  # Optional: defaults to SQLite
```

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd ../frontend

# Install dependencies
npm install

# Create environment file (optional)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

### 4. LM Studio Setup

1. Download and install [LM Studio](https://lmstudio.ai/)
2. Download a compatible model (e.g., Mistral 7B, Llama 2, etc.)
3. Start the local server in LM Studio on `http://localhost:1234/v1`
4. Ensure the server is running and accessible

## 🚀 Running the Application

### Start Backend Server
```bash
cd backend
PYTHONPATH=/path/to/kahani/backend JWT_SECRET_KEY="your-secret-key" python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Start Frontend Server
```bash
cd frontend
npm run dev
```

### Access the Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## 📚 Usage

### 1. User Registration
- Create a new account at http://localhost:3000/register
- Or login with existing credentials at http://localhost:3000/login

### 2. Create Your First Story
- Click "Create New Story" on the dashboard
- Fill in story details: title, description, genre, tone, and setting
- Submit to create your story foundation

### 3. Generate Scenes
- Open your story and click "Generate First Scene"
- The AI will create an opening scene based on your story settings
- Continue generating scenes by selecting from AI-suggested options or providing custom prompts

### 4. Edit and Customize
- Click "Edit" on any scene to modify AI-generated content
- Add custom directions for specific story developments
- Create branching narratives with multiple story paths

### 5. Character Management
- Create character templates for consistent personalities
- Characters can be referenced across scenes and stories

## 🔧 Configuration

### Environment Variables

**Backend** (`.env` in backend directory):
```bash
JWT_SECRET_KEY=your-super-secret-jwt-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
DATABASE_URL=sqlite:///./data/kahani.db
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=local-model
DEBUG=false
```

**Frontend** (`.env.local` in frontend directory):
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### LM Studio Configuration
- Ensure LM Studio is running on `http://localhost:1234/v1`
- Use OpenAI-compatible API mode
- Recommended models: Mistral 7B, Llama 2 7B, or similar

## 🗃️ Database Schema

The application uses SQLAlchemy with the following main entities:

- **Users**: Authentication and user management
- **Stories**: Story metadata and settings
- **Scenes**: Individual story scenes with content
- **Characters**: Character templates and definitions
- **SceneChoices**: Branching narrative options

## 🔌 API Endpoints

### Authentication
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user

### Stories
- `GET /api/stories` - List user stories
- `POST /api/stories` - Create new story
- `GET /api/stories/{id}` - Get story details
- `PUT /api/stories/{id}` - Update story
- `DELETE /api/stories/{id}` - Delete story

### Scene Generation
- `POST /api/stories/{id}/generate-scene` - Generate new scene
- `POST /api/scenes/{id}/generate-choices` - Generate scene choices

### Characters
- `GET /api/characters` - List characters
- `POST /api/characters` - Create character
- `GET /api/characters/{id}` - Get character details

## 🐳 Docker Deployment

### Using Docker Compose
```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

### Individual Docker Builds
```bash
# Backend
cd backend
docker build -t kahani-backend .

# Frontend
cd frontend
docker build -t kahani-frontend .
```

## 📝 Development

### Context Management System

Kahani includes a sophisticated context management system for handling long stories:

- **Smart Truncation**: Automatically manages context size for LLM token limits
- **Progressive Summarization**: Summarizes older scenes while preserving recent context
- **Configurable Thresholds**: Adjustable settings for context management behavior

#### Context Configuration
```python
# In backend/app/config.py
context_max_tokens: int = 4000        # Maximum tokens to send to LLM
context_keep_recent_scenes: int = 3   # Always keep recent scenes
context_summary_threshold: int = 5    # Summarize when story has more scenes
```

#### Monitoring Context Usage
- Use `/stories/{story_id}/context-info` endpoint to analyze token usage
- Monitor when summarization is triggered
- Track context efficiency for optimization

See [Context Management Documentation](docs/context-management.md) for detailed information.

### Code Structure
```
kahani/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app entry point
│   │   ├── config.py        # Configuration settings
│   │   ├── models/          # SQLAlchemy models
│   │   ├── api/             # API route handlers
│   │   ├── services/        # Business logic
│   │   └── dependencies.py  # Dependency injection
│   ├── data/               # SQLite database storage
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js app directory
│   │   ├── lib/            # Utility functions
│   │   └── store/          # Zustand state management
│   ├── public/             # Static assets
│   └── package.json        # Node.js dependencies
└── docker-compose.yml      # Container orchestration
```

### Running Tests
```bash
# Backend tests
cd backend
python -m pytest tests/

# Frontend tests
cd frontend
npm test
```

### Linting and Formatting
```bash
# Backend
cd backend
black app/ tests/
flake8 app/ tests/

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