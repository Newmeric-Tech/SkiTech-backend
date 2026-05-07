"""
Core Configuration Module

Handles environment variables and application-level configuration.
Uses Pydantic Settings for typed, validated configuration management.
Supports development, staging, and production environments.

Environment-specific settings can override defaults via .env files.
"""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Settings

    Configuration is loaded from environment variables and .env files.
    Use uppercase names for environment variables.
    """

    # Application
    APP_NAME: str = "Skitec"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Skitec"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://neondb_owner:npg_rwo8P2MWAekG@ep-nameless-sunset-a4voeg0c-pooler.us-east-1.aws.neon.tech/neondb"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 0
    DB_ECHO: bool = False

    # JWT & Security
    SECRET_KEY: str = "change-me-in-production-minimum-32-characters-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5173",
    ]
    ALLOWED_CREDENTIALS: bool = True
    ALLOWED_METHODS: list[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    ALLOWED_HEADERS: list[str] = ["*"]

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None

    # Email/SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # File Upload
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB

    # AWS S3 Configuration
    AWS_S3_BUCKET_NAME: str = ""
    AWS_S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_ENDPOINT_URL: Optional[str] = None  # For S3-compatible services
    S3_FILE_UPLOAD_PREFIX: str = "kra-submissions"  # S3 folder prefix

    # Redis (for caching & background tasks)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Reporting
    REPORT_RETENTION_DAYS: int = 90

    class Config:
        """Pydantic config"""
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() == "development"


# Global settings instance
settings = Settings()
