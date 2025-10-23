# 🚀 Kahani Quick Start Guide

Get Kahani running in **under 5 minutes** with Docker!

## 🐳 Docker Installation (Recommended)

### Prerequisites
- Docker and Docker Compose installed
- Git installed

### Step 1: Clone and Setup
```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Set up environment configuration
./setup-env.sh
```

### Step 2: Start with Docker
```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

### Step 3: Access the Application
- **Frontend**: http://localhost:6789
- **Backend API**: http://localhost:9876
- **API Documentation**: http://localhost:9876/docs

**That's it!** 🎉

---

## 🖥️ Baremetal Installation (Advanced)

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### Step 1: Clone and Setup
```bash
# Clone the repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Set up environment
./setup-env.sh
```

### Step 2: Install Dependencies
```bash
# Backend dependencies
cd backend
pip install -r requirements.txt

# Frontend dependencies
cd ../frontend
npm install
```

### Step 3: Start Development Server
```bash
# Start both frontend and backend
./start-dev.sh
```

### Step 4: Access the Application
- **Frontend**: http://localhost:6789
- **Backend API**: http://localhost:9876

---

## ⚙️ Configuration

### LLM Setup
Edit `.env` file to configure your AI model:

```bash
# For LM Studio (local)
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=your-model-name

# For OpenAI (cloud)
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4
```

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
- **Port conflicts**: Change ports in `.env` file
- **Model download**: First run downloads AI models (~200MB)
- **Database**: Automatically created on first run

---

## 📚 Next Steps

- **Configuration Guide**: See `CONFIGURATION_GUIDE.md` for detailed setup
- **Network Setup**: See `NETWORK_CONFIGURATION.md` for remote access
- **Documentation**: Check `docs/` folder for feature guides

---

## 🆘 Need Help?

- **Issues**: [GitHub Issues](https://github.com/ncoder-ai/kahani/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ncoder-ai/kahani/discussions)
- **Documentation**: Check the `docs/` folder

---

**Happy storytelling!** 📖✨