#!/bin/bash

# Test script to verify Docker connectivity
echo "🔍 Testing Kahani Docker Connectivity"
echo "===================================="

# Test 1: Check if backend is accessible from host
echo "1. Testing backend accessibility from host..."
if curl -f http://localhost:9876/health > /dev/null 2>&1; then
    echo "✅ Backend is accessible from host at localhost:9876"
    curl -s http://localhost:9876/health | jq . 2>/dev/null || echo "Backend responding (not JSON)"
else
    echo "❌ Backend is NOT accessible from host"
    echo "Trying to get more details..."
    curl -v http://localhost:9876/health 2>&1 | head -10
fi

echo ""

# Test 2: Check if frontend is accessible
echo "2. Testing frontend accessibility..."
if curl -f http://localhost:6789/ > /dev/null 2>&1; then
    echo "✅ Frontend is accessible at localhost:6789"
else
    echo "❌ Frontend is NOT accessible"
fi

echo ""

# Test 3: Check container status
echo "3. Checking container status..."
if docker ps | grep -q kahani-backend; then
    echo "✅ Backend container is running"
else
    echo "❌ Backend container is not running"
fi

if docker ps | grep -q kahani-frontend; then
    echo "✅ Frontend container is running"
else
    echo "❌ Frontend container is not running"
fi

echo ""

# Test 4: Check if backend is listening on the correct port inside container
echo "4. Testing backend port binding inside container..."
if docker exec kahani-backend netstat -tlnp | grep -q ":9876"; then
    echo "✅ Backend is listening on port 9876 inside container"
else
    echo "❌ Backend is NOT listening on port 9876 inside container"
    echo "Checking what ports are open..."
    docker exec kahani-backend netstat -tlnp 2>/dev/null || echo "netstat not available, trying ss..."
    docker exec kahani-backend ss -tlnp 2>/dev/null || echo "ss not available"
fi

echo ""

# Test 5: Check backend logs for any errors
echo "5. Checking recent backend logs for errors..."
echo "Recent backend logs:"
docker logs --tail 10 kahani-backend 2>&1 | grep -E "(ERROR|WARN|Exception|Traceback)" || echo "No errors found in recent logs"

echo ""
echo "🔧 If backend is not accessible, try:"
echo "1. docker-compose down && docker-compose up -d --build"
echo "2. Check if port 9876 is already in use: lsof -i :9876"
echo "3. Check Docker logs: docker logs kahani-backend"
