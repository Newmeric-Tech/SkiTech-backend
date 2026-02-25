"""
Configuration settings for the service.
"""

from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    """Application configuration settings."""
    
    # App metadata
    APP_NAME: str = os.getenv("APP_NAME", "Base Service")
    APP_DESCRIPTION: str = os.getenv("APP_DESCRIPTION", "Base FastAPI Service")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    
    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8001",
    ]
    
    # Database settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/skitec"
    )
    DATABASE_ECHO: bool = os.getenv("DATABASE_ECHO", "False").lower() == "true"
    
    # Redis settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # API settings
    API_PREFIX: str = "/api/v1"
    API_TIMEOUT: int = 30
    
    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    class Config:
        """Pydantic config."""
        env_file = ".env"
        case_sensitive = True

# Create global settings instance
settings = Settings()
