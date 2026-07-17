# Known Limitations (Honest Status)

This repository is a **working, tested foundation**, not a finished commercial
release. This document states plainly what is and isn't done, so nothing here is
oversold.

## Completion increment (added since the first foundation)

Closed and covered by tests (now 97 total):
- **Safe additive migrations** (`ALTER TABLE ADD COLUMN`) with a pre-migration
  backup — the app no longer relies on `create_all()` alone for upgrades. Startup
  upgrades the schema **before any current-version ORM query runs**, reading only
  the old-compatible `profile_code` via raw SQL; migration failure retains the
  database and backup (never deletes) and shows a clear message. Covered by
  `tests/test_startup_migration.py` for empty/v1/v2/v3/current/missing-version.
- **Global Business Identity**: bilingual name/contact/logo/footer model +
  service + Settings→Business Information tab; used in the shell title & sidebar.
  Logo is validated and copied into a managed folder (survives original deletion).
- **Real weighted-average cost & profit** — the dashboard profit card is no
  longer a fake zero.
- **Duplicate-product prevention** (similar-item check; genuine variants allowed)
  and confirmed **product reuse** (repeated purchases increase the existing
  product's stock via transactions — the Paracetamol workflow test).
- **Pharmacy FEFO** batch suggestion + expired-batch sale blocking.
- **New Purchase** and **New Sale/POS** pages wired with product search and
  inline create-product.
- **Numeric input widgets** (CurrencyInput/QuantityInput) with proper minimum
  widths — fixes the overlapping-spinbox issue — applied to the main forms.
- **Branded printing (first slice)**: sale invoice rendered as A4 / 80mm / 58mm
  with the saved business identity (logo, bilingual name, phone, address,
  tax/registration, footers, terms), full RTL for Persian; print-preview dialog
  with paper switching and verified PDF export, opened from the Sales List
  (double-click or Print Preview). Still pending: A5, purchase documents,
  vouchers, statements, shift reports, and the invoice-settings screen.
- **Sales & purchase returns**: dedicated return documents with atomic stock
  restore, over-return/duplicate-return guards, exact-batch restoration, and
  party-balance reversal; wired Sales/Purchase Returns pages.
- **Finance module**: cash/bank/mobile-money accounts; customer receipts and
  supplier payments with invoice allocation, atomic balance updates, duplicate
  protection and reversal (permission+reason); expenses with approve-posts-to-
  account and net-profit effect; account transfers (atomic, money-conserving);
  branded receipt/payment/expense vouchers with PDF export; wired pages.

## What is real and tested (97 automated tests, all passing)

- Five-profile registry with feature flags; forbidden profiles proven absent.
- Database schema (SQLAlchemy), Argon2id hashing, service-layer permissions.
- Core services: auth (+ rate-limit/lockout), catalog, parties, inventory,
  **atomic** sale/purchase posting, stock transfer, backup/restore, reporting.
  Guards verified: negative-stock, credit-limit, expired-batch, duplicate code.
- **Full license system**: Ed25519 signing, machine binding, profile binding,
  tamper detection, demo/full, perpetual, clock-rollback, transfer request, and a
  vendor License Manager CLI. Verified end-to-end.
- Design system (tokens + light/dark QSS), bilingual i18n (en_US/fa_AF, RTL,
  key-parity asserted).
- Login, setup wizard (with profile↔license enforcement), main shell, and eleven
  data-wired pages: Dashboard, Products (+create), Customers (+create), Suppliers
  (+create), Sales List, Stock Balance, Audit Logs, License, Backup, Users,
  Settings. All build/navigate across five profiles and six resolutions in tests.

## Not yet implemented (deliberately hidden, not faked)

Modules without a finished page are **not shown** in the sidebar (no placeholder
screens). Remaining for a full release:

- **Feature UIs:** Categories/Units/Barcodes/Price-List editors,
  Warehouses/Transfer/Adjustment/Count screens, Damaged/Expiring stock,
  Cashier-shift open/close, Roles editor, Reports screens, batch selection on
  the purchase/sale pages. (Services/back-end for most of these already exist;
  the UI is what remains.) Sales/Purchase **Returns** and the **Finance module**
  (receipts/payments/expenses/accounts/transfers) are done (atomic, guarded, wired).
- **Printing:** A5 paper, purchase documents, payment/expense vouchers,
  statements, shift-closing and expiry reports, and the invoice-settings screen.
  (The branded sale invoice for A4/80mm/58mm with preview + PDF export IS done.)
- **Reporting:** profit uses *current* weighted-average cost, not the historical
  cost at sale time; full report screens (date ranges, export) remain to build.
- **Windows packaging artifacts:** the PyInstaller spec, version metadata, and the
  Inno Setup script are provided and the CI workflow drives them, **but a
  successful Windows build/installer has not yet been produced and verified** in
  this environment (Linux). Do not treat the installer as shipped until CI
  produces the artifacts on a Windows runner.
- **DPAPI / QR / Caps-Lock:** DPAPI wrapping activates only on Windows with
  `pywin32`; the machine-request QR code and a robust Caps-Lock indicator are
  planned.
- **Additional docs:** per-profile user guides, DATABASE.md, RESPONSIVE_UI_GUIDE,
  LOCALIZATION_GUIDE, OFFLINE_ACTIVATION_GUIDE, LICENSE_TRANSFER_GUIDE,
  BACKUP_RESTORE_GUIDE, WINDOWS_TEST_CHECKLIST are outlined in the brief and not
  all written yet.

## Security honesty

The license system uses real asymmetric signatures, machine binding and
tamper-evident local state. It is **strong practical protection**, not
uncrackable — a determined attacker with the binary can attempt to patch
verification. The design keeps the private signing key entirely vendor-side so
attackers cannot forge new valid licenses.
