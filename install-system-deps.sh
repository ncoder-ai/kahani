#!/bin/bash

# Kahani System Dependencies Installation Script
# Installs only system-wide dependencies (Python, Node.js, etc.)
# Supports Linux and macOS
# Author: Kahani Team
# Description: System dependencies installer for Kahani storytelling platform

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        log_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
    log_info "Detected OS: $OS"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    local missing_deps=()
    
    # Check for essential tools
    if ! command_exists curl; then
        missing_deps+=("curl")
    fi
    
    if ! command_exists git; then
        missing_deps+=("git")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_deps[*]}"
        log_info "Please install these tools before continuing"
        exit 1
    fi
    
    # Check available disk space (need at least 5GB for models)
    if [[ "$OS" == "linux" ]]; then
        available_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    else
        available_space=$(df -g . | awk 'NR==2 {print $4}')
    fi
    
    if [[ $available_space -lt 5 ]]; then
        log_warning "Low disk space: ${available_space}GB available. Recommended: 5GB+ (includes AI models)"
    fi
    
    log_success "System requirements check passed"
}

# Install system dependencies
install_system_deps() {
    log_info "Installing system dependencies..."
    log_info "Using --no-upgrade flag to avoid breaking existing system packages"
    
    if [[ "$OS" == "linux" ]]; then
        # Install ONLY essential build tools and libraries required for:
        # - PyTorch compilation (build-essential)
        # - cryptography library (libssl-dev, libffi-dev)
        # - Python packages (zlib1g-dev for compression)
        # - SQLite support (libsqlite3-dev)
        # - Basic build tools (build-essential includes gcc, g++, make)
        sudo apt install -y --no-upgrade \
            build-essential \
            libssl-dev \
            libffi-dev \
            zlib1g-dev \
            libsqlite3-dev
        
    elif [[ "$OS" == "macos" ]]; then
        # Check if Homebrew is installed
        if ! command_exists brew; then
            log_info "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        
        # Install only essential packages (don't upgrade existing ones)
        # Note: macOS typically has most of these already installed
        # Use --force to reinstall if already installed, but don't upgrade system packages
        brew install --ignore-dependencies curl wget git openssl 2>/dev/null || true
    fi
    
    log_success "System dependencies installed"
}

# Install Python
install_python() {
    # Check for Python 3.11+ (3.11, 3.12, 3.13, etc.)
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            log_info "Python $version already installed"
            break
        fi
    done
    
    if [[ -n "$python_cmd" ]]; then
        return
    fi
    
    log_info "Installing Python 3.11+ (will try 3.12 first, then 3.11)..."
    
    if [[ "$OS" == "linux" ]]; then
        # Try Python 3.12 first (newer, often available in default repos)
        if sudo apt install -y --no-upgrade python3.12 python3.12-venv python3.12-pip 2>/dev/null; then
            log_success "Python 3.12 installed from default repositories"
        elif sudo apt install -y --no-upgrade python3.11 python3.11-venv python3.11-pip 2>/dev/null; then
            log_success "Python 3.11 installed from default repositories"
        else
            log_info "Python 3.11+ not available in default repos, adding deadsnakes PPA..."
            # Only install software-properties-common if not already installed
            sudo apt install -y --no-upgrade software-properties-common
            sudo add-apt-repository -y ppa:deadsnakes/ppa
            # Only update package list for the new PPA, don't touch existing packages
            # Use --allow-releaseinfo-change to avoid errors if release info changed
            sudo apt update --allow-releaseinfo-change
            sudo apt install -y --no-upgrade python3.11 python3.11-venv python3.11-pip
        fi
        
    elif [[ "$OS" == "macos" ]]; then
        # Try Python 3.12 first, fallback to 3.11
        # Use --force to reinstall if needed, but don't upgrade unrelated packages
        if brew install python@3.12 2>/dev/null; then
            log_success "Python 3.12 installed via Homebrew"
        else
            brew install python@3.11
        fi
    fi
    
    log_success "Python 3.11+ installed"
}

# Install Node.js
install_nodejs() {
    # Check if Node.js 20.9.0+ is already installed
    if command_exists node; then
        node_version=$(node -v | cut -d'v' -f2)
        node_major=$(echo "$node_version" | cut -d'.' -f1)
        node_minor=$(echo "$node_version" | cut -d'.' -f2)
        
        if [[ $node_major -gt 20 ]] || [[ $node_major -eq 20 && $node_minor -ge 9 ]]; then
            log_info "Node.js 20.9.0+ already installed (v$node_version)"
            return
        else
            log_warning "Node.js $node_version found, but 20.9.0+ required"
        fi
    fi
    
    log_info "Installing Node.js 20..."
    
    # Install Node.js via NodeSource
    if [[ "$OS" == "linux" ]]; then
        # Download and run NodeSource setup script
        # Note: This script will run 'apt update' to refresh package lists for the new repo
        # This is unavoidable when adding a repository, but we use --no-upgrade when installing
        # to prevent upgrading existing packages
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        
        # Check if Node.js is already installed
        if dpkg -l | grep -q "^ii.*nodejs "; then
            log_info "Node.js is already installed. Removing old version to install Node.js 20..."
            # Remove old Node.js without removing dependencies
            sudo apt-get remove -y nodejs 2>/dev/null || true
        fi
        
        # Install Node.js 20 (allowing upgrade/replacement of nodejs package)
        # We allow upgrading nodejs specifically, but not other packages
        sudo apt-get install -y nodejs
        
    elif [[ "$OS" == "macos" ]]; then
        # Install Node.js 20 without upgrading existing packages
        # Check if node@20 is already installed first
        if brew list node@20 &>/dev/null; then
            log_info "Node.js 20 already installed via Homebrew"
        else
            brew install node@20
        fi
        # Link it (this won't upgrade, just switch symlinks)
        brew link --overwrite node@20 2>/dev/null || true
    fi
    
    log_success "Node.js 20 installed"
}

# Verify system dependencies
verify_system_deps() {
    log_info "Verifying system dependencies..."
    
    local errors=0
    
    # Check Python installation (3.11+)
    local python_cmd=""
    for version in 3.13 3.12 3.11; do
        if command_exists "python$version"; then
            python_cmd="python$version"
            break
        fi
    done
    
    if [[ -z "$python_cmd" ]]; then
        log_error "Python 3.11+ not found"
        ((errors++))
    else
        python_version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        log_success "Python $python_version: OK"
    fi
    
    # Check Node.js installation
    if ! command_exists node; then
        log_error "Node.js not found"
        ((errors++))
    else
        node_version=$(node -v | cut -d'v' -f2)
        node_major=$(echo "$node_version" | cut -d'.' -f1)
        node_minor=$(echo "$node_version" | cut -d'.' -f2)
        
        # Check if version is 20.9.0+
        if [[ $node_major -lt 20 ]] || [[ $node_major -eq 20 && $node_minor -lt 9 ]]; then
            log_error "Node.js $node_version found, but 20.9.0+ required"
            log_info "Please manually upgrade Node.js or re-run install-system-deps.sh"
            ((errors++))
        else
            log_success "Node.js $node_version: OK"
        fi
    fi
    
    # Check Git installation
    if ! command_exists git; then
        log_error "Git not found"
        ((errors++))
    else
        git_version=$(git --version)
        log_success "$git_version: OK"
    fi
    
    if [[ $errors -gt 0 ]]; then
        log_error "System dependencies verification failed with $errors error(s)"
        exit 1
    fi
    
    log_success "All system dependencies verified!"
}

# Main installation function
main() {
    echo "🔧 Kahani System Dependencies Installer"
    echo "======================================="
    echo ""
    echo "This script installs only system-wide dependencies:"
    echo "  • Python 3.11+"
    echo "  • Node.js 20.9.0+ (required for Next.js 16)"
    echo "  • npm 10+ (comes with Node.js 20.9.0+)"
    echo "  • Git"
    echo "  • Build tools and libraries"
    echo ""
    echo "After this, run './install.sh' to set up the application."
    echo ""
    
    detect_os
    check_requirements
    
    log_info "Starting system dependencies installation..."
    
    # Install dependencies
    install_system_deps
    install_python
    install_nodejs
    
    # Verify installation
    verify_system_deps
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 System dependencies installed successfully!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📋 What was installed:"
    echo "   ✓ Python 3.11+ with pip and venv"
    echo "   ✓ Node.js 20.9.0+ with npm 10+"
    echo "   ✓ Git"
    echo "   ✓ Essential build tools (build-essential, libssl-dev, libffi-dev, zlib1g-dev, libsqlite3-dev)"
    echo ""
    echo "🚀 Next steps:"
    echo "   1. Run './install.sh' to set up the Kahani application"
    echo "   2. Or run './install.sh' from the Kahani project directory"
    echo ""
    echo "💡 This script only installs system dependencies."
    echo "   The application setup is handled by './install.sh'"
    echo ""
}

# Run main function
main "$@"