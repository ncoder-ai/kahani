# Multi-stage build for Python FastAPI backend - with venv

# Build stage
FROM python:3.12-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Create virtual environment
RUN python -m venv /app/venv

# Activate virtual environment and upgrade pip
RUN /app/venv/bin/pip install --upgrade pip

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies in venv
RUN /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.12-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/app/venv \
    PATH="/app/venv/bin:$PATH"

# Install system dependencies for runtime
RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with UID/GID 1000
RUN groupadd -r -g 1000 kahani && useradd -r -u 1000 -g kahani kahani

# Set working directory
WORKDIR /app

# Create app directories with proper ownership from the start
RUN mkdir -p /app/data /app/logs /app/.cache/huggingface && \
    chown -R 1000:1000 /app

# Copy virtual environment from builder stage with correct ownership
COPY --from=builder --chown=1000:1000 /app/venv /app/venv

# Copy application code with correct ownership
COPY --chown=1000:1000 . .

# Copy entrypoint script with correct ownership and make it executable
COPY --chown=1000:1000 docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Download AI models (embedding + reranker) during build as the kahani user
# Use BuildKit cache mount to persist model downloads between builds
USER kahani
RUN --mount=type=cache,target=/app/.cache/huggingface \
    echo "📦 Downloading AI models for semantic memory..." && \
    python download_models.py || echo "⚠️  Model download failed, will retry at runtime"

# Switch back to root for final setup (entrypoint will handle user switching)
USER root

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-9876}/health || exit 1

# Expose port
EXPOSE ${PORT:-9876}

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9876"]