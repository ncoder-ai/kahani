# Requirements Files Documentation

This directory contains multiple requirements files for different installation scenarios.

## Files Overview

### `requirements-prod.txt` - Production Docker Requirements  
**Use for:** Production Docker builds (used by Dockerfile)
**Contains:** 
- Core dependencies without test tools (no pytest)
- STT dependencies (faster-whisper, webrtcvad)
- PyTorch and torchaudio are installed separately in Dockerfile before this file
- sentence-transformers installed separately in Dockerfile after PyTorch

### `requirements-baremetal.txt` - Bare-Metal Installation Requirements
**Use for:** Non-Docker installations (Linux, macOS, Windows)
**Contains:** All dependencies including:
- PyTorch CPU-only version (`torch>=2.0.0`)
- torchaudio for STT features
- sentence-transformers
- STT dependencies (faster-whisper, webrtcvad, torchaudio)
- Test dependencies (pytest) for development
- All other core dependencies
**Installation:** Used automatically by `install.sh`

### `requirements.txt` - Legacy/Base Requirements
**Use for:** Reference or legacy Docker builds (not currently used)
**Contains:** Similar to requirements-prod.txt but includes test dependencies
**Note:** Dockerfile now uses `requirements-prod.txt` instead

## Installation Commands

### For Development (Bare-Metal)
```bash
./install.sh
# Uses requirements-baremetal.txt automatically
# Includes PyTorch, sentence-transformers, STT dependencies, and test tools
```

### For Docker Production
```bash
docker compose up --build
# Dockerfile uses requirements-prod.txt
# PyTorch CPU and sentence-transformers installed separately in Dockerfile
```

### For Production Docker Build
```bash
# Build uses requirements-prod.txt via Dockerfile
docker build -f Dockerfile -t kahani:latest .
# This is the recommended approach for production Docker deployments
```

## Why Multiple Files?

**PyTorch Installation Order:**
- PyTorch must be installed before sentence-transformers
- Docker: Dockerfile installs PyTorch CPU first, then requirements-prod.txt, then sentence-transformers
- Bare-metal: requirements-baremetal.txt includes PyTorch and installs in correct order

**STT Dependencies:**
- Both `requirements-prod.txt` and `requirements-baremetal.txt` include STT dependencies
- Docker: PyTorch/torchaudio installed separately in Dockerfile before requirements-prod.txt
- Bare-metal: All STT dependencies (torch, torchaudio, faster-whisper, webrtcvad) in requirements-baremetal.txt

**Size Optimization:**
- Docker: Can use optimized PyTorch CPU builds, excludes test dependencies
- Bare-metal: Uses PyTorch CPU from official PyTorch index, includes test tools for development
- Production: Excludes test dependencies (pytest) to reduce image size

## Maintenance

When adding new dependencies:
1. Add to `requirements-prod.txt` (Docker production - used by Dockerfile)
2. Add to `requirements-baremetal.txt` (bare-metal installations - used by install.sh)
3. Optionally add to `requirements.txt` (legacy/reference)

**Special Cases:**
- **PyTorch and torchaudio**: 
  - Only in `requirements-baremetal.txt` (for bare-metal)
  - Docker installs these separately in Dockerfile before requirements-prod.txt
- **sentence-transformers**: 
  - Only in `requirements-baremetal.txt` (for bare-metal)
  - Docker installs separately in Dockerfile after PyTorch
- **STT dependencies** (faster-whisper, webrtcvad):
  - Included in both `requirements-prod.txt` and `requirements-baremetal.txt`

