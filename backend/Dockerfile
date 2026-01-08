# ============================================================================
# KAHANI BACKEND DOCKERFILE
# ============================================================================
# Multi-stage build for Python FastAPI backend
#
# Database Configuration:
# - Database is configured via DATABASE_URL environment variable
# - Supports SQLite (default) and PostgreSQL
# - See docker-compose.yml and .env.example for database setup instructions
# ============================================================================

# Build stage
FROM python:3.12-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KAHANI_NO_PROMPT=true

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements-prod.txt .

# Install PyTorch CPU-only first (must be before sentence-transformers)
# This satisfies the torch>=2.0.0 requirement for STT dependencies
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.6.0+cpu torchaudio==2.6.0

# Install Python dependencies (torch will be skipped since already installed)
RUN pip install --no-cache-dir -r requirements-prod.txt

# Install sentence-transformers after PyTorch
RUN pip install --no-cache-dir sentence-transformers==2.3.0

# Production stage
FROM python:3.12-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies for runtime
RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r kahani && useradd -r -g kahani kahani

# Create app directory with proper permissions
RUN mkdir -p /app /app/data /app/logs /app/.cache/huggingface && \
    chown -R 1000:1000 /app

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Copy entrypoint script and make it executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Note: Models are downloaded automatically on first use (lazy loading)
# To pre-download models, use: python download_models.py
# Or use the API endpoint: POST /api/settings/download-stt-model

# Set ownership of application files and model cache
RUN chown -R 1000:1000 /app

# User will be set via docker-compose user mapping

# Health check (uses PORT env var with 9876 default)
HEALTHCHECK --interval=30s --timeout=30s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-9876}/health || exit 1

# Expose port (default 9876, can be overridden with PORT env var)
EXPOSE ${PORT:-9876}

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command (uses PORT env var with 9876 default)
# Use run_server.py to respect log_level from config.yaml
CMD ["python", "run_server.py"]