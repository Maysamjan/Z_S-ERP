"""License payload model and canonical (de)serialization.

The signed unit is a canonical JSON encoding of the payload (sorted keys, no
whitespace). A signature over any other encoding is rejected, so the same bytes
are always reproduced for signing and verification.
"""

from __future__ import annotations

import base64
import enum
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone


LICENSE_FORMAT_VERSION = 1


class LicenseType(str, enum.Enum):
    DEMO = "DEMO"
    FULL = "FULL"


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass
class License:
    """A signed license payload.

    ``expiry_date`` is ``None`` for a perpetual Full license. All dates are ISO
    ``YYYY-MM-DD`` strings so the canonical form is unambiguous.
    """

    license_id: str
    customer_name: str
    business_name: str
    profile_code: str            # must equal one of ProfileCode values
    license_type: str            # LicenseType value
    machine_fingerprint: str     # SHA-256 hex of the bound machine
    issue_date: str
    start_date: str
    expiry_date: str | None      # None => perpetual (Full only)
    max_users: int
    max_branches: int
    enabled_modules: list[str]   # empty list => "all modules for the profile"
    license_version: int = LICENSE_FORMAT_VERSION

    # ---- canonical form -------------------------------------------------
    def canonical_bytes(self) -> bytes:
        """Deterministic bytes that get signed/verified."""
        data = asdict(self)
        # normalise: modules sorted, ensure list types
        data["enabled_modules"] = sorted(data.get("enabled_modules") or [])
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["enabled_modules"] = sorted(d.get("enabled_modules") or [])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "License":
        return cls(
            license_id=str(d["license_id"]),
            customer_name=str(d["customer_name"]),
            business_name=str(d["business_name"]),
            profile_code=str(d["profile_code"]),
            license_type=str(d["license_type"]),
            machine_fingerprint=str(d["machine_fingerprint"]),
            issue_date=str(d["issue_date"]),
            start_date=str(d["start_date"]),
            expiry_date=(None if d.get("expiry_date") in (None, "", "null") else str(d["expiry_date"])),
            max_users=int(d["max_users"]),
            max_branches=int(d["max_branches"]),
            enabled_modules=list(d.get("enabled_modules") or []),
            license_version=int(d.get("license_version", LICENSE_FORMAT_VERSION)),
        )

    # ---- helpers --------------------------------------------------------
    @property
    def is_perpetual(self) -> bool:
        return self.license_type == LicenseType.FULL.value and self.expiry_date is None

    def parsed_expiry(self) -> date | None:
        return None if self.expiry_date is None else date.fromisoformat(self.expiry_date)

    def parsed_start(self) -> date:
        return date.fromisoformat(self.start_date)


@dataclass
class SignedLicense:
    """A license payload plus its detached Ed25519 signature (base64)."""

    payload: License
    signature_b64: str

    # ---- activation-key form (compact single line) ----------------------
    def to_key(self) -> str:
        payload_b64 = base64.urlsafe_b64encode(self.payload.canonical_bytes()).decode("ascii")
        return f"ZBE1.{payload_b64}.{self.signature_b64}"

    @classmethod
    def from_key(cls, key: str) -> "SignedLicense":
        key = key.strip().replace("\n", "").replace(" ", "")
        parts = key.split(".")
        if len(parts) != 3 or parts[0] != "ZBE1":
            raise ValueError("Malformed activation key")
        payload_json = base64.urlsafe_b64decode(parts[1].encode("ascii"))
        payload = License.from_dict(json.loads(payload_json))
        return cls(payload=payload, signature_b64=parts[2])

    # ---- license-file form (.zlic JSON) ---------------------------------
    def to_file_json(self) -> str:
        return json.dumps(
            {
                "format": "zenith-license",
                "version": LICENSE_FORMAT_VERSION,
                "payload": self.payload.to_dict(),
                "signature": self.signature_b64,
            },
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_file_json(cls, text: str) -> "SignedLicense":
        obj = json.loads(text)
        if obj.get("format") != "zenith-license":
            raise ValueError("Not a Zenith license file")
        return cls(
            payload=License.from_dict(obj["payload"]),
            signature_b64=str(obj["signature"]),
        )
