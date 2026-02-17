#!/usr/bin/env python3
"""
Startup script for Uvicorn that respects log_level from config.yaml
"""
import os
import sys
import yaml
from pathlib import Path

# Find config.yaml using same logic as app/config.py
def find_config_file():
    """Find config.yaml in possible locations"""
    # Try to determine backend directory
    # If running from /app (Docker), backend is current dir
    # If running from project root, need to go into backend
    possible_locations = [
        Path("/app/config.yaml"),     # Docker mount location
        Path(__file__).parent.parent / "config.yaml",  # Project root (from backend/)
        Path("config.yaml"),           # Current directory fallback
    ]
    
    for location in possible_locations:
        if location.exists():
            return location
    return None

# Read log level from config.yaml
log_level = "info"  # default
access_log = True

config_file = find_config_file()
if config_file:
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if config and 'logging' in config and 'log_level' in config['logging']:
                log_level = config['logging']['log_level'].lower()
                # Disable access log when log level is ERROR
                if log_level == "error":
                    access_log = False
    except Exception as e:
        print(f"Warning: Could not read config.yaml from {config_file}: {e}", file=sys.stderr)
else:
    print("Warning: config.yaml not found, using default log level 'info'", file=sys.stderr)

# Import uvicorn after reading config
import uvicorn

# Get port from environment or default
port = int(os.getenv("PORT", "9876"))
host = os.getenv("HOST", "0.0.0.0")

# Start Uvicorn with configured log level
uvicorn.run(
    "app.main:app",
    host=host,
    port=port,
    log_level=log_level,
    access_log=access_log
)

