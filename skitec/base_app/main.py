"""
Base FastAPI Application
Main entry point for the service.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from routes import health

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Service is running"}

# Lifespan event handlers
@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    print(f"Starting {settings.APP_NAME}...")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    print(f"Shutting down {settings.APP_NAME}...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
