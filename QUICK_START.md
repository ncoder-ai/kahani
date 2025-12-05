# 🚀 Kahani Quick Start Guide

Get Kahani running in **under 5 minutes** with Docker!

## 🐳 Docker Installation (Recommended)

### Prerequisites
- Docker and Docker Compose installed
- Git installed

### Step 1: Clone Repository
```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
```

### Step 2: Create .env File with Secrets
```bash
# Generate secrets
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Create .env file with the generated secrets
# If .env.example exists, copy it first:
# cp .env.example .env
# Then edit .env and add the generated secrets above
# Or manually create .env:
cat > .env << EOF
SECRET_KEY=your-generated-secret-key-here
JWT_SECRET_KEY=your-generated-jwt-secret-key-here
EOF
```

**Important:** Replace `your-generated-secret-key-here` with the actual generated secrets above.

### Step 3: Start with Docker
```bash
docker-compose up -d
```

### Step 4: Check Status
```bash
# Check status
docker-compose ps
```

### Step 5: Access the Application
- **Frontend**: http://localhost:6789
- **Backend API**: http://localhost:9876
- **API Documentation**: http://localhost:9876/docs

**That's it!** 🎉

### Using PostgreSQL (Optional)

By default, Kahani uses SQLite. For production or better performance, you can use PostgreSQL:

1. **Edit `.env` file** and add PostgreSQL credentials:
   ```bash
   POSTGRES_USER=kahani
   POSTGRES_PASSWORD=your_secure_password_here
   POSTGRES_DB=kahani
   DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
   ```

2. **Edit `docker-compose.yml`**:
   - Uncomment the `postgres` service (remove `#` from lines 42-58)
   - Uncomment the `depends_on` section in the `backend` service (lines 88-90)
   - Uncomment the `volumes` section at the bottom (line 117)

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

The backend will automatically detect PostgreSQL and use it instead of SQLite.

---

## 🖥️ Baremetal Installation (Advanced)

### Prerequisites
- Python 3.11+
- Node.js 20.9.0+ (required for Next.js 16)
- npm 10+ (comes with Node.js 20.9.0+)
- Git

### Step 1: Clone and Install
```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Install the application
./install.sh
```

### Step 2: Start Development Server
```bash
# Start both frontend and backend
./start-dev.sh
```

### Step 3: Access the Application
- **Frontend**: http://localhost:6789
- **Backend API**: http://localhost:9876

---

## ⚙️ Configuration

### LLM Setup
Configure your AI model through the application Settings:

1. Go to **Settings** → **LLM Settings**
2. Enter your LLM API URL (e.g., `http://localhost:1234/v1` for local models like LM Studio or Ollama)
3. Select your API type (OpenAI-compatible, Ollama, etc.)
4. Enter your model name and API key (if required)

**Note:** LLM configuration is stored per-user. Each user configures their own LLM settings through the web interface.

### Local Extraction Model (Optional)
Reduce costs by using a small local model for plot event extraction:

1. Set up an OpenAI-compatible inference server (LM Studio, Ollama, etc.)
2. Go to **Settings** → **Context Settings** → **Local Extraction Model**
3. Select a preset (LM Studio, Ollama, etc.) or configure custom endpoint
4. Test connection and enable extraction model
5. Extraction will use local model, story generation uses your main LLM

**See [Extraction Model Setup Guide](docs/EXTRACTION_MODEL_SETUP.md) for detailed instructions.**

### TTS Setup
Configure text-to-speech in the application:
1. Go to **Settings** → **TTS Settings**
2. Choose your TTS provider
3. Configure voice and speed preferences

---

## 🎯 First Steps

1. **Register an account** at http://localhost:6789
2. **Create your first story**
3. **Generate a scene** with AI assistance
4. **Try the TTS feature** to hear your story narrated
5. **Explore character management** and story organization

---

## 🔧 Troubleshooting

### Docker Issues
```bash
# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Rebuild if needed
docker-compose build --no-cache
```

### Baremetal Issues
```bash
# Check backend logs
tail -f backend/logs/kahani.log

# Verify dependencies
cd backend && pip list
cd frontend && npm list
```

### Common Issues
- **Port conflicts**: Change ports in `config.yaml` (under `server.backend.port` and `server.frontend.port`)
- **Model download**: First run downloads AI models (~200MB)
- **Database**: Automatically created on first run (SQLite by default, PostgreSQL if configured)
- **PostgreSQL connection**: If using PostgreSQL, ensure the postgres service is healthy before backend starts
- **Configuration**: All settings are in `config.yaml`, only secrets go in `.env`

---

## 📚 Next Steps

- **Configuration Guide**: See `CONFIGURATION_GUIDE.md` for detailed setup
- **Documentation**: Check `docs/` folder for feature guides

---

## 🆘 Need Help?

- **Issues**: [GitHub Issues](https://github.com/ncoder-ai/kahani/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ncoder-ai/kahani/discussions)
- **Documentation**: Check the `docs/` folder

---

**Happy storytelling!** 📖✨