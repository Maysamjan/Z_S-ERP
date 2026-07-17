"""Regression tests for the Business Information logo preview.

Guards against the PyQt6 ``QPixmap.scaled`` crash (raw ints / obsolete enum
aliases) and the "reopen after saving a logo" scenario, plus the font-size
warning guard.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui


def _make_image(path, w, h, fmt, color="navy"):
    from PyQt6.QtGui import QImage, QColor
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    assert img.save(str(path), fmt.upper())
    return path


# --------------------------------------------------------------------------
# LogoPreview widget: typed enums + edge cases + responsiveness
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["png", "jpg", "jpeg", "webp"])
def test_logo_preview_renders_supported_formats(fmt, tmp_path):
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from zenith.ui.widgets.logo_preview import LogoPreview
    img = _make_image(tmp_path / f"logo.{fmt}", 300, 180, fmt)
    lp = LogoPreview(96)
    assert lp.set_logo(img) is True
    assert not lp.pixmap().isNull()


def test_logo_preview_handles_bad_inputs_without_crashing(tmp_path):
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from zenith.ui.widgets.logo_preview import LogoPreview
    lp = LogoPreview(96)
    # empty, None, missing, and garbage-content all return False, never raise
    assert lp.set_logo("") is False
    assert lp.set_logo(None) is False
    assert lp.set_logo("/no/such/logo.png") is False
    garbage = tmp_path / "fake.png"
    garbage.write_bytes(b"not a real image")
    assert lp.set_logo(garbage) is False
    assert lp.pixmap().isNull()  # shows placeholder


def test_logo_preview_caps_very_large_image(tmp_path):
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from zenith.ui.widgets.logo_preview import LogoPreview
    big = _make_image(tmp_path / "huge.png", 4000, 3000, "png", "darkred")
    lp = LogoPreview(96)
    assert lp.set_logo(big) is True  # decoded within bounds, no crash


def test_logo_preview_responsive_and_reopen(tmp_path):
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from zenith.ui.widgets.logo_preview import LogoPreview
    img = _make_image(tmp_path / "logo.png", 400, 200, "png")
    lp = LogoPreview(96)
    lp.set_logo(img)
    lp.resize(48, 48)   # resizeEvent -> re-render, must not raise
    lp.resize(240, 240)
    lp.clear_logo()
    assert lp.set_logo(img) is True   # re-open after clear


# --------------------------------------------------------------------------
# Business Information page: save logo, open, render, close, reopen
# --------------------------------------------------------------------------
def _ctx_with_admin(db):
    from zenith.db.base import session_scope
    from zenith.services import bootstrap
    from zenith.services.auth import AuthService
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code="GENERAL_STORE", business_name="D",
                             admin_username="admin", admin_password="admin123")
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
    from zenith.ui.context import AppContext
    return AppContext(db=db, profile_code="GENERAL_STORE", business_name="D", session=sess)


def test_business_info_save_logo_open_close_reopen(db, tmp_path, data_dir):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    ctx = _ctx_with_admin(db)
    ctx.apply_theme(app)

    # save a real logo through the identity service (as the upload flow does)
    from zenith.db.base import session_scope
    from zenith.services.business_identity import BusinessIdentityService
    src = _make_image(tmp_path / "biz.png", 500, 250, "png", "teal")
    with session_scope(db) as s:
        BusinessIdentityService(s).set_logo(ctx.user, str(src))

    from zenith.ui.pages.admin_pages import SettingsPage
    # Open Business Information -> _load_business() renders the saved logo.
    page = SettingsPage(ctx)
    assert not page.logo_preview.pixmap().isNull()  # rendered, no crash

    # Close and reopen (the exact reported reopen-after-save scenario).
    page.deleteLater()
    page2 = SettingsPage(ctx)
    assert not page2.logo_preview.pixmap().isNull()

    # calling _render_logo directly (the previously crashing method) is safe
    page2._render_logo(None)
    page2._render_logo(str(src))
    assert not page2.logo_preview.pixmap().isNull()


# --------------------------------------------------------------------------
# Font guard
# --------------------------------------------------------------------------
def test_safe_point_size_never_non_positive():
    from zenith.ui.theme.fonts import safe_point_size
    assert safe_point_size(-1) > 0
    assert safe_point_size(0) > 0
    assert safe_point_size(None) > 0
    assert safe_point_size(12) == 12


def test_font_warning_filter_suppresses_only_benign():
    import io
    import sys
    from PyQt6.QtCore import QtMsgType
    from zenith.ui.theme.fonts import _message_filter
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        _message_filter(QtMsgType.QtWarningMsg, None,
                        "QFont::setPointSize: Point size <= 0 (-1), must be greater than 0")
        _message_filter(QtMsgType.QtWarningMsg, None, "A genuine warning")
    finally:
        sys.stderr = old
    out = buf.getvalue()
    assert "setPointSize" not in out
    assert "A genuine warning" in out
