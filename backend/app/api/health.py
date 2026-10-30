import subprocess
from functools import cache

from fastapi import APIRouter

router = APIRouter()


# The binary doesn't change while the process runs, so probe it once.
@cache
def ffmpeg_version() -> str | None:
    try:
        # Argument list, never shell=True: later steps pass user-derived paths to ffmpeg the same way.
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # First line is "ffmpeg version <version> Copyright ...".
    parts = result.stdout.split(maxsplit=3)
    return parts[2] if len(parts) > 2 else None


@router.get("/health")
def health() -> dict:
    version = ffmpeg_version()
    # The app is useless without ffmpeg, so report that instead of a blanket "ok".
    return {"status": "ok" if version else "degraded", "ffmpeg_version": version}
