"""Sales invoices + customer accounts (credit ledger).

The authoritative test is the "Ahmad" acceptance workflow from the spec: an
opening balance, a partial-credit sale, a reopen that must preserve the balance,
a second credit sale, and an oldest-first payment. Every asserted number is the
number the spec requires. Supporting tests cover the ledger invariant
(``Customer.balance`` always equals the latest ledger entry), credit controls,
cash-customer rules, returns through the ledger, and the statement service.

All money is ``Decimal`` -- never float.
"""

from decimal import Decimal

import pytest

from zenith.core.exceptions import (
    BusinessRuleError, CreditLimitExceeded, ValidationError, PermissionDenied,
)
from zenith.db.base import session_scope
from zenith.db.models import Account, Customer, CustomerLedgerEntry, Sale, Role, User
from zenith.security.password import hash_password
from zenith.services import bootstrap, customer_ledger
from zenith.services.auth import AuthService
from zenith.services.catalog import CatalogService
from zenith.services.finance import ReceiptService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.returns import SalesReturnService, ReturnLineInput
from zenith.services.sales import SalesService, LineInput


def _admin(db):
    with session_scope(db) as s:
        return AuthService(s).login("admin", "admin123").user


def _seed(db):
    """Bootstrap, one product stocked with 100 units, a cash account."""
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code="GENERAL_STORE", business_name="T",
                             admin_username="admin", admin_password="admin123")
    with session_scope(db) as s:
        ad = AuthService(s).login("admin", "admin123").user
        cash = s.query(Account).filter_by(kind="cash").first()
        prod = CatalogService(s).create_product(ad, code="P1", name="Rice",
                                                purchase_price="70", sale_price="100")
        sup = PartyService(s).create_supplier(ad, "ACME")
        po = PurchaseService(s).create_purchase(
            ad, supplier_id=sup.id, lines=[PurchaseLineInput(prod.id, "100", "70")], is_credit=True)
        PurchaseService(s).approve_purchase(ad, po.id)
        return {"cash": cash.id, "prod": prod.id}


# --------------------------------------------------------------------------
# The Ahmad acceptance workflow (spec section: acceptance test)
# --------------------------------------------------------------------------
def test_ahmad_acceptance_workflow(db):
    ids = _seed(db); ad = _admin(db)
    prod = ids["prod"]

    # Ahmad, opening balance 5,000 AFN owed to the business.
    with session_scope(db) as s:
        ahmad = PartyService(s).create_customer(
            ad, "Ahmad", phone="0700000001", opening_balance="5000", credit_limit="100000")
        cid = ahmad.id
    with session_scope(db) as s:
        assert s.get(Customer, cid).balance == Decimal("5000")

    # Sale of 800 (8 x 100), pays 300 in cash -> 500 on credit.
    with session_scope(db) as s:
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(prod, Decimal("8"), Decimal("100"))],
            is_credit=True, paid="300")
        SalesService(s).approve_sale(ad, sale.id)
        sale1 = sale.id
    with session_scope(db) as s:
        sale = s.get(Sale, sale1)
        assert sale.paid == Decimal("300")              # invoice paid
        assert sale.remaining == Decimal("500")         # invoice remaining
        assert sale.previous_balance == Decimal("5000") # previous balance
        assert sale.new_balance == Decimal("5500")      # new balance
        assert sale.payment_status == "partial"         # PARTIALLY_PAID
        assert s.get(Customer, cid).balance == Decimal("5500")

    # Reopen (view again) must NOT change the balance.
    with session_scope(db) as s:
        assert customer_ledger.current_balance(s, cid) == Decimal("5500")
        assert s.get(Customer, cid).balance == Decimal("5500")

    # A second, fully-credit sale of 1,000 (10 x 100) -> balance 6,500.
    with session_scope(db) as s:
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(prod, Decimal("10"), Decimal("100"))],
            is_credit=True, paid="0")
        SalesService(s).approve_sale(ad, sale.id)
        sale2 = sale.id
    with session_scope(db) as s:
        assert s.get(Customer, cid).balance == Decimal("6500")
        assert s.get(Sale, sale2).payment_status == "unpaid"

    # Receive 2,000, allocated oldest-first -> balance 4,500.
    with session_scope(db) as s:
        ReceiptService(s).create_receipt(ad, customer_id=cid, amount="2000",
                                         account_id=ids["cash"], reference="RCPT1")
    with session_scope(db) as s:
        assert s.get(Customer, cid).balance == Decimal("4500")
        # oldest invoice cleared first: sale1's 500 remainder, then sale2's 1000
        assert s.get(Sale, sale1).paid == Decimal("800")
        assert s.get(Sale, sale1).payment_status == "paid"
        assert s.get(Sale, sale2).paid == Decimal("1000")
        assert s.get(Sale, sale2).payment_status == "paid"


# --------------------------------------------------------------------------
# Ledger invariant: Customer.balance == latest ledger entry balance, always.
# --------------------------------------------------------------------------
def test_ledger_is_single_source_of_truth(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Zia", opening_balance="1000", credit_limit="100000")
        cid = c.id
        for _ in range(3):
            sale = SalesService(s).create_sale(
                ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("2"), Decimal("100"))],
                is_credit=True, paid="0")
            SalesService(s).approve_sale(ad, sale.id)
        ReceiptService(s).create_receipt(ad, customer_id=cid, amount="500", account_id=ids["cash"])
    with session_scope(db) as s:
        last = customer_ledger.last_balance(s, cid)
        assert s.get(Customer, cid).balance == last
        # 1000 opening + 3*200 - 500 = 1100
        assert last == Decimal("1100")


def test_opening_balance_owed_to_customer_is_negative(db):
    _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(
            ad, "Karim", opening_balance="300", opening_balance_type="owed_to_customer")
        assert s.get(Customer, c.id).balance == Decimal("-300")


def test_no_opening_balance_posts_no_ledger_entry(db):
    _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Nadia")
        assert s.query(CustomerLedgerEntry).filter_by(customer_id=c.id).count() == 0
        assert s.get(Customer, c.id).balance == Decimal("0")


# --------------------------------------------------------------------------
# Credit controls
# --------------------------------------------------------------------------
def test_credit_sale_requires_customer(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        sale = SalesService(s).create_sale(
            ad, customer_id=None, lines=[LineInput(ids["prod"], Decimal("1"), Decimal("100"))],
            is_credit=True, paid="0")
        with pytest.raises(BusinessRuleError) as ei:
            SalesService(s).approve_sale(ad, sale.id)
        assert ei.value.message_key == "error.credit_needs_customer"


def test_cash_customer_cannot_carry_debt(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        walkin = PartyService(s).create_customer(ad, "Walk-in", is_cash_customer=True)
        sale = SalesService(s).create_sale(
            ad, customer_id=walkin.id, lines=[LineInput(ids["prod"], Decimal("1"), Decimal("100"))],
            is_credit=True, paid="0")
        with pytest.raises(BusinessRuleError) as ei:
            SalesService(s).approve_sale(ad, sale.id)
        assert ei.value.message_key == "error.cash_customer_no_debt"


def test_credit_limit_enforced_and_overridable(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Limited", credit_limit="500")
        cid = c.id
    # a 600 credit sale exceeds the 500 limit
    with session_scope(db) as s:
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("6"), Decimal("100"))],
            is_credit=True, paid="0")
        with pytest.raises(CreditLimitExceeded):
            SalesService(s).approve_sale(ad, sale.id)
    # admin has CREDIT_OVERRIDE, so it goes through with the override flag
    with session_scope(db) as s:
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("6"), Decimal("100"))],
            is_credit=True, paid="0")
        SalesService(s).approve_sale(ad, sale.id, credit_override=True)
        assert s.get(Customer, cid).balance == Decimal("600")


def test_credit_override_requires_permission(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        role = s.scalar(__import__("sqlalchemy").select(Role).where(Role.name == "Cashier"))
        cashier = User(username="csh", full_name="C", password_hash=hash_password("csh123"),
                       role_id=role.id)
        s.add(cashier); s.flush()
        from zenith.services.permissions_util import attach_permissions
        attach_permissions(s, cashier); s.expunge(cashier)
        c = PartyService(s).create_customer(ad, "L2", credit_limit="100")
        cid = c.id
    with session_scope(db) as s:
        # cashier may create a sale but not approve past the limit even with override
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("2"), Decimal("100"))],
            is_credit=True, paid="0")
        sid = sale.id
    with session_scope(db) as s:
        with pytest.raises(PermissionDenied):
            SalesService(s).approve_sale(cashier, sid, credit_override=True)


def test_duplicate_phone_blocked(db):
    _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        PartyService(s).create_customer(ad, "First", phone="0700123456")
    with session_scope(db) as s:
        with pytest.raises(ValidationError) as ei:
            PartyService(s).create_customer(ad, "Second", phone="0700123456")
        assert ei.value.message_key == "error.duplicate_phone_customer"
    # explicit override allows it
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Second", phone="0700123456",
                                            allow_duplicate_phone=True)
        assert c.id is not None


# --------------------------------------------------------------------------
# Returns reduce the customer balance through the ledger
# --------------------------------------------------------------------------
def test_sales_return_credits_customer_ledger(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Rahim", credit_limit="100000")
        cid = c.id
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("5"), Decimal("100"))],
            is_credit=True, paid="0")
        SalesService(s).approve_sale(ad, sale.id)
        sid = sale.id
        line_id = sale.lines[0].id
    with session_scope(db) as s:
        assert s.get(Customer, cid).balance == Decimal("500")
        SalesReturnService(s).create_return(ad, sid, [ReturnLineInput(line_id, Decimal("2"))])
    with session_scope(db) as s:
        # 500 - (2 x 100) = 300
        assert s.get(Customer, cid).balance == Decimal("300")
        assert customer_ledger.last_balance(s, cid) == Decimal("300")


# --------------------------------------------------------------------------
# Payment reversal re-adds the debt through the ledger
# --------------------------------------------------------------------------
def test_payment_reversal_restores_balance_via_ledger(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Sara", opening_balance="1000", credit_limit="100000")
        cid = c.id
        p = ReceiptService(s).create_receipt(ad, customer_id=cid, amount="400",
                                             account_id=ids["cash"], reference="RV")
        pid = p.id
    with session_scope(db) as s:
        assert s.get(Customer, cid).balance == Decimal("600")
        ReceiptService(s).reverse(ad, pid, reason="entered twice")
    with session_scope(db) as s:
        assert s.get(Customer, cid).balance == Decimal("1000")
        assert customer_ledger.last_balance(s, cid) == Decimal("1000")


# --------------------------------------------------------------------------
# Statement service
# --------------------------------------------------------------------------
def test_statement_lists_running_balance(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Omar", opening_balance="1000", credit_limit="100000")
        cid = c.id
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("3"), Decimal("100"))],
            is_credit=True, paid="0")
        SalesService(s).approve_sale(ad, sale.id)
        ReceiptService(s).create_receipt(ad, customer_id=cid, amount="500", account_id=ids["cash"])
    with session_scope(db) as s:
        st = customer_ledger.statement(s, cid)
        assert st.closing == Decimal("800")   # 1000 + 300 - 500
        assert st.lines[-1].balance == Decimal("800")
        assert st.total_debit == Decimal("1300")   # opening 1000 + sale 300
        assert st.total_credit == Decimal("500")   # payment
        totals = customer_ledger.totals(s, cid)
        assert totals["total_purchases"] == Decimal("300")
        assert totals["total_payments"] == Decimal("500")
        assert totals["balance"] == Decimal("800")


def test_aging_buckets_and_outstanding(db):
    ids = _seed(db); ad = _admin(db)
    from datetime import date, timedelta
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Aged", opening_balance="1000", credit_limit="100000")
        cid = c.id
        # an old unpaid invoice (dated 100 days ago) -> over-90 bucket
        old = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("2"), Decimal("100"))],
            is_credit=True, paid="0")
        old.date = date.today() - timedelta(days=100)
        SalesService(s).approve_sale(ad, old.id)
    with session_scope(db) as s:
        aging = customer_ledger.aging_for(s, cid)
        assert aging.over_90 == Decimal("200")     # the 100-day-old invoice
        assert aging.current == Decimal("1000")    # opening balance residual
        assert aging.balance == Decimal("1200")
        rows = customer_ledger.outstanding(s)
        assert any(r.customer_id == cid and r.balance == Decimal("1200") for r in rows)


@pytest.mark.gui
def test_customer_statement_pdf(db, tmp_path):
    from zenith.services.business_identity import BusinessIdentityService
    from zenith.services.printing import render_customer_statement, export_pdf
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        BusinessIdentityService(s).update(ad, business_name="Demo", business_name_en="Demo Store",
                                          phone="0700111222")
        c = PartyService(s).create_customer(ad, "Ahmad", opening_balance="5000", credit_limit="100000")
        cid = c.id
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("8"), Decimal("100"))],
            is_credit=True, paid="300")
        SalesService(s).approve_sale(ad, sale.id)
    with session_scope(db) as s:
        doc = render_customer_statement(s, cid, paper="a4", locale="en_US")
        assert "Demo Store" in doc.html and "Account Statement" in doc.html
        assert "Ahmad" in doc.html and "5,500.00" in doc.html   # closing balance
    out = export_pdf(doc, tmp_path / "stmt.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"


@pytest.mark.gui
def test_invoice_shows_previous_and_new_balance(db):
    from zenith.services.printing import render_sale_invoice
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "Ahmad", opening_balance="5000", credit_limit="100000")
        cid = c.id
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("8"), Decimal("100"))],
            is_credit=True, paid="300")
        SalesService(s).approve_sale(ad, sale.id)
        sid = sale.id
    with session_scope(db) as s:
        doc = render_sale_invoice(s, sid, paper="a4", locale="en_US")
        assert "Previous balance" in doc.html and "5,000.00" in doc.html
        assert "New balance" in doc.html and "5,500.00" in doc.html


@pytest.mark.gui
@pytest.mark.parametrize("locale", ["en_US", "fa_AF"])
def test_customer_pages_build_bilingual(db, locale):
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    ids = _seed(db)
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
        ad = sess.user
        c = PartyService(s).create_customer(ad, "Ahmad", opening_balance="5000", credit_limit="100000")
        cid = c.id
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("8"), Decimal("100"))],
            is_credit=True, paid="300")
        SalesService(s).approve_sale(ad, sale.id)
    from zenith.ui.context import AppContext
    from zenith.ui.pages.customers import CustomersPage, ReceivablesPage, CustomerAccountDialog
    ctx = AppContext(db=db, profile_code="WHOLESALE", business_name="D", session=sess, locale=locale)
    ctx.apply_theme(app); ctx.apply_direction(app)
    for Page in (CustomersPage, ReceivablesPage):
        page = Page(ctx)
        page.refresh()
    dlg = CustomerAccountDialog(ctx, cid)
    dlg.refresh()


def test_cash_sale_posts_no_ledger_entry(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        c = PartyService(s).create_customer(ad, "CashBuyer")
        cid = c.id
        sale = SalesService(s).create_sale(
            ad, customer_id=cid, lines=[LineInput(ids["prod"], Decimal("2"), Decimal("100"))],
            is_credit=False, paid="200")
        SalesService(s).approve_sale(ad, sale.id)
        assert sale.sale_type == "cash"
        assert sale.payment_status == "paid"
    with session_scope(db) as s:
        assert s.query(CustomerLedgerEntry).filter_by(customer_id=cid).count() == 0
        assert s.get(Customer, cid).balance == Decimal("0")
