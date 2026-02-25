"""
Utilities Module - Initialization
"""

from app.utils.exceptions import (
    ConflictError,
    DatabaseError,
    ForbiddenError,
    InvalidCredentialsError,
    NotFoundError,
    SkitecException,
    UnauthorizedError,
    ValidationError,
)
from app.utils.helpers import (
    convert_timestamp_to_timezone,
    format_datetime,
    get_utc_now,
    paginate,
    safe_get,
    truncate_string,
)
from app.utils.validators import (
    DateValidator,
    EmailValidator,
    PasswordValidator,
    PhoneValidator,
    validate_pagination,
)

__all__ = [
    # Exceptions
    "SkitecException",
    "InvalidCredentialsError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "DatabaseError",
    # Validators
    "EmailValidator",
    "PhoneValidator",
    "PasswordValidator",
    "DateValidator",
    "validate_pagination",
    # Helpers
    "get_utc_now",
    "convert_timestamp_to_timezone",
    "format_datetime",
    "safe_get",
    "truncate_string",
    "paginate",
]
