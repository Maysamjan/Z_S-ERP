# Private-Key Backup Guide (Owner-Only)

The Ed25519 **private signing key** is the single most important secret in the
whole product. Every customer license is signed with it, and the customer app
trusts the matching public key that is embedded in the ERP.

## How it is stored

- Encrypted at rest as `signing_key.enc` (AES-256-GCM; the passphrase is stretched
  with scrypt). On Windows it is additionally wrapped with DPAPI when available.
- The raw key is only ever held in memory while the License Manager is unlocked.
  It is never displayed, copied to the clipboard, or written to logs.

## Backing up

Use **Security & Backup → Backup encrypted private key…** in the License Manager,
or copy `signing_key.enc` from the vendor data directory. The backup is the
**encrypted** envelope — it still requires the passphrase to use.

Recommended:
1. Keep at least two backups of `signing_key.enc` on separate offline media.
2. Store the passphrase separately from the key file (e.g. a password manager).
3. Periodically verify a restore into a scratch key store.

## Restoring

**Security & Backup → Restore**, or `KeyStore.restore_backup(path)`. The passphrase
is still required to unlock the restored key.

## Losing the key

If **both** the key store and every backup are lost, the private key cannot be
recreated. You would have to:
1. generate a **new** key pair,
2. embed the new **public** key in the ERP (`zenith/licensing/keys.py`), and ship
   an app update, and
3. **re-issue every customer's license** with the new key.

All licenses signed with the old key stop validating the moment the embedded public
key changes. There is deliberately **no recovery backdoor** — a recovery mechanism
would weaken the cryptography. Guard the key and its backups accordingly.

## Rotating the passphrase

**Security & Backup → Change key passphrase** re-encrypts the same key under a new
passphrase (the public key and all issued licenses are unaffected).
