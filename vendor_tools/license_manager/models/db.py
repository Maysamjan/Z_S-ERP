"""Vendor-only SQLite database: owner accounts, license history, audit log.

Completely separate from the customer ERP database. Stored under the owner's
vendor data directory (never a customer data directory).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, String, Integer, DateTime, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session


class VendorBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def vendor_data_dir() -> Path:
    env = os.environ.get("ZENITH_VENDOR_DIR")
    if env:
        p = Path(env)
    elif os.name == "nt":  # pragma: no cover - Windows only
        p = Path(os.environ.get("APPDATA", str(Path.home()))) / "ZenithLicenseManager"
    else:
        p = Path.home() / ".local" / "share" / "ZenithLicenseManager"
    p.mkdir(parents=True, exist_ok=True)
    return p


class OwnerUser(VendorBase):
    __tablename__ = "owner_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class LicenseRecord(VendorBase):
    """One issued license, with full history and renewal/replacement links."""
    __tablename__ = "license_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(60), default="", index=True)
    customer_name: Mapped[str] = mapped_column(String(160), default="", index=True)
    business_name: Mapped[str] = mapped_column(String(200), default="", index=True)
    phone: Mapped[str] = mapped_column(String(60), default="", index=True)
    email: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    machine_fingerprint: Mapped[str] = mapped_column(String(80), default="", index=True)
    profile_code: Mapped[str] = mapped_column(String(40), default="", index=True)
    license_type: Mapped[str] = mapped_column(String(10), default="")   # DEMO/FULL
    is_perpetual: Mapped[bool] = mapped_column(Boolean, default=False)
    start_date: Mapped[str] = mapped_column(String(12), default="")
    expiry_date: Mapped[str | None] = mapped_column(String(12))
    max_users: Mapped[int] = mapped_column(Integer, default=1)
    max_branches: Mapped[int] = mapped_column(Integer, default=1)
    enabled_modules: Mapped[str] = mapped_column(Text, default="[]")     # JSON list
    activation_key: Mapped[str] = mapped_column(Text, default="")        # full ZBE1 key
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    created_by: Mapped[str] = mapped_column(String(60), default="")
    renewed_from: Mapped[str | None] = mapped_column(String(40))         # prior license_id
    replaced_from: Mapped[str | None] = mapped_column(String(40))        # prior license_id
    reason: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    #  active / expired / replaced / revoked_local / test


class VendorAudit(VendorBase):
    __tablename__ = "vendor_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    owner_user: Mapped[str] = mapped_column(String(60), default="")
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    license_id: Mapped[str] = mapped_column(String(40), default="")
    customer: Mapped[str] = mapped_column(String(160), default="")
    profile: Mapped[str] = mapped_column(String(40), default="")
    result: Mapped[str] = mapped_column(String(20), default="")
    reason: Mapped[str] = mapped_column(Text, default="")


class VendorDatabase:
    def __init__(self, url: str | None = None):
        if url is None:
            url = f"sqlite:///{vendor_data_dir() / 'vendor.db'}"
        self.url = url
        self.engine = create_engine(url, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _fk(dbapi_conn, _):  # pragma: no cover
                cur = dbapi_conn.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.close()
        self._Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        VendorBase.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self._Session()


@contextmanager
def session_scope(db: VendorDatabase):
    s = db.session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
