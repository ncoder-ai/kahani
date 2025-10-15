# Kahani Docker Quick Reference

Quick command reference for Docker deployment.

## 🚀 Getting Started

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit configuration
nano .env

# 3. Start services
docker-compose up -d

# 4. Check status
docker-compose ps

# 5. View logs
docker-compose logs -f

# 6. Access application
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## 📋 Common Commands

### Service Management

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d kahani-backend

# Stop all services
docker-compose down

# Restart service
docker-compose restart kahani-backend

# Rebuild and restart
docker-compose up -d --build kahani-backend

# View running containers
docker-compose ps

# View all containers (including stopped)
docker-compose ps -a
```

### Logs & Monitoring

```bash
# View all logs
docker-compose logs

# Follow logs (tail)
docker-compose logs -f

# View logs for specific service
docker-compose logs -f kahani-backend

# View last 100 lines
docker-compose logs --tail=100

# View resource usage
docker stats

# View disk usage
docker system df
```

### Container Access

```bash
# Enter backend container
docker exec -it kahani-backend bash

# Enter frontend container
docker exec -it kahani-frontend sh

# Enter PostgreSQL container
docker exec -it kahani-postgres psql -U kahani

# Run command in container
docker exec kahani-backend python --version
```

### Database Operations

```bash
# SQLite backup
docker exec kahani-backend cp /app/data/kahani.db /app/backups/kahani_backup.db

# PostgreSQL backup
docker exec kahani-postgres pg_dump -U kahani kahani > backup.sql

# PostgreSQL restore
docker exec -i kahani-postgres psql -U kahani kahani < backup.sql

# View database
docker exec -it kahani-backend python -c "
from app.database import SessionLocal
from app.models import Story
db = SessionLocal()
stories = db.query(Story).all()
print(f'Total stories: {len(stories)}')
"
```

## 🔧 Troubleshooting

### Port Conflicts

```bash
# Find what's using port 3000
sudo lsof -i :3000

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
ports:
  - "3001:3000"
```

### Rebuild from Scratch

```bash
# Stop and remove everything
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Rebuild and start
docker-compose build --no-cache
docker-compose up -d
```

### View Container Details

```bash
# Inspect container
docker inspect kahani-backend

# View environment variables
docker exec kahani-backend env

# View processes
docker top kahani-backend

# Check health
docker inspect --format='{{.State.Health.Status}}' kahani-backend
```

### Database Issues

```bash
# Check PostgreSQL logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres

# Reset PostgreSQL (WARNING: Data loss!)
docker-compose down -v
docker-compose up -d postgres
```

## 🔄 Updates & Maintenance

### Update Application

```bash
# Pull latest code
git pull origin main

# Rebuild containers
docker-compose build

# Apply updates
docker-compose up -d

# Run migrations
docker exec -it kahani-backend python migrate_add_tts.py
```

### Clean Up

```bash
# Remove stopped containers
docker-compose down

# Remove unused images
docker image prune -a

# Remove unused volumes (WARNING!)
docker volume prune

# Clean everything (WARNING!)
docker system prune -a --volumes
```

### Backup & Restore

```bash
# Backup data volume
docker run --rm -v kahani_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/kahani_data_backup.tar.gz -C /data .

# Restore data volume
docker run --rm -v kahani_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/kahani_data_backup.tar.gz -C /data

# Backup PostgreSQL
docker exec kahani-postgres pg_dump -U kahani kahani | \
  gzip > kahani_postgres_$(date +%Y%m%d).sql.gz

# Restore PostgreSQL
gunzip < kahani_postgres_backup.sql.gz | \
  docker exec -i kahani-postgres psql -U kahani kahani
```

## 📊 Deployment Modes

### Development (SQLite)

```bash
docker-compose up -d
```

### Production (PostgreSQL)

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### With Ollama LLM

```bash
COMPOSE_PROFILES=llm docker-compose up -d

# Pull model
docker exec -it kahani-ollama ollama pull llama2
```

### With All Optional Services

```bash
COMPOSE_PROFILES=llm,redis,proxy docker-compose \
  -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 🔐 Security

### Change Secrets

```bash
# Generate random secret
openssl rand -hex 32

# Update .env file
SECRET_KEY=<generated-secret>
JWT_SECRET_KEY=<generated-secret>
POSTGRES_PASSWORD=<generated-secret>
```

### SSL/HTTPS Setup

```bash
# Create SSL directory
mkdir -p ssl

# Generate self-signed certificate (testing only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/privkey.pem -out ssl/fullchain.pem

# For production, use Let's Encrypt
# Configure nginx.prod.conf with your domain
```

## 🎯 Useful One-Liners

```bash
# Follow backend logs
docker-compose logs -f kahani-backend

# Check health status
curl http://localhost:8000/health | jq

# View TTS settings
docker exec -it kahani-backend python -c "
from app.database import SessionLocal
from app.models.tts_settings import TTSSettings
db = SessionLocal()
settings = db.query(TTSSettings).first()
if settings:
    print(f'Provider: {settings.tts_provider_type}')
    print(f'URL: {settings.tts_api_url}')
    print(f'Enabled: {settings.tts_enabled}')
"

# Count stories
docker exec -it kahani-backend python -c "
from app.database import SessionLocal
from app.models.story import Story
db = SessionLocal()
count = db.query(Story).count()
print(f'Total stories: {count}')
"

# View resource usage summary
docker stats --no-stream --format \
  "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Find large images
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | \
  sort -k3 -h -r | head -10

# Export container environment
docker exec kahani-backend env | sort > container_env.txt

# Test database connection
docker exec kahani-backend python -c "
from app.database import engine
try:
    engine.connect()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
"
```

## 📱 Mobile Access

```bash
# Find your local IP
ip addr show | grep "inet " | grep -v 127.0.0.1

# Or on macOS
ifconfig | grep "inet " | grep -v 127.0.0.1

# Access from mobile device
# http://YOUR_LOCAL_IP:3000

# Update CORS in .env
CORS_ORIGINS=["http://YOUR_LOCAL_IP:3000", "http://localhost:3000"]

# Restart backend
docker-compose restart kahani-backend
```

## 🎨 Customization

### Change Ports

Edit `docker-compose.yml`:

```yaml
ports:
  - "8080:8000"  # Backend on port 8080
  - "3001:3000"  # Frontend on port 3001
```

### Add Environment Variable

Edit `.env`:

```env
NEW_VARIABLE=value
```

Add to `docker-compose.yml`:

```yaml
environment:
  - NEW_VARIABLE=${NEW_VARIABLE}
```

Restart:

```bash
docker-compose up -d
```

### Mount Additional Volume

Edit `docker-compose.yml`:

```yaml
volumes:
  - kahani_data:/app/data
  - ./local_folder:/app/custom_path
```

## 🆘 Emergency Procedures

### Complete Reset (WARNING: Data Loss!)

```bash
# Stop all services
docker-compose down -v

# Remove all images
docker-compose down --rmi all

# Clean Docker system
docker system prune -a --volumes

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d
```

### Restore from Backup

```bash
# Stop services
docker-compose down

# Restore data volume
docker run --rm -v kahani_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/kahani_data_backup.tar.gz -C /data

# Restore database (PostgreSQL)
gunzip < backup.sql.gz | \
  docker exec -i kahani-postgres psql -U kahani kahani

# Start services
docker-compose up -d
```

### View Full Container Logs

```bash
# Save logs to file
docker-compose logs > logs_$(date +%Y%m%d_%H%M%S).txt

# View logs with timestamps
docker-compose logs -t

# View logs since specific time
docker-compose logs --since="2024-01-01T00:00:00"

# View logs until specific time
docker-compose logs --until="2024-01-02T00:00:00"
```

## 📞 Getting Help

```bash
# Docker version
docker --version
docker-compose --version

# Container info
docker ps -a
docker inspect kahani-backend

# Network info
docker network ls
docker network inspect kahani-network

# Volume info
docker volume ls
docker volume inspect kahani_data

# System info
docker info
docker system df -v
```

---

For detailed documentation, see `DOCKER_DEPLOYMENT.md`
