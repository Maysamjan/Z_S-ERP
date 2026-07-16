"""Password hashing with Argon2id.

Passwords are never stored in plaintext. Argon2id is the default; parameters are
sized for a desktop machine. ``needs_rehash`` lets us transparently upgrade hashes
when parameters change.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)


def hash_password(password: str) -> str:
    if not password or len(password) < 4:
        raise ValueError("Password too short")
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored_hash)
    except Exception:
        return False
