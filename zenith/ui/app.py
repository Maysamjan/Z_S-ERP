"""Application controller.

Owns the QApplication and the top-level flow:

    first run?  -> Setup Wizard -> Login -> Main Shell
    configured? -> Login -> Main Shell

Enforces the license at startup and after login (a NOT_ACTIVATED/INVALID license
sends the user to activation; an EXPIRED demo opens the shell in read-only mode).
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from sqlalchemy import select

from zenith.db.base import Database, session_scope
from zenith.db.models import BusinessSettings
from zenith.licensing.service import LicenseService
from zenith.ui.context import AppContext
from zenith.ui import i18n


class ZenithApp:
    def __init__(self, argv=None):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.qt = QApplication.instance() or QApplication(argv or sys.argv)
        self.db = Database()
        self.db.create_all()
        self.license_service = LicenseService()
        self.ctx: AppContext | None = None
        self._window = None

    # -- startup -----------------------------------------------------------
    def _load_settings(self) -> BusinessSettings | None:
        with session_scope(self.db) as session:
            return session.scalar(select(BusinessSettings).limit(1))

    def _make_context(self, settings: BusinessSettings) -> AppContext:
        ctx = AppContext(
            db=self.db, profile_code=settings.profile_code, theme_name=settings.theme or "light",
            locale=settings.language or "en_US", license_service=self.license_service,
            business_name=settings.business_name,
        )
        ctx.apply_theme(self.qt)
        ctx.apply_direction(self.qt)
        return ctx

    def run(self) -> int:
        settings = self._load_settings()
        if settings is None:
            self._start_setup()
        else:
            self.ctx = self._make_context(settings)
            self._show_login()
        return self.qt.exec()

    # -- flow steps --------------------------------------------------------
    def _start_setup(self) -> None:
        from zenith.ui.screens.setup_wizard import SetupWizard

        # baseline context for theme/i18n during setup
        i18n.set_locale("en_US")
        self.qt.setStyleSheet("")
        from zenith.ui.theme import build_stylesheet
        from zenith.ui.theme.tokens import LIGHT
        self.qt.setStyleSheet(build_stylesheet(LIGHT))

        wizard = SetupWizard(self.db, self.license_service)
        wizard.completedSetup.connect(self._after_setup)
        self._window = wizard
        wizard.show()

    def _after_setup(self, _result) -> None:
        settings = self._load_settings()
        self.ctx = self._make_context(settings)
        if self._window:
            self._window.close()
        self._show_login()

    def _show_login(self) -> None:
        from zenith.ui.screens.login import LoginWindow

        login = LoginWindow(self.ctx)
        login.loggedIn.connect(self._after_login)
        login.languageChanged.connect(self._relaunch_login)
        self._window = login
        login.showMaximized()

    def _relaunch_login(self, locale: str) -> None:
        self.ctx.set_locale(locale)
        self.ctx.apply_direction(self.qt)
        old = self._window
        self._show_login()
        if old:
            old.close()

    def _after_login(self, _session) -> None:
        from zenith.ui.screens.main_window import MainWindow

        status = self.ctx.license_status()
        if not status.can_open:
            QMessageBox.warning(None, self.ctx.tr("license.title"), self.ctx.tr(status.reason_key))
            return
        window = MainWindow(self.ctx)
        window.logoutRequested.connect(self._logout)
        window.languageChanged.connect(self._relaunch_after_login_lang)
        if self._window:
            self._window.close()
        self._window = window
        window.showMaximized()

    def _relaunch_after_login_lang(self, locale: str) -> None:
        self.ctx.set_locale(locale)
        self.ctx.apply_direction(self.qt)
        self._after_login(None)

    def _logout(self) -> None:
        self.ctx.session = None
        old = self._window
        self._show_login()
        if old:
            old.close()


def main(argv=None) -> int:
    return ZenithApp(argv).run()
