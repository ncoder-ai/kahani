#!/usr/bin/env python3
"""
Read configuration values from config.yaml
Usage: python3 read-config.py <key>
Example: python3 read-config.py backend_port
"""
import sys
import yaml
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print("Usage: read-config.py <key>", file=sys.stderr)
        print("Available keys: backend_port, frontend_port, backend_host", file=sys.stderr)
        sys.exit(1)
    
    key = sys.argv[1]
    
    # Find config.yaml in project root (same directory as this script)
    script_dir = Path(__file__).parent
    config_file = script_dir / "config.yaml"
    
    if not config_file.exists():
        print(f"Error: config.yaml not found at {config_file}", file=sys.stderr)
        print(f"Please ensure config.yaml exists in the project root directory.", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing config.yaml: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading config.yaml: {e}", file=sys.stderr)
        sys.exit(1)
    
    if config is None:
        print("Error: config.yaml is empty", file=sys.stderr)
        sys.exit(1)
    
    # Map keys to config paths
    mappings = {
        'backend_port': ['server', 'backend', 'port'],
        'frontend_port': ['server', 'frontend', 'port'],
        'backend_host': ['server', 'backend', 'host'],
    }
    
    if key not in mappings:
        print(f"Error: Unknown key '{key}'", file=sys.stderr)
        print(f"Available keys: {', '.join(mappings.keys())}", file=sys.stderr)
        sys.exit(1)
    
    # Navigate nested config
    value = config
    path = mappings[key]
    for p in path:
        if not isinstance(value, dict):
            print(f"Error: Expected dictionary at {'.'.join(path[:path.index(p)])}, got {type(value).__name__}", file=sys.stderr)
            sys.exit(1)
        if p not in value:
            print(f"Error: {'.'.join(path)} not found in config.yaml", file=sys.stderr)
            print(f"Please ensure config.yaml has the following structure:", file=sys.stderr)
            print(f"  {' -> '.join(path)}", file=sys.stderr)
            sys.exit(1)
        value = value[p]
    
    # Validate port values
    if 'port' in key:
        if not isinstance(value, int):
            print(f"Error: Invalid port value '{value}' (must be an integer)", file=sys.stderr)
            sys.exit(1)
        if value < 1 or value > 65535:
            print(f"Error: Invalid port {value} (must be between 1 and 65535)", file=sys.stderr)
            sys.exit(1)
    
    # Output the value
    print(value)

if __name__ == "__main__":
    main()







