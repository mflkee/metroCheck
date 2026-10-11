"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://mkair:mkair_secret@localhost:5432/mkair"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # External APIs
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    ARSHIN_BEARER_TOKEN: str = ""
    ARSHIN_BASE_URL: str = "https://fgis.gost.ru/fundmetrology/eapi"

    # Token sync via shared file (Synology Drive / Dropbox / etc.)
    # Path where token JSON file appears after sync from Zonov's PC
    TOKEN_FILE_PATH: str = "/shared/tokens/jwt-arshin-token.json"

    # Security
    FASTAPI_API_KEY: str = "CHANGE_ME_API_KEY"
    SECRET_KEY: str = "metrocheck-jwt-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Admin auth
    ADMIN_USERNAME: str = "admin-metrochek"
    ADMIN_PASSWORD: str = ""  # auto-generate if empty

    # Single sign-on (Authentik OIDC). Disabled until explicitly enabled in the env.
    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = "https://auth.mkair-it.ru/application/o/metrocheck/"
    OIDC_CLIENT_ID: str = "metrocheck"
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = "https://metrocheck.mkair-it.ru/api/v1/auth/oidc/callback"
    OIDC_SCOPES: str = "openid email profile groups"
    OIDC_TRANSACTION_TTL_SECONDS: int = 600
    OIDC_HTTP_TIMEOUT_SECONDS: float = 10.0
    OIDC_COOKIE_SECURE: bool = True
    FRONTEND_APP_URL: str = "https://metrocheck.mkair-it.ru"

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Protocols path
    METROCHECK_PROTOCOLS_PATH: str = "/protocols"

    # AI Models fallback chain
    AI_MODELS: list[str] = [
        "google/gemma-4-31b-it:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "openai/gpt-oss-120b:free",
        "openai/gpt-4o-mini",
    ]
    AI_MAX_TOKENS: int = 1000
    AI_TEMPERATURE: float = 0.1

    # Email notifications
    SMTP_HOST: str = "mail.mkair-it.ru"
    SMTP_PORT: int = 465
    SMTP_USER: str = "robot@mkair-it.ru"
    SMTP_PASS: str = ""
    FROM_EMAIL: str = "no-reply@mkair-it.ru"
    FROM_NAME: str = "metroCheck Robot"
    REPORT_EMAIL: str = ""  # Comma-separated list of report recipients

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
