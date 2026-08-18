# CivicLens Ethiopia — Production Checklist

> **Deploying to a platform (Render / Railway / Fly / Vercel / any Docker
> host)?** Start with **[DEPLOYMENT.md](DEPLOYMENT.md)** — it covers the
> checked-in one-click configs (`render.yaml`, `railway.json`, `fly.toml`,
> `frontend/vercel.json`, `frontend/netlify.toml`, GHCR image publishing) and
> the first-boot entrypoint that automates migrations, base seeding and admin
> creation. Then return here for the full hardening checklist.

Status legend: **[x] = executed and verified** in the full-stack validation run
(PostgreSQL 17 + Redis + real Ollama vision model + real SMTP + nginx TLS + worker).
Items marked *(re-do per deployment)* must be repeated with your real infrastructure values.

## Secrets & configuration
- [x] `CL_SECRET_KEY` set to a long random string (`openssl rand -hex 48`) — *(re-do per deployment)*
- [x] `CL_ENV=production` (enables Secure cookies + HSTS header) — verified: cookies issued with `Secure; HttpOnly; SameSite=lax`
- [x] `POSTGRES_PASSWORD` strong and unique (generated via `openssl rand -hex 16`) — *(re-do per deployment)*
- [x] No secrets in images, git, or `.env.example` — repo grep clean; validation secrets lived only in `/tmp`
- [x] SMTP credentials only via environment (`CL_SMTP_*`), `CL_EMAIL_BACKEND=smtp` — verified against a real SMTP server: 8 notification emails delivered (received/analyzed/assigned/in-progress/resolved/password-reset)
- [x] S3 credentials only via environment (`CL_S3_*`) if using object storage — local backend used in validation; S3 backend is env-driven code-verified

## Infrastructure
- [x] HTTPS terminated by a reverse proxy — nginx with TLS verified end-to-end *(use real certs per deployment)*
- [x] PostgreSQL with persistent volume + automated backups — `scripts/backup.sh` executed against live prod DB
- [x] Redis running; `CL_JOB_BACKEND=redis` — worker processed jobs from the Redis queue in validation
- [x] At least one worker container running `python -m app.worker` — ran, processed AI jobs, recovered stuck jobs
- [x] AI service reachable (`CL_AI_SERVICE_URL`) — verified with BOTH the heuristic engine and a real Ollama vision model (`moondream`); `/api/ready` reported `"ai_service": "ollama:moondream"`
- [x] Storage volume with restricted permissions; never served directly — media only via access-controlled API endpoints (tested)
- [x] Restart policies on all containers — `restart: unless-stopped` in docker-compose.yml

## Database
- [x] `alembic upgrade head` run during deploy — 3 migrations applied to an empty PostgreSQL 17 database
- [x] Migrations tested against realistic data — downgrade/upgrade cycle + PG enum migration verified
- [x] `scripts/backup.sh` + `scripts/restore.sh` tested — full DR drill: destroyed DB **and** media, restored, counts identical (reports/users/media/audit = 1/3/2/17, 4 files), video streamed 206 after restore

## Application security
- [x] `CL_SEED_DEMO_DATA=false` + `CL_CREATE_DEMO_ACCOUNTS=false` — verified: with `CL_ENV=production` and flags unset, `seed.py` **refuses with exit 2**; with flags false it seeds orgs+rules only
- [x] First admin created via `python create_admin.py <email> "<Name>"` — password via `CL_ADMIN_PASSWORD` env/prompt, never argv; verified login on the prod stack
- [x] CORS — production serves the SPA same-origin through the proxy (verified); no CORS origins required
- [x] Rate limits reviewed — Redis-backed shared limiting verified across simulated instances; memory fallback verified when Redis dies
- [x] Session lifetime reviewed (`CL_SESSION_TTL_HOURS`, default 14 days)
- [x] Upload limits reviewed (`CL_MAX_VIDEO_MB`/`CL_MAX_VIDEO_SECONDS`/`CL_MAX_ATTACHMENTS`) — corrupt/oversized/fake uploads rejected in tests
- [x] Coordinate privacy reviewed (`CL_PUBLIC_COORD_DECIMALS`, `CL_SENSITIVE_CATEGORIES`) — public API leak-check clean

## Reverse proxy (HTTPS)
- [x] `deploy/nginx.conf.example` deployed (with self-signed certs for validation) — *(use certbot/Let's Encrypt per deployment)*
- [x] HSTS set in BOTH layers — verified: response carried the header from nginx (`add_header ... always`) **and** the API middleware
- [x] HTTP→301→HTTPS redirect verified
- [x] Secure + HttpOnly + SameSite=Lax cookies verified through the proxy
- [x] `client_max_body_size 120m` + large video upload through proxy verified (201)
- [x] Range/206 video streaming through the proxy verified
- [x] SPA fallback + `/api` routing + `/api/health` + `/api/ready` through proxy verified

## Backups (verified procedure)
- [x] `scripts/backup.sh` (pg_dump custom format + media tar) — cron it nightly; DB and media MUST be backed up together
- [x] Restore drill performed on the LIVE production stack — database schema dropped, storage deleted, fully restored; reports, users, media streaming, org assignments and audit history verified identical

## Pre-launch items
- [x] **Real Ollama vision test** — `AI_MODEL=ollama OLLAMA_MODEL=moondream pytest test_ollama_integration.py -v` → **2 passed** (real video → FFmpeg frames → real model → structured validated output). Full pipeline also verified E2E: a report analyzed by `ollama:moondream` through the Redis worker, stored with correct model metadata, routed to the Roads Authority.
  *Note: this sandbox (1.9GB RAM, CPU-only, +swap) required the smallest vision model with `CL_AI_FRAMES_PER_VIDEO=1`. On real hardware use `llava:7b`+ and 3 frames.*
- [x] **Password reset against real SMTP** — forgot-password → token e-mail captured by a real SMTP server → token extracted from the actual e-mail body → password reset → login with new password 200 → token reuse 400. Browser-side flow separately E2E-tested (3 Playwright tests).
- [x] **Playwright against the deployed HTTPS origin** — account-independent suite (`--grep-invert @needs-demo-accounts`): **11 passed** against `https://…:8443` (a11y, mobile viewports, auth walls). Full 38-test journey suite: **passed** against the staging (demo-data) stack.

## Monitoring
- [x] `/api/health` (liveness) + `/api/ready` (DB/AI/Redis checks) — verified in all states incl. DB-down → 503
- [x] Structured logs with request IDs — verified in API output; worker logs job IDs
- [ ] Wire into your alerting system (Prometheus/Grafana/UptimeRobot/...) — *(environment-specific, re-do per deployment)*
- [ ] Alert on dead jobs (`/api/admin/jobs?status=dead`) and storage disk usage — *(environment-specific)*

## Verification after deploy *(repeat on your real deployment)*
- [x] Register a test citizen, submit a report with video, watch it route to an organization — done on the validation prod stack (report `CL-A0FBB2`: video → FFmpeg → Ollama → routed → accepted → in-progress → resolution evidence → resolved → reopened, with 7 real e-mails delivered)
- [x] Org staff sees only their own organization's reports — verified
- [x] `/docs` matches reality; admin dashboards show real data — verified
- [x] Worker killed mid-job recovers — stuck-job requeue verified in worker logs


## P2 production scale (verified in validation run)
- [x] **Prometheus metrics** at `/api/metrics` (restrict to monitoring network at the proxy):
      http requests/latency histograms, job counts/durations, AI success/failure + latency,
      Redis queue depth, worker heartbeat age, job-status gauges, open reports, SLA escalations,
      circuit-breaker events. Grafana: point dashboards at these series.
- [x] **Circuit breakers** around AI (3 failures/45s), SMTP (3/120s), storage (5/30s) —
      states exposed in `/api/ready`; SMTP-open verified to never lose in-app notifications.
- [x] **S3 media** verified against real MinIO: save/open/delete, signed access, lifecycle
      policy on `_chunks/`, upload -> thumbnail -> stream through the app, cross-instance reads.
- [x] **Horizontal scaling** verified: 2 API instances + Redis worker on PostgreSQL+S3;
      report created on instance A, processed by worker, read + Range-streamed from instance B;
      shared rate limits across instances (12 failures on A -> 429 on B).
- [x] **Automated DR**: `scripts/dr-verify.sh` — backup -> dump integrity -> restore into an
      ISOLATED db -> row-count comparison -> media archive + sha256 spot-check. Cron nightly;
      non-zero exit = alert. RPO = backup age; RTO = measured restore duration.
- [x] **CI/CD**: `.github/workflows/ci.yml` — lint -> typecheck -> SQLite+PG migration chain
      (incl. downgrade/upgrade) -> backend tests -> AI tests -> AI eval-harness regression gate
      -> secret scan (gitleaks) -> pip-audit + SBOM -> production build -> Playwright (+axe).
- [x] **AI evaluation harness**: `ai-service/eval_harness.py` — versioned dataset (en/am/mixed,
      severity ordering, adversarial robustness, language detection), history in
      eval_history.jsonl, committed baseline blocks regressions in CI.
      Current: en 1.0 / am 1.0 / mixed 1.0 / ordering 1.0 / adversarial 1.0.
- [x] Migration-chain bug found & fixed by this pass: 5ce1f3eaa5ef was missing 4 CREATE TABLEs
      (masked by dev create_all) — now verified on truly fresh PostgreSQL and SQLite.

## P2 completion pass (all former "known limitations" closed)
- [x] **Sliding-window rate limiter** — Redis sorted-set sliding log replaces the fixed-window
      counter; no boundary-burst edge (regression-tested: full limit consumed, still blocked
      across the old window boundary; rejected requests don't extend lockout).
- [x] **Grafana + Prometheus shipping in-repo** — `docker-compose.monitoring.yml` overlay,
      provisioned datasource + 9-panel overview dashboard, 7 alert rules matched to real
      metric names (see DEPLOYMENT.md §10).
- [x] **Worker scaling** — `CL_WORKER_CONCURRENCY` thread pool inside each worker
      (4×2s jobs verified finishing in 2.1s wall) + horizontal replicas sharing the Redis
      queue; `CivicLensQueueBacklog` alert is the scale-up signal. Also fixed a latent
      redis-py 8.x BLPOP socket-timeout bug in the worker loop.
- [x] **Web push (VAPID)** — `app/push.py` + `/api/push/*` endpoints + service-worker
      handler + Settings toggle with test button; keygen via `python -m app.push
      --generate-keys`; verified END-TO-END against a mock push service (real pywebpush
      encryption, aes128gcm + VAPID JWT observed). Disabled-by-default; degrades silently.
- [x] **PWA service worker** — `public/sw.js`: app-shell precache, offline navigation
      fallback, immutable-asset caching, API responses never cached; push + notification
      click handling; registered in production builds only.
- [x] **video_embedding duplicate analyzer** — multi-frame perceptual signatures
      (4 frames/video at upload, stored in report_media.frame_sigs) with best-pair +
      coverage scoring; catches re-recordings a single poster hash misses. Candidates
      surface for human review only — never auto-merged (tested).
- [x] **Afaan Oromo + Tigrinya** — full UI dictionaries (language switcher: EN/አማ/OM/ትግ),
      AI language detection (script + distinctive-token analysis, am-vs-ti and en-vs-om
      disambiguation) and per-category om/ti keywords (heuristic v1.4). Eval harness
      extended: om 1.0 / ti 1.0, language detection 7/7, no en/am regression.
- [x] Migration 8/8: b8e2d91a4c33 (push_subscriptions + report_media.frame_sigs) verified
      on fresh SQLite; batch_alter_table used for SQLite compatibility.
