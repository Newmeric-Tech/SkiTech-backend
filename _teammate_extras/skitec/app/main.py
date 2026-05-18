"""
Skitec Backend - Application Entry Point

Production-ready entry point for FastAPI application.
Can be run with:
    uvicorn app.main:app --reload
    
For production, use:
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
"""

from app import app

__all__ = ["app"]
