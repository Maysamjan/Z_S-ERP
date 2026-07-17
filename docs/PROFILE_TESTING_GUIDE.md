# Profile Testing Guide (Owner/Developer)

The ERP stores exactly **one** installed profile per database. To test all five
profiles on one Windows machine, use **separate, isolated test workspaces** — never
edit a production database's `profile_code`.

## Isolated workspaces via ZENITH_DATA_DIR

The ERP resolves all data (database, config, license, logs, backups) under the
directory named by the `ZENITH_DATA_DIR` environment variable. Give each profile its
own directory:

```
ZenithBusinessERP_Test/
├── GENERAL_STORE/
├── SUPERMARKET/
├── WHOLESALE/
├── PHARMACY/
└── WAREHOUSE/
```

Launch one profile's workspace (Windows example):

```bat
set ZENITH_DATA_DIR=%CD%\ZenithBusinessERP_Test\PHARMACY
ZenithBusinessERP.exe
```

Each workspace runs Setup independently: pick that profile, activate its own `.zlic`
(from the Profile Test Licenses bundle), and use it. One workspace can never modify
another's database.

Production mode uses the normal customer data directory (no `ZENITH_DATA_DIR`
override), so this testing method does not affect real customer installs.

## Generating the five test licenses

In **Zenith License Manager → Profile Test Licenses**, paste the target machine's
fingerprint and generate. You get `Profile-Test-Licenses/{PROFILE}.zlic` — import
each one into the matching workspace.

## Verifying binding

Each license is profile-bound: importing `PHARMACY.zlic` into the `WAREHOUSE`
workspace is rejected with "different business profile". This is asserted in the
test suite (`test_customer_activation_roundtrip`, `test_profile_test_bundle`).

## Cross-platform note

On Linux/macOS the same variable works:

```bash
ZENITH_DATA_DIR=~/ZenithBusinessERP_Test/PHARMACY python -m zenith
```

## Safety

There is **no** in-app test-mode bypass in production builds. The deterministic
fingerprint override (`ZENITH_MACHINE_ID`) is honored only when
`ZENITH_ALLOW_TEST_FINGERPRINT=1` is set, which production builds never set.
