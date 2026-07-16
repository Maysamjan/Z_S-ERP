"""Business profile registry.

Five approved profiles only. Everything profile-specific (enabled modules, menus,
dashboards, product fields, default units/roles/settings) is *data*, resolved
through this registry -- never customer-specific branching in source code.
"""

from zenith.profiles.registry import (
    PROFILES,
    ProfileCode,
    ProfileDefinition,
    get_profile,
    all_profiles,
    is_valid_profile,
)

__all__ = [
    "PROFILES",
    "ProfileCode",
    "ProfileDefinition",
    "get_profile",
    "all_profiles",
    "is_valid_profile",
]
