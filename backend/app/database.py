from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from .config import settings
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure data directory exists
try:
    os.makedirs(settings.data_dir, exist_ok=True)
    # Test if we can write to the data directory
    test_file = os.path.join(settings.data_dir, '.test_write')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
except (PermissionError, OSError) as e:
    logger.warning(f"Cannot write to data directory {settings.data_dir}: {e}")
    logger.warning("Database operations may fail. Check directory permissions.")

database_url = settings.database_url

# PostgreSQL connection pool configuration
pool_size = settings.db_pool_size
max_overflow = settings.db_max_overflow
pool_timeout = settings.db_pool_timeout

engine = create_engine(
    database_url,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=pool_timeout,
    pool_pre_ping=True,
    pool_recycle=3600,
)
logger.info(f"PostgreSQL database configured with connection pool (size={pool_size}, max_overflow={max_overflow}, timeout={pool_timeout}s, max_total={pool_size + max_overflow})")

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get database session (for FastAPI routes)
def get_db():
    """
    FastAPI dependency that yields a database session.
    The session is automatically closed when the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_background_db():
    """
    Context manager for database sessions in background tasks.

    Background tasks (asyncio.create_task, BackgroundTasks) should use this
    instead of get_db() because they run outside the request lifecycle.

    This ensures proper cleanup with rollback on errors:

    Usage:
        with get_background_db() as db:
            # do database operations
            db.commit()  # if needed
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.warning(f"Background DB session error, rolling back: {e}")
        db.rollback()
        raise
    finally:
        db.close()
