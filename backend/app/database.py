from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings
import os
from pathlib import Path

# Ensure data directory exists
os.makedirs(settings.data_dir, exist_ok=True)

# Convert relative database URL to absolute path if it's SQLite
database_url = settings.database_url
if "sqlite:///" in database_url and not database_url.startswith("sqlite:////"):
    # It's a relative path, convert to absolute
    backend_dir = Path(__file__).parent.parent  # backend/app -> backend/
    relative_path = database_url.replace("sqlite:///", "")
    absolute_path = (backend_dir / relative_path).resolve()
    database_url = f"sqlite:///{absolute_path}"
    print(f"[DATABASE] Using absolute path: {database_url}")

# Create SQLAlchemy engine
engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()