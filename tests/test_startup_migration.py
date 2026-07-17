"""Regression tests for the startup migration ordering bug.

Reproduces the reported crash: an existing older database whose ``business_settings``
table lacks ``business_name_en`` (and the other newer columns) used to crash during
``ZenithApp`` startup because migrations queried the current-version ORM model
before upgrading the schema.

These tests build databases at every supported older schema version and drive the
REAL ``ZenithApp`` startup path, asserting it upgrades safely and preserves data.
"""

from __future__ import annotations

import sqlite3

import pytest

from zenith.db.base import Database
from zenith.services.bootstrap import CURRENT_SCHEMA_VERSION

# business_settings columns present at each historical version.
_V1_BSETTINGS = [
    "id INTEGER PRIMARY KEY", "business_name TEXT", "profile_code TEXT NOT NULL",
    "logo_path TEXT", "address TEXT", "phone TEXT", "email TEXT",
    "currency TEXT", "date_system TEXT", "language TEXT", "theme TEXT",
]
_V2_ADDED = [
    "business_name_en TEXT", "owner_name TEXT", "phone_secondary TEXT", "whatsapp TEXT",
    "website TEXT", "address_en TEXT", "province TEXT", "city TEXT", "district TEXT",
    "registration_no TEXT", "tax_no TEXT", "slogan TEXT", "invoice_footer_fa TEXT",
    "invoice_footer_en TEXT", "terms_fa TEXT", "terms_en TEXT", "currency_secondary TEXT",
]


def _make_old_db(path, version: str) -> None:
    """Create a database that looks like the given historical version."""
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    if version == "empty":
        conn.close()
        return  # a zero-table database

    cols = list(_V1_BSETTINGS)
    if version in ("v2", "v3"):
        cols += _V2_ADDED
    cur.execute(f"CREATE TABLE business_settings ({', '.join(cols)})")
    cur.execute("INSERT INTO business_settings (business_name, profile_code, phone) "
                "VALUES ('Old Pharmacy', 'PHARMACY', '0700111222')")

    # v3 also predates returned_qty on sale_lines; include it to exercise a column add.
    if version == "v3":
        cur.execute("CREATE TABLE sale_lines (id INTEGER PRIMARY KEY, sale_id INTEGER, "
                    "product_id INTEGER, quantity NUMERIC, unit_price NUMERIC, line_total NUMERIC)")

    if version != "missing_version":
        cur.execute("CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER, applied_at TEXT)")
        ver = {"v1": 1, "v2": 2, "v3": 3}.get(version, 1)
        cur.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", (ver, "2026-01-01"))
    conn.commit()
    conn.close()


def _make_current_db(path) -> None:
    """A fully current v4 database (migration should be a no-op)."""
    from zenith.db.base import session_scope
    from zenith.services import bootstrap
    db = Database(f"sqlite:///{path}")
    db.create_all()
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code="PHARMACY", business_name="Current Co",
                             admin_username="admin", admin_password="admin123")
    db.engine.dispose()


def _start_app(monkeypatch, data_dir):
    """Point ZenithApp at data_dir and run its real startup (__init__)."""
    monkeypatch.setenv("ZENITH_DATA_DIR", str(data_dir))
    from zenith.db.base import reset_database_singleton
    reset_database_singleton()
    from zenith.ui.app import ZenithApp
    return ZenithApp([])


def _columns(path, table) -> set[str]:
    conn = sqlite3.connect(str(path))
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _max_version(path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    finally:
        conn.close()


@pytest.mark.gui  # constructs QApplication via ZenithApp
@pytest.mark.parametrize("version", ["empty", "v1", "v2", "v3", "missing_version", "current"])
def test_startup_migrates_old_database(version, tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "zenith.db"

    populated = version not in ("empty",)
    if version == "current":
        _make_current_db(db_file)
    else:
        _make_old_db(db_file, version)

    # --- the real startup path: this used to crash on v1/missing_version ---
    app = _start_app(monkeypatch, data_dir)
    assert app.migration_error is None, f"startup crashed: {app.migration_error}"

    # schema reaches the current version
    assert _max_version(db_file) == CURRENT_SCHEMA_VERSION

    # all newer business_settings columns are present now
    cols = _columns(db_file, "business_settings")
    for c in ("business_name_en", "tax_no", "slogan", "currency_secondary"):
        assert c in cols, f"missing migrated column {c} for {version}"

    # BusinessSettings loads via the ORM after migration
    settings = app._load_settings()
    if version == "empty":
        assert settings is None  # fresh install -> setup wizard path
    else:
        assert settings is not None
        expected_name = "Current Co" if version == "current" else "Old Pharmacy"
        assert settings.business_name == expected_name          # data preserved
        assert settings.profile_code == "PHARMACY"
        _ = settings.business_name_en                            # new column readable

    # re-running migrations does not migrate again (idempotent / run-once)
    from zenith.db.migrations import run_migrations, read_profile_code_raw
    db2 = Database(f"sqlite:///{db_file}")
    report = run_migrations(db2, profile_code=read_profile_code_raw(db2), backup=False)
    assert not report.changed
    assert report.from_version == CURRENT_SCHEMA_VERSION


@pytest.mark.gui
def test_v1_startup_preserves_data_and_adds_all_columns(tmp_path, monkeypatch):
    """Focused reproduction of the exact reported crash + full assertions."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "zenith.db"
    _make_old_db(db_file, "v1")

    # before: the crashing column does not exist
    assert "business_name_en" not in _columns(db_file, "business_settings")

    app = _start_app(monkeypatch, data_dir)

    assert app.migration_error is None
    assert "business_name_en" in _columns(db_file, "business_settings")
    assert _max_version(db_file) == CURRENT_SCHEMA_VERSION

    settings = app._load_settings()
    assert settings is not None and settings.business_name == "Old Pharmacy"
    assert settings.phone == "0700111222"  # existing data preserved

    # a pre-migration backup was produced for the populated database
    from zenith.core import paths
    backups = list((paths.backups_dir()).glob("*.zbak"))
    assert backups, "expected a pre-migration backup"


def test_read_profile_code_raw_handles_all_shapes(tmp_path):
    """The raw profile read never raises, whatever the schema looks like."""
    from zenith.db.migrations import read_profile_code_raw

    empty = tmp_path / "empty.db"
    _make_old_db(empty, "empty")
    assert read_profile_code_raw(Database(f"sqlite:///{empty}")) is None

    v1 = tmp_path / "v1.db"
    _make_old_db(v1, "v1")
    assert read_profile_code_raw(Database(f"sqlite:///{v1}")) == "PHARMACY"
