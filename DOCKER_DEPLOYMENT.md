# Kahani Docker Deployment Guide

Complete guide for deploying Kahani using Docker and Docker Compose.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Deployment Options](#deployment-options)
- [TTS Integration](#tts-integration)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## 🚀 Quick Start

### 1. Install Docker

**Linux (Ubuntu/Debian):**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get install docker-compose-plugin

# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**macOS:**
```bash
# Install Docker Desktop from https://www.docker.com/products/docker-desktop

# Or using Homebrew:
brew install --cask docker
```

**Windows:**
- Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
- Enable WSL 2 backend (recommended)

### 2. Clone and Configure

```bash
# Clone repository
git clone https://github.com/ncoder-ai/kahani.git
cd kahani

# Copy environment file
cp .env.example .env

# Edit configuration
nano .env  # or vim, code, etc.
```

### 3. Start Services

```bash
# Development mode (SQLite database)
docker-compose up -d

# Production mode (PostgreSQL database)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# With optional services (Ollama LLM)
COMPOSE_PROFILES=llm docker-compose up -d
```

### 4. Access Application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 5. Create First User

```bash
# Access backend container
docker exec -it kahani-backend bash

# Create admin user
python create_user.py
```

## ✅ Prerequisites

### System Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 4 GB
- Disk: 10 GB free space
- Docker: 20.10+
- Docker Compose: 2.0+

**Recommended:**
- CPU: 4+ cores
- RAM: 8+ GB
- Disk: 20+ GB SSD
- Docker: Latest stable
- Docker Compose: Latest stable

### Port Requirements

Default ports used:
- `3000` - Frontend (Next.js)
- `8000` - Backend (FastAPI)
- `5432` - PostgreSQL (if using)
- `11434` - Ollama LLM (optional)
- `6379` - Redis (optional)
- `80/443` - Nginx (production)

Make sure these ports are available or change them in `docker-compose.yml`.

## ⚙️ Configuration

### Environment Variables

Create `.env` file from `.env.example`:

```bash
cp .env.example .env
```

#### Essential Settings

```env
# Security (CHANGE THESE!)
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here

# Database (SQLite or PostgreSQL)
DATABASE_URL=sqlite:///./data/kahani.db

# LLM Configuration
LLM_BASE_URL=http://host.docker.internal:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL=local-model
```

#### TTS Configuration (Optional)

```env
# TTS Provider
TTS_PROVIDER=openai-compatible
TTS_API_URL=http://host.docker.internal:8080/v1/audio/speech
TTS_API_KEY=

# Or configure via UI after first run
```

#### PostgreSQL (Production)

```env
DATABASE_URL=postgresql://kahani:your_password@postgres:5432/kahani
POSTGRES_DB=kahani
POSTGRES_USER=kahani
POSTGRES_PASSWORD=your_strong_password_here
```

### Docker Compose Profiles

Enable optional services using profiles:

```bash
# Enable Ollama LLM
COMPOSE_PROFILES=llm docker-compose up -d

# Enable Redis cache
COMPOSE_PROFILES=redis docker-compose up -d

# Enable Nginx reverse proxy
COMPOSE_PROFILES=proxy docker-compose up -d

# Enable multiple services
COMPOSE_PROFILES=llm,redis,proxy docker-compose up -d
```

## 🚢 Deployment Options

### Option 1: Development (SQLite)

**Best for:** Testing, local development, single user

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**Pros:**
- ✅ Simplest setup
- ✅ No external database needed
- ✅ Fast to start

**Cons:**
- ⚠️ Not suitable for multiple concurrent users
- ⚠️ Limited scalability

### Option 2: Production (PostgreSQL)

**Best for:** Production deployment, multiple users

```bash
# Start with production overrides
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Stop services
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
```

**Pros:**
- ✅ Better performance
- ✅ Supports concurrent users
- ✅ Better data integrity
- ✅ Backup/restore capabilities

**Cons:**
- ⚠️ More complex setup
- ⚠️ Requires more resources

### Option 3: With Ollama LLM (Self-hosted)

**Best for:** Privacy-focused deployment, no external API

```bash
# Start with Ollama
COMPOSE_PROFILES=llm docker-compose up -d

# Pull a model
docker exec -it kahani-ollama ollama pull llama2

# Configure in .env
LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=llama2
```

**Pros:**
- ✅ Complete privacy (no external APIs)
- ✅ No API costs
- ✅ Works offline

**Cons:**
- ⚠️ Requires powerful hardware (GPU recommended)
- ⚠️ Slower than commercial APIs
- ⚠️ Larger Docker images

### Option 4: Behind Nginx Reverse Proxy

**Best for:** Production with SSL, domain name

```bash
# Setup SSL certificates (Let's Encrypt)
mkdir -p ssl
# Copy your SSL certificates to ssl/

# Configure nginx.prod.conf with your domain

# Start with Nginx
COMPOSE_PROFILES=proxy docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Pros:**
- ✅ HTTPS support
- ✅ Better security
- ✅ Load balancing capabilities
- ✅ Custom domain support

## 🔊 TTS Integration

### Option 1: Configure via Environment Variables

```env
# In .env file
TTS_PROVIDER=openai-compatible
TTS_API_URL=http://host.docker.internal:8080/v1/audio/speech
TTS_API_KEY=your-api-key-if-needed
```

### Option 2: Configure via UI (Recommended)

1. Start Kahani without TTS configuration
2. Login to application
3. Go to Settings → TTS Settings
4. Configure your TTS provider:
   - Provider Type: Kokoro, Chatterbox, OpenAI-compatible
   - API URL: Your TTS service endpoint
   - API Key: If required
   - Voice settings

### Supported TTS Providers

#### Kokoro TTS (Self-hosted)
```bash
# Run Kokoro TTS separately
docker run -d -p 8080:8080 kokoro/tts

# Configure in Kahani
TTS_PROVIDER=kokoro
TTS_API_URL=http://host.docker.internal:8080/v1/audio/speech
```

#### Chatterbox TTS (Self-hosted)
```bash
# Run Chatterbox TTS separately
docker run -d -p 5000:5000 chatterbox/tts

# Configure in Kahani
TTS_PROVIDER=chatterbox
TTS_API_URL=http://host.docker.internal:5000/v1/audio/speech
```

#### OpenAI TTS (Cloud)
```env
TTS_PROVIDER=openai-compatible
TTS_API_URL=https://api.openai.com/v1/audio/speech
TTS_API_KEY=sk-your-openai-api-key
```

### Accessing Host Services from Docker

Use `host.docker.internal` to access services running on your host machine:

```env
# LM Studio on host
LLM_BASE_URL=http://host.docker.internal:1234/v1

# Kokoro TTS on host
TTS_API_URL=http://host.docker.internal:8080/v1/audio/speech
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Port Already in Use

```bash
# Find what's using the port
sudo lsof -i :3000  # or :8000, :5432, etc.

# Kill the process or change port in docker-compose.yml
ports:
  - "3001:3000"  # Use different host port
```

#### 2. Database Connection Failed

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

#### 3. Backend Not Starting

```bash
# Check logs
docker-compose logs kahani-backend

# Common issues:
# - Database not ready (wait 30 seconds and check again)
# - Missing environment variables (check .env file)
# - Port conflict (change port in docker-compose.yml)
```

#### 4. Frontend Build Errors

```bash
# Rebuild frontend
docker-compose build --no-cache kahani-frontend
docker-compose up -d kahani-frontend

# Check logs
docker-compose logs kahani-frontend
```

#### 5. TTS Not Working

```bash
# Check TTS provider is accessible
docker exec -it kahani-backend curl -v http://host.docker.internal:8080/health

# Check TTS configuration in database
docker exec -it kahani-backend python -c "
from app.database import SessionLocal
from app.models.tts_settings import TTSSettings
db = SessionLocal()
settings = db.query(TTSSettings).first()
print(f'Provider: {settings.tts_provider_type}')
print(f'URL: {settings.tts_api_url}')
"
```

### Useful Commands

```bash
# View all container logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f kahani-backend

# Restart a service
docker-compose restart kahani-backend

# Rebuild and restart
docker-compose up -d --build kahani-backend

# Enter backend container
docker exec -it kahani-backend bash

# Enter frontend container  
docker exec -it kahani-frontend sh

# Check container status
docker-compose ps

# View resource usage
docker stats

# Clean up stopped containers
docker-compose down

# Clean up everything (including volumes!)
docker-compose down -v  # WARNING: Deletes data!
```

## 🔄 Maintenance

### Backups

#### Database Backup

```bash
# SQLite
docker exec kahani-backend tar -czf /app/backups/kahani_$(date +%Y%m%d_%H%M%S).tar.gz -C /app/data .

# Copy backup to host
docker cp kahani-backend:/app/backups/kahani_backup.tar.gz ./backups/

# PostgreSQL
docker exec kahani-postgres pg_dump -U kahani kahani > backup_$(date +%Y%m%d).sql
```

#### Audio Files Backup

```bash
# Backup TTS audio files
docker exec kahani-backend tar -czf /app/backups/audio_$(date +%Y%m%d_%H%M%S).tar.gz -C /app/data/audio .

# Copy to host
docker cp kahani-backend:/app/backups/audio_backup.tar.gz ./backups/
```

### Updates

```bash
# Pull latest changes
git pull origin main

# Rebuild containers
docker-compose build --no-cache

# Restart with new images
docker-compose up -d

# Run migrations if needed
docker exec -it kahani-backend python migrate_add_tts.py
```

### Monitoring

```bash
# View resource usage
docker stats

# Check disk usage
docker system df

# View logs
docker-compose logs -f --tail=100

# Health checks
curl http://localhost:8000/health
curl http://localhost:3000/
```

### Cleanup

```bash
# Remove stopped containers
docker-compose down

# Remove unused images
docker image prune -a

# Remove unused volumes (WARNING: Data loss!)
docker volume prune

# Complete cleanup (WARNING: Deletes everything!)
docker-compose down -v
docker system prune -a --volumes
```

## 📊 Resource Management

### Resource Limits

Configure in `docker-compose.prod.yml`:

```yaml
services:
  kahani-backend:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
```

### Monitoring Resource Usage

```bash
# Real-time stats
docker stats

# Specific container
docker stats kahani-backend

# Export metrics
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

## 🔐 Security Best Practices

1. **Change Default Secrets**
   ```env
   SECRET_KEY=use-a-long-random-string-here
   JWT_SECRET_KEY=another-long-random-string
   POSTGRES_PASSWORD=strong-database-password
   ```

2. **Use PostgreSQL in Production**
   - SQLite is not suitable for concurrent users
   - PostgreSQL offers better security and performance

3. **Enable HTTPS**
   - Use Nginx reverse proxy with SSL
   - Get free certificates from Let's Encrypt

4. **Limit Exposed Ports**
   - Only expose necessary ports
   - Use firewall rules

5. **Regular Updates**
   - Keep Docker images updated
   - Update application regularly
   - Apply security patches

6. **Backup Regularly**
   - Automate database backups
   - Store backups securely off-site
   - Test restore procedures

## 📞 Support

- **Documentation:** https://github.com/ncoder-ai/kahani
- **Issues:** https://github.com/ncoder-ai/kahani/issues
- **Discussions:** https://github.com/ncoder-ai/kahani/discussions

## ✅ Checklist

Before deploying to production:

- [ ] Changed all default secrets and passwords
- [ ] Using PostgreSQL instead of SQLite
- [ ] Configured proper backup strategy
- [ ] Set up monitoring and logging
- [ ] Enabled HTTPS with valid certificate
- [ ] Configured firewall rules
- [ ] Tested disaster recovery procedures
- [ ] Documented configuration for team
- [ ] Set up automated updates (optional)
- [ ] Configured resource limits
- [ ] Tested with expected load
- [ ] Prepared rollback plan
