from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "LoanFlow_API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/loanflow"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # AWS
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "loanflow-kyc-documents"
    SQS_QUEUE_URL: str = ""

    # External APIs
    CREDIT_BUREAU_URL: str = "https://api.cibil.com/v3"
    CREDIT_BUREAU_API_KEY: str = ""
    CREDIT_BUREAU_TIMEOUT: int = 10

    # Feature flags
    USE_AWS_S3: bool = False
    USE_AWS_SQS: bool = False
    USE_REAL_CREDIT_BUREAU: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

