#!/usr/bin/env bash
# CivicLens Ethiopia — restore database + media from a backup directory.
# Usage: scripts/restore.sh backups/20260817-120000
set -euo pipefail
SRC="${1:?usage: restore.sh <backup-dir>}"

echo "!! This will REPLACE the current database and media. Ctrl-C to abort."
sleep 5

if [ -n "${DATABASE_URL:-}" ]; then
  pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" "$SRC/db.dump"
else
  pg_restore --clean --if-exists --no-owner --dbname="${PGDATABASE:-civiclens}" "$SRC/db.dump"
fi
echo "database restored"

STORAGE_DIR="${CL_STORAGE_DIR:-./backend/storage}"
if [ -f "$SRC/media.tar.gz" ]; then
  rm -rf "$STORAGE_DIR"
  tar xzf "$SRC/media.tar.gz" -C "$(dirname "$STORAGE_DIR")"
  echo "media restored"
fi
echo "Restore complete. Restart API + worker."
