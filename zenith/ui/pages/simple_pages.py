"""Smaller, read/query-oriented pages: sales list, stock balance, audit log.

All are wired to real queries. None are placeholders -- each shows live data with
an empty state when there is nothing yet.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout

from sqlalchemy import select, func

from zenith.db.base import session_scope
from zenith.db.models import Sale, Customer, Product, StockItem, AuditLog
from zenith.services import inventory
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.common import SearchInput
from zenith.ui.widgets.data_table import DataTable


_STATUS_BADGE = {
    "approved": ("success", "common.status"),
    "draft": ("muted", "common.status"),
    "returned": ("warning", "common.status"),
    "cancelled": ("danger", "common.status"),
}


class SalesListPage(BasePage):
    title_key = "sales.title"
    subtitle_key = "sales.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("print.preview")).clicked.connect(self._preview_selected)
        self.table = DataTable(
            [ctx.tr("sales.col.invoice"), ctx.tr("common.date"), ctx.tr("sales.col.customer"),
             ctx.tr("sales.col.total"), ctx.tr("sales.col.status")],
            empty_text=ctx.tr("common.empty"),
        )
        # Double-click a sale to open the branded print preview with its real data.
        self.table.rowActivated.connect(self._open_preview)
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _preview_selected(self):
        sale_id = self.table.selected_id()
        if sale_id is not None:
            self._open_preview(sale_id)

    def _open_preview(self, sale_id):
        from zenith.ui.dialogs.print_preview import SalePrintPreviewDialog
        SalePrintPreviewDialog(self.ctx, sale_id, self).exec()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            sales = session.scalars(select(Sale).order_by(Sale.id.desc()).limit(200)).all()
            cust_names = dict(session.execute(select(Customer.id, Customer.name)).all())
            for s in sales:
                rows.append((
                    s.invoice_no, s.date.isoformat(),
                    cust_names.get(s.customer_id, "-"),
                    f"{s.total:,.2f}", self.ctx.tr(f"license.status.{s.status}") if False else s.status,
                ))
                ids.append(s.id)
        self.table.set_rows(rows, ids)


class StockBalancePage(BasePage):
    title_key = "module.stock_balance"
    subtitle_key = "products.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.search = SearchInput(ctx.tr("common.search"))
        self.search.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.search); bar.addStretch(1)
        self.content.addLayout(bar)
        self.table = DataTable(
            [ctx.tr("products.col.code"), ctx.tr("products.col.name"),
             ctx.tr("products.col.stock"), ctx.tr("products.field.min_stock")],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        term = (self.search.text() if hasattr(self, "search") else "").strip().lower()
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            products = session.scalars(
                select(Product).where(Product.is_deleted == False).order_by(Product.name)  # noqa: E712
            ).all()
            for p in products:
                if term and term not in p.name.lower() and term not in p.code.lower():
                    continue
                stock = inventory.balance(session, p.id)
                rows.append((p.code, p.name, f"{stock:,.2f}", f"{p.min_stock:,.2f}"))
                ids.append(p.id)
        self.table.set_rows(rows, ids)


class AuditLogPage(BasePage):
    title_key = "audit.title"
    subtitle_key = "audit.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.table = DataTable(
            [ctx.tr("common.date"), "User", "Action", "Detail"],
            empty_text=ctx.tr("common.empty"),
        )
        self.content.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            logs = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(300)).all()
            for a in logs:
                rows.append((a.at.strftime("%Y-%m-%d %H:%M"), a.username or "-", a.action, a.detail))
                ids.append(a.id)
        self.table.set_rows(rows, ids)
