# Kahani Docker Setup - Complete Guide

## 📦 What's Included

Kahani provides complete Docker support with:

- ✅ Multi-stage Docker builds (optimized images)
- ✅ Docker Compose for easy orchestration
- ✅ Development and production configurations
- ✅ PostgreSQL database support
- ✅ Optional Ollama LLM integration
- ✅ Optional Redis caching
- ✅ Optional Nginx reverse proxy
- ✅ Health checks and auto-restart
- ✅ Volume management for data persistence
- ✅ Network isolation
- ✅ Resource limits (production)

## 🚀 Quick Start

### 1. Install Docker

#### Linux (Ubuntu/Debian)
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt-get install docker-compose-plugin
```

#### macOS
```bash
# Install Docker Desktop
brew install --cask docker

# Or download from: https://www.docker.com/products/docker-desktop
```

#### Windows
1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
2. Enable WSL 2 backend (recommended)

### 2. Quick Deploy

```bash
# Clone repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Configure
cp .env.example .env
nano .env  # Edit configuration

# Start (SQLite - simplest)
docker-compose up -d

# Or start with PostgreSQL (recommended for production)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Check status
docker-compose ps

# Access application
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## 📂 File Structure

```
kahani/
├── docker-compose.yml           # Main composition
├── docker-compose.prod.yml      # Production overrides
├── docker-compose.dev.yml       # Development overrides
├── .env.example                 # Environment template
├── .dockerignore                # Docker build exclusions
├── docker-entrypoint.sh         # Backend startup script
├── backend/
│   └── Dockerfile              # Backend image
├── frontend/
│   └── Dockerfile              # Frontend image
└── nginx.prod.conf             # Nginx configuration
```

## ⚙️ Configuration Files

### 1. docker-compose.yml

Main Docker Compose file with:
- Backend (FastAPI)
- Frontend (Next.js)
- PostgreSQL database
- Optional services (Ollama, Redis, Nginx)

**Services:**
- `kahani-backend` - Python FastAPI backend (port 8000)
- `kahani-frontend` - Next.js frontend (port 3000)
- `postgres` - PostgreSQL database (port 5432)
- `ollama` - Ollama LLM (port 11434) - optional
- `redis` - Redis cache (port 6379) - optional
- `nginx` - Reverse proxy (ports 80, 443) - optional

**Volumes:**
- `kahani_data` - Application database
- `kahani_audio` - TTS audio files
- `kahani_exports` - Story exports
- `kahani_logs` - Application logs
- `postgres_data` - PostgreSQL data
- `ollama_data` - Ollama models
- `redis_data` - Redis persistence

**Networks:**
- `kahani-network` - Bridge network for all services

### 2. docker-compose.prod.yml

Production overrides with:
- Resource limits
- Stronger security
- PostgreSQL instead of SQLite
- Redis caching
- Nginx reverse proxy
- Production environment variables

### 3. docker-compose.dev.yml

Development overrides with:
- Hot reload for both backend and frontend
- Debug port exposed (5678)
- Source code mounted as volumes
- Adminer for database management
- Development environment variables

### 4. .env

Environment configuration file. Copy from `.env.example` and customize:

```env
# Required
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-key
DATABASE_URL=sqlite:///./data/kahani.db

# LLM
LLM_BASE_URL=http://host.docker.internal:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=local-model

# TTS (optional)
TTS_PROVIDER=openai-compatible
TTS_API_URL=http://host.docker.internal:8080/v1/audio/speech
TTS_API_KEY=

# PostgreSQL (production)
POSTGRES_PASSWORD=change_this_password
```

### 5. Backend Dockerfile

Multi-stage build:
1. **builder** - Install dependencies
2. **production** - Minimal runtime image

Features:
- Python 3.11 slim base
- Non-root user
- Health checks
- Optimized layers

### 6. Frontend Dockerfile

Multi-stage build:
1. **deps** - Install dependencies
2. **builder** - Build Next.js app
3. **production** - Minimal runtime

Features:
- Node 18 Alpine base
- Non-root user
- Health checks
- Optimized for production

## 🎯 Deployment Modes

### Mode 1: Development (SQLite)

**Best for:** Local development, testing

```bash
# Standard development
docker-compose up -d

# Or with hot reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# With database admin tool
COMPOSE_PROFILES=with-adminer docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Features:**
- ✅ Fast startup
- ✅ Simple configuration
- ✅ Hot reload (dev mode)
- ✅ Perfect for single user
- ⚠️ Not for concurrent users

### Mode 2: Production (PostgreSQL)

**Best for:** Production deployment, multiple users

```bash
# Start production stack
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

**Features:**
- ✅ Better performance
- ✅ Concurrent users
- ✅ Data integrity
- ✅ Resource limits
- ✅ Redis caching
- ✅ Production optimized

### Mode 3: With Ollama (Self-hosted LLM)

**Best for:** Complete privacy, offline use

```bash
# Start with Ollama
COMPOSE_PROFILES=llm docker-compose up -d

# Pull a model
docker exec -it kahani-ollama ollama pull llama2

# Configure .env
LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=llama2

# Restart backend
docker-compose restart kahani-backend
```

**Features:**
- ✅ Complete privacy
- ✅ No API costs
- ✅ Works offline
- ⚠️ Requires GPU (recommended)
- ⚠️ Slower than cloud APIs

### Mode 4: Full Production Stack

**Best for:** Production with all features

```bash
# Start everything
COMPOSE_PROFILES=llm,redis,proxy docker-compose \
  -f docker-compose.yml -f docker-compose.prod.yml up -d

# Check status
docker-compose ps
```

**Includes:**
- ✅ PostgreSQL database
- ✅ Redis caching
- ✅ Nginx reverse proxy
- ✅ Ollama LLM
- ✅ Resource limits
- ✅ Health monitoring

## 🔧 Common Tasks

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f kahani-backend

# With timestamps
docker-compose logs -f -t

# Last 100 lines
docker-compose logs --tail=100
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart kahani-backend

# Rebuild and restart
docker-compose up -d --build kahani-backend
```

### Database Operations

```bash
# Backup SQLite
docker exec kahani-backend tar -czf /app/backups/backup.tar.gz -C /app/data .

# Backup PostgreSQL
docker exec kahani-postgres pg_dump -U kahani kahani > backup.sql

# Restore SQLite
docker cp backup.tar.gz kahani-backend:/app/backups/
docker exec kahani-backend tar -xzf /app/backups/backup.tar.gz -C /app/data

# Restore PostgreSQL
docker exec -i kahani-postgres psql -U kahani kahani < backup.sql
```

### Access Containers

```bash
# Backend shell
docker exec -it kahani-backend bash

# Frontend shell
docker exec -it kahani-frontend sh

# PostgreSQL shell
docker exec -it kahani-postgres psql -U kahani

# Run Python script
docker exec kahani-backend python script.py
```

## 🔐 Security Checklist

Before production deployment:

- [ ] **Change all default secrets**
  ```env
  SECRET_KEY=$(openssl rand -hex 32)
  JWT_SECRET_KEY=$(openssl rand -hex 32)
  POSTGRES_PASSWORD=$(openssl rand -hex 16)
  ```

- [ ] **Use PostgreSQL** instead of SQLite

- [ ] **Configure firewall**
  ```bash
  # Only allow necessary ports
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw deny 5432/tcp  # Don't expose PostgreSQL
  ```

- [ ] **Set up HTTPS** with Let's Encrypt or valid SSL certificate

- [ ] **Enable resource limits** (already in docker-compose.prod.yml)

- [ ] **Regular backups** - automate with cron:
  ```bash
  # Daily backup at 2 AM
  0 2 * * * cd /path/to/kahani && docker exec kahani-postgres pg_dump -U kahani kahani > backup_$(date +\%Y\%m\%d).sql
  ```

- [ ] **Monitor logs** for suspicious activity

- [ ] **Keep Docker updated**
  ```bash
  sudo apt-get update && sudo apt-get upgrade docker-ce
  ```

## 📊 Resource Requirements

### Minimum

- **CPU:** 2 cores
- **RAM:** 4 GB
- **Disk:** 10 GB
- **Network:** 1 Mbps

### Recommended

- **CPU:** 4+ cores
- **RAM:** 8+ GB
- **Disk:** 20+ GB SSD
- **Network:** 10+ Mbps

### With Ollama LLM

- **CPU:** 8+ cores
- **RAM:** 16+ GB
- **GPU:** NVIDIA GPU with 8+ GB VRAM (recommended)
- **Disk:** 50+ GB (models are large)

## 🎨 Customization

### Change Ports

Edit `docker-compose.yml`:

```yaml
ports:
  - "8080:8000"  # Backend on 8080
  - "3001:3000"  # Frontend on 3001
```

### Add Custom TTS Provider

1. Run TTS service separately:
```bash
docker run -d -p 8080:8080 your-tts-provider
```

2. Configure in `.env`:
```env
TTS_API_URL=http://host.docker.internal:8080/v1/audio/speech
```

3. Restart backend:
```bash
docker-compose restart kahani-backend
```

### Mount Additional Directories

Edit `docker-compose.yml`:

```yaml
volumes:
  - kahani_data:/app/data
  - ./custom:/app/custom  # Add custom mount
```

## 🆘 Troubleshooting

### Port Already in Use

```bash
# Find what's using the port
sudo lsof -i :3000

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

### Database Connection Failed

```bash
# Check PostgreSQL
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres

# Wait for PostgreSQL to be ready
docker-compose up -d postgres
sleep 10
docker-compose up -d kahani-backend
```

### Backend Won't Start

```bash
# Check logs
docker-compose logs kahani-backend

# Common issues:
# 1. Database not ready - wait 30 seconds
# 2. Missing env vars - check .env
# 3. Port conflict - change port

# Reset backend
docker-compose down kahani-backend
docker-compose build --no-cache kahani-backend
docker-compose up -d kahani-backend
```

### TTS Not Working

```bash
# Check TTS provider is accessible
docker exec kahani-backend curl -v http://host.docker.internal:8080/health

# Check TTS configuration
docker exec -it kahani-backend python -c "
from app.database import SessionLocal
from app.models.tts_settings import TTSSettings
db = SessionLocal()
settings = db.query(TTSSettings).first()
print(f'Provider: {settings.tts_provider_type if settings else 'Not configured'}')
print(f'URL: {settings.tts_api_url if settings else 'Not configured'}')
"

# Reconfigure via Settings UI
# http://localhost:3000/settings
```

### Complete Reset

```bash
# WARNING: This deletes all data!

# Stop and remove everything
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Clean system
docker system prune -a --volumes

# Start fresh
docker-compose build --no-cache
docker-compose up -d
```

## 📚 Additional Resources

- **Full deployment guide:** `DOCKER_DEPLOYMENT.md`
- **Quick command reference:** `DOCKER_QUICK_REFERENCE.md`
- **Installation guide:** `INSTALLATION.md`
- **TTS configuration:** `docs/tts-quick-start.md`
- **General documentation:** `README.md`

## ✅ Success!

If you see this, your Docker deployment is successful:

```bash
$ docker-compose ps
NAME                 STATUS              PORTS
kahani-backend       Up (healthy)        0.0.0.0:8000->8000/tcp
kahani-frontend      Up (healthy)        0.0.0.0:3000->3000/tcp
kahani-postgres      Up                  0.0.0.0:5432->5432/tcp
```

Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## 🎉 Next Steps

1. Create your first user
2. Configure LLM provider
3. Set up TTS (optional)
4. Start writing your first story!

Enjoy Kahani! 🎭📖✨
