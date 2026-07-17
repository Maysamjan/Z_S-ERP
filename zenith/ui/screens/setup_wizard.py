"""First-run setup wizard.

Guides the user through language, profile, business info, admin account and license
activation, then creates the database. The profile chosen here is validated against
the license (a WHOLESALE license cannot activate a SUPERMARKET profile) before the
wizard can finish.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QRadioButton, QButtonGroup, QFrame, QGridLayout, QWidget, QMessageBox, QPlainTextEdit,
)

from zenith.db.base import session_scope
from zenith.licensing.machine import request_code, machine_fingerprint
from zenith.licensing.service import LicenseService, LicenseState
from zenith.profiles import all_profiles
from zenith.services import bootstrap
from zenith.ui import i18n


class SetupResult:
    def __init__(self):
        self.locale = "en_US"
        self.profile_code = "GENERAL_STORE"
        self.business_name = ""
        self.currency = "AFN"
        self.admin_username = "admin"
        self.admin_password = ""


class SetupWizard(QWizard):
    completedSetup = pyqtSignal(object)  # emits SetupResult

    def __init__(self, db, license_service: LicenseService | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.result_data = SetupResult()
        self.license_service = license_service or LicenseService()
        self.setWindowTitle(i18n.tr("setup.title"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(720, 560)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self.addPage(self._welcome_page())
        self.profile_page = ProfilePage(self.result_data)
        self.addPage(self.profile_page)
        self.business_page = BusinessPage(self.result_data)
        self.addPage(self.business_page)
        self.admin_page = AdminPage(self.result_data)
        self.addPage(self.admin_page)
        self.license_page = LicensePage(self.result_data, self.license_service)
        self.addPage(self.license_page)
        self.addPage(self._review_page())

        self.button(QWizard.WizardButton.FinishButton).clicked.connect(self._finish)

    def _welcome_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(i18n.tr("setup.welcome.title"))
        lay = QVBoxLayout(page)
        body = QLabel(i18n.tr("setup.welcome.body"))
        body.setWordWrap(True)
        lay.addWidget(body)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(i18n.tr("setup.step.language")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en_US")
        self.lang_combo.addItem("دری / فارسی", "fa_AF")
        self.lang_combo.currentIndexChanged.connect(
            lambda _i: self._set_locale(self.lang_combo.currentData())
        )
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch(1)
        lay.addLayout(lang_row)
        lay.addStretch(1)
        return page

    def _set_locale(self, locale: str) -> None:
        self.result_data.locale = locale
        i18n.set_locale(locale)
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight
            )

    def _review_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(i18n.tr("setup.step.review"))
        lay = QVBoxLayout(page)
        self.review_label = QLabel()
        self.review_label.setWordWrap(True)
        lay.addWidget(self.review_label)
        lay.addStretch(1)

        def refresh():
            d = self.result_data
            self.review_label.setText(
                f"<b>{i18n.tr('setup.step.profile')}:</b> {d.profile_code}<br>"
                f"<b>{i18n.tr('setup.business_name')}:</b> {d.business_name}<br>"
                f"<b>{i18n.tr('setup.currency')}:</b> {d.currency}<br>"
                f"<b>{i18n.tr('setup.admin_username')}:</b> {d.admin_username}<br>"
                f"<b>{i18n.tr('setup.finish_body')}</b>"
            )
        page.initializePage = refresh  # type: ignore
        return page

    def _finish(self) -> None:
        d = self.result_data
        try:
            with session_scope(self.db) as session:
                bootstrap.initialize(
                    session, profile_code=d.profile_code, business_name=d.business_name,
                    admin_username=d.admin_username, admin_password=d.admin_password,
                    currency=d.currency, language=d.locale,
                )
            self.completedSetup.emit(d)
        except Exception as exc:  # pragma: no cover - GUI error path
            QMessageBox.critical(self, i18n.tr("common.error"), str(exc))


class ProfilePage(QWizardPage):
    def __init__(self, result: SetupResult):
        super().__init__()
        self.result = result
        self.setTitle(i18n.tr("setup.choose_profile"))
        lay = QVBoxLayout(self)
        self.group = QButtonGroup(self)
        grid = QGridLayout()
        for idx, prof in enumerate(all_profiles()):
            card = self._profile_card(prof, idx == 0)
            grid.addWidget(card, idx // 2, idx % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        self.result.profile_code = all_profiles()[0].code.value

    def _profile_card(self, prof, checked: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        v = QVBoxLayout(frame)
        radio = QRadioButton(i18n.tr(prof.name_key))
        radio.setChecked(checked)
        radio.toggled.connect(lambda on, code=prof.code.value: self._select(code) if on else None)
        self.group.addButton(radio)
        v.addWidget(radio)
        desc = QLabel(i18n.tr(prof.description_key))
        desc.setProperty("role", "muted")
        desc.setWordWrap(True)
        v.addWidget(desc)
        for hk in prof.highlight_keys:
            b = QLabel("• " + i18n.tr(hk))
            b.setProperty("role", "muted")
            v.addWidget(b)
        return frame

    def _select(self, code: str) -> None:
        self.result.profile_code = code

    def isComplete(self) -> bool:
        return bool(self.result.profile_code)


class BusinessPage(QWizardPage):
    def __init__(self, result: SetupResult):
        super().__init__()
        self.result = result
        self.setTitle(i18n.tr("setup.step.business"))
        lay = QGridLayout(self)
        lay.addWidget(QLabel(i18n.tr("setup.business_name")), 0, 0)
        self.name = QLineEdit()
        self.name.textChanged.connect(self._sync)
        lay.addWidget(self.name, 0, 1)
        lay.addWidget(QLabel(i18n.tr("setup.currency")), 1, 0)
        self.currency = QComboBox()
        for c in ["AFN", "USD", "PKR", "EUR"]:
            self.currency.addItem(c, c)
        self.currency.currentTextChanged.connect(self._sync)
        lay.addWidget(self.currency, 1, 1)

    def _sync(self, *_):
        self.result.business_name = self.name.text().strip()
        self.result.currency = self.currency.currentText()
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return bool(self.name.text().strip())


class AdminPage(QWizardPage):
    def __init__(self, result: SetupResult):
        super().__init__()
        self.result = result
        self.setTitle(i18n.tr("setup.step.admin"))
        lay = QGridLayout(self)
        lay.addWidget(QLabel(i18n.tr("setup.admin_username")), 0, 0)
        self.username = QLineEdit("admin")
        self.username.textChanged.connect(self._sync)
        lay.addWidget(self.username, 0, 1)
        lay.addWidget(QLabel(i18n.tr("setup.admin_password")), 1, 0)
        self.pw1 = QLineEdit(); self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw1.textChanged.connect(self._sync)
        lay.addWidget(self.pw1, 1, 1)
        lay.addWidget(QLabel(i18n.tr("setup.admin_password2")), 2, 0)
        self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2.textChanged.connect(self._sync)
        lay.addWidget(self.pw2, 2, 1)
        self.hint = QLabel("")
        self.hint.setProperty("badge", "danger")
        self.hint.setVisible(False)
        lay.addWidget(self.hint, 3, 0, 1, 2)

    def _sync(self, *_):
        self.result.admin_username = self.username.text().strip()
        self.result.admin_password = self.pw1.text()
        mismatch = self.pw1.text() and self.pw2.text() and self.pw1.text() != self.pw2.text()
        self.hint.setText(i18n.tr("error.password_mismatch") if mismatch else "")
        self.hint.setVisible(bool(mismatch))
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return (
            bool(self.username.text().strip())
            and len(self.pw1.text()) >= 6
            and self.pw1.text() == self.pw2.text()
        )


class LicensePage(QWizardPage):
    def __init__(self, result: SetupResult, license_service: LicenseService):
        super().__init__()
        self.result = result
        self.license_service = license_service
        self._activated = False
        self.setTitle(i18n.tr("setup.step.license"))
        lay = QVBoxLayout(self)

        from PyQt6.QtCore import Qt as _Qt
        lay.addWidget(QLabel(i18n.tr("license.fingerprint") + ":"))
        self.fingerprint = QLineEdit(machine_fingerprint())
        self.fingerprint.setReadOnly(True)
        self.fingerprint.setLayoutDirection(_Qt.LayoutDirection.LeftToRight)
        lay.addWidget(self.fingerprint)

        from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
        req_row = QHBoxLayout()
        copy_fp = SecondaryButton(i18n.tr("license.copy_fingerprint")); copy_fp.clicked.connect(self._copy_fp)
        save_req = SecondaryButton(i18n.tr("license.save_request")); save_req.clicked.connect(self._save_request)
        req_row.addWidget(copy_fp); req_row.addWidget(save_req); req_row.addStretch(1)
        lay.addLayout(req_row)

        lay.addWidget(QLabel(i18n.tr("setup.license_key")))
        self.key_input = QPlainTextEdit()
        self.key_input.setPlaceholderText("ZBE1....")
        self.key_input.setMaximumHeight(90)
        self.key_input.setLayoutDirection(_Qt.LayoutDirection.LeftToRight)
        lay.addWidget(self.key_input)

        btn_row = QHBoxLayout()
        self.activate_btn = PrimaryButton(i18n.tr("setup.activate"))
        self.activate_btn.clicked.connect(self._activate)
        self.import_file_btn = SecondaryButton(i18n.tr("license.import_file"))
        self.import_file_btn.clicked.connect(self._import_file)
        btn_row.addWidget(self.activate_btn); btn_row.addWidget(self.import_file_btn); btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)

    def _apply_status(self, st):
        if st.state == LicenseState.ACTIVE:
            self._activated = True
            self.status.setProperty("badge", "success")
            self.status.setText(i18n.tr("license.status.active"))
        else:
            self._activated = False
            self.status.setProperty("badge", "danger")
            self.status.setText(i18n.tr(st.reason_key))
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)
        self.completeChanged.emit()

    def _activate(self):
        key = self.key_input.toPlainText().strip()
        if not key:
            return
        self._apply_status(self.license_service.import_key(
            key, expected_profile=self.result.profile_code, today=date.today()))

    def _import_file(self):
        from PyQt6.QtWidgets import QFileDialog
        from pathlib import Path
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr("license.import_file"), "", "Zenith License (*.zlic)")
        if not path:
            return
        self._apply_status(self.license_service.import_file(
            Path(path).read_text(encoding="utf-8"), expected_profile=self.result.profile_code, today=date.today()))

    def _copy_fp(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.fingerprint.text())

    def _save_request(self):
        from PyQt6.QtWidgets import QFileDialog
        from pathlib import Path
        from zenith.licensing.request import build_request
        from zenith import __version__
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("license.save_request"), f"{self.result.profile_code}.zreq", "Zenith Request (*.zreq)")
        if path:
            req = build_request(self.fingerprint.text().strip(), self.result.profile_code,
                                app_version=__version__, business_name=self.result.business_name)
            Path(path).write_text(req.to_file_json(), encoding="utf-8")

    def isComplete(self) -> bool:
        return self._activated
