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
    TOKEN_FILE_PATH: str = "/shared/tokens/arshin-token.json"
    
    # Legacy: Netbird settings (deprecated, kept for compatibility)
    ZONOV_IP: str = "100.89.96.31"
    TOKEN_AGENT_KEY: str = "mkair-token-agent-key"

    # Security
    FASTAPI_API_KEY: str = "mkair-secret-key"
    SECRET_KEY: str = "mkair-jwt-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Protocols path
    MKAIR_PROTOCOLS_PATH: str = "/protocols"

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
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    FROM_EMAIL: str = "mkair-reports@example.com"
    REPORT_EMAIL: str = ""  # Where to send reports

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
