# Kahani - Deployment Guide

This guide covers deploying Kahani with semantic memory capabilities enabled.

## Prerequisites

- Python 3.11+
- Node.js 18+
- 2GB+ free disk space (for AI models)
- Internet connection (for initial setup)

## Backend Deployment

### 1. Initial Setup

```bash
cd backend

# Run the automated setup script
./setup.sh
```

This will:
- Create a virtual environment
- Install all Python dependencies  
- **Download AI models** (sentence-transformers, ~90MB)
- Run database migrations
- Create necessary data directories

### 2. Manual Setup (Alternative)

If you prefer manual setup:

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Download AI models (IMPORTANT!)
python download_models.py

# Run database migrations
python migrate_add_semantic_memory.py

# Create data directories
mkdir -p data/chromadb data/exports logs
```

### 3. Configuration

Edit `backend/app/config.py` or set environment variables:

```python
# Semantic Memory Settings
enable_semantic_memory = True  # Enable vector search
semantic_db_path = "./data/chromadb"  # ChromaDB storage
semantic_embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
context_strategy = "hybrid"  # Use semantic + linear context
```

### 4. Start the Backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 9876 --reload
```

Or use the start script:

```bash
./start.sh
```

### 5. Verify Installation

Check that semantic memory is working:

```bash
curl http://localhost:9876/
# Should return: {"message":"Welcome to Kahani","version":"0.1.0"}
```

Check logs for:
```
✅ Semantic memory service initialized successfully
✅ ChromaDB collections initialized successfully
```

## Frontend Deployment

```bash
cd frontend
npm install
npm run dev  # Development
# OR
npm run build && npm start  # Production
```

## Production Deployment

### Using Docker (Recommended)

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download AI models during build (NOT at runtime!)
COPY download_models.py .
RUN python download_models.py

# Copy application code
COPY . .

# Run migrations
RUN python migrate_add_semantic_memory.py

# Expose port
EXPOSE 9876

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9876"]
```

Build and run:

```bash
cd backend
docker build -t kahani-backend .
docker run -p 9876:9876 -v $(pwd)/data:/app/data kahani-backend
```

### Using systemd (Linux)

Create `/etc/systemd/system/kahani-backend.service`:

```ini
[Unit]
Description=Kahani Backend Server
After=network.target

[Service]
Type=simple
User=kahani
WorkingDirectory=/opt/kahani/backend
Environment="PATH=/opt/kahani/backend/.venv/bin"
ExecStart=/opt/kahani/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9876
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable kahani-backend
sudo systemctl start kahani-backend
sudo systemctl status kahani-backend
```

## Important Notes

### Model Downloads

**⚠️ CRITICAL**: Always download AI models during deployment, NOT at runtime!

```bash
# Run this BEFORE starting the application
python download_models.py
```

This ensures:
- No delays when users first generate scenes
- All dependencies are verified before going live
- Predictable deployment process
- No surprises in production

### Directory Structure

```
backend/
├── data/
│   ├── chromadb/          # Vector embeddings (auto-created)
│   ├── exports/           # Exported stories
│   └── kahani.db          # SQLite database
├── logs/                  # Application logs
├── .venv/                 # Python virtual environment
├── download_models.py     # Model download script
├── setup.sh               # Automated setup
└── start.sh               # Start script
```

### Performance

- **First Scene Generation**: Models load from cache (~1-2s one-time load)
- **Subsequent Scenes**: Embeddings generated in background (~100-200ms)
- **Semantic Search**: ~10-50ms per query
- **Database**: ChromaDB stores ~1KB per scene embedding

### Troubleshooting

**Backend won't start:**
```bash
# Check if models are downloaded
ls -la ~/.cache/torch/sentence_transformers/

# Check logs
tail -f logs/backend.log

# Verify dependencies
pip list | grep -E "(chromadb|sentence-transformers|tiktoken)"
```

**Semantic memory disabled:**
```bash
# Check config
python -c "from app.config import settings; print(settings.enable_semantic_memory)"

# Should print: True
```

**Port already in use:**
```bash
# Find and kill process
lsof -ti:9876 | xargs kill -9

# Or use a different port
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Monitoring

Check semantic memory stats:

```bash
# Count embeddings
sqlite3 data/kahani.db "SELECT COUNT(*) FROM scene_embeddings;"

# Check ChromaDB collections
curl http://localhost:9876/api/semantic-search/stats
```

## Backup

Important files to backup:
- `data/kahani.db` - Main database
- `data/chromadb/` - Vector embeddings
- `data/exports/` - Exported stories

```bash
# Backup script
tar -czf kahani-backup-$(date +%Y%m%d).tar.gz \
    data/kahani.db \
    data/chromadb/ \
    data/exports/
```

## Updates

When updating:

```bash
cd backend
source .venv/bin/activate

# Update dependencies
pip install --upgrade -r requirements.txt

# Re-download models if model changed in config
python download_models.py

# Run any new migrations
python migrate_add_semantic_memory.py

# Restart server
./start.sh
```

## Security

For production:

1. **Change default secrets** in `config.py`
2. **Use environment variables** for sensitive data
3. **Enable HTTPS** (use nginx/caddy as reverse proxy)
4. **Restrict CORS** origins to your domain
5. **Set up firewall** rules
6. **Regular backups** of database and embeddings

## Support

For issues:
1. Check logs in `logs/backend.log`
2. Verify models downloaded: `python download_models.py`
3. Test semantic memory: `curl http://localhost:9876/api/semantic-search/scenes/1?query_text=test`

