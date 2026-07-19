"""Customers module: list, create/edit, and the customer account screen.

The account screen is the heart of customer credit management: it shows the live
balance (from the authoritative ledger), aggregate purchases/payments/returns, a
full running-balance statement, and lets the operator receive a payment or print
a branded statement -- all wired to the real services, never sample data.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QDialog, QLineEdit, QDialogButtonBox, QLabel,
    QComboBox, QCheckBox, QGridLayout,
)

from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.services import customer_ledger
from zenith.services.finance import AccountService, ReceiptService
from zenith.services.parties import PartyService
from zenith.ui.dialogs.print_preview import StatementPreviewDialog
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.common import FormSection, MetricCard, SearchInput, Toast
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.data_table import DataTable
from zenith.ui.widgets.inputs import CurrencyInput


class CustomerDialog(QDialog):
    """Create or edit a customer, including the commercial identity fields."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(ctx.tr("customers.new"))
        self.setMinimumWidth(540)
        lay = QVBoxLayout(self)

        sec = FormSection(ctx.tr("products.section.basic"))
        self.name = QLineEdit()
        self.business_name = QLineEdit()
        self.phone = QLineEdit()
        self.address = QLineEdit()
        sec.add_row(ctx.tr("common.name"), self.name, required=True, span=True)
        sec.add_row(ctx.tr("customers.field.business_name"), self.business_name, span=True)
        sec.add_row(ctx.tr("common.phone"), self.phone, span=True)
        sec.add_row(ctx.tr("common.address"), self.address, span=True)
        lay.addWidget(sec)

        pay = FormSection(ctx.tr("products.section.pricing"))
        self.opening = CurrencyInput()
        self.opening_type = QComboBox()
        self.opening_type.addItem(ctx.tr("customers.owed_to_business"), "owed_to_business")
        self.opening_type.addItem(ctx.tr("customers.owed_to_customer"), "owed_to_customer")
        self.limit = CurrencyInput()
        self.cash_only = QCheckBox(ctx.tr("customers.is_cash_customer"))
        pay.add_row(ctx.tr("customers.field.opening_balance"), self.opening)
        pay.add_row(ctx.tr("customers.field.opening_balance_type"), self.opening_type)
        pay.add_row(ctx.tr("customers.field.credit_limit"), self.limit)
        pay.add_row("", self.cash_only, span=True)
        lay.addWidget(pay)

        self.error = QLabel(""); self.error.setProperty("badge", "danger")
        self.error.setWordWrap(True); self.error.setVisible(False)
        lay.addWidget(self.error)

        buttons = QDialogButtonBox()
        save = PrimaryButton(ctx.tr("common.save"))
        cancel = SecondaryButton(ctx.tr("common.cancel"))
        buttons.addButton(save, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        lay.addWidget(buttons)
        self.name.setFocus()

    def _save(self):
        try:
            with session_scope(self.ctx.db) as session:
                c = PartyService(session).create_customer(
                    self.ctx.user, name=self.name.text(), phone=self.phone.text(),
                    address=self.address.text(),
                    opening_balance=self.opening.value_decimal(),
                    opening_balance_type=self.opening_type.currentData(),
                    credit_limit=self.limit.value_decimal(),
                    is_cash_customer=self.cash_only.isChecked(),
                    business_name=self.business_name.text().strip(),
                )
                self.created_id = c.id
            self.accept()
        except ZenithError as exc:
            self.error.setText(self.ctx.tr(exc.message_key)); self.error.setVisible(True)


class _ReceivePaymentDialog(QDialog):
    """Minimal receive-payment form used from the account screen."""

    def __init__(self, ctx, customer_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.customer_id = customer_id
        self.setWindowTitle(ctx.tr("finance.receipt_voucher"))
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        sec = FormSection(ctx.tr("finance.receipt_voucher"))
        self.amount = CurrencyInput()
        self.account = QComboBox()
        with session_scope(ctx.db) as s:
            for acc in AccountService(s).list_accounts(active_only=True):
                self.account.addItem(acc.name, acc.id)
        self.reference = QLineEdit()
        sec.add_row(ctx.tr("common.amount"), self.amount, required=True)
        sec.add_row(ctx.tr("finance.account"), self.account, required=True)
        sec.add_row(ctx.tr("finance.reference"), self.reference)
        lay.addWidget(sec)

        self.error = QLabel(""); self.error.setProperty("badge", "danger")
        self.error.setWordWrap(True); self.error.setVisible(False)
        lay.addWidget(self.error)

        buttons = QDialogButtonBox()
        ok = PrimaryButton(ctx.tr("common.save"))
        cancel = SecondaryButton(ctx.tr("common.cancel"))
        buttons.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self):
        if self.account.currentData() is None:
            self.error.setText(self.ctx.tr("error.no_warehouse")); self.error.setVisible(True)
            return
        try:
            with session_scope(self.ctx.db) as s:
                ReceiptService(s).create_receipt(
                    self.ctx.user, customer_id=self.customer_id,
                    amount=self.amount.value_decimal(), account_id=self.account.currentData(),
                    reference=self.reference.text().strip())
            self.accept()
        except ZenithError as exc:
            self.error.setText(self.ctx.tr(exc.message_key)); self.error.setVisible(True)


class CustomerAccountDialog(QDialog):
    """A customer's account: balance summary, statement, receive payment, print."""

    def __init__(self, ctx, customer_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.customer_id = customer_id
        self.setWindowTitle(ctx.tr("customers.account"))
        self.setMinimumSize(760, 560)
        self._lay = QVBoxLayout(self)

        with session_scope(ctx.db) as s:
            name = PartyService(s).get_customer(customer_id).name
        self._lay.addWidget(QLabel(f"<h3>{name}</h3>"))

        # summary metric cards
        cards = QGridLayout()
        self.card_balance = MetricCard(ctx.tr("customers.col.balance"))
        self.card_purchases = MetricCard(ctx.tr("customers.total_purchases"))
        self.card_payments = MetricCard(ctx.tr("customers.total_payments"))
        self.card_returns = MetricCard(ctx.tr("customers.total_returns"))
        cards.addWidget(self.card_balance, 0, 0)
        cards.addWidget(self.card_purchases, 0, 1)
        cards.addWidget(self.card_payments, 0, 2)
        cards.addWidget(self.card_returns, 0, 3)
        self._lay.addLayout(cards)

        # action bar
        bar = QHBoxLayout()
        receive = PrimaryButton(ctx.tr("finance.receipt_voucher"))
        receive.clicked.connect(self._receive)
        statement = SecondaryButton(ctx.tr("customers.print_statement"))
        statement.clicked.connect(self._print_statement)
        close = SecondaryButton(ctx.tr("common.close"))
        close.clicked.connect(self.accept)
        bar.addWidget(receive); bar.addWidget(statement); bar.addStretch(1); bar.addWidget(close)
        self._lay.addLayout(bar)

        self.table = DataTable(
            [ctx.tr("common.date"), ctx.tr("finance.reference"), ctx.tr("common.description"),
             ctx.tr("common.amount"), ctx.tr("customers.col.balance")],
            empty_text=ctx.tr("common.empty"),
        )
        self._lay.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        with session_scope(self.ctx.db) as s:
            totals = customer_ledger.totals(s, self.customer_id)
            st = customer_ledger.statement(s, self.customer_id)
        self.card_balance.set_value(f"{totals['balance']:,.2f}")
        self.card_purchases.set_value(f"{totals['total_purchases']:,.2f}")
        self.card_payments.set_value(f"{totals['total_payments']:,.2f}")
        self.card_returns.set_value(f"{totals['total_returns']:,.2f}")
        rows = []
        for ln in st.lines:
            day = ln.at.date().isoformat() if hasattr(ln.at, "date") else str(ln.at)
            amount = f"{ln.debit:,.2f}" if ln.debit else f"-{ln.credit:,.2f}"
            rows.append((day, ln.ref_no or "-", ln.description or ln.entry_type,
                         amount, f"{ln.balance:,.2f}"))
        self.table.set_rows(rows, list(range(len(rows))))

    def _receive(self):
        if _ReceivePaymentDialog(self.ctx, self.customer_id, self).exec():
            Toast.show_message(self, self.ctx.tr("common.saved"), "success")
            self.refresh()

    def _print_statement(self):
        StatementPreviewDialog(self.ctx, self.customer_id, parent=self).exec()


class CustomersPage(BasePage):
    title_key = "customers.title"
    subtitle_key = "customers.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("customers.new")).clicked.connect(self._new)
        bar = QHBoxLayout()
        self.search = SearchInput(ctx.tr("customers.search"))
        self.search.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.search); bar.addStretch(1)
        view_btn = SecondaryButton(ctx.tr("customers.view_account"))
        view_btn.clicked.connect(self._open_selected)
        bar.addWidget(view_btn)
        self.content.addLayout(bar)
        self.table = DataTable(
            [ctx.tr("customers.col.name"), ctx.tr("customers.col.phone"),
             ctx.tr("customers.col.balance"), ctx.tr("customers.col.limit")],
            empty_text=ctx.tr("common.empty"),
        )
        self.table.rowActivated.connect(self._open_account)
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new(self):
        if CustomerDialog(self.ctx, self).exec():
            Toast.show_message(self, self.ctx.tr("customers.saved"), "success")
            self.refresh()

    def _open_selected(self):
        cid = self.table.selected_id()
        if cid is not None:
            self._open_account(cid)

    def _open_account(self, customer_id):
        CustomerAccountDialog(self.ctx, customer_id, self).exec()
        self.refresh()

    def refresh(self):
        term = self.search.text() if hasattr(self, "search") else ""
        rows, ids = [], []
        with session_scope(self.ctx.db) as session:
            for c in PartyService(session).search_customers(term):
                rows.append((c.name, c.phone, f"{c.balance:,.2f}", f"{c.credit_limit:,.2f}"))
                ids.append(c.id)
        self.table.set_rows(rows, ids)


class ReceivablesPage(BasePage):
    """Outstanding customer balances with standard aging buckets."""

    title_key = "customers.receivables"
    subtitle_key = "customers.receivables.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.total_card = MetricCard(ctx.tr("customers.col.balance"))
        self.content.addWidget(self.total_card)
        self.table = DataTable(
            [ctx.tr("customers.col.name"), ctx.tr("customers.aging.current"),
             ctx.tr("customers.aging.30"), ctx.tr("customers.aging.60"),
             ctx.tr("customers.aging.over90"), ctx.tr("customers.col.balance")],
            empty_text=ctx.tr("common.empty"),
        )
        self.table.rowActivated.connect(self._open_account)
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _open_account(self, customer_id):
        CustomerAccountDialog(self.ctx, customer_id, self).exec()
        self.refresh()

    def refresh(self):
        rows, ids = [], []
        total = Decimal("0")
        with session_scope(self.ctx.db) as s:
            for a in customer_ledger.outstanding(s):
                rows.append((a.name, f"{a.current:,.2f}", f"{a.days_30:,.2f}",
                             f"{a.days_60:,.2f}", f"{a.over_90:,.2f}", f"{a.balance:,.2f}"))
                ids.append(a.customer_id)
                total += a.balance
        self.total_card.set_value(f"{total:,.2f}")
        self.table.set_rows(rows, ids)
