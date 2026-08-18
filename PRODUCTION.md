# CivicLens Ethiopia — Production Checklist

Work through every item before going live.

## Secrets & configuration
- [ ] `CL_SECRET_KEY` set to a long random string (e.g. `openssl rand -hex 48`); never the dev default
- [ ] `CL_ENV=production` (enables Secure cookies + HSTS header)
- [ ] `POSTGRES_PASSWORD` strong and unique
- [ ] No secrets in images, git, or `.env.example`
- [ ] SMTP credentials only via environment (`CL_SMTP_*`), `CL_EMAIL_BACKEND=smtp`
- [ ] S3 credentials only via environment (`CL_S3_*`) if using object storage

## Infrastructure
- [ ] HTTPS terminated by a reverse proxy (Caddy/Nginx/Traefik) in front of the API container
- [ ] PostgreSQL with persistent volume + automated backups (`scripts/backup.sh` in cron)
- [ ] Redis running with `appendonly yes`; `CL_JOB_BACKEND=redis`
- [ ] At least one worker container running `python -m app.worker`
- [ ] AI service reachable from the API (`CL_AI_SERVICE_URL`); optionally Ollama with a vision model
- [ ] Storage volume (or S3 bucket) with restricted permissions — the web server must never serve it directly
- [ ] Restart policies on all containers (`restart: unless-stopped` in compose)

## Database
- [ ] `alembic upgrade head` run during deploy (compose api command does this)
- [ ] Migrations tested against a copy of production data before rollout
- [ ] `scripts/backup.sh` + `scripts/restore.sh` tested at least once (DB + media together)

## Application security
- [ ] Demo accounts removed or deactivated (`/api/admin/users` → deactivate; or skip `seed.py` entirely)
- [ ] Real admin created (see README "Create an admin account")
- [ ] CORS: production serves the SPA same-origin, so no CORS origins should be needed
- [ ] Rate limits reviewed (`CL_RATE_LIMIT_*`, `CL_LOGIN_MAX_FAILURES`)
- [ ] Session lifetime reviewed (`CL_SESSION_TTL_HOURS`)
- [ ] Upload limits reviewed (`CL_MAX_VIDEO_MB`, `CL_MAX_VIDEO_SECONDS`, `CL_MAX_ATTACHMENTS`)
- [ ] Coordinate privacy reviewed (`CL_PUBLIC_COORD_DECIMALS`, `CL_SENSITIVE_CATEGORIES`)

## Monitoring
- [ ] `/api/health` (liveness) and `/api/ready` (DB/AI/Redis checks) wired into your monitor
- [ ] Log aggregation for API + worker (structured logs include request IDs)
- [ ] Alert on: readiness failures, dead jobs (`/api/admin/jobs?status=dead`), disk usage of storage volume

## Verification after deploy
- [ ] Register a test citizen, submit a report with video, watch it route to an organization
- [ ] Confirm org staff can only see their own organization's reports
- [ ] Confirm `/docs` matches reality and admin dashboards show real data
- [ ] Kill the worker mid-job and confirm the job recovers (stuck-job requeue on worker restart)
