"""GUI construction tests (offscreen).

Verify the login, setup wizard and main shell build for every profile, that all
sidebar pages construct and navigate without error, and that the shell survives
every required resolution and both text directions -- our responsive/localization
smoke coverage.
"""

import pytest

pytest.importorskip("PyQt6")
pytestmark = pytest.mark.gui

PROFILES = ["GENERAL_STORE", "SUPERMARKET", "WHOLESALE", "PHARMACY", "WAREHOUSE"]
RESOLUTIONS = [(1024, 768), (1280, 720), (1366, 768), (1440, 900), (1600, 900), (1920, 1080)]


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _fresh(profile):
    from zenith.db.base import Database, session_scope
    from zenith.services import bootstrap
    from zenith.services.auth import AuthService
    db = Database("sqlite:///:memory:")
    db.create_all()
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code=profile, business_name="Demo",
                             admin_username="admin", admin_password="admin123")
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
    return db, sess


def _ctx(db, profile, sess, qapp, locale="en_US"):
    from zenith.ui.context import AppContext
    ctx = AppContext(db=db, profile_code=profile, business_name="Demo", session=sess, locale=locale)
    ctx.apply_theme(qapp)
    ctx.apply_direction(qapp)
    return ctx


@pytest.mark.parametrize("profile", PROFILES)
def test_shell_builds_and_navigates(qapp, profile):
    db, sess = _fresh(profile)
    ctx = _ctx(db, profile, sess, qapp)
    from zenith.ui.screens.main_window import MainWindow
    win = MainWindow(ctx)
    keys = list(win._nav_buttons.keys())
    assert keys, "sidebar has no navigable pages"
    for k in keys:
        win.navigate(k)  # must not raise
    # no forbidden module leaked into the sidebar
    assert all("restaurant" not in k and "school" not in k for k in keys)


@pytest.mark.parametrize("res", RESOLUTIONS)
def test_shell_survives_resolutions(qapp, res):
    db, sess = _fresh("SUPERMARKET")
    ctx = _ctx(db, "SUPERMARKET", sess, qapp)
    from zenith.ui.screens.main_window import MainWindow
    win = MainWindow(ctx)
    w, h = res
    win.resize(w, h)
    qapp.processEvents()
    assert win.width() == w and win.height() == h


def test_login_builds_ltr_and_rtl(qapp):
    db, sess = _fresh("GENERAL_STORE")
    from zenith.ui.screens.login import LoginWindow
    ctx_en = _ctx(db, "GENERAL_STORE", sess, qapp, locale="en_US")
    LoginWindow(ctx_en)
    ctx_fa = _ctx(db, "GENERAL_STORE", sess, qapp, locale="fa_AF")
    LoginWindow(ctx_fa)


def test_setup_wizard_builds(qapp):
    from zenith.db.base import Database
    from zenith.ui.screens.setup_wizard import SetupWizard
    db = Database("sqlite:///:memory:")
    db.create_all()
    wiz = SetupWizard(db)
    assert len(wiz.pageIds()) == 6


def test_wizard_enforces_profile_license_match(qapp, keypair, machine_fp):
    from zenith.db.base import Database
    from zenith.ui.screens.setup_wizard import SetupWizard
    from zenith.vendor.license_issuer import build_license, issue_signed
    from zenith.licensing.model import LicenseType
    db = Database("sqlite:///:memory:")
    db.create_all()
    wiz = SetupWizard(db)
    key = issue_signed(
        build_license(customer_name="a", business_name="b", profile_code="WHOLESALE",
                      license_type=LicenseType.FULL, machine_fingerprint=machine_fp, perpetual=True),
        keypair,
    ).to_key()
    wiz.result_data.profile_code = "SUPERMARKET"
    wiz.license_page.key_input.setPlainText(key)
    wiz.license_page._activate()
    assert not wiz.license_page.isComplete()  # mismatch blocks finish
    wiz.result_data.profile_code = "WHOLESALE"
    wiz.license_page._activate()
    assert wiz.license_page.isComplete()
