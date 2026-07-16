# Zenith Business ERP

A small, **offline-first, bilingual (English + Persian/Dari), commercially
sellable** business-management system built on **one shared core with five
business profiles**:

- **General Store** — simple, fast retail
- **Supermarket** — POS, cashier shifts, batch & expiry
- **Wholesale** — tiered pricing, credit, unit conversion
- **Pharmacy** — medicine fields, batch, expiry blocking
- **Warehouse** — multi-warehouse stock control

One codebase → one executable (`ZenithBusinessERP`) → one installer. The active
profile (chosen at first-run setup and bound to a signed license) decides which
modules, menus, dashboards, product fields and reports are enabled.

## Highlights

- **PyQt6 desktop app**, responsive layouts (no absolute positioning), light/dark
  themes from a central design-token system, full RTL for Persian/Dari.
- **Signed licensing** — Ed25519, machine-bound, profile-bound, demo/full,
  clock-rollback detection, offline activation, and a separate **vendor License
  Manager** CLI. The customer app ships only the public key.
- **Secure core** — Argon2id password hashing, service-layer permissions,
  atomic posting (all-or-nothing) for sales/purchases, negative-stock and
  credit-limit guards, append-only audit log.
- **Backup/restore** with verification; customer data survives updates.

## Quick start (development)

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m zenith                                   # launch the app
```

Run the tests (Qt runs headless via the offscreen platform):

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

## Vendor: issuing a license

```bash
# one time: create the signing keypair, embed the printed PUBLIC key in
# zenith/licensing/keys.py; keep the PRIVATE key secret and never ship it.
python -m zenith.vendor.license_manager_cli init-keys --out ./vendor_keys

# issue a machine-bound, profile-bound license from a customer's request code
export ZENITH_LICENSE_PRIVATE_KEY=./vendor_keys/vendor_private_key.pem
python -m zenith.vendor.license_manager_cli issue \
  --profile SUPERMARKET --type DEMO --days 30 \
  --customer "Ali Ahmadi" --business "Kabul Mart" \
  --machine <fingerprint-from-request-code> --out kabulmart.zlic
```

## Documentation

- [`docs/SMALL_ERP_REDESIGN_AUDIT.md`](docs/SMALL_ERP_REDESIGN_AUDIT.md) — audit & plan
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/BUSINESS_PROFILES.md`](docs/BUSINESS_PROFILES.md)
- [`docs/LICENSING_ARCHITECTURE.md`](docs/LICENSING_ARCHITECTURE.md)
- [`docs/UI_DESIGN_SYSTEM.md`](docs/UI_DESIGN_SYSTEM.md)
- [`docs/BUILD_RELEASE_GUIDE.md`](docs/BUILD_RELEASE_GUIDE.md)
- [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) — honest status of what remains

## Project status

This repository is a **working, tested foundation**, not yet a finished
commercial release. The shared core, the complete license system, the profile
architecture, the design/i18n systems and eleven data-wired pages are real and
covered by 54 automated tests. Remaining work (additional feature UIs, print
templates, produced Windows installer artifacts) is tracked transparently in
`docs/KNOWN_LIMITATIONS.md`.
