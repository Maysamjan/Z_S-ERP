"""Feature flags.

Feature flags gate behaviour that is more granular than a whole module -- e.g.
wholesale pricing columns, batch/expiry fields, POS cashier-shift enforcement.
Services and widgets check ``profile.has_feature(flag)`` instead of branching on
the profile code, so behaviour stays data-driven.
"""

F_POS = "pos"                          # dedicated fast POS screen
F_CASHIER_SHIFTS = "cashier_shifts"    # enforce open shift before POS sale
F_BATCH_EXPIRY = "batch_expiry"        # products carry batch number + expiry
F_EXPIRY_ALERTS = "expiry_alerts"      # near-expiry / expired reporting + warnings
F_WEIGHT_PRODUCTS = "weight_products"  # weighed (scale) products
F_WHOLESALE_PRICING = "wholesale_pricing"   # retail + wholesale price columns
F_CUSTOMER_PRICING = "customer_pricing"     # per-customer price lists
F_UNIT_CONVERSION = "unit_conversion"       # carton/pack/piece conversions
F_CREDIT_LIMIT = "credit_limit"             # enforce customer credit limits
F_PHARMACY_FIELDS = "pharmacy_fields"       # generic/trade/manufacturer etc.
F_MULTI_WAREHOUSE = "multi_warehouse"       # many warehouses + transfers
F_STORAGE_BINS = "storage_bins"             # bin locations inside a warehouse
F_THERMAL_RECEIPT = "thermal_receipt"       # 58/80mm receipt printing
F_PROMOTIONS = "promotions"                 # promotional discounts
F_INVENTORY_FIRST = "inventory_first"       # inventory-first dashboard/menus

ALL_FEATURES = frozenset({
    F_POS, F_CASHIER_SHIFTS, F_BATCH_EXPIRY, F_EXPIRY_ALERTS, F_WEIGHT_PRODUCTS,
    F_WHOLESALE_PRICING, F_CUSTOMER_PRICING, F_UNIT_CONVERSION, F_CREDIT_LIMIT,
    F_PHARMACY_FIELDS, F_MULTI_WAREHOUSE, F_STORAGE_BINS, F_THERMAL_RECEIPT,
    F_PROMOTIONS, F_INVENTORY_FIRST,
})
