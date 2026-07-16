"""Programmatic license issuing (used by the vendor CLI and tests)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from zenith.licensing.model import License, LicenseType, SignedLicense
from zenith.licensing.signing import sign_license
from zenith.profiles import is_valid_profile


def build_license(
    *,
    customer_name: str,
    business_name: str,
    profile_code: str,
    license_type: LicenseType,
    machine_fingerprint: str,
    max_users: int = 3,
    max_branches: int = 1,
    enabled_modules: list[str] | None = None,
    duration_days: int | None = None,
    perpetual: bool = False,
    start_date: date | None = None,
    license_id: str | None = None,
) -> License:
    """Construct (unsigned) license payload with validation.

    Demo licenses are always time-limited. Full licenses may be perpetual or a
    subscription (``duration_days``).
    """
    if not is_valid_profile(profile_code):
        raise ValueError(f"Unknown profile code: {profile_code}")

    start = start_date or date.today()
    if license_type == LicenseType.DEMO:
        if perpetual:
            raise ValueError("Demo licenses cannot be perpetual")
        days = duration_days if duration_days is not None else 15
        expiry = (start + timedelta(days=days)).isoformat()
    else:  # FULL
        if perpetual:
            expiry = None
        else:
            if duration_days is None:
                raise ValueError("Full subscription requires duration_days or perpetual=True")
            expiry = (start + timedelta(days=duration_days)).isoformat()

    return License(
        license_id=license_id or f"ZBE-{uuid.uuid4().hex[:12].upper()}",
        customer_name=customer_name,
        business_name=business_name,
        profile_code=profile_code,
        license_type=license_type.value,
        machine_fingerprint=machine_fingerprint,
        issue_date=date.today().isoformat(),
        start_date=start.isoformat(),
        expiry_date=expiry,
        max_users=max_users,
        max_branches=max_branches,
        enabled_modules=sorted(enabled_modules or []),
    )


def issue_signed(payload: License, private_key: Ed25519PrivateKey) -> SignedLicense:
    return sign_license(payload, private_key)
