from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url_async: str = "postgresql+asyncpg://fintrack:fintrack@localhost:5432/fintrack"
    database_url_sync: str = "postgresql+psycopg://fintrack:fintrack@localhost:5432/fintrack"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # Stub auth
    dev_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    dev_user_email: str = "dev@fintrack.local"

    # External data sources
    alpha_vantage_api_key: str = ""

    # Pillar 4 client selection (mock until real credentials exist)
    reddit_client_impl: str = "mock"
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "fintrack/0.1"

    research_agent_impl: str = "mock"
    anthropic_api_key: str = ""

    # Web push (Checkpoint 6)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:dev@fintrack.local"

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
