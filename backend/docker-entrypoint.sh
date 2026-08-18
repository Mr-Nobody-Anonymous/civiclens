#!/bin/sh
# CivicLens Ethiopia — container entrypoint (API image, also used by worker).
#
#   docker run image            -> api    (migrate + seed + serve on $PORT)
#   docker run image worker     -> redis job worker (CL_JOB_BACKEND=redis)
#   docker run image migrate    -> run migrations only, then exit
#   docker run image <anything> -> exec verbatim (escape hatch)
#
# Portable across any Docker host and PaaS (Render/Railway/Fly/Heroku-style):
# honors the platform-injected $PORT, defaults to 8000.
set -e

ROLE="${1:-api}"

# --- production safety defaults -------------------------------------------
# seed.py refuses to run in production unless demo data is EXPLICITLY off.
# For one-click platform deploys, default the flags off when CL_ENV=production
# (an operator can still opt in explicitly for a staging environment).
if [ "${CL_ENV:-development}" = "production" ]; then
  export CL_SEED_DEMO_DATA="${CL_SEED_DEMO_DATA:-false}"
  export CL_CREATE_DEMO_ACCOUNTS="${CL_CREATE_DEMO_ACCOUNTS:-false}"
fi

run_migrations() {
  echo "[entrypoint] applying database migrations..."
  python -m alembic upgrade head
}

bootstrap() {
  run_migrations
  echo "[entrypoint] seeding base data (organizations + routing rules)..."
  python seed.py
  # Optional non-interactive first admin (idempotent: promotes if it exists).
  # Set CL_ADMIN_EMAIL + CL_ADMIN_PASSWORD (+ optional CL_ADMIN_NAME) once,
  # then remove them from the environment.
  if [ -n "${CL_ADMIN_EMAIL}" ] && [ -n "${CL_ADMIN_PASSWORD}" ]; then
    echo "[entrypoint] ensuring admin account ${CL_ADMIN_EMAIL} exists..."
    python create_admin.py "${CL_ADMIN_EMAIL}" "${CL_ADMIN_NAME:-Administrator}" || true
  fi
}

case "$ROLE" in
  api)
    bootstrap
    echo "[entrypoint] starting API on 0.0.0.0:${PORT:-8000}"
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-1}" --proxy-headers --forwarded-allow-ips "*"
    ;;
  worker)
    echo "[entrypoint] starting job worker (queue: redis)"
    exec python -m app.worker
    ;;
  migrate)
    run_migrations
    ;;
  *)
    exec "$@"
    ;;
esac
