"""Authentication service.

Handles login with failed-attempt rate limiting and temporary lockout, password
change, and account activation. Emits audit events for success and failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from zenith.core.exceptions import AuthenticationError, AccountDisabled, RateLimited, ValidationError
from zenith.db.models import User
from zenith.security.password import hash_password, verify_password, needs_rehash
from zenith.services import audit

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 5


@dataclass
class AuthSession:
    user: User
    started_at: datetime
    timeout_minutes: int = 30

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return now > self.started_at + timedelta(minutes=self.timeout_minutes)

    def touch(self) -> None:
        self.started_at = datetime.utcnow()


class AuthService:
    def __init__(self, session: Session):
        self.session = session

    def _get(self, username: str) -> User | None:
        return self.session.scalar(
            select(User).where(User.username == username, User.is_deleted == False)  # noqa: E712
        )

    def login(self, username: str, password: str, now: datetime | None = None) -> AuthSession:
        now = now or datetime.utcnow()
        user = self._get((username or "").strip())
        if user is None:
            audit.log(self.session, "login_failure", detail=f"unknown user '{username}'")
            raise AuthenticationError(message_key="error.auth_failed")

        if user.locked_until and now < user.locked_until:
            raise RateLimited(message_key="error.too_many_attempts")

        if not user.is_active:
            audit.log(self.session, "login_failure", actor=user, detail="account disabled")
            raise AccountDisabled(message_key="error.account_disabled")

        if not verify_password(user.password_hash, password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_attempts = 0
                audit.log(self.session, "account_locked", actor=user)
            else:
                audit.log(self.session, "login_failure", actor=user,
                          detail=f"bad password ({user.failed_attempts}/{MAX_ATTEMPTS})")
            raise AuthenticationError(message_key="error.auth_failed")

        # success
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = now
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        audit.log(self.session, "login_success", actor=user)
        # Cache permissions so the (soon-detached) actor works across later sessions.
        from zenith.services.permissions_util import attach_permissions
        attach_permissions(self.session, user)
        return AuthSession(user=user, started_at=now)

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(user.password_hash, old_password):
            raise AuthenticationError(message_key="error.auth_failed")
        if not new_password or len(new_password) < 6:
            raise ValidationError(message_key="error.password_too_short")
        user.password_hash = hash_password(new_password)
        audit.log(self.session, "password_changed", actor=user)

    def set_active(self, actor: User, target: User, active: bool) -> None:
        target.is_active = active
        audit.log(self.session, "user_activated" if active else "user_deactivated",
                  actor=actor, entity="user", entity_id=target.id)
