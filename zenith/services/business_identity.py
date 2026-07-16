"""Global Business Identity service.

One authoritative source for the customer's business name, logo, contact details
and document footers/terms. Consumed by the app shell, settings, and every
official document/report -- never re-read ad hoc per page.

Logo handling copies the chosen image into an application-managed folder under the
customer data directory, so the logo survives even if the original file is moved
or deleted, and is included in backups.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from zenith.core import paths
from zenith.core.exceptions import ValidationError
from zenith.db.models import BusinessSettings, User
from zenith.security.permissions import Permission
from zenith.services import audit
from zenith.services.permissions_util import require

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+()\-\s0-9]{6,25}$")
LOGO_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_LOGO_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class BusinessIdentity:
    """Immutable snapshot used by the shell and documents (locale-aware)."""
    name_fa: str
    name_en: str
    logo_path: str | None
    phone: str
    phone_secondary: str
    whatsapp: str
    email: str
    website: str
    address_fa: str
    address_en: str
    registration_no: str
    tax_no: str
    slogan: str
    currency: str

    def name(self, locale: str = "en_US") -> str:
        if locale.startswith("fa") or locale.startswith("ps"):
            return self.name_fa or self.name_en
        return self.name_en or self.name_fa

    def address(self, locale: str = "en_US") -> str:
        if locale.startswith("fa") or locale.startswith("ps"):
            return self.address_fa or self.address_en
        return self.address_en or self.address_fa


def logo_dir() -> Path:
    d = paths.data_dir() / "business"
    d.mkdir(parents=True, exist_ok=True)
    return d


class BusinessIdentityService:
    def __init__(self, session: Session):
        self.session = session

    def _settings(self) -> BusinessSettings:
        s = self.session.scalar(select(BusinessSettings).limit(1))
        if s is None:
            raise ValidationError(message_key="error.not_found")
        return s

    def get_identity(self) -> BusinessIdentity:
        s = self._settings()
        return BusinessIdentity(
            name_fa=s.business_name or "",
            name_en=s.business_name_en or s.business_name or "",
            logo_path=s.logo_path,
            phone=s.phone or "",
            phone_secondary=s.phone_secondary or "",
            whatsapp=s.whatsapp or "",
            email=s.email or "",
            website=s.website or "",
            address_fa=s.address or "",
            address_en=s.address_en or s.address or "",
            registration_no=s.registration_no or "",
            tax_no=s.tax_no or "",
            slogan=s.slogan or "",
            currency=s.currency or "AFN",
        )

    def update(self, actor: User, **fields) -> BusinessSettings:
        require(actor, Permission.SETTINGS_MANAGE)
        s = self._settings()

        name = (fields.get("business_name") if "business_name" in fields else s.business_name) or ""
        if not name.strip():
            raise ValidationError(message_key="error.name_required")

        email = fields.get("email")
        if email and not _EMAIL_RE.match(email.strip()):
            raise ValidationError(message_key="error.invalid_email")

        for pk in ("phone", "phone_secondary", "whatsapp"):
            val = fields.get(pk)
            if val and not _PHONE_RE.match(val.strip()):
                raise ValidationError(message_key="error.invalid_phone")

        allowed = {c.name for c in BusinessSettings.__table__.columns} - {"id", "profile_code"}
        for key, value in fields.items():
            if key in allowed:
                setattr(s, key, value)
        audit.log(self.session, "business_identity_update", actor=actor,
                  entity="business_settings", entity_id=s.id)
        return s

    def set_logo(self, actor: User, source_path: str | Path) -> str:
        """Validate and copy a logo into the managed business directory."""
        require(actor, Permission.SETTINGS_MANAGE)
        src = Path(source_path)
        if not src.exists():
            raise ValidationError(message_key="error.file_not_found")
        if src.suffix.lower() not in LOGO_FORMATS:
            raise ValidationError(message_key="error.logo_format")
        if src.stat().st_size > MAX_LOGO_BYTES:
            raise ValidationError(message_key="error.logo_too_large")
        dest = logo_dir() / f"customer_logo{src.suffix.lower()}"
        # remove any previously stored logo with a different extension
        for existing in logo_dir().glob("customer_logo.*"):
            if existing != dest:
                existing.unlink(missing_ok=True)
        shutil.copy2(src, dest)
        s = self._settings()
        s.logo_path = str(dest)
        audit.log(self.session, "business_logo_update", actor=actor,
                  entity="business_settings", entity_id=s.id, detail=dest.name)
        return str(dest)

    def remove_logo(self, actor: User) -> None:
        require(actor, Permission.SETTINGS_MANAGE)
        s = self._settings()
        if s.logo_path:
            Path(s.logo_path).unlink(missing_ok=True)
        s.logo_path = None
        audit.log(self.session, "business_logo_remove", actor=actor,
                  entity="business_settings", entity_id=s.id)
