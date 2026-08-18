#!/usr/bin/env bash
# CivicLens Ethiopia — consistent backup of database + media.
# IMPORTANT: database and media MUST be backed up together; report_media rows
# reference storage keys, so restoring one without the other breaks evidence links.
set -euo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
OUT="${BACKUP_DIR:-./backups}/$STAMP"
mkdir -p "$OUT"

# --- PostgreSQL (set PGHOST/PGUSER/PGPASSWORD/PGDATABASE or DATABASE_URL) ---
if [ -n "${DATABASE_URL:-}" ]; then
  pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" > "$OUT/db.dump"
else
  pg_dump --format=custom --no-owner "${PGDATABASE:-civiclens}" > "$OUT/db.dump"
fi
echo "database -> $OUT/db.dump"

# --- media (local storage backend; for S3 use bucket versioning/replication) ---
STORAGE_DIR="${CL_STORAGE_DIR:-./backend/storage}"
if [ -d "$STORAGE_DIR" ]; then
  tar czf "$OUT/media.tar.gz" -C "$(dirname "$STORAGE_DIR")" "$(basename "$STORAGE_DIR")"
  echo "media    -> $OUT/media.tar.gz"
fi

echo "Backup complete: $OUT"
