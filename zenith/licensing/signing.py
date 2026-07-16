"""Vendor-side license signing.

This module is imported by the vendor tool. It requires the private signing key,
which is never present in a customer installation, so signing simply cannot happen
on a customer machine.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from zenith.licensing.model import License, SignedLicense


def sign_license(payload: License, private_key: Ed25519PrivateKey) -> SignedLicense:
    signature = private_key.sign(payload.canonical_bytes())
    return SignedLicense(payload=payload, signature_b64=base64.b64encode(signature).decode("ascii"))
