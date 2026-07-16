# Small ERP Redesign — Repository Audit

_Date: 2026-07-16 · Branch: `claude/zenith-erp-scope-reduction-lxjtoi`_

## 1. Audit finding: the repository was empty

The redesign brief describes reducing an existing 31-profile ERP down to five
profiles. On inspection the remote repository (`Maysamjan/Z_S-ERP`) contained
**no branches, no commits and no source files** — only an initialized `.git`.

There was therefore no 31-profile codebase to "reduce". The honest and useful
interpretation of the brief is: **build the small, five-profile product directly,
scoped from the start to the approved profiles**, applying every scope-reduction
rule as a design constraint rather than a deletion exercise.

Nothing was removed because nothing existed; instead the product was **built
scoped**. The unrelated profiles (restaurant, hotel, mobile/computer repair,
schools, manufacturing, etc.) are simply never introduced — see the profile
registry (`zenith/profiles/registry.py`) which admits exactly five codes and the
test `tests/test_profiles.py::test_forbidden_profiles_absent` which asserts the
rest are invalid.

## 2. Final scope (five profiles only)

| Code | Profile | Emphasis |
|------|---------|----------|
| `GENERAL_STORE` | General Store | Simple, fast retail |
| `SUPERMARKET` | Supermarket | POS, cashier shifts, batch/expiry |
| `WHOLESALE` | Wholesale | Tiered pricing, credit, unit conversion |
| `PHARMACY` | Pharmacy | Medicine fields, batch, expiry blocking |
| `WAREHOUSE` | Warehouse | Multi-warehouse stock control |

Profiles are **pure configuration**. The active profile determines enabled
modules, dashboard cards, product fields, default units, and license binding —
never customer-specific `if name == ...` branching.

## 3. What is preserved / built / (not) removed

- **Preserved / shared core:** authentication, users & roles, products,
  categories, units, customers, suppliers, purchases, sales, inventory,
  warehouses, payments, expenses, accounts, reporting, backup, licensing,
  settings — one schema, one codebase, one executable.
- **Built to real completeness this iteration:** profile registry, database
  schema, security (Argon2 + permissions), the full **license system**
  (Ed25519 signing, machine + profile binding, demo/full, clock-rollback,
  vendor tool), core services (auth, catalog, parties, inventory, sales,
  purchases, backup, reporting) with transaction safety, the design system
  (tokens + light/dark QSS), i18n (en_US / fa_AF, RTL), login, setup wizard,
  main shell, and eleven data-wired feature pages.
- **Not present (correctly excluded):** every unrelated profile/module named in
  the brief. They are absent from the registry, sidebar, license, tests and docs.

## 4. Database migration risks

- The schema is new, so there is no destructive migration this iteration; the
  first run creates the schema and seeds the chosen profile.
- A `schema_version` table + a **verified backup before any future destructive
  migration** are in place (`zenith/services/backup.py`). Customer data lives
  under `%PROGRAMDATA%\ZenithBusinessERP` so it is never deleted on
  update/uninstall.
- Money is `Numeric(18,4)` (never float); unique constraints exist on product
  code/barcode, document numbers, batch (product+number), and stock slots.

## 5. UI / responsive / translation / licensing review

- **UI design problems addressed:** a single design-token system generates the
  whole stylesheet; no per-screen ad-hoc QSS; consistent page scaffold
  (header + scrollable content + empty/loading states).
- **Responsive:** only Qt layouts + size policies are used (no absolute
  positioning). The shell auto-collapses the sidebar below 1100px, the dashboard
  reflows its card grid, long content scrolls, and tables scroll horizontally.
  Verified at 1024×768 → 1920×1080 in `tests/test_gui.py`.
- **Translation:** every visible string is a translation key; en_US and fa_AF
  are key-for-key complete (asserted in tests); RTL is applied app-wide for
  Persian/Dari.
- **Licensing:** signature/machine/profile/date/limit checks are enforced in a
  pure verifier and the service layer; the setup wizard blocks finishing on a
  profile↔license mismatch; the app ships only the public key.

## 6. Implementation plan (this iteration → next)

Delivered: Phases 1–8 of the brief in foundational form (scope, design system,
login/wizard/shell, core CRUD + posting, per-profile config, backup/audit,
full licensing, and automated responsive/localization/licensing/service tests).

Remaining for a full commercial release is tracked honestly in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — chiefly: returns/POS/expense
UIs, printing templates, profit (COGS) reporting, produced Windows installer
artifacts, and the additional per-profile guide docs. No placeholder screens
were shipped: a module without a finished page is simply not offered in the
sidebar yet (`zenith/ui/pages/registry.py`).
