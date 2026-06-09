"""
Core Configuration - app/core/config.py

Loads all settings from environment variables / .env file.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "SkiTech"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:pstsql16@localhost:5432/skitech"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # JWT & Security
    SECRET_KEY: str = "change-me-in-production-minimum-32-characters-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "https://skitech-iota.vercel.app",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5173",
    ]
    ALLOWED_CREDENTIALS: bool = True
    ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    ALLOWED_HEADERS: List[str] = ["*"]

    # Email / OTP
    SENDGRID_API_KEY: str = ""
    SMTP_EMAIL: str = ""
    SMTP_PASSWORD: str = ""

    # AWS S3 — shared credentials used by all S3 buckets
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # S3 bucket names (create these in the AWS console)
    S3_PROPERTY_IMAGES_BUCKET: str = "skitech-property-images"  # public-read
    S3_SOP_BUCKET: str = "skitech-sop-documents"                # private
    S3_CHAT_BUCKET: str = "skitech-chat-files"                   # private

    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "https://skitech-iota.vercel.app"

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None

    class Config:
        env_file = str(Path(__file__).resolve().parent.parent.parent / ".env")
        case_sensitive = True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()
