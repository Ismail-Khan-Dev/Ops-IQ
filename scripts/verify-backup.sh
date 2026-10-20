#!/usr/bin/env bash
# ── OpsIQ Backup Verification ──────────────────────────────
# Tests that backups can actually be restored (not just created)
# Usage: ./scripts/verify-backup.sh [backup_file]
# If no file specified, uses latest backup in ./backups/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
CONTAINER_NAME="${POSTGRES_CONTAINER:-opsiq-postgres}"
DB_NAME="${POSTGRES_DB:-ecommerce_ops}"
DB_USER="${POSTGRES_USER:-postgres}"
TEST_DB="ecommerce_ops_verify_$$"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "[$(date +%H:%M:%S)] $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Find backup file ────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
    BACKUP_FILE="$1"
else
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/ecom_ops_*.sql.gz 2>/dev/null | head -1)
fi

[[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]] && fail "No backup file found"
log "Verifying backup: $BACKUP_FILE"

# ── Step 1: Check file integrity ────────────────────────────
log "[1/5] Checking file integrity..."
if gzip -t "$BACKUP_FILE" 2>/dev/null; then
    ok "Gzip integrity: PASS"
else
    fail "Gzip integrity: FAIL — backup is corrupted"
fi

FILE_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)
if [[ "$FILE_SIZE" -lt 100 ]]; then
    fail "Backup too small (${FILE_SIZE} bytes) — likely empty"
fi
ok "File size: $(numfmt --to=iec "$FILE_SIZE" 2>/dev/null || echo "${FILE_SIZE} bytes")"

# ── Step 2: Check SQL structure ─────────────────────────────
log "[2/5] Checking SQL structure..."
SQL_STRUCTURE=$(zcat "$BACKUP_FILE" 2>/dev/null | head -50)
if echo "$SQL_STRUCTURE" | grep -q "PostgreSQL database dump"; then
    ok "SQL header: valid PostgreSQL dump"
else
    warn "SQL header: not a standard pg_dump format (may still work)"
fi

TABLE_COUNT=$(zcat "$BACKUP_FILE" 2>/dev/null | grep -c "CREATE TABLE" || true)
if [[ "$TABLE_COUNT" -gt 0 ]]; then
    ok "Tables found: $TABLE_COUNT"
else
    warn "No CREATE TABLE found — backup may be empty"
fi

# ── Step 3: Test restore to temp database ───────────────────
log "[3/5] Restoring to test database: $TEST_DB..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $TEST_DB;" >/dev/null 2>&1
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE $TEST_DB;" >/dev/null 2>&1

if zcat "$BACKUP_FILE" 2>/dev/null | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" >/dev/null 2>&1; then
    ok "Restore: SUCCESS"
else
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $TEST_DB;" >/dev/null 2>&1
    fail "Restore: FAILED — backup cannot be restored"
fi

# ── Step 4: Verify restored data ────────────────────────────
log "[4/5] Verifying restored data..."
RESTORED_TABLES=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
ok "Restored tables: $RESTORED_TABLES"

# Check for expected tables
for table in pipeline_runs agent_decisions audit_logs; do
    EXISTS=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" -t -c \
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '$table');" 2>/dev/null | tr -d ' ')
    if [[ "$EXISTS" == "t" ]]; then
        COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" -t -c \
            "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' ')
        ok "  $table: $COUNT rows"
    else
        warn "  $table: MISSING"
    fi
done

# ── Step 5: Cleanup ─────────────────────────────────────────
log "[5/5] Cleaning up test database..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $TEST_DB;" >/dev/null 2>&1
ok "Test database dropped"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
ok "BACKUP VERIFICATION: PASSED"
echo "  File: $BACKUP_FILE"
echo "  Size: $(numfmt --to=iec "$FILE_SIZE" 2>/dev/null || echo "${FILE_SIZE} bytes")"
echo "  Tables: $TABLE_COUNT"
echo "  Restore: OK"
echo "═══════════════════════════════════════════════"
