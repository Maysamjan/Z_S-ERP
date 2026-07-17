"""Shared test fixtures.

A deterministic machine fingerprint (``ZENITH_MACHINE_ID``), an isolated temp data
directory, an in-memory database, and a per-session Ed25519 keypair that replaces
the app's embedded public key -- so license tests can both *sign* (with the test
private key) and *verify* (via the app's normal code path) without ever needing
the real vendor private key.
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("ZENITH_ALLOW_TEST_FINGERPRINT", "1")  # enable test override (never set in prod)
os.environ.setdefault("ZENITH_MACHINE_ID", "TEST-MACHINE-DEFAULT")
os.environ.setdefault("ZENITH_DATA_DIR", tempfile.mkdtemp(prefix="zenith-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# One persistent QApplication for the whole test session. Creating/destroying
# multiple QApplications (or passing a transient argv list to QApplication) can
# abort inside Qt (e.g. QPrinter PDF export), so we build exactly one here and
# keep its argv alive at module scope.
_QT_ARGV = ["pytest-zenith"]
_QT_APP = None


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    global _QT_APP
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        yield None
        return
    _QT_APP = QApplication.instance() or QApplication(_QT_ARGV)
    yield _QT_APP


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("ZENITH_DATA_DIR", str(d))
    return d


@pytest.fixture()
def db(data_dir):
    from zenith.db.base import Database
    database = Database("sqlite:///:memory:")
    database.create_all()
    return database


@pytest.fixture()
def keypair(monkeypatch):
    """Generate a test signing keypair and install its public key as the embedded key."""
    from zenith.licensing.keys import generate_keypair, load_private_key
    import zenith.licensing.keys as keys_mod

    priv_pem, pub_pem = generate_keypair()
    monkeypatch.setattr(keys_mod, "EMBEDDED_PUBLIC_KEY_PEM", pub_pem)
    return load_private_key(priv_pem)


@pytest.fixture()
def machine_fp():
    from zenith.licensing.machine import machine_fingerprint
    return machine_fingerprint()


@pytest.fixture()
def admin(db):
    """A bootstrapped admin user bound to a fresh session."""
    from zenith.db.base import session_scope
    from zenith.services import bootstrap
    with session_scope(db) as session:
        user = bootstrap.initialize(
            session, profile_code="GENERAL_STORE", business_name="Test Co",
            admin_username="admin", admin_password="admin123",
        )
        session.expunge(user)
    return user


@pytest.fixture()
def session(db):
    s = db.session()
    yield s
    s.rollback()
    s.close()
