# Kahani Configuration Guide

## Configuration System

Kahani uses a two-file configuration system:

| File | Purpose | Commit to Git? |
|------|---------|----------------|
| `config.yaml` | All application settings (copy from `config.yaml.example`) | No |
| `.env` | Secrets and deployment-specific overrides | No |

**Loading Priority** (highest wins):
1. Environment variables
2. `.env` file
3. `config.yaml`

## config.yaml Reference

### Server Settings
```yaml
server:
  backend:
    port: 9876
    host: "0.0.0.0"
  frontend:
    port: 6789

cors:
  origins: "*"  # Use specific origins in production
```

### Database
```yaml
database:
  database_url: "sqlite:///./data/kahani.db"
  # PostgreSQL connection pool (ignored for SQLite)
  pool_size: 20
  max_overflow: 40
  pool_timeout: 30
```

Override with environment variable:
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/kahani
```

### Context Management
```yaml
context:
  max_tokens: 4000
  keep_recent_scenes: 3
  summary_threshold: 5
  summary_threshold_tokens: 10000

context_strategy:
  strategy: "hybrid"  # "linear" or "hybrid"
  semantic_scenes_in_context: 5
  character_moments_in_context: 3
```

### Semantic Memory
```yaml
semantic_memory:
  enabled: true
  # Vectors stored in PostgreSQL via pgvector (no external vector DB needed)
  embedding_model: "sentence-transformers/all-mpnet-base-v2"
  search_top_k: 5
```

### Extraction Settings
```yaml
extraction:
  auto_extract_character_moments: true
  auto_extract_plot_events: true
  confidence_threshold: 70

extraction_model:
  enabled: false
  url: "http://localhost:1234/v1"
  model_name: "qwen2.5-3b-instruct"
```

### NPC Tracking
```yaml
npc_tracking:
  enabled: true
  importance_threshold: 1.0
  active_recency_window: 5      # Scenes for full NPC details
  inactive_recency_window: 15   # Scenes for brief mention
  use_chapter_awareness: true
```

### Speech-to-Text
```yaml
stt:
  model: "small"  # tiny, base, small, medium, large-v2
  device: "auto"  # auto, cuda, cpu
  compute_type: "int8"
  language: "en"
```

### Features
```yaml
features:
  enable_registration: true
  enable_story_sharing: true
  enable_public_stories: false
```

### Logging
```yaml
logging:
  log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  log_file: "./logs/kahani.log"
```

## Environment Variables

### Required
```bash
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key
```

### Optional Overrides
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db

# CORS (overrides config.yaml)
CORS_ORIGINS=*
CORS_ORIGINS=["http://localhost:6789","https://example.com"]

# Frontend API URL (for Docker or separate machines)
NEXT_PUBLIC_API_URL=http://backend:9876
```

## Deployment Scenarios

### Local Development
No special configuration needed. `start-dev.sh` handles everything.

### Docker
Docker Compose sets `NEXT_PUBLIC_API_URL=http://backend:9876` automatically. Override in `.env` only if needed.

### Network Access (via IP)
Ensure `cors.origins: "*"` in `config.yaml` or set `CORS_ORIGINS=*` in `.env`.

### Reverse Proxy
When behind nginx/traefik on standard ports (80/443), the frontend auto-detects the API URL. No `NEXT_PUBLIC_API_URL` needed.

### Production
```bash
# .env
SECRET_KEY=production-secret
JWT_SECRET_KEY=production-jwt-secret
DATABASE_URL=postgresql://user:pass@localhost:5432/kahani
CORS_ORIGINS=["https://yourdomain.com"]
```

## LLM Configuration

LLM settings are configured per-user through the web UI (Settings → LLM Settings).

### Chat vs Text Completion Mode

| Mode | Use When | Example Models |
|------|----------|----------------|
| Chat Completion | Most cloud APIs, Ollama | GPT-4, Claude, Ollama models |
| Text Completion | Local models with specific prompt formats | Llama 3, Mistral, Qwen |

### Text Completion Templates

For local models that need specific prompt formatting:

1. Go to Settings → LLM Settings
2. Select "Text Completion API"
3. Choose a preset (Llama 3, Mistral, Qwen, GLM) or create custom

**Template Components:**
- `bos_token`: Beginning of sequence token
- `eos_token`: End of sequence token
- `system_prefix/suffix`: Wraps system prompt
- `instruction_prefix/suffix`: Wraps user input
- `response_prefix`: Precedes assistant response

### Model Recommendations

| Model | Mode | Preset |
|-------|------|--------|
| GPT-3.5/4, Claude | Chat Completion | N/A |
| Llama 3.x Instruct | Text Completion | Llama 3 |
| Mistral Instruct | Text Completion | Mistral |
| Qwen2/2.5 Instruct | Text Completion | Qwen |
| Ollama (any) | Chat Completion | N/A |

## TTS Configuration

TTS providers are configured per-user in Settings → TTS Settings.

Default provider URLs (can be changed in settings):
```yaml
frontend:
  tts:
    default_providers:
      openai_compatible: "http://localhost:1234"
      chatterbox: "http://localhost:8880"
      kokoro: "http://localhost:8188"
      vibevoice: "http://localhost:3000"
```

See [docs/tts-quick-start.md](docs/tts-quick-start.md) for provider setup.

## Troubleshooting

**CORS errors when accessing via IP:**
Set `cors.origins: "*"` in config.yaml or `CORS_ORIGINS=*` in .env.

**Frontend can't reach backend in Docker:**
Ensure `NEXT_PUBLIC_API_URL=http://backend:9876` is set (this is the default).

**LLM not responding:**
1. Check API URL in Settings → LLM Settings
2. Test endpoint: `curl http://your-llm-url/v1/models`
3. Check backend logs: `docker compose logs backend`

**Database connection failed:**
1. For PostgreSQL: ensure postgres container is healthy
2. Check `DATABASE_URL` format
3. Verify credentials
