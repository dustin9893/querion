from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # -- Postgres --
    DATABASE_URL: str = (
        "postgresql+asyncpg://querion:querion_secret@localhost:5432/querion"
    )

    # -- Redis --
    REDIS_URL: str = "redis://localhost:6379/0"

    # -- MinIO --
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin_secret"
    MINIO_BUCKET: str = "querion-docs"
    MINIO_USE_SSL: bool = False

    # -- App --
    APP_NAME: str = "Querion API"
    DEBUG: bool = True

    # -- Auth / JWT --
    JWT_SECRET: str = "querion-dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- Super Admin Seed --
    SUPER_ADMIN_EMAIL: str = "admin@querion.io"
    SUPER_ADMIN_PASSWORD: str = "admin123"
    SUPER_ADMIN_NAME: str = "Super Admin"

    # -- Encryption --
    ENCRYPTION_KEY: str = ""

    # -- Workflow runtime hardening --
    # code_execute runs exec() with a restricted builtins dict — NOT a sandbox. Off by default.
    ENABLE_CODE_EXECUTE: bool = False
    # http_request node: refuse loopback / private / link-local targets unless explicitly allowed.
    HTTP_REQUEST_ALLOW_PRIVATE: bool = False

    # -- Public / embedded chat rate limits (Redis fixed window) --
    PUBLIC_RATE_LIMIT_PER_IP: int = 20          # messages per (assistant, IP) per window
    PUBLIC_RATE_WINDOW_SEC: int = 300
    PUBLIC_RATE_LIMIT_PER_APP_DAY: int = 2000   # messages per assistant per day
    STAFF_RATE_LIMIT_PER_EMPLOYEE: int = 60     # per (assistant, employee) per window

    # -- Agent tools --
    ENABLE_MCP_STDIO: bool = False          # MCP over stdio launches a local process: opt-in only
    # Internal hosts tools may call despite the SSRF guard, e.g. "core-api.msb.local:8443,localhost:8099".
    # A narrow allow-list is the realistic shape for a bank: tools do call internal systems.
    TOOL_INTERNAL_ALLOWLIST: str = ""
    AGENT_MAX_TOOL_ROUNDS: int = 4

    # -- PII masking engine: presidio (Microsoft Presidio + spaCy en_core_web_sm) | regex | off --
    PII_ENGINE: str = "presidio"

    # -- Web app origin (used in printed embed snippets) --
    WEB_PUBLIC_URL: str = "http://localhost:3000"
    # Browser origins allowed to call the API cross-origin (comma-separated). In production the
    # reverse proxy serves web and API on one origin, so this is only a safety net.
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = {"env_file": [".env", "../../.env"], "extra": "ignore"}


settings = Settings()
