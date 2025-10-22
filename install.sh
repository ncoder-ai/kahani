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
            break
        fi
    done
    
    # Create virtual environment
    $python_cmd -m venv .venv
    
    # Activate and upgrade pip
    source .venv/bin/activate
    pip install --upgrade pip
    
    # Install Python dependencies
    log_info "Installing Python dependencies..."
    pip install -r backend/requirements.txt
    
    log_success "Python environment setup complete"
}

# Setup Node.js dependencies
setup_nodejs_env() {
    log_info "Setting up Node.js environment..."
    
    cd frontend
    npm install
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
    mkdir -p backend/data backend/backups backend/logs exports backend/data/audio backend/data/chromadb
    chmod -R 755 backend/data backend/backups backend/logs exports
    
    # Debug: Check directory permissions
    log_info "Checking directory permissions..."
    ls -la backend/ | grep data
    
    # Initialize or update database
    if [[ -f backend/data/kahani.db ]]; then
        log_warning "Database already exists, updating schema..."
        cd backend && $python_cmd update_database_schema.py && cd .. || {
            log_error "Failed to update database schema"
            exit 1
        }
    else
        log_info "Initializing database..."
        cd backend && $python_cmd init_database.py && cd .. || {
            log_error "Database initialization failed"
            exit 1
        }
    fi
    
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
    
    # Copy .env.example to .env
    cp .env.example .env
    
    # Get absolute path for database
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    ABSOLUTE_DB_PATH="${SCRIPT_DIR}/backend/data/kahani.db"
    ABSOLUTE_CHROMA_PATH="${SCRIPT_DIR}/backend/data/chromadb"
    
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
        sed -i '' "s|SEMANTIC_DB_PATH=.*|SEMANTIC_DB_PATH=${ABSOLUTE_CHROMA_PATH}|g" .env
    else
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
        sed -i "s|DATABASE_URL=.*|DATABASE_URL=sqlite:///${ABSOLUTE_DB_PATH}|g" .env
        sed -i "s|SEMANTIC_DB_PATH=.*|SEMANTIC_DB_PATH=${ABSOLUTE_CHROMA_PATH}|g" .env
    fi
    
    log_info "✓ Database URL: sqlite:///${ABSOLUTE_DB_PATH}"
    log_info "✓ ChromaDB Path: ${ABSOLUTE_CHROMA_PATH}"
    
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
    echo "🔐 Default login: test@test.com / test"
    echo ""
}

main "$@"
