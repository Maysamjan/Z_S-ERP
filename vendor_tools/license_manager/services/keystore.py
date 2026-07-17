"""Encrypted private-key store (owner machine only).

The Ed25519 signing key is stored **encrypted at rest**: the passphrase is
stretched with scrypt and the PEM is sealed with AES-256-GCM (authenticated, so
tampering is detected). On Windows the sealed blob is additionally wrapped with
DPAPI when available (defence in depth, tied to the owner's Windows account).

Security rules enforced here:
* the raw private key never leaves this module except as a live key object for
  signing -- it is never returned as text, logged, or written unencrypted;
* backups copy only the **encrypted** file, never plaintext;
* the public key is stored alongside (public is safe) for quick verification.

Losing both the key and its encrypted backup is unrecoverable -- a new key pair
would require re-embedding a new public key in the customer app, invalidating all
previously issued licenses. This is documented in PRIVATE_KEY_BACKUP_GUIDE.md.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32
ENVELOPE_VERSION = 1


class KeyStoreError(Exception):
    pass


class BadPassphrase(KeyStoreError):
    pass


def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(passphrase.encode("utf-8"))


def _dpapi_protect(data: bytes) -> bytes:  # pragma: no cover - Windows only
    try:
        import win32crypt  # type: ignore
        return b"DPAPI1" + win32crypt.CryptProtectData(data, "ZenithSigningKey", None, None, None, 0)
    except Exception:
        return data


def _dpapi_unprotect(data: bytes) -> bytes:  # pragma: no cover - Windows only
    if data.startswith(b"DPAPI1"):
        try:
            import win32crypt  # type: ignore
            _, out = win32crypt.CryptUnprotectData(data[6:], None, None, None, 0)
            return out
        except Exception:
            return data
    return data


@dataclass
class KeyStore:
    path: Path

    # -- state ------------------------------------------------------------
    def is_initialized(self) -> bool:
        return Path(self.path).exists()

    # -- create -----------------------------------------------------------
    def initialize(self, private_pem: bytes, passphrase: str, *, overwrite: bool = False) -> None:
        if self.is_initialized() and not overwrite:
            raise KeyStoreError("Key store already initialized")
        if not passphrase or len(passphrase) < 8:
            raise KeyStoreError("Passphrase must be at least 8 characters")
        priv = serialization.load_pem_private_key(private_pem, password=None)
        if not isinstance(priv, Ed25519PrivateKey):
            raise KeyStoreError("Not an Ed25519 private key")
        pub_pem = priv.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = _derive(passphrase, salt)
        ct = AESGCM(key).encrypt(nonce, private_pem, None)
        envelope = json.dumps({
            "format": "zenith-keystore", "version": ENVELOPE_VERSION,
            "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ct).decode(),
            "public_key": pub_pem.decode(),
        }).encode("utf-8")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.path).write_bytes(_dpapi_protect(envelope))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # -- read -------------------------------------------------------------
    def _envelope(self) -> dict:
        if not self.is_initialized():
            raise KeyStoreError("Key store not initialized")
        raw = _dpapi_unprotect(Path(self.path).read_bytes())
        return json.loads(raw.decode("utf-8"))

    def public_key_pem(self) -> bytes:
        return self._envelope()["public_key"].encode("utf-8")

    def load_private_key(self, passphrase: str) -> Ed25519PrivateKey:
        env = self._envelope()
        salt = base64.b64decode(env["salt"])
        nonce = base64.b64decode(env["nonce"])
        ct = base64.b64decode(env["ciphertext"])
        key = _derive(passphrase, salt)
        try:
            pem = AESGCM(key).decrypt(nonce, ct, None)
        except Exception as exc:  # authentication failure => wrong passphrase / tampered
            raise BadPassphrase("Incorrect passphrase or corrupted key store") from exc
        priv = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(priv, Ed25519PrivateKey):
            raise KeyStoreError("Stored key is not an Ed25519 private key")
        return priv

    def verify_passphrase(self, passphrase: str) -> bool:
        try:
            self.load_private_key(passphrase)
            return True
        except BadPassphrase:
            return False

    # -- change passphrase ------------------------------------------------
    def change_passphrase(self, old: str, new: str) -> None:
        priv = self.load_private_key(old)  # authenticates old passphrase
        pem = priv.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.initialize(pem, new, overwrite=True)

    # -- backup / restore (encrypted only) --------------------------------
    def export_backup(self, dest: str | Path) -> Path:
        if not self.is_initialized():
            raise KeyStoreError("Nothing to back up")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, dest)  # copies the ENCRYPTED envelope only
        return dest

    def restore_backup(self, src: str | Path) -> None:
        src = Path(src)
        # validate it is a real key store before overwriting
        probe = KeyStore(src)
        probe._envelope()  # raises if not a valid envelope
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, self.path)

    # -- helpers ----------------------------------------------------------
    def matches_public_key(self, expected_public_pem: bytes) -> bool:
        try:
            stored = serialization.load_pem_public_key(self.public_key_pem())
            expected = serialization.load_pem_public_key(expected_public_pem)
        except Exception:
            return False
        if not isinstance(stored, Ed25519PublicKey) or not isinstance(expected, Ed25519PublicKey):
            return False
        raw = lambda k: k.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)  # noqa: E731
        return raw(stored) == raw(expected)
