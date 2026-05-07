"""
Utilities - Helpers

Common helper functions and utilities used throughout the application.
"""

from datetime import datetime
from typing import Optional

import pytz


def get_utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(pytz.UTC)


def convert_timestamp_to_timezone(
    timestamp: datetime, timezone: str = "UTC"
) -> datetime:
    """
    Convert timestamp to specific timezone

    Args:
        timestamp: Datetime to convert
        timezone: Target timezone string (e.g., 'US/Eastern')

    Returns:
        Datetime in specified timezone
    """
    if timestamp.tzinfo is None:
        timestamp = pytz.UTC.localize(timestamp)

    target_tz = pytz.timezone(timezone)
    return timestamp.astimezone(target_tz)


def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime to string

    Args:
        dt: Datetime to format
        format_str: Format string

    Returns:
        Formatted datetime string
    """
    return dt.strftime(format_str)


def safe_get(dictionary: dict, key: str, default: Optional[str] = None):
    """
    Safely get value from dictionary

    Args:
        dictionary: Dictionary to get from
        key: Key to retrieve
        default: Default value if key not found

    Returns:
        Value from dictionary or default
    """
    return dictionary.get(key, default)


def truncate_string(text: str, length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to specified length

    Args:
        text: String to truncate
        length: Maximum length
        suffix: Suffix to append if truncated

    Returns:
        Truncated string
    """
    if len(text) <= length:
        return text
    return text[: length - len(suffix)] + suffix


def paginate(
    items: list, skip: int = 0, limit: int = 20
) -> tuple[list, int]:
    """
    Paginate a list

    Args:
        items: List to paginate
        skip: Number of items to skip
        limit: Maximum items to return

    Returns:
        Tuple of (paginated_list, total_count)
    """
    total = len(items)
    return items[skip : skip + limit], total
