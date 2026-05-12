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
    super_admin_email: str | None = Field(
        default=None,
        alias="SUPER_ADMIN_EMAIL",
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
    whatsapp_default_calling_code: str | None = Field(
        default=None,
        alias="WHATSAPP_DEFAULT_CALLING_CODE",
        description=(
            "Optional ITU country calling code (no +), e.g. 91 for India. "
            "When set, 10-digit numbers stored without a country code are prefixed for Meta API `to`."
        ),
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
    meta_webhook_verify_token: str = Field(
        default="change-this-webhook-token",
        alias="META_WEBHOOK_VERIFY_TOKEN",
    )
    meta_app_secret: str | None = Field(
        default=None,
        alias="META_APP_SECRET",
    )
    public_base_url: str | None = Field(
        default=None,
        alias="PUBLIC_BASE_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )
    celery_default_queue: str = Field(
        default="bulk-messages",
        alias="CELERY_DEFAULT_QUEUE",
    )
    celery_webhook_queue: str = Field(
        default="webhooks",
        alias="CELERY_WEBHOOK_QUEUE",
    )
    celery_result_ttl_seconds: int = Field(
        default=86400,
        alias="CELERY_RESULT_TTL_SECONDS",
    )
    queue_retry_max_attempts: int = Field(
        default=4,
        alias="QUEUE_RETRY_MAX_ATTEMPTS",
    )
    queue_retry_base_delay_seconds: int = Field(
        default=2,
        alias="QUEUE_RETRY_BASE_DELAY_SECONDS",
    )
    queue_idempotency_ttl_seconds: int = Field(
        default=604800,
        alias="QUEUE_IDEMPOTENCY_TTL_SECONDS",
    )
    queue_inflight_ttl_seconds: int = Field(
        default=120,
        alias="QUEUE_INFLIGHT_TTL_SECONDS",
    )
    queue_workspace_rate_limit_count: int = Field(
        default=20,
        alias="QUEUE_WORKSPACE_RATE_LIMIT_COUNT",
    )
    queue_workspace_rate_limit_window_seconds: int = Field(
        default=1,
        alias="QUEUE_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS",
    )
    webhook_dispatch_max_retries: int = Field(
        default=5,
        alias="WEBHOOK_DISPATCH_MAX_RETRIES",
    )
    webhook_dedupe_ttl_seconds: int = Field(
        default=900,
        alias="WEBHOOK_DEDUPE_TTL_SECONDS",
    )
    webhook_ingest_rate_limit_per_ip_per_minute: int = Field(
        default=0,
        alias="WEBHOOK_INGEST_RATE_LIMIT_PER_IP_PER_MINUTE",
        description="0 disables per-IP sliding window limiting on webhook HTTP ingress.",
    )
    queue_dlq_enabled: bool = Field(default=True, alias="QUEUE_DLQ_ENABLED")
    meta_credentials_encryption_key: str = Field(
        default="change-this-meta-encryption-key",
        alias="META_CREDENTIALS_ENCRYPTION_KEY",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/bulk_messaging",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(
        default=2,
        alias="DATABASE_POOL_SIZE",
    )
    database_max_overflow: int = Field(
        default=0,
        alias="DATABASE_MAX_OVERFLOW",
    )
    database_pool_timeout_seconds: int = Field(
        default=30,
        alias="DATABASE_POOL_TIMEOUT_SECONDS",
    )
    database_pool_recycle_seconds: int = Field(
        default=1800,
        alias="DATABASE_POOL_RECYCLE_SECONDS",
    )
    database_use_null_pool: bool = Field(
        default=False,
        alias="DATABASE_USE_NULL_POOL",
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

    @field_validator("super_admin_email")
    @classmethod
    def validate_super_admin_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        return normalized

    @field_validator("whatsapp_default_calling_code")
    @classmethod
    def validate_whatsapp_default_calling_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = "".join(ch for ch in value.strip() if ch.isdigit())
        if not normalized or len(normalized) > 3:
            raise ValueError(
                "WHATSAPP_DEFAULT_CALLING_CODE must be 1-3 digits (e.g. 91), no plus sign",
            )
        return normalized

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

    @field_validator("database_pool_size", "database_pool_timeout_seconds", "database_pool_recycle_seconds")
    @classmethod
    def validate_positive_database_pool_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Database pool settings must be greater than 0")
        return value

    @field_validator("database_max_overflow")
    @classmethod
    def validate_database_max_overflow(cls, value: int) -> int:
        if value < 0:
            raise ValueError("DATABASE_MAX_OVERFLOW must be 0 or greater")
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

    @field_validator("meta_webhook_verify_token")
    @classmethod
    def validate_meta_webhook_verify_token(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError(
                "META_WEBHOOK_VERIFY_TOKEN must be at least 8 characters")
        return normalized

    @field_validator("meta_app_secret")
    @classmethod
    def validate_meta_app_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) < 16:
            raise ValueError("META_APP_SECRET must be at least 16 characters")
        return normalized

    @field_validator("public_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        if not normalized.startswith(("http://", "https://")):
            raise ValueError(
                "PUBLIC_BASE_URL must start with http:// or https://")
        return normalized

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("REDIS_URL cannot be empty")
        return normalized

    @field_validator("celery_default_queue", "celery_webhook_queue")
    @classmethod
    def validate_celery_queue_names(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Celery queue name cannot be empty")
        return normalized

    @field_validator("celery_result_ttl_seconds")
    @classmethod
    def validate_celery_result_ttl_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "CELERY_RESULT_TTL_SECONDS must be greater than 0")
        return value

    @field_validator(
        "queue_retry_max_attempts",
        "queue_retry_base_delay_seconds",
        "queue_idempotency_ttl_seconds",
        "queue_inflight_ttl_seconds",
        "queue_workspace_rate_limit_count",
        "queue_workspace_rate_limit_window_seconds",
        "webhook_dedupe_ttl_seconds",
    )
    @classmethod
    def validate_positive_queue_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Queue numeric settings must be greater than 0")
        return value

    @field_validator("webhook_dispatch_max_retries")
    @classmethod
    def validate_webhook_dispatch_max_retries(cls, value: int) -> int:
        if value < 1:
            raise ValueError("WEBHOOK_DISPATCH_MAX_RETRIES must be at least 1")
        return value

    @field_validator("webhook_ingest_rate_limit_per_ip_per_minute")
    @classmethod
    def validate_webhook_ingest_rate_limit(cls, value: int) -> int:
        if value < 0:
            raise ValueError(
                "WEBHOOK_INGEST_RATE_LIMIT_PER_IP_PER_MINUTE must be 0 or greater"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
