# Requirements Files Documentation

This directory contains multiple requirements files for different installation scenarios.

## Files Overview

### `requirements.txt` - Base Docker Requirements
**Use for:** Docker builds only
**Contains:** Core dependencies without PyTorch or sentence-transformers
**Note:** PyTorch and sentence-transformers are installed separately in the Dockerfile after PyTorch CPU is set up

### `requirements-prod.txt` - Production Docker Requirements  
**Use for:** Production Docker builds
**Contains:** Same as `requirements.txt` but without test dependencies (pytest, etc.)
**Note:** More minimal, production-focused version for Docker

### `requirements-baremetal.txt` - Bare-Metal Installation Requirements
**Use for:** Non-Docker installations (Linux, macOS, Windows)
**Contains:** All dependencies including:
- PyTorch CPU-only version
- sentence-transformers
- All other core dependencies
**Installation:** Used automatically by `install.sh`

## Installation Commands

### For Development (Bare-Metal)
```bash
./install.sh
# Uses requirements-baremetal.txt automatically
```

### For Docker
```bash
docker-compose up --build
# Uses requirements.txt + Dockerfile installs
```

### For Production Docker
```bash
# Build uses requirements-prod.txt via Dockerfile
docker build -f Dockerfile -t kahani:latest .
```

## Why Multiple Files?

**PyTorch Installation Order:**
- PyTorch must be installed before sentence-transformers
- Docker: Dockerfile installs PyTorch CPU first, then sentence-transformers
- Bare-metal: requirements-baremetal.txt installs in correct order using `--extra-index-url`

**Size Optimization:**
- Docker: Can use optimized PyTorch CPU builds
- Bare-metal: Uses PyTorch CPU from official PyTorch index
- Production: Excludes test dependencies to reduce image size

## Maintenance

When adding new dependencies:
1. Add to `requirements.txt` (Docker base)
2. Add to `requirements-prod.txt` if production-relevant
3. Add to `requirements-baremetal.txt` if non-Docker installation needs it

**Exception:** PyTorch and sentence-transformers
- Only in `requirements-baremetal.txt`
- Docker installs these via Dockerfile

