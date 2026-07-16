"""License system.

A license is a small JSON payload, Ed25519-signed by the vendor. The customer
application ships **only** the public verification key; the private signing key
lives exclusively in the separate vendor tool (``zenith.vendor``) and must never
be committed or bundled.

Every license is bound to one business profile, one customer/business, and one
machine fingerprint. Verification enforces signature, machine, profile, edition,
dates and limits -- copying the license/database/config to another machine or
using it for another profile fails.
"""

from zenith.licensing.model import License, LicenseType
from zenith.licensing.machine import machine_fingerprint, request_code
from zenith.licensing.verifier import verify_license, LicenseVerification
from zenith.licensing.service import LicenseService, LicenseStatus

__all__ = [
    "License",
    "LicenseType",
    "machine_fingerprint",
    "request_code",
    "verify_license",
    "LicenseVerification",
    "LicenseService",
    "LicenseStatus",
]
