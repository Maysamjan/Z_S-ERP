"""Permission keys and default role templates.

Permissions are enforced at the service layer (authoritative) and mirrored in the
UI (to hide controls). A role stores a JSON list of these keys.
"""

from __future__ import annotations

import enum


class Permission(str, enum.Enum):
    # sales
    SALE_VIEW = "sale.view"
    SALE_CREATE = "sale.create"
    SALE_APPROVE = "sale.approve"
    SALE_RETURN = "sale.return"
    # purchases
    PURCHASE_VIEW = "purchase.view"
    PURCHASE_CREATE = "purchase.create"
    PURCHASE_APPROVE = "purchase.approve"
    PURCHASE_RETURN = "purchase.return"
    # products
    PRODUCT_VIEW = "product.view"
    PRODUCT_MANAGE = "product.manage"
    PRICE_CHANGE = "product.price_change"
    # parties
    PARTY_VIEW = "party.view"
    PARTY_MANAGE = "party.manage"
    # inventory
    STOCK_VIEW = "stock.view"
    STOCK_ADJUST = "stock.adjust"
    STOCK_TRANSFER = "stock.transfer"
    STOCK_COUNT = "stock.count"
    # finance
    FINANCE_VIEW = "finance.view"
    PAYMENT_MANAGE = "finance.payment"
    EXPENSE_MANAGE = "finance.expense"
    # reports
    REPORT_VIEW = "report.view"
    REPORT_EXPORT = "report.export"
    # admin
    USER_MANAGE = "admin.user"
    ROLE_MANAGE = "admin.role"
    AUDIT_VIEW = "admin.audit"
    BACKUP_MANAGE = "admin.backup"
    LICENSE_MANAGE = "admin.license"
    SETTINGS_MANAGE = "admin.settings"


ALL_PERMISSIONS = [p.value for p in Permission]


ROLE_TEMPLATES: dict[str, list[str]] = {
    "Administrator": ALL_PERMISSIONS,
    "Manager": [
        Permission.SALE_VIEW.value, Permission.SALE_CREATE.value, Permission.SALE_APPROVE.value,
        Permission.SALE_RETURN.value, Permission.PURCHASE_VIEW.value, Permission.PURCHASE_CREATE.value,
        Permission.PURCHASE_APPROVE.value, Permission.PURCHASE_RETURN.value, Permission.PRODUCT_VIEW.value,
        Permission.PRODUCT_MANAGE.value, Permission.PRICE_CHANGE.value, Permission.PARTY_VIEW.value,
        Permission.PARTY_MANAGE.value, Permission.STOCK_VIEW.value, Permission.STOCK_ADJUST.value,
        Permission.STOCK_TRANSFER.value, Permission.STOCK_COUNT.value, Permission.FINANCE_VIEW.value,
        Permission.PAYMENT_MANAGE.value, Permission.EXPENSE_MANAGE.value, Permission.REPORT_VIEW.value,
        Permission.REPORT_EXPORT.value,
    ],
    "Cashier": [
        Permission.SALE_VIEW.value, Permission.SALE_CREATE.value, Permission.PRODUCT_VIEW.value,
        Permission.PARTY_VIEW.value, Permission.STOCK_VIEW.value, Permission.PAYMENT_MANAGE.value,
    ],
    "Storekeeper": [
        Permission.PRODUCT_VIEW.value, Permission.STOCK_VIEW.value, Permission.STOCK_ADJUST.value,
        Permission.STOCK_TRANSFER.value, Permission.STOCK_COUNT.value, Permission.PURCHASE_VIEW.value,
        Permission.REPORT_VIEW.value,
    ],
}
