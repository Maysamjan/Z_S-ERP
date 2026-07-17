"""Zenith License Manager -- OWNER/VENDOR ONLY.

A separate, owner-only desktop application for generating, verifying, saving and
managing signed licenses. It holds the Ed25519 **private signing key** and MUST
NEVER be shipped to customers (not in the customer installer, source ZIP,
executable, data directory, or CI artifacts).

The customer Zenith Business ERP application can only *verify* licenses (it ships
only the public key). Nothing under ``vendor_tools`` may be imported by the
customer runtime.
"""

__app_name__ = "Zenith License Manager"
__exe_name__ = "ZenithLicenseManager.exe"
__version__ = "0.1.0"
