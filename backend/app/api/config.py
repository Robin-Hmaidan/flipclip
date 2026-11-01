from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


# Lets the UI reject an oversized file before uploading it, instead of after minutes of upload,
# and explain an out-of-range clip edit before sending it.
@router.get("/config")
def public_config() -> dict:
    return {
        "max_upload_mb": settings.max_upload_mb, "max_duration_sec": settings.max_duration_sec,
        "edit_min_sec": settings.edit_min_sec, "max_clip_sec": settings.max_clip_sec,
        "sample_available": settings.sample_video.is_file(),
    }
