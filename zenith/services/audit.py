"""Audit logging helper.

Audit entries are append-only from the application's perspective: no service
exposes update/delete for ``AuditLog``. Normal users cannot edit them.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from zenith.db.models import AuditLog, User


def log(session: Session, action: str, *, actor: User | None = None,
        entity: str = "", entity_id: str | int = "", detail: str = "") -> AuditLog:
    entry = AuditLog(
        user_id=actor.id if actor else None,
        username=actor.username if actor else "",
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        detail=detail,
    )
    session.add(entry)
    return entry
