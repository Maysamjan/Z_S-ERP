"""Canonical catalogue of application modules.

A *module* is a navigable feature area. Profiles enable a subset of these. The UI
sidebar, permissions and license "enabled_modules" all reference these stable keys.
Only modules relevant to the five approved profiles exist here -- there are no
restaurant / education / repair / manufacturing modules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDef:
    key: str
    group: str          # sidebar group
    title_key: str      # translation key
    icon: str           # icon resource name (without extension)


# --- Module keys (stable identifiers) --------------------------------------
DASHBOARD = "dashboard"

SALES_NEW = "sales.new"
SALES_LIST = "sales.list"
SALES_RETURNS = "sales.returns"
POS = "sales.pos"

PURCHASE_NEW = "purchases.new"
PURCHASE_LIST = "purchases.list"
PURCHASE_RETURNS = "purchases.returns"

PRODUCTS = "products.products"
CATEGORIES = "products.categories"
UNITS = "products.units"
BARCODES = "products.barcodes"
PRICE_LISTS = "products.price_lists"

STOCK_BALANCE = "inventory.balance"
STOCK_MOVEMENTS = "inventory.movements"
WAREHOUSES = "inventory.warehouses"
STOCK_TRANSFER = "inventory.transfer"
STOCK_ADJUSTMENT = "inventory.adjustment"
DAMAGED_STOCK = "inventory.damaged"
EXPIRING_STOCK = "inventory.expiring"
STOCK_COUNT = "inventory.count"

CUSTOMERS = "parties.customers"
SUPPLIERS = "parties.suppliers"
CUSTOMER_ACCOUNTS = "parties.customer_accounts"
SUPPLIER_ACCOUNTS = "parties.supplier_accounts"

RECEIPTS = "finance.receipts"
PAYMENTS = "finance.payments"
EXPENSES = "finance.expenses"
CASH_ACCOUNTS = "finance.cash_accounts"
BANK_ACCOUNTS = "finance.bank_accounts"
ACCOUNT_TRANSFERS = "finance.transfers"
DAILY_CASH = "finance.daily_cash"
CASHIER_SHIFTS = "finance.cashier_shifts"

REPORTS = "reports"

USERS = "admin.users"
ROLES = "admin.roles"
AUDIT_LOGS = "admin.audit"
BACKUP = "admin.backup"
LICENSE = "admin.license"
SETTINGS = "admin.settings"


# group keys
G_MAIN = "group.main"
G_SALES = "group.sales"
G_PURCHASES = "group.purchases"
G_PRODUCTS = "group.products"
G_INVENTORY = "group.inventory"
G_PARTIES = "group.parties"
G_FINANCE = "group.finance"
G_REPORTS = "group.reports"
G_ADMIN = "group.admin"


MODULE_CATALOG: dict[str, ModuleDef] = {
    m.key: m
    for m in [
        ModuleDef(DASHBOARD, G_MAIN, "module.dashboard", "dashboard"),

        ModuleDef(SALES_NEW, G_SALES, "module.sales_new", "sale"),
        ModuleDef(POS, G_SALES, "module.pos", "pos"),
        ModuleDef(SALES_LIST, G_SALES, "module.sales_list", "list"),
        ModuleDef(SALES_RETURNS, G_SALES, "module.sales_returns", "return"),

        ModuleDef(PURCHASE_NEW, G_PURCHASES, "module.purchase_new", "purchase"),
        ModuleDef(PURCHASE_LIST, G_PURCHASES, "module.purchase_list", "list"),
        ModuleDef(PURCHASE_RETURNS, G_PURCHASES, "module.purchase_returns", "return"),

        ModuleDef(PRODUCTS, G_PRODUCTS, "module.products", "product"),
        ModuleDef(CATEGORIES, G_PRODUCTS, "module.categories", "category"),
        ModuleDef(UNITS, G_PRODUCTS, "module.units", "unit"),
        ModuleDef(BARCODES, G_PRODUCTS, "module.barcodes", "barcode"),
        ModuleDef(PRICE_LISTS, G_PRODUCTS, "module.price_lists", "price"),

        ModuleDef(STOCK_BALANCE, G_INVENTORY, "module.stock_balance", "stock"),
        ModuleDef(STOCK_MOVEMENTS, G_INVENTORY, "module.stock_movements", "movement"),
        ModuleDef(WAREHOUSES, G_INVENTORY, "module.warehouses", "warehouse"),
        ModuleDef(STOCK_TRANSFER, G_INVENTORY, "module.stock_transfer", "transfer"),
        ModuleDef(STOCK_ADJUSTMENT, G_INVENTORY, "module.stock_adjustment", "adjust"),
        ModuleDef(DAMAGED_STOCK, G_INVENTORY, "module.damaged_stock", "damaged"),
        ModuleDef(EXPIRING_STOCK, G_INVENTORY, "module.expiring_stock", "expiry"),
        ModuleDef(STOCK_COUNT, G_INVENTORY, "module.stock_count", "count"),

        ModuleDef(CUSTOMERS, G_PARTIES, "module.customers", "customer"),
        ModuleDef(SUPPLIERS, G_PARTIES, "module.suppliers", "supplier"),
        ModuleDef(CUSTOMER_ACCOUNTS, G_PARTIES, "module.customer_accounts", "account"),
        ModuleDef(SUPPLIER_ACCOUNTS, G_PARTIES, "module.supplier_accounts", "account"),

        ModuleDef(RECEIPTS, G_FINANCE, "module.receipts", "receipt"),
        ModuleDef(PAYMENTS, G_FINANCE, "module.payments", "payment"),
        ModuleDef(EXPENSES, G_FINANCE, "module.expenses", "expense"),
        ModuleDef(CASH_ACCOUNTS, G_FINANCE, "module.cash_accounts", "cash"),
        ModuleDef(BANK_ACCOUNTS, G_FINANCE, "module.bank_accounts", "bank"),
        ModuleDef(ACCOUNT_TRANSFERS, G_FINANCE, "module.account_transfers", "transfer"),
        ModuleDef(DAILY_CASH, G_FINANCE, "module.daily_cash", "cash"),
        ModuleDef(CASHIER_SHIFTS, G_FINANCE, "module.cashier_shifts", "shift"),

        ModuleDef(REPORTS, G_REPORTS, "module.reports", "report"),

        ModuleDef(USERS, G_ADMIN, "module.users", "users"),
        ModuleDef(ROLES, G_ADMIN, "module.roles", "roles"),
        ModuleDef(AUDIT_LOGS, G_ADMIN, "module.audit_logs", "audit"),
        ModuleDef(BACKUP, G_ADMIN, "module.backup", "backup"),
        ModuleDef(LICENSE, G_ADMIN, "module.license", "license"),
        ModuleDef(SETTINGS, G_ADMIN, "module.settings", "settings"),
    ]
}


def module_exists(key: str) -> bool:
    return key in MODULE_CATALOG


# Modules that every profile always includes (the shared administrative spine).
CORE_ALWAYS_ON = [
    DASHBOARD,
    PRODUCTS, CATEGORIES, UNITS,
    CUSTOMERS, SUPPLIERS,
    STOCK_BALANCE, STOCK_MOVEMENTS,
    REPORTS,
    USERS, ROLES, AUDIT_LOGS, BACKUP, LICENSE, SETTINGS,
]
