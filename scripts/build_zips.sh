#!/usr/bin/env bash
# Build the customer-safe and owner-only source ZIPs from the committed HEAD.
#
#   Zenith-Business-ERP-Source.zip            -> customers (NO signing code)
#   Zenith-License-Manager-Source-Owner-Only.zip -> owner only (full, incl. vendor_tools)
#
# The customer ZIP excludes every private-key signing path:
#   vendor_tools/, zenith/vendor/, zenith/licensing/signing.py, and the dev tests.
set -euo pipefail
OUT="${1:-dist}"
mkdir -p "$OUT"

echo "Building customer-safe source ZIP (no signing code)…"
git archive --format=zip -o "$OUT/Zenith-Business-ERP-Source.zip" HEAD -- . \
  ':(exclude)vendor_tools' \
  ':(exclude)zenith/vendor' \
  ':(exclude)zenith/licensing/signing.py' \
  ':(exclude)tests'

echo "Building owner-only License Manager source ZIP (full)…"
git archive --format=zip -o "$OUT/Zenith-License-Manager-Source-Owner-Only.zip" HEAD

echo "Done:"
ls -lh "$OUT"/*.zip

echo
echo "Verifying the customer ZIP contains no signing code…"
if unzip -l "$OUT/Zenith-Business-ERP-Source.zip" | grep -E 'vendor_tools|zenith/vendor|signing\.py' ; then
  echo "ERROR: customer ZIP contains signing code!" >&2; exit 1
else
  echo "OK: customer ZIP is free of signing/vendor code."
fi
