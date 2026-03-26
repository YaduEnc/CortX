from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SecondMind API"
    environment: str = "development"
    api_v1_prefix: str = "/v1"
    log_level: str = "INFO"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 1440
    pair_token_ttl_seconds: int = 120
    admin_bootstrap_key: str

    database_url: str
    redis_url: str

    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "secondmind-audio"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    whisper_model_size: str = "small"
    whisper_compute_type: str = "int8"
    whisper_device: str = "cpu"

    max_chunk_bytes: int = 256000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
