"""Protected local activation state.

Persists the imported license, the last-seen date (clock-rollback detection) and
demo counters. Integrity is protected by an HMAC keyed on the machine fingerprint,
so a state file copied to another machine (or hand-edited) is detected as tampered.
On Windows the blob is additionally wrapped with DPAPI when available.

This is deliberately *tamper-evident + machine-bound*, not a secrecy vault: the
authoritative trust anchor is the Ed25519 signature on the license itself, which a
customer cannot forge without the vendor private key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path

from zenith.core import paths


def _dpapi_protect(data: bytes) -> bytes:  # pragma: no cover - Windows only
    try:
        import win32crypt  # type: ignore

        return b"DPAPI1" + win32crypt.CryptProtectData(data, "ZenithLicense", None, None, None, 0)
    except Exception:
        return data


def _dpapi_unprotect(data: bytes) -> bytes:  # pragma: no cover - Windows only
    if data.startswith(b"DPAPI1"):
        try:
            import win32crypt  # type: ignore

            _, out = win32crypt.CryptUnprotectData(data[6:], None, None, None, 0)
            return out
        except Exception:
            return data
    return data


@dataclass
class ActivationState:
    activation_key: str | None = None       # SignedLicense.to_key()
    activated_at: str | None = None         # ISO date of first activation
    last_seen_date: str | None = None       # for clock-rollback detection
    demo_invoice_count: int = 0
    demo_product_count: int = 0
    history: list[dict] = field(default_factory=list)   # audit of activations/transfers

    def record(self, event: str, detail: str = "") -> None:
        self.history.append({"event": event, "detail": detail, "date": date.today().isoformat()})


class ActivationStore:
    """Reads/writes the machine-bound, integrity-protected activation state."""

    def __init__(self, machine_fp: str, path: Path | None = None):
        self._machine_fp = machine_fp
        self._path = path or (paths.license_dir() / "activation.dat")

    # -- integrity ---------------------------------------------------------
    def _mac(self, payload: bytes) -> str:
        return hmac.new(self._machine_fp.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # -- io ----------------------------------------------------------------
    def load(self) -> ActivationState:
        if not self._path.exists():
            return ActivationState()
        try:
            raw = _dpapi_unprotect(self._path.read_bytes())
            envelope = json.loads(raw.decode("utf-8"))
            payload_b64 = envelope["payload"]
            payload = base64.b64decode(payload_b64)
            if not hmac.compare_digest(envelope.get("mac", ""), self._mac(payload)):
                # Tampered or copied from another machine -> ignore stored state.
                return ActivationState()
            data = json.loads(payload.decode("utf-8"))
            return ActivationState(**data)
        except Exception:
            return ActivationState()

    def save(self, state: ActivationState) -> None:
        payload = json.dumps(asdict(state), separators=(",", ":")).encode("utf-8")
        envelope = json.dumps(
            {"payload": base64.b64encode(payload).decode("ascii"), "mac": self._mac(payload)}
        ).encode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(_dpapi_protect(envelope))
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def clear(self) -> None:
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
