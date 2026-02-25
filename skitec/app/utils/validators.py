"""
Utilities - Validators

Common validators and validation utilities for data integrity.
"""

import re
from typing import Optional

from app.utils.exceptions import ValidationError


class EmailValidator:
    """Email validation utilities"""

    EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    @classmethod
    def validate(cls, email: str) -> bool:
        """
        Validate email format

        Args:
            email: Email string to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(re.match(cls.EMAIL_PATTERN, email))


class PhoneValidator:
    """Phone number validation utilities"""

    @classmethod
    def validate(cls, phone: str) -> bool:
        """
        Validate phone number format

        Accepts:
        - +1234567890
        - 1234567890
        - (123) 456-7890
        - +1 (123) 456-7890

        Args:
            phone: Phone number to validate

        Returns:
            True if valid, False otherwise
        """
        pattern = r"^\+?1?\s?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$"
        return bool(re.match(pattern, phone))


class PasswordValidator:
    """Password validation utilities"""

    @classmethod
    def validate(cls, password: str) -> tuple[bool, Optional[str]]:
        """
        Validate password strength

        Requirements:
        - At least 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        special_chars = r"[!@#$%^&*()_+\-=\[\]{};:'\",.<>?/\\|`~]"
        if not re.search(special_chars, password):
            return False, "Password must contain at least one special character"

        return True, None


class DateValidator:
    """Date validation utilities"""

    @classmethod
    def is_valid_iso_date(cls, date_str: str) -> bool:
        """
        Validate ISO 8601 date format (YYYY-MM-DD)

        Args:
            date_str: Date string to validate

        Returns:
            True if valid, False otherwise
        """
        pattern = r"^\d{4}-\d{2}-\d{2}$"
        return bool(re.match(pattern, date_str))


def validate_pagination(skip: int, limit: int) -> None:
    """
    Validate pagination parameters

    Args:
        skip: Number of items to skip
        limit: Maximum items to return

    Raises:
        ValidationError: If parameters are invalid
    """
    if skip < 0:
        raise ValidationError("skip must be >= 0")
    if limit < 1 or limit > 100:
        raise ValidationError("limit must be between 1 and 100")
