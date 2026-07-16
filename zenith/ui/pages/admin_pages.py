"""Administration pages: License status, Backup & Restore, Users, Settings.

All wired to real services (LicenseService, backup module, AuthService/DB).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPlainTextEdit, QComboBox,
    QFileDialog, QMessageBox, QTabWidget, QWidget,
)
from PyQt6.QtGui import QPixmap

from sqlalchemy import select

from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.db.models import User, Role
from zenith.licensing.service import LicenseState
from zenith.services import backup as backup_service
from zenith.services.business_identity import BusinessIdentityService
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
        self.tabs = QTabWidget()
        self.tabs.addTab(self._business_tab(), ctx.tr("settings.tab.business"))
        self.tabs.addTab(self._preferences_tab(), ctx.tr("settings.tab.preferences"))
        self.content.addWidget(self.tabs, 1)
        self._load_business()

    # -- Business Information tab ------------------------------------------
    def _business_tab(self) -> QWidget:
        ctx = self.ctx
        host = QWidget()
        lay = QVBoxLayout(host)

        ident = FormSection(ctx.tr("business.section.identity"))
        self.name_fa = QLineEdit(); self.name_en = QLineEdit(); self.owner = QLineEdit()
        self.slogan = QLineEdit()
        ident.add_row(ctx.tr("business.name_fa"), self.name_fa, required=True, span=True)
        ident.add_row(ctx.tr("business.name_en"), self.name_en, span=True)
        ident.add_row(ctx.tr("business.owner"), self.owner, span=True)
        ident.add_row(ctx.tr("business.slogan"), self.slogan, span=True)
        lay.addWidget(ident)

        # logo row
        logo_row = QHBoxLayout()
        self.logo_preview = QLabel("—")
        self.logo_preview.setFixedSize(96, 96)
        self.logo_preview.setStyleSheet("border:1px solid #ccc;border-radius:8px;")
        logo_row.addWidget(self.logo_preview)
        logo_btns = QVBoxLayout()
        up = SecondaryButton(ctx.tr("business.upload_logo")); up.clicked.connect(self._upload_logo)
        rm = SecondaryButton(ctx.tr("business.remove_logo")); rm.clicked.connect(self._remove_logo)
        logo_btns.addWidget(QLabel(ctx.tr("business.logo")))
        logo_btns.addWidget(up); logo_btns.addWidget(rm); logo_btns.addStretch(1)
        logo_row.addLayout(logo_btns); logo_row.addStretch(1)
        lay.addLayout(logo_row)

        contact = FormSection(ctx.tr("business.section.contact"))
        self.phone = QLineEdit(); self.phone2 = QLineEdit(); self.whatsapp = QLineEdit()
        self.email = QLineEdit(); self.website = QLineEdit()
        self.address_fa = QLineEdit(); self.address_en = QLineEdit()
        self.province = QLineEdit(); self.city = QLineEdit(); self.district = QLineEdit()
        self.reg_no = QLineEdit(); self.tax_no = QLineEdit()
        contact.add_row(ctx.tr("business.phone"), self.phone)
        contact.add_row(ctx.tr("business.phone2"), self.phone2)
        contact.add_row(ctx.tr("business.whatsapp"), self.whatsapp)
        contact.add_row(ctx.tr("business.email"), self.email)
        contact.add_row(ctx.tr("business.website"), self.website, span=True)
        contact.add_row(ctx.tr("business.address_fa"), self.address_fa, span=True)
        contact.add_row(ctx.tr("business.address_en"), self.address_en, span=True)
        contact.add_row(ctx.tr("business.province"), self.province)
        contact.add_row(ctx.tr("business.city"), self.city)
        contact.add_row(ctx.tr("business.district"), self.district)
        contact.add_row(ctx.tr("business.reg_no"), self.reg_no)
        contact.add_row(ctx.tr("business.tax_no"), self.tax_no)
        lay.addWidget(contact)

        docs = FormSection(ctx.tr("business.section.documents"))
        self.footer_fa = QLineEdit(); self.footer_en = QLineEdit()
        self.terms_fa = QLineEdit(); self.terms_en = QLineEdit()
        docs.add_row(ctx.tr("business.footer_fa"), self.footer_fa, span=True)
        docs.add_row(ctx.tr("business.footer_en"), self.footer_en, span=True)
        docs.add_row(ctx.tr("business.terms_fa"), self.terms_fa, span=True)
        docs.add_row(ctx.tr("business.terms_en"), self.terms_en, span=True)
        lay.addWidget(docs)

        save = PrimaryButton(ctx.tr("common.save"))
        save.clicked.connect(self._save_business)
        lay.addWidget(save)
        lay.addStretch(1)
        return host

    def _preferences_tab(self) -> QWidget:
        ctx = self.ctx
        host = QWidget()
        lay = QVBoxLayout(host)
        sec = FormSection(ctx.tr("settings.tab.preferences"))
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
        lay.addWidget(sec)
        apply = PrimaryButton(ctx.tr("common.save"))
        apply.clicked.connect(self._apply_prefs)
        lay.addWidget(apply)
        lay.addStretch(1)
        return host

    _BFIELDS = {
        "name_fa": "business_name", "name_en": "business_name_en", "owner": "owner_name",
        "slogan": "slogan", "phone": "phone", "phone2": "phone_secondary",
        "whatsapp": "whatsapp", "email": "email", "website": "website",
        "address_fa": "address", "address_en": "address_en", "province": "province",
        "city": "city", "district": "district", "reg_no": "registration_no", "tax_no": "tax_no",
        "footer_fa": "invoice_footer_fa", "footer_en": "invoice_footer_en",
        "terms_fa": "terms_fa", "terms_en": "terms_en",
    }

    def _load_business(self):
        from zenith.db.models import BusinessSettings
        with session_scope(self.ctx.db) as s:
            bs = s.scalar(select(BusinessSettings).limit(1))
            if not bs:
                return
            for widget_name, col in self._BFIELDS.items():
                getattr(self, widget_name).setText(getattr(bs, col) or "")
            self._render_logo(bs.logo_path)

    def _render_logo(self, path):
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self.logo_preview.setPixmap(pix.scaled(
                    96, 96, aspectRatioMode=1, transformMode=1))
                return
        self.logo_preview.setText("—")

    def _save_business(self):
        fields = {col: getattr(self, w).text() for w, col in self._BFIELDS.items()}
        try:
            with session_scope(self.ctx.db) as s:
                BusinessIdentityService(s).update(self.ctx.user, **fields)
            Toast.show_message(self, self.ctx.tr("business.saved"), "success")
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))

    def _upload_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.ctx.tr("business.upload_logo"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            with session_scope(self.ctx.db) as s:
                stored = BusinessIdentityService(s).set_logo(self.ctx.user, path)
            self._render_logo(stored)
            Toast.show_message(self, self.ctx.tr("business.saved"), "success")
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))

    def _remove_logo(self):
        with session_scope(self.ctx.db) as s:
            BusinessIdentityService(s).remove_logo(self.ctx.user)
        self._render_logo(None)

    def _apply_prefs(self):
        self.ctx.set_theme(self.theme.currentData())
        Toast.show_message(self, self.ctx.tr("common.ok"), "success")
