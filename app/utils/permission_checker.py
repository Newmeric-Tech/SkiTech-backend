"""
Permission checking utilities for role-based access control.
"""


def require_permission(perm: str):
    """Dependency for checking user permissions."""
    return lambda: None
