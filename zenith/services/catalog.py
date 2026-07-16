"""Product / category / unit service."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from zenith.core.exceptions import ValidationError, NotFound
from zenith.db.models import Product, Category, Unit
from zenith.security.permissions import Permission
from zenith.services import audit
from zenith.services.permissions_util import require


class CatalogService:
    def __init__(self, session: Session):
        self.session = session

    # -- categories / units ------------------------------------------------
    def create_category(self, actor, name: str, parent_id: int | None = None) -> Category:
        require(actor, Permission.PRODUCT_MANAGE)
        name = (name or "").strip()
        if not name:
            raise ValidationError(message_key="error.name_required")
        cat = Category(name=name, parent_id=parent_id)
        self.session.add(cat)
        self.session.flush()
        return cat

    def create_unit(self, actor, code: str, name: str = "", base_unit_id: int | None = None,
                    factor: Decimal | str = "1") -> Unit:
        require(actor, Permission.PRODUCT_MANAGE)
        code = (code or "").strip()
        if not code:
            raise ValidationError(message_key="error.code_required")
        unit = Unit(code=code, name=name or code, base_unit_id=base_unit_id, factor=Decimal(str(factor)))
        self.session.add(unit)
        self.session.flush()
        return unit

    # -- products ----------------------------------------------------------
    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def find_similar(self, name: str, *, strength: str | None = None,
                     dosage_form: str | None = None, manufacturer: str | None = None) -> list[Product]:
        """Return existing products that look like the same item.

        Genuinely different items (e.g. Paracetamol 500mg tablet vs
        Paracetamol 120mg/5ml syrup) differ in strength/dosage form and are NOT
        reported as duplicates.
        """
        norm = self._normalize(name)
        if not norm:
            return []
        candidates = self.session.scalars(
            select(Product).where(Product.is_deleted == False, Product.name.ilike(f"%{name.strip()}%"))  # noqa: E712
        ).all()
        out = []
        for p in candidates:
            if self._normalize(p.name) != norm:
                continue
            if strength and p.strength and self._normalize(p.strength) != self._normalize(strength):
                continue
            if dosage_form and p.dosage_form and self._normalize(p.dosage_form) != self._normalize(dosage_form):
                continue
            if manufacturer and p.manufacturer and self._normalize(p.manufacturer) != self._normalize(manufacturer):
                continue
            out.append(p)
        return out

    def create_product(self, actor, *, allow_similar: bool = False, **fields) -> Product:
        require(actor, Permission.PRODUCT_MANAGE)
        code = (fields.get("code") or "").strip()
        name = (fields.get("name") or "").strip()
        if not code:
            raise ValidationError(message_key="error.code_required")
        if not name:
            raise ValidationError(message_key="error.name_required")
        if not allow_similar:
            similar = self.find_similar(
                name, strength=fields.get("strength"),
                dosage_form=fields.get("dosage_form"), manufacturer=fields.get("manufacturer"),
            )
            if similar:
                raise ValidationError(message_key="error.duplicate_similar")
        if self.session.scalar(select(Product).where(Product.code == code, Product.is_deleted == False)):  # noqa: E712
            raise ValidationError(message_key="error.duplicate_code")
        barcode = fields.get("barcode")
        if barcode and self.session.scalar(
            select(Product).where(Product.barcode == barcode, Product.is_deleted == False)  # noqa: E712
        ):
            raise ValidationError(message_key="error.duplicate_barcode")
        allowed = {c.name for c in Product.__table__.columns}
        clean = {k: v for k, v in fields.items() if k in allowed}
        product = Product(**clean)
        self.session.add(product)
        self.session.flush()
        audit.log(self.session, "product_create", actor=actor, entity="product",
                  entity_id=product.id, detail=code)
        return product

    def update_price(self, actor, product_id: int, *, sale_price=None, purchase_price=None,
                     wholesale_price=None) -> Product:
        require(actor, Permission.PRICE_CHANGE)
        product = self.session.get(Product, product_id)
        if not product or product.is_deleted:
            raise NotFound(message_key="error.not_found")
        before = f"sale={product.sale_price} purch={product.purchase_price}"
        if sale_price is not None:
            product.sale_price = Decimal(str(sale_price))
        if purchase_price is not None:
            product.purchase_price = Decimal(str(purchase_price))
        if wholesale_price is not None:
            product.wholesale_price = Decimal(str(wholesale_price))
        audit.log(self.session, "price_change", actor=actor, entity="product", entity_id=product_id,
                  detail=f"{before} -> sale={product.sale_price}")
        return product

    def soft_delete(self, actor, product_id: int) -> None:
        require(actor, Permission.PRODUCT_MANAGE)
        product = self.session.get(Product, product_id)
        if not product:
            raise NotFound(message_key="error.not_found")
        product.is_deleted = True
        product.is_active = False
        audit.log(self.session, "product_delete", actor=actor, entity="product", entity_id=product_id)

    def search(self, term: str = "", limit: int = 100, offset: int = 0) -> list[Product]:
        q = select(Product).where(Product.is_deleted == False)  # noqa: E712
        term = (term or "").strip()
        if term:
            like = f"%{term}%"
            q = q.where(or_(Product.name.ilike(like), Product.code.ilike(like), Product.barcode.ilike(like)))
        q = q.order_by(Product.name).limit(limit).offset(offset)
        return list(self.session.scalars(q))

    def by_barcode(self, barcode: str) -> Product | None:
        return self.session.scalar(
            select(Product).where(Product.barcode == barcode, Product.is_deleted == False)  # noqa: E712
        )
