#!/bin/bash

# Kahani Configuration Validation Script
# This script validates that all configuration files are consistent and working

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Validating Kahani Configuration...${NC}"

# Function to check if a file exists
check_file() {
    if [[ -f "$1" ]]; then
        echo -e "${GREEN}✅ $1 exists${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 missing${NC}"
        return 1
    fi
}

# Function to check if a command exists
check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✅ $1 is available${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 not found${NC}"
        return 1
    fi
}

# Function to validate YAML syntax
validate_yaml() {
    if command -v python3 &> /dev/null; then
        python3 -c "import yaml; yaml.safe_load(open('$1'))" 2>/dev/null
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✅ $1 has valid YAML syntax${NC}"
            return 0
        else
            echo -e "${RED}❌ $1 has invalid YAML syntax${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️  Cannot validate YAML syntax (python3 not available)${NC}"
        return 0
    fi
}

# Function to validate JSON syntax
validate_json() {
    if command -v python3 &> /dev/null; then
        python3 -c "import json; json.load(open('$1'))" 2>/dev/null
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✅ $1 has valid JSON syntax${NC}"
            return 0
        else
            echo -e "${RED}❌ $1 has invalid JSON syntax${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️  Cannot validate JSON syntax (python3 not available)${NC}"
        return 0
    fi
}

# Function to check network configuration
check_network_config() {
    echo -e "${BLUE}🌐 Checking network configuration...${NC}"
    
    # Test network configuration utility
    if [[ -f "backend/app/utils/network_config.py" ]]; then
        python3 -c "
import sys
sys.path.append('backend')
try:
    from backend.app.utils.network_config import NetworkConfig
    config = NetworkConfig.get_deployment_config()
    print(f'Network IP: {config[\"network_ip\"]}')
    print(f'API URL: {config[\"api_url\"]}')
    print(f'Frontend URL: {config[\"frontend_url\"]}')
    print(f'CORS Origins: {config[\"cors_origins\"]}')
    print('✅ Network configuration working')
except Exception as e:
    print(f'❌ Network configuration error: {e}')
    sys.exit(1)
" 2>/dev/null
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✅ Network configuration is working${NC}"
        else
            echo -e "${RED}❌ Network configuration has issues${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ Network configuration utility not found${NC}"
        return 1
    fi
}

# Main validation
echo -e "${BLUE}📋 Checking required files...${NC}"

# Check core configuration files
check_file "config.yaml" || exit 1
check_file "env.template" || exit 1
check_file "setup-env.sh" || exit 1

# Check backend files
check_file "backend/app/config.py" || exit 1
check_file "backend/app/main.py" || exit 1
check_file "backend/app/utils/network_config.py" || exit 1

# Check frontend files
check_file "frontend/package.json" || exit 1
check_file "frontend/next.config.js" || exit 1

# Check scripts
check_file "start-dev.sh" || exit 1
check_file "start-prod.sh" || exit 1

# Validate file syntax
echo -e "${BLUE}🔍 Validating file syntax...${NC}"
validate_yaml "config.yaml" || exit 1
validate_json "frontend/package.json" || exit 1

# Check required commands
echo -e "${BLUE}🛠️  Checking required tools...${NC}"
check_command "python3" || exit 1
check_command "node" || exit 1
check_command "npm" || exit 1

# Check network configuration
check_network_config || exit 1

# Check if .env exists, if not suggest setup
if [[ ! -f ".env" ]]; then
    echo -e "${YELLOW}⚠️  .env file not found. Run ./setup-env.sh to create it${NC}"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Check if virtual environment exists
if [[ -d "venv" ]] || [[ -d ".venv" ]]; then
    echo -e "${GREEN}✅ Python virtual environment found${NC}"
else
    echo -e "${YELLOW}⚠️  Python virtual environment not found. Consider creating one${NC}"
fi

# Check if node_modules exists
if [[ -d "frontend/node_modules" ]]; then
    echo -e "${GREEN}✅ Frontend dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  Frontend dependencies not installed. Run npm install in frontend/ directory${NC}"
fi

echo -e "${GREEN}🎉 Configuration validation complete!${NC}"
echo ""
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Run ./setup-env.sh if .env doesn't exist"
echo "2. Run ./start-dev.sh to start the development server"
echo "3. Access the application at http://localhost:6789"
