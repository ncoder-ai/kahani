# ============================================================================
# VIBEVOICE TTS SERVICE DOCKERFILE
# ============================================================================
# Standalone Dockerfile for VibeVoice TTS service
# Supports both GPU (CUDA) and CPU deployments
# ============================================================================

# Use Python 3.11 (VibeVoice requires >=3.9, 3.11 is stable)
FROM python:3.11-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Clone VibeVoice from GitHub
# This ensures we always have the latest compatible version
# For local development, you can mount VibeVoice source as a volume instead
ARG VIBEVOICE_VERSION=main
RUN git clone --depth 1 --branch ${VIBEVOICE_VERSION} https://github.com/microsoft/VibeVoice.git /app/vibevoice-source

# Install VibeVoice dependencies
WORKDIR /app/vibevoice-source

# Install PyTorch first (CPU version by default, can be overridden for GPU)
# For GPU support, use: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install VibeVoice dependencies from pyproject.toml
RUN pip install --no-cache-dir \
    accelerate==1.6.0 \
    transformers==4.51.3 \
    llvmlite>=0.40.0 \
    numba>=0.57.0 \
    diffusers \
    tqdm \
    numpy \
    scipy \
    librosa \
    ml-collections \
    absl-py \
    gradio \
    av \
    aiortc \
    uvicorn[standard] \
    fastapi \
    websockets

# Production stage
FROM python:3.11-slim as production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/vibevoice-source

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy installed packages and VibeVoice source from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/vibevoice-source /app/vibevoice-source

# Set working directory to VibeVoice source
WORKDIR /app/vibevoice-source

# Create directories for models and voices
RUN mkdir -p /app/models /app/voices

# Expose port
EXPOSE 3000

# Default environment variables (can be overridden)
ENV MODEL_PATH="microsoft/VibeVoice-Realtime-0.5B" \
    MODEL_DEVICE="cpu" \
    PORT=3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/config || exit 1

# Run VibeVoice service
# Uses the demo web app which provides the /stream and /config endpoints
# Use shell form to allow environment variable substitution
CMD sh -c "python -m uvicorn demo.web.app:app --host 0.0.0.0 --port ${PORT:-3000}"
