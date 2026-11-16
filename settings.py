from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://shipments_app:change-me@localhost:5432/shipments_erp"
    app_env: str = "development"
    app_secret_key: str = "development-only-change-me"
    cors_origins: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
settings = Settings()
