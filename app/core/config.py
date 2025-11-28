"""
Application Configuration Module.

This module uses Pydantic Settings to manage configuration from environment variables.
All settings are validated at startup, failing fast if required values are missing.

Usage:
    from app.core.config import settings
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings are validated using Pydantic V2. Required settings will raise
    an error at startup if not provided, ensuring fail-fast behavior.
    
    Attributes:
        APP_NAME: Name of the application.
        APP_ENV: Current environment (development/staging/production).
        DEBUG: Enable debug mode (never True in production).
        DATABASE_URL: Async PostgreSQL connection string.
        REDIS_URL: Redis connection string for caching.
        SUPABASE_URL: Supabase project URL.
        SUPABASE_JWT_SECRET: Secret for validating Supabase JWTs.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra env vars
    )
    
    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    APP_NAME: str = "Exclusive-Change"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    
    # -------------------------------------------------------------------------
    # Database Settings (Supabase PostgreSQL)
    # -------------------------------------------------------------------------
    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = Field(default=20, ge=5, le=100)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=10, le=120)
    
    # -------------------------------------------------------------------------
    # Redis Cache Settings
    # -------------------------------------------------------------------------
    REDIS_URL: RedisDsn = Field(default="redis://localhost:6379/0")  # type: ignore
    CACHE_TTL_SECONDS: int = Field(default=30, ge=1, le=3600)
    
    # -------------------------------------------------------------------------
    # Supabase Auth Settings
    # -------------------------------------------------------------------------
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str  # Public anon key for Supabase Auth API
    SUPABASE_JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    
    # -------------------------------------------------------------------------
    # CORS Settings
    # -------------------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:3000"
    
    # -------------------------------------------------------------------------
    # API Key Settings
    # -------------------------------------------------------------------------
    API_KEY_PREFIX: str = "xc_live_"
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string to list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return str(self.DATABASE_URL).replace(
            "postgresql+asyncpg://", "postgresql://"
        )
    
    @field_validator("DEBUG", mode="before")
    @classmethod
    def validate_debug_in_production(cls, v: bool, info) -> bool:
        """Ensure DEBUG is always False in production."""
        # Note: We can't access other fields easily in V2 validators
        # This is handled in __init__ instead
        return v
    
    def __init__(self, **kwargs) -> None:
        """Initialize settings and validate environment-specific rules."""
        super().__init__(**kwargs)
        
        # Security: Never allow DEBUG in production
        if self.APP_ENV == "production" and self.DEBUG:
            raise ValueError("DEBUG must be False in production environment")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Uses lru_cache to ensure settings are only loaded once and reused
    across the application lifecycle.
    
    Returns:
        Settings: Application settings instance.
    
    Example:
        >>> settings = get_settings()
        >>> print(settings.APP_NAME)
        'Exclusive-Change'
    """
    return Settings()


# Convenience export for direct import
settings = get_settings()
