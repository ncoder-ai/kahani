# Multi-stage build for Python FastAPI backend

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

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

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
    chmod -R 755 /app/data /app/logs

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

# Download AI models (embedding + reranker) during build
# This ensures models are cached in the image
RUN echo "📦 Downloading AI models for semantic memory..." && \
    python download_models.py || echo "⚠️  Model download failed, will retry at runtime"

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9876"]