from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/transactions_db"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    # "celery" is the local Compose default; use "inline" where no worker is deployed.
    PROCESSING_MODE: str = "celery"
    GEMINI_API_KEY: str = ""
    JWT_SECRET_KEY: str = "local-development-only-change-before-deploy"
    JWT_ACCESS_TOKEN_MINUTES: int = 720
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
