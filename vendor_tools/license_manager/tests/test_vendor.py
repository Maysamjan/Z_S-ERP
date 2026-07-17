"""Zenith License Manager test suite (owner-only).

Covers the 28 required scenarios: key matching, generation (demo/subscription/
perpetual), machine/profile binding, signature/tamper/expiry rejection, limits,
request parsing, .zreq / .zlic import-export, activation-key integrity, bilingual
GUI construction, profile-test bundle, renewal, replacement, history persistence,
encrypted key backup/restore, customer round-trip, and the production override lock.
"""

from __future__ import annotations

import base64
from datetime import date, timedelta

import pytest

from zenith.licensing import keys as _keys
from zenith.licensing.model import LicenseType, SignedLicense
from zenith.licensing.request import MachineRequest, build_request, RequestError
from zenith.licensing.verifier import verify_license
from zenith.licensing.service import LicenseService, LicenseState

from vendor_tools.license_manager.models.db import session_scope, VendorDatabase
from vendor_tools.license_manager.services import generator, history
from vendor_tools.license_manager.services.keystore import KeyStore, BadPassphrase
from vendor_tools.license_manager.tests.conftest import PASSPHRASE, FINGERPRINT


def _gen(vdb, keystore, **over):
    inp = generator.LicenseInput(
        profile_code=over.pop("profile_code", "PHARMACY"),
        machine_fingerprint=over.pop("machine_fingerprint", FINGERPRINT),
        license_type=over.pop("license_type", "DEMO"),
        duration_days=over.pop("duration_days", 30),
        max_users=over.pop("max_users", 3), max_branches=over.pop("max_branches", 1),
        **over)
    with session_scope(vdb) as s:
        return generator.generate(s, keystore, PASSPHRASE, inp, owner="owner")


# 1. private key matches embedded public key
def test_keystore_matches_embedded_public_key(keystore):
    assert keystore.matches_public_key(_keys.EMBEDDED_PUBLIC_KEY_PEM)


# 2. valid demo generation
def test_valid_demo(vdb, keystore):
    res = _gen(vdb, keystore, license_type="DEMO", duration_days=30)
    assert res.verification.ok
    assert res.activation_key.startswith("ZBE1.")
    assert res.signed.payload.license_type == "DEMO"


# 3. valid full subscription
def test_valid_full_subscription(vdb, keystore):
    res = _gen(vdb, keystore, license_type="FULL", duration_days=365, perpetual=False)
    assert res.verification.ok
    assert res.signed.payload.expiry_date is not None


# 4. valid perpetual full
def test_valid_full_perpetual(vdb, keystore):
    res = _gen(vdb, keystore, license_type="FULL", perpetual=True, duration_days=None)
    assert res.verification.ok
    assert res.signed.payload.is_perpetual


# 5 + 6. machine binding correct / wrong-machine rejected
def test_machine_binding(vdb, keystore):
    res = _gen(vdb, keystore)
    signed = SignedLicense.from_key(res.activation_key)
    ok = verify_license(signed, machine_fp=FINGERPRINT, expected_profile="PHARMACY",
                        today=date.today(), public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM)
    bad = verify_license(signed, machine_fp="0" * 64, expected_profile="PHARMACY",
                         today=date.today(), public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM)
    assert ok.ok and not bad.ok and bad.reason_key == "license.error.machine"


# 7 + 8. profile binding correct / wrong-profile rejected
def test_profile_binding(vdb, keystore):
    res = _gen(vdb, keystore, profile_code="PHARMACY")
    signed = SignedLicense.from_key(res.activation_key)
    bad = verify_license(signed, machine_fp=FINGERPRINT, expected_profile="WAREHOUSE",
                         today=date.today(), public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM)
    assert not bad.ok and bad.reason_key == "license.error.profile"


# 9 + 10. invalid signature / modified payload rejected
def test_modified_payload_rejected(vdb, keystore):
    res = _gen(vdb, keystore)
    signed = SignedLicense.from_key(res.activation_key)
    signed.payload.max_users = 999  # tamper
    bad = verify_license(signed, machine_fp=FINGERPRINT, expected_profile="PHARMACY",
                         today=date.today(), public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM)
    assert not bad.ok and bad.reason_key == "license.error.signature"


# 11. expired license rejected
def test_expired_rejected(vdb, keystore):
    res = _gen(vdb, keystore, duration_days=7)
    signed = SignedLicense.from_key(res.activation_key)
    future = date.today() + timedelta(days=30)
    bad = verify_license(signed, machine_fp=FINGERPRINT, expected_profile="PHARMACY",
                         today=future, public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM)
    assert not bad.ok and bad.reason_key == "license.error.expired"


# 12 + 13. user/branch limit payload
def test_limits_payload(vdb, keystore):
    res = _gen(vdb, keystore, max_users=7, max_branches=4)
    assert res.signed.payload.max_users == 7 and res.signed.payload.max_branches == 4


# 14. module-limit payload
def test_module_limit_payload(vdb, keystore):
    from zenith.profiles import get_profile
    mods = get_profile("PHARMACY").enabled_modules[:3]
    res = _gen(vdb, keystore, enabled_modules=list(mods))
    assert set(res.signed.payload.enabled_modules) == set(mods)


def test_invalid_module_rejected(vdb, keystore):
    with pytest.raises(generator.GenerationError):
        _gen(vdb, keystore, enabled_modules=["not.a.module"])


# 15. request-code parsing
def test_request_code_roundtrip():
    req = build_request(FINGERPRINT, "SUPERMARKET", app_version="0.1.0", business_name="X")
    code = req.to_code()
    back = MachineRequest.from_code(code)
    assert back.machine_fingerprint == FINGERPRINT and back.profile_code == "SUPERMARKET"


def test_request_validation_rejects_bad_fingerprint():
    with pytest.raises(RequestError):
        build_request("short", "PHARMACY")


# 16. .zreq import
def test_zreq_file_roundtrip():
    req = build_request(FINGERPRINT, "WHOLESALE")
    text = req.to_file_json()
    back = MachineRequest.from_file_json(text)
    assert back.profile_code == "WHOLESALE"


# 17 + 18. .zlic export/import + activation-key not truncated
def test_zlic_export_import_and_key_integrity(vdb, keystore):
    res = _gen(vdb, keystore)
    key = res.activation_key
    # export to .zlic and re-parse
    signed = SignedLicense.from_file_json(res.signed.to_file_json())
    assert signed.to_key() == key            # key survives file round-trip, untruncated
    assert len(key) > 400 and key.count(".") == 2


# 19 + 20. bilingual GUI construction
@pytest.mark.parametrize("locale", ["en_US", "fa_AF"])
def test_gui_constructs_bilingual(vdb, keystore, locale):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    from zenith.ui.theme import build_stylesheet
    from zenith.ui.theme.tokens import get_tokens
    app.setStyleSheet(build_stylesheet(get_tokens("light")))
    from vendor_tools.license_manager import i18n
    i18n.get_translator().set_locale(locale)
    from vendor_tools.license_manager.app import AppState
    from vendor_tools.license_manager.services.owner_auth import OwnerAuthService
    with session_scope(vdb) as s:
        OwnerAuthService(s).create_owner("owner", "OwnerPass123")
        sess = OwnerAuthService(s).login("owner", "OwnerPass123")
    state = AppState(db=vdb, keystore=keystore, session=sess, passphrase=PASSPHRASE)
    from vendor_tools.license_manager.main_window import MainWindow
    from vendor_tools.license_manager.login import OwnerLoginWindow
    OwnerLoginWindow(AppState(db=vdb, keystore=keystore))
    win = MainWindow(state)
    # driving the generate flow through the widgets
    win.f_fingerprint.setText(FINGERPRINT)
    win.f_profile.setCurrentIndex(win.f_profile.findData("PHARMACY"))
    win._generate()
    assert win.key_output.toPlainText().startswith("ZBE1.")
    # responsive
    for w, h in [(1024, 768), (1366, 768), (1920, 1080)]:
        win.resize(w, h)
        assert win.width() == w


# 21. profile test bundle -> five separate profile-bound licenses
def test_profile_test_bundle(vdb, keystore):
    with session_scope(vdb) as s:
        bundle = generator.generate_test_bundle(
            s, keystore, PASSPHRASE, machine_fingerprint=FINGERPRINT, duration_days=30, owner="owner")
    assert set(bundle) == {"GENERAL_STORE", "SUPERMARKET", "WHOLESALE", "PHARMACY", "WAREHOUSE"}
    # each is profile-bound (no wildcard): GENERAL_STORE key rejected as SUPERMARKET
    gs = SignedLicense.from_key(bundle["GENERAL_STORE"].activation_key)
    cross = verify_license(gs, machine_fp=FINGERPRINT, expected_profile="SUPERMARKET",
                           today=date.today(), public_key_pem=_keys.EMBEDDED_PUBLIC_KEY_PEM)
    assert not cross.ok


# 22. renewal creates a new signed license
def test_renewal_new_license(vdb, keystore):
    res = _gen(vdb, keystore)
    old_id = res.record.license_id
    with session_scope(vdb) as s:
        changes = generator.LicenseInput(profile_code="X", machine_fingerprint="X",
                                          license_type="FULL", perpetual=True, duration_days=None,
                                          max_users=9, max_branches=3)
        ren = generator.renew(s, keystore, PASSPHRASE, old_id, changes, owner="owner")
    assert ren.record.license_id != old_id
    assert ren.record.renewed_from == old_id
    assert ren.record.profile_code == "PHARMACY"          # profile unchanged
    assert ren.record.machine_fingerprint == FINGERPRINT  # machine unchanged


# 23. replacement references old license
def test_replacement_references_old(vdb, keystore):
    res = _gen(vdb, keystore)
    old_id = res.record.license_id
    with session_scope(vdb) as s:
        rep_in = generator.LicenseInput(profile_code="PHARMACY", machine_fingerprint="f" * 64,
                                        license_type="DEMO", duration_days=15)
        rep = generator.replace(s, keystore, PASSPHRASE, old_id, rep_in, reason="new PC", owner="owner")
        assert rep.record.replaced_from == old_id
        assert history.get(s, old_id).status == "replaced"


def test_replacement_requires_reason(vdb, keystore):
    res = _gen(vdb, keystore)
    with session_scope(vdb) as s:
        with pytest.raises(generator.GenerationError):
            generator.replace(s, keystore, PASSPHRASE, res.record.license_id,
                              generator.LicenseInput(profile_code="PHARMACY", machine_fingerprint=FINGERPRINT),
                              reason="", owner="owner")


# 24. license history persists after restart
def test_history_persists_after_restart(vendor_dir, keystore):
    db1 = VendorDatabase()
    res = _gen(db1, keystore)
    lid = res.record.license_id
    del db1
    db2 = VendorDatabase()  # reopen same file
    with session_scope(db2) as s:
        assert history.get(s, lid) is not None
        assert len(history.search(s)) >= 1


# 25. encrypted private-key backup and restore
def test_key_backup_and_restore(keystore, tmp_path):
    bak = tmp_path / "key.enc.bak"
    keystore.export_backup(bak)
    # the backup is the encrypted envelope, not plaintext PEM
    assert b"BEGIN PRIVATE KEY" not in bak.read_bytes()
    # restore into a new store and verify signing still works
    from vendor_tools.license_manager.services.keystore import KeyStore
    restored = KeyStore(tmp_path / "restored.enc")
    restored.restore_backup(bak)
    assert restored.verify_passphrase(PASSPHRASE)
    with pytest.raises(BadPassphrase):
        restored.load_private_key("wrong-pass")


# 26 + 27. customer activates a generated license / rejects other-profile
def test_customer_activation_roundtrip(vdb, keystore, tmp_path, monkeypatch):
    monkeypatch.setenv("ZENITH_DATA_DIR", str(tmp_path / "cust"))
    res = _gen(vdb, keystore, profile_code="PHARMACY")
    svc = LicenseService(machine_fp=FINGERPRINT)
    st = svc.import_file(res.signed.to_file_json(), expected_profile="PHARMACY", today=date.today())
    assert st.state == LicenseState.ACTIVE
    st_wrong = svc.status(expected_profile="WAREHOUSE")
    assert st_wrong.state == LicenseState.INVALID and st_wrong.reason_key == "license.error.profile"


# 28. production build cannot use the test machine override
def test_production_ignores_machine_override(monkeypatch):
    from zenith.licensing import machine
    monkeypatch.setenv("ZENITH_MACHINE_ID", "SPOOFED-MACHINE")
    # production: the allow-flag is NOT set -> override ignored, real fingerprint used
    monkeypatch.delenv("ZENITH_ALLOW_TEST_FINGERPRINT", raising=False)
    prod_fp = machine.machine_fingerprint()
    assert "override:SPOOFED-MACHINE" not in machine.raw_identifiers()
    # test mode: allow-flag set -> override honored
    monkeypatch.setenv("ZENITH_ALLOW_TEST_FINGERPRINT", "1")
    assert machine.machine_fingerprint() != prod_fp


# bonus: bad passphrase cannot sign
def test_generation_requires_correct_passphrase(vdb, keystore):
    inp = generator.LicenseInput(profile_code="PHARMACY", machine_fingerprint=FINGERPRINT)
    with session_scope(vdb) as s:
        with pytest.raises(BadPassphrase):
            generator.generate(s, keystore, "wrong-passphrase", inp, owner="owner")
