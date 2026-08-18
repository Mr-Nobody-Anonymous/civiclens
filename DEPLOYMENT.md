# CivicLens Ethiopia — Deploy Anywhere Guide

This repo now ships **portable deployment support**: push it to GitHub and run
it on any machine or platform — a laptop, a VPS, Render, Railway, Fly.io, or a
Vercel/Netlify frontend in front of a hosted API.

```
┌────────────────────────────────────────────────────────────────────────┐
│ Pick your path                                                         │
├────────────────────────────────────────────────────────────────────────┤
│ 1. GitHub setup (required once)                 → §1                   │
│ 2. Any machine with Docker (VPS, on-prem)       → §2                   │
│ 3. Render.com — one-click full stack            → §3                   │
│ 4. Railway                                      → §4                   │
│ 5. Fly.io                                       → §5                   │
│ 6. Vercel / Netlify frontend + hosted API       → §6                   │
│ 7. Split deployment (SPA & API on 2 origins)    → §7                   │
│ 8. CI/CD: auto-build images & auto-deploy       → §8                   │
│ 9. First-boot checklist & troubleshooting       → §9                   │
└────────────────────────────────────────────────────────────────────────┘
```

**Architecture refresher** — 3 deployable pieces, all containerized:

| Piece | Image | What it does |
|---|---|---|
| `api` | `Dockerfile` (repo root) | FastAPI backend **+ built React SPA** in one image. Entrypoint auto-runs migrations, base seeding, optional first-admin creation, then serves on `$PORT` (default 8000). |
| `worker` | same image, `worker` arg | Redis job worker (AI pipeline, SLA sweeps). Only needed when `CL_JOB_BACKEND=redis`; the thread backend runs jobs in-process. |
| `ai` | `ai-service/Dockerfile` | Private AI analysis service (heuristic default; optional Ollama). Never expose it to the internet. |

Plus PostgreSQL (or SQLite for tiny installs) and Redis (optional but recommended).

---

## 1. GitHub setup (once)

```bash
cd civiclens
git init -b main
git add .
git commit -m "CivicLens Ethiopia"
git remote add origin https://github.com/<OWNER>/<REPO>.git
git push -u origin main
```

The repo root `.gitignore` keeps secrets (`.env`), the dev SQLite DB and media
out of git. What you get automatically after pushing:

- **CI** (`.github/workflows/ci.yml`) — backend, AI, build, migration tests on every push/PR.
- **Image publishing** (`.github/workflows/deploy.yml`) — on every push to
  `main`, builds and pushes two images to GitHub Container Registry:
  - `ghcr.io/<OWNER>/<REPO>:latest` (API + SPA)
  - `ghcr.io/<OWNER>/<REPO>-ai:latest` (AI service)

  > If the packages are private, `docker login ghcr.io` with a PAT
  > (`read:packages`) on the target machine. To make them public:
  > GitHub → Packages → package → Settings → Change visibility.

---

## 2. Any machine with Docker (VPS, on-prem server, your laptop)

### Option A — build from source on the machine

```bash
git clone https://github.com/<OWNER>/<REPO>.git civiclens && cd civiclens
cp .env.example .env
# edit .env — minimum required:
#   POSTGRES_PASSWORD=<random>
#   CL_SECRET_KEY=$(openssl rand -hex 48)
#   CL_ADMIN_EMAIL=admin@yourcity.gov.et
#   CL_ADMIN_PASSWORD=<strong password>
docker compose up -d --build
```

### Option B — prebuilt images from GHCR (no build tools needed)

```bash
git clone https://github.com/<OWNER>/<REPO>.git civiclens && cd civiclens   # or just copy the 2 files
cp .env.example .env            # same minimum vars as above, plus:
# CIVICLENS_IMAGE=ghcr.io/<OWNER>/<REPO>
docker compose -f docker-compose.prebuilt.yml pull
docker compose -f docker-compose.prebuilt.yml up -d
```

Both options give you: PostgreSQL 16 + Redis 7 + API/SPA on **http://server:8000**
+ worker + private AI service. First boot automatically:

1. applies all Alembic migrations,
2. seeds organizations + routing rules (**no demo data** — `CL_ENV=production`
   defaults `CL_SEED_DEMO_DATA/CL_CREATE_DEMO_ACCOUNTS` to `false`),
3. creates/promotes the admin from `CL_ADMIN_EMAIL`/`CL_ADMIN_PASSWORD`
   (idempotent — remove these vars after first boot).

**TLS**: put a reverse proxy in front (see `deploy/nginx.conf.example`, HSTS
included) or a managed edge (Cloudflare, Caddy: `caddy reverse-proxy --from
civiclens.example.com --to localhost:8000`).

**Upgrades**: `git pull && docker compose up -d --build` (or `pull` + `up -d`
for prebuilt). Migrations run automatically on start.

**Backups**: `scripts/backup.sh`, restore drill: `scripts/dr-verify.sh`.

---

## 3. Render.com — one-click full stack (`render.yaml`)

The repo root contains a **Render Blueprint** describing the entire stack
(web + worker + private AI service + managed PostgreSQL + Key Value/Redis + media disk).

1. Push to GitHub (§1).
2. Render Dashboard → **New → Blueprint** → pick the repo.
3. Render reads `render.yaml`; fill in the two prompted secrets:
   `CL_ADMIN_EMAIL`, `CL_ADMIN_PASSWORD` (`CL_SECRET_KEY` is auto-generated).
4. Click **Apply**. First deploy migrates, seeds and creates your admin.

Your app is live at `https://civiclens-api.onrender.com` (rename the service
for a nicer subdomain, or attach a custom domain — Render provides TLS).

Notes:
- The SPA is served by the API service → same-origin → no CORS/cookie config.
- Media lives on a 10 GB Render Disk mounted at `/data/storage`
  (or switch to S3: `CL_STORAGE_BACKEND=s3` + `CL_S3_*`).
- Free-tier caveat: free web services sleep and **have no disks** — use at
  least Starter for the API, or S3 storage.

---

## 4. Railway (`railway.json`)

1. railway.app → **New Project → Deploy from GitHub repo** → pick the repo.
   `railway.json` makes it build the root `Dockerfile` and health-check `/api/health`.
2. Add plugins: **PostgreSQL** and **Redis** (Railway injects `DATABASE_URL`, `REDIS_URL`).
3. Service → Variables:

   ```
   CL_ENV=production
   CL_SECRET_KEY=<openssl rand -hex 48>
   CL_DATABASE_URL=${{Postgres.DATABASE_URL}}   # then change postgres:// → postgresql+psycopg://
   CL_REDIS_URL=${{Redis.REDIS_URL}}
   CL_JOB_BACKEND=redis
   CL_ADMIN_EMAIL=... / CL_ADMIN_PASSWORD=...
   ```

   > SQLAlchemy needs the `postgresql+psycopg://` scheme. If your platform
   > injects `postgres://…`, paste the value and edit the scheme.

4. Duplicate the service for the **worker** (same repo/vars, start command
   `./docker-entrypoint.sh worker`) and add a third service for **ai-service/**
   (root directory `ai-service`), then set `CL_AI_SERVICE_URL` on api+worker to
   its private URL.
5. Media storage on Railway is ephemeral → attach a volume at `/data/storage`
   or set `CL_STORAGE_BACKEND=s3`.

---

## 5. Fly.io (`fly.toml`)

```bash
fly launch --copy-config --no-deploy          # uses the checked-in fly.toml
fly postgres create --name civiclens-db && fly postgres attach civiclens-db
fly redis create                              # note the Upstash URL
fly volumes create civiclens_media --size 10
fly secrets set \
  CL_SECRET_KEY=$(openssl rand -hex 48) \
  CL_DATABASE_URL='postgresql+psycopg://...' \
  CL_REDIS_URL='redis://default:...@fly-....upstash.io:6379' \
  CL_ADMIN_EMAIL=admin@yourcity.gov.et CL_ADMIN_PASSWORD='...'
fly deploy
fly scale count app=1 worker=1
```

`fly.toml` defines two process groups (`app` = API+SPA, `worker`) sharing the
image and the media volume, health-checked on `/api/health`, region `jnb`
(closest to Ethiopia). Deploy the AI service as a second Fly app from
`ai-service/` and point `CL_AI_SERVICE_URL` at its `.internal` address, or
leave it unset — reports then fall back to manual review gracefully.

---

## 6. Vercel / Netlify frontend + hosted API (recommended split)

Deploy the **frontend** to Vercel/Netlify's CDN while the API runs on any of
§2–§5. The configs proxy `/api/*` at the edge so the **browser stays
same-origin** — sessions, CSRF and SSE work with zero backend changes.

> Vercel/Netlify run static sites + short serverless functions. The CivicLens
> API needs FFmpeg, background jobs, SSE and persistent storage, so the API
> itself belongs on Render/Fly/Railway/VPS — this split is the supported way
> to "deploy on Vercel".

### Vercel

1. Deploy the API somewhere (e.g. §3) → note `https://civiclens-api.onrender.com`.
2. Edit `frontend/vercel.json` → replace `YOUR-API-HOST.example.com` with your API host.
3. vercel.com → **Add New Project** → import the GitHub repo →
   **Root Directory: `frontend`** (framework auto-detected: Vite). Deploy.

   Or from the CLI: `cd frontend && npx vercel --prod`.

### Netlify

Same idea: edit `frontend/netlify.toml` (API host), then **Add new site →
Import from GitHub**, set **Base directory: `frontend`**. The file already
configures build, SPA fallback, `/api/*` proxy and cache headers.

---

## 7. Split deployment WITHOUT a proxy (two real origins)

If you cannot proxy (SPA at `https://app.example.com` calling
`https://api.example.org` directly from the browser):

**Frontend build:**
```bash
VITE_API_BASE=https://api.example.org npm run build     # or set in Vercel env UI
```
Every API call, media URL, upload and the SSE stream is then prefixed with
that origin, and the client bootstraps its CSRF token from
`GET /api/auth/csrf` (it can't read the API domain's cookie).

**API env:**
```bash
CL_CORS_ORIGINS=https://app.example.com     # exact origins, comma separated
# cookies auto-switch to SameSite=None; Secure — HTTPS is mandatory on BOTH sides
```

Caveats (why §6 is preferred): Safari/iOS privacy modes can block third-party
cookies entirely; SameSite=None requires HTTPS everywhere. If SPA and API
share a parent domain (`app.example.com` + `api.example.com`), you may set
`CL_COOKIE_SAMESITE=lax` — that pair counts as *same-site*.

---

## 8. CI/CD summary

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | push/PR | lint + backend/AI tests + build + migrations |
| `deploy.yml` | push to `main`, tags `v*` | build+push GHCR images; optional auto-deploys |

Auto-deploy hooks (all optional — enable via repo **Variables** + **Secrets**):

| Platform | Variable | Secret |
|---|---|---|
| Render | `RENDER_ENABLED=true` | `RENDER_DEPLOY_HOOK_URL` |
| Vercel | `VERCEL_ENABLED=true` | `VERCEL_DEPLOY_HOOK_URL` |
| Fly.io | `FLY_ENABLED=true` | `FLY_API_TOKEN` |

Versioned releases: `git tag v1.0.0 && git push --tags` → images
`ghcr.io/<OWNER>/<REPO>:1.0.0`.

---

## 9. First-boot checklist & troubleshooting

**Minimum required env** (everything else has safe defaults):

| Var | Value |
|---|---|
| `CL_ENV` | `production` |
| `CL_SECRET_KEY` | `openssl rand -hex 48` |
| `CL_DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/db` (SQLite ok for tiny installs) |
| `CL_ADMIN_EMAIL` / `CL_ADMIN_PASSWORD` | first admin (remove after boot) |

**Verify a deployment:**
```bash
curl https://your-host/api/health      # {"status":"ok",...}
curl https://your-host/api/ready       # DB / AI / Redis / circuit breakers
```

**Common issues**

| Symptom | Cause → fix |
|---|---|
| `REFUSING to seed demo data` in logs, container exits | You explicitly set `CL_SEED_DEMO_DATA=true` with `CL_ENV=production`. Unset it (entrypoint defaults both flags to `false` in production). |
| Login works but every POST returns 403 CSRF | Split deployment without `VITE_API_BASE` baked into the SPA build, or missing `CL_CORS_ORIGINS` on the API. See §7. |
| Cookies not set at all (split mode) | Not HTTPS. `SameSite=None` cookies require `Secure`. Terminate TLS on both origins. |
| `could not translate host name` / DB scheme errors | Platform injected `postgres://…`; SQLAlchemy needs `postgresql+psycopg://…`. |
| AI status “unreachable” in `/api/ready` | `CL_AI_SERVICE_URL` wrong/absent. Non-fatal: reports queue for manual review. Bare `host:port` values are accepted (scheme auto-added). |
| Media disappears after redeploy | Ephemeral disk. Attach a volume at `/data/storage` or use `CL_STORAGE_BACKEND=s3`. |
| 429s during smoke tests | Production rate limits (10 reports/h). Raise `CL_RATE_LIMIT_*` temporarily. |

**Security notes for public deployments**
- Block `/api/metrics` at the proxy (Prometheus scrape endpoint).
- Keep the AI service private (Render `pserv`, Fly `.internal`, compose `expose`).
- Set `CL_EMAIL_BACKEND=smtp` + `CL_SMTP_*` so password resets actually send.
- See `PRODUCTION.md` for the full 44-point hardening checklist.

---

## 10. Monitoring (Prometheus + Grafana)

The repo ships a full monitoring overlay — dashboards and alert rules included:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
# Grafana:    http://localhost:3001  (admin / $GRAFANA_PASSWORD)
# Prometheus: http://localhost:9090  (alert rules pre-loaded)
```

| Piece | File |
|---|---|
| Scrape config | `deploy/monitoring/prometheus.yml` |
| 7 alert rules (API down, worker stalled, queue backlog, dead jobs, 5xx rate, p95 latency, AI failures) | `deploy/monitoring/alerts.yml` |
| Grafana datasource + dashboard provisioning | `deploy/monitoring/grafana/provisioning/` |
| "CivicLens — Platform Overview" dashboard (9 panels) | `deploy/monitoring/grafana/dashboards/civiclens-overview.json` |

For managed monitoring (Grafana Cloud etc.): point the scraper at
`https://your-host/api/metrics` from your monitoring network and import the
dashboard JSON.

## 11. Worker scaling

Two knobs, both driven by the `civiclens_queue_depth` metric:

1. **Vertical:** `CL_WORKER_CONCURRENCY=N` — parallel jobs per worker process
   (thread pool; verified 4x parallelism). Default 2; raise on bigger machines.
2. **Horizontal:** add worker replicas — they share the Redis queue safely
   (`docker compose up -d --scale worker=3`, or extra Render/Fly worker
   instances). Job records are idempotent and crash-recovery re-queues stuck
   jobs, so scaling down is safe too.

The `CivicLensQueueBacklog` alert fires when depth stays over 25 for 5
minutes — that is your scale-up signal (Kubernetes users: attach an HPA to
the same metric via prometheus-adapter).

## 12. Web push notifications

```bash
cd backend && python -m app.push --generate-keys   # once per deployment
# put the printed CL_VAPID_* values in the API + worker environment
```

Users then enable "Push notifications on this device" in **Settings →
Notification preferences** (toggle + test button). Notes:
- Requires HTTPS in real browsers (localhost is exempt for testing).
- Without keys the feature degrades silently: the UI explains it is not
  configured, the API returns 503, nothing else changes.
- Dead subscriptions (browser revoked) are pruned automatically on send.
