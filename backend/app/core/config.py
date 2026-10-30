from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Limits are enforced by the upload/download steps later; declared now so env wiring is settled.
    max_upload_mb: int = 500
    max_duration_sec: int = 3600
    storage_dir: Path = Path("/data")
    # Kept as a plain comma-separated string: a list[str] field would require JSON in the env var.
    allowed_origins: str = "http://localhost:5173"

    # .env is optional: compose injects variables, and this lets the local venv pick them up too.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
