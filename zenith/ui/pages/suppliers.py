"""Suppliers page: list + create form, wired to PartyService."""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QDialog, QLineEdit, QDoubleSpinBox, QDialogButtonBox, QLabel,
)

from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.services.parties import PartyService
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.common import SearchInput, FormSection, Toast
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.data_table import DataTable


class SupplierDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(ctx.tr("suppliers.new"))
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        sec = FormSection(ctx.tr("products.section.basic"))
        self.name = QLineEdit(); self.phone = QLineEdit(); self.address = QLineEdit()
        self.opening = QDoubleSpinBox(); self.opening.setMaximum(1_000_000_000); self.opening.setDecimals(2)
        sec.add_row(ctx.tr("common.name"), self.name, required=True, span=True)
        sec.add_row(ctx.tr("common.phone"), self.phone, span=True)
        sec.add_row(ctx.tr("common.address"), self.address, span=True)
        sec.add_row(ctx.tr("customers.field.opening_balance"), self.opening, span=True)
        lay.addWidget(sec)
        self.error = QLabel(""); self.error.setProperty("badge", "danger")
        self.error.setWordWrap(True); self.error.setVisible(False)
        lay.addWidget(self.error)
        buttons = QDialogButtonBox()
        save = PrimaryButton(ctx.tr("common.save")); cancel = SecondaryButton(ctx.tr("common.cancel"))
        buttons.addButton(save, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        save.clicked.connect(self._save); cancel.clicked.connect(self.reject)
        lay.addWidget(buttons); self.name.setFocus()

    def _save(self):
        try:
            with session_scope(self.ctx.db) as session:
                PartyService(session).create_supplier(
                    self.ctx.user, name=self.name.text(), phone=self.phone.text(),
                    address=self.address.text(), opening_balance=Decimal(str(self.opening.value())),
                )
            self.accept()
        except ZenithError as exc:
            self.error.setText(self.ctx.tr(exc.message_key)); self.error.setVisible(True)


class SuppliersPage(BasePage):
    title_key = "suppliers.title"
    subtitle_key = "suppliers.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("suppliers.new")).clicked.connect(self._new)
        bar = QHBoxLayout()
        self.search = SearchInput(ctx.tr("common.search"))
        self.search.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.search); bar.addStretch(1)
        self.content.addLayout(bar)
        self.table = DataTable(
            [ctx.tr("common.name"), ctx.tr("common.phone"), ctx.tr("customers.col.balance")],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new(self):
        if SupplierDialog(self.ctx, self).exec():
            Toast.show_message(self, self.ctx.tr("customers.saved"), "success")
            self.refresh()

    def refresh(self):
        term = self.search.text() if hasattr(self, "search") else ""
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            for s in PartyService(session).search_suppliers(term):
                rows.append((s.name, s.phone, f"{s.balance:,.2f}"))
                ids.append(s.id)
        self.table.set_rows(rows, ids)
