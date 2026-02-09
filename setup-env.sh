#!/bin/bash

# Kahani Environment Setup Script
# This script creates the .env file with proper configuration

set -e

echo "🔧 Setting up Kahani environment configuration..."

# Create .env file if it doesn't exist
if [[ ! -f .env ]]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ .env file created from .env.example"
else
    echo "✅ .env file already exists"
fi

# Make sure the script is executable
chmod +x setup-env.sh

echo "🎉 Environment setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Review and customize .env file if needed"
echo "2. Run ./start-dev.sh to start the development server"
echo "3. Access the application at http://localhost:6789"