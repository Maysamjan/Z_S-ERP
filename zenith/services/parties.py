"""Customer and supplier service."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from zenith.core.exceptions import ValidationError, NotFound
from zenith.db.models import Customer, Supplier
from zenith.security.permissions import Permission
from zenith.services import audit
from zenith.services.permissions_util import require


class PartyService:
    def __init__(self, session: Session):
        self.session = session

    def find_by_phone(self, phone: str) -> Customer | None:
        phone = (phone or "").strip()
        if not phone:
            return None
        return self.session.scalar(
            select(Customer).where(Customer.phone == phone, Customer.is_deleted == False)  # noqa: E712
        )

    def create_customer(self, actor, name: str, phone: str = "", address: str = "",
                        opening_balance: Decimal | str = "0", credit_limit: Decimal | str = "0",
                        notes: str = "", *, opening_balance_type: str = "owed_to_business",
                        allow_duplicate_phone: bool = False, is_cash_customer: bool = False,
                        **extra) -> Customer:
        require(actor, Permission.PARTY_MANAGE)
        name = (name or "").strip()
        if not name:
            raise ValidationError(message_key="error.name_required")
        phone = (phone or "").strip()
        if phone and not allow_duplicate_phone and self.find_by_phone(phone) is not None:
            raise ValidationError(message_key="error.duplicate_phone_customer")
        ob = Decimal(str(opening_balance))
        allowed = {col.name for col in Customer.__table__.columns}
        clean = {k: v for k, v in extra.items() if k in allowed}
        c = Customer(name=name, phone=phone, address=address, opening_balance=ob,
                     credit_limit=Decimal(str(credit_limit)), notes=notes,
                     opening_balance_type=opening_balance_type, is_cash_customer=is_cash_customer,
                     balance=Decimal("0"), **clean)
        self.session.add(c)
        self.session.flush()
        # Seed the opening balance through the authoritative ledger.
        from zenith.services import customer_ledger
        customer_ledger.seed_opening_balance(self.session, c, actor=actor)
        audit.log(self.session, "customer_create", actor=actor, entity="customer", entity_id=c.id, detail=name)
        return c

    def create_supplier(self, actor, name: str, phone: str = "", address: str = "",
                        opening_balance: Decimal | str = "0", notes: str = "") -> Supplier:
        require(actor, Permission.PARTY_MANAGE)
        name = (name or "").strip()
        if not name:
            raise ValidationError(message_key="error.name_required")
        ob = Decimal(str(opening_balance))
        s = Supplier(name=name, phone=phone, address=address, opening_balance=ob, balance=ob, notes=notes)
        self.session.add(s)
        self.session.flush()
        audit.log(self.session, "supplier_create", actor=actor, entity="supplier", entity_id=s.id, detail=name)
        return s

    def search_customers(self, term: str = "", limit: int = 100, offset: int = 0) -> list[Customer]:
        q = select(Customer).where(Customer.is_deleted == False)  # noqa: E712
        if term.strip():
            like = f"%{term.strip()}%"
            q = q.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
        return list(self.session.scalars(q.order_by(Customer.name).limit(limit).offset(offset)))

    def search_suppliers(self, term: str = "", limit: int = 100, offset: int = 0) -> list[Supplier]:
        q = select(Supplier).where(Supplier.is_deleted == False)  # noqa: E712
        if term.strip():
            like = f"%{term.strip()}%"
            q = q.where(or_(Supplier.name.ilike(like), Supplier.phone.ilike(like)))
        return list(self.session.scalars(q.order_by(Supplier.name).limit(limit).offset(offset)))

    def get_customer(self, customer_id: int) -> Customer:
        c = self.session.get(Customer, customer_id)
        if not c or c.is_deleted:
            raise NotFound(message_key="error.not_found")
        return c
