"""ZenithLicenseManager -- vendor command-line tool.

Generates signing keys and issues/inspects/revokes signed licenses. Requires the
private signing key (env ``ZENITH_LICENSE_PRIVATE_KEY`` or ``--key``). Ships only
in the vendor environment, never to customers.

Examples
--------
    # one-time: create the vendor keypair (embed the printed public key in the app)
    zenith-license-manager init-keys --out ./vendor_keys

    # issue a 30-day Supermarket demo bound to a customer's request fingerprint
    zenith-license-manager issue \
        --profile SUPERMARKET --type DEMO --days 30 \
        --customer "Ali Ahmadi" --business "Kabul Mart" \
        --machine <fingerprint> --out kabulmart.zlic

    # inspect any key/file (verifies the signature with the public key)
    zenith-license-manager inspect --key ZBE1....
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from zenith.licensing.keys import generate_keypair, load_vendor_private_key, load_public_key
from zenith.licensing.model import LicenseType, SignedLicense
from zenith.licensing.verifier import verify_license
from zenith.profiles import ProfileCode
from zenith.vendor.license_issuer import build_license, issue_signed


def _cmd_init_keys(args: argparse.Namespace) -> int:
    priv_pem, pub_pem = generate_keypair()
    if args.out:
        import os

        os.makedirs(args.out, exist_ok=True)
        priv_path = os.path.join(args.out, "vendor_private_key.pem")
        pub_path = os.path.join(args.out, "vendor_public_key.pem")
        with open(priv_path, "wb") as fh:
            fh.write(priv_pem)
        try:
            os.chmod(priv_path, 0o600)
        except OSError:
            pass
        with open(pub_path, "wb") as fh:
            fh.write(pub_pem)
        print(f"Private key: {priv_path}  (KEEP SECRET - never ship to customers)")
        print(f"Public key : {pub_path}  (embed in zenith/licensing/keys.py)")
    print(pub_pem.decode())
    return 0


def _cmd_issue(args: argparse.Namespace) -> int:
    private_key = load_vendor_private_key(args.key)
    payload = build_license(
        customer_name=args.customer,
        business_name=args.business,
        profile_code=args.profile,
        license_type=LicenseType(args.type),
        machine_fingerprint=args.machine,
        max_users=args.max_users,
        max_branches=args.max_branches,
        enabled_modules=args.modules.split(",") if args.modules else None,
        duration_days=args.days,
        perpetual=args.perpetual,
    )
    signed = issue_signed(payload, private_key)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(signed.to_file_json())
        print(f"License file written: {args.out}")
    print("\n--- Activation key ---")
    print(signed.to_key())
    print("\n--- Summary ---")
    print(json.dumps(payload.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            signed = SignedLicense.from_file_json(fh.read())
    elif args.key:
        signed = SignedLicense.from_key(args.key)
    else:
        print("Provide --key or --file", file=sys.stderr)
        return 2

    pub_pem = None
    if args.public_key:
        with open(args.public_key, "rb") as fh:
            pub_pem = fh.read()
    result = verify_license(
        signed,
        machine_fp=signed.payload.machine_fingerprint,  # inspect: check signature only
        expected_profile=None,
        today=date.today(),
        public_key_pem=pub_pem,
    )
    print(json.dumps(signed.payload.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nSignature/verification: {'VALID' if result.ok else 'INVALID: ' + result.reason_key}")
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="zenith-license-manager", description="Zenith License Manager (vendor tool)")
    sub = p.add_subparsers(dest="command", required=True)

    pk = sub.add_parser("init-keys", help="Generate a new Ed25519 signing keypair")
    pk.add_argument("--out", help="Directory to write the keypair to")
    pk.set_defaults(func=_cmd_init_keys)

    pi = sub.add_parser("issue", help="Issue and sign a license")
    pi.add_argument("--key", help="Private key PEM path (or set ZENITH_LICENSE_PRIVATE_KEY)")
    pi.add_argument("--profile", required=True, choices=[c.value for c in ProfileCode])
    pi.add_argument("--type", required=True, choices=[t.value for t in LicenseType])
    pi.add_argument("--customer", required=True)
    pi.add_argument("--business", required=True)
    pi.add_argument("--machine", required=True, help="Machine fingerprint from the customer's request code")
    pi.add_argument("--days", type=int, default=None, help="Duration in days (demo/subscription)")
    pi.add_argument("--perpetual", action="store_true", help="Perpetual Full license")
    pi.add_argument("--max-users", type=int, default=3, dest="max_users")
    pi.add_argument("--max-branches", type=int, default=1, dest="max_branches")
    pi.add_argument("--modules", default="", help="Comma-separated module keys (empty = all for profile)")
    pi.add_argument("--out", help="Write a .zlic license file")
    pi.set_defaults(func=_cmd_issue)

    pins = sub.add_parser("inspect", help="Inspect/verify a license key or file")
    pins.add_argument("--key")
    pins.add_argument("--file")
    pins.add_argument("--public-key", help="Public key PEM (defaults to embedded key)")
    pins.set_defaults(func=_cmd_inspect)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
