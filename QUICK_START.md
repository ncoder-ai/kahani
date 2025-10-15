# 🚀 Kahani - 5-Minute Quick Start Guide

Get Kahani running in under 5 minutes with this step-by-step guide.

---

## 🎯 Choose Your Path

### Path 1: Docker (Easiest - Recommended) 🐳

**Best for**: Anyone who wants the fastest setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/kahani.git
cd kahani

# 2. Configure environment
cp .env.example .env
# Open .env and set your LLM URL (see Configuration below)

# 3. Start everything
docker-compose up -d

# 4. Wait ~30 seconds for startup, then open:
# http://localhost:3000
```

**That's it!** Login with: `test@test.com` / `test`

### Path 2: Native Installation (For Developers) 💻

**Best for**: Developers who want full control

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/kahani.git
cd kahani

# 2. Run the installer
chmod +x install.sh
./install.sh

# 3. Start the app
./start-dev.sh

# 4. Open:
# http://localhost:3000
```

**That's it!** Login with: `test@test.com` / `test`

---

## 🔧 Essential Configuration

### Step 1: Choose Your LLM Provider

Edit `.env` and set ONE of these options:

#### Option A: LM Studio (Local, Free) ⭐ **Recommended for Beginners**
```bash
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=local-model
```

**Setup LM Studio**:
1. Download from https://lmstudio.ai/
2. Download a model (try "llama-2-7b-chat")
3. Click "Start Server" in LM Studio
4. Use port 1234 (default)

#### Option B: Ollama (Local, Free)
```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=llama2
```

**Setup Ollama**:
1. Install from https://ollama.ai/
2. Run: `ollama pull llama2`
3. Run: `ollama serve`

#### Option C: OpenAI (Cloud, Paid)
```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-api-key-here
LLM_MODEL=gpt-3.5-turbo
```

Get API key from: https://platform.openai.com/api-keys

### Step 2: Optional - Enable Text-to-Speech 🎙️

**Skip this if you just want to test the app!**

To enable audio narration, add to `.env`:

```bash
TTS_PROVIDER=openai
TTS_API_URL=https://api.openai.com/v1
TTS_API_KEY=sk-your-api-key-here
TTS_VOICE=alloy
```

---

## 🎮 Using Kahani

### 1. Login
- Open http://localhost:3000
- Login with: `test@test.com` / `test`

### 2. Create Your First Story
1. Click **"New Story"** button
2. Fill in:
   - **Title**: Your story name
   - **Genre**: Fantasy, Sci-Fi, Mystery, etc.
   - **Initial Context**: Brief description of your story world
3. Click **"Create Story"**

### 3. Generate Scenes
1. Click **"Generate Scene"** button
2. Wait for AI to create the first scene
3. Read the scene
4. Click **"Generate Scene"** again for next chapter
5. Don't like a scene? Click **"Regenerate"** or press **→** key

### 4. Use Summaries
- **Chapter Summary**: Auto-generates every 5 scenes (or click button)
- **Story So Far**: Click button in sidebar for full narrative summary
- **Dashboard**: See story summary on main page

### 5. Keyboard Shortcuts
- **← (Left)**: Previous scene
- **→ (Right)**: Regenerate current scene
- **Esc**: Close panels

---

## 📊 Verify Everything Works

### ✅ Checklist

Run these checks to ensure everything is working:

#### Backend
```bash
# Should return: {"status":"healthy"}
curl http://localhost:8000/health

# Should show API docs
open http://localhost:8000/docs
```

#### Frontend
```bash
# Should show the login page
open http://localhost:3000
```

#### Docker (if using Docker)
```bash
# All should show "Up" status
docker-compose ps

# Should show no errors
docker-compose logs kahani-backend | grep -i error
docker-compose logs kahani-frontend | grep -i error
```

#### LLM Connection
```bash
# For LM Studio
curl http://localhost:1234/v1/models

# For Ollama
curl http://localhost:11434/api/tags

# Should show your models
```

---

## 🚨 Troubleshooting

### "Cannot connect to LLM"
**Problem**: Kahani can't reach your AI model  
**Fix**:
1. Make sure LM Studio or Ollama is running
2. Check `LLM_BASE_URL` in `.env` matches your service
3. Test connection: `curl http://localhost:1234/v1/models`

### "Port already in use"
**Problem**: Port 3000 or 8000 already taken  
**Fix**:
```bash
# Find what's using the port
lsof -i :3000
lsof -i :8000

# Kill the process or change ports in .env:
BACKEND_PORT=8001
FRONTEND_PORT=3001
```

### "Docker container won't start"
**Problem**: Container crashes or won't start  
**Fix**:
```bash
# View detailed logs
docker-compose logs -f

# Rebuild containers
docker-compose down
docker-compose up -d --build

# Check disk space
docker system df
```

### "Database error"
**Problem**: Database locked or corrupted  
**Fix**:
```bash
# Native installation
cd backend
python init_database.py

# Docker
docker-compose exec kahani-backend python init_database.py
```

### "Scene generation fails"
**Problem**: AI doesn't generate scenes  
**Fix**:
1. Check LLM is running: `curl http://localhost:1234/v1/models`
2. Check backend logs: `docker-compose logs kahani-backend`
3. Verify API key (if using cloud provider)
4. Try a different model

---

## 📚 Next Steps

### Learn More
- **Full Documentation**: [README.md](README.md)
- **Docker Guide**: [DOCKER_SETUP_GUIDE.md](DOCKER_SETUP_GUIDE.md)
- **User Settings**: [docs/user-settings-guide.md](docs/user-settings-guide.md)
- **TTS Setup**: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md#tts-configuration)

### Customize Kahani
1. **Change Default User**:
   ```bash
   cd backend
   python create_user.py your@email.com yourpassword
   ```

2. **Add Prompt Templates**:
   - Login → Settings → Prompt Templates
   - Create custom prompts for different story types

3. **Adjust AI Settings**:
   - Login → Settings → LLM Settings
   - Change temperature, max tokens, etc.

4. **Enable Auto-Summary**:
   - Login → Settings → User Preferences
   - Set "Auto-Summary Frequency" (e.g., every 5 scenes)

### Production Deployment
```bash
# Use production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# See: DOCKER_DEPLOYMENT.md for full production guide
```

---

## 🎉 You're Ready!

You now have Kahani running! Here's what to do next:

1. ✅ Login at http://localhost:3000
2. ✅ Create your first story
3. ✅ Generate a few scenes
4. ✅ Explore the features (summaries, regeneration, TTS)
5. ✅ Check out the documentation for advanced features

**Need Help?**
- 📖 Check [COMPLETE_PROJECT_SUMMARY.md](COMPLETE_PROJECT_SUMMARY.md)
- 🐛 Report issues: [GitHub Issues](https://github.com/yourusername/kahani/issues)
- 💬 Ask questions: [GitHub Discussions](https://github.com/yourusername/kahani/discussions)

---

<p align="center">
  <strong>Happy Storytelling! 🎭📚✨</strong>
</p>

<p align="center">
  <em>Remember: The best stories start with a single scene.</em>
</p>
