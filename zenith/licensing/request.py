"""Machine-request package (``.zreq``) -- customer-safe, contains no secrets.

The customer application produces one of these so the vendor can issue a
machine-bound, profile-bound license. It carries only public, non-sensitive
information (a hashed machine fingerprint, the selected profile, app version and
a timestamp). Both the customer app (to create) and the vendor tool (to parse)
share this module; it never touches the private signing key.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

REQUEST_FORMAT_VERSION = 1
FINGERPRINT_HEX_LEN = 64  # SHA-256 hex


class RequestError(ValueError):
    """Raised for a malformed / unsupported request package."""


@dataclass
class MachineRequest:
    machine_fingerprint: str          # 64-hex SHA-256 (no raw hardware data)
    profile_code: str
    app_version: str = ""
    business_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    request_version: int = REQUEST_FORMAT_VERSION

    # ---- validation -----------------------------------------------------
    def validate(self) -> None:
        from zenith.profiles import is_valid_profile

        if self.request_version != REQUEST_FORMAT_VERSION:
            raise RequestError(f"Unsupported request version: {self.request_version}")
        fp = (self.machine_fingerprint or "").strip().lower()
        if len(fp) != FINGERPRINT_HEX_LEN or any(c not in "0123456789abcdef" for c in fp):
            raise RequestError("Machine fingerprint must be 64 hexadecimal characters")
        if not is_valid_profile(self.profile_code):
            raise RequestError(f"Unknown profile code: {self.profile_code}")

    @property
    def is_valid(self) -> bool:
        try:
            self.validate()
            return True
        except RequestError:
            return False

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def to_file_json(self) -> str:
        return json.dumps(
            {"format": "zenith-request", "version": REQUEST_FORMAT_VERSION, "request": self.to_dict()},
            indent=2, ensure_ascii=False,
        )

    def to_code(self) -> str:
        """Compact single-line request code (base64url of the canonical JSON)."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "ZREQ1." + base64.urlsafe_b64encode(payload).decode("ascii")

    # ---- parsing --------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "MachineRequest":
        try:
            return cls(
                machine_fingerprint=str(d["machine_fingerprint"]).strip().lower(),
                profile_code=str(d["profile_code"]).strip(),
                app_version=str(d.get("app_version", "")),
                business_name=str(d.get("business_name", "")),
                created_at=str(d.get("created_at", "")),
                request_version=int(d.get("request_version", REQUEST_FORMAT_VERSION)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RequestError(f"Malformed request: {exc}") from exc

    @classmethod
    def from_code(cls, code: str) -> "MachineRequest":
        code = (code or "").strip().replace("\n", "").replace(" ", "")
        if not code.startswith("ZREQ1."):
            raise RequestError("Not a Zenith request code")
        try:
            payload = base64.urlsafe_b64decode(code[len("ZREQ1."):].encode("ascii"))
            return cls.from_dict(json.loads(payload))
        except (ValueError, json.JSONDecodeError) as exc:
            raise RequestError(f"Invalid request code: {exc}") from exc

    @classmethod
    def from_file_json(cls, text: str) -> "MachineRequest":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RequestError(f"Invalid request file: {exc}") from exc
        if obj.get("format") != "zenith-request":
            raise RequestError("Not a Zenith request file")
        return cls.from_dict(obj.get("request", {}))


def build_request(machine_fingerprint: str, profile_code: str, *,
                  app_version: str = "", business_name: str = "") -> MachineRequest:
    req = MachineRequest(
        machine_fingerprint=(machine_fingerprint or "").strip().lower(),
        profile_code=profile_code, app_version=app_version, business_name=business_name,
    )
    req.validate()
    return req
