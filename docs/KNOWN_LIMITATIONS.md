# Known Limitations (Honest Status)

This repository is a **working, tested foundation**, not a finished commercial
release. This document states plainly what is and isn't done, so nothing here is
oversold.

## What is real and tested (54 automated tests, all passing)

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

- **Feature UIs:** New Sale/POS screen, Sales/Purchase Returns, New Purchase form,
  Categories/Units/Barcodes/Price-List editors, Warehouses/Transfer/Adjustment/
  Count screens, Damaged/Expiring stock, Receipts/Payments/Expenses/Accounts,
  Cashier-shift open/close, Roles editor, Reports screens. (Services/back-end for
  most of these already exist; the UI is what remains.)
- **Printing:** A4/A5 invoices, 58/80mm receipts, statements, vouchers, shift
  closing, expiry reports. (Not implemented.)
- **Reporting:** profit (gross/net) requires a COGS ledger; the dashboard
  "profit" card is currently a placeholder value of 0 and is documented as such
  in `zenith/services/reporting.py`.
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
