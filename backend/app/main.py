"""CivicLens Ethiopia — API entrypoint.

Serves the REST API under /api and, when a built frontend exists
(frontend/dist), the compiled SPA for every other route.
"""
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import admin as admin_router, auth, dashboard, orgs, reports
from .security import csrf_protect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s rid=%(request_id)s %(message)s"
    if False else "%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("civiclens")

app = FastAPI(
    title="CivicLens Ethiopia API",
    version="1.0.0",
    description=(
        "Civic issue reporting platform for Ethiopian cities. "
        "Citizens report problems with video evidence; a local AI service "
        "classifies them and routes them to the responsible organization. "
        "Interactive docs: /docs — OpenAPI JSON: /openapi.json"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def request_pipeline(request: Request, call_next):
    """Request ID + structured access log + CSRF + security headers."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    start = time.time()

    # CSRF protection for state-changing requests from cookie-authenticated sessions
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api"):
        db = SessionLocal()
        try:
            await csrf_protect(request, db)
        except HTTPException as e:
            db.close()
            return JSONResponse({"detail": e.detail, "request_id": rid}, status_code=e.status_code)
        finally:
            try:
                db.close()
            except Exception:
                pass

    try:
        resp = await call_next(request)
    except Exception:
        log.exception("unhandled error rid=%s %s %s", rid, request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)

    dur = (time.time() - start) * 1000
    if request.url.path.startswith("/api"):
        log.info("rid=%s %s %s -> %s %.0fms", rid, request.method, request.url.path,
                 resp.status_code, dur)

    # security headers
    resp.headers["X-Request-ID"] = rid
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
            "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self' https://nominatim.openstreetmap.org; "
            "frame-ancestors 'none'; base-uri 'self'")
    if settings.env == "production":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Consistent, human-readable validation errors (never raw stack traces)."""
    errors = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "detail": errors[0]["message"] if errors else "Validation error",
        "errors": errors,
        "request_id": getattr(request.state, "request_id", None)})


app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(orgs.router)
app.include_router(orgs.rules_router)
app.include_router(dashboard.router)
app.include_router(dashboard.misc_router)
app.include_router(admin_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.env}


@app.get("/api/ready")
def ready():
    """Readiness probe: DB, AI service, Redis (when configured)."""
    import httpx
    checks = {}
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
    try:
        r = httpx.get(f"{settings.ai_service_url}/health", timeout=3)
        checks["ai_service"] = r.json().get("model", "ok") if r.status_code == 200 else "error"
    except Exception:
        checks["ai_service"] = "unreachable (reports fall back to manual review)"
    if settings.job_backend == "redis":
        try:
            import redis as _r
            _r.from_url(settings.redis_url).ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unreachable"
    healthy = checks.get("database") == "ok"
    return JSONResponse({"ready": healthy, "checks": checks}, status_code=200 if healthy else 503)


# create tables if migrations haven't run (dev convenience; alembic in prod)
Base.metadata.create_all(bind=engine)

# ---- serve built SPA ----
_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", settings.frontend_dist))
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = os.path.join(_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_dist, "index.html"))
