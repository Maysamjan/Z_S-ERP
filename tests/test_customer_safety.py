"""Guard: the customer ERP runtime must never import private-key signing code.

Importing the customer application (verification path) must not pull in
``zenith.licensing.signing``, ``zenith.vendor`` or ``vendor_tools`` -- those are
owner-only. The customer can verify but not generate licenses.
"""

from __future__ import annotations

import subprocess
import sys


def test_customer_runtime_has_no_signing_imports():
    # Run in a clean subprocess so earlier test imports don't pollute sys.modules.
    code = (
        "import zenith.ui.app, zenith.licensing.service, zenith.licensing.verifier, "
        "zenith.ui.pages.admin_pages, zenith.ui.screens.setup_wizard, sys;"
        "bad=[m for m in sys.modules if m=='zenith.licensing.signing' "
        "or m.startswith('zenith.vendor') or m.startswith('vendor_tools')];"
        "print('BAD:'+','.join(bad)); assert not bad, bad"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={"QT_QPA_PLATFORM": "offscreen", "PATH": __import__("os").environ.get("PATH", "")})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BAD:\n" in (result.stdout + "\n") or "BAD:" in result.stdout


def test_customer_verifier_needs_only_public_key():
    # verify_license accepts a public key but there is no signing symbol in the module
    import zenith.licensing.verifier as v
    assert not hasattr(v, "sign_license")


def test_signing_module_is_isolated():
    # signing exists (for the vendor) but is not imported by the customer service
    import importlib
    svc = importlib.import_module("zenith.licensing.service")
    src = svc.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "signing" not in text and "sign_license" not in text
