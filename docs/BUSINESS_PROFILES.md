# Business Profiles

Five profiles share one core. Each is defined once in
`zenith/profiles/registry.py` as data (enabled modules, feature flags, product
fields, default units, dashboard cards). Adding/removing capability is a data
change, not a code fork.

## General Store (`GENERAL_STORE`)
Simple, fast retail. Products, categories, barcodes, cash & credit sales,
customers/suppliers, inventory, expenses, payments, thermal receipt + A4 invoice.

## Supermarket (`SUPERMARKET`)
Adds fast **POS**, **cashier shifts** (open/close cash reconciliation), **batch
numbers + expiration** with alerts, weighed products, promotions.
Feature flags: `pos`, `cashier_shifts`, `batch_expiry`, `expiry_alerts`,
`weight_products`, `thermal_receipt`, `promotions`.

## Wholesale (`WHOLESALE`)
Adds **retail + wholesale + customer-specific pricing**, **unit conversion**
(carton/pack/piece), **credit limits** and credit sales, customer statements.
Feature flags: `wholesale_pricing`, `customer_pricing`, `unit_conversion`,
`credit_limit`.

## Pharmacy (`PHARMACY`)
Commercial medicine inventory & sales (no diagnosis/patient records). Adds
generic/trade name, manufacturer, country, dosage form, strength, package type,
units per package, **batch + manufacturing/expiry dates**, and **expired-sale
blocking**. Feature flags: `pharmacy_fields`, `batch_expiry`, `expiry_alerts`.

## Warehouse (`WAREHOUSE`)
Inventory-first. Adds **multiple warehouses**, storage bins, stock receipt/issue,
**transfer**, adjustment, stock count, movement history, stock valuation.
Sales/purchases remain available but the dashboard and menus prioritise
inventory. Feature flags: `multi_warehouse`, `storage_bins`, `inventory_first`,
`batch_expiry`.

## License binding

The chosen profile is validated against the license at setup and enforced at
startup. A key issued for one profile never activates another — see
[`LICENSING_ARCHITECTURE.md`](LICENSING_ARCHITECTURE.md).
