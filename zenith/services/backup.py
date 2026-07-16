"""Backup and restore.

Backups are timestamped copies of the SQLite database plus a manifest recording
the app version and business profile, wrapped in a single ``.zbak`` (zip) file.
A verified backup is always taken *before* a destructive schema migration, and
customer data is never deleted on update/uninstall.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from zenith import __version__
from zenith.core import paths


@dataclass
class BackupInfo:
    path: Path
    created_at: str
    app_version: str
    profile_code: str
    db_sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_backup(profile_code: str, db_file: Path | None = None,
                  dest_dir: Path | None = None) -> BackupInfo:
    db_file = db_file or paths.db_path()
    dest_dir = dest_dir or paths.backups_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not db_file.exists():
        raise FileNotFoundError(f"Database not found: {db_file}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = dest_dir / f"zenith-{profile_code}-{stamp}.zbak"
    digest = _sha256(db_file)
    manifest = {
        "format": "zenith-backup",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": __version__,
        "profile_code": profile_code,
        "db_sha256": digest,
        "db_name": db_file.name,
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_file, arcname=db_file.name)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return BackupInfo(out, manifest["created_at"], __version__, profile_code, digest)


def verify_backup(backup_path: Path) -> bool:
    """Confirm the archived db matches its recorded hash and manifest is valid."""
    with zipfile.ZipFile(backup_path, "r") as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            return False
        manifest = json.loads(zf.read("manifest.json"))
        db_name = manifest.get("db_name")
        if db_name not in names:
            return False
        h = hashlib.sha256(zf.read(db_name)).hexdigest()
        return h == manifest.get("db_sha256")


def restore_backup(backup_path: Path, *, expected_profile: str | None = None,
                   db_file: Path | None = None) -> None:
    """Restore a verified backup. Refuses profile-mismatched restores."""
    if not verify_backup(backup_path):
        raise ValueError("Backup failed verification (corrupt or tampered)")
    with zipfile.ZipFile(backup_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        if expected_profile and manifest.get("profile_code") != expected_profile:
            raise ValueError("Backup profile does not match the installed profile")
        db_file = db_file or paths.db_path()
        # safety copy of the current db first
        if db_file.exists():
            shutil.copy2(db_file, db_file.with_suffix(".db.pre-restore"))
        with zf.open(manifest["db_name"]) as src, open(db_file, "wb") as dst:
            shutil.copyfileobj(src, dst)


def list_backups(dest_dir: Path | None = None) -> list[Path]:
    dest_dir = dest_dir or paths.backups_dir()
    if not dest_dir.exists():
        return []
    return sorted(dest_dir.glob("*.zbak"), reverse=True)
