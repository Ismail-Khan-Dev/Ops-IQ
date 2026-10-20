from enum import StrEnum
from typing import Optional

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App Settings
    ENV: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    PROJECT_NAME: str = "ecommerce-ops-agent"
    LOG_LEVEL: str = "INFO"

    # Authentication
    API_KEY: Optional[SecretStr] = None
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8000"]

    # API Keys
    GOOGLE_API_KEY: Optional[SecretStr] = None
    DEEPSEEK_API_KEY: Optional[SecretStr] = None
    DEEPSEEK_BASE_URL: str = ""
    LLM_MODEL: str = "gemini-2.0-flash"

    SHOPIFY_API_KEY: Optional[SecretStr] = None
    SHOPIFY_PASSWORD: Optional[SecretStr] = None
    SHOPIFY_STORE_URL: Optional[str] = None
    SHOPIFY_API_VERSION: str = "2024-01"

    # Shopify OAuth (new)
    SHOPIFY_CLIENT_ID: Optional[str] = None
    SHOPIFY_CLIENT_SECRET: Optional[SecretStr] = None
    SHOPIFY_APP_URL: Optional[str] = None
    SHOPIFY_SHOP_DOMAIN: Optional[str] = None
    SHOPIFY_ACCESS_TOKEN: Optional[SecretStr] = None

    # DB & Cache
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ecommerce_ops"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Connection Pooling
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    # Task Queue
    TASK_QUEUE_WORKERS: int = 2
    TASK_QUEUE_MAX_SIZE: int = 100

    # Safety Thresholds
    GLOBAL_PO_LIMIT: float = 1000.0
    GLOBAL_PRICE_CHANGE_LIMIT_PERCENT: float = 20.0
    SHADOW_MODE: bool = True
    # Auto-approval: decisions with confidence >= AUTO_APPROVE_CONFIDENCE_SCORE
    # are auto-approved when shadow_mode is off. Agent autonomy graduation
    # (streak >= 50) is handled by update_agent_streak in the pipeline runner.
    AUTO_APPROVE_CONFIDENCE_SCORE: float = 0.95

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # Trusted proxies for X-Forwarded-For header parsing.
    # In production, set to the CIDR/range of your load balancer/proxy
    # (e.g. "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" for private LBs).
    # Requests from untrusted IPs will NOT have X-Forwarded-For honored,
    # preventing IP spoofing for rate-limit / per-IP connection limits.
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)

    # Notification
    SLACK_BOT_TOKEN: Optional[SecretStr] = None
    SLACK_CHANNEL: Optional[str] = None
    # Full incoming-webhook URL (https://hooks.slack.com/services/...) —
    # preferred over SLACK_BOT_TOKEN for workspace apps.
    # When set, it is used first and the bot-token path is skipped.
    SLACK_WEBHOOK_URL: Optional[str] = None
    RESEND_API_KEY: Optional[SecretStr] = None
    NOTIFY_EMAIL: Optional[str] = None
    NOTIFY_FROM_EMAIL: Optional[str] = None

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.ENV == Environment.PRODUCTION:
            if not self.API_KEY:
                raise ValueError("API_KEY must be set in production")
            if not self.GOOGLE_API_KEY and not self.DEEPSEEK_API_KEY:
                raise ValueError(
                    "Either GOOGLE_API_KEY or DEEPSEEK_API_KEY must be set in production"
                )
            if "postgresql" not in self.DATABASE_URL:
                raise ValueError("DATABASE_URL must use PostgreSQL in production")
            if not self.REDIS_URL or not self.REDIS_URL.startswith("redis"):
                raise ValueError("REDIS_URL must be a valid redis:// URL in production")

            # Shopify integration: if enabled in production, require OAuth credentials
            # so the system fails closed instead of running with partial config.
            shopify_enabled = bool(self.SHOPIFY_SHOP_DOMAIN or self.SHOPIFY_STORE_URL)
            if shopify_enabled:
                missing = []
                if not self.SHOPIFY_CLIENT_ID:
                    missing.append("SHOPIFY_CLIENT_ID")
                if not self.SHOPIFY_CLIENT_SECRET:
                    missing.append("SHOPIFY_CLIENT_SECRET")
                if not self.SHOPIFY_ACCESS_TOKEN and not self.SHOPIFY_APP_URL:
                    missing.append("SHOPIFY_ACCESS_TOKEN or SHOPIFY_APP_URL")
                if missing:
                    raise ValueError(
                        "Shopify is enabled in production but missing required config: "
                        + ", ".join(missing)
                    )
        return self


settings = Settings()
