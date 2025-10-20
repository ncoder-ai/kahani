# Kahani Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Frontend Build
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./
RUN npm ci --only=production

# Copy frontend source
COPY frontend/ ./

# Build the frontend
RUN npm run build

# Stage 2: Backend Setup
FROM python:3.11-slim AS backend-builder

WORKDIR /app/backend

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 3: Production Image
FROM python:3.11-slim AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NODE_ENV=production
ENV FAST_API_ENV=production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r kahani && useradd -r -g kahani -s /bin/bash kahani

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy backend source
COPY backend/ ./backend/

# Download AI models (embedding + reranker) during build
# This ensures models are cached in the image (~170MB)
RUN echo "📦 Downloading AI models for semantic memory..." && \
    cd backend && \
    python download_models.py || echo "⚠️  Model download failed, will retry at runtime"

# Copy built frontend
COPY --from=frontend-builder /app/frontend/out ./frontend/out
COPY --from=frontend-builder /app/frontend/package*.json ./frontend/
COPY --from=frontend-builder /app/frontend/node_modules ./frontend/node_modules

# Copy startup scripts
COPY docker-entrypoint.sh ./
COPY start-prod.sh ./

# Create necessary directories
RUN mkdir -p backend/data backend/logs

# Set permissions
RUN chown -R kahani:kahani /app
RUN chmod +x docker-entrypoint.sh start-prod.sh

# Switch to app user
USER kahani

# Expose ports (same as development: 9876 backend, 6789 frontend)
EXPOSE 9876 6789

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:9876/health || exit 1

# Start the application
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["./start-prod.sh"]