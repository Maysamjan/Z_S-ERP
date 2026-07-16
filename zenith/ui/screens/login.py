"""Premium login window.

Independent from the main shell: the sidebar is never shown before authentication
succeeds. Two panels -- branding (product identity) and the login form (customer
identity + credentials). Enter submits, the button shows a loading state and is
disabled while authenticating, and license/auth problems are shown inline.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QComboBox,
    QFrame, QSizePolicy,
)

from zenith import __version__
from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.services.auth import AuthService
from zenith.ui import i18n
from zenith.ui.context import AppContext
from zenith.ui.widgets.buttons import PrimaryButton


class LoginWindow(QWidget):
    loggedIn = pyqtSignal(object)       # emits AuthSession
    languageChanged = pyqtSignal(str)   # emits new locale (app controller re-creates window)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Root")
        self.setWindowTitle(ctx.tr("app.name"))
        self.setMinimumSize(880, 560)
        self._busy = False
        self._build()

    # -- layout ------------------------------------------------------------
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._brand_panel(), 5)
        root.addWidget(self._form_panel(), 4)

    def _brand_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("BrandPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(48, 48, 48, 48)
        lay.addStretch(1)
        logo = QLabel("◆ " + self.ctx.tr("app.name"))
        logo.setObjectName("BrandTitle")
        lay.addWidget(logo)
        sub = QLabel(self.ctx.tr("app.tagline"))
        sub.setObjectName("BrandSubtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addStretch(2)
        ver = QLabel(self.ctx.tr("login.version", version=__version__))
        ver.setObjectName("BrandSubtitle")
        lay.addWidget(ver)
        cp = QLabel(self.ctx.tr("app.copyright"))
        cp.setObjectName("BrandSubtitle")
        lay.addWidget(cp)
        return panel

    def _form_panel(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("LoginCard")
        card.setMaximumWidth(380)
        form = QVBoxLayout(card)
        form.setContentsMargins(28, 28, 28, 28)
        form.setSpacing(12)

        biz = QLabel(self.ctx.business_name or self.ctx.tr("app.name"))
        biz.setProperty("role", "h2")
        form.addWidget(biz)
        welcome = QLabel(self.ctx.tr("login.welcome"))
        welcome.setProperty("role", "h1")
        form.addWidget(welcome)
        sub = QLabel(self.ctx.tr("login.subtitle"))
        sub.setProperty("role", "muted")
        form.addWidget(sub)

        self.username = QLineEdit()
        self.username.setPlaceholderText(self.ctx.tr("login.username"))
        form.addWidget(self.username)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText(self.ctx.tr("login.password"))
        form.addWidget(self.password)

        show = QCheckBox(self.ctx.tr("login.show_password"))
        show.toggled.connect(
            lambda v: self.password.setEchoMode(
                QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password
            )
        )
        form.addWidget(show)

        self.remember = QCheckBox(self.ctx.tr("login.remember"))
        form.addWidget(self.remember)

        self.caps = QLabel("⇪ " + self.ctx.tr("login.caps_lock"))
        self.caps.setProperty("badge", "warning")
        self.caps.setVisible(False)
        form.addWidget(self.caps)

        self.error = QLabel("")
        self.error.setProperty("badge", "danger")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        form.addWidget(self.error)

        self.submit = PrimaryButton(self.ctx.tr("login.submit"))
        self.submit.clicked.connect(self.attempt_login)
        form.addWidget(self.submit)

        lang = QComboBox()
        lang.addItem("English", "en_US")
        lang.addItem("دری / فارسی", "fa_AF")
        lang.setCurrentIndex(0 if self.ctx.locale == "en_US" else 1)
        lang.currentIndexChanged.connect(lambda _i: self._change_lang(lang.currentData()))
        form.addWidget(lang)

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(2)

        self.password.returnPressed.connect(self.attempt_login)
        self.username.returnPressed.connect(self.password.setFocus)
        return wrap

    # -- behaviour ---------------------------------------------------------
    def _change_lang(self, locale: str) -> None:
        if locale and locale != self.ctx.locale:
            self.languageChanged.emit(locale)

    def _set_error(self, message_key: str) -> None:
        self.error.setText(self.ctx.tr(message_key))
        self.error.setVisible(True)

    def keyPressEvent(self, event):  # Caps Lock hint
        try:
            state = QGuiApplication.queryKeyboardModifiers()
            self.caps.setVisible(False)  # best-effort; platform dependent
        except Exception:
            pass
        super().keyPressEvent(event)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.submit.setEnabled(not busy)
        self.submit.setText(self.ctx.tr("login.signing_in") if busy else self.ctx.tr("login.submit"))

    def attempt_login(self) -> None:
        if self._busy:
            return
        self.error.setVisible(False)
        self.set_busy(True)
        try:
            with session_scope(self.ctx.db) as session:
                auth = AuthService(session)
                auth_session = auth.login(self.username.text(), self.password.text())
                # detach a light copy for the UI thread
                user = auth_session.user
                _ = (user.id, user.username, user.full_name)
            self.ctx.session = auth_session
            self.loggedIn.emit(auth_session)
        except ZenithError as exc:
            self._set_error(exc.message_key)
        except Exception:
            self._set_error("error.generic")
        finally:
            self.set_busy(False)
