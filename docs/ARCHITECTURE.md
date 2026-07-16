# Architecture

One codebase, one executable, one shared core, five profiles.

```
zenith/
├── core/          paths, config, exceptions            (shared)
├── profiles/      the five-profile registry, modules, feature flags
├── db/            SQLAlchemy engine, session, models, migrations
├── security/      Argon2 password hashing, permission keys/roles
├── services/      business rules, permissions, transaction safety
├── licensing/     Ed25519 signing/verify, machine binding, activation
├── vendor/        VENDOR ONLY: license issuer + CLI (never shipped to customers)
└── ui/            PyQt6: design system, i18n, widgets, screens, pages
```

## Layering

```
UI (PyQt6)  ──►  Services  ──►  DB models (SQLAlchemy)
   │               │
   │               └─ permissions_util, audit, numbering, inventory
   └─ context (db, session, profile, license, i18n, theme)
```

- **Services never trust the UI.** Permissions are enforced in services
  (`permissions_util.require`), invariants (negative stock, credit limit,
  expired stock, duplicate documents) are enforced in services, and multi-row
  postings run inside one transaction via `session_scope` (commit on success,
  rollback on any exception).
- **Profiles are data.** `ProfileDefinition` lists enabled modules, feature
  flags, product fields, default units and dashboard cards. Code checks
  `profile.has_feature(flag)` / `profile.has_module(key)` — never the profile
  name.
- **No placeholder pages.** The sidebar shows the intersection of the profile's
  enabled modules and the *registered* pages (`ui/pages/registry.py`). A module
  without a finished page is simply not offered.

## Data & money

- SQLite single-file database under `%PROGRAMDATA%\ZenithBusinessERP` (offline).
- Money and quantities are `Numeric(18,4)` — never floats.
- Foreign keys enforced (`PRAGMA foreign_keys=ON`); unique constraints on
  product code/barcode, document numbers, batch (product+number) and stock slots;
  indexes on hot lookup columns.
- Soft-delete on catalog/party rows; audit log is append-only.

## Transaction safety

`session_scope()` wraps a unit of work. Sale/purchase **approval** is the single
atomic posting step: stock movements, balance updates and party-balance changes
either all commit or all roll back. This is exercised directly in
`tests/test_services.py` (insufficient-stock and credit-limit paths verify no
partial writes remain).
