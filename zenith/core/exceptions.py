"""Domain exceptions used across the service layer.

Each carries a translation key so the UI can present a localized message without
string-matching on error text.
"""

from __future__ import annotations


class ZenithError(Exception):
    """Base class. ``message_key`` maps to a translation entry."""

    message_key = "error.generic"

    def __init__(self, message: str = "", *, message_key: str | None = None, **params):
        super().__init__(message or (message_key or self.message_key))
        if message_key:
            self.message_key = message_key
        self.params = params


class ValidationError(ZenithError):
    message_key = "error.validation"


class PermissionDenied(ZenithError):
    message_key = "error.permission_denied"


class AuthenticationError(ZenithError):
    message_key = "error.auth_failed"


class AccountDisabled(AuthenticationError):
    message_key = "error.account_disabled"


class RateLimited(AuthenticationError):
    message_key = "error.too_many_attempts"


class NotFound(ZenithError):
    message_key = "error.not_found"


class BusinessRuleError(ZenithError):
    message_key = "error.business_rule"


class InsufficientStock(BusinessRuleError):
    message_key = "error.insufficient_stock"


class ExpiredStockError(BusinessRuleError):
    message_key = "error.expired_stock"


class CreditLimitExceeded(BusinessRuleError):
    message_key = "error.credit_limit"


class CreditNeedsCustomer(BusinessRuleError):
    message_key = "error.credit_needs_customer"


class CashCustomerNoDebt(BusinessRuleError):
    message_key = "error.cash_customer_no_debt"


class DuplicatePosting(BusinessRuleError):
    message_key = "error.duplicate_posting"


class AlreadyReversed(BusinessRuleError):
    message_key = "error.already_reversed"


# --- Licensing ------------------------------------------------------------
class LicenseError(ZenithError):
    message_key = "license.error.generic"


class LicenseSignatureInvalid(LicenseError):
    message_key = "license.error.signature"


class LicenseExpired(LicenseError):
    message_key = "license.error.expired"


class LicenseMachineMismatch(LicenseError):
    message_key = "license.error.machine"


class LicenseProfileMismatch(LicenseError):
    message_key = "license.error.profile"


class LicenseClockRollback(LicenseError):
    message_key = "license.error.clock_rollback"


class LicenseLimitExceeded(LicenseError):
    message_key = "license.error.limit"
