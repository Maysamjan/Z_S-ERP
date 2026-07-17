"""Owner authentication for the License Manager (Argon2id, lockout, session lock)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from zenith.security.password import hash_password, verify_password
from vendor_tools.license_manager.models.db import OwnerUser
from vendor_tools.license_manager.services.audit import audit

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 5
SESSION_TIMEOUT_MINUTES = 15


class AuthError(Exception):
    pass


class AccountLocked(AuthError):
    pass


@dataclass
class OwnerSession:
    username: str
    started_at: datetime
    last_active: datetime
    locked: bool = False
    timeout_minutes: int = SESSION_TIMEOUT_MINUTES

    def touch(self) -> None:
        self.last_active = datetime.utcnow()

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return now > self.last_active + timedelta(minutes=self.timeout_minutes)

    def lock(self) -> None:
        self.locked = True


class OwnerAuthService:
    def __init__(self, session: Session):
        self.session = session

    def has_owner(self) -> bool:
        return self.session.scalar(select(OwnerUser).limit(1)) is not None

    def create_owner(self, username: str, password: str) -> OwnerUser:
        username = (username or "").strip()
        if not username:
            raise AuthError("Username required")
        if not password or len(password) < 8:
            raise AuthError("Owner password must be at least 8 characters")
        if self.session.scalar(select(OwnerUser).where(OwnerUser.username == username)):
            raise AuthError("Owner already exists")
        user = OwnerUser(username=username, password_hash=hash_password(password))
        self.session.add(user)
        self.session.flush()
        audit(self.session, "owner_created", owner=username, result="ok")
        return user

    def login(self, username: str, password: str, now: datetime | None = None) -> OwnerSession:
        now = now or datetime.utcnow()
        user = self.session.scalar(select(OwnerUser).where(OwnerUser.username == (username or "").strip()))
        if user is None:
            audit(self.session, "login_failure", owner=username, result="unknown_user")
            raise AuthError("Invalid username or password")
        if user.locked_until and now < user.locked_until:
            raise AccountLocked("Account temporarily locked")
        if not user.is_active:
            raise AuthError("Account disabled")
        if not verify_password(user.password_hash, password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_attempts = 0
                audit(self.session, "account_locked", owner=user.username, result="locked")
            else:
                audit(self.session, "login_failure", owner=user.username, result="bad_password")
            raise AuthError("Invalid username or password")
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = now
        audit(self.session, "login_success", owner=user.username, result="ok")
        return OwnerSession(username=user.username, started_at=now, last_active=now)

    def change_password(self, username: str, old: str, new: str) -> None:
        user = self.session.scalar(select(OwnerUser).where(OwnerUser.username == username))
        if not user or not verify_password(user.password_hash, old):
            raise AuthError("Current password is incorrect")
        if not new or len(new) < 8:
            raise AuthError("New password must be at least 8 characters")
        user.password_hash = hash_password(new)
        audit(self.session, "owner_password_changed", owner=username, result="ok")
