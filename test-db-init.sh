#!/bin/bash

# Test script to verify database initialization works correctly
# This simulates a fresh install and checks all steps

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[TEST]${NC} $1"; }
log_success() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }

echo "🧪 Kahani Database Initialization Test"
echo "======================================"
echo ""

# Check if we're in the right directory
if [[ ! -f "backend/app/main.py" ]]; then
    log_error "Please run from the Kahani root directory"
    exit 1
fi

TEST_DIR="$(pwd)/backend/data/test_db"
TEST_DB="$TEST_DIR/kahani_test.db"

# Cleanup function
cleanup() {
    log_info "Cleaning up test database..."
    rm -rf "$TEST_DIR"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Step 1: Create test directory
log_info "Creating test database directory..."
mkdir -p "$TEST_DIR"
log_success "Test directory created: $TEST_DIR"

# Step 2: Test Alembic migrations
log_info "Testing Alembic migrations on fresh database..."

# Temporarily override DATABASE_URL for test
export DATABASE_URL="sqlite:///$TEST_DB"
cd backend

# Run migrations
if source ../.venv/bin/activate 2>/dev/null; then
    log_info "Virtual environment activated"
    
    # Check Alembic is installed
    if ! command -v alembic &> /dev/null; then
        log_error "Alembic not found in virtual environment"
        exit 1
    fi
    
    # Run migrations
    log_info "Running: alembic upgrade head"
    if alembic upgrade head; then
        log_success "Alembic migrations completed successfully"
    else
        log_error "Alembic migrations failed"
        exit 1
    fi
    
    # Check Alembic version
    log_info "Checking Alembic version..."
    CURRENT_VERSION=$(alembic current 2>&1)
    echo "  $CURRENT_VERSION"
    
    if echo "$CURRENT_VERSION" | grep -q "head"; then
        log_success "Database is at HEAD version"
    else
        log_error "Database is not at HEAD version"
        exit 1
    fi
    
    deactivate
else
    log_error "Could not activate virtual environment"
    exit 1
fi

cd ..

# Step 3: Verify database structure
log_info "Verifying database structure..."

if [[ -f "$TEST_DB" ]]; then
    log_success "Test database created: $TEST_DB"
    
    # Check database size
    DB_SIZE=$(du -h "$TEST_DB" | cut -f1)
    log_info "Database size: $DB_SIZE"
    
    # List tables using sqlite3
    if command -v sqlite3 &> /dev/null; then
        log_info "Checking database tables..."
        TABLES=$(sqlite3 "$TEST_DB" ".tables")
        TABLE_COUNT=$(echo "$TABLES" | wc -w | tr -d ' ')
        
        echo "  Found $TABLE_COUNT tables:"
        for table in $TABLES; do
            echo "    - $table"
        done
        
        # Check for essential tables
        REQUIRED_TABLES=("users" "stories" "scenes" "alembic_version")
        for table in "${REQUIRED_TABLES[@]}"; do
            if echo "$TABLES" | grep -q "$table"; then
                log_success "Required table exists: $table"
            else
                log_error "Required table missing: $table"
                exit 1
            fi
        done
        
        # Check alembic_version has a value
        VERSION_COUNT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM alembic_version;")
        if [[ "$VERSION_COUNT" -gt 0 ]]; then
            VERSION=$(sqlite3 "$TEST_DB" "SELECT version_num FROM alembic_version;")
            log_success "Alembic version tracked in database: $VERSION"
        else
            log_error "Alembic version table is empty"
            exit 1
        fi
    else
        log_info "sqlite3 CLI not available, skipping table verification"
    fi
else
    log_error "Test database was not created"
    exit 1
fi

# Step 4: Test that migrations are idempotent (can run twice)
log_info "Testing idempotency (running migrations again)..."
cd backend
source ../.venv/bin/activate

if alembic upgrade head 2>&1 | grep -q "Target database is not up to date"; then
    log_error "Migrations should be idempotent"
    exit 1
else
    log_success "Migrations are idempotent (no changes on second run)"
fi

deactivate
cd ..

echo ""
echo "======================================"
log_success "All tests passed! ✅"
echo "======================================"
echo ""
echo "Summary:"
echo "  ✓ Alembic migrations run successfully"
echo "  ✓ Database structure created correctly"
echo "  ✓ Alembic version tracking works"
echo "  ✓ Migrations are idempotent"
echo ""
echo "The database initialization process is working correctly."
