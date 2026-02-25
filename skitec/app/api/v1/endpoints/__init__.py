"""
Endpoints Module - Initialization
"""

from app.api.v1.endpoints import auth, governance, properties, reports, users, workforce

__all__ = [
    "auth",
    "users",
    "properties",
    "workforce",
    "governance",
    "reports",
]
