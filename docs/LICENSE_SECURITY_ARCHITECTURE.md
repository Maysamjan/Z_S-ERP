# License Security Architecture

## Key material

| Item | Location | Ships to customer? |
|------|----------|--------------------|
| Ed25519 **public** verification key | `zenith/licensing/keys.py :: EMBEDDED_PUBLIC_KEY_PEM` | ✅ yes (safe) |
| Ed25519 **private** signing key | owner machine only, inside the License Manager key store (`signing_key.enc`, AES-256-GCM encrypted) | ❌ never |

**Audit result (this repo):** the public key is embedded in the customer source;
the private key is **not** committed anywhere (`git grep "BEGIN PRIVATE KEY"` is
empty; `.gitignore` blocks `*_private_key.pem`). The private key held by the owner
**matches** the embedded public key, so the existing pair is preserved — no new
key pair was generated.

## Who can do what

- **Customer ERP** (`zenith/`): can only **verify** licenses (`zenith.licensing.verifier`).
  It has no signing code path at runtime and no private key.
- **Zenith License Manager** (`vendor_tools/license_manager/`, owner-only): holds
  the encrypted private key and can **generate/renew/replace** licenses. It is
  never packaged into customer builds.

## License payload (signed, canonical)

`license_id, customer_name, business_name, profile_code, license_type (DEMO|FULL),
machine_fingerprint, issue_date, start_date, expiry_date (null=perpetual Full),
max_users, max_branches, enabled_modules, license_version`, signed with Ed25519.
Any change to any field invalidates the signature.

## Bindings (no wildcards)

- **Machine**: SHA-256 fingerprint (64 hex). A license only verifies on the machine
  it was issued for.
- **Profile**: the exact profile code. A GENERAL_STORE license never activates
  SUPERMARKET, etc.
- There is **no** machine wildcard and **no** profile wildcard for production
  licenses. The "Profile Test Licenses" feature generates **five separate**
  profile-bound licenses — not one wildcard.

## Test-override lockout (production safety)

`ZENITH_MACHINE_ID` can force a deterministic fingerprint for automated tests, but
it is honored **only** when `ZENITH_ALLOW_TEST_FINGERPRINT=1` is set. Production
builds never set that flag, so the environment variable cannot bypass machine
binding in production (`test_production_ignores_machine_override`).

## Request / license file formats

- `.zreq` (customer → vendor): structured JSON, **no secrets** — full machine
  fingerprint, selected profile, app version, date, request-format version.
- `.zlic` (vendor → customer): the signed license payload + signature.

## Offline revocation honesty

A fully offline customer installation cannot learn about a later **local**
revocation in the owner's records unless a signed revocation list or a replacement
license is delivered to it. The License Manager marks such licenses
`revoked_local` and never claims remote revocation.

## What is NOT implemented (by design)

No hard-coded master key, universal license, signature bypass, keyboard/env bypass
in production, customer-accessible private key, or unsigned/editable licenses.
