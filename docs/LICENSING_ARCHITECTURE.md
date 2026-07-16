# Licensing Architecture

Every installation requires a valid, **digitally signed** license that is bound to
one **business profile**, one **customer/business**, and one **computer**.

## Trust model

- **Ed25519** asymmetric signatures. The customer application contains **only the
  public verification key** (`zenith/licensing/keys.py :: EMBEDDED_PUBLIC_KEY_PEM`).
- The **private signing key never ships** to customers — not in source, the
  executable, the installer, config, or the database. It lives only in the vendor
  environment and is loaded by the vendor tool from `ZENITH_LICENSE_PRIVATE_KEY`.
- `.gitignore` blocks `*_private_key.pem` and similar from ever being committed.

## License payload (signed)

`zenith/licensing/model.py :: License`

```
license_id, customer_name, business_name, profile_code, license_type (DEMO|FULL),
machine_fingerprint, issue_date, start_date, expiry_date (null = perpetual Full),
max_users, max_branches, enabled_modules, license_version, signature
```

The signed bytes are a **canonical** JSON encoding (sorted keys, no whitespace),
so signing and verification always reproduce identical bytes. Any modification to
any field invalidates the signature.

## Machine binding

`zenith/licensing/machine.py` builds a fingerprint from several stable system
values — on Windows: registry `MachineGuid` + baseboard/BIOS/disk serials; other
platforms fall back to `machine-id`/MAC/platform. Only the **SHA-256 hash** is
used or stored (privacy-conscious; raw identifiers are discarded). A `request_code`
is a human-friendly, grouped form the customer sends to the vendor.

Copying the setup file / app folder / license file / database / activation state
to another computer fails: the fingerprint no longer matches
(`license.error.machine`).

## Profile binding

The installer/setup-selected profile must equal the license `profile_code`. A
`WHOLESALE` license cannot activate a `SUPERMARKET` profile, etc. The setup wizard
refuses to finish on a mismatch and shows a translated message
(`license.error.profile`).

## Verification (`verifier.py`, pure & testable)

Order: signature → profile validity → machine → profile-match → edition → dates
→ limits. `today` and `machine_fp` are injected for deterministic tests.

## Activation state (`storage.py`)

Persisted locally, **HMAC-bound to the machine fingerprint** (tamper-evident +
machine-bound) and DPAPI-wrapped on Windows when available. Tracks the imported
license, `activated_at`, `last_seen_date` (clock-rollback detection) and an
activation/transfer history. State copied to another machine is rejected by the
HMAC check.

## Demo vs Full

- **Demo:** always time-limited + machine + profile specific. Reinstalling on the
  same machine does not restart the demo (state is machine-bound). After expiry the
  app is **read-only** — customer data is never destroyed.
- **Full:** perpetual or subscription; same machine/profile binding; a Full key
  will not activate a second computer.

## Clock-rollback

If the system date is earlier than the stored `last_seen_date`, the app enters a
read-only `CLOCK_ROLLBACK` state and records an audit event until the date is
corrected.

## Offline activation flow

1. Customer installs and selects a profile.
2. App shows a **machine request code** (copy button; QR planned).
3. Customer sends it to the vendor.
4. Vendor uses **ZenithLicenseManager** (`zenith.vendor.license_manager_cli`) to
   issue a signed activation key / `.zlic` file for the matching profile.
5. Customer imports the key or file; the app verifies signature + machine +
   profile + dates + limits and activates only if every check passes.

## Transfer / rehost

`LicenseService.begin_transfer()` records a transfer request and returns the new
machine's request code; the vendor then issues a fresh machine-bound license.
There is deliberately **no customer-side button that mints unlimited machine
licenses**.
