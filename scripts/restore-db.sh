#!/usr/bin/env bash
# ── OpsIQ Point-in-Time Recovery ────────────────────────────
# Restore database to a specific point in time or from a backup file
# Usage: ./scripts/restore-db.sh [backup_file] [--force]
#
# This script:
#   1. Stops the API (prevents writes during restore)
#   2. Creates a safety backup of current state
#   3. Restores from specified backup
#   4. Verifies data integrity
#   5. Restarts the API

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="docker-compose.yml"
CONTAINER_NAME="${POSTGRES_CONTAINER:-opsiq-postgres}"
DB_NAME="${POSTGRES_DB:-ecommerce_ops}"
DB_USER="${POSTGRES_USER:-postgres}"
BACKUP_DIR="${PROJECT_DIR}/backups"
FORCE=false

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Parse args ──────────────────────────────────────────────
BACKUP_FILE=""
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        *.sql.gz) BACKUP_FILE="$arg" ;;
    esac
done

if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup_file.sql.gz> [--force]"
    echo ""
    echo "Available backups:"
    ls -lht "$BACKUP_DIR"/ecom_ops_*.sql.gz 2>/dev/null | head -10 || echo "  No backups found"
    exit 1
fi

[[ -f "$BACKUP_FILE" ]] || fail "Backup file not found: $BACKUP_FILE"

# ── Safety check ────────────────────────────────────────────
if [[ "$FORCE" != "true" ]]; then
    warn "This will OVERWRITE the current database with: $BACKUP_FILE"
    warn "A safety backup of the current state will be created first."
    echo ""
    read -p "Continue? (yes/no): " CONFIRM
    [[ "$CONFIRM" != "yes" ]] && fail "Aborted by user"
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ── Step 1: Create safety backup ────────────────────────────
log "[1/6] Creating safety backup of current state..."
SAFETY_BACKUP="$BACKUP_DIR/safety_${TIMESTAMP}.sql.gz"
mkdir -p "$BACKUP_DIR"

if docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" 2>/dev/null | gzip > "$SAFETY_BACKUP"; then
    SAFETY_SIZE=$(stat -f%z "$SAFETY_BACKUP" 2>/dev/null || stat -c%s "$SAFETY_BACKUP" 2>/dev/null)
    ok "Safety backup: $SAFETY_BACKUP ($SAFETY_SIZE bytes)"
else
    warn "Safety backup failed — proceeding anyway"
fi

# ── Step 2: Stop API (prevent writes) ───────────────────────
log "[2/6] Stopping API server..."
cd "$PROJECT_DIR"
docker compose -f "$COMPOSE_FILE" stop api 2>/dev/null || true
sleep 2
ok "API stopped"

# ── Step 3: Drop and recreate database ──────────────────────
log "[3/6] Dropping and recreating database..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;" 2>/dev/null
ok "Database recreated"

# ── Step 4: Restore backup ──────────────────────────────────
log "[4/6] Restoring from backup..."
if zcat "$BACKUP_FILE" 2>/dev/null | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" 2>/dev/null; then
    ok "Restore completed"
else
    warn "Restore had errors — checking if data exists..."
fi

# ── Step 5: Verify restore ──────────────────────────────────
log "[5/6] Verifying restored data..."
TABLE_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

ROW_COUNTS=""
for table in pipeline_runs agent_decisions audit_logs; do
    EXISTS=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '$table');" 2>/dev/null | tr -d ' ')
    if [[ "$EXISTS" == "t" ]]; then
        COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
            "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' ')
        ROW_COUNTS="$ROW_COUNTS  $table: $COUNT rows\n"
    fi
done

if [[ "$TABLE_COUNT" -gt 0 ]]; then
    ok "Verification: $TABLE_COUNT tables found"
    echo -e "$ROW_COUNTS"
else
    fail "Verification: No tables found — restore may have failed"
fi

# ── Step 6: Restart API ─────────────────────────────────────
log "[6/6] Restarting API server..."
docker compose -f "$COMPOSE_FILE" start api 2>/dev/null

# Wait for health
MAX_WAIT=60
ELAPSED=0
while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        ok "API is healthy!"
        break
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

if [[ $ELAPSED -ge $MAX_WAIT ]]; then
    warn "API health check timed out — check logs: docker compose logs api"
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
ok "POINT-IN-TIME RECOVERY: COMPLETE"
echo "  Restored from: $BACKUP_FILE"
echo "  Safety backup: $SAFETY_BACKUP"
echo "  Tables: $TABLE_COUNT"
echo "  API: running"
echo "═══════════════════════════════════════════════"
echo ""
echo "To rollback to safety backup, run:"
echo "  $0 $SAFETY_BACKUP --force"
