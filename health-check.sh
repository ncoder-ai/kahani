#!/bin/bash

# Health check script for Kahani services
# Usage: ./health-check.sh [service]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_URL=${BACKEND_URL:-"http://localhost:8000"}
FRONTEND_URL=${FRONTEND_URL:-"http://localhost:3000"}
TIMEOUT=${TIMEOUT:-10}

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_url() {
    local url=$1
    local name=$2
    local expected_status=${3:-200}
    
    log_info "Checking $name at $url..."
    
    if ! command -v curl >/dev/null 2>&1; then
        log_error "curl is required but not installed"
        return 1
    fi
    
    local response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TIMEOUT "$url" 2>/dev/null)
    
    if [[ "$response" == "$expected_status" ]]; then
        log_info "$name is healthy (HTTP $response)"
        return 0
    else
        log_error "$name is unhealthy (HTTP $response)"
        return 1
    fi
}

check_backend() {
    log_info "=== Backend Health Check ==="
    
    local healthy=true
    
    # Check main health endpoint
    if ! check_url "$BACKEND_URL/health" "Backend Health"; then
        healthy=false
    fi
    
    # Check API docs
    if ! check_url "$BACKEND_URL/docs" "API Documentation"; then
        healthy=false
    fi
    
    # Check if we can reach the auth endpoint
    if ! check_url "$BACKEND_URL/api/auth/me" "Auth Endpoint" 401; then
        log_warn "Auth endpoint check failed (this might be expected without token)"
    fi
    
    if [ "$healthy" = true ]; then
        log_info "Backend is fully operational"
        return 0
    else
        log_error "Backend has issues"
        return 1
    fi
}

check_frontend() {
    log_info "=== Frontend Health Check ==="
    
    if check_url "$FRONTEND_URL" "Frontend"; then
        log_info "Frontend is operational"
        return 0
    else
        log_error "Frontend is not responding"
        return 1
    fi
}

check_database() {
    log_info "=== Database Health Check ==="
    
    # Try to check database through backend API
    local response=$(curl -s --connect-timeout $TIMEOUT "$BACKEND_URL/api/stories" 2>/dev/null || echo "error")
    
    if [[ "$response" == *"Unauthorized"* ]] || [[ "$response" == "[]" ]]; then
        log_info "Database connection is working (got expected auth response)"
        return 0
    elif [[ "$response" == "error" ]]; then
        log_error "Cannot connect to backend for database check"
        return 1
    else
        log_info "Database connection appears to be working"
        return 0
    fi
}

check_llm() {
    log_info "=== LLM Service Health Check ==="
    
    local llm_url=${LLM_BASE_URL:-"http://localhost:1234/v1"}
    
    if check_url "$llm_url/models" "LLM Service"; then
        log_info "LLM service is responding"
        return 0
    else
        log_warn "LLM service is not responding (this might be expected if not running locally)"
        return 1
    fi
}

check_docker() {
    log_info "=== Docker Services Health Check ==="
    
    if ! command -v docker >/dev/null 2>&1; then
        log_warn "Docker is not installed or not in PATH"
        return 1
    fi
    
    local services=("kahani-backend" "kahani-frontend")
    local all_healthy=true
    
    for service in "${services[@]}"; do
        if docker ps --format "table {{.Names}}" | grep -q "$service"; then
            local status=$(docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null || echo "unknown")
            if [[ "$status" == "healthy" ]]; then
                log_info "$service container is healthy"
            elif [[ "$status" == "unknown" ]]; then
                log_warn "$service container has no health check"
            else
                log_error "$service container is unhealthy ($status)"
                all_healthy=false
            fi
        else
            log_warn "$service container is not running"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        return 0
    else
        return 1
    fi
}

run_all_checks() {
    log_info "Starting comprehensive health check for Kahani..."
    echo ""
    
    local overall_status=0
    
    if ! check_backend; then
        overall_status=1
    fi
    echo ""
    
    if ! check_frontend; then
        overall_status=1
    fi
    echo ""
    
    if ! check_database; then
        overall_status=1
    fi
    echo ""
    
    if ! check_llm; then
        # LLM failure is not critical for overall status
        true
    fi
    echo ""
    
    if ! check_docker; then
        # Docker check failure is not critical if services are running otherwise
        true
    fi
    echo ""
    
    if [ $overall_status -eq 0 ]; then
        log_info "🎉 All critical services are healthy!"
    else
        log_error "❌ Some critical services have issues"
    fi
    
    return $overall_status
}

# Main script logic
case "${1:-all}" in
    "backend")
        check_backend
        ;;
    "frontend")
        check_frontend
        ;;
    "database")
        check_database
        ;;
    "llm")
        check_llm
        ;;
    "docker")
        check_docker
        ;;
    "all"|"")
        run_all_checks
        ;;
    *)
        echo "Usage: $0 [backend|frontend|database|llm|docker|all]"
        echo ""
        echo "Environment variables:"
        echo "  BACKEND_URL   - Backend URL (default: http://localhost:8000)"
        echo "  FRONTEND_URL  - Frontend URL (default: http://localhost:3000)"
        echo "  LLM_BASE_URL  - LLM service URL (default: http://localhost:1234/v1)"
        echo "  TIMEOUT       - Request timeout in seconds (default: 10)"
        exit 1
        ;;
esac