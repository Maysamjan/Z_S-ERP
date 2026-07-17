"""Entry point for Zenith License Manager (owner-only).

    python -m vendor_tools.license_manager.run
"""

import sys


def main() -> int:
    if "--help" in sys.argv:
        print("Zenith License Manager (owner-only)")
        return 0
    from vendor_tools.license_manager.app import main as app_main
    return app_main(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
