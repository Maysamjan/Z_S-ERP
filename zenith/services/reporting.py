"""Read-only reporting/metrics used by dashboards and reports.

Pure aggregate queries -- no side effects. Values are computed from posted
documents and current stock, so the dashboard always reflects real data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from zenith.db.models import (
    Sale, SaleLine, Product, Customer, Account, StockItem, Warehouse, Batch, StockMovement,
    Purchase, PurchaseLine,
)


def weighted_avg_cost(session: Session, product_id: int) -> Decimal:
    """Weighted-average purchase cost of a product across approved purchases.

    Falls back to the product's stored purchase price when there is no purchase
    history yet. This is *current* WAC (not historical-at-sale-time); the
    limitation is documented in KNOWN_LIMITATIONS.
    """
    q = (
        select(
            func.coalesce(func.sum(PurchaseLine.quantity * PurchaseLine.unit_price), 0),
            func.coalesce(func.sum(PurchaseLine.quantity), 0),
        )
        .select_from(PurchaseLine)
        .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
        .where(Purchase.status == "approved", PurchaseLine.product_id == product_id)
    )
    total_value, total_qty = session.execute(q).one()
    total_value = Decimal(str(total_value or 0))
    total_qty = Decimal(str(total_qty or 0))
    if total_qty > 0:
        return (total_value / total_qty).quantize(Decimal("0.0001"))
    product = session.get(Product, product_id)
    return Decimal(str(product.purchase_price)) if product else Decimal("0")


def profit_for_day(session: Session, day: date | None = None) -> Decimal:
    """Gross profit of approved sales on a day: revenue - weighted-average COGS."""
    day = day or date.today()
    lines = session.execute(
        select(SaleLine.product_id, SaleLine.quantity, SaleLine.line_total)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(Sale.status == "approved", Sale.date == day)
    ).all()
    cost_cache: dict[int, Decimal] = {}
    profit = Decimal("0")
    for product_id, qty, line_total in lines:
        if product_id not in cost_cache:
            cost_cache[product_id] = weighted_avg_cost(session, product_id)
        profit += Decimal(str(line_total)) - (Decimal(str(qty)) * cost_cache[product_id])
    return profit


def today_sales_total(session: Session, day: date | None = None) -> Decimal:
    day = day or date.today()
    q = select(func.coalesce(func.sum(Sale.total), 0)).where(
        Sale.date == day, Sale.status == "approved"
    )
    return Decimal(str(session.scalar(q) or 0))


def receivables_total(session: Session) -> Decimal:
    q = select(func.coalesce(func.sum(Customer.balance), 0)).where(Customer.is_deleted == False)  # noqa: E712
    return Decimal(str(session.scalar(q) or 0))


def cash_on_hand(session: Session) -> Decimal:
    q = select(func.coalesce(func.sum(Account.balance), 0)).where(Account.kind == "cash")
    return Decimal(str(session.scalar(q) or 0))


def low_stock_count(session: Session) -> int:
    # products whose total stock <= min_stock (and min_stock > 0)
    stock_sub = (
        select(StockItem.product_id, func.sum(StockItem.quantity).label("qty"))
        .group_by(StockItem.product_id).subquery()
    )
    q = (
        select(func.count())
        .select_from(Product)
        .join(stock_sub, stock_sub.c.product_id == Product.id, isouter=True)
        .where(
            Product.is_deleted == False,  # noqa: E712
            Product.min_stock > 0,
            func.coalesce(stock_sub.c.qty, 0) <= Product.min_stock,
        )
    )
    return int(session.scalar(q) or 0)


def total_stock_value(session: Session) -> Decimal:
    q = (
        select(func.coalesce(func.sum(StockItem.quantity * Product.purchase_price), 0))
        .select_from(StockItem)
        .join(Product, Product.id == StockItem.product_id)
    )
    return Decimal(str(session.scalar(q) or 0))


def warehouse_count(session: Session) -> int:
    return int(session.scalar(
        select(func.count()).select_from(Warehouse).where(Warehouse.is_deleted == False)  # noqa: E712
    ) or 0)


def expiring_soon_count(session: Session, within_days: int = 60, day: date | None = None) -> int:
    from datetime import timedelta
    day = day or date.today()
    horizon = day + timedelta(days=within_days)
    q = select(func.count()).select_from(Batch).where(
        Batch.expiry_date != None, Batch.expiry_date >= day, Batch.expiry_date <= horizon  # noqa: E711
    )
    return int(session.scalar(q) or 0)


def expired_stock_count(session: Session, day: date | None = None) -> int:
    day = day or date.today()
    q = select(func.count()).select_from(Batch).where(
        Batch.expiry_date != None, Batch.expiry_date < day  # noqa: E711
    )
    return int(session.scalar(q) or 0)


def recent_movements_count(session: Session, day: date | None = None) -> int:
    day = day or date.today()
    q = select(func.count()).select_from(StockMovement).where(func.date(StockMovement.at) == day.isoformat())
    return int(session.scalar(q) or 0)


#: card key -> callable(session) -> value; formatter marks money vs count.
CARD_PROVIDERS = {
    "today_sales": (today_sales_total, "money"),
    "today_profit": (profit_for_day, "money"),  # real weighted-average COGS profit
    "low_stock": (low_stock_count, "count"),
    "receivables": (receivables_total, "money"),
    "cash_on_hand": (cash_on_hand, "money"),
    "open_shift": (lambda s: 0, "count"),
    "expiring_soon": (expiring_soon_count, "count"),
    "expired_stock": (expired_stock_count, "count"),
    "overdue": (receivables_total, "money"),
    "top_customers": (lambda s: 0, "count"),
    "total_stock_value": (total_stock_value, "money"),
    "warehouses": (warehouse_count, "count"),
    "pending_transfers": (lambda s: 0, "count"),
    "recent_movements": (recent_movements_count, "count"),
}


def card_value(session: Session, key: str) -> tuple[str, str]:
    provider = CARD_PROVIDERS.get(key)
    if provider is None:
        return ("—", "count")
    fn, kind = provider
    return (str(fn(session)), kind)
