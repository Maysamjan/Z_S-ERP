"""Password hashing, backup/restore, and localization catalogs."""

import json

import pytest

from zenith.core import paths
from zenith.security.password import hash_password, verify_password
from zenith.security.permissions import ROLE_TEMPLATES, ALL_PERMISSIONS, Permission


# --- security -------------------------------------------------------------
def test_password_hash_is_not_plaintext():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password(h, "secret123")
    assert not verify_password(h, "wrong")


def test_admin_role_has_all_permissions():
    assert set(ROLE_TEMPLATES["Administrator"]) == set(ALL_PERMISSIONS)


def test_cashier_cannot_approve_sales():
    assert Permission.SALE_APPROVE.value not in ROLE_TEMPLATES["Cashier"]


# --- backup ---------------------------------------------------------------
def test_backup_create_verify_restore(db, admin, tmp_path, monkeypatch):
    from zenith.services import backup as bk
    # point backups at a temp dir and use the on-disk db
    import zenith.core.paths as p
    dbfile = tmp_path / "zenith.db"
    # write a small sqlite file by copying the in-memory schema to a file db
    from zenith.db.base import Database
    filedb = Database(f"sqlite:///{dbfile}")
    filedb.create_all()

    info = bk.create_backup("GENERAL_STORE", db_file=dbfile, dest_dir=tmp_path / "bk")
    assert info.path.exists()
    assert bk.verify_backup(info.path)

    # restore into a new location
    target = tmp_path / "restored.db"
    bk.restore_backup(info.path, expected_profile="GENERAL_STORE", db_file=target)
    assert target.exists()


def test_backup_profile_mismatch_refused(tmp_path):
    from zenith.services import backup as bk
    from zenith.db.base import Database
    dbfile = tmp_path / "z.db"
    Database(f"sqlite:///{dbfile}").create_all()
    info = bk.create_backup("PHARMACY", db_file=dbfile, dest_dir=tmp_path / "bk")
    with pytest.raises(ValueError):
        bk.restore_backup(info.path, expected_profile="WAREHOUSE", db_file=tmp_path / "out.db")


# --- i18n -----------------------------------------------------------------
def _load(locale):
    return json.loads((paths.resource_dir() / "translations" / f"{locale}.json").read_text(encoding="utf-8"))


def test_locales_have_matching_keys():
    en, fa = _load("en_US"), _load("fa_AF")
    assert set(en) == set(fa)
    assert len(en) > 200


def test_no_empty_translations():
    for loc in ("en_US", "fa_AF"):
        cat = _load(loc)
        empties = [k for k, v in cat.items() if not str(v).strip()]
        assert not empties, f"empty values in {loc}: {empties}"


def test_rtl_detection():
    from zenith.ui import i18n
    i18n.set_locale("fa_AF")
    assert i18n.is_rtl()
    i18n.set_locale("en_US")
    assert not i18n.is_rtl()


def test_translator_falls_back_to_key():
    from zenith.ui.i18n import Translator
    t = Translator("en_US")
    assert t.tr("nonexistent.key.xyz") == "nonexistent.key.xyz"
