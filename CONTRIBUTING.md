# Contributing to Kahani

Thank you for your interest in contributing to Kahani!

## Getting Started

### Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ncoder-ai/kahani.git
   cd kahani
   ```

2. **Copy configuration files:**
   ```bash
   cp .env.example .env
   cp config.yaml.example config.yaml
   cp docker-compose.yml.example docker-compose.yml
   ```

3. **Start with Docker (recommended):**
   ```bash
   docker compose up -d --build
   ```

   Or install locally:
   ```bash
   ./install.sh
   ./start-dev.sh
   ```

4. **Access the app:** http://localhost:6789

### Project Structure

- **Backend** (FastAPI): `backend/app/`
  - `api/` — REST endpoints
  - `services/` — Business logic
  - `models/` — SQLAlchemy ORM models
- **Frontend** (Next.js): `frontend/src/`
  - `app/` — Pages (App Router)
  - `components/` — React components
  - `lib/api/` — API client modules

See [CLAUDE.md](CLAUDE.md) for a detailed architecture overview.

## Making Changes

### Code Style

- **Python**: Follow PEP 8. Use type hints where practical.
- **TypeScript/React**: Components require `'use client'` directive. Use functional components.
- **Commits**: Write clear, concise commit messages describing the "why" not the "what".

### Common Tasks

| Task | Command |
|------|---------|
| Run backend | `cd backend && uvicorn app.main:app --reload --port 9876` |
| Run frontend | `cd frontend && npm run dev` |
| Run migrations | `cd backend && alembic upgrade head` |
| Create migration | `cd backend && alembic revision --autogenerate -m "description"` |
| Lint frontend | `cd frontend && npm run lint` |
| Rebuild Docker | `docker compose up -d --build` |

### Database Changes

1. Modify or create models in `backend/app/models/`
2. Export in `backend/app/models/__init__.py`
3. Generate migration: `cd backend && alembic revision --autogenerate -m "description"`
4. Test migration: `cd backend && alembic upgrade head`

### LLM Prompts

Edit `backend/prompts.yml` — changes are hot-reloaded on the next request.

## Pull Requests

1. Fork the repository and create a feature branch
2. Make your changes with clear commits
3. Test your changes locally (Docker or baremetal)
4. Open a PR against `main` with a description of what and why

### PR Guidelines

- Keep PRs focused — one feature or fix per PR
- Include a brief description of the change and its motivation
- If the PR changes UI, include a screenshot
- Ensure the app builds and starts without errors

## Reporting Issues

Open an issue on GitHub with:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version, browser)

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
