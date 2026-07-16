"""Permission resolution helpers shared by services."""

from __future__ import annotations

import json

from zenith.core.exceptions import PermissionDenied
from zenith.db.models import User
from zenith.security.permissions import Permission


_PERM_CACHE_ATTR = "_zenith_perm_cache"


def attach_permissions(session, user: User | None) -> None:
    """Cache a user's permission set as a plain attribute.

    Call this while ``user`` is still bound to ``session`` (e.g. at login). The
    cache then survives detachment, so a permission check on the detached actor
    used across later sessions never triggers a lazy ``user.role`` load.
    """
    if user is None:
        return
    perms: set[str] = set()
    if user.role_id is not None:
        from zenith.db.models import Role
        role = session.get(Role, user.role_id)
        if role is not None:
            try:
                perms = set(json.loads(role.permissions or "[]"))
            except (ValueError, TypeError):
                perms = set()
    object.__setattr__(user, _PERM_CACHE_ATTR, perms)


def user_permissions(user: User | None) -> set[str]:
    if user is None:
        return set()
    cached = getattr(user, _PERM_CACHE_ATTR, None)
    if cached is not None:
        return cached
    try:
        role = user.role
    except Exception:
        return set()
    if role is None:
        return set()
    try:
        return set(json.loads(role.permissions or "[]"))
    except (ValueError, TypeError):
        return set()


def has_permission(user: User | None, perm: Permission | str) -> bool:
    key = perm.value if isinstance(perm, Permission) else perm
    return key in user_permissions(user)


def require(user: User | None, perm: Permission | str) -> None:
    if not has_permission(user, perm):
        key = perm.value if isinstance(perm, Permission) else perm
        raise PermissionDenied(f"Missing permission: {key}", message_key="error.permission_denied")
