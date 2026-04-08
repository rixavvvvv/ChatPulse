from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bulk Messaging API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    jwt_secret_key: str = Field(
        default="change-this-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    whatsapp_provider: str = Field(
        default="simulation", alias="WHATSAPP_PROVIDER")
    whatsapp_phone_number_id: str | None = Field(
        default=None,
        alias="WHATSAPP_PHONE_NUMBER_ID",
    )
    whatsapp_access_token: str | None = Field(
        default=None,
        alias="WHATSAPP_ACCESS_TOKEN",
    )
    meta_graph_api_base_url: str = Field(
        default="https://graph.facebook.com",
        alias="META_GRAPH_API_BASE_URL",
    )
    meta_graph_api_version: str = Field(
        default="v18.0",
        alias="META_GRAPH_API_VERSION",
    )
    meta_api_timeout_seconds: float = Field(
        default=15.0,
        alias="META_API_TIMEOUT_SECONDS",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )
    celery_default_queue: str = Field(
        default="bulk-messages",
        alias="CELERY_DEFAULT_QUEUE",
    )
    celery_result_ttl_seconds: int = Field(
        default=86400,
        alias="CELERY_RESULT_TTL_SECONDS",
    )
    meta_credentials_encryption_key: str = Field(
        default="change-this-meta-encryption-key",
        alias="META_CREDENTIALS_ENCRYPTION_KEY",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/bulk_messaging",
        alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        alias="CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        raise ValueError(
            "CORS_ORIGINS must be a comma-separated string or a list")

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_token_expiration(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0")
        return value

    @field_validator("whatsapp_provider")
    @classmethod
    def validate_whatsapp_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"simulation", "cloud"}:
            raise ValueError(
                "WHATSAPP_PROVIDER must be either 'simulation' or 'cloud'")
        return normalized

    @field_validator("meta_credentials_encryption_key")
    @classmethod
    def validate_meta_credentials_encryption_key(cls, value: str) -> str:
        if len(value.strip()) < 16:
            raise ValueError(
                "META_CREDENTIALS_ENCRYPTION_KEY must be at least 16 characters")
        return value

    @field_validator("meta_graph_api_base_url")
    @classmethod
    def validate_meta_graph_api_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("META_GRAPH_API_BASE_URL cannot be empty")
        return normalized

    @field_validator("meta_graph_api_version")
    @classmethod
    def validate_meta_graph_api_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("META_GRAPH_API_VERSION cannot be empty")
        return normalized

    @field_validator("meta_api_timeout_seconds")
    @classmethod
    def validate_meta_api_timeout_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("META_API_TIMEOUT_SECONDS must be greater than 0")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("REDIS_URL cannot be empty")
        return normalized

    @field_validator("celery_default_queue")
    @classmethod
    def validate_celery_default_queue(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("CELERY_DEFAULT_QUEUE cannot be empty")
        return normalized

    @field_validator("celery_result_ttl_seconds")
    @classmethod
    def validate_celery_result_ttl_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "CELERY_RESULT_TTL_SECONDS must be greater than 0")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
