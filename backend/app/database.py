from sqlalchemy import create_engine, MetaData, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
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

# Convert relative database URL to absolute path if it's SQLite
database_url = settings.database_url
is_sqlite = "sqlite" in database_url

if is_sqlite and "sqlite:///" in database_url and not database_url.startswith("sqlite:////"):
    # It's a relative path, convert to absolute
    backend_dir = Path(__file__).parent.parent  # backend/app -> backend/
    relative_path = database_url.replace("sqlite:///", "")
    absolute_path = (backend_dir / relative_path).resolve()
    database_url = f"sqlite:///{absolute_path}"

# Configure engine based on database type
if is_sqlite:
    # SQLite-specific configuration for concurrent access
    # - NullPool: Don't pool connections (avoids connection pool exhaustion)
    # - timeout: Wait up to 30 seconds for database locks instead of failing immediately
    # - check_same_thread: Allow connections to be used across threads (needed for async)
    engine = create_engine(
        database_url,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,  # Wait up to 30s for database locks
        },
        poolclass=NullPool,  # Don't pool SQLite connections - avoids pool exhaustion
    )
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """
        Configure SQLite PRAGMA settings for better concurrent access.
        These settings are applied each time a connection is established.
        """
        cursor = dbapi_connection.cursor()
        
        # WAL mode allows concurrent reads while writing
        # This is the key setting for preventing "database is locked" errors
        cursor.execute("PRAGMA journal_mode=WAL")
        
        # Busy timeout - wait this many milliseconds before giving up on locks
        # This complements the connect_args timeout
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
        
        # NORMAL synchronous is faster than FULL while still being safe with WAL
        cursor.execute("PRAGMA synchronous=NORMAL")
        
        # Enable foreign key constraints (SQLite doesn't enable by default)
        cursor.execute("PRAGMA foreign_keys=ON")
        
        # Use memory for temp tables (faster)
        cursor.execute("PRAGMA temp_store=MEMORY")
        
        # Increase cache size (default is 2000 pages, ~8MB with 4KB pages)
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        
        cursor.close()
        
    logger.info(f"SQLite database configured with WAL mode and NullPool: {database_url}")
else:
    # Non-SQLite database (PostgreSQL, MySQL, etc.)
    # Configure connection pool to handle concurrent requests better
    # Pool settings are configurable via config.yaml for production tuning
    pool_size = settings.db_pool_size
    max_overflow = settings.db_max_overflow
    pool_timeout = settings.db_pool_timeout
    
    engine = create_engine(
        database_url,
        pool_size=pool_size,        # Base pool size (configurable, default: 20)
        max_overflow=max_overflow,  # Additional connections when pool exhausted (configurable, default: 40)
        pool_timeout=pool_timeout,  # Seconds to wait for connection (configurable, default: 30)
        pool_pre_ping=True,         # Verify connections are alive before using them
        pool_recycle=3600,          # Recycle connections after 1 hour to avoid stale connections
    )
    logger.info(f"PostgreSQL/MySQL database configured with connection pool (size={pool_size}, max_overflow={max_overflow}, timeout={pool_timeout}s, max_total={pool_size + max_overflow})")

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
