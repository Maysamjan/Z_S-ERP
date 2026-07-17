"""License history: search, filter, sort, status refresh, local revoke."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from vendor_tools.license_manager.models.db import LicenseRecord
from vendor_tools.license_manager.services.audit import audit


def search(session: Session, *, term: str = "", profile: str | None = None,
           license_type: str | None = None, status: str | None = None,
           newest_first: bool = True) -> list[LicenseRecord]:
    q = select(LicenseRecord)
    term = (term or "").strip()
    if term:
        like = f"%{term}%"
        q = q.where(or_(
            LicenseRecord.customer_name.ilike(like),
            LicenseRecord.business_name.ilike(like),
            LicenseRecord.phone.ilike(like),
            LicenseRecord.license_id.ilike(like),
            LicenseRecord.machine_fingerprint.ilike(like),
        ))
    if profile:
        q = q.where(LicenseRecord.profile_code == profile)
    if license_type:
        q = q.where(LicenseRecord.license_type == license_type)
    if status:
        q = q.where(LicenseRecord.status == status)
    q = q.order_by(LicenseRecord.created_at.desc() if newest_first else LicenseRecord.created_at.asc())
    return list(session.scalars(q))


def get(session: Session, license_id: str) -> LicenseRecord | None:
    return session.scalar(select(LicenseRecord).where(LicenseRecord.license_id == license_id))


def refresh_statuses(session: Session, today: date | None = None) -> int:
    """Mark time-expired licenses as expired (does not touch replaced/revoked/test)."""
    today = today or date.today()
    changed = 0
    for rec in session.scalars(select(LicenseRecord).where(LicenseRecord.status == "active")):
        if rec.expiry_date and date.fromisoformat(rec.expiry_date) < today:
            rec.status = "expired"
            changed += 1
    return changed


def revoke_local(session: Session, license_id: str, reason: str, owner: str = "") -> LicenseRecord:
    """Mark a license revoked in the OWNER'S records only.

    Note: a fully offline customer installation cannot learn about this local
    revocation unless a signed revocation list or replacement license is sent to
    it. This never claims remote revocation.
    """
    rec = get(session, license_id)
    if rec is None:
        raise ValueError("License not found")
    rec.status = "revoked_local"
    rec.reason = reason
    audit(session, "license_revoked_local", owner=owner, license_id=license_id,
          customer=rec.customer_name, profile=rec.profile_code, result="ok", reason=reason)
    return rec
