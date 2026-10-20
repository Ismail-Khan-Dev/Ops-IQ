#!/usr/bin/env bash
# ── Check for Alembic migration drift ──────────────────────
# Detects if SQLAlchemy models diverge from migration history
# Usage: bash scripts/check-migrations.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Checking for migration drift..."

cd "$PROJECT_DIR"

# Generate current model state as a migration (dry run)
ALEMBIC_OUTPUT=$(alembic revision --autogenerate -m "drift_check" 2>&1 || true)

if echo "$ALEMBIC_OUTPUT" | grep -q "No changes detected"; then
    echo "✓ No migration drift detected — models match migrations"
    # Clean up the generated migration file if any
    rm -f alembic/versions/*drift_check*.py
    exit 0
else
    echo "✗ Migration drift detected!"
    echo ""
    echo "The following changes would be generated:"
    echo "$ALEMBIC_OUTPUT"
    echo ""
    echo "To fix: run 'alembic revision --autogenerate -m \"description\"' and review"
    # Clean up the generated migration file
    rm -f alembic/versions/*drift_check*.py
    exit 1
fi
