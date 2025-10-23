# Docker Troubleshooting Guide for Kahani

## Problem: Frontend loads but login/API calls fail with "load failed" error

This guide helps you diagnose and fix Docker connectivity issues between the frontend and backend services.

## Quick Fix

1. **Use the fixed Docker Compose configuration:**
   ```bash
   docker-compose -f docker-compose.fixed.yml down
   docker-compose -f docker-compose.fixed.yml up -d
   ```

2. **Or apply the fixes to your current setup:**
   ```bash
   # Stop current containers
   docker-compose down
   
   # Rebuild with fixes
   docker-compose up -d --build
   ```

## Common Issues and Solutions

### 1. CORS Configuration Issues

**Problem:** Frontend can't make API calls due to CORS errors.

**Solution:** The backend needs proper CORS configuration for Docker.

**Check:** Look for CORS errors in browser console or backend logs.

**Fix:** Ensure these environment variables are set in docker-compose.yml:
```yaml
environment:
  - CORS_ORIGINS=["http://localhost:6789","http://localhost:3000","http://localhost:3001"]
  - DOCKER_CONTAINER=true
```

### 2. Network Connectivity Issues

**Problem:** Containers can't communicate with each other.

**Solution:** Use a proper Docker network.

**Check:** Run the debug script:
```bash
./docker-debug.sh
```

**Fix:** Use the fixed docker-compose.yml with network configuration.

### 3. Backend Not Starting Properly

**Problem:** Backend container starts but API endpoints don't work.

**Check:** 
```bash
docker logs kahani-backend
```

**Common causes:**
- Database permissions issues
- Missing environment variables
- Port conflicts

**Fix:**
```bash
# Check if backend is healthy
curl http://localhost:9876/health

# If not responding, check logs
docker logs kahani-backend | grep -E "(ERROR|WARN)"
```

### 4. Frontend API Configuration

**Problem:** Frontend is configured with wrong API URL.

**Check:** Look at browser network tab for failed requests.

**Fix:** Ensure frontend has correct API URL:
```yaml
environment:
  - NEXT_PUBLIC_API_URL=http://localhost:9876
  - NEXT_PUBLIC_API_BASE_URL=http://localhost:9876
```

## Debugging Steps

### Step 1: Check Container Status
```bash
docker ps
```
Both `kahani-backend` and `kahani-frontend` should be running.

### Step 2: Check Backend Health
```bash
curl http://localhost:9876/health
```
Should return JSON with status "healthy".

### Step 3: Check Frontend Accessibility
```bash
curl http://localhost:6789/
```
Should return HTML (Next.js app).

### Step 4: Check Container Logs
```bash
# Backend logs
docker logs kahani-backend | grep -E "(ERROR|WARN|CORS)"

# Frontend logs  
docker logs kahani-frontend | grep -E "(ERROR|WARN|API)"
```

### Step 5: Test API Endpoints
```bash
# Test login endpoint
curl -X POST http://localhost:9876/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'
```

## Environment Variables Reference

### Backend Environment Variables
```yaml
environment:
  - DATABASE_URL=sqlite:///./data/kahani.db
  - SECRET_KEY=your-secret-key
  - JWT_SECRET_KEY=your-jwt-secret
  - CORS_ORIGINS=["http://localhost:6789","http://localhost:3000","http://localhost:3001"]
  - DOCKER_CONTAINER=true
  - KAHANI_ENV=development
  - PORT=9876
```

### Frontend Environment Variables
```yaml
environment:
  - NEXT_PUBLIC_API_URL=http://localhost:9876
  - NEXT_PUBLIC_API_BASE_URL=http://localhost:9876
  - PORT=6789
```

## Complete Working Configuration

Use `docker-compose.fixed.yml` which includes:

1. **Proper networking** with a dedicated bridge network
2. **Health checks** for both services
3. **Correct CORS configuration** for Docker
4. **Service dependencies** to ensure proper startup order
5. **Container names** for network resolution

## Manual Testing

### Test Backend API
```bash
# Health check
curl http://localhost:9876/health

# API docs
curl http://localhost:9876/docs

# Test CORS
curl -X OPTIONS \
  -H "Origin: http://localhost:6789" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  http://localhost:9876/api/auth/login
```

### Test Frontend
```bash
# Check if frontend loads
curl http://localhost:6789/

# Check if frontend can reach backend (from inside container)
docker exec kahani-frontend curl http://backend:9876/health
```

## Still Having Issues?

1. **Check the debug script:**
   ```bash
   ./docker-debug.sh
   ```

2. **Rebuild everything:**
   ```bash
   docker-compose down
   docker system prune -f
   docker-compose -f docker-compose.fixed.yml up -d --build
   ```

3. **Check for port conflicts:**
   ```bash
   lsof -i :9876
   lsof -i :6789
   ```

4. **Verify Docker network:**
   ```bash
   docker network ls
   docker network inspect kahani_kahani-network
   ```

## Logs to Check

- **Backend logs:** `docker logs kahani-backend`
- **Frontend logs:** `docker logs kahani-frontend`
- **Docker compose logs:** `docker-compose logs`
- **Browser console:** Open DevTools and check for network errors

## Success Indicators

✅ Backend responds to health check  
✅ Frontend loads without errors  
✅ No CORS errors in browser console  
✅ API calls succeed (check Network tab)  
✅ Login works without "load failed" errors
