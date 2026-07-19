"""New Purchase and New Sale / POS pages.

Both let the user search an existing product (name / code / barcode) and add it as
a line -- repeated purchases of the same product reuse the existing Product Master
and increase its stock via stock transactions (never a duplicate product, never a
hand-edited stock field). A "Create new product" action opens the product dialog
without losing the in-progress document and auto-selects the new product.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QComboBox, QLabel, QCompleter, QMessageBox, QCheckBox,
)

from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.services import inventory
from zenith.services.catalog import CatalogService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.sales import SalesService, LineInput
from zenith.ui.pages.base import BasePage
from zenith.ui.pages.products import ProductDialog
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.common import Card, Toast
from zenith.ui.widgets.data_table import DataTable
from zenith.ui.widgets.inputs import QuantityInput, CurrencyInput


class _LineEditorMixin:
    """Shared product-picker + lines-table machinery for both pages."""

    def _build_product_picker(self, ctx):
        self._products: dict[str, int] = {}      # display -> product_id
        self._prices: dict[int, Decimal] = {}     # product_id -> default price
        picker = Card()
        row = QHBoxLayout()
        self.product_combo = QComboBox()
        self.product_combo.setEditable(True)
        self.product_combo.setMinimumWidth(280)
        self.product_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = self.product_combo.completer()
        if completer:
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        row.addWidget(self.product_combo, 1)

        self.qty_input = QuantityInput()
        self.qty_input.setValue(1)
        row.addWidget(QLabel(ctx.tr("purchase.qty")))
        row.addWidget(self.qty_input)

        self.price_input = CurrencyInput(currency=ctx.identity().currency if _safe_currency(ctx) else "")
        row.addWidget(QLabel(ctx.tr("purchase.unit_price")))
        row.addWidget(self.price_input)

        add = PrimaryButton(ctx.tr("purchase.add_line"))
        add.clicked.connect(self._add_line)
        row.addWidget(add)
        new_prod = SecondaryButton(ctx.tr("purchase.new_product"))
        new_prod.clicked.connect(self._create_product)
        row.addWidget(new_prod)
        picker.body().addLayout(row)
        self.product_combo.currentIndexChanged.connect(self._on_product_selected)
        return picker

    def _reload_products(self, select_id: int | None = None):
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self._products.clear()
        self._prices.clear()
        with session_scope(self.ctx.db) as s:
            for p in CatalogService(s).search("", limit=1000):
                label = f"{p.name} — {p.code}" + (f" [{p.barcode}]" if p.barcode else "")
                self.product_combo.addItem(label, p.id)
                self._products[label] = p.id
                self._prices[p.id] = self._default_price(p)
        self.product_combo.blockSignals(False)
        if select_id is not None:
            idx = self.product_combo.findData(select_id)
            if idx >= 0:
                self.product_combo.setCurrentIndex(idx)

    def _on_product_selected(self, *_):
        pid = self.product_combo.currentData()
        if pid in self._prices:
            self.price_input.setValue(float(self._prices[pid]))

    def _create_product(self):
        dlg = ProductDialog(self.ctx, self)
        if dlg.exec():
            # auto-select the just-created product without losing the document
            self._reload_products(select_id=dlg.created_id)
            Toast.show_message(self, self.ctx.tr("products.saved"), "success")

    def _refresh_lines_table(self):
        rows = [(r["name"], f'{r["qty"]:,.2f}', f'{r["price"]:,.2f}', f'{r["total"]:,.2f}')
                for r in self._lines]
        self.lines_table.set_rows(rows, list(range(len(self._lines))))
        total = sum((r["total"] for r in self._lines), Decimal("0"))
        self.total_label.setText(f"{self.ctx.tr('purchase.grand_total')}: {total:,.2f}")


def _safe_currency(ctx) -> bool:
    try:
        ctx.identity()
        return True
    except Exception:
        return False


class NewPurchasePage(BasePage, _LineEditorMixin):
    title_key = "purchase.title"
    subtitle_key = "purchase.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._lines: list[dict] = []

        top = QHBoxLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(240)
        top.addWidget(QLabel(ctx.tr("purchase.supplier")))
        top.addWidget(self.supplier_combo)
        top.addStretch(1)
        self.content.addLayout(top)

        self.content.addWidget(self._build_product_picker(ctx))

        self.lines_table = DataTable(
            [ctx.tr("products.col.name"), ctx.tr("purchase.qty"),
             ctx.tr("purchase.unit_price"), ctx.tr("purchase.line_total")],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.lines_table, 1)

        bottom = QHBoxLayout()
        self.total_label = QLabel(f"{ctx.tr('purchase.grand_total')}: 0.00")
        self.total_label.setProperty("role", "h2")
        bottom.addWidget(self.total_label)
        bottom.addStretch(1)
        approve = PrimaryButton(ctx.tr("purchase.approve"))
        approve.clicked.connect(self._approve)
        bottom.addWidget(approve)
        self.content.addLayout(bottom)

        self.refresh()

    def _default_price(self, product) -> Decimal:
        return Decimal(str(product.purchase_price or 0))

    def refresh(self):
        self.supplier_combo.clear()
        with session_scope(self.ctx.db) as s:
            for sup in PartyService(s).search_suppliers("", limit=1000):
                self.supplier_combo.addItem(sup.name, sup.id)
        self._reload_products()
        self._lines = []
        self._refresh_lines_table()

    def _add_line(self):
        pid = self.product_combo.currentData()
        if pid is None:
            QMessageBox.information(self, self.ctx.tr("common.error"), self.ctx.tr("error.select_product"))
            return
        qty = self.qty_input.value_decimal()
        price = self.price_input.value_decimal()
        if qty <= 0:
            return
        self._lines.append({"product_id": pid, "name": self.product_combo.currentText(),
                            "qty": qty, "price": price, "total": qty * price})
        self._refresh_lines_table()

    def _approve(self):
        if not self._lines:
            QMessageBox.information(self, self.ctx.tr("common.error"), self.ctx.tr("error.no_lines"))
            return
        supplier_id = self.supplier_combo.currentData()
        lines = [PurchaseLineInput(r["product_id"], r["qty"], r["price"]) for r in self._lines]
        try:
            with session_scope(self.ctx.db) as s:
                svc = PurchaseService(s)
                po = svc.create_purchase(self.ctx.user, supplier_id=supplier_id, lines=lines, paid="0")
                svc.approve_purchase(self.ctx.user, po.id)
            Toast.show_message(self, self.ctx.tr("purchase.approved"), "success")
            self.refresh()
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))


class NewSalePage(BasePage, _LineEditorMixin):
    title_key = "sale.new_title"
    subtitle_key = "sale.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._lines: list[dict] = []

        top = QHBoxLayout()
        self.customer_combo = QComboBox()
        self.customer_combo.setMinimumWidth(240)
        # searchable: type a name/phone to filter the existing customers
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        _cc = self.customer_combo.completer()
        if _cc:
            _cc.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            _cc.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        top.addWidget(QLabel(ctx.tr("sale.customer")))
        top.addWidget(self.customer_combo)
        new_cust = SecondaryButton(ctx.tr("customers.new"))
        new_cust.clicked.connect(self._create_customer)
        top.addWidget(new_cust)
        self.credit_check = QCheckBox(ctx.tr("sale.is_credit"))
        top.addWidget(self.credit_check)
        top.addStretch(1)
        self.content.addLayout(top)

        self.content.addWidget(self._build_product_picker(ctx))

        self.lines_table = DataTable(
            [ctx.tr("products.col.name"), ctx.tr("purchase.qty"),
             ctx.tr("common.price"), ctx.tr("purchase.line_total")],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.lines_table, 1)

        bottom = QHBoxLayout()
        self.total_label = QLabel(f"{ctx.tr('purchase.grand_total')}: 0.00")
        self.total_label.setProperty("role", "h2")
        bottom.addWidget(self.total_label)
        bottom.addWidget(QLabel(ctx.tr("sale.paid")))
        self.paid_input = CurrencyInput()
        bottom.addWidget(self.paid_input)
        bottom.addStretch(1)
        complete = PrimaryButton(ctx.tr("sale.complete"))
        complete.clicked.connect(self._complete)
        bottom.addWidget(complete)
        self.content.addLayout(bottom)

        self.refresh()

    def _default_price(self, product) -> Decimal:
        return Decimal(str(product.sale_price or 0))

    def _reload_customers(self, select_id: int | None = None):
        self.customer_combo.blockSignals(True)
        self.customer_combo.clear()
        self.customer_combo.addItem(self.ctx.tr("sale.walk_in"), None)
        with session_scope(self.ctx.db) as s:
            for c in PartyService(s).search_customers("", limit=1000):
                label = c.name + (f" — {c.phone}" if c.phone else "")
                self.customer_combo.addItem(label, c.id)
        self.customer_combo.blockSignals(False)
        if select_id is not None:
            idx = self.customer_combo.findData(select_id)
            if idx >= 0:
                self.customer_combo.setCurrentIndex(idx)

    def _create_customer(self):
        from zenith.ui.pages.customers import CustomerDialog
        dlg = CustomerDialog(self.ctx, self)
        if dlg.exec():
            self._reload_customers(select_id=getattr(dlg, "created_id", None))
            Toast.show_message(self, self.ctx.tr("customers.saved"), "success")

    def refresh(self):
        self._reload_customers()
        self._reload_products()
        self._lines = []
        self._refresh_lines_table()

    def _add_line(self):
        pid = self.product_combo.currentData()
        if pid is None:
            QMessageBox.information(self, self.ctx.tr("common.error"), self.ctx.tr("error.select_product"))
            return
        qty = self.qty_input.value_decimal()
        price = self.price_input.value_decimal()
        if qty <= 0:
            return
        self._lines.append({"product_id": pid, "name": self.product_combo.currentText(),
                            "qty": qty, "price": price, "total": qty * price})
        self._refresh_lines_table()

    def _complete(self):
        if not self._lines:
            QMessageBox.information(self, self.ctx.tr("common.error"), self.ctx.tr("error.no_lines"))
            return
        customer_id = self.customer_combo.currentData()
        is_credit = self.credit_check.isChecked()
        lines = [LineInput(r["product_id"], r["qty"], r["price"]) for r in self._lines]
        try:
            with session_scope(self.ctx.db) as s:
                svc = SalesService(s)
                sale = svc.create_sale(self.ctx.user, customer_id=customer_id, lines=lines,
                                       is_credit=is_credit, paid=str(self.paid_input.value_decimal()))
                svc.approve_sale(self.ctx.user, sale.id)
            Toast.show_message(self, self.ctx.tr("sale.completed"), "success")
            self.refresh()
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))
