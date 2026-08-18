"""Prometheus metrics — zero-dependency exposition (text format 0.0.4).

Tracked:
  civiclens_http_requests_total{method,path,status}
  civiclens_http_request_seconds{path}            (histogram)
  civiclens_jobs_total{name,status}
  civiclens_job_seconds{name}                     (histogram)
  civiclens_ai_requests_total{outcome}
  civiclens_ai_seconds                            (histogram)
  civiclens_queue_depth                           (gauge, redis backend)
  civiclens_sla_escalations_total
  civiclens_worker_heartbeat_age_seconds          (gauge)
"""
import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict = defaultdict(float)
_hist_buckets = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
_hists: dict = defaultdict(lambda: {"sum": 0.0, "count": 0,
                                    "buckets": defaultdict(int)})


def _fmt_labels(labels: dict | None) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{str(v)[:80]}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


def inc(name: str, labels: dict | None = None, value: float = 1):
    with _lock:
        _counters[(name, _fmt_labels(labels))] += value


def observe(name: str, seconds: float, labels: dict | None = None):
    key = (name, _fmt_labels(labels))
    with _lock:
        h = _hists[key]
        h["sum"] += seconds
        h["count"] += 1
        for b in _hist_buckets:
            if seconds <= b:
                h["buckets"][b] += 1


def _normalize_path(path: str) -> str:
    """Collapse IDs so cardinality stays bounded."""
    parts = []
    for seg in path.split("/"):
        if len(seg) >= 16 and all(c in "0123456789abcdef-" for c in seg.lower()):
            parts.append(":id")
        elif seg.startswith("CL-"):
            parts.append(":code")
        else:
            parts.append(seg)
    return "/".join(parts)


def track_request(method: str, path: str, status: int, seconds: float):
    p = _normalize_path(path)
    inc("civiclens_http_requests_total", {"method": method, "path": p, "status": status})
    observe("civiclens_http_request_seconds", seconds, {"path": p})


def render() -> str:
    """Render all metrics + live gauges in Prometheus text format."""
    lines = []
    with _lock:
        for (name, labels), v in sorted(_counters.items()):
            lines.append(f"{name}{labels} {v}")
        for (name, labels), h in sorted(_hists.items()):
            cumulative = 0
            for b in _hist_buckets:
                cumulative += h["buckets"].get(b, 0)
                lb = labels[:-1] + f',le="{b}"}}' if labels else f'{{le="{b}"}}'
                lines.append(f"{name}_bucket{lb} {cumulative}")
            lb_inf = labels[:-1] + ',le="+Inf"}' if labels else '{le="+Inf"}'
            lines.append(f"{name}_bucket{lb_inf} {h['count']}")
            lines.append(f"{name}_sum{labels} {h['sum']:.4f}")
            lines.append(f"{name}_count{labels} {h['count']}")

    # live gauges
    try:
        from .config import settings
        if settings.job_backend == "redis":
            import redis
            r = redis.from_url(settings.redis_url, socket_timeout=1)
            lines.append(f"civiclens_queue_depth {r.llen('civiclens:jobs')}")
            hb = r.get("civiclens:worker:heartbeat")
            if hb:
                from datetime import datetime, timezone
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(hb.decode())).total_seconds()
                lines.append(f"civiclens_worker_heartbeat_age_seconds {age:.0f}")
    except Exception:
        pass
    try:
        from .db import SessionLocal
        from .models import Job, Report, OPEN_STATUSES
        from sqlalchemy import func
        db = SessionLocal()
        for status in ("queued", "running", "failed", "dead"):
            n = db.query(func.count(Job.id)).filter(Job.status == status).scalar() or 0
            lines.append(f'civiclens_jobs_gauge{{status="{status}"}} {n}')
        open_n = db.query(func.count(Report.id)).filter(Report.status.in_(OPEN_STATUSES)).scalar() or 0
        lines.append(f"civiclens_open_reports {open_n}")
        db.close()
    except Exception:
        pass
    return "\n".join(lines) + "\n"
