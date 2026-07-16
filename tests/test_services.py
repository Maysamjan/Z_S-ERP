"""Service-layer business rules and transaction safety."""

from decimal import Decimal

import pytest

from zenith.core.exceptions import (
    AuthenticationError, PermissionDenied, InsufficientStock, CreditLimitExceeded,
    ValidationError, ExpiredStockError,
)
from zenith.db.base import session_scope
from zenith.db.models import Role, User, Batch
from zenith.security.password import hash_password
from zenith.services import inventory
from zenith.services.auth import AuthService
from zenith.services.catalog import CatalogService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.sales import SalesService, LineInput


def _cashier(session):
    from sqlalchemy import select
    role = session.scalar(select(Role).where(Role.name == "Cashier"))
    u = User(username="cash", full_name="C", password_hash=hash_password("cash123"), role_id=role.id)
    session.add(u)
    session.flush()
    return u


def test_login_success_and_failure(db, admin):
    with session_scope(db) as s:
        auth = AuthService(s)
        sess = auth.login("admin", "admin123")
        assert sess.user.username == "admin"
        with pytest.raises(AuthenticationError):
            auth.login("admin", "wrong")


def test_rate_limit_locks_account(db, admin):
    with session_scope(db) as s:
        auth = AuthService(s)
        for _ in range(5):
            with pytest.raises(AuthenticationError):
                auth.login("admin", "bad")
    with session_scope(db) as s:
        from zenith.core.exceptions import RateLimited
        with pytest.raises(RateLimited):
            AuthService(s).login("admin", "admin123")


def test_duplicate_product_code_rejected(db, admin):
    with session_scope(db) as s:
        cat = CatalogService(s)
        cat.create_product(admin, code="P1", name="A", sale_price="10")
        with pytest.raises(ValidationError):
            cat.create_product(admin, code="P1", name="B", sale_price="10")


def test_sale_deducts_stock_atomically(db, admin):
    with session_scope(db) as s:
        p = CatalogService(s).create_product(admin, code="P1", name="Rice", sale_price="100", purchase_price="70")
        sup = PartyService(s).create_supplier(admin, "ACME")
        pur = PurchaseService(s)
        po = pur.create_purchase(admin, supplier_id=sup.id, lines=[PurchaseLineInput(p.id, "10", "70")])
        pur.approve_purchase(admin, po.id)
        assert inventory.balance(s, p.id) == Decimal("10")
        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=None, lines=[LineInput(p.id, "3", Decimal("100"))])
        sales.approve_sale(admin, so.id)
        assert inventory.balance(s, p.id) == Decimal("7")


def test_insufficient_stock_rolls_back(db, admin):
    with session_scope(db) as s:
        p = CatalogService(s).create_product(admin, code="P1", name="X", sale_price="5")
        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=None, lines=[LineInput(p.id, "100", Decimal("5"))])
        with pytest.raises(InsufficientStock):
            sales.approve_sale(admin, so.id)
    # nothing was deducted / no negative stock created
    with session_scope(db) as s2:
        from sqlalchemy import select
        from zenith.db.models import Product
        pid = s2.scalar(select(Product.id))
        assert inventory.balance(s2, pid) == Decimal("0")


def test_credit_limit_enforced(db, admin):
    with session_scope(db) as s:
        p = CatalogService(s).create_product(admin, code="P1", name="X", sale_price="100")
        sup = PartyService(s).create_supplier(admin, "S")
        pur = PurchaseService(s)
        po = pur.create_purchase(admin, supplier_id=sup.id, lines=[PurchaseLineInput(p.id, "100", "50")])
        pur.approve_purchase(admin, po.id)
        cust = PartyService(s).create_customer(admin, "Bob", credit_limit="150")
        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=cust.id, lines=[LineInput(p.id, "5", Decimal("100"))], is_credit=True)
        with pytest.raises(CreditLimitExceeded):
            sales.approve_sale(admin, so.id)


def test_permission_denied_for_cashier(db, admin):
    with session_scope(db) as s:
        cashier = _cashier(s)
        p = CatalogService(s).create_product(admin, code="P1", name="X", sale_price="10")
        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=None, lines=[LineInput(p.id, "1", Decimal("10"))])
        with pytest.raises(PermissionDenied):
            sales.approve_sale(cashier, so.id)


def test_expired_batch_blocked(db, admin):
    from datetime import date, timedelta
    with session_scope(db) as s:
        p = CatalogService(s).create_product(admin, code="MED1", name="Amox", sale_price="20")
        wh = inventory.default_warehouse(s)
        batch = Batch(product_id=p.id, batch_number="B1", expiry_date=date.today() - timedelta(days=1))
        s.add(batch); s.flush()
        inventory.apply_movement(s, product_id=p.id, warehouse_id=wh.id, qty_change=Decimal("10"),
                                 kind="purchase", batch_id=batch.id, actor=admin)
        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=None,
                               lines=[LineInput(p.id, "1", Decimal("20"), batch_id=batch.id)])
        with pytest.raises(ExpiredStockError):
            sales.approve_sale(admin, so.id, block_expired=True)


def test_stock_transfer_between_warehouses(db, admin):
    from zenith.db.models import Warehouse
    with session_scope(db) as s:
        p = CatalogService(s).create_product(admin, code="P1", name="X", sale_price="10")
        wh1 = inventory.default_warehouse(s)
        wh2 = Warehouse(code="W2", name="Second")
        s.add(wh2); s.flush()
        inventory.apply_movement(s, product_id=p.id, warehouse_id=wh1.id, qty_change=Decimal("20"),
                                 kind="purchase", actor=admin)
        inventory.transfer(s, admin, product_id=p.id, from_wh=wh1.id, to_wh=wh2.id, quantity=Decimal("8"))
        assert inventory.balance(s, p.id, wh1.id) == Decimal("12")
        assert inventory.balance(s, p.id, wh2.id) == Decimal("8")
        assert inventory.balance(s, p.id) == Decimal("20")
