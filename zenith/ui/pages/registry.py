"""Map module keys -> page factories.

Only modules that appear here are shown in the sidebar (further intersected with
the active profile). This is the mechanism that guarantees no placeholder pages:
a module without a real page is simply not offered in this release.
"""

from __future__ import annotations

from typing import Callable

from zenith.profiles import modules as M
from zenith.ui.context import AppContext
from zenith.ui.pages.dashboard import DashboardPage
from zenith.ui.pages.products import ProductsPage
from zenith.ui.pages.customers import CustomersPage
from zenith.ui.pages.suppliers import SuppliersPage
from zenith.ui.pages.simple_pages import SalesListPage, StockBalancePage, AuditLogPage
from zenith.ui.pages.admin_pages import LicensePage, BackupPage, UsersPage, SettingsPage
from zenith.ui.pages.transactions import NewPurchasePage, NewSalePage
from zenith.ui.pages.returns_pages import SalesReturnsPage, PurchaseReturnsPage

PageFactory = Callable[[AppContext], object]

PAGE_REGISTRY: dict[str, PageFactory] = {
    M.DASHBOARD: DashboardPage,
    M.SALES_NEW: NewSalePage,
    M.POS: NewSalePage,
    M.SALES_RETURNS: SalesReturnsPage,
    M.PURCHASE_NEW: NewPurchasePage,
    M.PURCHASE_RETURNS: PurchaseReturnsPage,
    M.PRODUCTS: ProductsPage,
    M.CUSTOMERS: CustomersPage,
    M.SUPPLIERS: SuppliersPage,
    M.SALES_LIST: SalesListPage,
    M.STOCK_BALANCE: StockBalancePage,
    M.AUDIT_LOGS: AuditLogPage,
    M.LICENSE: LicensePage,
    M.BACKUP: BackupPage,
    M.USERS: UsersPage,
    M.SETTINGS: SettingsPage,
}


def has_page(module_key: str) -> bool:
    return module_key in PAGE_REGISTRY


def build_page(module_key: str, ctx: AppContext):
    return PAGE_REGISTRY[module_key](ctx)
