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

# Create non-root user
RUN groupadd -r kahani && useradd -r -g kahani kahani

# Create app directory with proper permissions
RUN mkdir -p /app /app/data /app/logs /app/.cache/huggingface && \
    chmod -R 755 /app/data /app/logs

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/venv /app/venv

# Copy application code
COPY . .

# Copy entrypoint script and make it executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Set ownership of application files
RUN chown -R 1000:1000 /app

# Note: AI models will be downloaded on first use at runtime
# This avoids the slow chown operation on large model files during build

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-9876}/health || exit 1

# Expose port
EXPOSE ${PORT:-9876}

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9876"]