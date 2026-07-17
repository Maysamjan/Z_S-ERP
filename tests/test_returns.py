"""Sales & purchase returns: atomic restore, over-return / duplicate guards,
exact-batch restoration, schema v3 migration, and the wired return pages."""

from decimal import Decimal

import pytest

from zenith.core.exceptions import BusinessRuleError, ValidationError
from zenith.db.base import Database, session_scope
from zenith.db.models import Customer, Supplier, Batch, SalesReturn, PurchaseReturn
from zenith.services import bootstrap, inventory
from zenith.services.auth import AuthService
from zenith.services.catalog import CatalogService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.sales import SalesService, LineInput
from zenith.services.returns import SalesReturnService, PurchaseReturnService, ReturnLineInput


def _seed(db):
    with session_scope(db) as s:
        admin = bootstrap.initialize(s, profile_code="GENERAL_STORE", business_name="T",
                                     admin_username="admin", admin_password="admin123")
    with session_scope(db) as s:
        admin = AuthService(s).login("admin", "admin123").user
        prod = CatalogService(s).create_product(admin, code="P1", name="Rice",
                                                purchase_price="70", sale_price="100")
        sup = PartyService(s).create_supplier(admin, "ACME")
        po = PurchaseService(s).create_purchase(admin, supplier_id=sup.id,
                                                lines=[PurchaseLineInput(prod.id, "50", "70")])
        PurchaseService(s).approve_purchase(admin, po.id)
        cust = PartyService(s).create_customer(admin, "Bob", credit_limit="100000")
        sale = SalesService(s).create_sale(admin, customer_id=cust.id,
                                           lines=[LineInput(prod.id, "10", Decimal("100"))], is_credit=True)
        SalesService(s).approve_sale(admin, sale.id)
        return {
            "prod": prod.id, "cust": cust.id, "sup": sup.id,
            "sale": sale.id, "sale_line": sale.lines[0].id,
            "po": po.id, "po_line": po.lines[0].id,
        }


def _admin(db):
    with session_scope(db) as s:
        return AuthService(s).login("admin", "admin123").user


def test_sales_return_restores_stock_and_reduces_receivable(db):
    ids = _seed(db)
    admin = _admin(db)
    with session_scope(db) as s:
        assert inventory.balance(s, ids["prod"]) == Decimal("40")
    with session_scope(db) as s:
        SalesReturnService(s).create_return(admin, ids["sale"], [ReturnLineInput(ids["sale_line"], "3")])
    with session_scope(db) as s:
        assert inventory.balance(s, ids["prod"]) == Decimal("43")
        assert s.get(Customer, ids["cust"]).balance == Decimal("700")  # 1000 - 300


def test_over_return_blocked_and_no_partial_write(db):
    ids = _seed(db)
    admin = _admin(db)
    with session_scope(db) as s:
        with pytest.raises(BusinessRuleError):
            SalesReturnService(s).create_return(admin, ids["sale"], [ReturnLineInput(ids["sale_line"], "11")])
    with session_scope(db) as s:
        assert inventory.balance(s, ids["prod"]) == Decimal("40")  # unchanged


def test_duplicate_return_blocked(db):
    ids = _seed(db)
    admin = _admin(db)
    with session_scope(db) as s:
        SalesReturnService(s).create_return(admin, ids["sale"], [ReturnLineInput(ids["sale_line"], "10")])
    with session_scope(db) as s:
        assert inventory.balance(s, ids["prod"]) == Decimal("50")
        with pytest.raises(BusinessRuleError):
            SalesReturnService(s).create_return(admin, ids["sale"], [ReturnLineInput(ids["sale_line"], "1")])


def test_purchase_return_removes_stock_and_reduces_payable(db):
    ids = _seed(db)
    admin = _admin(db)
    with session_scope(db) as s:
        before = s.get(Supplier, ids["sup"]).balance
        PurchaseReturnService(s).create_return(admin, ids["po"], [ReturnLineInput(ids["po_line"], "5")])
    with session_scope(db) as s:
        assert inventory.balance(s, ids["prod"]) == Decimal("35")  # 40 - 5
        assert s.get(Supplier, ids["sup"]).balance == before - Decimal("350")


def test_sales_return_restores_exact_batch(db):
    with session_scope(db) as s:
        admin = bootstrap.initialize(s, profile_code="PHARMACY", business_name="Rx",
                                     admin_username="admin", admin_password="admin123")
    admin = _admin(db)
    with session_scope(db) as s:
        prod = CatalogService(s).create_product(admin, code="M1", name="Amox",
                                                sale_price="20", batch_tracked=True)
        wh = inventory.default_warehouse(s)
        batch = Batch(product_id=prod.id, batch_number="B1")
        s.add(batch); s.flush()
        inventory.apply_movement(s, product_id=prod.id, warehouse_id=wh.id, qty_change=Decimal("20"),
                                 kind="purchase", batch_id=batch.id, actor=admin)
        sale = SalesService(s).create_sale(admin, customer_id=None,
                                           lines=[LineInput(prod.id, "5", Decimal("20"), batch_id=batch.id)])
        SalesService(s).approve_sale(admin, sale.id)
        pid, bid, sid, slid = prod.id, batch.id, sale.id, sale.lines[0].id
    with session_scope(db) as s:
        assert inventory.balance(s, pid, inventory.default_warehouse(s).id) == Decimal("15")
        SalesReturnService(s).create_return(admin, sid, [ReturnLineInput(slid, "5")])
    with session_scope(db) as s:
        # stock is back on the exact original batch
        by_batch = dict((b.id, q) for b, q in inventory.batch_stock(s, pid))
        assert by_batch[bid] == Decimal("20")


def test_migration_v2_to_v3_adds_returned_qty_and_tables(tmp_path):
    """An existing v2 database gains returned_qty columns and the return tables."""
    from sqlalchemy import create_engine, text, inspect
    dbfile = tmp_path / "v2.db"
    eng = create_engine(f"sqlite:///{dbfile}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE sale_lines (id INTEGER PRIMARY KEY, sale_id INTEGER, "
                       "product_id INTEGER, quantity NUMERIC, unit_price NUMERIC, line_total NUMERIC)"))
        c.execute(text("CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER, applied_at DATETIME)"))
        c.execute(text("INSERT INTO schema_version (version, applied_at) VALUES (2, '2026-01-01')"))
    eng.dispose()

    from zenith.db.migrations import run_migrations
    db = Database(f"sqlite:///{dbfile}")
    report = run_migrations(db, profile_code=None, backup=False)
    assert report.to_version == 3
    insp = inspect(db.engine)
    assert "returned_qty" in {c["name"] for c in insp.get_columns("sale_lines")}
    assert "sales_returns" in insp.get_table_names()
    assert "purchase_return_lines" in insp.get_table_names()


@pytest.mark.gui
def test_return_pages_build_and_post(data_dir):
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    db = Database("sqlite:///:memory:")
    db.create_all()
    ids = _seed(db)
    from zenith.services.auth import AuthService
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
    from zenith.ui.context import AppContext
    from zenith.ui.pages.returns_pages import SalesReturnsPage
    ctx = AppContext(db=db, profile_code="GENERAL_STORE", business_name="T", session=sess)
    ctx.apply_theme(app)
    page = SalesReturnsPage(ctx)
    # the approved sale is listed
    assert page.table.table.rowCount() == 1
    # post a return directly through the service the page uses
    with session_scope(db) as s:
        SalesReturnService(s).create_return(sess.user, ids["sale"], [ReturnLineInput(ids["sale_line"], "2")])
    with session_scope(db) as s:
        assert inventory.balance(s, ids["prod"]) == Decimal("42")
