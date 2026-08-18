"""Organization routing engine.

The AI recommends a category; routing rules (organization_rules table)
map category (+optional keyword/city matches) to an organization.
Rules never silently finalise an assignment unless auto_assign is set —
otherwise the report lands in 'under_review' for a human to confirm.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from .models import Organization, OrganizationRule, Report


def route_report(db: DBSession, report: Report, ai_category: Optional[str],
                 text: str) -> Tuple[Optional[Organization], Optional[OrganizationRule]]:
    category = ai_category or report.category or report.user_category
    if not category:
        return None, None
    text_l = (text or "").lower()

    q = (db.query(OrganizationRule)
           .filter(OrganizationRule.is_active == True,  # noqa: E712
                   OrganizationRule.category == category)
           .order_by(OrganizationRule.priority.asc(), OrganizationRule.created_at.asc()))
    rules = q.all()

    scored: list = []
    for idx, rule in enumerate(rules):
        score = 0.0
        # city-specific rules beat national ones when they match
        if rule.city:
            if report.city and rule.city.lower() == report.city.lower():
                score += 10
            else:
                continue  # city rule for a different city: skip
        if rule.keywords:
            kws = [k.strip().lower() for k in rule.keywords.split(",") if k.strip()]
            hits = sum(1 for k in kws if k in text_l)
            if kws and hits == 0 and not rule.city:
                score -= 1  # generic keyword rule that didn't match
            score += hits * 2
        # deterministic tiebreak: lower priority number → earlier in list → higher score
        score += max(0.0, 5 - idx * 0.1)
        # skip rules pointing to disabled organizations — never route into a void
        org = db.get(Organization, rule.organization_id)
        if not org or not org.is_active:
            continue
        scored.append((score, idx, rule, org))

    if not scored:
        return None, None
    # deterministic: highest score wins; ties broken by rule order (priority, created_at)
    scored.sort(key=lambda t: (-t[0], t[1]))
    _score, _idx, best, org = scored[0]
    return org, best
