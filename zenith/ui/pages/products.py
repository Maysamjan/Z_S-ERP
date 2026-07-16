"""Products page: searchable list + a sectioned, profile-aware create form.

Fully wired to ``CatalogService`` and the inventory service (for the stock column).
The create form shows extra sections/fields only when the active profile enables
them (e.g. medicine details for Pharmacy, wholesale price for Wholesale).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QDialog, QLineEdit, QDialogButtonBox, QMessageBox,
)

from zenith.core.exceptions import ZenithError, ValidationError
from zenith.db.base import session_scope
from zenith.profiles.features import F_WHOLESALE_PRICING, F_PHARMACY_FIELDS
from zenith.services import inventory
from zenith.services.catalog import CatalogService
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.common import SearchInput, FormSection, Toast
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.data_table import DataTable
from zenith.ui.widgets.inputs import CurrencyInput, QuantityInput


class ProductDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.created_id: int | None = None
        self.setWindowTitle(ctx.tr("products.new"))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)

        basic = FormSection(ctx.tr("products.section.basic"))
        self.code = QLineEdit()
        self.name = QLineEdit()
        self.barcode = QLineEdit()
        basic.add_row(ctx.tr("products.field.code"), self.code, required=True, span=True)
        basic.add_row(ctx.tr("products.field.name"), self.name, required=True, span=True)
        basic.add_row(ctx.tr("products.field.barcode"), self.barcode, span=True)
        lay.addWidget(basic)

        pricing = FormSection(ctx.tr("products.section.pricing"))
        self.purchase = self._money()
        self.sale = self._money()
        pricing.add_row(ctx.tr("products.field.purchase_price"), self.purchase)
        pricing.add_row(ctx.tr("products.field.sale_price"), self.sale)
        self.wholesale = None
        if ctx.profile.has_feature(F_WHOLESALE_PRICING):
            self.wholesale = self._money()
            pricing.add_row(ctx.tr("products.field.wholesale_price"), self.wholesale)
        lay.addWidget(pricing)

        inv = FormSection(ctx.tr("products.section.inventory"))
        self.min_stock = QuantityInput()
        inv.add_row(ctx.tr("products.field.min_stock"), self.min_stock)
        lay.addWidget(inv)

        self.generic = self.trade = self.manufacturer = None
        if ctx.profile.has_feature(F_PHARMACY_FIELDS):
            pharm = FormSection(ctx.tr("products.section.pharmacy"))
            self.generic = QLineEdit()
            self.trade = QLineEdit()
            self.manufacturer = QLineEdit()
            pharm.add_row(ctx.tr("products.field.generic_name"), self.generic, span=True)
            pharm.add_row(ctx.tr("products.field.trade_name"), self.trade, span=True)
            pharm.add_row(ctx.tr("products.field.manufacturer"), self.manufacturer, span=True)
            lay.addWidget(pharm)

        self.error = self._error_label()
        lay.addWidget(self.error)

        buttons = QDialogButtonBox()
        save = PrimaryButton(ctx.tr("common.save"))
        cancel = SecondaryButton(ctx.tr("common.cancel"))
        buttons.addButton(save, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        lay.addWidget(buttons)

        self.code.setFocus()

    def _money(self) -> CurrencyInput:
        return CurrencyInput()

    def _error_label(self):
        from PyQt6.QtWidgets import QLabel
        lbl = QLabel("")
        lbl.setProperty("badge", "danger")
        lbl.setWordWrap(True)
        lbl.setVisible(False)
        return lbl

    def _save(self):
        fields = dict(
            code=self.code.text(), name=self.name.text(), barcode=self.barcode.text().strip() or None,
            purchase_price=Decimal(str(self.purchase.value())),
            sale_price=Decimal(str(self.sale.value())),
            min_stock=Decimal(str(self.min_stock.value())),
        )
        if self.wholesale is not None:
            fields["wholesale_price"] = Decimal(str(self.wholesale.value()))
        if self.generic is not None:
            fields["generic_name"] = self.generic.text().strip() or None
            fields["trade_name"] = self.trade.text().strip() or None
            fields["manufacturer"] = self.manufacturer.text().strip() or None
            fields["batch_tracked"] = True
        self._persist(fields, allow_similar=False)

    def _persist(self, fields: dict, allow_similar: bool) -> None:
        try:
            with session_scope(self.ctx.db) as session:
                product = CatalogService(session).create_product(
                    self.ctx.user, allow_similar=allow_similar, **fields)
                self.created_id = product.id
            self.accept()
        except ValidationError as exc:
            if exc.message_key == "error.duplicate_similar":
                # Offer to reuse-or-create; genuinely different items can proceed.
                choice = QMessageBox.question(
                    self, self.ctx.tr("products.new"),
                    self.ctx.tr("error.duplicate_similar") + "\n\n" + self.ctx.tr("common.add") + "?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if choice == QMessageBox.StandardButton.Yes:
                    self._persist(fields, allow_similar=True)
                return
            self.error.setText(self.ctx.tr(exc.message_key))
            self.error.setVisible(True)
        except ZenithError as exc:
            self.error.setText(self.ctx.tr(exc.message_key))
            self.error.setVisible(True)


class ProductsPage(BasePage):
    title_key = "products.title"
    subtitle_key = "products.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("products.new")).clicked.connect(self._new_product)

        toolbar = QHBoxLayout()
        self.search = SearchInput(ctx.tr("common.search"))
        self.search.textChanged.connect(self._reload)
        toolbar.addWidget(self.search)
        toolbar.addStretch(1)
        self.content.addLayout(toolbar)

        self.table = DataTable(
            [ctx.tr("products.col.code"), ctx.tr("products.col.name"),
             ctx.tr("products.col.price"), ctx.tr("products.col.stock")],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new_product(self):
        dlg = ProductDialog(self.ctx, self)
        if dlg.exec():
            Toast.show_message(self, self.ctx.tr("products.saved"), "success")
            self.refresh()

    def _reload(self):
        self.refresh()

    def refresh(self):
        term = self.search.text() if hasattr(self, "search") else ""
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            for p in CatalogService(session).search(term):
                stock = inventory.balance(session, p.id)
                rows.append((p.code, p.name, f"{p.sale_price:,.2f}", f"{stock:,.2f}"))
                ids.append(p.id)
        self.table.set_rows(rows, ids)
