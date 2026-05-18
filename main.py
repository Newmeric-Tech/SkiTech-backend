"""
Entry point - main.py

Run with:
    uvicorn main:app --reload
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from app import app  # main FastAPI app instance


@app.get("/")
async def root():
    return {
        "message": "SkiTech API is running",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }


__all__ = ["app"]
