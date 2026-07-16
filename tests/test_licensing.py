"""License system: signing, machine/profile binding, tamper, expiry, demo, rollback."""

from datetime import date, timedelta

import pytest

from zenith.licensing.model import LicenseType, SignedLicense
from zenith.licensing.service import LicenseService, LicenseState
from zenith.licensing.storage import ActivationStore
from zenith.licensing.verifier import verify_license
from zenith.vendor.license_issuer import build_license, issue_signed

pytestmark = pytest.mark.licensing


def _issue(private_key, machine_fp, profile="SUPERMARKET", ltype=LicenseType.DEMO,
           days=15, perpetual=False):
    payload = build_license(
        customer_name="Ali", business_name="Kabul Mart", profile_code=profile,
        license_type=ltype, machine_fingerprint=machine_fp, duration_days=days, perpetual=perpetual,
    )
    return issue_signed(payload, private_key)


def test_valid_demo_activates(keypair, machine_fp, data_dir):
    signed = _issue(keypair, machine_fp)
    svc = LicenseService(machine_fp=machine_fp)
    st = svc.import_key(signed.to_key(), expected_profile="SUPERMARKET")
    assert st.state == LicenseState.ACTIVE
    assert st.days_remaining == 15


def test_wrong_profile_rejected(keypair, machine_fp):
    signed = _issue(keypair, machine_fp, profile="SUPERMARKET")
    r = verify_license(signed, machine_fp=machine_fp, expected_profile="WHOLESALE", today=date.today())
    assert r.failed and r.reason_key == "license.error.profile"


def test_wrong_machine_rejected(keypair, machine_fp):
    signed = _issue(keypair, machine_fp)
    r = verify_license(signed, machine_fp="different-machine", expected_profile="SUPERMARKET", today=date.today())
    assert r.failed and r.reason_key == "license.error.machine"


def test_tampered_signature_rejected(keypair, machine_fp):
    signed = _issue(keypair, machine_fp)
    # flip the customer name after signing
    signed.payload.customer_name = "Attacker"
    r = verify_license(signed, machine_fp=machine_fp, expected_profile="SUPERMARKET", today=date.today())
    assert r.failed and r.reason_key == "license.error.signature"


def test_expired_demo_rejected(keypair, machine_fp):
    signed = _issue(keypair, machine_fp, days=7)
    future = date.today() + timedelta(days=30)
    r = verify_license(signed, machine_fp=machine_fp, expected_profile="SUPERMARKET", today=future)
    assert r.failed and r.reason_key == "license.error.expired"


def test_full_perpetual_never_expires(keypair, machine_fp):
    signed = _issue(keypair, machine_fp, profile="WHOLESALE", ltype=LicenseType.FULL, perpetual=True)
    far = date.today() + timedelta(days=365 * 20)
    r = verify_license(signed, machine_fp=machine_fp, expected_profile="WHOLESALE", today=far)
    assert r.ok


def test_demo_cannot_be_perpetual():
    with pytest.raises(ValueError):
        build_license(customer_name="a", business_name="b", profile_code="PHARMACY",
                      license_type=LicenseType.DEMO, machine_fingerprint="x", perpetual=True)


def test_activation_key_roundtrip(keypair, machine_fp):
    signed = _issue(keypair, machine_fp)
    key = signed.to_key()
    back = SignedLicense.from_key(key)
    assert back.payload.license_id == signed.payload.license_id
    assert back.signature_b64 == signed.signature_b64


def test_license_file_roundtrip(keypair, machine_fp):
    signed = _issue(keypair, machine_fp)
    text = signed.to_file_json()
    back = SignedLicense.from_file_json(text)
    assert back.payload.machine_fingerprint == machine_fp


def test_clock_rollback_detected(keypair, machine_fp, data_dir):
    signed = _issue(keypair, machine_fp, ltype=LicenseType.FULL, days=365)
    store = ActivationStore(machine_fp)
    svc = LicenseService(machine_fp=machine_fp, store=store)
    today = date.today()
    assert svc.import_key(signed.to_key(), expected_profile="SUPERMARKET", today=today).state == LicenseState.ACTIVE
    # move the clock backwards
    past = today - timedelta(days=5)
    st = svc.status(expected_profile="SUPERMARKET", today=past)
    assert st.state == LicenseState.CLOCK_ROLLBACK
    assert st.read_only


def test_state_copied_to_other_machine_is_ignored(keypair, machine_fp, data_dir):
    """Activation state is HMAC-bound to the machine fingerprint."""
    signed = _issue(keypair, machine_fp, ltype=LicenseType.FULL, days=365)
    store_a = ActivationStore(machine_fp)
    LicenseService(machine_fp=machine_fp, store=store_a).import_key(
        signed.to_key(), expected_profile="SUPERMARKET"
    )
    # another machine reading the same file gets no valid state
    store_b = ActivationStore("some-other-machine", path=store_a._path)
    assert store_b.load().activation_key is None


def test_transfer_request_returns_code(keypair, machine_fp, data_dir):
    signed = _issue(keypair, machine_fp, ltype=LicenseType.FULL, perpetual=True)
    svc = LicenseService(machine_fp=machine_fp)
    svc.import_key(signed.to_key(), expected_profile="SUPERMARKET")
    code = svc.begin_transfer()
    assert isinstance(code, str) and len(code) > 10


def test_not_activated_status(data_dir, machine_fp):
    svc = LicenseService(machine_fp=machine_fp)
    assert svc.status(expected_profile="GENERAL_STORE").state == LicenseState.NOT_ACTIVATED
