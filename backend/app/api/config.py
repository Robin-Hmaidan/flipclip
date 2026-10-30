from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


# Lets the UI reject an oversized file before uploading it, instead of after minutes of upload.
@router.get("/config")
def public_config() -> dict:
    return {"max_upload_mb": settings.max_upload_mb, "max_duration_sec": settings.max_duration_sec}
