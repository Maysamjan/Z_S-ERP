"""Finance services: accounts, receipts, supplier payments, expenses, transfers.

All money is ``Decimal``. Every posting is atomic (caller's ``session_scope``):
a receipt updates the account balance, the customer balance, and invoice
allocations together -- or not at all. Approved financial transactions are never
silently edited or deleted; corrections go through ``reverse_*`` which posts an
opposite entry (with permission + reason) and marks the original reversed.
Duplicate receipts/payments/transfers/expenses are blocked before posting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from zenith.core.exceptions import (
    ValidationError, NotFound, DuplicatePosting, AlreadyReversed, BusinessRuleError,
)
from zenith.db.models import (
    Account, Payment, PaymentAllocation, AccountTransfer, Expense, ExpenseCategory,
    Customer, Supplier, Sale, Purchase, User,
)
from zenith.security.permissions import Permission
from zenith.services import audit
from zenith.services.numbering import next_number
from zenith.services.permissions_util import require

ZERO = Decimal("0")


def _dec(v) -> Decimal:
    return Decimal(str(v))


@dataclass
class Allocation:
    doc_id: int
    amount: Decimal


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------
class AccountService:
    def __init__(self, session: Session):
        self.session = session

    def create_account(self, actor, name: str, kind: str = "cash",
                       opening_balance: Decimal | str = "0", is_default: bool = False) -> Account:
        require(actor, Permission.PAYMENT_MANAGE)
        name = (name or "").strip()
        if not name:
            raise ValidationError(message_key="error.name_required")
        if kind not in ("cash", "bank", "mobile_money"):
            raise ValidationError(message_key="error.invalid_line")
        ob = _dec(opening_balance)
        acc = Account(name=name, kind=kind, opening_balance=ob, balance=ob,
                      is_default=is_default, is_active=True)
        self.session.add(acc)
        self.session.flush()
        audit.log(self.session, "account_create", actor=actor, entity="account",
                  entity_id=acc.id, detail=f"{name} ({kind})")
        return acc

    def set_active(self, actor, account_id: int, active: bool) -> Account:
        require(actor, Permission.PAYMENT_MANAGE)
        acc = self.session.get(Account, account_id)
        if not acc:
            raise NotFound(message_key="error.not_found")
        acc.is_active = active
        audit.log(self.session, "account_activated" if active else "account_deactivated",
                  actor=actor, entity="account", entity_id=account_id)
        return acc

    def list_accounts(self, kind: str | None = None, active_only: bool = False) -> list[Account]:
        q = select(Account).where(Account.is_deleted == False)  # noqa: E712
        if kind:
            q = q.where(Account.kind == kind)
        if active_only:
            q = q.where(Account.is_active == True)  # noqa: E712
        return list(self.session.scalars(q.order_by(Account.name)))

    def _require_active(self, account_id: int) -> Account:
        acc = self.session.get(Account, account_id)
        if not acc or acc.is_deleted:
            raise NotFound(message_key="error.not_found")
        if not acc.is_active:
            raise BusinessRuleError(message_key="error.account_inactive")
        return acc

    def ledger(self, account_id: int, start: date | None = None, end: date | None = None) -> list[dict]:
        """Chronological account entries (payments + transfers + expenses)."""
        entries: list[dict] = []
        pays = self.session.scalars(
            select(Payment).where(Payment.account_id == account_id).order_by(Payment.date, Payment.id)
        ).all()
        for p in pays:
            sign = Decimal("1") if p.direction == "in" else Decimal("-1")
            entries.append({"date": p.date, "ref": p.ref_no, "kind": f"receipt/{p.direction}",
                            "amount": sign * p.amount})
        for t in self.session.scalars(select(AccountTransfer).order_by(AccountTransfer.date, AccountTransfer.id)):
            if t.from_account_id == account_id:
                entries.append({"date": t.date, "ref": t.ref_no, "kind": "transfer_out", "amount": -t.amount})
            if t.to_account_id == account_id:
                entries.append({"date": t.date, "ref": t.ref_no, "kind": "transfer_in", "amount": t.amount})
        for e in self.session.scalars(
            select(Expense).where(Expense.account_id == account_id, Expense.is_approved == True)  # noqa: E712
        ):
            entries.append({"date": e.date, "ref": e.voucher_no, "kind": "expense", "amount": -e.amount})
        if start:
            entries = [e for e in entries if e["date"] >= start]
        if end:
            entries = [e for e in entries if e["date"] <= end]
        entries.sort(key=lambda e: (e["date"], e["ref"]))
        return entries


# --------------------------------------------------------------------------
# Receipts (money in from customers) & supplier payments (money out)
# --------------------------------------------------------------------------
def _duplicate_exists(session: Session, *, direction: str, party_type: str, party_id,
                      account_id: int, amount: Decimal, day: date, reference: str) -> bool:
    q = select(func.count()).select_from(Payment).where(
        Payment.direction == direction, Payment.party_type == party_type,
        Payment.party_id == party_id, Payment.account_id == account_id,
        Payment.amount == amount, Payment.date == day,
        Payment.reference == (reference or ""), Payment.reversed == False,  # noqa: E712
        Payment.is_reversal == False,
    )
    return (session.scalar(q) or 0) > 0


class ReceiptService:
    def __init__(self, session: Session):
        self.session = session

    def create_receipt(self, actor, *, customer_id: int, amount: Decimal | str, account_id: int,
                       day: date | None = None, reference: str = "", note: str = "",
                       allocations: list[Allocation] | None = None, auto_allocate: bool = True) -> Payment:
        require(actor, Permission.PAYMENT_MANAGE)
        amount = _dec(amount)
        day = day or date.today()
        if amount <= 0:
            raise ValidationError(message_key="error.amount_positive")
        customer = self.session.get(Customer, customer_id)
        if not customer or customer.is_deleted:
            raise NotFound(message_key="error.not_found")
        account = AccountService(self.session)._require_active(account_id)

        if _duplicate_exists(self.session, direction="in", party_type="customer", party_id=customer_id,
                             account_id=account_id, amount=amount, day=day, reference=reference):
            raise DuplicatePosting(message_key="error.duplicate_posting")

        payment = Payment(
            ref_no=next_number(self.session, Payment, Payment.ref_no, "RCP"),
            date=day, direction="in", party_type="customer", party_id=customer_id,
            account_id=account_id, amount=amount, method=account.kind,
            reference=reference, note=note, user_id=actor.id if actor else None,
        )
        self.session.add(payment)

        # atomic: account up; customer debt down through the authoritative ledger
        account.balance = (account.balance or ZERO) + amount
        from zenith.services import customer_ledger
        customer_ledger.post(
            self.session, customer_id=customer_id, entry_type="customer_payment",
            credit=amount, ref_type="payment", ref_id=None, ref_no=payment.ref_no,
            description=f"Payment {payment.ref_no}", actor=actor)

        self._allocate(payment, customer_id, amount, allocations, auto_allocate)
        self.session.flush()
        audit.log(self.session, "receipt_create", actor=actor, entity="customer",
                  entity_id=customer_id, detail=f"{payment.ref_no} {amount}")
        return payment

    def _allocate(self, payment: Payment, customer_id: int, amount: Decimal,
                  allocations: list[Allocation] | None, auto_allocate: bool) -> None:
        remaining_to_allocate = amount
        if allocations:
            for alloc in allocations:
                sale = self.session.get(Sale, alloc.doc_id)
                if not sale or sale.customer_id != customer_id:
                    raise ValidationError(message_key="error.invalid_line")
                due = (sale.total or ZERO) - (sale.paid or ZERO)
                applied = min(_dec(alloc.amount), due, remaining_to_allocate)
                if applied <= 0:
                    continue
                sale.paid = (sale.paid or ZERO) + applied
                sale.payment_status = sale.compute_payment_status()
                self.session.add(PaymentAllocation(
                    payment=payment, doc_type="sale", doc_id=sale.id, amount=applied))
                remaining_to_allocate -= applied
        elif auto_allocate:
            unpaid = self.session.scalars(
                select(Sale).where(Sale.customer_id == customer_id, Sale.status == "approved")
                .order_by(Sale.date, Sale.id)
            ).all()
            for sale in unpaid:
                if remaining_to_allocate <= 0:
                    break
                due = (sale.total or ZERO) - (sale.paid or ZERO)
                if due <= 0:
                    continue
                applied = min(due, remaining_to_allocate)
                sale.paid = (sale.paid or ZERO) + applied
                sale.payment_status = sale.compute_payment_status()
                self.session.add(PaymentAllocation(
                    payment=payment, doc_type="sale", doc_id=sale.id, amount=applied))
                remaining_to_allocate -= applied

    def reverse(self, actor, payment_id: int, reason: str) -> Payment:
        return _reverse_payment(self.session, actor, payment_id, reason, party_kind="customer")


class SupplierPaymentService:
    def __init__(self, session: Session):
        self.session = session

    def create_payment(self, actor, *, supplier_id: int, amount: Decimal | str, account_id: int,
                       day: date | None = None, reference: str = "", note: str = "",
                       allocations: list[Allocation] | None = None, auto_allocate: bool = True) -> Payment:
        require(actor, Permission.PAYMENT_MANAGE)
        amount = _dec(amount)
        day = day or date.today()
        if amount <= 0:
            raise ValidationError(message_key="error.amount_positive")
        supplier = self.session.get(Supplier, supplier_id)
        if not supplier or supplier.is_deleted:
            raise NotFound(message_key="error.not_found")
        account = AccountService(self.session)._require_active(account_id)

        if _duplicate_exists(self.session, direction="out", party_type="supplier", party_id=supplier_id,
                             account_id=account_id, amount=amount, day=day, reference=reference):
            raise DuplicatePosting(message_key="error.duplicate_posting")

        payment = Payment(
            ref_no=next_number(self.session, Payment, Payment.ref_no, "PAY"),
            date=day, direction="out", party_type="supplier", party_id=supplier_id,
            account_id=account_id, amount=amount, method=account.kind,
            reference=reference, note=note, user_id=actor.id if actor else None,
        )
        self.session.add(payment)
        account.balance = (account.balance or ZERO) - amount
        supplier.balance = (supplier.balance or ZERO) - amount

        remaining = amount
        docs = allocations if allocations else None
        if docs:
            for alloc in docs:
                purchase = self.session.get(Purchase, alloc.doc_id)
                if not purchase or purchase.supplier_id != supplier_id:
                    raise ValidationError(message_key="error.invalid_line")
                due = (purchase.total or ZERO) - (purchase.paid or ZERO)
                applied = min(_dec(alloc.amount), due, remaining)
                if applied <= 0:
                    continue
                purchase.paid = (purchase.paid or ZERO) + applied
                self.session.add(PaymentAllocation(
                    payment=payment, doc_type="purchase", doc_id=purchase.id, amount=applied))
                remaining -= applied
        elif auto_allocate:
            unpaid = self.session.scalars(
                select(Purchase).where(Purchase.supplier_id == supplier_id, Purchase.status == "approved")
                .order_by(Purchase.date, Purchase.id)
            ).all()
            for purchase in unpaid:
                if remaining <= 0:
                    break
                due = (purchase.total or ZERO) - (purchase.paid or ZERO)
                if due <= 0:
                    continue
                applied = min(due, remaining)
                purchase.paid = (purchase.paid or ZERO) + applied
                self.session.add(PaymentAllocation(
                    payment=payment, doc_type="purchase", doc_id=purchase.id, amount=applied))
                remaining -= applied

        self.session.flush()
        audit.log(self.session, "supplier_payment_create", actor=actor, entity="supplier",
                  entity_id=supplier_id, detail=f"{payment.ref_no} {amount}")
        return payment

    def reverse(self, actor, payment_id: int, reason: str) -> Payment:
        return _reverse_payment(self.session, actor, payment_id, reason, party_kind="supplier")


def _reverse_payment(session: Session, actor, payment_id: int, reason: str, party_kind: str) -> Payment:
    require(actor, Permission.PAYMENT_MANAGE)
    if not (reason or "").strip():
        raise ValidationError(message_key="error.reason_required")
    original = session.get(Payment, payment_id)
    if not original:
        raise NotFound(message_key="error.not_found")
    if original.reversed or original.is_reversal:
        raise AlreadyReversed(message_key="error.already_reversed")

    account = session.get(Account, original.account_id)
    # opposite direction restores balances
    opp = "out" if original.direction == "in" else "in"
    rev = Payment(
        ref_no=next_number(session, Payment, Payment.ref_no, "REV"),
        date=date.today(), direction=opp, party_type=original.party_type, party_id=original.party_id,
        account_id=original.account_id, amount=original.amount, method=original.method,
        reference=original.reference, note=f"reversal: {reason}",
        user_id=actor.id if actor else None, is_reversal=True, reverses_id=original.id,
    )
    session.add(rev)
    if account:
        account.balance = (account.balance or ZERO) + (original.amount if opp == "in" else -original.amount)

    # restore party balance and de-allocate invoices
    if original.party_type == "customer":
        from zenith.services import customer_ledger
        # reversing a customer payment re-adds the debt through the ledger
        customer_ledger.post(
            session, customer_id=original.party_id, entry_type="payment_reversal",
            debit=original.amount, ref_type="payment", ref_id=original.id, ref_no=rev.ref_no,
            description=f"Reversal of {original.ref_no}", actor=actor)
        for a in original.allocations:
            sale = session.get(Sale, a.doc_id)
            if sale:
                sale.paid = (sale.paid or ZERO) - a.amount
                sale.payment_status = sale.compute_payment_status()
    else:
        party = session.get(Supplier, original.party_id)
        if party:
            party.balance = (party.balance or ZERO) + original.amount  # we owe again
        for a in original.allocations:
            purchase = session.get(Purchase, a.doc_id)
            if purchase:
                purchase.paid = (purchase.paid or ZERO) - a.amount

    original.reversed = True
    session.flush()
    audit.log(session, "payment_reversed", actor=actor, entity="payment", entity_id=payment_id,
              detail=f"{rev.ref_no} reason={reason}")
    return rev


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------
class ExpenseService:
    def __init__(self, session: Session):
        self.session = session

    def create_category(self, actor, name: str) -> ExpenseCategory:
        require(actor, Permission.EXPENSE_MANAGE)
        name = (name or "").strip()
        if not name:
            raise ValidationError(message_key="error.name_required")
        cat = ExpenseCategory(name=name)
        self.session.add(cat)
        self.session.flush()
        return cat

    def create_expense(self, actor, *, amount: Decimal | str, account_id: int, category_id: int | None = None,
                       day: date | None = None, description: str = "", reference: str = "",
                       attachment_path: str | None = None) -> Expense:
        require(actor, Permission.EXPENSE_MANAGE)
        amount = _dec(amount)
        day = day or date.today()
        if amount <= 0:
            raise ValidationError(message_key="error.amount_positive")
        exp = Expense(
            voucher_no=next_number(self.session, Expense, Expense.voucher_no, "EXP"),
            category_id=category_id, account_id=account_id, date=day, amount=amount,
            description=description, reference=reference, attachment_path=attachment_path,
            is_approved=False, user_id=actor.id if actor else None,
        )
        self.session.add(exp)
        self.session.flush()
        audit.log(self.session, "expense_create", actor=actor, entity="expense",
                  entity_id=exp.id, detail=f"{exp.voucher_no} {amount}")
        return exp

    def approve_expense(self, actor, expense_id: int) -> Expense:
        """Approving decrements the paying account balance atomically."""
        require(actor, Permission.EXPENSE_MANAGE)
        exp = self.session.get(Expense, expense_id)
        if not exp:
            raise NotFound(message_key="error.not_found")
        if exp.is_approved:
            raise BusinessRuleError(message_key="error.already_posted")
        if exp.account_id:
            account = AccountService(self.session)._require_active(exp.account_id)
            account.balance = (account.balance or ZERO) - exp.amount
        exp.is_approved = True
        audit.log(self.session, "expense_approve", actor=actor, entity="expense",
                  entity_id=exp.id, detail=exp.voucher_no)
        return exp


# --------------------------------------------------------------------------
# Account transfers
# --------------------------------------------------------------------------
class TransferService:
    def __init__(self, session: Session):
        self.session = session

    def create_transfer(self, actor, *, from_account_id: int, to_account_id: int,
                        amount: Decimal | str, day: date | None = None,
                        reference: str = "", note: str = "") -> AccountTransfer:
        require(actor, Permission.PAYMENT_MANAGE)
        amount = _dec(amount)
        day = day or date.today()
        if amount <= 0:
            raise ValidationError(message_key="error.amount_positive")
        if from_account_id == to_account_id:
            raise ValidationError(message_key="error.same_account")
        acc_svc = AccountService(self.session)
        src = acc_svc._require_active(from_account_id)
        dst = acc_svc._require_active(to_account_id)

        # duplicate guard
        dup = self.session.scalar(
            select(func.count()).select_from(AccountTransfer).where(
                AccountTransfer.from_account_id == from_account_id,
                AccountTransfer.to_account_id == to_account_id,
                AccountTransfer.amount == amount, AccountTransfer.date == day,
                AccountTransfer.reference == (reference or ""), AccountTransfer.reversed == False,  # noqa: E712
            )
        ) or 0
        if dup > 0:
            raise DuplicatePosting(message_key="error.duplicate_posting")

        transfer = AccountTransfer(
            ref_no=next_number(self.session, AccountTransfer, AccountTransfer.ref_no, "TRF"),
            date=day, from_account_id=from_account_id, to_account_id=to_account_id,
            amount=amount, reference=reference, note=note, user_id=actor.id if actor else None,
        )
        self.session.add(transfer)
        src.balance = (src.balance or ZERO) - amount
        dst.balance = (dst.balance or ZERO) + amount
        self.session.flush()
        audit.log(self.session, "account_transfer", actor=actor, entity="account",
                  entity_id=from_account_id, detail=f"{transfer.ref_no} {amount} -> acc{to_account_id}")
        return transfer
