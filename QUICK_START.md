# Kahani Quick Start Guide

## Docker Setup (Recommended)

### Prerequisites
- Docker and Docker Compose installed
- Git

### Step 1: Clone and Configure

```bash
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
cp .env.example .env
cp config.yaml.example config.yaml
cp docker-compose.yml.example docker-compose.yml
```

Edit `.env` and set your secret keys:
```bash
# Generate secrets with:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Add to .env:
SECRET_KEY=your-generated-secret-here
JWT_SECRET_KEY=your-generated-secret-here
```

### Step 2: Start Services

```bash
docker compose up -d
```

### Step 3: Access the App

- **Frontend**: http://localhost:6789
- **Backend API**: http://localhost:9876
- **API Docs**: http://localhost:9876/docs

Register your first account - the first user automatically becomes admin.

---

## Baremetal Setup

### Prerequisites
- Python 3.11+
- Node.js 20.9.0+
- Git

### Step 1: Clone and Install

```bash
git clone https://github.com/ncoder-ai/kahani.git
cd kahani
./install.sh
```

The install script will:
- Create Python virtual environment
- Install Python and Node.js dependencies
- Generate secret keys in `.env`
- Run database migrations
- Download required AI models

### Step 2: Start Development Server

```bash
./start-dev.sh
```

### Step 3: Access the App

- **Frontend**: http://localhost:6789
- **Backend API**: http://localhost:9876

---

## First Steps

1. **Register an account** - First user becomes admin
2. **Configure LLM** - Go to Settings → LLM Settings
   - Enter your LLM API URL (e.g., `http://localhost:1234/v1` for LM Studio)
   - Select API type and enter model name
3. **Create a story** - Click "New Story" on the dashboard
4. **Generate scenes** - Use AI to generate your first scene

---

## Database Options

**PostgreSQL (Default for Docker)**

Docker Compose uses PostgreSQL by default. Data is stored in `./postgres_data/`.

**SQLite (Simpler Alternative)**

To use SQLite instead, set in `.env`:
```bash
DATABASE_URL=sqlite:///./data/kahani.db
```

And comment out the postgres service in `docker-compose.yml`.

---

## Common Commands

```bash
# Docker
docker compose up -d          # Start services
docker compose down           # Stop services
docker compose logs -f        # View logs
docker compose restart        # Restart services

# Baremetal
./start-dev.sh               # Start development server
./install.sh                 # Reinstall/update dependencies

# Database
cd backend && alembic upgrade head    # Run migrations
```

---

## Troubleshooting

**Port already in use**

Change ports in `config.yaml` under `server.backend.port` and `server.frontend.port`.

**Backend not reachable from browser**

If accessing via IP address (not localhost), ensure CORS is configured in `config.yaml`:
```yaml
cors:
  origins: "*"
```

**Docker container won't start**

Check logs: `docker compose logs backend`

Common issues:
- Missing `.env` file or secret keys
- Port conflicts with other services
- Database connection issues (wait for postgres to be healthy)

**LLM not responding**

1. Verify your LLM server is running
2. Check the API URL in Settings → LLM Settings
3. Test with: `curl http://your-llm-url/v1/models`

---

## Next Steps

- [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) - Detailed configuration options
- [docs/EXTRACTION_MODEL_SETUP.md](docs/EXTRACTION_MODEL_SETUP.md) - Set up local extraction model
- [docs/tts-quick-start.md](docs/tts-quick-start.md) - Configure text-to-speech
