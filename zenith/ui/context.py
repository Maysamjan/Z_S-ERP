"""Application context shared across screens.

Holds the database, the authenticated session, the active profile, license status,
translator and theme. Screens read from here rather than importing globals, which
keeps them testable (a test can build a context over a temp database).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtWidgets import QApplication

from zenith.db.base import Database
from zenith.licensing.service import LicenseService, LicenseStatus
from zenith.profiles import ProfileDefinition, get_profile
from zenith.services.auth import AuthSession
from zenith.ui import i18n
from zenith.ui.theme import build_stylesheet
from zenith.ui.theme.tokens import get_tokens


@dataclass
class AppContext:
    db: Database
    profile_code: str
    theme_name: str = "light"
    locale: str = "en_US"
    session: AuthSession | None = None
    license_service: LicenseService = field(default_factory=LicenseService)
    business_name: str = ""

    def __post_init__(self):
        i18n.set_locale(self.locale)

    @property
    def profile(self) -> ProfileDefinition:
        return get_profile(self.profile_code)

    @property
    def user(self):
        return self.session.user if self.session else None

    def tr(self, key: str, **params) -> str:
        return i18n.tr(key, **params)

    def license_status(self) -> LicenseStatus:
        return self.license_service.status(expected_profile=self.profile_code)

    def identity(self):
        """Current business identity snapshot (name, logo, contact, footers)."""
        from zenith.db.base import session_scope
        from zenith.services.business_identity import BusinessIdentityService
        with session_scope(self.db) as session:
            return BusinessIdentityService(session).get_identity()

    def display_name(self) -> str:
        try:
            return self.identity().name(self.locale) or self.business_name
        except Exception:
            return self.business_name

    # -- theming / direction ----------------------------------------------
    def set_locale(self, locale: str) -> None:
        self.locale = locale
        i18n.set_locale(locale)
        self.apply_direction()

    def set_theme(self, name: str) -> None:
        self.theme_name = name
        self.apply_theme()

    def apply_theme(self, app: QApplication | None = None) -> None:
        app = app or QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(get_tokens(self.theme_name)))

    def apply_direction(self, app: QApplication | None = None) -> None:
        from PyQt6.QtCore import Qt

        app = app or QApplication.instance()
        if app is not None:
            app.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight
            )
