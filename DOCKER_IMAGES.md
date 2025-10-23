# Docker Images Guide

This guide explains how to use the pre-built Kahani Docker images from GitHub Container Registry (GHCR).

## 🚀 Quick Start

The fastest way to get started with Kahani:

```bash
# Download the pre-built docker-compose file
curl -O https://raw.githubusercontent.com/ncoder-ai/kahani/main/docker-compose.prebuilt.yml

# Start Kahani
docker-compose -f docker-compose.prebuilt.yml up -d
```

**Access the application**: http://localhost:6789

## 📦 Available Images

### GitHub Container Registry (GHCR)

All images are hosted on GitHub Container Registry and are **public** (no authentication required):

- **Backend**: `ghcr.io/ncoder-ai/kahani-backend`
- **Frontend**: `ghcr.io/ncoder-ai/kahani-frontend`

### Available Tags

| Tag | Description | When to Use |
|-----|-------------|-------------|
| `latest` | Latest stable release (main branch) | **Recommended for production** |
| `main` | Latest main branch build | Same as latest, explicit branch reference |
| `dev` | Latest development build | For testing new features |
| `v1.0.0` | Specific version | For reproducible deployments |

## 🔧 Usage Options

### Option 1: Pre-built Docker Compose (Recommended)

**Best for**: Quick setup, no build time, production use

```bash
# Download and start
curl -O https://raw.githubusercontent.com/ncoder-ai/kahani/main/docker-compose.prebuilt.yml
docker-compose -f docker-compose.prebuilt.yml up -d
```

### Option 2: Manual Docker Run

**Best for**: Custom configurations, integration with existing setups

```bash
# Create network
docker network create kahani-network

# Run backend
docker run -d \
  --name kahani-backend \
  --network kahani-network \
  -p 9876:9876 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -e DATABASE_URL=sqlite:///./data/kahani.db \
  -e SECRET_KEY=your-secret-key \
  -e JWT_SECRET_KEY=your-jwt-key \
  -e LLM_BASE_URL=http://host.docker.internal:1234/v1 \
  -e CORS_ORIGINS=* \
  --add-host host.docker.internal:host-gateway \
  ghcr.io/ncoder-ai/kahani-backend:latest

# Run frontend
docker run -d \
  --name kahani-frontend \
  --network kahani-network \
  -p 6789:6789 \
  -e PORT=6789 \
  ghcr.io/ncoder-ai/kahani-frontend:latest
```

### Option 3: Custom Docker Compose

**Best for**: Production deployments with custom configurations

```yaml
version: '3.8'

services:
  backend:
    image: ghcr.io/ncoder-ai/kahani-backend:latest
    container_name: kahani-backend
    ports:
      - "9876:9876"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - DATABASE_URL=sqlite:///./data/kahani.db
      - SECRET_KEY=${SECRET_KEY:-change-this-secret-key}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-this-jwt-key}
      - LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:1234/v1}
      - LLM_API_KEY=${LLM_API_KEY:-not-needed}
      - LLM_MODEL=${LLM_MODEL:-local-model}
      - CORS_ORIGINS=*
      - DOCKER_CONTAINER=true
      - KAHANI_ENV=production
      - PORT=9876
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - kahani-network
    restart: unless-stopped

  frontend:
    image: ghcr.io/ncoder-ai/kahani-frontend:latest
    container_name: kahani-frontend
    ports:
      - "6789:6789"
    environment:
      - PORT=6789
    depends_on:
      - backend
    networks:
      - kahani-network
    restart: unless-stopped

networks:
  kahani-network:
    driver: bridge
```

## 🔄 Updating Images

### Update to Latest Version

```bash
# Pull latest images
docker-compose -f docker-compose.prebuilt.yml pull

# Restart with new images
docker-compose -f docker-compose.prebuilt.yml up -d
```

### Update to Specific Version

```bash
# Edit docker-compose.prebuilt.yml and change tags:
# image: ghcr.io/ncoder-ai/kahani-backend:v1.0.0
# image: ghcr.io/ncoder-ai/kahani-frontend:v1.0.0

# Then pull and restart
docker-compose -f docker-compose.prebuilt.yml pull
docker-compose -f docker-compose.prebuilt.yml up -d
```

## 🆚 Pre-built vs Build from Source

### Pre-built Images (Recommended)

✅ **Pros:**
- **Instant deployment** - No 5-10 minute build wait
- **Bandwidth savings** - No downloading build dependencies
- **Consistency** - Everyone uses the same tested images
- **Easy updates** - Simple pull and restart
- **Free hosting** - GitHub Container Registry is free
- **No authentication** - Public images require no login

❌ **Cons:**
- Less customization during build
- Dependent on our build process

### Build from Source

✅ **Pros:**
- Full control over build process
- Can modify Dockerfiles
- Custom build arguments

❌ **Cons:**
- **Slow** - 5-10 minutes build time
- **Bandwidth intensive** - Downloads all dependencies
- **Inconsistent** - Different results on different machines
- **Complex updates** - Need to rebuild everything

## 🐛 Troubleshooting

### Common Issues

#### 1. Images Not Found

**Error**: `Error response from daemon: pull access denied for ghcr.io/ncoder-ai/kahani-backend`

**Solution**: Make sure you're using the correct image names:
- ✅ `ghcr.io/ncoder-ai/kahani-backend:latest`
- ❌ `ncoder-ai/kahani-backend:latest`

#### 2. Permission Denied

**Error**: `permission denied while trying to connect to the Docker daemon socket`

**Solution**: Add your user to the docker group:
```bash
sudo usermod -aG docker $USER
# Log out and back in
```

#### 3. Port Already in Use

**Error**: `bind: address already in use`

**Solution**: Check what's using the ports:
```bash
# Check port 6789 (frontend)
sudo lsof -i :6789

# Check port 9876 (backend)
sudo lsof -i :9876

# Kill the process or change ports in docker-compose.prebuilt.yml
```

#### 4. Database Issues

**Error**: Database not created or corrupted

**Solution**: Remove old data and restart:
```bash
# Stop containers
docker-compose -f docker-compose.prebuilt.yml down

# Remove data directory
rm -rf ./data

# Start fresh
docker-compose -f docker-compose.prebuilt.yml up -d
```

#### 5. LLM Connection Issues

**Error**: Cannot connect to LLM service

**Solution**: Check your LLM configuration:
```bash
# Check if LLM service is running
curl http://localhost:1234/v1/models

# Update environment variables
export LLM_BASE_URL=http://your-llm-server:1234/v1
export LLM_API_KEY=your-api-key
```

### Getting Help

1. **Check logs**:
   ```bash
   docker-compose -f docker-compose.prebuilt.yml logs backend
   docker-compose -f docker-compose.prebuilt.yml logs frontend
   ```

2. **Verify images**:
   ```bash
   docker images | grep kahani
   ```

3. **Test connectivity**:
   ```bash
   # Test backend
   curl http://localhost:9876/health
   
   # Test frontend
   curl http://localhost:6789
   ```

## 📊 Image Information

### Backend Image
- **Base**: Python 3.12 Alpine
- **Size**: ~800MB (includes AI models)
- **Architecture**: AMD64, ARM64
- **Includes**: FastAPI, ChromaDB, LiteLLM, AI models

### Frontend Image
- **Base**: Node.js 22 Alpine
- **Size**: ~200MB
- **Architecture**: AMD64, ARM64
- **Includes**: Next.js, React, Tailwind CSS

## 🔒 Security

- **Public images** - No authentication required to pull
- **Signed images** - All images are signed by GitHub Actions
- **Regular updates** - Images are rebuilt on every push
- **Vulnerability scanning** - Trivy scans run on every build

## 📈 Performance

### Resource Usage
- **Backend**: ~512MB RAM, 1 CPU core
- **Frontend**: ~256MB RAM, 0.5 CPU core
- **Storage**: ~1GB for images + data

### Optimization Tips
1. **Use specific tags** instead of `latest` for production
2. **Set resource limits** in docker-compose.yml
3. **Use volume mounts** for persistent data
4. **Enable restart policies** for reliability

## 🔗 Related Links

- [GitHub Container Registry](https://github.com/ncoder-ai/kahani/pkgs/container/kahani-backend)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [GitHub Actions Workflow](.github/workflows/docker.yml)
- [Main README](README.md)
