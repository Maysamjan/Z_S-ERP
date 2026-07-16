"""Filesystem locations.

On Windows the app stores customer data under ``%PROGRAMDATA%\\ZenithBusinessERP``
so that data survives application upgrades and uninstall. On other platforms
(dev / CI) a platform-appropriate directory is used. Tests override the base via
``ZENITH_DATA_DIR`` so they never touch a real installation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "ZenithBusinessERP"


def _default_base() -> Path:
    env = os.environ.get("ZENITH_DATA_DIR")
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / APP_DIR_NAME
    # dev / Linux / macOS
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def data_dir() -> Path:
    p = _default_base()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "zenith.db"


def backups_dir() -> Path:
    return _sub("backups")


def logs_dir() -> Path:
    return _sub("logs")


def license_dir() -> Path:
    return _sub("license")


def config_path() -> Path:
    return data_dir() / "config.json"


def resource_dir() -> Path:
    """Directory holding bundled UI resources (qss, translations, icons)."""
    return Path(__file__).resolve().parent.parent / "ui" / "resources"
