#!/usr/bin/env bash
# CivicLens — automated disaster-recovery verification.
# Cron this (e.g. nightly after backup.sh). It:
#   1. takes a fresh backup (DB + media)
#   2. verifies pg_dump integrity (pg_restore --list)
#   3. restores into an ISOLATED database (never the live one)
#   4. compares row counts of critical tables against the live DB
#   5. verifies media archive integrity + spot-checks a stored file hash
# Exit code != 0 means the backup CANNOT be trusted -> alert.
#
# Required env: DATABASE_URL (live), DR_DATABASE_URL (isolated scratch db),
#               CL_STORAGE_DIR (local backend) or S3 vars.
set -euo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
OUT="${BACKUP_DIR:-./backups}/drcheck-$STAMP"
mkdir -p "$OUT"
fail() { echo "DR-VERIFY FAIL: $1" >&2; exit 1; }

echo "[1/5] backup"
pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" > "$OUT/db.dump" || fail "pg_dump failed"
if [ -d "${CL_STORAGE_DIR:-}" ]; then
  tar czf "$OUT/media.tar.gz" -C "$(dirname "$CL_STORAGE_DIR")" "$(basename "$CL_STORAGE_DIR")"
fi

echo "[2/5] dump integrity"
pg_restore --list "$OUT/db.dump" > /dev/null || fail "dump unreadable"

echo "[3/5] restore into isolated DB"
pg_restore --clean --if-exists --no-owner --dbname="$DR_DATABASE_URL" "$OUT/db.dump" \
  || fail "restore into isolated environment failed"

echo "[4/5] row-count comparison"
for table in reports users report_media audit_logs organizations; do
  live=$(psql "$DATABASE_URL" -tAc "SELECT count(*) FROM $table")
  restored=$(psql "$DR_DATABASE_URL" -tAc "SELECT count(*) FROM $table")
  [ "$live" = "$restored" ] || fail "row mismatch in $table: live=$live restored=$restored"
  echo "  $table: $live == $restored ✓"
done

echo "[5/5] media verification"
if [ -f "$OUT/media.tar.gz" ]; then
  tar tzf "$OUT/media.tar.gz" > /dev/null || fail "media archive corrupt"
  # spot-check: newest media row's sha256 must match the archived file
  ROW=$(psql "$DATABASE_URL" -tAc \
    "SELECT storage_key || '|' || coalesce(sha256,'') FROM report_media ORDER BY created_at DESC LIMIT 1")
  KEY="${ROW%%|*}"; SHA="${ROW##*|}"
  if [ -n "$SHA" ]; then
    TMP=$(mktemp -d)
    tar xzf "$OUT/media.tar.gz" -C "$TMP"
    FILE=$(find "$TMP" -path "*$KEY" | head -1)
    [ -n "$FILE" ] || fail "spot-check file missing from archive: $KEY"
    ACTUAL=$(sha256sum "$FILE" | cut -d' ' -f1)
    [ "$ACTUAL" = "$SHA" ] || fail "media hash mismatch for $KEY"
    rm -rf "$TMP"
    echo "  media spot-check: sha256 verified ✓"
  fi
fi

echo "DR-VERIFY OK: $OUT"
echo "RPO: age of this backup. RTO: measured restore took the [3/5] step duration."
