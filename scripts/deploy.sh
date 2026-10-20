#!/usr/bin/env bash
# ── OpsIQ Production Deploy ────────────────────────────────
# One-command production deployment
# Usage: ./scripts/deploy.sh [action]
#   action: up (default), rolling, down, restart, logs, status, backup, rollback

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="docker-compose.yml"
BACKUP_FILE="docker-compose.backup.yml"
ACTION="${1:-up}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/ready}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Pre-flight Checks ──────────────────────────────────────
preflight() {
    log "Running pre-flight checks..."

    command -v docker >/dev/null 2>&1 || fail "Docker not installed"
    docker info >/dev/null 2>&1 || fail "Docker daemon not running"

    for f in "$PROJECT_DIR/docker-compose.yml" "$PROJECT_DIR/.env.docker"; do
        [[ -f "$f" ]] || fail "Missing required file: $f"
    done

    # Grafana admin password must be explicitly set — never defaulted (see .env.production).
    grafana_pw=""
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        grafana_pw="$(grep -E '^GRAFANA_ADMIN_PASSWORD=' "$PROJECT_DIR/.env" | head -1 | cut -d= -f2-)"
    fi
    if [[ -z "$grafana_pw" ]]; then
        warn "GRAFANA_ADMIN_PASSWORD is not set — Grafana will be inaccessible."
        warn "Add GRAFANA_ADMIN_PASSWORD=... to .env (see .env.production) and redeploy."
    elif [[ "$grafana_pw" == "CHANGE_ME_GRAFANA_PASSWORD" ]]; then
        fail "GRAFANA_ADMIN_PASSWORD still set to the placeholder value in .env"
    fi

    if [[ ! -f "$PROJECT_DIR/nginx/certs/server.crt" ]] || [[ ! -f "$PROJECT_DIR/nginx/certs/server.key" ]]; then
        fail "TLS certificates not found — nginx refuses to start without TLS."
        fail "Run: bash scripts/generate-tls-certs.sh (or mount real certs into nginx/certs/)"
    fi

    if [[ ! -f "$PROJECT_DIR/$BACKUP_FILE" ]]; then
        warn "Backup compose not found — skipping backup services"
        BACKUP_FILE=""
    fi

    ok "Pre-flight checks passed"
}

# ── Wait for Healthy ───────────────────────────────────────
wait_for_healthy() {
    local max_wait="${1:-$HEALTH_TIMEOUT}"
    local elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        log "  Waiting... (${elapsed}s/${max_wait}s)"
    done
    return 1
}

# ── Get current image tag ──────────────────────────────────
get_current_image() {
    docker inspect opsiq-api --format '{{.Config.Image}}' 2>/dev/null || echo ""
}

# ── Full Deploy (with downtime) ────────────────────────────
deploy_up() {
    preflight

    log "Starting OpsIQ production stack (full deploy)..."

    COMPOSE_CMD="docker compose -f $COMPOSE_FILE"
    [[ -n "${BACKUP_FILE:-}" && -f "$PROJECT_DIR/$BACKUP_FILE" ]] && \
        COMPOSE_CMD="$COMPOSE_CMD -f $BACKUP_FILE"

    cd "$PROJECT_DIR"

    log "Pulling latest images..."
    $COMPOSE_CMD pull --quiet 2>/dev/null || true

    log "Building API image..."
    $COMPOSE_CMD build api --quiet

    log "Stopping existing services..."
    $COMPOSE_CMD down --timeout 30 2>/dev/null || true

    log "Starting services..."
    $COMPOSE_CMD up -d --remove-orphans --force-recreate

    log "Waiting for services to become healthy..."
    if wait_for_healthy; then
        ok "API is healthy!"
    else
        warn "API health check timed out after ${HEALTH_TIMEOUT}s"
        warn "Check logs: docker compose logs api"
    fi

    deploy_status
}

# ── Rolling Deploy (zero-downtime) ─────────────────────────
deploy_rolling() {
    preflight
    cd "$PROJECT_DIR"

    local old_image
    old_image=$(get_current_image)
    log "Current image: ${old_image:-none}"

    log "Building new API image..."
    docker compose -f "$COMPOSE_FILE" build api --quiet

    local new_image
    new_image=$(docker compose -f "$COMPOSE_FILE" images api --format json 2>/dev/null \
        | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('Repository','') + ':' + json.load(sys.stdin).get('Tag',''))" 2>/dev/null || echo "")

    log "New image: ${new_image:-built}"

    log "Rolling API service (graceful restart)..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --build api

    log "Waiting for new API to become healthy..."
    if wait_for_healthy; then
        ok "Rolling deploy succeeded — API is healthy"
    else
        warn "New API failed health check — initiating rollback"
        deploy_rollback_internal
        return 1
    fi

    deploy_status
}

# ── Rollback ───────────────────────────────────────────────
deploy_rollback_internal() {
    cd "$PROJECT_DIR"

    if [[ -n "${old_image:-}" ]]; then
        log "Rolling back to previous image..."
        IMAGE_TAG="${old_image}" docker compose -f "$COMPOSE_FILE" up -d --no-deps api
        if wait_for_healthy 60; then
            ok "Rollback succeeded"
        else
            fail "Rollback also failed — manual intervention required"
        fi
    else
        warn "No previous image recorded — cannot auto-rollback"
    fi
}

deploy_rollback() {
    preflight
    deploy_rollback_internal
}

# ── Status ──────────────────────────────────────────────────
deploy_status() {
    cd "$PROJECT_DIR"
    log "Service status:"
    docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    echo ""
    log "Health check:"
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        ok "API: healthy"
    else
        warn "API: unhealthy or unreachable"
    fi

    if curl -sf http://localhost:9093/-/healthy >/dev/null 2>&1; then
        ok "Prometheus: healthy"
    else
        warn "Prometheus: unhealthy or unreachable"
    fi
}

# ── Logs ────────────────────────────────────────────────────
deploy_logs() {
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=100 "${@:2}"
}

# ── Backup ──────────────────────────────────────────────────
deploy_backup() {
    cd "$PROJECT_DIR"
    local backup_dir="$PROJECT_DIR/backups/$TIMESTAMP"
    mkdir -p "$backup_dir"

    log "Creating database backup..."
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        pg_dump -U postgres ecommerce_ops | gzip > "$backup_dir/postgres.sql.gz"

    log "Creating Redis backup..."
    docker compose -f "$COMPOSE_FILE" exec -T redis \
        redis-cli BGSAVE >/dev/null 2>&1 || true
    sleep 2
    docker compose -f "$COMPOSE_FILE" exec -T redis \
        redis-cli LASTSAVE > "$backup_dir/redis_lastsave.txt" 2>/dev/null || true

    log "Backing up configuration..."
    cp "$PROJECT_DIR/.env.docker" "$backup_dir/"
    cp "$PROJECT_DIR/docker-compose.yml" "$backup_dir/"
    cp -r "$PROJECT_DIR/monitoring" "$backup_dir/" 2>/dev/null || true

    ok "Backup created: $backup_dir"
    ls -la "$backup_dir"
}

# ── Main ────────────────────────────────────────────────────
case "$ACTION" in
    up|deploy)    deploy_up ;;
    rolling)      deploy_rolling ;;
    rollback)     deploy_rollback ;;
    down|stop)
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" down --timeout 30
        ok "Stack stopped"
        ;;
    restart)
        cd "$PROJECT_DIR"
        docker compose -f "$COMPOSE_FILE" restart
        ok "Stack restarted"
        ;;
    status)       deploy_status ;;
    logs)         deploy_logs "$@" ;;
    backup)       deploy_backup ;;
    *)
        echo "Usage: $0 {up|rolling|rollback|down|restart|status|logs|backup}"
        exit 1
        ;;
esac
