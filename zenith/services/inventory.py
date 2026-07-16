"""Inventory service: balances, movements, adjustments, transfers.

All stock changes go through ``apply_movement`` so a ``StockMovement`` row is
always written alongside the ``StockItem`` balance update -- the movement ledger
and the balances can never diverge. Negative stock is rejected unless explicitly
allowed (e.g. approved adjustments).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from zenith.core.exceptions import InsufficientStock, ValidationError, PermissionDenied
from zenith.db.models import StockItem, StockMovement, Warehouse, User
from zenith.security.permissions import Permission
from zenith.services import audit
from zenith.services.permissions_util import require


def default_warehouse(session: Session) -> Warehouse:
    wh = session.scalar(select(Warehouse).where(Warehouse.is_default == True))  # noqa: E712
    if wh is None:
        wh = session.scalar(select(Warehouse).order_by(Warehouse.id))
    if wh is None:
        raise ValidationError(message_key="error.no_warehouse")
    return wh


def _slot(session: Session, product_id: int, warehouse_id: int, batch_id: int | None) -> StockItem:
    item = session.scalar(
        select(StockItem).where(
            StockItem.product_id == product_id,
            StockItem.warehouse_id == warehouse_id,
            StockItem.batch_id.is_(batch_id) if batch_id is None else StockItem.batch_id == batch_id,
        )
    )
    if item is None:
        item = StockItem(product_id=product_id, warehouse_id=warehouse_id,
                         batch_id=batch_id, quantity=Decimal("0"))
        session.add(item)
        session.flush()
    return item


def balance(session: Session, product_id: int, warehouse_id: int | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(StockItem.quantity), 0)).where(StockItem.product_id == product_id)
    if warehouse_id is not None:
        q = q.where(StockItem.warehouse_id == warehouse_id)
    return Decimal(str(session.scalar(q) or 0))


def apply_movement(session: Session, *, product_id: int, warehouse_id: int, qty_change: Decimal,
                   kind: str, batch_id: int | None = None, ref_type: str = "", ref_id: int | None = None,
                   note: str = "", actor: User | None = None, allow_negative: bool = False) -> StockMovement:
    """Adjust a stock slot and record the movement atomically (within caller's tx)."""
    qty_change = Decimal(str(qty_change))
    if qty_change == 0:
        raise ValidationError(message_key="error.zero_quantity")
    item = _slot(session, product_id, warehouse_id, batch_id)
    new_qty = (item.quantity or Decimal("0")) + qty_change
    if new_qty < 0 and not allow_negative:
        raise InsufficientStock(message_key="error.insufficient_stock")
    item.quantity = new_qty
    mv = StockMovement(product_id=product_id, warehouse_id=warehouse_id, batch_id=batch_id,
                       qty_change=qty_change, kind=kind, ref_type=ref_type, ref_id=ref_id,
                       note=note, user_id=actor.id if actor else None)
    session.add(mv)
    return mv


def adjust(session: Session, actor: User, *, product_id: int, warehouse_id: int,
           qty_change: Decimal, note: str = "") -> StockMovement:
    require(actor, Permission.STOCK_ADJUST)
    mv = apply_movement(session, product_id=product_id, warehouse_id=warehouse_id,
                        qty_change=Decimal(str(qty_change)), kind="adjust", note=note,
                        actor=actor, allow_negative=True)
    audit.log(session, "stock_adjust", actor=actor, entity="product", entity_id=product_id,
              detail=f"{qty_change} @wh{warehouse_id}: {note}")
    return mv


def transfer(session: Session, actor: User, *, product_id: int, from_wh: int, to_wh: int,
             quantity: Decimal, batch_id: int | None = None, note: str = "") -> None:
    """Move stock between warehouses atomically. Rejects insufficient source stock."""
    require(actor, Permission.STOCK_TRANSFER)
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValidationError(message_key="error.zero_quantity")
    if from_wh == to_wh:
        raise ValidationError(message_key="error.same_warehouse")
    apply_movement(session, product_id=product_id, warehouse_id=from_wh, qty_change=-quantity,
                   kind="transfer", batch_id=batch_id, note=f"out->wh{to_wh} {note}", actor=actor)
    apply_movement(session, product_id=product_id, warehouse_id=to_wh, qty_change=quantity,
                   kind="transfer", batch_id=batch_id, note=f"in<-wh{from_wh} {note}", actor=actor)
    audit.log(session, "stock_transfer", actor=actor, entity="product", entity_id=product_id,
              detail=f"{quantity} wh{from_wh}->wh{to_wh}")
