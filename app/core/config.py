import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Telegram API Credentials
    API_ID: int = Field(..., description="Telegram API ID from my.telegram.org")
    API_HASH: str = Field(..., description="Telegram API Hash from my.telegram.org")
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token from @BotFather")
    
    # Storage Channel ID
    STORAGE_CHANNEL_ID: int = Field(..., description="Storage Channel ID (starts with -100)")
    
    # Database
    MONGODB_URI: str = Field(..., description="MongoDB connection URI")
    DATABASE_NAME: str = Field("telegram_file_host", description="MongoDB database name")
    
    # Web / Site URLs
    BASE_URL: str = Field("http://localhost:8000", description="Base URL of the running website")
    
    # Security
    SECRET_KEY: str = Field("dev_fallback_secret_key_change_me_in_production", description="Secret key for signatures")
    
    # Environment
    VERCEL_ENV: Optional[str] = Field("development", description="Vercel environment name (production, preview, development)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Load settings
# We can load settings, but let's allow fallback if we are running in an environment without .env (like Vercel production where environment variables are set directly)
try:
    settings = Settings()
except Exception as e:
    # If environment variables are missing (e.g. during building or setup), load from OS env with fallbacks to prevent crash during import
    # This is critical for Vercel builds where env variables might not be present at build time
    class FallbackSettings:
        API_ID = int(os.getenv("API_ID", "0"))
        API_HASH = os.getenv("API_HASH", "placeholder")
        BOT_TOKEN = os.getenv("BOT_TOKEN", "placeholder")
        STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0"))
        MONGODB_URI = os.getenv("MONGODB_URI", "")
        DATABASE_NAME = os.getenv("DATABASE_NAME", "telegram_file_host")
        BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
        SECRET_KEY = os.getenv("SECRET_KEY", "dev_fallback_secret_key")
        VERCEL_ENV = os.getenv("VERCEL_ENV", "development")
    settings = FallbackSettings()  # type: ignore
