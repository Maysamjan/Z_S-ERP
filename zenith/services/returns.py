"""Sales and purchase returns.

A return is a dedicated document linked to the original approved sale/purchase.
Posting is atomic (caller's ``session_scope``): stock is restored/removed, the
original line's ``returned_qty`` is advanced, and the party balance is adjusted --
all or nothing.

Guards (enforced here, not just the UI):
* the original document must be approved;
* a line's return quantity may not exceed its remaining returnable quantity
  (this is also what blocks a duplicate/over return);
* a sales return restores the **exact original batch** the goods left on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from zenith.core.exceptions import (
    ValidationError, BusinessRuleError, NotFound,
)
from zenith.db.models import (
    Sale, SaleLine, SalesReturn, SalesReturnLine,
    Purchase, PurchaseLine, PurchaseReturn, PurchaseReturnLine,
    Customer, Supplier,
)
from zenith.security.permissions import Permission
from zenith.services import audit, inventory
from zenith.services.numbering import next_number
from zenith.services.permissions_util import require


@dataclass
class ReturnLineInput:
    line_id: int          # original SaleLine / PurchaseLine id
    quantity: Decimal


class SalesReturnService:
    def __init__(self, session: Session):
        self.session = session

    def create_return(self, actor, sale_id: int, lines: list[ReturnLineInput]) -> SalesReturn:
        require(actor, Permission.SALE_RETURN)
        sale = self.session.get(Sale, sale_id)
        if sale is None:
            raise NotFound(message_key="error.not_found")
        if sale.status != "approved":
            raise BusinessRuleError(message_key="error.not_approved")
        if not lines:
            raise ValidationError(message_key="error.no_lines")

        doc = SalesReturn(
            return_no=next_number(self.session, SalesReturn, SalesReturn.return_no, "SRET"),
            sale_id=sale.id, date=date.today(), warehouse_id=sale.warehouse_id,
            user_id=actor.id if actor else None,
        )
        total = Decimal("0")
        for li in lines:
            qty = Decimal(str(li.quantity))
            if qty <= 0:
                raise ValidationError(message_key="error.zero_quantity")
            sale_line = self.session.get(SaleLine, li.line_id)
            if sale_line is None or sale_line.sale_id != sale.id:
                raise NotFound(message_key="error.not_found")
            if qty > sale_line.returnable_qty:
                # covers both over-return and duplicate-return
                raise BusinessRuleError(message_key="error.return_exceeds")

            line_total = sale_line.unit_price * qty
            doc.lines.append(SalesReturnLine(
                sale_line_id=sale_line.id, product_id=sale_line.product_id,
                batch_id=sale_line.batch_id, quantity=qty, unit_price=sale_line.unit_price,
                line_total=line_total,
            ))
            total += line_total
            sale_line.returned_qty = (sale_line.returned_qty or Decimal("0")) + qty

            # restore stock to the exact original batch
            inventory.apply_movement(
                self.session, product_id=sale_line.product_id, warehouse_id=sale.warehouse_id,
                qty_change=qty, kind="sale_return", batch_id=sale_line.batch_id,
                ref_type="sales_return", ref_id=None, actor=actor,
            )

        doc.total = total
        # reverse the receivable for a credit customer
        if sale.customer_id:
            customer = self.session.get(Customer, sale.customer_id)
            if customer:
                customer.balance = (customer.balance or Decimal("0")) - total

        self.session.add(doc)
        self.session.flush()
        # backfill ref_id on the movements now that the doc has an id
        audit.log(self.session, "sales_return", actor=actor, entity="sale", entity_id=sale.id,
                  detail=f"{doc.return_no} total={total}")
        return doc


class PurchaseReturnService:
    def __init__(self, session: Session):
        self.session = session

    def create_return(self, actor, purchase_id: int, lines: list[ReturnLineInput]) -> PurchaseReturn:
        require(actor, Permission.PURCHASE_RETURN)
        purchase = self.session.get(Purchase, purchase_id)
        if purchase is None:
            raise NotFound(message_key="error.not_found")
        if purchase.status != "approved":
            raise BusinessRuleError(message_key="error.not_approved")
        if not lines:
            raise ValidationError(message_key="error.no_lines")

        doc = PurchaseReturn(
            return_no=next_number(self.session, PurchaseReturn, PurchaseReturn.return_no, "PRET"),
            purchase_id=purchase.id, date=date.today(), warehouse_id=purchase.warehouse_id,
            user_id=actor.id if actor else None,
        )
        total = Decimal("0")
        for li in lines:
            qty = Decimal(str(li.quantity))
            if qty <= 0:
                raise ValidationError(message_key="error.zero_quantity")
            pline = self.session.get(PurchaseLine, li.line_id)
            if pline is None or pline.purchase_id != purchase.id:
                raise NotFound(message_key="error.not_found")
            if qty > pline.returnable_qty:
                raise BusinessRuleError(message_key="error.return_exceeds")

            line_total = pline.unit_price * qty
            doc.lines.append(PurchaseReturnLine(
                purchase_line_id=pline.id, product_id=pline.product_id,
                batch_id=pline.batch_id, quantity=qty, unit_price=pline.unit_price,
                line_total=line_total,
            ))
            total += line_total
            pline.returned_qty = (pline.returned_qty or Decimal("0")) + qty

            # remove stock (goods returned to supplier); block if it would go negative
            inventory.apply_movement(
                self.session, product_id=pline.product_id, warehouse_id=purchase.warehouse_id,
                qty_change=-qty, kind="purchase_return", batch_id=pline.batch_id,
                ref_type="purchase_return", ref_id=None, actor=actor,
            )

        doc.total = total
        # reduce the payable to the supplier
        if purchase.supplier_id:
            supplier = self.session.get(Supplier, purchase.supplier_id)
            if supplier:
                supplier.balance = (supplier.balance or Decimal("0")) - total

        self.session.add(doc)
        self.session.flush()
        audit.log(self.session, "purchase_return", actor=actor, entity="purchase",
                  entity_id=purchase.id, detail=f"{doc.return_no} total={total}")
        return doc
