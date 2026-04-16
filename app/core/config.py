from functools import lru_cache

from pydantic import AliasChoices, Field
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

    whisper_model_size: str = "large-v3"
    whisper_model_path: str | None = None
    whisper_download_root: str | None = None
    whisper_compute_type: str = "int8"
    whisper_device: str = "cpu"

    lmstudio_base_url: str = Field(
        "http://host.docker.internal:1234/v1",
        validation_alias=AliasChoices("LMSTUDIO_BASE_URL", "LM_STUDIO_BASE_URL"),
    )
    lmstudio_model: str = Field(
        "qwen/qwen2.5-coder-14b",
        validation_alias=AliasChoices("LMSTUDIO_MODEL", "LM_STUDIO_MODEL"),
    )
    lmstudio_embedding_model: str = "nomic-embed-text-v1.5"
    lmstudio_api_key: str | None = Field(
        None,
        validation_alias=AliasChoices("LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY"),
    )
    lmstudio_timeout_seconds: int = Field(
        45,
        validation_alias=AliasChoices(
            "LMSTUDIO_TIMEOUT_SECONDS",
            "LM_STUDIO_TIMEOUT_SECONDS",
        ),
    )
    lmstudio_temperature: float = Field(
        0.0,
        validation_alias=AliasChoices(
            "LMSTUDIO_TEMPERATURE",
            "LM_STUDIO_TEMPERATURE",
        ),
    )
    coqui_tts_model: str = "tts_models/en/ljspeech/tacotron2-DDC"
    tts_backend: str = "auto"
    espeak_voice: str = "en-us"
    espeak_speed: int = 165
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str = "SAz9YHcvj6GT2YYXdXww"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_timeout_seconds: int = 45
    sarvam_api_key: str | None = None
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "shubh"
    sarvam_tts_language_code: str = "en-IN"
    sarvam_tts_sample_rate: int = 24000
    sarvam_tts_pace: float = 1.0
    sarvam_tts_temperature: float = 0.6
    sarvam_tts_timeout_seconds: int = 45

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None

    max_chunk_bytes: int = 768000
    stream_token_ttl_seconds: int = 900
    stream_max_frame_bytes: int = 32768
    max_db_audio_bytes: int = 5_000_000
    password_reset_token_ttl_seconds: int = 900


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
