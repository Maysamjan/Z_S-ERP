"""First-run database bootstrap.

Seeds the roles, an administrator account, a default warehouse/account and the
profile's default units, and writes the chosen profile into ``BusinessSettings``.
Idempotent: safe to call again; it only creates what is missing.
"""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from zenith.db.models import (
    Role, User, Warehouse, Unit, Account, BusinessSettings, SchemaVersion,
)
from zenith.profiles import get_profile
from zenith.security.password import hash_password
from zenith.security.permissions import ROLE_TEMPLATES
from zenith.services import audit

CURRENT_SCHEMA_VERSION = 4


def seed_roles(session: Session) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name, perms in ROLE_TEMPLATES.items():
        role = session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, permissions=json.dumps(perms), is_system=True)
            session.add(role)
            session.flush()
        roles[name] = role
    return roles


def is_initialized(session: Session) -> bool:
    return session.scalar(select(BusinessSettings).limit(1)) is not None


def initialize(session: Session, *, profile_code: str, business_name: str,
               admin_username: str, admin_password: str, admin_full_name: str = "",
               currency: str = "AFN", language: str = "en_US",
               date_system: str = "gregorian") -> User:
    """Create the initial dataset for a freshly selected profile."""
    profile = get_profile(profile_code)  # validates the code

    if session.scalar(select(SchemaVersion).limit(1)) is None:
        session.add(SchemaVersion(version=CURRENT_SCHEMA_VERSION))

    roles = seed_roles(session)

    admin = session.scalar(select(User).where(User.username == admin_username))
    if admin is None:
        admin = User(
            username=admin_username,
            full_name=admin_full_name or admin_username,
            password_hash=hash_password(admin_password),
            role_id=roles["Administrator"].id,
            is_active=True,
        )
        session.add(admin)
        session.flush()

    # default warehouse
    if session.scalar(select(Warehouse).limit(1)) is None:
        session.add(Warehouse(code="MAIN", name="Main Warehouse", is_default=True))

    # default cash account
    if session.scalar(select(Account).limit(1)) is None:
        session.add(Account(name="Cash", kind="cash", balance=Decimal("0"), is_default=True))

    # profile default units
    existing_units = {u.code for u in session.scalars(select(Unit))}
    for code in profile.default_units:
        if code not in existing_units:
            session.add(Unit(code=code, name=code))

    # business settings
    settings = session.scalar(select(BusinessSettings).limit(1))
    if settings is None:
        settings = BusinessSettings(profile_code=profile_code)
        session.add(settings)
    settings.business_name = business_name
    settings.profile_code = profile_code
    settings.currency = currency
    settings.language = language
    settings.date_system = date_system

    session.flush()
    audit.log(session, "system_initialized", actor=admin, detail=f"profile={profile_code}")
    from zenith.services.permissions_util import attach_permissions
    attach_permissions(session, admin)
    return admin
