"""Tests for the completion increment: migrations, business identity, costing,
duplicate prevention, FEFO, and the new transaction pages."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from zenith.db.base import Database, session_scope
from zenith.services import bootstrap, inventory
from zenith.services.catalog import CatalogService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.sales import SalesService, LineInput


# --------------------------------------------------------------------------
# Additive migrations
# --------------------------------------------------------------------------
def test_migration_adds_missing_columns_and_preserves_data(tmp_path):
    """Simulate a v1 database missing the v2 identity columns."""
    from sqlalchemy import create_engine, text
    dbfile = tmp_path / "old.db"
    eng = create_engine(f"sqlite:///{dbfile}")
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE business_settings ("
            "id INTEGER PRIMARY KEY, business_name VARCHAR, profile_code VARCHAR NOT NULL, "
            "logo_path VARCHAR, address VARCHAR, phone VARCHAR, email VARCHAR, "
            "currency VARCHAR, date_system VARCHAR, language VARCHAR, theme VARCHAR)"
        ))
        c.execute(text("CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER, applied_at DATETIME)"))
        c.execute(text("INSERT INTO business_settings (business_name, profile_code) VALUES ('Old Co','PHARMACY')"))
        c.execute(text("INSERT INTO schema_version (version, applied_at) VALUES (1, '2026-01-01')"))
    eng.dispose()

    from zenith.db.migrations import run_migrations, plan_missing
    db = Database(f"sqlite:///{dbfile}")
    missing_tables, missing_cols = plan_missing(db)
    assert any(col == "business_name_en" for _, col in missing_cols)

    report = run_migrations(db, profile_code=None, backup=False)
    assert "business_settings.business_name_en" in report.added_columns
    assert report.to_version == 2

    # data preserved + new column present
    from sqlalchemy import inspect, select
    from zenith.db.models import BusinessSettings
    live = {c["name"] for c in inspect(db.engine).get_columns("business_settings")}
    assert "business_name_en" in live and "tax_no" in live
    with db.session() as s:
        row = s.scalar(select(BusinessSettings))
        assert row.business_name == "Old Co"
        assert row.business_name_en == ""  # new column default


# --------------------------------------------------------------------------
# Business identity
# --------------------------------------------------------------------------
def test_business_identity_update_and_validation(db, admin):
    from zenith.services.business_identity import BusinessIdentityService
    from zenith.core.exceptions import ValidationError
    with session_scope(db) as s:
        svc = BusinessIdentityService(s)
        svc.update(admin, business_name="فروشگاه تست", business_name_en="Test Shop",
                   phone="+93 700 000 000", email="info@test.af", address="Kabul")
        ident = svc.get_identity()
        assert ident.name("fa_AF") == "فروشگاه تست"
        assert ident.name("en_US") == "Test Shop"
    with session_scope(db) as s:
        with pytest.raises(ValidationError):
            BusinessIdentityService(s).update(admin, email="not-an-email")
    with session_scope(db) as s:
        with pytest.raises(ValidationError):
            BusinessIdentityService(s).update(admin, phone="abc$$$")


def test_logo_copied_into_managed_dir(db, admin, tmp_path, data_dir):
    from zenith.services.business_identity import BusinessIdentityService
    # make a tiny fake PNG
    src = tmp_path / "logo.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    with session_scope(db) as s:
        stored = BusinessIdentityService(s).set_logo(admin, str(src))
    from pathlib import Path
    assert Path(stored).exists()
    # survives deletion of the original
    src.unlink()
    assert Path(stored).exists()


# --------------------------------------------------------------------------
# Paracetamol product-reuse workflow (spec section 41)
# --------------------------------------------------------------------------
def test_paracetamol_reuse_workflow(db, admin):
    with session_scope(db) as s:
        cat = CatalogService(s)
        prod = cat.create_product(admin, code="MED-PARA", name="Paracetamol 500mg",
                                  purchase_price="7", sale_price="10", strength="500mg",
                                  dosage_form="tablet")
        sup = PartyService(s).create_supplier(admin, "PharmaDist")
        pur = PurchaseService(s)
        po1 = pur.create_purchase(admin, supplier_id=sup.id,
                                  lines=[PurchaseLineInput(prod.id, "150", "7")])
        pur.approve_purchase(admin, po1.id)
        assert inventory.balance(s, prod.id) == Decimal("150")

        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=None, lines=[LineInput(prod.id, "100", Decimal("10"))])
        sales.approve_sale(admin, so.id)
        assert inventory.balance(s, prod.id) == Decimal("50")

        # second purchase reuses the SAME product (no duplicate master)
        po2 = pur.create_purchase(admin, supplier_id=sup.id,
                                  lines=[PurchaseLineInput(prod.id, "80", "8")])
        pur.approve_purchase(admin, po2.id)
        assert inventory.balance(s, prod.id) == Decimal("130")

        from sqlalchemy import select, func
        from zenith.db.models import Product, Purchase
        assert s.scalar(select(func.count()).select_from(Product).where(Product.name == "Paracetamol 500mg")) == 1
        assert s.scalar(select(func.count()).select_from(Purchase)) == 2


def test_duplicate_similar_blocked_but_variants_allowed(db, admin):
    from zenith.core.exceptions import ValidationError
    with session_scope(db) as s:
        cat = CatalogService(s)
        cat.create_product(admin, code="P-500", name="Paracetamol", strength="500mg",
                           dosage_form="tablet", sale_price="10")
        # same name + same strength/form => similar => blocked
        with pytest.raises(ValidationError):
            cat.create_product(admin, code="P-500B", name="Paracetamol", strength="500mg",
                               dosage_form="tablet", sale_price="10")
        # genuinely different strength/form => allowed
        syrup = cat.create_product(admin, code="P-SYR", name="Paracetamol", strength="120mg/5ml",
                                   dosage_form="syrup", sale_price="15")
        assert syrup.id is not None
        # explicit override allowed
        forced = cat.create_product(admin, code="P-500C", name="Paracetamol", strength="500mg",
                                    dosage_form="tablet", sale_price="10", allow_similar=True)
        assert forced.id is not None


# --------------------------------------------------------------------------
# Costing / profit
# --------------------------------------------------------------------------
def test_weighted_average_cost_and_profit(db, admin):
    from zenith.services import reporting
    with session_scope(db) as s:
        prod = CatalogService(s).create_product(admin, code="X1", name="Widget",
                                                purchase_price="0", sale_price="20")
        sup = PartyService(s).create_supplier(admin, "S")
        pur = PurchaseService(s)
        # 10 @ 5 and 10 @ 7  => WAC = 6
        for qty, price in [("10", "5"), ("10", "7")]:
            po = pur.create_purchase(admin, supplier_id=sup.id, lines=[PurchaseLineInput(prod.id, qty, price)])
            pur.approve_purchase(admin, po.id)
        assert reporting.weighted_avg_cost(s, prod.id) == Decimal("6.0000")
        sales = SalesService(s)
        so = sales.create_sale(admin, customer_id=None, lines=[LineInput(prod.id, "5", Decimal("20"))])
        sales.approve_sale(admin, so.id)
        # profit = 5 * (20 - 6) = 70
        assert reporting.profit_for_day(s, date.today()) == Decimal("70.0000")


# --------------------------------------------------------------------------
# Pharmacy FEFO
# --------------------------------------------------------------------------
def test_fefo_suggests_nearest_non_expired_batch(db, admin):
    from zenith.db.models import Batch
    with session_scope(db) as s:
        prod = CatalogService(s).create_product(admin, code="MED", name="Amox", sale_price="20", batch_tracked=True)
        wh = inventory.default_warehouse(s)
        today = date.today()
        b_expired = Batch(product_id=prod.id, batch_number="EXP", expiry_date=today - timedelta(days=1))
        b_near = Batch(product_id=prod.id, batch_number="NEAR", expiry_date=today + timedelta(days=30))
        b_far = Batch(product_id=prod.id, batch_number="FAR", expiry_date=today + timedelta(days=365))
        s.add_all([b_expired, b_near, b_far]); s.flush()
        for b in (b_expired, b_near, b_far):
            inventory.apply_movement(s, product_id=prod.id, warehouse_id=wh.id, qty_change=Decimal("10"),
                                     kind="purchase", batch_id=b.id, actor=admin)
        suggested = inventory.suggest_fefo_batch(s, prod.id, wh.id, today=today)
        assert suggested is not None and suggested.batch_number == "NEAR"  # nearest non-expired


# --------------------------------------------------------------------------
# GUI: new transaction pages build and post through the widgets
# --------------------------------------------------------------------------
@pytest.mark.gui
def test_new_purchase_and_sale_pages_post(tmp_path):
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    db = Database("sqlite:///:memory:")
    db.create_all()
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code="PHARMACY", business_name="Rx",
                             admin_username="admin", admin_password="admin123")
    from zenith.services.auth import AuthService
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
        prod = CatalogService(s).create_product(sess.user, code="M1", name="Med",
                                                purchase_price="5", sale_price="12")
        PartyService(s).create_supplier(sess.user, "Sup")
    pid = prod.id

    from zenith.ui.context import AppContext
    from zenith.ui.pages.transactions import NewPurchasePage, NewSalePage
    ctx = AppContext(db=db, profile_code="PHARMACY", business_name="Rx", session=sess)
    ctx.apply_theme(app)

    # Purchase 40 via the page
    pp = NewPurchasePage(ctx)
    idx = pp.product_combo.findData(pid)
    pp.product_combo.setCurrentIndex(idx)
    pp.qty_input.setValue(40)
    pp.price_input.setValue(5)
    pp._add_line()
    assert len(pp._lines) == 1
    pp._approve()
    with session_scope(db) as s:
        assert inventory.balance(s, pid) == Decimal("40")

    # Sell 15 via the page
    sp = NewSalePage(ctx)
    idx = sp.product_combo.findData(pid)
    sp.product_combo.setCurrentIndex(idx)
    sp.qty_input.setValue(15)
    sp.price_input.setValue(12)
    sp._add_line()
    sp._complete()
    with session_scope(db) as s:
        assert inventory.balance(s, pid) == Decimal("25")
