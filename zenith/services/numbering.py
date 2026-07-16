"""Document-number generation.

Produces unique, human-readable document numbers (e.g. ``INV-000042``). Uniqueness
is also guaranteed by DB unique constraints; this just produces the next candidate.
"""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session


def next_number(session: Session, model, column, prefix: str, width: int = 6) -> str:
    count = session.scalar(select(func.count()).select_from(model)) or 0
    n = count + 1
    # ensure uniqueness in case of gaps/deletions
    while session.scalar(select(model).where(column == f"{prefix}-{n:0{width}d}")) is not None:
        n += 1
    return f"{prefix}-{n:0{width}d}"
