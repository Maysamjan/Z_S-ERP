"""PyInstaller / double-click entry point for Zenith Business ERP."""

import sys

from zenith.ui.app import main

if __name__ == "__main__":
    # `--help` gives packaged smoke tests something to assert on.
    if "--help" in sys.argv:
        print("Zenith Business ERP")
        raise SystemExit(0)
    raise SystemExit(main(sys.argv))
