import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MEMBERSHIP_DB_DSN: str = "postgresql://app:password@postgres:5432/membership"
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ACCESS_EXPIRY: int = 3600
    JWT_REFRESH_EXPIRY: int = 2592000
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@example.com"
    APP_BASE_URL: str = "http://localhost:3000"
    MEMBERSHIP_SERVICE_URL: str = "http://membership-service:8095"
    PLATFORM_ADMIN_KEY: str = "change_me_platform_admin_key"


settings = Settings()
