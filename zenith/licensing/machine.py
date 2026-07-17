"""Machine fingerprinting.

Builds a stable, privacy-conscious fingerprint from several system values and
stores only its SHA-256 hash -- never the raw hardware identifiers. On Windows it
prefers the registry ``MachineGuid`` plus BIOS/board identifiers; elsewhere it
falls back to platform values so the flow is exercisable in dev/CI.

Tests and deterministic environments may set ``ZENITH_MACHINE_ID`` to force a
known fingerprint. This is intentional: it lets the license test-suite bind and
mismatch machines deterministically without real hardware.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import uuid


def _windows_identifiers() -> list[str]:
    ids: list[str] = []
    try:  # pragma: no cover - Windows only
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            if guid:
                ids.append(f"machineguid:{guid}")
    except Exception:
        pass
    for query, tag in (
        (["wmic", "baseboard", "get", "serialnumber"], "board"),
        (["wmic", "bios", "get", "serialnumber"], "bios"),
        (["wmic", "diskdrive", "where", "index=0", "get", "serialnumber"], "disk"),
    ):
        try:  # pragma: no cover - Windows only
            out = subprocess.check_output(query, timeout=5, text=True, stderr=subprocess.DEVNULL)
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            if len(lines) >= 2 and lines[1].lower() not in ("", "to be filled by o.e.m."):
                ids.append(f"{tag}:{lines[1]}")
        except Exception:
            pass
    return ids


def _generic_identifiers() -> list[str]:
    ids: list[str] = []
    # MAC address of the primary interface (stable-ish; part of a blend, not sole).
    node = uuid.getnode()
    ids.append(f"node:{node:012x}")
    ids.append(f"platform:{platform.system()}-{platform.machine()}")
    # Linux machine-id if present (stable per install).
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                mid = fh.read().strip()
                if mid:
                    ids.append(f"machineid:{mid}")
                    break
        except OSError:
            continue
    return ids


def test_override_allowed() -> bool:
    """The ``ZENITH_MACHINE_ID`` fingerprint override is honored ONLY when an
    explicit automated-test flag is set. Production builds never set it, so the
    override cannot be used to bypass machine binding in production.
    """
    return os.environ.get("ZENITH_ALLOW_TEST_FINGERPRINT") == "1"


def raw_identifiers() -> list[str]:
    override = os.environ.get("ZENITH_MACHINE_ID")
    if override and test_override_allowed():
        return [f"override:{override.strip()}"]
    ids = _windows_identifiers() if os.name == "nt" else []
    ids += _generic_identifiers()
    return sorted(set(i for i in ids if i))


def machine_fingerprint() -> str:
    """Return a stable 64-hex-char SHA-256 fingerprint of this machine.

    Only the hash is ever persisted or embedded in a license; the raw hardware
    identifiers are discarded.
    """
    blob = "|".join(raw_identifiers()).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def request_code() -> str:
    """Human-friendly machine request code the customer sends to the vendor.

    Derived from the fingerprint; grouped into 5-char blocks for readability.
    The vendor binds the issued license to this exact fingerprint.
    """
    fp = machine_fingerprint()
    short = fp[:25].upper()
    return "-".join(short[i:i + 5] for i in range(0, 25, 5))
