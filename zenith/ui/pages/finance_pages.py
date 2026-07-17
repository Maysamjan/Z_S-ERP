"""Finance pages: Accounts, Receipts, Supplier Payments, Expenses, Transfers.

All wired to the finance service (atomic, guarded). Money uses the reusable
CurrencyInput. Receipts/payments print a branded voucher; expenses can be
approved (which posts to the account).
"""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QDialog, QLineEdit, QComboBox, QLabel, QDialogButtonBox,
    QMessageBox,
)
from sqlalchemy import select

from zenith.core.exceptions import ZenithError
from zenith.db.base import session_scope
from zenith.db.models import Account, Payment, Expense, AccountTransfer, ExpenseCategory
from zenith.services.finance import (
    AccountService, ReceiptService, SupplierPaymentService, ExpenseService, TransferService,
)
from zenith.services.parties import PartyService
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.buttons import PrimaryButton, SecondaryButton
from zenith.ui.widgets.common import FormSection, Toast
from zenith.ui.widgets.data_table import DataTable
from zenith.ui.widgets.inputs import CurrencyInput


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------
class _AccountDialog(QDialog):
    def __init__(self, ctx, kind_fixed: str | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(ctx.tr("finance.new_account"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        sec = FormSection(ctx.tr("finance.new_account"))
        self.name = QLineEdit()
        self.kind = QComboBox()
        for k in ("cash", "bank", "mobile_money"):
            self.kind.addItem(ctx.tr(f"finance.kind.{k}"), k)
        if kind_fixed:
            idx = self.kind.findData(kind_fixed)
            self.kind.setCurrentIndex(idx); self.kind.setEnabled(False)
        self.opening = CurrencyInput()
        sec.add_row(ctx.tr("common.name"), self.name, required=True, span=True)
        sec.add_row(ctx.tr("finance.kind"), self.kind, span=True)
        sec.add_row(ctx.tr("finance.opening_balance"), self.opening, span=True)
        lay.addWidget(sec)
        self.err = QLabel(""); self.err.setProperty("badge", "danger"); self.err.setVisible(False)
        lay.addWidget(self.err)
        bb = QDialogButtonBox()
        ok = PrimaryButton(ctx.tr("common.save")); cancel = SecondaryButton(ctx.tr("common.cancel"))
        bb.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self._save); cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        try:
            with session_scope(self.ctx.db) as s:
                AccountService(s).create_account(
                    self.ctx.user, name=self.name.text(), kind=self.kind.currentData(),
                    opening_balance=self.opening.value_decimal())
            self.accept()
        except ZenithError as exc:
            self.err.setText(self.ctx.tr(exc.message_key)); self.err.setVisible(True)


class _AccountsPage(BasePage):
    kind_filter: str | None = None

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("finance.new_account")).clicked.connect(self._new)
        self.table = DataTable(
            [ctx.tr("common.name"), ctx.tr("finance.kind"),
             ctx.tr("finance.current_balance"), ctx.tr("finance.active")],
            empty_text=ctx.tr("common.empty"))
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new(self):
        if _AccountDialog(self.ctx, kind_fixed=self.kind_filter, parent=self).exec():
            Toast.show_message(self, self.ctx.tr("finance.saved"), "success"); self.refresh()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as s:
            for a in AccountService(s).list_accounts(kind=self.kind_filter):
                rows.append((a.name, self.ctx.tr(f"finance.kind.{a.kind}"), f"{a.balance:,.2f}",
                             self.ctx.tr("common.yes") if a.is_active else self.ctx.tr("common.no")))
                ids.append(a.id)
        self.table.set_rows(rows, ids)


class CashAccountsPage(_AccountsPage):
    title_key = "finance.accounts_title"
    subtitle_key = "finance.accounts_subtitle"
    kind_filter = "cash"


class BankAccountsPage(_AccountsPage):
    title_key = "finance.accounts_title"
    subtitle_key = "finance.accounts_subtitle"
    kind_filter = "bank"


# --------------------------------------------------------------------------
# Receipts & supplier payments (shared dialog)
# --------------------------------------------------------------------------
class _PartyPaymentDialog(QDialog):
    def __init__(self, ctx, *, is_receipt: bool, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.is_receipt = is_receipt
        title = ctx.tr("finance.new_receipt" if is_receipt else "finance.new_payment")
        self.setWindowTitle(title); self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        sec = FormSection(title)
        self.party = QComboBox()
        self.account = QComboBox()
        self.amount = CurrencyInput()
        self.reference = QLineEdit()
        with session_scope(ctx.db) as s:
            parties = (PartyService(s).search_customers("", limit=1000) if is_receipt
                       else PartyService(s).search_suppliers("", limit=1000))
            for p in parties:
                self.party.addItem(p.name, p.id)
            for a in AccountService(s).list_accounts(active_only=True):
                self.account.addItem(f"{a.name} ({ctx.tr('finance.kind.'+a.kind)})", a.id)
        sec.add_row(ctx.tr("finance.customer" if is_receipt else "finance.supplier"), self.party, span=True)
        sec.add_row(ctx.tr("finance.account"), self.account, span=True)
        sec.add_row(ctx.tr("common.amount"), self.amount, span=True)
        sec.add_row(ctx.tr("finance.reference"), self.reference, span=True)
        lay.addWidget(sec)
        self.err = QLabel(""); self.err.setProperty("badge", "danger"); self.err.setVisible(False)
        lay.addWidget(self.err)
        bb = QDialogButtonBox()
        ok = PrimaryButton(ctx.tr("common.save")); cancel = SecondaryButton(ctx.tr("common.cancel"))
        bb.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self._save); cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        party_id = self.party.currentData()
        account_id = self.account.currentData()
        if party_id is None or account_id is None:
            self.err.setText(self.ctx.tr("error.validation")); self.err.setVisible(True); return
        try:
            with session_scope(self.ctx.db) as s:
                if self.is_receipt:
                    ReceiptService(s).create_receipt(
                        self.ctx.user, customer_id=party_id, amount=self.amount.value_decimal(),
                        account_id=account_id, reference=self.reference.text().strip())
                else:
                    SupplierPaymentService(s).create_payment(
                        self.ctx.user, supplier_id=party_id, amount=self.amount.value_decimal(),
                        account_id=account_id, reference=self.reference.text().strip())
            self.accept()
        except ZenithError as exc:
            self.err.setText(self.ctx.tr(exc.message_key)); self.err.setVisible(True)


class _PaymentListPage(BasePage):
    is_receipt = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        action = "finance.new_receipt" if self.is_receipt else "finance.new_payment"
        self.header.set_action(ctx.tr(action)).clicked.connect(self._new)
        self.table = DataTable(
            [ctx.tr("finance.voucher_no"), ctx.tr("common.date"),
             ctx.tr("common.amount"), ctx.tr("finance.reference")],
            empty_text=ctx.tr("common.empty"))
        self.table.rowActivated.connect(self._print)
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new(self):
        if _PartyPaymentDialog(self.ctx, is_receipt=self.is_receipt, parent=self).exec():
            Toast.show_message(self, self.ctx.tr("finance.saved"), "success"); self.refresh()

    def _print(self, payment_id):
        from zenith.ui.dialogs.print_preview import VoucherPreviewDialog
        kind = "receipt" if self.is_receipt else "supplier_payment"
        VoucherPreviewDialog(self.ctx, kind, payment_id, self).exec()

    def refresh(self):
        direction = "in" if self.is_receipt else "out"
        rows, ids = [], []
        with session_scope(self.ctx.db) as s:
            pays = s.scalars(
                select(Payment).where(Payment.direction == direction, Payment.is_reversal == False)  # noqa: E712
                .order_by(Payment.id.desc()).limit(300)).all()
            for p in pays:
                rows.append((p.ref_no, p.date.isoformat(), f"{p.amount:,.2f}", p.reference or "-"))
                ids.append(p.id)
        self.table.set_rows(rows, ids)


class ReceiptsPage(_PaymentListPage):
    title_key = "finance.receipts_title"
    subtitle_key = "finance.receipts_subtitle"
    is_receipt = True


class SupplierPaymentsPage(_PaymentListPage):
    title_key = "finance.payments_title"
    subtitle_key = "finance.payments_subtitle"
    is_receipt = False


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------
class _ExpenseDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(ctx.tr("finance.new_expense")); self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        sec = FormSection(ctx.tr("finance.new_expense"))
        self.category = QComboBox(); self.category.setEditable(True)
        self.account = QComboBox()
        self.amount = CurrencyInput()
        self.description = QLineEdit()
        with session_scope(ctx.db) as s:
            for c in s.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name)):
                self.category.addItem(c.name, c.id)
            for a in AccountService(s).list_accounts(active_only=True):
                self.account.addItem(a.name, a.id)
        sec.add_row(ctx.tr("finance.category"), self.category, span=True)
        sec.add_row(ctx.tr("finance.account"), self.account, span=True)
        sec.add_row(ctx.tr("common.amount"), self.amount, span=True)
        sec.add_row(ctx.tr("finance.description"), self.description, span=True)
        lay.addWidget(sec)
        self.err = QLabel(""); self.err.setProperty("badge", "danger"); self.err.setVisible(False)
        lay.addWidget(self.err)
        bb = QDialogButtonBox()
        ok = PrimaryButton(ctx.tr("common.save")); cancel = SecondaryButton(ctx.tr("common.cancel"))
        bb.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self._save); cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        try:
            with session_scope(self.ctx.db) as s:
                svc = ExpenseService(s)
                cat_id = self.category.currentData()
                if cat_id is None and self.category.currentText().strip():
                    cat_id = svc.create_category(self.ctx.user, self.category.currentText().strip()).id
                svc.create_expense(self.ctx.user, amount=self.amount.value_decimal(),
                                   account_id=self.account.currentData(), category_id=cat_id,
                                   description=self.description.text().strip())
            self.accept()
        except ZenithError as exc:
            self.err.setText(self.ctx.tr(exc.message_key)); self.err.setVisible(True)


class ExpensesPage(BasePage):
    title_key = "finance.expenses_title"
    subtitle_key = "finance.expenses_subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("finance.new_expense")).clicked.connect(self._new)
        bar = QHBoxLayout()
        approve = SecondaryButton(ctx.tr("finance.approve"))
        approve.clicked.connect(self._approve_selected)
        printbtn = SecondaryButton(ctx.tr("finance.print"))
        printbtn.clicked.connect(self._print_selected)
        bar.addWidget(approve); bar.addWidget(printbtn); bar.addStretch(1)
        self.content.addLayout(bar)
        self.table = DataTable(
            [ctx.tr("finance.voucher_no"), ctx.tr("common.date"), ctx.tr("finance.description"),
             ctx.tr("common.amount"), ctx.tr("common.status")],
            empty_text=ctx.tr("common.empty"))
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new(self):
        if _ExpenseDialog(self.ctx, self).exec():
            Toast.show_message(self, self.ctx.tr("finance.saved"), "success"); self.refresh()

    def _approve_selected(self):
        eid = self.table.selected_id()
        if eid is None:
            return
        try:
            with session_scope(self.ctx.db) as s:
                ExpenseService(s).approve_expense(self.ctx.user, eid)
            Toast.show_message(self, self.ctx.tr("finance.approved"), "success"); self.refresh()
        except ZenithError as exc:
            QMessageBox.warning(self, self.ctx.tr("common.error"), self.ctx.tr(exc.message_key))

    def _print_selected(self):
        eid = self.table.selected_id()
        if eid is None:
            return
        from zenith.ui.dialogs.print_preview import VoucherPreviewDialog
        VoucherPreviewDialog(self.ctx, "expense", eid, self).exec()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as s:
            for e in s.scalars(select(Expense).where(Expense.is_deleted == False)  # noqa: E712
                               .order_by(Expense.id.desc()).limit(300)):
                status = self.ctx.tr("finance.approved") if e.is_approved else self.ctx.tr("finance.pending")
                rows.append((e.voucher_no, e.date.isoformat(), e.description or "-",
                             f"{e.amount:,.2f}", status))
                ids.append(e.id)
        self.table.set_rows(rows, ids)


# --------------------------------------------------------------------------
# Account transfers
# --------------------------------------------------------------------------
class _TransferDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(ctx.tr("finance.new_transfer")); self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        sec = FormSection(ctx.tr("finance.new_transfer"))
        self.src = QComboBox(); self.dst = QComboBox(); self.amount = CurrencyInput()
        self.reference = QLineEdit()
        with session_scope(ctx.db) as s:
            for a in AccountService(s).list_accounts(active_only=True):
                self.src.addItem(a.name, a.id); self.dst.addItem(a.name, a.id)
        if self.dst.count() > 1:
            self.dst.setCurrentIndex(1)
        sec.add_row(ctx.tr("finance.from_account"), self.src, span=True)
        sec.add_row(ctx.tr("finance.to_account"), self.dst, span=True)
        sec.add_row(ctx.tr("common.amount"), self.amount, span=True)
        sec.add_row(ctx.tr("finance.reference"), self.reference, span=True)
        lay.addWidget(sec)
        self.err = QLabel(""); self.err.setProperty("badge", "danger"); self.err.setVisible(False)
        lay.addWidget(self.err)
        bb = QDialogButtonBox()
        ok = PrimaryButton(ctx.tr("common.save")); cancel = SecondaryButton(ctx.tr("common.cancel"))
        bb.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self._save); cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        try:
            with session_scope(self.ctx.db) as s:
                TransferService(s).create_transfer(
                    self.ctx.user, from_account_id=self.src.currentData(),
                    to_account_id=self.dst.currentData(), amount=self.amount.value_decimal(),
                    reference=self.reference.text().strip())
            self.accept()
        except ZenithError as exc:
            self.err.setText(self.ctx.tr(exc.message_key)); self.err.setVisible(True)


class AccountTransfersPage(BasePage):
    title_key = "finance.transfers_title"
    subtitle_key = "finance.transfers_subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.header.set_action(ctx.tr("finance.new_transfer")).clicked.connect(self._new)
        self.table = DataTable(
            [ctx.tr("finance.voucher_no"), ctx.tr("common.date"), ctx.tr("common.amount")],
            empty_text=ctx.tr("common.empty"))
        self.content.addWidget(self.table, 1)
        self.refresh()

    def _new(self):
        if _TransferDialog(self.ctx, self).exec():
            Toast.show_message(self, self.ctx.tr("finance.saved"), "success"); self.refresh()

    def refresh(self):
        rows, ids = [], []
        with session_scope(self.ctx.db) as s:
            for t in s.scalars(select(AccountTransfer).order_by(AccountTransfer.id.desc()).limit(300)):
                rows.append((t.ref_no, t.date.isoformat(), f"{t.amount:,.2f}"))
                ids.append(t.id)
        self.table.set_rows(rows, ids)
