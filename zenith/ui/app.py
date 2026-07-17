"""Application controller.

Owns the QApplication and the top-level flow:

    first run?  -> Setup Wizard -> Login -> Main Shell
    configured? -> Login -> Main Shell

Enforces the license at startup and after login (a NOT_ACTIVATED/INVALID license
sends the user to activation; an EXPIRED demo opens the shell in read-only mode).
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from sqlalchemy import select

from zenith.db.base import Database, session_scope
from zenith.db.models import BusinessSettings
from zenith.licensing.service import LicenseService
from zenith.ui.context import AppContext
from zenith.ui import i18n

log = logging.getLogger("zenith.app")


class ZenithApp:
    def __init__(self, argv=None):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.qt = QApplication.instance() or QApplication(argv or sys.argv)
        self._configure_logging()
        # Resolve the DB path and open the engine WITHOUT touching any ORM model.
        self.db = Database()
        self.migration_error: Exception | None = None
        # Upgrade the schema FIRST -- before any current-version ORM query runs.
        self._apply_migrations()
        self.license_service = LicenseService()
        self.ctx: AppContext | None = None
        self._window = None

    # -- startup -----------------------------------------------------------
    def _configure_logging(self) -> None:
        if logging.getLogger().handlers:
            return
        try:
            from zenith.core import paths
            handler = logging.FileHandler(paths.logs_dir() / "zenith.log", encoding="utf-8")
        except Exception:  # pragma: no cover - fall back to stderr
            handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    def _apply_migrations(self) -> None:
        """Upgrade an existing customer database to the current schema (additive).

        Reads only the old-compatible ``profile_code`` via raw SQL -- it must never
        query a current-version ORM model before the schema is upgraded. On failure
        the database and any backup are retained (never deleted) and the error is
        recorded so ``run()`` can show it and stop safely.
        """
        from zenith.db.migrations import run_migrations, read_profile_code_raw
        try:
            profile = read_profile_code_raw(self.db)  # raw SQL, safe on any old schema
            report = run_migrations(self.db, profile_code=profile, backup=bool(profile))
            if report.changed:
                log.info("Schema migrated v%s -> v%s (tables=%s, columns=%s, backup=%s)",
                         report.from_version, report.to_version,
                         report.added_tables, report.added_columns, report.backed_up)
        except Exception as exc:  # pragma: no cover - exercised via error-path handling
            self.migration_error = exc
            log.exception("Database migration failed; original data retained.")

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
        if self.migration_error is not None:
            # Retain the original database + backup; do not continue on a
            # half-known schema. Show a clear, non-destructive error.
            i18n.set_locale("en_US")
            QMessageBox.critical(
                None, i18n.tr("app.name"),
                i18n.tr("migration.failed", error=str(self.migration_error)),
            )
            return 1
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
