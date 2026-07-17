"""License generation, renewal, replacement and profile-test bundle.

Every generated license is:
1. built as a canonical payload,
2. signed with the Ed25519 private key from the (unlocked) key store,
3. **immediately verified** with the exact verifier the customer ERP uses, and
4. recorded in the owner-only license history.

Machine binding and profile binding are always preserved -- there is no wildcard.
Renewal keeps the same machine + profile; changing either is a *replacement*.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from zenith.licensing import keys as _keys
from zenith.licensing.model import LicenseType, SignedLicense
from zenith.licensing.request import FINGERPRINT_HEX_LEN
from zenith.licensing.signing import sign_license
from zenith.licensing.verifier import verify_license, LicenseVerification
from zenith.profiles import ProfileCode, is_valid_profile
from zenith.vendor.license_issuer import build_license

from vendor_tools.license_manager.models.db import LicenseRecord
from vendor_tools.license_manager.services.audit import audit
from vendor_tools.license_manager.services.keystore import KeyStore


class GenerationError(Exception):
    pass


@dataclass
class LicenseInput:
    profile_code: str
    machine_fingerprint: str
    license_type: str = LicenseType.DEMO.value
    perpetual: bool = False
    duration_days: int | None = 30
    start_date: date | None = None
    max_users: int = 3
    max_branches: int = 1
    enabled_modules: list[str] = field(default_factory=list)
    customer_name: str = ""
    business_name: str = ""
    customer_id: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    notes: str = ""
    is_test: bool = False


@dataclass
class GenerationResult:
    signed: SignedLicense
    verification: LicenseVerification
    record: LicenseRecord

    @property
    def activation_key(self) -> str:
        return self.signed.to_key()


def _new_license_id() -> str:
    return f"ZBE-{uuid.uuid4().hex[:12].upper()}"


def validate_input(inp: LicenseInput) -> None:
    fp = (inp.machine_fingerprint or "").strip().lower()
    if len(fp) != FINGERPRINT_HEX_LEN or any(c not in "0123456789abcdef" for c in fp):
        raise GenerationError("Machine fingerprint must be 64 hexadecimal characters")
    if not is_valid_profile(inp.profile_code):
        raise GenerationError("Invalid business profile")
    if inp.license_type not in (LicenseType.DEMO.value, LicenseType.FULL.value):
        raise GenerationError("Invalid license type")
    if inp.max_users < 1:
        raise GenerationError("Maximum users must be at least 1")
    if inp.max_branches < 1:
        raise GenerationError("Maximum branches must be at least 1")
    if inp.license_type == LicenseType.DEMO.value:
        if inp.perpetual:
            raise GenerationError("Demo licenses cannot be perpetual")
        if not inp.duration_days or inp.duration_days <= 0:
            raise GenerationError("Demo duration must be a positive number of days")
    else:  # FULL
        if not inp.perpetual and (not inp.duration_days or inp.duration_days <= 0):
            raise GenerationError("Subscription duration must be positive, or choose perpetual")
    # module validity against the profile
    if inp.enabled_modules:
        from zenith.profiles import get_profile
        allowed = set(get_profile(inp.profile_code).enabled_modules)
        bad = [m for m in inp.enabled_modules if m not in allowed]
        if bad:
            raise GenerationError(f"Modules not valid for this profile: {', '.join(bad)}")


def _sign(session: Session, keystore: KeyStore, passphrase: str, inp: LicenseInput,
          *, license_id: str, renewed_from: str | None = None, replaced_from: str | None = None,
          reason: str = "", owner: str = "") -> GenerationResult:
    validate_input(inp)
    if not keystore.is_initialized():
        raise GenerationError("Signing key store is not initialized")
    if not keystore.matches_public_key(_keys.EMBEDDED_PUBLIC_KEY_PEM):
        raise GenerationError("Stored signing key does not match the application's public key")
    if session.scalar(select(LicenseRecord).where(LicenseRecord.license_id == license_id)):
        raise GenerationError("License ID already exists")

    private_key = keystore.load_private_key(passphrase)  # authenticates passphrase
    payload = build_license(
        customer_name=inp.customer_name, business_name=inp.business_name,
        profile_code=inp.profile_code, license_type=LicenseType(inp.license_type),
        machine_fingerprint=inp.machine_fingerprint.strip().lower(),
        max_users=inp.max_users, max_branches=inp.max_branches,
        enabled_modules=inp.enabled_modules or None,
        duration_days=inp.duration_days, perpetual=inp.perpetual,
        start_date=inp.start_date, license_id=license_id,
    )
    signed = sign_license(payload, private_key)

    # immediate verification with the customer's exact verifier + embedded key
    verification = verify_license(
        signed, machine_fp=payload.machine_fingerprint,
        expected_profile=payload.profile_code, today=date.today(),
        public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM,
    )
    if verification.failed:
        audit(session, "signature_failed", owner=owner, profile=inp.profile_code,
              result="fail", reason=verification.reason_key)
        raise GenerationError(f"Generated license failed self-verification: {verification.reason_key}")

    record = LicenseRecord(
        license_id=license_id, customer_id=inp.customer_id, customer_name=inp.customer_name,
        business_name=inp.business_name, phone=inp.phone, email=inp.email, address=inp.address,
        machine_fingerprint=payload.machine_fingerprint, profile_code=payload.profile_code,
        license_type=payload.license_type, is_perpetual=payload.is_perpetual,
        start_date=payload.start_date, expiry_date=payload.expiry_date,
        max_users=payload.max_users, max_branches=payload.max_branches,
        enabled_modules=json.dumps(payload.enabled_modules), activation_key=signed.to_key(),
        created_by=owner, renewed_from=renewed_from, replaced_from=replaced_from,
        reason=reason, notes=inp.notes, status="test" if inp.is_test else "active",
    )
    session.add(record)
    session.flush()
    action = "license_generated"
    if renewed_from:
        action = "license_renewed"
    elif replaced_from:
        action = "license_replaced"
    audit(session, action, owner=owner, license_id=license_id, customer=inp.customer_name,
          profile=inp.profile_code, result="ok", reason=reason)
    return GenerationResult(signed=signed, verification=verification, record=record)


def generate(session: Session, keystore: KeyStore, passphrase: str, inp: LicenseInput,
             owner: str = "") -> GenerationResult:
    return _sign(session, keystore, passphrase, inp, license_id=_new_license_id(), owner=owner)


def renew(session: Session, keystore: KeyStore, passphrase: str, old_license_id: str,
          changes: LicenseInput, owner: str = "") -> GenerationResult:
    old = session.scalar(select(LicenseRecord).where(LicenseRecord.license_id == old_license_id))
    if old is None:
        raise GenerationError("Original license not found")
    # renewal keeps machine + profile fixed
    changes.machine_fingerprint = old.machine_fingerprint
    changes.profile_code = old.profile_code
    result = _sign(session, keystore, passphrase, changes,
                   license_id=_new_license_id(), renewed_from=old_license_id, owner=owner)
    return result


def replace(session: Session, keystore: KeyStore, passphrase: str, old_license_id: str,
            replacement: LicenseInput, reason: str, owner: str = "") -> GenerationResult:
    if not (reason or "").strip():
        raise GenerationError("A reason is required for replacement")
    old = session.scalar(select(LicenseRecord).where(LicenseRecord.license_id == old_license_id))
    if old is None:
        raise GenerationError("Original license not found")
    result = _sign(session, keystore, passphrase, replacement,
                   license_id=_new_license_id(), replaced_from=old_license_id,
                   reason=reason, owner=owner)
    old.status = "replaced"
    session.flush()
    return result


def generate_test_bundle(session: Session, keystore: KeyStore, passphrase: str, *,
                         machine_fingerprint: str, duration_days: int = 30,
                         max_users: int = 3, max_branches: int = 1,
                         owner: str = "") -> dict[str, GenerationResult]:
    """Five separate, profile-bound Demo licenses (no wildcard)."""
    results: dict[str, GenerationResult] = {}
    for code in [c.value for c in ProfileCode]:
        inp = LicenseInput(
            profile_code=code, machine_fingerprint=machine_fingerprint,
            license_type=LicenseType.DEMO.value, duration_days=duration_days,
            max_users=max_users, max_branches=max_branches,
            customer_name="Profile Test", business_name=f"Test {code}", is_test=True,
        )
        results[code] = _sign(session, keystore, passphrase, inp,
                              license_id=_new_license_id(), owner=owner)
    audit(session, "test_bundle_generated", owner=owner, result="ok",
          reason=f"{len(results)} profiles")
    return results
