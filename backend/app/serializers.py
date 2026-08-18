"""Convert ORM objects to API shapes with privacy controls baked in."""
from typing import Optional

from .config import settings
from .models import Report, ReportAIAnalysis, ReportMedia

_SENSITIVE = {c.strip() for c in settings.sensitive_categories.split(",") if c.strip()}


def _fuzz(coord: Optional[float], category: Optional[str]) -> Optional[float]:
    """Configurable coordinate fuzzing; stronger for sensitive categories
    (schools, safety incidents) to protect people and places."""
    if coord is None:
        return None
    decimals = (settings.sensitive_coord_decimals if category in _SENSITIVE
                else settings.public_coord_decimals)
    return round(coord, decimals)


def media_out(m: ReportMedia) -> dict:
    return {
        "id": m.id, "kind": m.kind, "content_type": m.content_type,
        "size_bytes": m.size_bytes, "duration_s": m.duration_s,
        "has_thumb": bool(m.thumb_key), "created_at": m.created_at,
    }


def ai_out(a: Optional[ReportAIAnalysis]) -> Optional[dict]:
    if not a:
        return None
    conf = a.confidence or 0
    band = ("high" if conf >= settings.ai_conf_high else
            "low" if conf < settings.ai_conf_low else "medium")
    return {
        "category": a.category, "issue_type": a.issue_type, "severity": a.severity,
        "confidence": a.confidence, "confidence_band": band, "urgency": a.urgency,
        "responsible_organization": a.responsible_organization,
        "organization_type": a.organization_type, "reasoning": a.reasoning,
        "model_name": a.model_name, "model_version": a.model_version,
        "analyzer": a.analyzer, "input_kind": a.input_kind,
        "duration_ms": a.duration_ms, "success": a.success,
        "frames_analyzed": a.frames_analyzed,
        "corrected": a.corrected_by is not None, "created_at": a.created_at,
    }


def approx_address(addr: Optional[str]) -> Optional[str]:
    return addr


def report_public(r: Report, dup_code: Optional[str] = None) -> dict:
    """Public serialization: reporter identity and internal comments are excluded."""
    return {
        "id": r.id, "public_code": r.public_code, "title": r.title,
        "description": r.description, "category": r.category, "issue_type": r.issue_type,
        "severity": r.severity, "status": r.status.value, "city": r.city,
        "human_confirmed": r.human_confirmed,
        "processing_state": r.processing_state,
        "latitude": _fuzz(r.latitude, r.category),
        "longitude": _fuzz(r.longitude, r.category),
        "address": approx_address(r.address),
        "organization_name": r.organization.name if r.organization else None,
        "is_demo": r.is_demo, "created_at": r.created_at, "resolved_at": r.resolved_at,
        "cluster_id": r.cluster_id,
        "resolution_confirmed": r.resolution_confirmed,
        "resolution_check_score": r.resolution_check_score,
        "resolution_check_notes": r.resolution_check_notes,
        "media": [media_out(m) for m in r.media if m.kind != "resolution" or r.status.value == "resolved"],
        "ai": ai_out(r.ai),
        "duplicate_of_code": dup_code,
    }


def report_privileged(r: Report, dup_code: Optional[str] = None) -> dict:
    d = report_public(r, dup_code)
    d.update({
        "reporter_name": r.reporter.name if r.reporter else None,
        "reporter_email": r.reporter.email if r.reporter else None,
        "comments": r.comments,
        "is_flagged": r.is_flagged, "flag_reason": r.flag_reason,
        "user_category": r.user_category,
        "routing_state": r.routing_state,
        "processing_error": r.processing_error,
        "integrity_score": r.integrity_score,
        "integrity_notes": r.integrity_notes,
        "acknowledged_at": r.acknowledged_at,
        "latitude": r.latitude, "longitude": r.longitude,   # exact coords for staff
    })
    return d
