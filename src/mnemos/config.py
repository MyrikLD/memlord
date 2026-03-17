from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MNEMOS_", env_file=".env", extra="ignore"
    )

    db_url: str = "postgresql+asyncpg://postgres:postgres@localhost/mnemos"
    db_echo: bool = False
    model_dir: Path = Path("/app/src/mnemos/onnx")
    host: str = "0.0.0.0"
    port: int = 8000
    base_url: str | None = None
    rrf_k: int = 60
    default_limit: int = 10
    sim_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    oauth_jwt_secret: str | None = None
    password: str | None = None


settings = Settings()
