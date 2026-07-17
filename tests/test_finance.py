"""Finance: receipts, supplier payments, expenses, transfers, reversals.

Covers the required end-to-end workflows plus duplicate protection, atomic
rollback, permission enforcement, bilingual GUI construction, and branded
voucher PDF output. All amounts are Decimal.
"""

from decimal import Decimal

import pytest

from zenith.core.exceptions import (
    DuplicatePosting, PermissionDenied, ValidationError, AlreadyReversed,
)
from zenith.db.base import Database, session_scope
from zenith.db.models import Account, Customer, Supplier, Role, User, Sale
from zenith.security.password import hash_password
from zenith.services import bootstrap, reporting
from zenith.services.auth import AuthService
from zenith.services.catalog import CatalogService
from zenith.services.parties import PartyService
from zenith.services.purchases import PurchaseService, PurchaseLineInput
from zenith.services.sales import SalesService, LineInput
from zenith.services.finance import (
    AccountService, ReceiptService, SupplierPaymentService, ExpenseService,
    TransferService, Allocation,
)


def _admin(db):
    with session_scope(db) as s:
        return AuthService(s).login("admin", "admin123").user


def _seed(db):
    with session_scope(db) as s:
        bootstrap.initialize(s, profile_code="GENERAL_STORE", business_name="T",
                             admin_username="admin", admin_password="admin123")
    with session_scope(db) as s:
        ad = AuthService(s).login("admin", "admin123").user
        cash = s.query(Account).filter_by(kind="cash").first()
        bank = AccountService(s).create_account(ad, "Bank", kind="bank")
        prod = CatalogService(s).create_product(ad, code="P1", name="Rice",
                                                purchase_price="70", sale_price="100")
        sup = PartyService(s).create_supplier(ad, "ACME")
        po = PurchaseService(s).create_purchase(ad, supplier_id=sup.id,
                                                lines=[PurchaseLineInput(prod.id, "50", "70")], is_credit=True)
        PurchaseService(s).approve_purchase(ad, po.id)
        cust = PartyService(s).create_customer(ad, "Bob", credit_limit="1000000")
        sale = SalesService(s).create_sale(ad, customer_id=cust.id,
                                           lines=[LineInput(prod.id, "10", Decimal("100"))], is_credit=True)
        SalesService(s).approve_sale(ad, sale.id)
        return {"cash": cash.id, "bank": bank.id, "cust": cust.id, "sup": sup.id,
                "sale": sale.id, "po": po.id, "prod": prod.id}


# 1. Credit sale -> partial receipt
def test_receipt_updates_balances_and_allocates(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        assert s.get(Customer, ids["cust"]).balance == Decimal("1000")
        ReceiptService(s).create_receipt(ad, customer_id=ids["cust"], amount="400",
                                         account_id=ids["cash"], reference="R1")
    with session_scope(db) as s:
        assert s.get(Customer, ids["cust"]).balance == Decimal("600")   # decreased
        assert s.get(Account, ids["cash"]).balance == Decimal("400")    # cash increased
        assert s.get(Sale, ids["sale"]).paid == Decimal("400")          # allocated to invoice


# 2. Credit purchase -> partial supplier payment
def test_supplier_payment_updates_balances(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        assert s.get(Supplier, ids["sup"]).balance == Decimal("3500")
        SupplierPaymentService(s).create_payment(ad, supplier_id=ids["sup"], amount="1000",
                                                 account_id=ids["cash"], reference="P1")
    with session_scope(db) as s:
        assert s.get(Supplier, ids["sup"]).balance == Decimal("2500")   # decreased
        assert s.get(Account, ids["cash"]).balance == Decimal("-1000")  # cash decreased


# 3. Expense -> cash down, net profit down
def test_expense_reduces_cash_and_net_profit(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        gross = reporting.profit_for_day(s)
        exp = ExpenseService(s).create_expense(ad, amount="50", account_id=ids["cash"], description="fuel")
        ExpenseService(s).approve_expense(ad, exp.id)
        assert reporting.net_profit_for_day(s) == gross - Decimal("50")
    with session_scope(db) as s:
        assert s.get(Account, ids["cash"]).balance == Decimal("-50")


# 4. Transfer conserves total money
def test_transfer_conserves_total(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        before = s.get(Account, ids["cash"]).balance + s.get(Account, ids["bank"]).balance
        TransferService(s).create_transfer(ad, from_account_id=ids["cash"],
                                           to_account_id=ids["bank"], amount="200", reference="T1")
    with session_scope(db) as s:
        cash = s.get(Account, ids["cash"]).balance
        bank = s.get(Account, ids["bank"]).balance
        assert bank == Decimal("200")
        assert cash + bank == before   # conserved


# 5. Duplicate protection
def test_duplicate_receipt_blocked(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        ReceiptService(s).create_receipt(ad, customer_id=ids["cust"], amount="100",
                                         account_id=ids["cash"], reference="DUP")
    with session_scope(db) as s:
        with pytest.raises(DuplicatePosting):
            ReceiptService(s).create_receipt(ad, customer_id=ids["cust"], amount="100",
                                             account_id=ids["cash"], reference="DUP")


def test_duplicate_transfer_blocked(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        TransferService(s).create_transfer(ad, from_account_id=ids["cash"],
                                           to_account_id=ids["bank"], amount="50", reference="TX")
    with session_scope(db) as s:
        with pytest.raises(DuplicatePosting):
            TransferService(s).create_transfer(ad, from_account_id=ids["cash"],
                                               to_account_id=ids["bank"], amount="50", reference="TX")


# 6. Atomic rollback on failure
def test_receipt_rolls_back_on_bad_allocation(db):
    ids = _seed(db); ad = _admin(db)
    # second customer whose sale we will wrongly allocate to
    with session_scope(db) as s:
        other = PartyService(s).create_customer(ad, "Other")
        other_id = other.id
    # The exception must escape session_scope so it rolls back (as the UI does).
    with pytest.raises(ValidationError):
        with session_scope(db) as s:
            ReceiptService(s).create_receipt(
                ad, customer_id=other_id, amount="100", account_id=ids["cash"],
                allocations=[Allocation(ids["sale"], Decimal("100"))],  # sale belongs to Bob
                auto_allocate=False)
    with session_scope(db) as s:
        # nothing persisted: cash unchanged, no payment rows
        assert s.get(Account, ids["cash"]).balance == Decimal("0")
        from zenith.db.models import Payment
        assert s.query(Payment).count() == 0


def test_same_account_transfer_rejected(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        with pytest.raises(ValidationError):
            TransferService(s).create_transfer(ad, from_account_id=ids["cash"],
                                               to_account_id=ids["cash"], amount="10")


# 7. Permission enforcement (service layer)
def test_permissions_enforced(db):
    ids = _seed(db)
    with session_scope(db) as s:
        role = s.scalar(__import__("sqlalchemy").select(Role).where(Role.name == "Storekeeper"))
        keeper = User(username="keep", full_name="K", password_hash=hash_password("keep123"), role_id=role.id)
        s.add(keeper); s.flush()
        from zenith.services.permissions_util import attach_permissions
        attach_permissions(s, keeper); s.expunge(keeper)
    with session_scope(db) as s:
        with pytest.raises(PermissionDenied):
            ReceiptService(s).create_receipt(keeper, customer_id=ids["cust"], amount="10",
                                             account_id=ids["cash"])


# Reversal
def test_reversal_restores_and_blocks_double(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        p = ReceiptService(s).create_receipt(ad, customer_id=ids["cust"], amount="300",
                                             account_id=ids["cash"], reference="RV")
        pid = p.id
    with session_scope(db) as s:
        assert s.get(Customer, ids["cust"]).balance == Decimal("700")
        ReceiptService(s).reverse(ad, pid, reason="entered twice")
    with session_scope(db) as s:
        assert s.get(Customer, ids["cust"]).balance == Decimal("1000")   # restored
        assert s.get(Account, ids["cash"]).balance == Decimal("0")       # restored
        with pytest.raises(AlreadyReversed):
            ReceiptService(s).reverse(ad, pid, reason="again")


def test_reversal_requires_reason(db):
    ids = _seed(db); ad = _admin(db)
    with session_scope(db) as s:
        p = ReceiptService(s).create_receipt(ad, customer_id=ids["cust"], amount="100",
                                             account_id=ids["cash"], reference="NR")
        pid = p.id
    with session_scope(db) as s:
        with pytest.raises(ValidationError):
            ReceiptService(s).reverse(ad, pid, reason="")


# 8. Bilingual GUI construction
@pytest.mark.gui
@pytest.mark.parametrize("locale", ["en_US", "fa_AF"])
def test_finance_pages_build_bilingual(db, locale):
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    _seed(db)
    with session_scope(db) as s:
        sess = AuthService(s).login("admin", "admin123")
    from zenith.ui.context import AppContext
    from zenith.ui.pages.finance_pages import (
        CashAccountsPage, ReceiptsPage, SupplierPaymentsPage, ExpensesPage, AccountTransfersPage,
    )
    ctx = AppContext(db=db, profile_code="WHOLESALE", business_name="D", session=sess, locale=locale)
    ctx.apply_theme(app); ctx.apply_direction(app)
    for Page in (CashAccountsPage, ReceiptsPage, SupplierPaymentsPage, ExpensesPage, AccountTransfersPage):
        page = Page(ctx)
        page.refresh()


# 9. Branded voucher PDF
@pytest.mark.gui
def test_receipt_voucher_pdf(db, tmp_path):
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    ids = _seed(db); ad = _admin(db)
    from zenith.services.business_identity import BusinessIdentityService
    from zenith.services.printing import render_customer_receipt, export_pdf
    with session_scope(db) as s:
        BusinessIdentityService(s).update(ad, business_name="Demo", business_name_en="Demo Store",
                                          phone="0700111222")
        p = ReceiptService(s).create_receipt(ad, customer_id=ids["cust"], amount="123.45",
                                             account_id=ids["cash"], reference="PDF")
        pid = p.id
    with session_scope(db) as s:
        doc = render_customer_receipt(s, pid, paper="a4", locale="en_US")
        assert "Demo Store" in doc.html and "Receipt Voucher" in doc.html and "123.45" in doc.html
    out = export_pdf(doc, tmp_path / "rcp.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"
