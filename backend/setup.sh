#!/bin/bash

# Kahani Backend Setup Script
# This script sets up the backend environment and downloads all required models

set -e  # Exit on error

echo "============================================"
echo "🚀 Kahani Backend Setup"
echo "============================================"

# Check if we're in the backend directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found"
    echo "   Please run this script from the backend directory"
    exit 1
fi

# Check Python version
echo ""
echo "📋 Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "   Found Python $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python -m venv .venv
    echo "   ✅ Virtual environment created"
else
    echo ""
    echo "📦 Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo ""
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Download AI models
echo ""
echo "🤖 Downloading AI models..."
python download_models.py

# Run database migrations
echo ""
echo "🗄️  Running database migrations..."

# Semantic memory migration
if [ -f "migrate_add_semantic_memory.py" ]; then
    echo "   Running semantic memory migration..."
    python migrate_add_semantic_memory.py
else
    echo "   ⚠️  Semantic memory migration not found, skipping..."
fi

# Entity states migration
if [ -f "migrate_add_entity_states.py" ]; then
    echo "   Running entity states migration..."
    python migrate_add_entity_states.py
else
    echo "   ⚠️  Entity states migration not found, skipping..."
fi

echo "   ✅ Database migrations complete"

# Create necessary directories
echo ""
echo "📁 Creating data directories..."
mkdir -p data/chromadb
mkdir -p data/exports
mkdir -p logs
echo "   ✅ Directories created"

echo ""
echo "============================================"
echo "✅ Setup Complete!"
echo "============================================"
echo ""
echo "To start the backend server:"
echo "  1. Activate the virtual environment:"
echo "     source .venv/bin/activate"
echo ""
echo "  2. Start the server:"
echo "     uvicorn app.main:app --host 0.0.0.0 --port 9876 --reload"
echo ""
echo "Or use the start script:"
echo "  ./start.sh"
echo ""

