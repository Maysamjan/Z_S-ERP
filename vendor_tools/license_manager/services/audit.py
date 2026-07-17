"""Vendor audit log helper. Never records key material or full passwords."""

from __future__ import annotations

from sqlalchemy.orm import Session

from vendor_tools.license_manager.models.db import VendorAudit


def audit(session: Session, action: str, *, owner: str = "", license_id: str = "",
          customer: str = "", profile: str = "", result: str = "", reason: str = "") -> VendorAudit:
    entry = VendorAudit(
        owner_user=owner, action=action, license_id=license_id, customer=customer,
        profile=profile, result=result, reason=reason,
    )
    session.add(entry)
    return entry
