# PostgreSQL Testing Guide

This guide covers testing Kahani with PostgreSQL instead of the default SQLite database.

## Overview

Kahani supports both SQLite (default) and PostgreSQL databases. This guide is divided into two phases:

1. **Phase 1**: Test PostgreSQL as a drop-in replacement (fresh database)
2. **Phase 2**: Migrate existing SQLite data to PostgreSQL

---

## Phase 1: PostgreSQL Drop-in Replacement Testing

### Prerequisites

- Docker and Docker Compose installed
- Kahani repository cloned
- Environment variables set up (`.env` file with `SECRET_KEY` and `JWT_SECRET_KEY`)

### Option A: Docker Compose Setup (Recommended)

#### Step 1: Enable PostgreSQL in Docker Compose

Edit `docker-compose.yml` and uncomment the PostgreSQL service:

```yaml
services:
  # Uncomment the postgres service
  postgres:
    image: postgres:16-alpine
    container_name: kahani-postgres
    environment:
      POSTGRES_USER: kahani
      POSTGRES_PASSWORD: kahani
      POSTGRES_DB: kahani
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"  # Optional: expose for external access
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kahani -d kahani"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped
```

Also uncomment the volumes section at the bottom:

```yaml
volumes:
  postgres_data:
```

#### Step 2: Update Backend Environment

In `docker-compose.yml`, update the backend service's `depends_on` and `DATABASE_URL`:

```yaml
backend:
  # ... other config ...
  environment:
    - DATABASE_URL=postgresql://kahani:kahani@postgres:5432/kahani
    # ... other environment variables ...
  depends_on:
    postgres:
      condition: service_healthy
```

Or set it via your `.env` file:

```bash
DATABASE_URL=postgresql://kahani:kahani@postgres:5432/kahani
```

#### Step 3: Build and Start

```bash
# Rebuild to include psycopg2-binary
docker-compose build backend

# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f backend
```

#### Step 4: Verify Database Connection

The backend logs should show:
```
🐘 PostgreSQL database detected
✅ PostgreSQL is ready!
🗄️ Running Alembic migrations to upgrade schema...
```

### Option B: Local PostgreSQL Setup

#### Step 1: Install PostgreSQL

```bash
# macOS
brew install postgresql@16
brew services start postgresql@16

# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

#### Step 2: Create Database and User

```bash
# Connect to PostgreSQL
psql postgres

# Create user and database
CREATE USER kahani WITH PASSWORD 'kahani';
CREATE DATABASE kahani OWNER kahani;
GRANT ALL PRIVILEGES ON DATABASE kahani TO kahani;
\q
```

#### Step 3: Install Python Dependencies

```bash
cd backend
source ../.venv/bin/activate  # or your virtualenv
pip install psycopg2-binary
```

#### Step 4: Set Environment Variable

```bash
export DATABASE_URL="postgresql://kahani:kahani@localhost:5432/kahani"
```

Or add to your `.env` file.

#### Step 5: Run Migrations

```bash
cd backend
alembic upgrade head
```

#### Step 6: Start the Application

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 9876 --reload
```

### Testing Checklist for Phase 1

After setting up PostgreSQL, verify the following:

- [ ] Application starts without errors
- [ ] Database connection is established (check logs)
- [ ] Alembic migrations run successfully
- [ ] Can register a new user
- [ ] Can log in with the new user
- [ ] Can create a new story
- [ ] Can add scenes to the story
- [ ] Can view and edit story settings
- [ ] All API endpoints respond correctly
- [ ] WebSocket connections work (STT/TTS if configured)

### Switching Back to SQLite

To switch back to SQLite:

1. Remove or comment out `DATABASE_URL` from your environment
2. Or set it back to SQLite:
   ```bash
   export DATABASE_URL="sqlite:///./data/kahani.db"
   ```
3. Restart the application

---

## Phase 2: Data Migration from SQLite to PostgreSQL

### Prerequisites

- Phase 1 completed successfully (PostgreSQL working with fresh database)
- Existing SQLite database with data you want to migrate

### Step 1: Backup Your SQLite Database

**IMPORTANT**: Always backup before migration!

```bash
cd backend
cp data/kahani.db data/kahani_backup_$(date +%Y%m%d_%H%M%S).db
```

### Step 2: Ensure PostgreSQL is Running

Make sure your PostgreSQL database is running and accessible.

### Step 3: Run the Migration Script

```bash
cd backend
python migrate_sqlite_to_postgres.py
```

The script will:
1. Connect to your SQLite database
2. Connect to your PostgreSQL database
3. Run Alembic migrations on PostgreSQL (if needed)
4. Transfer all data from SQLite to PostgreSQL
5. Verify data integrity
6. Report any errors

### Step 4: Verify Migration

```bash
# Check table counts match
python migrate_sqlite_to_postgres.py --verify-only
```

### Step 5: Test the Application

1. Start the application with PostgreSQL
2. Log in with an existing user
3. Verify your stories and data are present
4. Test creating new content

### Rollback (If Needed)

If something goes wrong:

1. Stop the application
2. Set `DATABASE_URL` back to SQLite
3. Restore from backup if needed:
   ```bash
   cp data/kahani_backup_YYYYMMDD_HHMMSS.db data/kahani.db
   ```
4. Restart the application

---

## Troubleshooting

### Connection Refused

```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Solution**: Ensure PostgreSQL is running and accessible at the specified host/port.

### Authentication Failed

```
psycopg2.OperationalError: FATAL: password authentication failed
```

**Solution**: Verify username and password in your connection string.

### Database Does Not Exist

```
psycopg2.OperationalError: FATAL: database "kahani" does not exist
```

**Solution**: Create the database first:
```sql
CREATE DATABASE kahani;
```

### Permission Denied

```
psycopg2.ProgrammingError: permission denied for table
```

**Solution**: Grant permissions to the user:
```sql
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO kahani;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO kahani;
```

### Migration Conflicts

If Alembic reports migration conflicts:

```bash
# Check current state
cd backend
alembic current

# If needed, stamp to current head (use with caution)
alembic stamp head
```

---

## Environment Variable Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `postgresql://user:pass@host:5432/db` |

### Connection String Format

```
postgresql://[user]:[password]@[host]:[port]/[database]
```

Examples:
- Docker Compose: `postgresql://kahani:kahani@postgres:5432/kahani`
- Local: `postgresql://kahani:kahani@localhost:5432/kahani`
- Remote: `postgresql://user:password@db.example.com:5432/kahani`

---

## Notes

- The application automatically detects the database type from the connection string
- SQLite-specific optimizations (WAL mode, PRAGMA settings) are only applied for SQLite
- PostgreSQL uses standard connection pooling
- Alembic migrations handle database-specific SQL syntax differences
- Some migrations have conditional logic for SQLite vs PostgreSQL

