"""Sales Returns and Purchase Returns pages.

Each lists the approved source documents; opening one shows its lines with the
remaining returnable quantity and a return-quantity input. Submitting posts a
guarded, atomic return through the service (over-return/duplicate blocked there).
"""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox, QMessageBox,
)
from sqlalchemy import select

from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.db.models import Sale, Purchase, Product, SaleLine, PurchaseLine
from zenith.services.returns import (
    SalesReturnService, PurchaseReturnService, ReturnLineInput,
)
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.common import Toast
from zenith.ui.widgets.data_table import DataTable
from zenith.ui.widgets.inputs import QuantityInput


class _ReturnDialog(QDialog):
    """Lists a document's lines with a return-qty input per line."""

    def __init__(self, ctx, title: str, line_rows: list[dict], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._inputs: dict[int, QuantityInput] = {}
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(title))

        for row in line_rows:
            r = QHBoxLayout()
            r.addWidget(QLabel(row["name"]), 2)
            r.addWidget(QLabel(f'{self.ctx.tr("returns.returnable")}: {row["returnable"]:,.2f}'))
            qty = QuantityInput()
            qty.setMaximum(float(row["returnable"]))
            self._inputs[row["line_id"]] = qty
            r.addWidget(qty)
            lay.addLayout(r)

        buttons = QDialogButtonBox()
        ok = PrimaryButton(ctx.tr("returns.create"))
        cancel = SecondaryButton(ctx.tr("common.cancel"))
        buttons.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        lay.addWidget(buttons)

    def return_lines(self) -> list[ReturnLineInput]:
        out = []
        for line_id, widget in self._inputs.items():
            qty = widget.value_decimal()
            if qty > 0:
                out.append(ReturnLineInput(line_id, qty))
        return out


class SalesReturnsPage(BasePage):
    title_key = "returns.sales_title"
    subtitle_key = "returns.sales_subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.content.addWidget(QLabel(ctx.tr("returns.pick_doc")))
        self.table = DataTable(
            [ctx.tr("sales.col.invoice"), ctx.tr("common.date"), ctx.tr("sales.col.total")],
            empty_text=ctx.tr("common.empty"),
        )
        self.table.rowActivated.connect(self._open)
        self.content.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as s:
            sales = s.scalars(
                select(Sale).where(Sale.status == "approved").order_by(Sale.id.desc()).limit(200)
            ).all()
            for sale in sales:
                rows.append((sale.invoice_no, sale.date.isoformat(), f"{sale.total:,.2f}"))
                ids.append(sale.id)
        self.table.set_rows(rows, ids)

    def _open(self, sale_id):
        with session_scope(self.ctx.db) as s:
            sale = s.get(Sale, sale_id)
            line_rows = []
            for line in sale.lines:
                if line.returnable_qty <= 0:
                    continue
                product = s.get(Product, line.product_id)
                line_rows.append({"line_id": line.id, "name": product.name if product else "?",
                                  "returnable": line.returnable_qty})
        if not line_rows:
            return
        dlg = _ReturnDialog(self.ctx, self.ctx.tr("returns.sales_title"), line_rows, self)
        if not dlg.exec():
            return
        lines = dlg.return_lines()
        if not lines:
            QMessageBox.information(self, self.ctx.tr("common.error"), self.ctx.tr("returns.no_qty"))
            return
        try:
            with session_scope(self.ctx.db) as s:
                SalesReturnService(s).create_return(self.ctx.user, sale_id, lines)
            Toast.show_message(self, self.ctx.tr("returns.created"), "success")
            self.refresh()
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))


class PurchaseReturnsPage(BasePage):
    title_key = "returns.purchase_title"
    subtitle_key = "returns.purchase_subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.content.addWidget(QLabel(ctx.tr("returns.pick_doc")))
        self.table = DataTable(
            ["#", ctx.tr("common.date"), ctx.tr("purchase.grand_total")],
            empty_text=ctx.tr("common.empty"),
        )
        self.table.rowActivated.connect(self._open)
        self.content.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as s:
            purchases = s.scalars(
                select(Purchase).where(Purchase.status == "approved").order_by(Purchase.id.desc()).limit(200)
            ).all()
            for po in purchases:
                rows.append((po.doc_no, po.date.isoformat(), f"{po.total:,.2f}"))
                ids.append(po.id)
        self.table.set_rows(rows, ids)

    def _open(self, purchase_id):
        with session_scope(self.ctx.db) as s:
            po = s.get(Purchase, purchase_id)
            line_rows = []
            for line in po.lines:
                if line.returnable_qty <= 0:
                    continue
                product = s.get(Product, line.product_id)
                line_rows.append({"line_id": line.id, "name": product.name if product else "?",
                                  "returnable": line.returnable_qty})
        if not line_rows:
            return
        dlg = _ReturnDialog(self.ctx, self.ctx.tr("returns.purchase_title"), line_rows, self)
        if not dlg.exec():
            return
        lines = dlg.return_lines()
        if not lines:
            QMessageBox.information(self, self.ctx.tr("common.error"), self.ctx.tr("returns.no_qty"))
            return
        try:
            with session_scope(self.ctx.db) as s:
                PurchaseReturnService(s).create_return(self.ctx.user, purchase_id, lines)
            Toast.show_message(self, self.ctx.tr("returns.created"), "success")
            self.refresh()
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))
