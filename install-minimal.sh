#!/bin/bash

# Kahani Minimal Installation Script
# Only installs what's absolutely necessary
# Safe for test servers and development environments

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
    
    # Check for essential tools
    if ! command_exists python3; then
        missing_deps+=("python3")
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
    
    # Check Python version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ $(echo "$python_version" | cut -d. -f1) -lt 3 ]] || [[ $(echo "$python_version" | cut -d. -f2) -lt 11 ]]; then
        log_error "Python 3.11+ required, found: $python_version"
        log_info "Please upgrade Python manually"
        exit 1
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
    
    # Create virtual environment
    python3 -m venv .venv
    
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
    
    # Create required directories
    mkdir -p backend/data backend/backups backend/logs exports data/audio backend/data/chromadb
    
    # Initialize database
    if [[ -f backend/data/kahani.db ]]; then
        log_warning "Database already exists, skipping initialization"
        return
    fi
    
    log_info "Initializing database..."
    cd backend && python init_database.py && cd .. || {
        log_error "Database initialization failed"
        exit 1
    }
    
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
    
    # Generate secure secrets
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    
    # Update secrets in .env file
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i '' "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
    else
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
    fi
    
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
    echo "🎭 Kahani Minimal Installation"
    echo "=============================="
    echo ""
    echo "⚠️  This script assumes you already have:"
    echo "   • Python 3.11+ installed"
    echo "   • Node.js 18+ installed"
    echo "   • Git installed"
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
    setup_database
    create_env_files
    verify_installation
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 Minimal installation completed!"
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
