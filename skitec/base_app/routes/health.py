"""
Health check endpoint.
"""

from fastapi import APIRouter, status
from datetime import datetime

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint.
    Returns service status and timestamp.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Base Service",
    }

@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """
    Readiness probe for Kubernetes/container orchestration.
    Indicates if the service is ready to handle requests.
    """
    return {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat(),
    }

@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """
    Liveness probe for Kubernetes/container orchestration.
    Indicates if the service is alive.
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat(),
    }
