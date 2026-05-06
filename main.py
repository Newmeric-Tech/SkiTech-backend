"""
SciTech - Root Entry Point

Allows running uvicorn from the project root directory.
Use: uvicorn main:app --reload
"""

from skitec.app import app

__all__ = ["app"]
