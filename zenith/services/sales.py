"""Sales service.

Draft -> approve lifecycle. Approval is the single atomic posting step: it checks
stock (and, when configured, blocks expired batches), deducts inventory, updates
the customer balance for credit sales, and enforces the credit limit. Any failure
raises and the caller's ``session_scope`` rolls the whole thing back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from zenith.core.exceptions import (
    ValidationError, BusinessRuleError, CreditLimitExceeded, ExpiredStockError, NotFound,
)
from zenith.db.models import Sale, SaleLine, Product, Customer, Batch
from zenith.security.permissions import Permission
from zenith.services import audit, inventory
from zenith.services.numbering import next_number
from zenith.services.permissions_util import require


@dataclass
class LineInput:
    product_id: int
    quantity: Decimal
    unit_price: Decimal | None = None   # resolved from product if None
    discount: Decimal = Decimal("0")
    batch_id: int | None = None


class SalesService:
    def __init__(self, session: Session):
        self.session = session

    def _price_for(self, product: Product, price_mode: str) -> Decimal:
        if price_mode == "wholesale" and product.wholesale_price is not None:
            return product.wholesale_price
        return product.sale_price

    def create_sale(self, actor, *, customer_id: int | None, lines: list[LineInput],
                    warehouse_id: int | None = None, is_credit: bool = False,
                    discount: Decimal | str = "0", paid: Decimal | str = "0",
                    price_mode: str = "retail") -> Sale:
        require(actor, Permission.SALE_CREATE)
        if not lines:
            raise ValidationError(message_key="error.no_lines")
        if warehouse_id is None:
            warehouse_id = inventory.default_warehouse(self.session).id

        sale = Sale(
            invoice_no=next_number(self.session, Sale, Sale.invoice_no, "INV"),
            date=date.today(), customer_id=customer_id, warehouse_id=warehouse_id,
            status="draft", is_credit=is_credit, price_mode=price_mode,
            user_id=actor.id if actor else None,
        )
        subtotal = Decimal("0")
        for li in lines:
            product = self.session.get(Product, li.product_id)
            if not product or product.is_deleted:
                raise NotFound(message_key="error.not_found")
            qty = Decimal(str(li.quantity))
            if qty <= 0:
                raise ValidationError(message_key="error.zero_quantity")
            price = Decimal(str(li.unit_price)) if li.unit_price is not None else self._price_for(product, price_mode)
            line_discount = Decimal(str(li.discount or 0))
            line_total = (price * qty) - line_discount
            if line_total < 0:
                raise ValidationError(message_key="error.negative_line")
            sale.lines.append(SaleLine(
                product_id=product.id, batch_id=li.batch_id, quantity=qty,
                unit_price=price, discount=line_discount, line_total=line_total,
            ))
            subtotal += line_total

        sale.subtotal = subtotal
        sale.discount = Decimal(str(discount))
        sale.total = subtotal - sale.discount
        if sale.total < 0:
            raise ValidationError(message_key="error.negative_total")
        sale.paid = Decimal(str(paid))
        self.session.add(sale)
        self.session.flush()
        audit.log(self.session, "sale_create", actor=actor, entity="sale", entity_id=sale.id,
                  detail=sale.invoice_no)
        return sale

    def approve_sale(self, actor, sale_id: int, *, block_expired: bool = True,
                     today: date | None = None) -> Sale:
        require(actor, Permission.SALE_APPROVE)
        today = today or date.today()
        sale = self.session.get(Sale, sale_id)
        if not sale:
            raise NotFound(message_key="error.not_found")
        if sale.status != "draft":
            raise BusinessRuleError(message_key="error.already_posted")

        # Credit limit check (customer owes existing balance + credit part of this sale).
        credit_amount = sale.total - sale.paid
        if sale.is_credit and sale.customer_id and credit_amount > 0:
            customer = self.session.get(Customer, sale.customer_id)
            if customer and customer.credit_limit and customer.credit_limit > 0:
                projected = (customer.balance or Decimal("0")) + credit_amount
                if projected > customer.credit_limit:
                    raise CreditLimitExceeded(message_key="error.credit_limit")

        # Post each line: expiry guard + stock deduction.
        for line in sale.lines:
            if block_expired and line.batch_id:
                batch = self.session.get(Batch, line.batch_id)
                if batch and batch.expiry_date and batch.expiry_date < today:
                    raise ExpiredStockError(message_key="error.expired_stock")
            inventory.apply_movement(
                self.session, product_id=line.product_id, warehouse_id=sale.warehouse_id,
                qty_change=-line.quantity, kind="sale", batch_id=line.batch_id,
                ref_type="sale", ref_id=sale.id, actor=actor,
            )

        # Update customer balance for the unpaid (credit) portion.
        if sale.customer_id and credit_amount > 0:
            customer = self.session.get(Customer, sale.customer_id)
            if customer:
                customer.balance = (customer.balance or Decimal("0")) + credit_amount

        sale.status = "approved"
        audit.log(self.session, "sale_approve", actor=actor, entity="sale", entity_id=sale.id,
                  detail=f"{sale.invoice_no} total={sale.total}")
        return sale
