from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=('.env', 'env'), extra='ignore')

    app_name: str = 'Horizon Radar'
    environment: str = 'dev'

    database_url: str = 'postgresql+psycopg://horizon:horizon@localhost:5432/horizonradar'
    redis_url: str = 'redis://localhost:6379/0'

    snapshot_dir: str = 'snapshots'
    report_dir: str = 'reports'

    embedding_dimension: int = 384
    embedding_provider: str = 'auto'
    embedding_model: str = 'text-embedding-3-small'

    # Groq — provider AI gratuito (llama-3.3-70b)
    groq_api_key: str | None = None
    # OpenAI — opzionale, solo per embedding se EMBEDDING_PROVIDER=openai
    openai_api_key: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = 'noreply@horizonradar.local'

    app_base_url: str = 'http://localhost:3000'


@lru_cache
def get_settings() -> Settings:
    return Settings()
