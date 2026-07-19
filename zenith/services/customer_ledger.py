"""Authoritative customer ledger.

Every change to a customer's balance goes through ``post()`` so the running
balance and ``Customer.balance`` can never diverge. Positive balance = the
customer owes the business. ``debit`` increases the debt, ``credit`` reduces it.

This is the single source of truth for a customer's balance and statement -- the
UI never computes balances from screen fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from zenith.db.models import CustomerLedgerEntry, Customer

ZERO = Decimal("0")


def _dec(v) -> Decimal:
    return Decimal(str(v or 0))


def last_balance(session: Session, customer_id: int) -> Decimal:
    row = session.scalar(
        select(CustomerLedgerEntry.balance)
        .where(CustomerLedgerEntry.customer_id == customer_id)
        .order_by(CustomerLedgerEntry.id.desc()).limit(1)
    )
    return _dec(row) if row is not None else ZERO


def post(session: Session, *, customer_id: int, entry_type: str,
         debit: Decimal | str = "0", credit: Decimal | str = "0",
         ref_type: str = "", ref_id: int | None = None, ref_no: str = "",
         description: str = "", actor=None, notes: str = "",
         at: datetime | None = None) -> CustomerLedgerEntry:
    debit, credit = _dec(debit), _dec(credit)
    if debit < 0 or credit < 0:
        raise ValueError("Ledger debit/credit must be non-negative")
    running = last_balance(session, customer_id) + debit - credit
    entry = CustomerLedgerEntry(
        at=at or datetime.utcnow(), customer_id=customer_id, entry_type=entry_type,
        ref_type=ref_type, ref_id=ref_id, ref_no=ref_no, description=description,
        debit=debit, credit=credit, balance=running,
        user_id=actor.id if actor else None, notes=notes,
    )
    session.add(entry)
    # keep the cached customer balance in lock-step with the ledger
    customer = session.get(Customer, customer_id)
    if customer is not None:
        customer.balance = running
    session.flush()
    return entry


def seed_opening_balance(session: Session, customer: Customer, actor=None) -> None:
    """Post the opening-balance entry for a brand-new customer, if any."""
    ob = _dec(customer.opening_balance)
    if ob == 0:
        return
    if customer.opening_balance_type == "owed_to_customer":
        post(session, customer_id=customer.id, entry_type="opening_balance",
             credit=ob, description="Opening balance (business owes customer)", actor=actor)
    else:
        post(session, customer_id=customer.id, entry_type="opening_balance",
             debit=ob, description="Opening balance (customer owes business)", actor=actor)


def current_balance(session: Session, customer_id: int) -> Decimal:
    return last_balance(session, customer_id)


@dataclass
class StatementLine:
    at: datetime
    entry_type: str
    ref_no: str
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


@dataclass
class Statement:
    customer_id: int
    opening: Decimal
    lines: list[StatementLine]
    total_debit: Decimal
    total_credit: Decimal
    closing: Decimal


def statement(session: Session, customer_id: int, *, start: date | None = None,
              end: date | None = None) -> Statement:
    q = (select(CustomerLedgerEntry).where(CustomerLedgerEntry.customer_id == customer_id)
         .order_by(CustomerLedgerEntry.id))
    entries = list(session.scalars(q))
    opening = ZERO
    lines: list[StatementLine] = []
    total_debit = total_credit = ZERO
    for e in entries:
        d = e.at.date() if isinstance(e.at, datetime) else e.at
        if start and d < start:
            opening = e.balance  # everything before the window rolls into opening
            continue
        if end and d > end:
            continue
        lines.append(StatementLine(e.at, e.entry_type, e.ref_no, e.description,
                                   e.debit, e.credit, e.balance))
        total_debit += e.debit
        total_credit += e.credit
    closing = lines[-1].balance if lines else opening
    return Statement(customer_id, opening, lines, total_debit, total_credit, closing)


@dataclass
class Aging:
    customer_id: int
    name: str
    balance: Decimal
    current: Decimal      # not yet due / 0-30 days
    days_30: Decimal      # 31-60
    days_60: Decimal      # 61-90
    days_90: Decimal      # over 90 (kept for compatibility with UI labels)
    over_90: Decimal


def _bucket_for(age_days: int) -> str:
    if age_days <= 30:
        return "current"
    if age_days <= 60:
        return "days_30"
    if age_days <= 90:
        return "days_60"
    return "over_90"


def aging_for(session: Session, customer_id: int, *, as_of: date | None = None) -> Aging:
    """Age a customer's outstanding balance across standard buckets.

    Unpaid invoice remainders are bucketed by the invoice's due date (or its
    date when no due date is set). Any residual balance not tied to an open
    invoice -- e.g. an opening balance -- lands in ``current``.
    """
    from zenith.db.models import Sale
    as_of = as_of or date.today()
    customer = session.get(Customer, customer_id)
    balance = current_balance(session, customer_id)
    buckets = {"current": ZERO, "days_30": ZERO, "days_60": ZERO, "over_90": ZERO}
    invoiced = ZERO
    sales = session.scalars(
        select(Sale).where(Sale.customer_id == customer_id, Sale.status == "approved")
    ).all()
    for sale in sales:
        remaining = (sale.total or ZERO) - (sale.paid or ZERO)
        if remaining <= 0:
            continue
        ref_day = sale.due_date or sale.date
        age = (as_of - ref_day).days
        buckets[_bucket_for(age)] += remaining
        invoiced += remaining
    # residual (opening balance / adjustments not tied to an open invoice)
    residual = balance - invoiced
    if residual > 0:
        buckets["current"] += residual
    return Aging(
        customer_id=customer_id, name=customer.name if customer else "",
        balance=balance, current=buckets["current"], days_30=buckets["days_30"],
        days_60=buckets["days_60"], days_90=ZERO, over_90=buckets["over_90"],
    )


def outstanding(session: Session, *, min_balance: Decimal = Decimal("0.01")) -> list[Aging]:
    """Aging rows for every customer with a positive (owed-to-business) balance."""
    rows: list[Aging] = []
    customers = session.scalars(
        select(Customer).where(Customer.is_deleted == False)  # noqa: E712
    ).all()
    for c in customers:
        if current_balance(session, c.id) >= min_balance:
            rows.append(aging_for(session, c.id))
    rows.sort(key=lambda a: a.balance, reverse=True)
    return rows


def totals(session: Session, customer_id: int) -> dict:
    """Aggregate purchases/payments/returns for the customer account header."""
    def _sum(col, types):
        return _dec(session.scalar(
            select(func.coalesce(func.sum(col), 0)).where(
                CustomerLedgerEntry.customer_id == customer_id,
                CustomerLedgerEntry.entry_type.in_(types),
            )))
    return {
        "balance": current_balance(session, customer_id),
        "total_purchases": _sum(CustomerLedgerEntry.debit, ["credit_sale", "partial_credit_sale"]),
        "total_payments": _sum(CustomerLedgerEntry.credit, ["customer_payment"]),
        "total_returns": _sum(CustomerLedgerEntry.credit, ["sales_return"]),
    }
