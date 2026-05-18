"""
Uvicorn configuration for improved performance - uvicorn_config.py

Windows-compatible performance tuning.

Usage:
    uvicorn uvicorn_config:app
    uvicorn uvicorn_config:app --reload
    uvicorn uvicorn_config:app --host 0.0.0.0 --port 8000 --workers 4

For Linux/macOS, add: --loop uvloop
"""

import logging
import sys
from app import app

if __name__ == "__main__":
    import uvicorn
    
    kwargs = {
        "host": "0.0.0.0",
        "port": 8000,
        "reload": True,  # Change to False in production
        "access_log": False,  # Disable access logs (using middleware logging instead)
        "log_level": logging.INFO,
    }
    
    # Use uvloop on Linux/macOS for better performance
    if sys.platform != "win32":
        kwargs["loop"] = "uvloop"
        kwargs["http"] = "httptools"
    
    uvicorn.run("app:app", **kwargs)
