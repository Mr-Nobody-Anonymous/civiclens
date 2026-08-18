from sqlalchemy.orm import Session as DBSession

from .models import AuditLog


def audit(db: DBSession, user_id: str | None, action: str, entity: str = "",
          entity_id: str = "", detail: str = "", ip: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, entity=entity,
                    entity_id=entity_id, detail=detail, ip=ip))
    db.commit()
