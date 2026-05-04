"""
config.py
Centralised settings loaded from environment / .env file.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # AWS
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "streamvault-videos"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./streamvault.db"

    # App
    APP_NAME: str = "StreamVault"
    PRESIGNED_URL_EXPIRY: int = 3600        # 1 hour
    MAX_UPLOAD_SIZE_MB: int = 2048          # 2 GB


settings = Settings()
