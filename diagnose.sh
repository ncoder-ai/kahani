#!/bin/bash
# ============================================================================
# KAHANI SYSTEM DIAGNOSTIC SCRIPT
# ============================================================================
# Use this script to view logs, check system status, and diagnose issues
# across all Kahani containers (backend, frontend, PostgreSQL)
#
# Usage:
#   ./diagnose.sh logs      - View live backend logs
#   ./diagnose.sh postgres  - View PostgreSQL logs
#   ./diagnose.sh frontend  - View frontend logs
#   ./diagnose.sh all       - View all container logs
#   ./diagnose.sh status    - Check container status
#   ./diagnose.sh delete    - Filter for delete-related logs
#   ./diagnose.sh connections - Show PostgreSQL active connections
#   ./diagnose.sh locks     - Show PostgreSQL lock status
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

case "$1" in
    logs|backend)
        echo -e "${GREEN}=== Backend Logs (Live) ===${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        docker logs -f --timestamps kahani-backend
        ;;
    
    postgres|db)
        echo -e "${GREEN}=== PostgreSQL Logs (Live) ===${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        docker logs -f --timestamps kahani-postgres
        ;;
    
    frontend)
        echo -e "${GREEN}=== Frontend Logs (Live) ===${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        docker logs -f --timestamps kahani-frontend
        ;;
    
    all)
        echo -e "${GREEN}=== All Container Logs (Last 50 lines each) ===${NC}"
        echo ""
        echo -e "${BLUE}--- Backend ---${NC}"
        docker logs --tail 50 kahani-backend 2>&1
        echo ""
        echo -e "${BLUE}--- PostgreSQL ---${NC}"
        docker logs --tail 50 kahani-postgres 2>&1
        echo ""
        echo -e "${BLUE}--- Frontend ---${NC}"
        docker logs --tail 50 kahani-frontend 2>&1
        ;;
    
    status)
        echo -e "${GREEN}=== Container Status ===${NC}"
        echo ""
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "kahani|NAMES"
        echo ""
        echo -e "${GREEN}=== Container Resource Usage ===${NC}"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -E "kahani|NAME"
        ;;
    
    delete)
        echo -e "${GREEN}=== Delete Operation Logs (Live Filter) ===${NC}"
        echo -e "${YELLOW}Filtering for: DELETE, SCENE:DELETE, CHAPTER:DELETE, DELETE-BG${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        docker logs -f kahani-backend 2>&1 | grep -E "DELETE|delete_scene|delete_chapter|CLEANUP"
        ;;
    
    recent)
        echo -e "${GREEN}=== Recent Delete Operations (Last 200 lines) ===${NC}"
        echo ""
        docker logs --tail 200 kahani-backend 2>&1 | grep -E "DELETE|CLEANUP|CHAPTER.*delete"
        ;;
    
    connections)
        echo -e "${GREEN}=== PostgreSQL Active Connections ===${NC}"
        echo ""
        docker exec kahani-postgres psql -U kahani -d kahani -c "SELECT pid, state, query_start, LEFT(query, 80) as query FROM pg_stat_activity WHERE datname = 'kahani' AND state != 'idle' ORDER BY query_start;"
        ;;
    
    locks)
        echo -e "${GREEN}=== PostgreSQL Lock Status ===${NC}"
        echo ""
        docker exec kahani-postgres psql -U kahani -d kahani -c "SELECT blocked_locks.pid AS blocked_pid, blocked_activity.usename AS blocked_user, blocking_locks.pid AS blocking_pid, blocking_activity.usename AS blocking_user, blocked_activity.query AS blocked_statement FROM pg_catalog.pg_locks blocked_locks JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype AND blocking_locks.DATABASE IS NOT DISTINCT FROM blocked_locks.DATABASE AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid AND blocking_locks.pid != blocked_locks.pid JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid WHERE NOT blocked_locks.GRANTED;"
        ;;
    
    *)
        echo -e "${GREEN}============================================================================${NC}"
        echo -e "${GREEN}KAHANI SYSTEM DIAGNOSTIC SCRIPT${NC}"
        echo -e "${GREEN}============================================================================${NC}"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo -e "  ${BLUE}logs${NC}        - View live backend logs"
        echo -e "  ${BLUE}postgres${NC}    - View live PostgreSQL logs"
        echo -e "  ${BLUE}frontend${NC}    - View live frontend logs"
        echo -e "  ${BLUE}all${NC}         - View last 50 lines from all containers"
        echo -e "  ${BLUE}status${NC}      - Check container status and resource usage"
        echo -e "  ${BLUE}delete${NC}      - Filter live logs for delete operations"
        echo -e "  ${BLUE}recent${NC}      - Show recent delete operations from logs"
        echo -e "  ${BLUE}connections${NC} - Show active PostgreSQL connections"
        echo -e "  ${BLUE}locks${NC}       - Show PostgreSQL lock status (for deadlock detection)"
        echo ""
        echo "Examples:"
        echo "  $0 logs        # Watch backend logs in real-time"
        echo "  $0 all         # View logs from all containers"
        echo "  $0 status      # Check container health"
        echo "  $0 delete      # Watch only delete-related logs"
        echo "  $0 locks       # Check for database deadlocks"
        echo ""
        ;;
esac
