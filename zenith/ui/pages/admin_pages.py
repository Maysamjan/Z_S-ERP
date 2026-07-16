"""Administration pages: License status, Backup & Restore, Users, Settings.

All wired to real services (LicenseService, backup module, AuthService/DB).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPlainTextEdit, QComboBox,
    QFileDialog, QMessageBox,
)

from sqlalchemy import select

from zenith.db.base import session_scope
from zenith.db.models import User, Role
from zenith.licensing.service import LicenseState
from zenith.services import backup as backup_service
from zenith.ui.i18n import SUPPORTED_LOCALES
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.common import FormSection, Card, Toast
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.data_table import DataTable


class LicensePage(BasePage):
    title_key = "license.title"
    subtitle_key = "license.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.card = Card()
        self.grid = QGridLayout()
        self.card.body().addLayout(self.grid)
        self.content.addWidget(self.card)

        row = QHBoxLayout()
        copy = SecondaryButton(ctx.tr("license.copy_request"))
        copy.clicked.connect(self._copy_request)
        transfer = SecondaryButton(ctx.tr("license.transfer"))
        transfer.clicked.connect(self._transfer)
        row.addWidget(copy); row.addWidget(transfer); row.addStretch(1)
        self.content.addLayout(row)

        imp = Card()
        imp.body().addWidget(QLabel(ctx.tr("setup.license_key")))
        self.key_input = QPlainTextEdit(); self.key_input.setMaximumHeight(80)
        imp.body().addWidget(self.key_input)
        btn = PrimaryButton(ctx.tr("license.import"))
        btn.clicked.connect(self._import)
        imp.body().addWidget(btn)
        self.content.addWidget(imp)
        self.content.addStretch(1)
        self.refresh()

    def _row(self, r, label_key, value):
        self.grid.addWidget(QLabel(self.ctx.tr(label_key)), r, 0)
        v = QLabel(str(value)); v.setProperty("role", "h2")
        self.grid.addWidget(v, r, 1)

    def refresh(self):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        st = self.ctx.license_status()
        lic = st.license
        self._row(0, "license.state", self.ctx.tr(st.reason_key))
        if lic:
            self._row(1, "license.type", lic.license_type)
            self._row(2, "license.customer", lic.customer_name)
            self._row(3, "license.business", lic.business_name)
            self._row(4, "license.profile", lic.profile_code)
            self._row(5, "license.machine", lic.machine_fingerprint[:16] + "…")
            self._row(6, "license.expiry", lic.expiry_date or self.ctx.tr("license.perpetual"))
            if st.days_remaining is not None:
                self._row(7, "license.days_remaining", st.days_remaining)
            self._row(8, "license.max_users", lic.max_users)

    def _copy_request(self):
        from PyQt6.QtWidgets import QApplication
        from zenith.licensing.machine import request_code
        QApplication.clipboard().setText(request_code())
        Toast.show_message(self, self.ctx.tr("setup.copy"), "info")

    def _transfer(self):
        code = self.ctx.license_service.begin_transfer()
        QMessageBox.information(self, self.ctx.tr("license.transfer"), code)

    def _import(self):
        st = self.ctx.license_service.import_key(
            self.key_input.toPlainText().strip(), expected_profile=self.ctx.profile_code
        )
        kind = "success" if st.state == LicenseState.ACTIVE else "danger"
        Toast.show_message(self, self.ctx.tr(st.reason_key), kind)
        self.refresh()


class BackupPage(BasePage):
    title_key = "backup.title"
    subtitle_key = "backup.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        create = PrimaryButton(ctx.tr("backup.create"))
        create.clicked.connect(self._create)
        restore = SecondaryButton(ctx.tr("backup.restore"))
        restore.clicked.connect(self._restore)
        row.addWidget(create); row.addWidget(restore); row.addStretch(1)
        self.content.addLayout(row)
        self.table = DataTable(["File", ctx.tr("common.date")], empty_text=ctx.tr("common.empty"))
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _create(self):
        try:
            info = backup_service.create_backup(self.ctx.profile_code)
            Toast.show_message(self, self.ctx.tr("backup.created", path=info.path.name), "success")
        except Exception as exc:
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))
        self.refresh()

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(self, self.ctx.tr("backup.restore"), "", "Zenith Backup (*.zbak)")
        if not path:
            return
        try:
            from pathlib import Path
            backup_service.restore_backup(Path(path), expected_profile=self.ctx.profile_code)
            Toast.show_message(self, self.ctx.tr("common.ok"), "success")
        except Exception as exc:
            QMessageBox.critical(self, self.ctx.tr("common.error"), str(exc))

    def refresh(self):
        rows, ids = [], []
        for i, p in enumerate(backup_service.list_backups()):
            rows.append((p.name, ""))
            ids.append(i)
        self.table.set_rows(rows, ids)


class UsersPage(BasePage):
    title_key = "users.title"
    subtitle_key = "users.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.table = DataTable(
            [ctx.tr("login.username"), ctx.tr("common.name"), "Role", ctx.tr("common.status")],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            users = session.scalars(select(User).where(User.is_deleted == False)).all()  # noqa: E712
            roles = dict(session.execute(select(Role.id, Role.name)).all())
            for u in users:
                status = self.ctx.tr("common.yes") if u.is_active else self.ctx.tr("common.no")
                rows.append((u.username, u.full_name, roles.get(u.role_id, "-"), status))
                ids.append(u.id)
        self.table.set_rows(rows, ids)


class SettingsPage(BasePage):
    title_key = "settings.title"
    subtitle_key = "settings.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        sec = FormSection(ctx.tr("settings.title"))
        self.language = QComboBox()
        for loc in SUPPORTED_LOCALES:
            self.language.addItem("English" if loc == "en_US" else "دری / فارسی", loc)
        self.language.setCurrentIndex(SUPPORTED_LOCALES.index(ctx.locale) if ctx.locale in SUPPORTED_LOCALES else 0)
        self.theme = QComboBox()
        self.theme.addItem(ctx.tr("nav.theme.light"), "light")
        self.theme.addItem(ctx.tr("nav.theme.dark"), "dark")
        self.theme.setCurrentIndex(0 if ctx.theme_name == "light" else 1)
        sec.add_row(ctx.tr("nav.language"), self.language, span=True)
        sec.add_row(ctx.tr("nav.theme"), self.theme, span=True)
        self.content.addWidget(sec)

        apply = PrimaryButton(ctx.tr("common.save"))
        apply.clicked.connect(self._apply)
        self.content.addWidget(apply)
        self.content.addStretch(1)

    def _apply(self):
        self.ctx.set_theme(self.theme.currentData())
        Toast.show_message(self, self.ctx.tr("common.ok"), "success")
