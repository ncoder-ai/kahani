#!/bin/bash

# Docker Debug Script for Kahani
# This script helps diagnose and fix Docker connectivity issues

echo "🔍 Kahani Docker Debug Script"
echo "=============================="

# Function to check if containers are running
check_containers() {
    echo "📦 Checking container status..."
    
    if docker ps | grep -q kahani-backend; then
        echo "✅ Backend container is running"
    else
        echo "❌ Backend container is not running"
        return 1
    fi
    
    if docker ps | grep -q kahani-frontend; then
        echo "✅ Frontend container is running"
    else
        echo "❌ Frontend container is not running"
        return 1
    fi
}

# Function to check backend health
check_backend_health() {
    echo "🏥 Checking backend health..."
    
    # Check if backend responds
    if curl -f http://localhost:9876/health > /dev/null 2>&1; then
        echo "✅ Backend health check passed"
        curl -s http://localhost:9876/health | jq . 2>/dev/null || echo "Backend is responding but not JSON"
    else
        echo "❌ Backend health check failed"
        echo "Trying to get more details..."
        curl -v http://localhost:9876/health 2>&1 | head -20
    fi
}

# Function to check frontend connectivity
check_frontend_connectivity() {
    echo "🌐 Checking frontend connectivity..."
    
    if curl -f http://localhost:6789/ > /dev/null 2>&1; then
        echo "✅ Frontend is accessible"
    else
        echo "❌ Frontend is not accessible"
    fi
}

# Function to check network connectivity between containers
check_container_network() {
    echo "🔗 Checking container network connectivity..."
    
    # Check if backend can reach frontend
    echo "Backend -> Frontend connectivity:"
    docker exec kahani-backend curl -f http://frontend:6789/ > /dev/null 2>&1 && echo "✅ Backend can reach frontend" || echo "❌ Backend cannot reach frontend"
    
    # Check if frontend can reach backend
    echo "Frontend -> Backend connectivity:"
    docker exec kahani-frontend curl -f http://backend:9876/health > /dev/null 2>&1 && echo "✅ Frontend can reach backend" || echo "❌ Frontend cannot reach backend"
}

# Function to check logs
check_logs() {
    echo "📋 Checking recent logs..."
    
    echo "Backend logs (last 20 lines):"
    docker logs --tail 20 kahani-backend 2>&1 | grep -E "(ERROR|WARN|CORS|network|connection)" || echo "No relevant errors in backend logs"
    
    echo "Frontend logs (last 20 lines):"
    docker logs --tail 20 kahani-frontend 2>&1 | grep -E "(ERROR|WARN|API|connection)" || echo "No relevant errors in frontend logs"
}

# Function to test API endpoints
test_api_endpoints() {
    echo "🧪 Testing API endpoints..."
    
    # Test health endpoint
    echo "Testing /health endpoint:"
    curl -s http://localhost:9876/health | jq . 2>/dev/null || echo "Failed to get health status"
    
    # Test CORS preflight
    echo "Testing CORS preflight:"
    curl -s -X OPTIONS -H "Origin: http://localhost:6789" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: Content-Type" http://localhost:9876/api/auth/login -v 2>&1 | grep -E "(Access-Control|CORS)" || echo "CORS headers not found"
}

# Function to fix common issues
fix_common_issues() {
    echo "🔧 Attempting to fix common issues..."
    
    # Restart containers
    echo "Restarting containers..."
    docker-compose restart
    
    # Wait for containers to be ready
    echo "Waiting for containers to be ready..."
    sleep 10
    
    # Check if the issue is resolved
    if curl -f http://localhost:9876/health > /dev/null 2>&1; then
        echo "✅ Backend is now responding"
    else
        echo "❌ Backend is still not responding"
    fi
}

# Main execution
echo "Starting diagnosis..."

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install docker-compose."
    exit 1
fi

# Check if containers exist
if ! docker ps -a | grep -q kahani-backend; then
    echo "❌ Kahani containers not found. Please run 'docker-compose up -d' first."
    exit 1
fi

# Run all checks
check_containers
check_backend_health
check_frontend_connectivity
check_container_network
check_logs
test_api_endpoints

echo ""
echo "🔧 If issues were found, you can try:"
echo "1. docker-compose down && docker-compose up -d"
echo "2. Check the fixed configuration: docker-compose -f docker-compose.fixed.yml up -d"
echo "3. Check logs: docker logs kahani-backend && docker logs kahani-frontend"
echo ""
echo "For more detailed debugging, check the logs with:"
echo "docker logs kahani-backend | grep -E '(ERROR|WARN|CORS)'"
echo "docker logs kahani-frontend | grep -E '(ERROR|WARN|API)'"
