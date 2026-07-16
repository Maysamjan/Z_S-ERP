"""Profile registry: exactly the five approved profiles, all valid, no leftovers."""

import pytest

from zenith.profiles import all_profiles, get_profile, is_valid_profile, ProfileCode, PROFILES
from zenith.profiles.modules import MODULE_CATALOG, module_exists

FORBIDDEN = [
    "RESTAURANT", "COFFEE_SHOP", "HOTEL", "MOBILE_SHOP", "IMEI", "MOBILE_REPAIR",
    "COMPUTER_REPAIR", "SCHOOL", "UNIVERSITY", "TRAINING_CENTER", "KINDERGARTEN",
    "DARUL_ULOOM", "MANUFACTURING", "PROJECT_MANAGEMENT",
]

APPROVED = {"GENERAL_STORE", "SUPERMARKET", "WHOLESALE", "PHARMACY", "WAREHOUSE"}


def test_exactly_five_profiles():
    assert len(PROFILES) == 5
    assert {c.value for c in PROFILES} == APPROVED


def test_forbidden_profiles_absent():
    for code in FORBIDDEN:
        assert not is_valid_profile(code)


@pytest.mark.parametrize("code", sorted(APPROVED))
def test_profile_loads_and_is_consistent(code):
    prof = get_profile(code)
    assert prof.code.value == code
    # every enabled module exists in the catalog
    for key in prof.enabled_modules:
        assert module_exists(key), f"{code} references unknown module {key}"
    # dashboard cards + product fields are non-empty
    assert prof.dashboard_cards
    assert prof.product_fields
    assert "code" in prof.product_fields and "name" in prof.product_fields


def test_profiles_have_translation_keys():
    import json
    from zenith.core import paths
    en = json.loads((paths.resource_dir() / "translations" / "en_US.json").read_text(encoding="utf-8"))
    for prof in all_profiles():
        assert prof.name_key in en
        assert prof.description_key in en
        for hk in prof.highlight_keys:
            assert hk in en, f"missing translation {hk}"


def test_module_titles_translated():
    import json
    from zenith.core import paths
    en = json.loads((paths.resource_dir() / "translations" / "en_US.json").read_text(encoding="utf-8"))
    for mod in MODULE_CATALOG.values():
        assert mod.title_key in en, f"missing module title {mod.title_key}"
        assert mod.group in en
