"""Zenith License Manager application controller (owner-only)."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from zenith.ui.theme import build_stylesheet
from zenith.ui.theme.tokens import get_tokens

from vendor_tools.license_manager.models.db import VendorDatabase, vendor_data_dir
from vendor_tools.license_manager.services.keystore import KeyStore
from vendor_tools.license_manager import i18n


@dataclass
class AppState:
    db: VendorDatabase
    keystore: KeyStore
    session: object | None = None       # OwnerSession
    passphrase: str | None = None       # held only while unlocked; cleared on lock
    theme_name: str = "light"

    @property
    def owner_name(self) -> str:
        return self.session.username if self.session else ""

    def lock(self) -> None:
        self.passphrase = None
        if self.session:
            self.session.lock()

    @property
    def is_unlocked(self) -> bool:
        return bool(self.session) and self.passphrase is not None


class LicenseManagerApp:
    def __init__(self, argv=None):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        self.qt = QApplication.instance() or QApplication(argv or sys.argv)
        # quiet the benign pixel-QSS font warning, consistent with the ERP
        try:
            from zenith.ui.theme.fonts import apply_base_font, install_font_warning_filter
            install_font_warning_filter(); apply_base_font(self.qt)
        except Exception:
            pass
        self.state = AppState(
            db=VendorDatabase(),
            keystore=KeyStore(vendor_data_dir() / "signing_key.enc"),
        )
        self.apply_theme()
        self._window = None

    def apply_theme(self) -> None:
        self.qt.setStyleSheet(build_stylesheet(get_tokens(self.state.theme_name)))

    def set_locale(self, locale: str) -> None:
        i18n.set_locale(locale) if False else i18n.get_translator().set_locale(locale)
        self.qt.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if i18n.get_translator().is_rtl
            else Qt.LayoutDirection.LeftToRight)

    def run(self) -> int:
        from vendor_tools.license_manager.login import OwnerLoginWindow
        login = OwnerLoginWindow(self.state)
        login.authenticated.connect(self._open_main)
        self._window = login
        login.show()
        return self.qt.exec()

    def _open_main(self, session, passphrase: str) -> None:
        from vendor_tools.license_manager.main_window import MainWindow
        self.state.session = session
        self.state.passphrase = passphrase
        win = MainWindow(self.state, controller=self)
        if self._window:
            self._window.close()
        self._window = win
        win.showMaximized()


def main(argv=None) -> int:
    return LicenseManagerApp(argv).run()
