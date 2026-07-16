"""Shared-core ORM models.

One schema serves all five profiles. Profile-specific product attributes
(wholesale price, generic/trade name, batch flags, storage bin) are nullable
columns on ``Product`` -- gated in the UI by the active profile's feature flags,
never by separate per-profile tables. Money is ``Numeric(18, 4)`` (never float).
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Numeric, Boolean, DateTime, Date, Text, ForeignKey,
    UniqueConstraint, Index, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from zenith.db.base import Base


MONEY = Numeric(18, 4)
QTY = Numeric(18, 4)


def _now() -> datetime:
    return datetime.utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# --------------------------------------------------------------------------
# System / meta
# --------------------------------------------------------------------------
class SchemaVersion(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class BusinessSettings(Base):
    """Single-row company profile + settings."""
    __tablename__ = "business_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200), default="")
    profile_code: Mapped[str] = mapped_column(String(40), nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str] = mapped_column(String(300), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    currency: Mapped[str] = mapped_column(String(10), default="AFN")
    date_system: Mapped[str] = mapped_column(String(20), default="gregorian")  # or "solar_hijri"
    language: Mapped[str] = mapped_column(String(10), default="en_US")
    theme: Mapped[str] = mapped_column(String(10), default="light")


# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    permissions: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of permission keys
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    role: Mapped[Role | None] = relationship(back_populates="users")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(60), default="")
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[str] = mapped_column(Text, default="")


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------
class Category(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    __table_args__ = (UniqueConstraint("name", name="uq_category_name"),)


class Unit(Base, TimestampMixin):
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), default="")
    # For unit conversion (wholesale): factor relative to a base unit.
    base_unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    factor: Mapped[Decimal] = mapped_column(QTY, default=Decimal("1"))


class Product(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"))
    barcode: Mapped[str | None] = mapped_column(String(60))
    purchase_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    sale_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    min_stock: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500))

    # profile-specific (nullable) fields
    wholesale_price: Mapped[Decimal | None] = mapped_column(MONEY)      # wholesale
    carton_size: Mapped[Decimal | None] = mapped_column(QTY)            # wholesale
    pack_size: Mapped[Decimal | None] = mapped_column(QTY)              # wholesale/supermarket
    is_weighed: Mapped[bool] = mapped_column(Boolean, default=False)    # supermarket
    batch_tracked: Mapped[bool] = mapped_column(Boolean, default=False) # supermarket/pharmacy/warehouse
    storage_bin: Mapped[str | None] = mapped_column(String(40))         # warehouse
    # pharmacy
    generic_name: Mapped[str | None] = mapped_column(String(160))
    trade_name: Mapped[str | None] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(80))
    dosage_form: Mapped[str | None] = mapped_column(String(80))
    strength: Mapped[str | None] = mapped_column(String(80))
    package_type: Mapped[str | None] = mapped_column(String(80))
    units_per_package: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("code", name="uq_product_code"),
        Index("ix_product_barcode", "barcode"),
        Index("ix_product_name", "name"),
    )


# --------------------------------------------------------------------------
# Parties
# --------------------------------------------------------------------------
class Customer(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(60), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))  # positive = owes us
    credit_limit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_customer_name", "name"),)


class Supplier(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(60), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))  # positive = we owe
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_supplier_name", "name"),)


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
class Warehouse(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Batch(Base, TimestampMixin):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(60), nullable=False)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    __table_args__ = (
        UniqueConstraint("product_id", "batch_number", name="uq_batch_product_number"),
    )


class StockItem(Base):
    """Current balance of a product in a warehouse (optionally per batch)."""
    __tablename__ = "stock_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"), nullable=False)
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", "batch_id", name="uq_stock_slot"),
        Index("ix_stock_product", "product_id"),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    qty_change: Mapped[Decimal] = mapped_column(QTY, nullable=False)  # +in / -out
    kind: Mapped[str] = mapped_column(String(30), nullable=False)     # purchase/sale/transfer/adjust/damage/count
    ref_type: Mapped[str] = mapped_column(String(30), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(200), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# --------------------------------------------------------------------------
# Finance accounts
# --------------------------------------------------------------------------
class Account(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="cash")  # cash/bank/mobile_money
    balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class ExpenseCategory(Base, TimestampMixin):
    __tablename__ = "expense_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Expense(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_categories.id"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------
# Sales / Purchases
# --------------------------------------------------------------------------
class Sale(Base, TimestampMixin):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_no: Mapped[str] = mapped_column(String(40), nullable=False)
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/approved/returned/cancelled
    is_credit: Mapped[bool] = mapped_column(Boolean, default=False)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    paid: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    price_mode: Mapped[str] = mapped_column(String(20), default="retail")  # retail/wholesale
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("cashier_shifts.id"))
    lines: Mapped[list["SaleLine"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("invoice_no", name="uq_sale_invoice_no"),
        CheckConstraint("total >= 0", name="ck_sale_total_nonneg"),
    )

    @property
    def remaining(self) -> Decimal:
        return (self.total or Decimal("0")) - (self.paid or Decimal("0"))


class SaleLine(Base):
    __tablename__ = "sale_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sale: Mapped[Sale] = relationship(back_populates="lines")


class Purchase(Base, TimestampMixin):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_invoice: Mapped[str] = mapped_column(String(60), default="")
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    is_credit: Mapped[bool] = mapped_column(Boolean, default=False)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    extra_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    paid: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    lines: Mapped[list["PurchaseLine"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("doc_no", name="uq_purchase_doc_no"),)

    @property
    def remaining(self) -> Decimal:
        return (self.total or Decimal("0")) - (self.paid or Decimal("0"))


class PurchaseLine(Base):
    __tablename__ = "purchase_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    purchase: Mapped[Purchase] = relationship(back_populates="lines")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # in (receipt) / out (payment)
    party_type: Mapped[str] = mapped_column(String(10), default="")     # customer/supplier
    party_id: Mapped[int | None] = mapped_column(Integer)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="cash")
    note: Mapped[str] = mapped_column(Text, default="")


class CashierShift(Base, TimestampMixin):
    __tablename__ = "cashier_shifts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    opening_cash: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    closing_cash: Mapped[Decimal | None] = mapped_column(MONEY)
    expected_cash: Mapped[Decimal | None] = mapped_column(MONEY)
    difference: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open/closed
