"""High-level license service used by the application.

Ties verification + protected storage together and exposes a single ``status()``
the whole app consults on startup and at enforcement points. Handles:

* importing a license (activation key or ``.zlic`` file),
* machine + profile + signature enforcement (delegated to the verifier),
* clock-rollback detection using the stored ``last_seen_date``,
* demo expiry behaviour (post-expiry the app enters read-only mode -- customer
  data is never destroyed).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date

from zenith.licensing.machine import machine_fingerprint
from zenith.licensing.model import License, LicenseType, SignedLicense
from zenith.licensing.storage import ActivationStore
from zenith.licensing.verifier import verify_license


class LicenseState(str, enum.Enum):
    NOT_ACTIVATED = "not_activated"
    ACTIVE = "active"
    EXPIRED = "expired"          # demo/subscription expired -> read-only
    INVALID = "invalid"          # signature/machine/profile failure
    CLOCK_ROLLBACK = "clock_rollback"


@dataclass
class LicenseStatus:
    state: LicenseState
    reason_key: str
    license: License | None = None
    days_remaining: int | None = None
    read_only: bool = False

    @property
    def is_usable(self) -> bool:
        """Can the app perform normal transactions?"""
        return self.state == LicenseState.ACTIVE

    @property
    def can_open(self) -> bool:
        """Can the user log in at all (even if read-only)?"""
        return self.state in (LicenseState.ACTIVE, LicenseState.EXPIRED)


class LicenseService:
    def __init__(self, machine_fp: str | None = None, store: ActivationStore | None = None):
        self._machine_fp = machine_fp or machine_fingerprint()
        self._store = store or ActivationStore(self._machine_fp)

    @property
    def machine_fp(self) -> str:
        return self._machine_fp

    # -- import ------------------------------------------------------------
    def import_key(self, activation_key: str, expected_profile: str | None, today: date | None = None) -> LicenseStatus:
        try:
            signed = SignedLicense.from_key(activation_key)
        except Exception:
            return LicenseStatus(LicenseState.INVALID, "license.error.malformed")
        return self._import(signed, expected_profile, today)

    def import_file(self, text: str, expected_profile: str | None, today: date | None = None) -> LicenseStatus:
        try:
            signed = SignedLicense.from_file_json(text)
        except Exception:
            return LicenseStatus(LicenseState.INVALID, "license.error.malformed")
        return self._import(signed, expected_profile, today)

    def _import(self, signed: SignedLicense, expected_profile: str | None, today: date | None) -> LicenseStatus:
        today = today or date.today()
        result = verify_license(
            signed,
            machine_fp=self._machine_fp,
            expected_profile=expected_profile,
            today=today,
        )
        if result.failed:
            state = self.load_state()
            state.record("activation_failed", result.reason_key)
            self._store.save(state)
            return LicenseStatus(LicenseState.INVALID, result.reason_key, license=result.license)

        state = self.load_state()
        state.activation_key = signed.to_key()
        if not state.activated_at:
            state.activated_at = today.isoformat()
        state.last_seen_date = today.isoformat()
        state.record("activated", signed.payload.license_id)
        self._store.save(state)
        return self.status(expected_profile=expected_profile, today=today)

    # -- status ------------------------------------------------------------
    def load_state(self):
        return self._store.load()

    def status(self, expected_profile: str | None = None, today: date | None = None) -> LicenseStatus:
        today = today or date.today()
        state = self.load_state()
        if not state.activation_key:
            return LicenseStatus(LicenseState.NOT_ACTIVATED, "license.status.not_activated")

        try:
            signed = SignedLicense.from_key(state.activation_key)
        except Exception:
            return LicenseStatus(LicenseState.INVALID, "license.error.malformed")

        # Clock-rollback: system date earlier than the last date we recorded.
        if state.last_seen_date:
            last_seen = date.fromisoformat(state.last_seen_date)
            if today < last_seen:
                state.record("clock_rollback", f"{today} < {last_seen}")
                self._store.save(state)
                return LicenseStatus(
                    LicenseState.CLOCK_ROLLBACK, "license.error.clock_rollback",
                    license=signed.payload, read_only=True,
                )

        result = verify_license(
            signed, machine_fp=self._machine_fp,
            expected_profile=expected_profile, today=today,
        )
        lic = result.license

        if result.failed:
            # Expiry is a soft state (read-only), everything else is hard-invalid.
            if result.reason_key == "license.error.expired":
                return LicenseStatus(
                    LicenseState.EXPIRED, "license.status.expired",
                    license=lic, days_remaining=0, read_only=True,
                )
            return LicenseStatus(LicenseState.INVALID, result.reason_key, license=lic)

        # Valid: advance last_seen, compute days remaining.
        if not state.last_seen_date or today > date.fromisoformat(state.last_seen_date):
            state.last_seen_date = today.isoformat()
            self._store.save(state)

        days = None
        expiry = lic.parsed_expiry()
        if expiry is not None:
            days = (expiry - today).days
        return LicenseStatus(LicenseState.ACTIVE, "license.status.active", license=lic, days_remaining=days)

    # -- transfer ----------------------------------------------------------
    def begin_transfer(self) -> str:
        """Record a transfer request and return the machine request code.

        The vendor then issues a new machine-bound license for the target
        machine. There is deliberately no customer-side path to mint new
        machine licenses.
        """
        from zenith.licensing.machine import request_code

        state = self.load_state()
        state.record("transfer_requested", self._machine_fp[:16])
        self._store.save(state)
        return request_code()
