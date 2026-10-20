#!/usr/bin/env bash
# Automated PostgreSQL backup for OpsIQ
# Usage: ./scripts/backup-db.sh [output_dir]
# Offsite upload: set S3_BUCKET=gs://bucket-name or AWS_DEFAULT_REGION + S3_BUCKET
set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
BACKUP_FILE="${OUTPUT_DIR}/ecom_ops_${TIMESTAMP}.sql.gz"
CONTAINER_NAME="${POSTGRES_CONTAINER:-opsiq-postgres}"
DB_NAME="${POSTGRES_DB:-ecommerce_ops}"
DB_USER="${POSTGRES_USER:-postgres}"
S3_BUCKET="${S3_BUCKET:-}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

mkdir -p "$OUTPUT_DIR"

echo "[1/4] Dumping database..."
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "[2/4] Verifying backup..."
BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)
if [ "$BACKUP_SIZE" -lt 100 ]; then
  echo "[ERROR] Backup too small ($BACKUP_SIZE bytes), likely empty"
  rm -f "$BACKUP_FILE"
  exit 1
fi
echo "  Size: $(numfmt --to=iec "$BACKUP_FILE" 2>/dev/null || echo "${BACKUP_SIZE} bytes")"

echo "[3/4] Offsite upload..."
if [[ -n "$S3_BUCKET" ]]; then
  if command -v aws &>/dev/null; then
    aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/backups/ecom_ops_${TIMESTAMP}.sql.gz" \
      --storage-class STANDARD_IA \
      --only-show-errors && echo "  Uploaded to s3://${S3_BUCKET}" \
      || echo "[WARN] S3 upload failed — local backup preserved"
  elif command -v gsutil &>/dev/null; then
    gsutil -q cp "$BACKUP_FILE" "gs://${S3_BUCKET}/backups/ecom_ops_${TIMESTAMP}.sql.gz" \
      && echo "  Uploaded to gs://${S3_BUCKET}" \
      || echo "[WARN] GCS upload failed — local backup preserved"
  else
    echo "[WARN] Neither aws CLI nor gsutil found — skipping offsite upload"
  fi
else
  echo "  S3_BUCKET not set — skipping offsite upload"
fi

echo "[4/4] Cleaning old backups (keep ${RETENTION_DAYS} days)..."
find "$OUTPUT_DIR" -name "ecom_ops_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

echo ""
echo "[OK] Backup complete: $BACKUP_FILE"
ls -lh "$OUTPUT_DIR"/ecom_ops_*.sql.gz 2>/dev/null | tail -5
