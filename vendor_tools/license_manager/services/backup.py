"""Vendor-side backup: history DB, settings, public key and the ENCRYPTED key file.

The private key is only ever included in its already-encrypted form (the key-store
envelope). The plaintext private key is never written to a backup.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from vendor_tools.license_manager import __version__
from vendor_tools.license_manager.models.db import vendor_data_dir


@dataclass
class VendorBackupInfo:
    path: Path
    created_at: str
    sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_backup(dest_dir: Path | None = None, *, include_keystore: bool = True) -> VendorBackupInfo:
    base = vendor_data_dir()
    dest_dir = dest_dir or (base / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = dest_dir / f"vendor-backup-{stamp}.zvbak"

    members: list[tuple[Path, str]] = []
    for name in ("vendor.db", "public_key.pem"):
        p = base / name
        if p.exists():
            members.append((p, name))
    if include_keystore:
        ks = base / "signing_key.enc"
        if ks.exists():
            members.append((ks, "signing_key.enc"))  # already encrypted

    manifest = {
        "format": "zenith-vendor-backup", "version": __version__,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "members": [name for _, name in members],
        "note": "signing_key.enc is AES-GCM encrypted; no plaintext private key is included.",
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, name in members:
            zf.write(path, arcname=name)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return VendorBackupInfo(out, manifest["created_at"], _sha256(out))


def verify_backup(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                return False
            manifest = json.loads(zf.read("manifest.json"))
            return all(m in zf.namelist() for m in manifest.get("members", []))
    except Exception:
        return False


def preview_backup(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        return json.loads(zf.read("manifest.json"))


def restore_backup(path: Path, dest_dir: Path | None = None) -> None:
    if not verify_backup(path):
        raise ValueError("Backup failed verification")
    base = dest_dir or vendor_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        for name in manifest.get("members", []):
            # safety copy of any existing file
            target = base / name
            if target.exists():
                target.replace(target.with_suffix(target.suffix + ".pre-restore"))
            with zf.open(name) as src, open(base / name, "wb") as dst:
                dst.write(src.read())
