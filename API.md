# CivicLens Ethiopia — API Documentation

Base URL: `/api` · Interactive docs (Swagger UI): **`/docs`** · OpenAPI JSON: `/openapi.json`

Authentication: **session cookie** (`cl_session`, HttpOnly, Secure in production, SameSite=Lax).
Roles: `citizen`, `moderator`, `org_staff`, `admin`.

**CSRF:** all state-changing requests (POST/PUT/PATCH/DELETE) from an authenticated session must
send `X-CSRF-Token` matching the `cl_csrf` cookie set at login (double-submit pattern). The
frontend API client does this automatically. Login/register/password-reset are exempt (no session
yet). Requests failing the check get `403 {"detail": "CSRF token missing or invalid"}`.

**Errors:** consistent JSON `{"detail": "...", "request_id": "..."}`; validation errors add an
`errors: [{field, message}]` array. Status codes: 401 unauthenticated, 403 forbidden/CSRF,
404 missing, 409 invalid state transition / conflict, 413 too large, 415 bad media type,
422 validation, 429 rate-limited/locked out.

**Rate limits (configurable):** login/register 10/min/IP, anonymous reports 10/h/IP,
uploads 30/h/IP, flags 10/h/IP, password reset 5/h/IP. Account lockout: 8 failed logins → 15 min.

```bash
# Example: login then create a report with CSRF
curl -c jar -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@civiclens.et","password":"admin12345"}'
CSRF=$(grep cl_csrf jar | awk '{print $7}')
curl -b jar -X POST localhost:8000/api/reports \
  -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"title":"Pothole on Bole Road","description":"Deep pothole near Edna Mall affecting traffic.","category":"Roads & Transportation","city":"Addis Ababa","latitude":8.99,"longitude":38.79}'
```

## Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | Create citizen account `{name,email,password,city?,language?}` |
| POST | `/api/auth/login` | — | Log in `{email,password}` |
| POST | `/api/auth/logout` | cookie | Destroy session |
| POST | `/api/auth/logout-all` | user | Revoke every session for this account |
| POST | `/api/auth/change-password` | user | `{current_password,new_password}` — revokes other sessions |
| POST | `/api/auth/forgot-password` | — | `{email}` — always 200 (no enumeration); reset token e-mailed |
| POST | `/api/auth/reset-password` | — | `{token,new_password}` — single-use, 2h expiry |
| GET | `/api/auth/me` | cookie | Current user or `null` |
| PATCH | `/api/auth/settings` | user | Update name/city/language/email_notifications |
| DELETE | `/api/auth/me` | user | Delete account (reports anonymised) |

## Reports
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/reports` | optional | Create report. Anonymous submissions require `captcha_a`,`captcha_b`,`captcha_answer` (arithmetic check). Rate-limited per IP. Returns `possible_duplicate` hint. |
| POST | `/api/reports/:id/media` | reporter/staff | Multipart upload (`file`, optional `kind=resolution`, `finalize=true|false`). Validates MIME type, magic bytes, size. Generates thumbnail + metadata via FFmpeg. |
| POST | `/api/reports/:id/finalize` | optional | Kick off async AI pipeline (frame extraction → local AI → routing). |
| GET | `/api/reports` | — | List. Filters: `q, category, status, severity, min_severity, city, mine, sort(recent|severity), page, page_size`. Public shape hides reporter identity; coordinates rounded. |
| GET | `/api/reports/map` | — | Lightweight GeoJSON-ish list for the map (max 1000). Filters: `category, min_severity, status`. |
| GET | `/api/reports/priority` | staff/org | Priority queue: open reports, severity desc. Org staff see only their org. |
| GET | `/api/reports/:id` | — | Detail (accepts internal id or public code `CL-XXXXXX`). Privileged viewers additionally get reporter info, internal notes, exact coordinates. |
| GET | `/api/reports/:id/analysis` | — | AI analysis status/result (poll after submit). |
| GET | `/api/reports/:id/media/:mid/file` | access-controlled | Streams media with HTTP Range support. Storage paths are never exposed. |
| GET | `/api/reports/:id/media/:mid/thumb` | access-controlled | JPEG thumbnail. |
| PATCH | `/api/reports/:id/status` | staff/org | `{status, note?}` — status transitions with history + reporter notification. |
| PATCH | `/api/reports/:id/assignment` | admin/mod (re-route), org (accept) | `{organization_id?, note?}` or `{accept: true|false}`. |
| PATCH | `/api/reports/:id/correction` | admin/mod | Correct AI: `{category?, issue_type?, severity?, note?}` — marks analysis as human-corrected. |
| POST | `/api/reports/:id/comments` | user | `{body, internal?}` (internal notes: staff only). |
| POST | `/api/reports/:id/flag` | optional | Flag spam/abuse `{reason}` — hides report from public pending moderation. |
| PATCH | `/api/reports/:id/unflag` | admin/mod | Restore flagged report. |
| PATCH | `/api/reports/:id/duplicate?of_code=CL-XXXX` | admin/mod | Mark as duplicate. |

## Organizations & routing rules
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/organizations` | — | Active organizations |
| POST | `/api/organizations` | admin | Create organization |
| POST | `/api/organizations/:id/members?email=&org_role=` | admin | Add staff member (promotes user to `org_staff`) |
| GET | `/api/rules` | staff | List routing rules |
| POST | `/api/rules` | admin | `{category, organization_id, keywords?, city?, priority?, auto_assign?}` |
| DELETE | `/api/rules/:id` | admin | Deactivate rule |

## Dashboards
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/dashboard/public-stats` | — | Landing counters |
| GET | `/api/dashboard/stats` | staff | Full admin stats: totals, trends, category/status/severity/org breakdowns, AI confidence + correction rate, avg resolution time, hotspots |
| GET | `/api/dashboard/org-stats` | org staff | Own-organization stats |
| GET | `/api/dashboard/org-reports?status=` | org staff | Reports assigned to own org only |

## Admin management
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/admin/users?q=&role=&page=` | admin | User management list |
| PATCH | `/api/admin/users/:id/role` | admin | Change role (cannot change own role) |
| PATCH | `/api/admin/users/:id/active?active=` | admin | Deactivate/reactivate (kills sessions) |
| GET | `/api/admin/jobs?status=` | staff | Background job list incl. failed/dead |
| POST | `/api/admin/jobs/:id/retry` | admin | Requeue a failed/dead job |
| GET | `/api/admin/ai-performance` | staff | AI success/correction/confidence/duration stats |
| GET | `/api/admin/reports/:id/routing` | staff | Explain why a report was routed where it was |

## Misc
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/notifications` | user | In-app notifications |
| POST | `/api/notifications/read-all` | user | Mark all read |
| GET | `/api/audit-logs?limit=` | staff | Audit trail |
| GET | `/api/meta` | — | Categories, cities, limits, map center |
| GET | `/api/health` | — | Health check |

## AI service (internal, port 8090)
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Model name/version |
| POST | `/analyze` | `{title, description, comments?, user_category?, city?, frames_b64[], images_b64[], video_meta?}` → `{category, issue_type, severity 1-5, confidence 0-1, urgency, responsible_organization, organization_type, reasoning, model_name, model_version, frames_analyzed}` |

Severity scale: **1 Minor · 2 Low · 3 Moderate · 4 Serious · 5 Critical**.

**Status state machine** (invalid transitions are rejected with 409):
`submitted → ai_analysis → under_review → assigned → in_progress → resolved`,
plus `rejected` (requires a reason note), `duplicate`, and `reopened`
(from resolved/rejected — reporter can dispute). `routing_state` tracks
`unrouted | routed | needs_manual_routing | manual`; `processing_state` tracks the AI
pipeline (`none | queued | processing | done | failed`) so no report ever silently disappears.

**Health:** `GET /api/health` (liveness) · `GET /api/ready` (DB / AI service / Redis checks).
