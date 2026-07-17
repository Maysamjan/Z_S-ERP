"""Owner login / first-run setup for the License Manager."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QFileDialog, QMessageBox, QFrame,
)

from vendor_tools.license_manager import i18n
from vendor_tools.license_manager.models.db import session_scope
from vendor_tools.license_manager.services.owner_auth import OwnerAuthService, AuthError, AccountLocked
from vendor_tools.license_manager.services.keystore import KeyStoreError
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton


class OwnerLoginWindow(QWidget):
    authenticated = pyqtSignal(object, str)  # (OwnerSession, passphrase)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.tr = i18n.tr
        self.setObjectName("Root")
        self.setWindowTitle(self.tr("app.name"))
        self.setMinimumSize(560, 420)
        with session_scope(state.db) as s:
            self._first_run = not OwnerAuthService(s).has_owner()
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        title = QLabel("◆ " + self.tr("app.name"))
        title.setProperty("role", "h1")
        root.addWidget(title)
        sub = QLabel(self.tr("app.subtitle")); sub.setProperty("role", "muted")
        root.addWidget(sub)
        root.addSpacing(12)

        card = QFrame(); card.setObjectName("Card")
        form = QVBoxLayout(card)

        self.username = QLineEdit(); self.username.setPlaceholderText(self.tr("login.username"))
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText(self.tr("login.password"))
        form.addWidget(QLabel(self.tr("login.username"))); form.addWidget(self.username)
        form.addWidget(QLabel(self.tr("login.password"))); form.addWidget(self.password)

        if self._first_run:
            hint = QLabel(self.tr("login.create_hint")); hint.setWordWrap(True)
            hint.setProperty("role", "muted")
            form.addWidget(hint)
            self.passphrase = QLineEdit(); self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
            self.passphrase.setPlaceholderText(self.tr("login.passphrase"))
            form.addWidget(QLabel(self.tr("login.passphrase"))); form.addWidget(self.passphrase)
            keyrow = QHBoxLayout()
            self.key_path = QLineEdit(); self.key_path.setReadOnly(True)
            self.key_path.setPlaceholderText(self.tr("login.private_key_file"))
            self.key_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            browse = SecondaryButton(self.tr("login.browse")); browse.clicked.connect(self._browse_key)
            keyrow.addWidget(self.key_path, 1); keyrow.addWidget(browse)
            form.addWidget(QLabel(self.tr("login.private_key_file"))); form.addLayout(keyrow)
            btn = PrimaryButton(self.tr("login.create")); btn.clicked.connect(self._create)
        else:
            self.passphrase = QLineEdit(); self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
            self.passphrase.setPlaceholderText(self.tr("login.passphrase"))
            form.addWidget(QLabel(self.tr("login.passphrase"))); form.addWidget(self.passphrase)
            btn = PrimaryButton(self.tr("login.submit")); btn.clicked.connect(self._login)

        self.error = QLabel(""); self.error.setProperty("badge", "danger")
        self.error.setWordWrap(True); self.error.setVisible(False)
        form.addWidget(self.error)
        form.addWidget(btn)
        root.addWidget(card)
        root.addStretch(1)
        self.password.returnPressed.connect(btn.click)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("login.private_key_file"), "", "PEM (*.pem)")
        if path:
            self.key_path.setText(path)

    def _fail(self, msg):
        self.error.setText(msg); self.error.setVisible(True)

    def _create(self):
        try:
            with open(self.key_path.text(), "rb") as fh:
                pem = fh.read()
        except Exception:
            return self._fail(self.tr("login.private_key_file"))
        passphrase = self.passphrase.text()
        try:
            self.state.keystore.initialize(pem, passphrase, overwrite=not self.state.keystore.is_initialized())
            with session_scope(self.state.db) as s:
                OwnerAuthService(s).create_owner(self.username.text(), self.password.text())
                sess = OwnerAuthService(s).login(self.username.text(), self.password.text())
            self.passphrase.clear()
            self.authenticated.emit(sess, passphrase)
        except (AuthError, KeyStoreError) as exc:
            self._fail(str(exc))

    def _login(self):
        passphrase = self.passphrase.text()
        try:
            if not self.state.keystore.verify_passphrase(passphrase):
                return self._fail(self.tr("login.bad"))
            with session_scope(self.state.db) as s:
                sess = OwnerAuthService(s).login(self.username.text(), self.password.text())
            self.passphrase.clear()
            self.authenticated.emit(sess, passphrase)
        except AccountLocked:
            self._fail(self.tr("login.locked"))
        except AuthError:
            self._fail(self.tr("login.bad"))
