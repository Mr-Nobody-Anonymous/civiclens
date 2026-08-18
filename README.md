# 🇪🇹 CivicLens Ethiopia

A full-stack civic-tech platform for Ethiopian cities: citizens report public-service
problems with **video evidence**, a **locally-hosted AI** classifies each report
(category, issue type, severity 1–5, confidence), and configurable **routing rules**
send it to the responsible organization (Ethio telecom, Roads Authority, Water &
Sewerage Authority, Electric Utility, Education Bureau, City Administration, …).

**English + Amharic UI · dark/light · mobile-first · map with clustering & heatmap · RBAC (citizen / moderator / org staff / admin).**

---

## Architecture

```
Browser (React SPA, Vite, Tailwind, Leaflet, Recharts)
   │  same-origin /api  (session cookie, no keys in frontend)
   ▼
FastAPI backend ──► SQLAlchemy ORM ──► SQLite (dev) / PostgreSQL (prod, Alembic migrations)
   │   ├── Storage abstraction: local disk (dev) / S3-compatible (prod) — private keys,
   │   │   media streamed only through access-controlled endpoints (Range supported)
   │   ├── Background jobs: in-process thread pool (dev) / Redis queue + worker (prod)
   │   └── Notifications: in-app + email (console dev / SMTP prod; SMS/Telegram pluggable)
   ▼ (async job)
FFmpeg pipeline (probe, thumbnail, N representative frames, optional transcode)
   ▼
Local AI service (FastAPI, port 8090) — pluggable analyzers:
   • heuristic  : built-in EN+AM multilingual classifier (zero deps, always works)
   • ollama     : any local Ollama model (llava for vision frames, llama3.x for text)
   ▼
Routing rules (organization_rules table) → recommendation → human review → organization portal
```

**Stack choice:** the brief suggested Next.js; I used **Vite + React SPA + FastAPI**
instead because the platform already needs a Python service for FFmpeg/AI work — one
Python backend for API + jobs + AI orchestration is simpler to operate on-premise
(municipal servers), and the built SPA is served directly by FastAPI, so production is
a single container + AI sidecar. All requirements (SSR isn't needed here) are met.

## Quick start (local, no Docker)

```bash
# 1) AI service
cd ai-service && pip install -r requirements.txt
python main.py                                   # :8090

# 2) Backend API (new terminal)
cd backend && pip install -r requirements.txt
python -m alembic upgrade head                   # run migrations
python seed.py                                   # demo orgs/rules/reports/accounts
python -m uvicorn app.main:app --port 8000       # :8000  (needs ffmpeg installed)

# 3) Frontend (new terminal)
cd frontend && npm install
npm run dev                                      # :5173 (proxies /api → :8000)
```

Open http://localhost:5173. Swagger docs: http://localhost:8000/docs.

### Demo accounts (from `seed.py`)
| Account | Password | Role |
|---|---|---|
| admin@civiclens.et | admin12345 | Administrator |
| moderator@civiclens.et | moderator123 | Moderator |
| staff@ethiotelecom.et | telecom123 | Ethio telecom staff |
| staff@roads.et | roads12345 | Roads Authority staff |
| citizen@example.et | citizen123 | Citizen |

Demo reports are labelled with a **DEMO** badge.

## Environment variables

See **`.env.example`** (all prefixed `CL_`). Key ones:

| Variable | Purpose | Dev default |
|---|---|---|
| `CL_SECRET_KEY` | session security — set a long random string in prod | dev value |
| `CL_DATABASE_URL` | any SQLAlchemy URL | SQLite file |
| `CL_STORAGE_BACKEND` / `CL_STORAGE_DIR` | `local` or `s3` (+S3 creds via env) | local `./storage` |
| `CL_AI_SERVICE_URL` | where the AI service lives | `http://127.0.0.1:8090` |
| `CL_JOB_BACKEND` | `thread` or `redis` | thread |
| `CL_EMAIL_BACKEND` | `console` or `smtp` | console |
| `CL_MAX_VIDEO_MB` / `CL_MAX_IMAGE_MB` | upload limits | 100 / 10 |
| `CL_CITIES` | configurable city list (first = default) | 8 Ethiopian cities |

## How to…

**Start the AI service** — `cd ai-service && python main.py` (env `PORT`, default 8090).

**Start the worker (Redis mode)** — set `CL_JOB_BACKEND=redis`, run Redis, then
`cd backend && python -m app.worker` (any number of workers). In `thread` mode no
worker is needed; jobs run in the API process.

**Create an admin account** — seed creates one, or promote any user:
```bash
cd backend && python -c "
from app.db import SessionLocal; from app.models import User, Role
db=SessionLocal(); u=db.query(User).filter_by(email='you@example.et').first()
u.role=Role.admin; db.commit(); print('promoted', u.email)"
```

**Add an organization + route reports to it** (as admin, via API or Swagger):
```bash
curl -b cookies.txt -X POST localhost:8000/api/organizations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Adama Roads Bureau","org_type":"Roads/Public Works","city":"Adama"}'
curl -b cookies.txt -X POST localhost:8000/api/rules \
  -H 'Content-Type: application/json' \
  -d '{"category":"Roads & Transportation","organization_id":"<ORG_ID>","city":"Adama","priority":10}'
curl -b cookies.txt -X POST "localhost:8000/api/organizations/<ORG_ID>/members?email=staff@adama.et"
```

**Configure the local AI model** — the AI layer is pluggable:
```bash
# default: built-in heuristic (EN + Amharic), zero dependencies
AI_MODEL=heuristic python ai-service/main.py

# real local vision/LLM via Ollama (frames from videos are passed as images):
ollama pull llava:7b
AI_MODEL=ollama OLLAMA_MODEL=llava:7b python ai-service/main.py
```
If Ollama is unreachable the service degrades gracefully to the heuristic engine.
To add a better model later, implement another `Analyzer` class in
`ai-service/main.py` — the `/analyze` contract never changes.

**Deploy (Docker Compose)** — PostgreSQL + Redis + API + worker + AI service:
```bash
cp .env.example .env    # set CL_SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build -d
# app at http://localhost:8000 (frontend baked into the API image)
```
Put a TLS reverse proxy (Caddy/Nginx) in front for production; cookies become
`Secure` automatically when `CL_ENV=production`.

## Tests

```bash
cd backend && python -m pytest tests -q      # 39 tests: auth, CSRF, lockout, RBAC, org isolation,
                                             #   uploads incl. malicious, media authz, state machine,
                                             #   jobs/dead-letter, routing, full E2E workflow
cd ai-service && python -m pytest -q         # 10 tests: EN/AM classification, Ollama offline/invalid
                                             #   JSON/unknown-category fallbacks, metadata
```

## Production hardening (v2)
- **CSRF**: double-submit cookie (`cl_csrf` + `X-CSRF-Token`) enforced on all state-changing
  requests; frontend client attaches it automatically
- **Auth**: password change + reset flow (single-use 2h tokens, no account enumeration),
  logout-all-devices, per-email lockout (8 failures → 15 min), session revocation & cleanup
- **State machine**: central transition service — invalid report status changes get 409;
  reopen/dispute flow for citizens; rejected requires a reason
- **Jobs**: persistent `jobs` table with retries, exponential backoff, dead-letter state,
  stuck-job recovery on worker restart, admin retry UI; idempotent processing (no duplicate
  AI results/notifications)
- **AI resilience**: reports never disappear — AI outage → `needs_manual_routing` +
  `under_review`, admins can re-run analysis; confidence bands (high/medium/low) gate
  auto-assignment; human corrections are never overwritten by automation
- **Uploads**: extension/MIME/magic-byte agreement, ffprobe deep validation, duration cap,
  attachment cap, corrupt-media rejection, server-generated storage keys
- **Headers**: CSP, X-Frame-Options, Permissions-Policy, HSTS (prod), nosniff, request IDs
- **Observability**: `/api/health` + `/api/ready` (DB/AI/Redis checks), structured request
  logs, job/audit trails, AI performance dashboard endpoint
- **Ops**: `scripts/backup.sh` + `scripts/restore.sh` (DB + media together), PRODUCTION.md
  checklist, non-root Docker images with healthchecks, Redis AOF persistence

## Security & privacy highlights
- PBKDF2 password hashing (260k iterations), HttpOnly session cookies, DB-backed sessions
- Role-based access control on every privileged endpoint; org staff see only their org's reports
- Upload validation: MIME allow-list + magic-byte sniffing + size limits
- Media streamed through authorised endpoints only; storage keys never exposed
- Public API never returns reporter identity; public coordinates rounded (~11 m)
- Per-IP rate limits, arithmetic captcha for anonymous reports, duplicate detection (geo+text)
- Flagging/moderation pipeline, full audit log, account deletion with report anonymisation
- AI output is always labelled as a recommendation with confidence; admins can correct it
  (corrections are tracked to measure AI quality)

## Repository layout
```
civiclens/
├── backend/           FastAPI app (routers, models, jobs, storage, security)
│   ├── migrations/    Alembic migrations
│   ├── seed.py        demo data
│   └── tests/         pytest suite
├── ai-service/        local AI analysis service (pluggable models) + tests
├── frontend/          React + TypeScript + Tailwind SPA
├── docker-compose.yml full stack: postgres, redis, api, worker, ai
├── Dockerfile         api image (frontend build baked in)
├── API.md             endpoint documentation
└── .env.example       all configuration
```
