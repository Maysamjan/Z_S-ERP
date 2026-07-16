"""Customer-side license verification.

Pure, side-effect-free checks: signature, machine binding, profile binding,
edition, dates and limits. Clock-rollback detection lives in the service layer
(it needs persistent "last seen" state). ``today`` and ``machine_fp`` are injected
so the whole thing is deterministically testable.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date

from cryptography.exceptions import InvalidSignature

from zenith.licensing.keys import load_public_key
from zenith.licensing.model import License, LicenseType, SignedLicense
from zenith.profiles import is_valid_profile


@dataclass
class LicenseVerification:
    ok: bool
    reason_key: str = "license.ok"
    license: License | None = None

    @property
    def failed(self) -> bool:
        return not self.ok


def _fail(reason_key: str, lic: License | None = None) -> LicenseVerification:
    return LicenseVerification(ok=False, reason_key=reason_key, license=lic)


def verify_license(
    signed: SignedLicense,
    *,
    machine_fp: str,
    expected_profile: str | None,
    today: date,
    public_key_pem: bytes | None = None,
) -> LicenseVerification:
    """Verify a signed license against this machine, profile and date.

    ``expected_profile`` is the profile selected during setup/installation; a
    license for a different profile is rejected (``license.error.profile``).
    Pass ``None`` to skip the profile-match check (e.g. when first importing a
    license before setup has recorded the selected profile).
    """
    lic = signed.payload

    # 1. Signature (integrity + authenticity). Any tampering fails here.
    try:
        pub = load_public_key(public_key_pem)
        pub.verify(base64.b64decode(signed.signature_b64), lic.canonical_bytes())
    except (InvalidSignature, ValueError, TypeError):
        return _fail("license.error.signature", lic)

    # 2. Structural validity of the profile code.
    if not is_valid_profile(lic.profile_code):
        return _fail("license.error.profile", lic)

    # 3. Machine binding.
    if lic.machine_fingerprint != machine_fp:
        return _fail("license.error.machine", lic)

    # 4. Profile binding (installer/setup selection must match license).
    if expected_profile is not None and lic.profile_code != expected_profile:
        return _fail("license.error.profile", lic)

    # 5. Edition sanity.
    if lic.license_type not in (LicenseType.DEMO.value, LicenseType.FULL.value):
        return _fail("license.error.generic", lic)

    # 6. Dates.
    if today < lic.parsed_start():
        return _fail("license.error.not_started", lic)
    expiry = lic.parsed_expiry()
    if expiry is not None and today > expiry:
        return _fail("license.error.expired", lic)
    # Only a Full license may be perpetual.
    if expiry is None and lic.license_type != LicenseType.FULL.value:
        return _fail("license.error.generic", lic)

    # 7. Limit sanity (non-negative).
    if lic.max_users < 1 or lic.max_branches < 1:
        return _fail("license.error.limit", lic)

    return LicenseVerification(ok=True, reason_key="license.ok", license=lic)
