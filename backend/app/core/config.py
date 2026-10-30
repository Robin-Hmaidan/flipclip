from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    max_upload_mb: int = 500
    max_duration_sec: int = 3600
    storage_dir: Path = Path("/data")
    # Kept as a plain comma-separated string: a list[str] field would require JSON in the env var.
    allowed_origins: str = "http://localhost:5173"
    # Clip length bounds for segmentation.
    min_clip_sec: float = 15
    max_clip_sec: float = 60
    # Face detection samples per second. Faces move slowly; the crop is interpolated in between.
    track_fps: float = Field(default=5, gt=0, le=30)

    # .env is optional: compose injects variables, and this lets the local venv pick them up too.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _check_clip_bounds(self) -> "Settings":
        # Splitting an over-long clip evenly yields pieces just over max/2; this keeps them >= min.
        if not 0 < self.min_clip_sec <= self.max_clip_sec / 2:
            raise ValueError("MIN_CLIP_SEC must be positive and at most half of MAX_CLIP_SEC")
        return self

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
