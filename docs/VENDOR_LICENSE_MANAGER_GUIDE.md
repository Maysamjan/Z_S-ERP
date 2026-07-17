# Zenith License Manager — Owner Guide

**Owner-only.** This tool holds the private signing key. Never send it, its source,
its data directory, or its key store to a customer.

## Open the License Manager

```bash
python -m vendor_tools.license_manager.run
```
(or run the built `ZenithLicenseManager.exe`).

**First run:** create the owner account, choose a signing-key passphrase, and point
it at the private-key PEM to initialize the encrypted key store. After that, sign
in with the owner password + key passphrase.

## Import a request

Customer sends a `.zreq` file (or request code). In **Generate License**:
- **Open .zreq file…** or **Paste request code** — this auto-fills the full machine
  fingerprint and the requested profile. The fingerprint length/validity is shown.

## Generate a Demo

1. Fill customer/business info.
2. Confirm the fingerprint (64 hex) and profile.
3. License type **Demo**, pick a duration preset (7/15/30/60/90) or type days.
4. Set max users / branches.
5. **Generate License** → the activation key (`ZBE1…`) appears and is *immediately
   self-verified* with the customer's exact verifier. The verification panel shows
   signature/machine/profile/type/dates/limits.
6. **Save License File (.zlic)** (or Copy Activation Key) and send it to the customer.

## Generate a Full license

Choose **Full**, then **Subscription** (set duration) or **Perpetual** (no expiry).
Everything else is the same.

## Renew a license

**License History** → select a license → **Renew**. Creates a **new** signed
license (new License ID, `renewed_from` link). Machine and profile stay the same.
You may change expiry, type, limits and modules.

## Replace a license (machine change / wrong profile)

**License History** → select → **Replace** → enter a **reason**. Creates a new
signed license (`replaced_from` link) and marks the old one **replaced**. Use this
when the machine fingerprint or profile must change.

## Generate five test-profile licenses

**Profile Test Licenses** tab → paste one machine fingerprint, set demo duration →
**Generate**. Exports `Profile-Test-Licenses/{PROFILE}.zlic` + `SUMMARY.txt`. Each
is a separate profile-bound license (no wildcard).

## Back up the encrypted private key

**Security & Backup** → **Backup encrypted private key…** copies the AES-GCM
encrypted key store (never plaintext). Also **Backup vendor data…** for the full
history DB + public key + encrypted key.

See `PRIVATE_KEY_BACKUP_GUIDE.md`.

## What must NEVER be sent to customers

- The private key or its encrypted key store (`signing_key.enc`).
- The `vendor_tools/` source or the `ZenithLicenseManager` build.
- The vendor history database.

Customers only receive: the ERP app (public key only), and per-customer `.zlic`
license files.
