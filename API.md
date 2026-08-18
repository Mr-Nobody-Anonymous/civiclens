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
| GET | `/api/auth/csrf` | cookie | CSRF token for the current session (`{csrf_token}` or `null`). Used by cross-origin SPAs (split deployments) that cannot read the `cl_csrf` cookie; same-origin frontends read the cookie directly. |
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

## Trust & operations (CivicLens 2.0)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/reviews?status=&reason=` | staff | AI Review Queue: pending recommendations with per-reason counts (`low_confidence`, `high_severity`, `ai_disagreement`, `integrity_flag`) |
| POST | `/api/reviews/:id/decide` | staff | `{action: accepted|corrected|rejected, corrected_category?, corrected_severity?, reason}` — corrections apply to the report and set `human_confirmed`; one decision resolves all sibling reviews |
| GET | `/api/reviews/history` | staff | AI prediction → human decision dataset (model evaluation) |
| GET | `/api/clusters?status=&city=` | — | Issue clusters (≥2 reports): one underlying civic issue, report/reporter counts, first/last reported |
| GET | `/api/clusters/:id` | — | Cluster detail with member reports (public shapes) |
| GET | `/api/reports/:id/sla` | staff/org | Live SLA state: ack/resolve windows, age, overdue hours, breach flag |
| GET | `/api/sla/escalations` | staff | Escalation events (created once per breach kind, admins notified) |
| POST | `/api/sla/check` | staff | On-demand SLA sweep (worker also runs it every 5 min) |
| GET | `/api/organizations/:id/sla-stats` | staff/org | Compliance %, overdue, critical overdue, avg response time |
| GET | `/api/stream` | user | Server-Sent Events: real-time notification push (30s polling remains the fallback) |

Evidence integrity: every upload records a SHA-256 (evidence chain) and a perceptual hash;
reports get an `integrity_score` (0–1) + human-readable `integrity_notes`. Low scores are phrased
as "requires additional verification" and queue human review — never auto-rejected. Duplicate
analyzers now include `image_hash` (visual near-duplicates) alongside `geo_text`.

## Phase B: resolution verification · moderation · resumable uploads · offline
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/reports/:id/confirm-resolution?confirmed=` | reporter | Citizen verdict on a resolved report; `false` reopens via the state machine ("still a problem") |
| GET | `/api/moderation/queue?kind=` | staff | Unified queue: `ai_review`, `flagged_report`, `flagged_comment`, `dup_cluster` — severity-first ordering, per-kind counts |
| POST | `/api/moderation/comments/:id/flag` | user | Report an abusive comment |
| POST | `/api/moderation/comments/:id/hide` | staff | `{hidden, reason}` — reversible hide/restore (never deletes) |
| POST | `/api/moderation/bulk` | staff | Safe reversible bulk actions only (`unflag_reports`, `hide_comments`, `restore_comments`; ≤50 items) |
| GET | `/api/moderation/history` | staff | Full moderation audit trail |
| POST | `/api/uploads` | reporter/staff | Create resumable upload session `{report_id, content_type, total_size, sha256?}` → `{upload_id, chunk_size, total_chunks}` |
| PUT | `/api/uploads/:id/chunks/:n` | session owner | Upload one chunk (idempotent re-PUT) |
| GET | `/api/uploads/:id` | session owner | Resume info: received + missing chunk indexes |
| POST | `/api/uploads/:id/complete` | session owner | Assemble → checksum verify → full media validation pipeline (idempotent) |
| DELETE | `/api/uploads/:id` | session owner | Abort + cleanup (abandoned sessions auto-cleaned after 24h) |

**Resolution verification rules:** physical categories (Roads, Water, Electricity, Sanitation,
Public Buildings, Safety) cannot be marked resolved without resolution evidence — admins/mods may
override with a written, audited reason. Uploading resolution evidence triggers an ADVISORY
before/after visual comparison (`resolution_check_score`/`notes`); low scores queue human review.
The advisory never changes status — humans do.

**Offline idempotency:** report creation accepts `client_key`; retried submissions with the same
key return the original report (`deduplicated: true`) so reconnecting phones can never create
duplicates. The frontend queues offline reports in localStorage and auto-syncs on reconnect.

**The AI rule (enforced everywhere):** AI recommends → deterministic backend validates → human can
override → audit trail records everything. No model can resolve/delete/ban/expose/bypass anything.

## Phase C: multilingual AI · voice · subscriptions · community · intelligence
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/voice/transcribe` | optional | Raw audio body → local Whisper STT (Amharic + English) → transcript + language + AI draft (category/severity). Citizen ALWAYS reviews before submitting. Rate-limited. |
| POST | `/api/subscriptions` | user | Follow a `report`, `cluster`, `category`, or `area` (lat/lng + radius). Idempotent. |
| GET/DELETE | `/api/subscriptions[/:id]` | user | List / unfollow. Followers get `followed_update` notifications when new reports match. |
| POST | `/api/reports/:id/verify` | user | Community verification `{vote: still_exists|resolved|not_sure}` — one vote per citizen (changeable), no self-votes, rate-limited. **Votes are evidence for reviewers, never authority** — status never changes from votes. |
| GET | `/api/reports/:id/verification` | — | Anonymous public aggregation (+ `my_vote` when signed in). |
| GET/PUT | `/api/notification-preferences` | user | Per-kind notification toggles (status changes, org responses, resolution, reopened, followed updates, email). Unknown keys ignored. |
| GET | `/api/intelligence/overview?city=` | staff | City intelligence: open/critical counts, active clusters, geographic hotspots with week-over-week trends, emerging category trends — all real aggregation, advisories clearly labelled. |
| GET | `/api/intelligence/hotspots?city=&days=` | — | Public hotspot cells (coarse ~1km grid coordinates only). |

**Multilingual AI (heuristic v1.3):** deep Amharic keyword coverage per category, Amharic
severity/urgency/scale signals, mixed-language (አማርኛ+English) understanding, language detection,
and **AI reasoning written in the reporter's language**. Amharic accuracy eval dataset lives in
`ai-service/test_ai.py` (≥5/6 categories required). Whisper model via `WHISPER_MODEL`
(tiny dev / small+ prod). **Geographic routing:** rules may carry a lat/lng/radius geofence —
category + location + jurisdiction beats city-wide rules inside the fence.

## P1: org operations · transparency · advanced search · security maturity
| Method | Path | Auth | Description |
|---|---|---|---|
| POST/GET | `/api/orgops/organizations/:id/departments` | org manager+ | Departments/teams with optional geofence responsibility; list shows member counts + open workload |
| POST | `/api/orgops/organizations/:id/invites` | org manager+ | Staff invitation by email `{email, org_role, department_id?}` — 7-day token, single use, email-bound |
| POST | `/api/orgops/invites/:token/accept` | invitee | Accept → becomes org_staff with role + department |
| GET | `/api/orgops/organizations/:id/assignment-recommendation?report_id=` | org manager+ | ADVISORY staff ranking (geofence match + lowest workload) — supervisor assigns |
| GET | `/api/orgops/organizations/:id/escalations` | org manager+ | Escalation events with live SLA state. SLA sweep now escalates: assignee → supervisors → admins |
| GET | `/api/transparency?city=` | — | **Public portal**: totals, resolution rate, top issues, org performance (rate + avg days), 6-month trend. Privacy-preserving. |
| GET | `/api/transparency/clusters/:id/timeline` | — | Public issue page: cluster overview + member status breakdown |
| GET | `/api/search?...` | — | Advanced search: q/category/status/min_severity/city/organization/cluster/date range/geo radius; `sla=breached` staff-only |
| POST/GET | `/api/saved-searches` | user | Save + list named filter sets |
| GET | `/api/organizations/:id/resolution-quality` | staff/org | ADVISORY composite: evidence 30% · citizen confirmation 25% · reopen rate 20% · before/after 15% · community 10% |
| GET | `/api/intelligence/briefing?city=` | staff | **Civic Briefing**: critical/new/SLA/reopened/citizens/votes KPIs + template-generated advisory. Always labelled "AI-generated advisory. Human decision required." |
| POST | `/api/security/verify-email/request` + `/confirm` | user | Email verification (24h single-use tokens) |
| POST | `/api/security/mfa/setup` → `/enable` → `/disable` | user | TOTP MFA (RFC 6238, stdlib) + 8 hashed single-use backup codes; login returns **428** when MFA code missing |
| GET/DELETE | `/api/security/sessions[/:prefix]` | user | Device/session management: list (current marked), revoke by prefix |

## Misc
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/notifications` | user | In-app notifications |
| POST | `/api/notifications/read-all` | user | Mark all read |
| GET | `/api/audit-logs?limit=` | staff | Audit trail |
| GET | `/api/meta` | — | Categories, cities, limits, map center |
| GET | `/api/health` | — | Health check |

## Web push (VAPID; disabled unless CL_VAPID_* keys are set)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/push/vapid-public-key` | — | Server public key for PushManager (503 when unconfigured) |
| GET | `/api/push/status` | user | `{enabled, devices}` for the current user |
| POST | `/api/push/subscribe` | user | Register this browser `{endpoint,p256dh,auth}`; idempotent per endpoint |
| DELETE | `/api/push/subscribe` | user | Remove by endpoint (own subscriptions only) |
| POST | `/api/push/test` | user | Send a test notification to all of my devices (rate-limited 5/h) |

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
