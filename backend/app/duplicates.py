"""Pluggable duplicate-detection architecture.

Analyzers implement `find(db, report) -> list[DuplicateCandidate]`. The default
deployment uses GeoTextAnalyzer (no heavy models). Image/video-embedding
analyzers can be added later by registering another analyzer here — the report
model and API do not change: candidates are surfaced for HUMAN review; nothing
is ever auto-deleted or auto-merged.

Enable/disable via CL_DUPLICATE_ANALYZERS (comma list, default "geo_text").
"""
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session as DBSession

from .config import settings
from .models import OPEN_STATUSES, Report


@dataclass
class DuplicateCandidate:
    report: Report
    score: float           # 0..1 — probability-ish, analyzer-specific
    analyzer: str
    reason: str


class DuplicateAnalyzer(ABC):
    name = "base"

    @abstractmethod
    def find(self, db: DBSession, report: Report) -> List[DuplicateCandidate]: ...


def _haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class GeoTextAnalyzer(DuplicateAnalyzer):
    """Default analyzer: geographic proximity + Jaccard text overlap + category
    + configurable time window. Zero external dependencies."""
    name = "geo_text"

    def find(self, db: DBSession, report: Report) -> List[DuplicateCandidate]:
        if report.latitude is None or report.longitude is None:
            return []
        window = datetime.now(timezone.utc) - timedelta(days=settings.duplicate_window_days)
        near = (db.query(Report)
                  .filter(Report.id != report.id,
                          Report.created_at >= window,
                          Report.status.in_(OPEN_STATUSES),
                          Report.latitude.between(report.latitude - 0.01, report.latitude + 0.01),
                          Report.longitude.between(report.longitude - 0.01, report.longitude + 0.01))
                  .limit(200).all())
        words = set(w for w in (report.title + " " + report.description).lower().split() if len(w) > 3)
        out: List[DuplicateCandidate] = []
        for other in near:
            dist = _haversine_m(report.latitude, report.longitude, other.latitude, other.longitude)
            if dist > settings.duplicate_radius_m:
                continue
            ow = set(w for w in (other.title + " " + other.description).lower().split() if len(w) > 3)
            jaccard = len(words & ow) / max(1, len(words | ow)) if words and ow else 0.0
            same_cat = bool(report.user_category and
                            report.user_category == (other.user_category or other.category))
            score = min(1.0, 0.3 * (1 - dist / max(1, settings.duplicate_radius_m))
                        + 0.5 * jaccard + (0.3 if same_cat else 0))
            if jaccard > 0.25 or (same_cat and dist < settings.duplicate_radius_m):
                out.append(DuplicateCandidate(
                    report=other, score=round(score, 2), analyzer=self.name,
                    reason=f"{int(dist)}m away, {int(jaccard*100)}% text overlap"
                           + (", same category" if same_cat else "")))
        out.sort(key=lambda c: -c.score)
        return out[:5]


class ImageHashAnalyzer(DuplicateAnalyzer):
    """Visual near-duplicate analyzer using 64-bit perceptual hashes computed
    at upload time (no heavy embedding model). Catches re-uploaded or
    re-recorded evidence of the same scene."""
    name = "image_hash"

    def find(self, db: DBSession, report: Report) -> List[DuplicateCandidate]:
        from .integrity import phash_distance
        from .models import ReportMedia
        my_hashes = [m.phash for m in report.media if m.phash]
        if not my_hashes:
            return []
        window = datetime.now(timezone.utc) - timedelta(days=settings.duplicate_window_days * 4)
        others = (db.query(ReportMedia).join(Report, Report.id == ReportMedia.report_id)
                    .filter(ReportMedia.phash.isnot(None),
                            ReportMedia.report_id != report.id,
                            Report.created_at >= window)
                    .limit(1000).all())
        best: dict[str, tuple[int, ReportMedia]] = {}
        for om in others:
            d = min(phash_distance(h, om.phash) for h in my_hashes)
            if d <= 12 and (om.report_id not in best or d < best[om.report_id][0]):
                best[om.report_id] = (d, om)
        out = []
        for rid, (d, om) in best.items():
            other = db.get(Report, rid)
            if not other:
                continue
            score = round(1.0 - d / 16.0, 2)   # d=0 -> 1.0, d=12 -> 0.25
            out.append(DuplicateCandidate(
                report=other, score=score, analyzer=self.name,
                reason=f"visual similarity {int((1 - d/64)*100)}% (hash distance {d})"))
        out.sort(key=lambda c: -c.score)
        return out[:5]


class VideoEmbeddingAnalyzer(DuplicateAnalyzer):
    """Video near-duplicate analyzer using multi-frame perceptual signatures.

    At upload time we sample N frames across each video and store their
    perceptual hashes (report_media.frame_sigs). Two videos of the same scene
    — even re-recorded from a slightly different angle or trimmed differently —
    share visually similar frames; a single poster-frame hash misses those.

    Matching: best-pair frame distance (any of mine vs any of theirs) plus a
    coverage bonus when MULTIPLE frame pairs match (whole-video similarity,
    not one lucky frame). Candidates are surfaced for HUMAN review only."""
    name = "video_embedding"

    FRAME_MATCH_T = 14        # phash distance for "same scene" (frames differ more than stills)
    MIN_SCORE = 0.5

    def find(self, db: DBSession, report: Report) -> List[DuplicateCandidate]:
        import json as _json
        from .integrity import phash_distance
        from .models import ReportMedia

        mine: List[str] = []
        for m in report.media:
            if m.frame_sigs:
                try:
                    mine.extend(_json.loads(m.frame_sigs))
                except Exception:
                    pass
        if not mine:
            return []

        window = datetime.now(timezone.utc) - timedelta(days=settings.duplicate_window_days * 4)
        others = (db.query(ReportMedia).join(Report, Report.id == ReportMedia.report_id)
                    .filter(ReportMedia.frame_sigs.isnot(None),
                            ReportMedia.report_id != report.id,
                            Report.created_at >= window)
                    .limit(500).all())

        best: dict[str, tuple[float, int, int]] = {}   # report_id -> (score, best_d, pairs)
        for om in others:
            try:
                theirs = _json.loads(om.frame_sigs)
            except Exception:
                continue
            if not theirs:
                continue
            dists = [phash_distance(a, b) for a in mine for b in theirs]
            best_d = min(dists)
            if best_d > self.FRAME_MATCH_T:
                continue
            pairs = sum(1 for d in dists if d <= self.FRAME_MATCH_T)
            coverage = min(1.0, pairs / max(1, min(len(mine), len(theirs))))
            score = round(min(1.0, (1.0 - best_d / 24.0) * 0.7 + coverage * 0.3), 2)
            if score < self.MIN_SCORE:
                continue
            if om.report_id not in best or score > best[om.report_id][0]:
                best[om.report_id] = (score, best_d, pairs)

        out = []
        for rid, (score, d, pairs) in best.items():
            other = db.get(Report, rid)
            if not other:
                continue
            out.append(DuplicateCandidate(
                report=other, score=score, analyzer=self.name,
                reason=f"video frame similarity: {pairs} matching frame pair(s), "
                       f"closest distance {d}"))
        out.sort(key=lambda c: -c.score)
        return out[:5]


_REGISTRY = {
    "geo_text": GeoTextAnalyzer,
    "image_hash": ImageHashAnalyzer,
    "video_embedding": VideoEmbeddingAnalyzer,
}


def get_analyzers() -> List[DuplicateAnalyzer]:
    names = [n.strip() for n in
             getattr(settings, "duplicate_analyzers", "geo_text").split(",") if n.strip()]
    return [_REGISTRY[n]() for n in names if n in _REGISTRY]


def find_duplicates(db: DBSession, report: Report) -> List[DuplicateCandidate]:
    """Run all configured analyzers; merge + dedupe candidates by report id."""
    seen, merged = set(), []
    for analyzer in get_analyzers():
        for cand in analyzer.find(db, report):
            if cand.report.id not in seen:
                seen.add(cand.report.id)
                merged.append(cand)
    merged.sort(key=lambda c: -c.score)
    return merged


def best_duplicate(db: DBSession, report: Report) -> Optional[Report]:
    cands = find_duplicates(db, report)
    return cands[0].report if cands else None
