# Kahani Installation & Deployment - Complete Summary

## 📦 What's Available

Kahani now has **three installation methods**:

### 1. 🐳 Docker (Recommended)
- ✅ Easiest deployment
- ✅ Works on Linux, macOS, Windows
- ✅ Isolated environment
- ✅ One-command start
- ✅ Production-ready

### 2. 💻 Native Installation
- ✅ Best performance
- ✅ Direct access to code
- ✅ Ideal for development
- ✅ Full control
- ✅ Automated script available

### 3. 🔧 Manual Installation
- ✅ Maximum flexibility
- ✅ Custom configuration
- ✅ Learning the system
- ✅ Step-by-step guide

## 🚀 Quick Start (Choose One)

### Option A: Docker (Fastest)

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Clone and configure
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
cp .env.example .env

# 3. Start
docker-compose up -d

# 4. Access
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

### Option B: Native Install (Linux/macOS)

```bash
# 1. Clone repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# 2. Run installer
chmod +x install.sh
./install.sh

# 3. Start services
# Backend will auto-start
cd frontend && npm run dev

# 4. Access
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

### Option C: Manual Install

See `INSTALLATION.md` for detailed step-by-step instructions.

## 📚 Documentation Structure

### Installation Guides

1. **`INSTALLATION.md`** - Comprehensive installation guide
   - System requirements
   - Step-by-step setup
   - Troubleshooting
   - Configuration

2. **`install.sh`** - Automated installation script
   - Checks system requirements
   - Installs dependencies
   - Sets up environment
   - Initializes database
   - Starts services

3. **`DOCKER_SETUP_GUIDE.md`** - Complete Docker guide
   - Docker installation
   - Configuration options
   - Deployment modes
   - Customization

4. **`DOCKER_DEPLOYMENT.md`** - Detailed Docker deployment
   - Prerequisites
   - Configuration
   - TTS integration
   - Troubleshooting
   - Maintenance

5. **`DOCKER_QUICK_REFERENCE.md`** - Docker command reference
   - Common commands
   - Quick operations
   - One-liners
   - Emergency procedures

6. **`QUICK_REFERENCE.md`** - General quick reference
   - Common tasks
   - Configuration
   - Troubleshooting
   - Commands

### Configuration Files

1. **`.env.example`** - Environment template
   - Database configuration
   - LLM settings
   - TTS settings
   - Security keys

2. **`docker-compose.yml`** - Main composition
   - All services
   - Volumes
   - Networks
   - Default config

3. **`docker-compose.prod.yml`** - Production overrides
   - PostgreSQL
   - Redis
   - Nginx
   - Resource limits

4. **`docker-compose.dev.yml`** - Development overrides
   - Hot reload
   - Debug ports
   - Adminer
   - Dev environment

5. **`.dockerignore`** - Docker build exclusions
   - Optimized builds
   - Smaller images
   - Faster builds

6. **`docker-entrypoint.sh`** - Backend startup script
   - Database initialization
   - Migrations
   - Health checks
   - Service waiting

### Docker Files

1. **`backend/Dockerfile`**
   - Multi-stage build
   - Python 3.11
   - Health checks
   - Non-root user

2. **`frontend/Dockerfile`**
   - Multi-stage build
   - Node 18 Alpine
   - Optimized production
   - Non-root user

## 🎯 Deployment Scenarios

### Scenario 1: Local Development

**Goal:** Quick setup for development

**Method:** Native install with hot reload

```bash
# Install
./install.sh

# Develop
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev
```

**Pros:**
- Fast iteration
- Direct file access
- Easy debugging
- Best performance

### Scenario 2: Testing/Demo

**Goal:** Quick demo for others

**Method:** Docker with SQLite

```bash
# Start
docker-compose up -d

# Share
# Access at http://YOUR_IP:3000
```

**Pros:**
- One command
- Isolated environment
- Easy cleanup
- Portable

### Scenario 3: Production Deployment

**Goal:** Production-ready deployment

**Method:** Docker with PostgreSQL

```bash
# Configure
cp .env.example .env
nano .env  # Set strong passwords

# Deploy
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Monitor
docker-compose logs -f
```

**Pros:**
- Production-ready
- PostgreSQL database
- Resource limits
- Auto-restart

### Scenario 4: Complete Privacy

**Goal:** No external APIs, complete privacy

**Method:** Docker with Ollama

```bash
# Start with Ollama
COMPOSE_PROFILES=llm docker-compose up -d

# Pull model
docker exec -it kahani-ollama ollama pull llama2

# Configure
# Set LLM_BASE_URL=http://ollama:11434/v1 in .env
docker-compose restart kahani-backend
```

**Pros:**
- Complete privacy
- No API costs
- Works offline
- Self-hosted LLM

### Scenario 5: Production with All Features

**Goal:** Full production stack

**Method:** Docker with everything

```bash
# Start full stack
COMPOSE_PROFILES=llm,redis,proxy docker-compose \
  -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Includes:**
- PostgreSQL
- Redis caching
- Nginx reverse proxy
- Ollama LLM
- Resource limits

## 🔧 System Requirements

### Minimum

| Component | Requirement |
|-----------|-------------|
| OS | Linux, macOS, Windows 10+ |
| CPU | 2 cores |
| RAM | 4 GB |
| Disk | 10 GB free |
| Python | 3.11+ (native) |
| Node.js | 18+ (native) |
| Docker | 20.10+ (Docker) |

### Recommended

| Component | Requirement |
|-----------|-------------|
| OS | Linux Ubuntu 22.04+, macOS 12+, Windows 11 |
| CPU | 4+ cores |
| RAM | 8+ GB |
| Disk | 20+ GB SSD |
| Python | 3.11+ |
| Node.js | 18+ |
| Docker | Latest stable |

### With Self-Hosted LLM (Ollama)

| Component | Requirement |
|-----------|-------------|
| CPU | 8+ cores |
| RAM | 16+ GB |
| GPU | NVIDIA GPU with 8+ GB VRAM |
| Disk | 50+ GB |

## 📋 Installation Checklist

### Pre-Installation

- [ ] Check system requirements
- [ ] Decide installation method (Docker vs Native)
- [ ] Choose database (SQLite vs PostgreSQL)
- [ ] Plan LLM provider (Local vs Cloud)
- [ ] Plan TTS provider (Optional)

### During Installation

- [ ] Clone repository
- [ ] Copy .env.example to .env
- [ ] Configure environment variables
- [ ] Install system dependencies
- [ ] Install Python dependencies (native)
- [ ] Install Node.js dependencies (native)
- [ ] Build Docker images (Docker)
- [ ] Initialize database
- [ ] Run migrations

### Post-Installation

- [ ] Start services
- [ ] Verify backend health (http://localhost:8000/health)
- [ ] Access frontend (http://localhost:3000)
- [ ] Create first user
- [ ] Configure LLM provider
- [ ] Configure TTS (optional)
- [ ] Test story generation
- [ ] Set up backups
- [ ] Configure monitoring (production)

### Production-Specific

- [ ] Change all default secrets
- [ ] Use PostgreSQL instead of SQLite
- [ ] Set up HTTPS with SSL certificates
- [ ] Configure firewall rules
- [ ] Set up regular backups
- [ ] Configure monitoring/logging
- [ ] Test disaster recovery
- [ ] Document configuration

## 🔐 Security Checklist

- [ ] **Change default secrets**
  ```bash
  SECRET_KEY=$(openssl rand -hex 32)
  JWT_SECRET_KEY=$(openssl rand -hex 32)
  ```

- [ ] **Use strong database password**
  ```bash
  POSTGRES_PASSWORD=$(openssl rand -hex 16)
  ```

- [ ] **Use PostgreSQL in production** (not SQLite)

- [ ] **Enable HTTPS** with valid SSL certificate

- [ ] **Configure firewall**
  ```bash
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw deny 8000/tcp  # Don't expose backend directly
  ```

- [ ] **Regular updates**
  ```bash
  git pull origin main
  docker-compose build --no-cache  # Docker
  # or
  pip install -r requirements.txt --upgrade  # Native
  ```

- [ ] **Regular backups**
  - Database: Daily
  - Audio files: Weekly
  - Configuration: On change

- [ ] **Monitor logs** for suspicious activity

- [ ] **Limit resource usage** (Docker production config)

## 🆘 Troubleshooting

### Common Issues

| Issue | Native Fix | Docker Fix |
|-------|-----------|------------|
| Port in use | `sudo lsof -i :3000` | `docker-compose down` |
| Python not found | `python3 --version` | Check Dockerfile |
| Node not found | `node --version` | Check Dockerfile |
| Database error | Check DATABASE_URL | `docker-compose logs postgres` |
| LLM connection | Check LLM_BASE_URL | Check host.docker.internal |
| TTS not working | Check TTS_API_URL | Configure via UI |
| Permission denied | `chmod +x install.sh` | Check user in Dockerfile |

### Getting Help

1. Check documentation in `docs/` folder
2. View logs: `docker-compose logs -f` or check `logs/kahani.log`
3. Search issues: https://github.com/ncoder-ai/kahani/issues
4. Ask questions: https://github.com/ncoder-ai/kahani/discussions

## 📊 Feature Comparison

| Feature | Docker | Native |
|---------|--------|--------|
| **Ease of Setup** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Performance** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Isolation** | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Production Ready** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Development** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Portability** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Resource Usage** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Maintenance** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

## 🎯 Recommendations

### For Beginners
**Use:** Docker installation
**Why:** Easiest setup, all dependencies included

### For Developers
**Use:** Native installation
**Why:** Best performance, direct code access

### For Production
**Use:** Docker with PostgreSQL
**Why:** Production-ready, isolated, easy to scale

### For Privacy
**Use:** Docker with Ollama
**Why:** Complete privacy, no external APIs

## ✅ Success Indicators

Your installation is successful if:

1. ✅ Backend health check passes
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status": "healthy"}
   ```

2. ✅ Frontend loads
   ```bash
   curl http://localhost:3000
   # Should return HTML
   ```

3. ✅ Database initialized
   ```bash
   # Native
   ls backend/data/kahani.db
   
   # Docker
   docker exec kahani-backend ls /app/data/kahani.db
   ```

4. ✅ Can create user and login

5. ✅ Can generate stories

## 📞 Support & Resources

### Documentation
- Installation: `INSTALLATION.md`
- Docker Setup: `DOCKER_SETUP_GUIDE.md`
- Docker Commands: `DOCKER_QUICK_REFERENCE.md`
- Docker Deployment: `DOCKER_DEPLOYMENT.md`
- Quick Reference: `QUICK_REFERENCE.md`
- TTS Setup: `docs/tts-quick-start.md`

### Online
- GitHub: https://github.com/ncoder-ai/kahani
- Issues: https://github.com/ncoder-ai/kahani/issues
- Discussions: https://github.com/ncoder-ai/kahani/discussions

### Commands

```bash
# Check installation
./install.sh --check

# View logs (Docker)
docker-compose logs -f

# View logs (Native)
tail -f logs/kahani.log

# Restart services (Docker)
docker-compose restart

# Restart services (Native)
pkill -f uvicorn && cd backend && uvicorn app.main:app &
```

## 🎉 Next Steps

After successful installation:

1. **Create First User**
   - Access http://localhost:3000
   - Sign up for an account

2. **Configure LLM**
   - Settings → LLM Configuration
   - Add your LM Studio / Ollama / OpenAI endpoint

3. **Configure TTS (Optional)**
   - Settings → TTS Settings
   - Choose provider and configure

4. **Create First Story**
   - Dashboard → New Story
   - Follow the creation wizard
   - Start writing!

5. **Explore Features**
   - Story generation
   - Scene variants
   - Context management
   - Chapter summaries
   - TTS narration (if configured)

Enjoy Kahani! 🎭📖✨
