"""Fixtures for the vendor License Manager tests (owner-only)."""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ZENITH_ALLOW_TEST_FINGERPRINT", "1")
os.environ.setdefault("ZENITH_MACHINE_ID", "VENDOR-TEST-MACHINE")

_QT_ARGV = ["vendor-tests"]
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
def keypair(monkeypatch):
    """A fresh Ed25519 keypair; install its public key as the app's embedded key."""
    from zenith.licensing.keys import generate_keypair
    import zenith.licensing.keys as keys_mod
    priv_pem, pub_pem = generate_keypair()
    monkeypatch.setattr(keys_mod, "EMBEDDED_PUBLIC_KEY_PEM", pub_pem)
    return priv_pem, pub_pem


@pytest.fixture()
def vendor_dir(tmp_path, monkeypatch):
    d = tmp_path / "vendor"
    d.mkdir()
    monkeypatch.setenv("ZENITH_VENDOR_DIR", str(d))
    return d


@pytest.fixture()
def keystore(vendor_dir, keypair):
    from vendor_tools.license_manager.services.keystore import KeyStore
    from vendor_tools.license_manager.models.db import vendor_data_dir
    priv_pem, _ = keypair
    ks = KeyStore(vendor_data_dir() / "signing_key.enc")
    ks.initialize(priv_pem, "test-passphrase-123")
    return ks


@pytest.fixture()
def vdb(vendor_dir):
    from vendor_tools.license_manager.models.db import VendorDatabase
    return VendorDatabase()


PASSPHRASE = "test-passphrase-123"
FINGERPRINT = "ab95f07a49a2fcec8d5b01da9c4097fdbdffd42047a7bb0977cb5d662baaecbd"
