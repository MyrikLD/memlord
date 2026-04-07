from pathlib import Path

from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMLORD_", env_file=".env", extra="ignore")

    db_url: str = "postgresql+asyncpg://postgres:postgres@localhost/memlord"
    db_echo: bool = False

    model_dir: Path = Path("src/memlord/onnx")
    host: str = "0.0.0.0"
    port: int = 8000
    base_url: str = "http://localhost:8000"
    rrf_k: int = 60
    default_limit: int = 10
    sim_threshold: float = Field(0.25, ge=0.0, le=1.0)
    dedup_threshold: float = Field(0.85, ge=0.0, le=1.0)
    oauth_jwt_secret: str = "memlord-dev-secret-please-change"
    stdio_user_id: int | None = Field(None, description="use for stdio mode")

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: EmailStr | None = None
    smtp_tls: bool = True


settings = Settings()
