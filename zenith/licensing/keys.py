"""Public verification key + key loading helpers.

SECURITY: the customer application contains ONLY the Ed25519 *public* key below.
The corresponding *private* signing key is held exclusively by the vendor (see
``docs/LICENSING_ARCHITECTURE.md``) and must never be committed, bundled in the
installer, or placed in customer configuration/database.

The private key is loaded on the vendor side from ``ZENITH_LICENSE_PRIVATE_KEY``
(a PEM file path) or an explicit path -- never from within this package.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Production public verification key (safe to distribute).
EMBEDDED_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAuMFgtaha55kf7FMgq38oJVWpsEc5qevgkwD7JZRbDIs=
-----END PUBLIC KEY-----
"""


def load_public_key(pem: bytes | None = None) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem or EMBEDDED_PUBLIC_KEY_PEM)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("Expected an Ed25519 public key")
    return key


def load_private_key(pem: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Expected an Ed25519 private key")
    return key


def load_vendor_private_key(path: str | None = None) -> Ed25519PrivateKey:
    """Vendor-only. Load the signing key from a PEM path or env var.

    Never call this from customer application code paths.
    """
    path = path or os.environ.get("ZENITH_LICENSE_PRIVATE_KEY")
    if not path:
        raise RuntimeError(
            "No signing key configured. Set ZENITH_LICENSE_PRIVATE_KEY to the "
            "vendor private key PEM path (vendor environment only)."
        )
    with open(path, "rb") as fh:
        return load_private_key(fh.read())


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh Ed25519 keypair -> (private_pem, public_pem).

    Used by the vendor tool's ``init-keys`` command and by tests.
    """
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem
