"""Purchases service (draft -> approve, atomic stock-in + supplier balance)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from zenith.core.exceptions import ValidationError, BusinessRuleError, NotFound
from zenith.db.models import Purchase, PurchaseLine, Product, Supplier
from zenith.security.permissions import Permission
from zenith.services import audit, inventory
from zenith.services.numbering import next_number
from zenith.services.permissions_util import require


@dataclass
class PurchaseLineInput:
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    batch_id: int | None = None


class PurchaseService:
    def __init__(self, session: Session):
        self.session = session

    def create_purchase(self, actor, *, supplier_id: int | None, lines: list[PurchaseLineInput],
                        warehouse_id: int | None = None, supplier_invoice: str = "",
                        is_credit: bool = False, discount: Decimal | str = "0",
                        extra_cost: Decimal | str = "0", paid: Decimal | str = "0") -> Purchase:
        require(actor, Permission.PURCHASE_CREATE)
        if not lines:
            raise ValidationError(message_key="error.no_lines")
        if warehouse_id is None:
            warehouse_id = inventory.default_warehouse(self.session).id

        purchase = Purchase(
            doc_no=next_number(self.session, Purchase, Purchase.doc_no, "PUR"),
            supplier_invoice=supplier_invoice, date=date.today(), supplier_id=supplier_id,
            warehouse_id=warehouse_id, status="draft", is_credit=is_credit,
            user_id=actor.id if actor else None,
        )
        subtotal = Decimal("0")
        for li in lines:
            product = self.session.get(Product, li.product_id)
            if not product or product.is_deleted:
                raise NotFound(message_key="error.not_found")
            qty = Decimal(str(li.quantity))
            price = Decimal(str(li.unit_price))
            if qty <= 0 or price < 0:
                raise ValidationError(message_key="error.invalid_line")
            line_total = price * qty
            purchase.lines.append(PurchaseLine(
                product_id=product.id, batch_id=li.batch_id, quantity=qty,
                unit_price=price, line_total=line_total,
            ))
            subtotal += line_total

        purchase.subtotal = subtotal
        purchase.discount = Decimal(str(discount))
        purchase.extra_cost = Decimal(str(extra_cost))
        purchase.total = subtotal - purchase.discount + purchase.extra_cost
        purchase.paid = Decimal(str(paid))
        self.session.add(purchase)
        self.session.flush()
        audit.log(self.session, "purchase_create", actor=actor, entity="purchase",
                  entity_id=purchase.id, detail=purchase.doc_no)
        return purchase

    def approve_purchase(self, actor, purchase_id: int) -> Purchase:
        require(actor, Permission.PURCHASE_APPROVE)
        purchase = self.session.get(Purchase, purchase_id)
        if not purchase:
            raise NotFound(message_key="error.not_found")
        if purchase.status != "draft":
            raise BusinessRuleError(message_key="error.already_posted")

        for line in purchase.lines:
            inventory.apply_movement(
                self.session, product_id=line.product_id, warehouse_id=purchase.warehouse_id,
                qty_change=line.quantity, kind="purchase", batch_id=line.batch_id,
                ref_type="purchase", ref_id=purchase.id, actor=actor,
            )
            # Update moving purchase price on the product.
            product = self.session.get(Product, line.product_id)
            if product:
                product.purchase_price = line.unit_price

        credit_amount = purchase.total - purchase.paid
        if purchase.supplier_id and credit_amount > 0:
            supplier = self.session.get(Supplier, purchase.supplier_id)
            if supplier:
                supplier.balance = (supplier.balance or Decimal("0")) + credit_amount

        purchase.status = "approved"
        audit.log(self.session, "purchase_approve", actor=actor, entity="purchase",
                  entity_id=purchase.id, detail=f"{purchase.doc_no} total={purchase.total}")
        return purchase
