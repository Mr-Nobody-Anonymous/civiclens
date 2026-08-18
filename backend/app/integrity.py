"""Evidence Integrity Pipeline.

Computes trust signals for uploaded evidence WITHOUT accusing anyone:
  - sha256          exact-duplicate detection + immutable evidence chain
  - phash           perceptual hash (dHash 64-bit) for near-duplicate visuals
  - location        consistency between report pin and configured city
  - composite score 0..1 stored on the report; low scores queue human review

The output is always phrased as "requires additional verification", never
"fraud". Humans make the final call via the AI review queue.
"""
import hashlib
import logging
import math
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from .models import Report, ReportMedia

log = logging.getLogger("civiclens.integrity")

# rough city centers for location-consistency checks (must match CL_CITIES)
CITY_CENTERS = {
    "addis ababa": (9.0108, 38.7613), "adama": (8.5410, 39.2705),
    "bahir dar": (11.5936, 37.3908), "hawassa": (7.0504, 38.4762),
    "mekelle": (13.4967, 39.4697), "dire dawa": (9.5931, 41.8661),
    "gondar": (12.6075, 37.4661), "jimma": (7.6733, 36.8344),
}
CITY_RADIUS_KM = 40.0


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_phash(path: str) -> Optional[str]:
    """64-bit difference hash of an image (or extracted video thumbnail)."""
    try:
        from PIL import Image
        img = Image.open(path).convert("L").resize((9, 8), Image.LANCZOS)
        px = list(img.getdata())
        bits = 0
        for row in range(8):
            for col in range(8):
                bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
        return f"{bits:016x}"
    except Exception:
        return None


def phash_distance(a: str, b: str) -> int:
    """Hamming distance between two 64-bit hex phashes (0=identical, <=10 similar)."""
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 64


def _haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def location_consistency(report: Report) -> tuple[float, str]:
    """1.0 = pin matches the stated city; degrades with distance."""
    if report.latitude is None or not report.city:
        return 0.7, "No coordinates to verify against the city"
    center = CITY_CENTERS.get(report.city.strip().lower())
    if not center:
        return 0.8, f"No reference center for {report.city}"
    d = _haversine_km(report.latitude, report.longitude, *center)
    if d <= CITY_RADIUS_KM:
        return 1.0, f"Location within {report.city} ({d:.0f} km from center)"
    if d <= CITY_RADIUS_KM * 3:
        return 0.5, f"Location {d:.0f} km from {report.city} center — outside expected area"
    return 0.2, f"Location {d:.0f} km from {report.city} — strong mismatch"


def evaluate_report(db: DBSession, report: Report) -> tuple[float, list[str]]:
    """Composite integrity score + human-readable notes. Signals:
    exact-duplicate evidence, near-duplicate visuals, location consistency,
    evidence presence."""
    notes: list[str] = []
    score = 1.0

    # --- exact duplicate evidence (same file hash used in another report) ---
    for m in report.media:
        if not m.sha256:
            continue
        dup = (db.query(ReportMedia)
                 .filter(ReportMedia.sha256 == m.sha256,
                         ReportMedia.report_id != report.id).first())
        if dup:
            score -= 0.35
            notes.append(f"Evidence file identical to media in report {dup.report_id[:8]}…")
            break

    # --- near-duplicate visuals (perceptual hash) ---
    for m in report.media:
        if not m.phash:
            continue
        others = (db.query(ReportMedia)
                    .filter(ReportMedia.phash.isnot(None),
                            ReportMedia.report_id != report.id)
                    .limit(500).all())
        near = [o for o in others if phash_distance(m.phash, o.phash) <= 8]
        if near:
            score -= 0.15
            notes.append(f"Visually similar evidence found in {len(near)} other report(s)")
            break

    # --- location consistency ---
    loc_score, loc_note = location_consistency(report)
    score -= (1.0 - loc_score) * 0.4
    notes.append(loc_note)

    # --- evidence presence ---
    if not report.media:
        score -= 0.1
        notes.append("No visual evidence attached")

    score = max(0.0, min(1.0, round(score, 2)))
    return score, notes
