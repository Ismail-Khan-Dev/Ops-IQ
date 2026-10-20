#!/usr/bin/env bash
# ── OpsIQ Disaster Recovery Runbook ─────────────────────────
# Automated DR checklist — validates system health after recovery
# Usage: ./scripts/disaster-recovery.sh [check|full|report]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="docker-compose.yml"
CONTAINER_NAME="${POSTGRES_CONTAINER:-opsiq-postgres}"
DB_NAME="${POSTGRES_DB:-ecommerce_ops}"
DB_USER="${POSTGRES_USER:-postgres}"
ACTION="${1:-check}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; PASS=$((PASS + 1)); }
warn() { echo -e "${YELLOW}[!]${NC} $*"; WARN=$((WARN + 1)); }
fail() { echo -e "${RED}[✗]${NC} $*"; FAIL=$((FAIL + 1)); }

# ── Check 1: Docker services ───────────────────────────────
check_services() {
    log "Checking Docker services..."
    cd "$PROJECT_DIR"

    local services=("postgres" "redis" "api" "nginx" "prometheus" "grafana")
    for svc in "${services[@]}"; do
        local status
        status=$(docker compose -f "$COMPOSE_FILE" ps --format '{{.State}}' "$svc" 2>/dev/null || echo "missing")
        if [[ "$status" == "running" ]]; then
            ok "  $svc: running"
        elif [[ "$status" == "exited" ]]; then
            fail "  $svc: exited"
        else
            warn "  $svc: $status"
        fi
    done
}

# ── Check 2: Database connectivity ──────────────────────────
check_database() {
    log "Checking database..."
    if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" >/dev/null 2>&1; then
        ok "  PostgreSQL: accepting connections"
    else
        fail "  PostgreSQL: not accepting connections"
    fi

    local tables
    tables=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
    if [[ "$tables" -gt 0 ]]; then
        ok "  Tables: $tables"
    else
        fail "  Tables: 0 (database may be empty)"
    fi

    # Check for data integrity
    for table in pipeline_runs agent_decisions audit_logs; do
        local exists
        exists=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '$table');" 2>/dev/null | tr -d ' ')
        if [[ "$exists" == "t" ]]; then
            ok "  $table: exists"
        else
            warn "  $table: missing"
        fi
    done
}

# ── Check 3: API health ─────────────────────────────────────
check_api() {
    log "Checking API health..."

    local health
    health=$(curl -sf http://localhost:8000/health 2>/dev/null || echo '{"status":"unreachable"}')
    if echo "$health" | grep -q '"status":"ok"'; then
        ok "  API health: OK"
    else
        fail "  API health: UNHEALTHY"
    fi

    # Check API responds to authenticated request
    local auth_response
    auth_response=$(curl -sf -w "\n%{http_code}" -o /tmp/api_body \
        http://localhost:8000/api/v1/agents \
        -H "X-API-Key: ${API_KEY:?Set API_KEY environment variable}" 2>/dev/null | tail -1 || echo "000")
    if [[ "$auth_response" == "200" ]]; then
        ok "  API auth: working"
    elif [[ "$auth_response" == "000" ]]; then
        warn "  API auth: connection failed"
    else
        warn "  API auth: returned HTTP $auth_response"
    fi
}

# ── Check 4: Redis connectivity ─────────────────────────────
check_redis() {
    log "Checking Redis..."
    if docker exec opsiq-redis redis-cli ping 2>/dev/null | grep -q PONG; then
        ok "  Redis: responding"
    else
        fail "  Redis: not responding"
    fi
}

# ── Check 5: Monitoring stack ───────────────────────────────
check_monitoring() {
    log "Checking monitoring stack..."

    if curl -sf http://localhost:9093/-/healthy >/dev/null 2>&1; then
        ok "  Prometheus: healthy"
    else
        warn "  Prometheus: unhealthy or unreachable"
    fi

    if curl -sf http://localhost:3003/api/health >/dev/null 2>&1; then
        ok "  Grafana: healthy"
    else
        warn "  Grafana: unhealthy or unreachable"
    fi
}

# ── Check 6: Disk space ─────────────────────────────────────
check_disk() {
    log "Checking disk usage..."
    local usage
    usage=$(df -h / 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")
    # Handle non-numeric output (Windows Git Bash)
    if [[ "$usage" =~ ^[0-9]+$ ]]; then
        if [[ "$usage" -lt 80 ]]; then
            ok "  Disk usage: ${usage}%"
        elif [[ "$usage" -lt 90 ]]; then
            warn "  Disk usage: ${usage}% (high)"
        else
            fail "  Disk usage: ${usage}% (critical)"
        fi
    else
        warn "  Disk usage: unable to determine on this platform"
    fi
}

# ── Check 7: Backup availability ────────────────────────────
check_backups() {
    log "Checking backup availability..."
    local backup_count
    backup_count=$(ls "$PROJECT_DIR/backups"/ecom_ops_*.sql.gz 2>/dev/null | wc -l)

    if [[ "$backup_count" -gt 0 ]]; then
        local latest
        latest=$(ls -t "$PROJECT_DIR/backups"/ecom_ops_*.sql.gz 2>/dev/null | head -1)
        local age
        age=$(( ($(date +%s) - $(stat -f%m "$latest" 2>/dev/null || stat -c %Y "$latest" 2>/dev/null)) / 3600 ))
        ok "  Backups available: $backup_count (latest: ${age}h ago)"

        if [[ "$age" -gt 24 ]]; then
            warn "  Latest backup is over 24 hours old"
        fi
    else
        warn "  No backups found"
    fi
}

# ── Report ──────────────────────────────────────────────────
generate_report() {
    echo ""
    echo "═══════════════════════════════════════════════"
    echo "  OpsIQ Disaster Recovery Report"
    echo "  Generated: $(date)"
    echo "═══════════════════════════════════════════════"
    echo ""
    echo -e "  ${GREEN}Passed: $PASS${NC}"
    echo -e "  ${YELLOW}Warnings: $WARN${NC}"
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo ""

    if [[ $FAIL -eq 0 ]]; then
        echo -e "  ${GREEN}DR STATUS: OPERATIONAL${NC}"
    elif [[ $FAIL -le 2 ]]; then
        echo -e "  ${YELLOW}DR STATUS: DEGRADED${NC}"
    else
        echo -e "  ${RED}DR STATUS: CRITICAL${NC}"
    fi
    echo "═══════════════════════════════════════════════"

    # Write JSON report
    local report_file="$PROJECT_DIR/backups/dr_report_$(date +%Y%m%d_%H%M%S).json"
    cat > "$report_file" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "passed": $PASS,
  "warnings": $WARN,
  "failed": $FAIL,
  "status": "$([ $FAIL -eq 0 ] && echo "operational" || ([ $FAIL -le 2 ] && echo "degraded" || echo "critical"))"
}
EOF
    log "Report saved: $report_file"
}

# ── Main ────────────────────────────────────────────────────
case "$ACTION" in
    check)
        echo "OpsIQ DR Check — $(date)"
        echo "─────────────────────────────────────"
        check_services
        check_database
        check_api
        check_redis
        check_monitoring
        check_disk
        check_backups
        generate_report
        ;;
    full)
        echo "OpsIQ DR Full Recovery Check — $(date)"
        echo "─────────────────────────────────────"
        check_services
        check_database
        check_redis
        check_api
        check_monitoring
        check_disk
        check_backups
        generate_report
        ;;
    report)
        check_services
        check_database
        check_api
        check_redis
        check_monitoring
        check_disk
        check_backups
        generate_report
        ;;
    *)
        echo "Usage: $0 {check|full|report}"
        echo "  check  — Quick health check"
        echo "  full   — Full recovery verification"
        echo "  report — Generate JSON report"
        exit 1
        ;;
esac
