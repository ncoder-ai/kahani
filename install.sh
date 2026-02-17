#!/bin/bash

# Kahani Installation Script
# Installs the Kahani application and all dependencies
# Assumes system dependencies (Python, Node.js, Git) are already installed
# For system dependencies, run './install-system-deps.sh' first

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check minimal requirements
check_requirements() {
    log_info "Checking minimal requirements..."
    
    local missing_deps=()
    
    # Check for essential tools (Python 3.11+)
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            break
        fi
    done
    
    if [[ -z "$python_cmd" ]]; then
        missing_deps+=("python3.11+")
    fi
    
    if ! command_exists node; then
        missing_deps+=("node")
    fi
    
    if ! command_exists git; then
        missing_deps+=("git")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_deps[*]}"
        log_info "Please install these manually:"
        log_info "  - Python 3.11+ (https://python.org/downloads/)"
        log_info "  - Node.js 18+ (https://nodejs.org/)"
        log_info "  - Git (https://git-scm.com/)"
        exit 1
    fi
    
    # Check Python version (3.11+)
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            break
        fi
    done
    
    if [[ -n "$python_cmd" ]]; then
        python_version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ $(echo "$python_version" | cut -d. -f1) -lt 3 ]] || [[ $(echo "$python_version" | cut -d. -f2) -lt 11 ]]; then
            log_error "Python 3.11+ required, found: $python_version"
            log_info "Please upgrade Python manually"
            exit 1
        fi
    fi
    
    # Check Node version
    node_version=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [[ $node_version -lt 18 ]]; then
        log_error "Node.js 18+ required, found: v$node_version"
        log_info "Please upgrade Node.js manually"
        exit 1
    fi
    
    log_success "All requirements satisfied"
}

# Setup Python environment
setup_python_env() {
    log_info "Setting up Python virtual environment..."
    
    # Find the best available Python version
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            log_info "Using Python version: $python_cmd"
            break
        fi
    done
    
    if [[ -z "$python_cmd" ]]; then
        log_error "No suitable Python version found (3.11+)"
        exit 1
    fi
    
    # Create virtual environment
    $python_cmd -m venv .venv
    
    # Activate and upgrade pip
    source .venv/bin/activate
    pip install --upgrade pip
    
    # Install Python dependencies
    # Use requirements-baremetal.txt for bare-metal installations (includes torch and sentence-transformers)
    # Docker installations should use Dockerfile which handles dependencies differently
    log_info "Installing Python dependencies..."
    if [[ -f "backend/requirements-baremetal.txt" ]]; then
        log_info "Using bare-metal requirements (includes PyTorch CPU-only and sentence-transformers)..."
        
        # Install PyTorch CPU-only first (must be before sentence-transformers)
        # This avoids installing GPU dependencies (~900MB vs ~150MB)
        log_info "Installing PyTorch CPU-only (this may take a few minutes)..."
        pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.6.0+cpu torchaudio==2.6.0 || {
            log_warning "Failed to install PyTorch CPU-only from PyTorch index, falling back to PyPI"
            log_warning "Note: This will install GPU-enabled PyTorch (~900MB)"
            pip install --no-cache-dir torch>=2.0.0,<3.0.0 torchaudio>=2.0.0
        }
        
        # Install remaining dependencies
        pip install -r backend/requirements-baremetal.txt
    else
        log_warning "requirements-baremetal.txt not found, falling back to requirements.txt"
        log_warning "Note: torch and sentence-transformers may need to be installed separately"
        pip install -r backend/requirements.txt
    fi
    
    log_success "Python environment setup complete"
}

# Setup Node.js dependencies
setup_nodejs_env() {
    log_info "Setting up Node.js environment..."
    
    cd frontend
    # Use --legacy-peer-deps to handle React 19 peer dependency conflicts
    npm install --legacy-peer-deps || {
        log_error "npm install failed"
        exit 1
    }
    cd ..
    
    log_success "Node.js environment setup complete"
}

# Download AI models
download_ai_models() {
    log_info "Downloading AI models for semantic memory..."
    log_info "This may take several minutes..."
    
    source .venv/bin/activate
    cd backend
    python download_models.py || {
        log_warning "Model download failed, continuing anyway"
        log_info "You can download models later: cd backend && python download_models.py"
    }
    cd ..
    
    log_success "AI models download complete"
}

# Setup database
setup_database() {
    log_info "Setting up database..."
    
    source .venv/bin/activate
    
    # Create required directories with proper permissions
    mkdir -p backend/data backend/backups backend/logs exports backend/data/audio
    chmod -R 755 backend/data backend/backups backend/logs exports
    
    # Debug: Check directory permissions
    log_info "Checking directory permissions..."
    ls -la backend/ | grep data
    
    # Find the best available Python version
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            break
        fi
    done
    
    if [[ -z "$python_cmd" ]]; then
        log_error "No suitable Python version found (3.11+)"
        exit 1
    fi
    
    log_info "Using Python command: $python_cmd"
    
    # Run Alembic migrations to create/upgrade database schema
    # This is the ONLY way database schema should be modified
    log_info "Setting up database schema using Alembic..."
    source .venv/bin/activate
    cd backend
    
    # Check if database file exists
    if [[ -f data/kahani.db ]]; then
        log_info "Database file exists, checking Alembic version..."
        
        # Check if alembic_version table exists
        # If it doesn't, the database was created by old init_database.py
        # We need to stamp it with the initial revision before upgrading
        if ! $python_cmd -c "
import sqlite3
from pathlib import Path

db_path = Path('data/kahani.db')
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'\")
    result = cursor.fetchone()
    conn.close()
    exit(0 if result else 1)
else:
    exit(1)
" 2>/dev/null; then
            log_warning "Database exists but alembic_version table not found"
            log_info "This database was likely created by the old init_database.py"
            log_info "Stamping with initial revision (001) before upgrading..."
            alembic stamp 001 || {
                log_error "Failed to stamp database. You may need to recreate it."
                log_info "To recreate: rm backend/data/kahani.db && ./install.sh"
                cd ..
                deactivate
                exit 1
            }
        fi
    else
        log_info "Database file does not exist, Alembic will create it..."
    fi
    
    # Run Alembic migrations - this creates/updates all tables
    log_info "Running Alembic migrations to create/upgrade schema..."
    alembic upgrade head || {
        log_error "Alembic migration failed"
        cd ..
        deactivate
        exit 1
    }
    
    # Seed initial data (system settings, etc.)
    # This does NOT modify schema, only adds default data
    log_info "Seeding initial data..."
    $python_cmd init_database_data.py || {
        log_warning "Failed to seed initial data (database will still work)"
        log_info "You can run this manually later: cd backend && python init_database_data.py"
    }
    
    cd ..
    deactivate
    
    log_success "Database setup complete"
}

# Create environment files
create_env_files() {
    log_info "Creating environment configuration..."
    
    if [[ -f .env ]]; then
        log_info ".env file already exists, skipping..."
        return
    fi
    
    if [[ ! -f .env.example ]]; then
        log_error ".env.example not found!"
        exit 1
    fi
    
    # Copy example files
    cp .env.example .env

    if [[ ! -f config.yaml ]] && [[ -f config.yaml.example ]]; then
        cp config.yaml.example config.yaml
        log_info "Created config.yaml from config.yaml.example"
    fi

    if [[ ! -f docker-compose.yml ]] && [[ -f docker-compose.yml.example ]]; then
        cp docker-compose.yml.example docker-compose.yml
        log_info "Created docker-compose.yml from docker-compose.yml.example"
    fi
    
    # Get absolute path for database
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ABSOLUTE_DB_PATH="${SCRIPT_DIR}/backend/data/kahani.db"
    # Find the best available Python version
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            break
        fi
    done

    # Generate secure secrets
    SECRET_KEY=$($python_cmd -c "import secrets; print(secrets.token_urlsafe(32))")
    JWT_SECRET_KEY=$($python_cmd -c "import secrets; print(secrets.token_urlsafe(32))")

    # Update secrets and paths in .env file
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i '' "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
        sed -i '' "s|DATABASE_URL=.*|DATABASE_URL=sqlite:///${ABSOLUTE_DB_PATH}|g" .env
    else
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
        sed -i "s|DATABASE_URL=.*|DATABASE_URL=sqlite:///${ABSOLUTE_DB_PATH}|g" .env
    fi

    log_info "✓ Database URL: sqlite:///${ABSOLUTE_DB_PATH}"
    
    log_success "Environment configuration created"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    local errors=0
    
    # Check virtual environment
    if [[ ! -d ".venv" ]]; then
        log_error "Virtual environment not found"
        ((errors++))
    else
        log_success "Virtual environment: OK"
    fi
    
    # Check database
    if [[ ! -f "backend/data/kahani.db" ]]; then
        log_error "Database not found"
        ((errors++))
    else
        log_success "Database: OK"
    fi
    
    # Check configuration
    if [[ ! -f ".env" ]]; then
        log_error "Configuration missing"
        ((errors++))
    else
        log_success "Configuration: OK"
    fi
    
    # Check Python packages
    source .venv/bin/activate
    if ! python -c "import fastapi" 2>/dev/null; then
        log_error "Python dependencies incomplete"
        ((errors++))
    else
        log_success "Backend dependencies: OK"
    fi
    deactivate
    
    # Check Node modules
    if [[ ! -d "frontend/node_modules" ]]; then
        log_warning "Frontend dependencies might be incomplete"
    else
        log_success "Frontend dependencies: OK"
    fi
    
    if [[ $errors -gt 0 ]]; then
        log_error "Installation verification failed with $errors error(s)"
        exit 1
    fi
    
    log_success "Installation verification passed!"
}

# Main function
main() {
    echo "🎭 Kahani Installation"
    echo "====================="
    echo ""
    echo "⚠️  This script assumes you already have:"
    echo "   • Python 3.11+ installed"
    echo "   • Node.js 18+ installed"
    echo "   • Git installed"
    echo ""
    echo "💡 If you need to install system dependencies first, run:"
    echo "   ./install-system-deps.sh"
    echo ""
    
    # Check if we're in the right directory
    if [[ ! -f "backend/app/main.py" ]] || [[ ! -f "frontend/package.json" ]]; then
        log_error "Please run this script from the root directory of the Kahani project"
        exit 1
    fi
    
    check_requirements
    setup_python_env
    setup_nodejs_env
    download_ai_models
    create_env_files
    setup_database
    verify_installation
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 Installation completed!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🚀 Start the application:"
    echo "   ./start-dev.sh"
    echo ""
    echo "🌐 Access URLs:"
    echo "   Application: http://localhost:6789"
    echo "   API:        http://localhost:9876"
    echo ""
    echo "🔐 Register your first account to get started"
    echo ""
}

main "$@"
