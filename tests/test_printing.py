"""Branded document rendering: identity, lines, totals, RTL, PDF export, preview."""

from decimal import Decimal

import pytest

pytest.importorskip("PyQt6")

from zenith.db.base import Database, session_scope
from zenith.services import bootstrap
from zenith.services.auth import AuthService
from zenith.services.business_identity import BusinessIdentityService
from zenith.services.catalog import CatalogService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.sales import SalesService, LineInput
from zenith.services.printing import render_sale_invoice, export_pdf
from zenith.ui import i18n


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def posted_sale(data_dir):
    """A db with saved identity and one approved sale; returns (db, sale_id, sess)."""
    db = Database("sqlite:///:memory:")
    db.create_all()
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code="GENERAL_STORE", business_name="فروشگاه دمو",
                             admin_username="admin", admin_password="admin123")
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
        admin = sess.user
        BusinessIdentityService(s).update(
            admin, business_name="فروشگاه دمو", business_name_en="Demo Store",
            phone="+93 700 111 222", address="کابل", address_en="Kabul, Dehburi",
            invoice_footer_en="Thank you!", terms_en="No returns after 7 days.",
            invoice_footer_fa="تشکر از خرید شما", tax_no="TAX-99",
        )
        prod = CatalogService(s).create_product(admin, code="P1", name="Rice 5kg",
                                                purchase_price="70", sale_price="100")
        sup = PartyService(s).create_supplier(admin, "ACME")
        po = PurchaseService(s).create_purchase(
            admin, supplier_id=sup.id, lines=[PurchaseLineInput(prod.id, "50", "70")])
        PurchaseService(s).approve_purchase(admin, po.id)
        cust = PartyService(s).create_customer(admin, "Bob", phone="0777")
        sale = SalesService(s).create_sale(
            admin, customer_id=cust.id, lines=[LineInput(prod.id, "3", Decimal("100"))], paid="200")
        SalesService(s).approve_sale(admin, sale.id)
        sale_id = sale.id
    return db, sale_id, sess


def test_a4_invoice_uses_business_identity_en(posted_sale):
    db, sale_id, _ = posted_sale
    i18n.set_locale("en_US")
    with session_scope(db) as s:
        doc = render_sale_invoice(s, sale_id, paper="a4", locale="en_US")
    for needle in ["Demo Store", "+93 700 111 222", "Kabul, Dehburi", "Tax: TAX-99",
                   "Rice 5kg", "300.00", "200.00", "100.00", "Thank you!",
                   "No returns after 7 days.", "Bob", "INV-", "direction: ltr"]:
        assert needle in doc.html, f"missing: {needle}"


def test_receipt_rtl_persian(posted_sale):
    db, sale_id, _ = posted_sale
    with session_scope(db) as s:
        doc = render_sale_invoice(s, sale_id, paper="80mm", locale="fa_AF")
    assert "فروشگاه دمو" in doc.html          # Persian business name
    assert "تشکر از خرید شما" in doc.html      # Persian footer
    assert "direction: rtl" in doc.html
    assert "width: 72mm" in doc.html


def test_58mm_width(posted_sale):
    db, sale_id, _ = posted_sale
    with session_scope(db) as s:
        doc = render_sale_invoice(s, sale_id, paper="58mm", locale="en_US")
    assert "width: 50mm" in doc.html


def test_pdf_export_produces_file(posted_sale, qapp, tmp_path):
    db, sale_id, _ = posted_sale
    with session_scope(db) as s:
        doc = render_sale_invoice(s, sale_id, paper="a4", locale="en_US")
    out = export_pdf(doc, tmp_path / "invoice.pdf")
    assert out.exists() and out.stat().st_size > 1000
    assert out.read_bytes()[:5] == b"%PDF-"


def test_unposted_sale_raises(posted_sale):
    from zenith.core.exceptions import NotFound
    db, _, _ = posted_sale
    with session_scope(db) as s:
        with pytest.raises(NotFound):
            render_sale_invoice(s, 999999)


@pytest.mark.gui
def test_preview_dialog_builds_with_real_data(posted_sale, qapp):
    from zenith.ui.context import AppContext
    from zenith.ui.dialogs.print_preview import SalePrintPreviewDialog
    db, sale_id, sess = posted_sale
    ctx = AppContext(db=db, profile_code="GENERAL_STORE", business_name="Demo", session=sess)
    dlg = SalePrintPreviewDialog(ctx, sale_id)
    html = dlg.view.toHtml()
    assert "Rice 5kg" in html and "INV-" in html   # real data, not samples
    # switching paper re-renders
    dlg.paper.setCurrentIndex(1)
    assert "Rice 5kg" in dlg.view.toHtml()
