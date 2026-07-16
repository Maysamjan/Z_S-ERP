"""The five approved business profiles.

Each profile is pure configuration data. Adding/removing a profile here is the
*only* place profiles are defined -- installer, setup wizard, sidebar, dashboards,
license binding and tests all read from this registry.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from zenith.profiles import modules as M


class ProfileCode(str, enum.Enum):
    GENERAL_STORE = "GENERAL_STORE"
    SUPERMARKET = "SUPERMARKET"
    WHOLESALE = "WHOLESALE"
    PHARMACY = "PHARMACY"
    WAREHOUSE = "WAREHOUSE"


# Product fields available across profiles. Profiles opt into extra fields.
BASE_PRODUCT_FIELDS = [
    "code", "name", "category_id", "unit_id", "barcode",
    "purchase_price", "sale_price", "min_stock", "notes", "is_active",
]


@dataclass(frozen=True)
class ProfileDefinition:
    code: ProfileCode
    name_key: str                 # translation key for display name
    description_key: str          # translation key for one-line description
    icon: str                     # icon resource name
    enabled_modules: list[str]
    features: frozenset[str]      # feature flags (see zenith.profiles.features)
    product_fields: list[str]
    default_units: list[str]      # unit codes seeded for this profile
    dashboard_cards: list[str]    # metric card keys for the dashboard
    highlight_keys: list[str] = field(default_factory=list)  # setup-card bullets

    def has_module(self, key: str) -> bool:
        return key in self.enabled_modules

    def has_feature(self, flag: str) -> bool:
        return flag in self.features


# ---------------------------------------------------------------------------
# Feature flags (imported here to keep a single source of truth)
# ---------------------------------------------------------------------------
from zenith.profiles.features import (  # noqa: E402
    F_POS, F_CASHIER_SHIFTS, F_BATCH_EXPIRY, F_EXPIRY_ALERTS, F_WEIGHT_PRODUCTS,
    F_WHOLESALE_PRICING, F_CUSTOMER_PRICING, F_UNIT_CONVERSION, F_CREDIT_LIMIT,
    F_PHARMACY_FIELDS, F_MULTI_WAREHOUSE, F_STORAGE_BINS, F_THERMAL_RECEIPT,
    F_PROMOTIONS, F_INVENTORY_FIRST,
)


def _general_store() -> ProfileDefinition:
    mods = list(M.CORE_ALWAYS_ON) + [
        M.SALES_NEW, M.SALES_LIST, M.SALES_RETURNS,
        M.PURCHASE_NEW, M.PURCHASE_LIST, M.PURCHASE_RETURNS,
        M.BARCODES,
        M.STOCK_ADJUSTMENT, M.DAMAGED_STOCK,
        M.CUSTOMER_ACCOUNTS, M.SUPPLIER_ACCOUNTS,
        M.RECEIPTS, M.PAYMENTS, M.EXPENSES, M.CASH_ACCOUNTS, M.BANK_ACCOUNTS, M.DAILY_CASH,
    ]
    return ProfileDefinition(
        code=ProfileCode.GENERAL_STORE,
        name_key="profile.general_store.name",
        description_key="profile.general_store.desc",
        icon="profile_general_store",
        enabled_modules=_dedup(mods),
        features=frozenset({F_THERMAL_RECEIPT}),
        product_fields=list(BASE_PRODUCT_FIELDS),
        default_units=["pcs", "box", "kg", "liter"],
        dashboard_cards=["today_sales", "today_profit", "low_stock", "receivables", "cash_on_hand"],
        highlight_keys=[
            "profile.general_store.hl.simple",
            "profile.general_store.hl.barcode",
            "profile.general_store.hl.cash_credit",
            "profile.general_store.hl.thermal",
        ],
    )


def _supermarket() -> ProfileDefinition:
    mods = list(M.CORE_ALWAYS_ON) + [
        M.POS, M.SALES_NEW, M.SALES_LIST, M.SALES_RETURNS,
        M.PURCHASE_NEW, M.PURCHASE_LIST, M.PURCHASE_RETURNS,
        M.BARCODES, M.PRICE_LISTS,
        M.STOCK_ADJUSTMENT, M.DAMAGED_STOCK, M.EXPIRING_STOCK,
        M.CUSTOMER_ACCOUNTS,
        M.RECEIPTS, M.PAYMENTS, M.EXPENSES, M.CASH_ACCOUNTS, M.BANK_ACCOUNTS,
        M.DAILY_CASH, M.CASHIER_SHIFTS,
    ]
    return ProfileDefinition(
        code=ProfileCode.SUPERMARKET,
        name_key="profile.supermarket.name",
        description_key="profile.supermarket.desc",
        icon="profile_supermarket",
        enabled_modules=_dedup(mods),
        features=frozenset({
            F_POS, F_CASHIER_SHIFTS, F_BATCH_EXPIRY, F_EXPIRY_ALERTS,
            F_WEIGHT_PRODUCTS, F_THERMAL_RECEIPT, F_PROMOTIONS,
        }),
        product_fields=BASE_PRODUCT_FIELDS + ["batch_tracked", "is_weighed"],
        default_units=["pcs", "box", "kg", "gram", "liter", "pack"],
        dashboard_cards=["today_sales", "open_shift", "today_profit", "expiring_soon", "low_stock"],
        highlight_keys=[
            "profile.supermarket.hl.pos",
            "profile.supermarket.hl.barcode",
            "profile.supermarket.hl.batch_expiry",
            "profile.supermarket.hl.shifts",
        ],
    )


def _wholesale() -> ProfileDefinition:
    mods = list(M.CORE_ALWAYS_ON) + [
        M.SALES_NEW, M.SALES_LIST, M.SALES_RETURNS,
        M.PURCHASE_NEW, M.PURCHASE_LIST, M.PURCHASE_RETURNS,
        M.BARCODES, M.PRICE_LISTS,
        M.STOCK_ADJUSTMENT, M.DAMAGED_STOCK,
        M.CUSTOMER_ACCOUNTS, M.SUPPLIER_ACCOUNTS,
        M.RECEIPTS, M.PAYMENTS, M.EXPENSES, M.CASH_ACCOUNTS, M.BANK_ACCOUNTS,
        M.ACCOUNT_TRANSFERS, M.DAILY_CASH,
    ]
    return ProfileDefinition(
        code=ProfileCode.WHOLESALE,
        name_key="profile.wholesale.name",
        description_key="profile.wholesale.desc",
        icon="profile_wholesale",
        enabled_modules=_dedup(mods),
        features=frozenset({
            F_WHOLESALE_PRICING, F_CUSTOMER_PRICING, F_UNIT_CONVERSION, F_CREDIT_LIMIT,
        }),
        product_fields=BASE_PRODUCT_FIELDS + ["wholesale_price", "carton_size", "pack_size"],
        default_units=["pcs", "pack", "carton", "kg", "ton"],
        dashboard_cards=["today_sales", "receivables", "overdue", "top_customers", "cash_on_hand"],
        highlight_keys=[
            "profile.wholesale.hl.pricing",
            "profile.wholesale.hl.credit",
            "profile.wholesale.hl.conversion",
            "profile.wholesale.hl.statements",
        ],
    )


def _pharmacy() -> ProfileDefinition:
    mods = list(M.CORE_ALWAYS_ON) + [
        M.SALES_NEW, M.SALES_LIST, M.SALES_RETURNS,
        M.PURCHASE_NEW, M.PURCHASE_LIST, M.PURCHASE_RETURNS,
        M.BARCODES,
        M.STOCK_ADJUSTMENT, M.DAMAGED_STOCK, M.EXPIRING_STOCK,
        M.CUSTOMER_ACCOUNTS, M.SUPPLIER_ACCOUNTS,
        M.RECEIPTS, M.PAYMENTS, M.EXPENSES, M.CASH_ACCOUNTS, M.BANK_ACCOUNTS, M.DAILY_CASH,
    ]
    return ProfileDefinition(
        code=ProfileCode.PHARMACY,
        name_key="profile.pharmacy.name",
        description_key="profile.pharmacy.desc",
        icon="profile_pharmacy",
        enabled_modules=_dedup(mods),
        features=frozenset({
            F_PHARMACY_FIELDS, F_BATCH_EXPIRY, F_EXPIRY_ALERTS, F_THERMAL_RECEIPT,
        }),
        product_fields=BASE_PRODUCT_FIELDS + [
            "generic_name", "trade_name", "manufacturer", "country",
            "dosage_form", "strength", "package_type", "units_per_package",
            "batch_tracked", "wholesale_price",
        ],
        default_units=["tablet", "capsule", "bottle", "box", "strip", "tube", "vial"],
        dashboard_cards=["today_sales", "expiring_soon", "expired_stock", "low_stock", "today_profit"],
        highlight_keys=[
            "profile.pharmacy.hl.generic_trade",
            "profile.pharmacy.hl.manufacturer",
            "profile.pharmacy.hl.batch_expiry",
            "profile.pharmacy.hl.packaging",
        ],
    )


def _warehouse() -> ProfileDefinition:
    mods = list(M.CORE_ALWAYS_ON) + [
        M.WAREHOUSES, M.STOCK_TRANSFER, M.STOCK_ADJUSTMENT, M.STOCK_COUNT,
        M.DAMAGED_STOCK, M.EXPIRING_STOCK,
        # Sales/purchases available but de-prioritised (inventory-first dashboard)
        M.PURCHASE_NEW, M.PURCHASE_LIST,
        M.SALES_NEW, M.SALES_LIST,
        M.SUPPLIER_ACCOUNTS,
        M.EXPENSES,
    ]
    return ProfileDefinition(
        code=ProfileCode.WAREHOUSE,
        name_key="profile.warehouse.name",
        description_key="profile.warehouse.desc",
        icon="profile_warehouse",
        enabled_modules=_dedup(mods),
        features=frozenset({
            F_MULTI_WAREHOUSE, F_STORAGE_BINS, F_INVENTORY_FIRST, F_BATCH_EXPIRY,
        }),
        product_fields=BASE_PRODUCT_FIELDS + ["batch_tracked", "storage_bin"],
        default_units=["pcs", "pallet", "carton", "kg", "ton"],
        dashboard_cards=["total_stock_value", "warehouses", "low_stock", "pending_transfers", "recent_movements"],
        highlight_keys=[
            "profile.warehouse.hl.multi",
            "profile.warehouse.hl.receipt_issue",
            "profile.warehouse.hl.transfer",
            "profile.warehouse.hl.count",
        ],
    )


def _dedup(seq: list[str]) -> list[str]:
    """Preserve order, drop duplicates, and validate against the module catalog."""
    seen: set[str] = set()
    out: list[str] = []
    for k in seq:
        if not M.module_exists(k):
            raise ValueError(f"Unknown module key in profile: {k!r}")
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


PROFILES: dict[ProfileCode, ProfileDefinition] = {
    p.code: p
    for p in [
        _general_store(),
        _supermarket(),
        _wholesale(),
        _pharmacy(),
        _warehouse(),
    ]
}


def get_profile(code: ProfileCode | str) -> ProfileDefinition:
    if isinstance(code, str):
        try:
            code = ProfileCode(code)
        except ValueError as exc:
            raise KeyError(f"Unknown profile code: {code!r}") from exc
    return PROFILES[code]


def all_profiles() -> list[ProfileDefinition]:
    """Registry order = the order shown in the setup wizard."""
    return [
        PROFILES[ProfileCode.GENERAL_STORE],
        PROFILES[ProfileCode.SUPERMARKET],
        PROFILES[ProfileCode.WHOLESALE],
        PROFILES[ProfileCode.PHARMACY],
        PROFILES[ProfileCode.WAREHOUSE],
    ]


def is_valid_profile(code: str) -> bool:
    return code in ProfileCode._value2member_map_
