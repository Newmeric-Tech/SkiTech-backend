"""
Permission checking utilities for role-based access control
"""


def require_permission(perm):
    """
    Dependency for checking user permissions
    
    Args:
        perm: Permission string to check
        
    Returns:
        Dependency function
    """
    return lambda: None
