import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.config import settings
from app.services import segmenter, youtube
from app.services.jobs import Job, job_store
from app.services.probe import ProbeError, probe
from app.services.storage import create_job_dir, delete_job_dir, job_dir, parse_job_id
from app.services.upload import MULTIPART_OVERHEAD, UploadMalformed, UploadTooLarge, stream_upload

log = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs")


class JobOut(BaseModel):
    id: str
    status: str
    progress: int
    error: str | None
    duration: float | None
    width: int | None
    height: int | None


class YoutubeIn(BaseModel):
    url: str = Field(max_length=2048)


class ClipOut(BaseModel):
    index: int
    start: float
    end: float
    duration: float
    thumbnail_url: str


def _out(job: Job) -> JobOut:
    return JobOut(
        id=job.id, status=job.status, progress=job.progress, error=job.error,
        duration=job.duration, width=job.width, height=job.height,
    )


def _too_long() -> HTTPException:
    return HTTPException(422, f"Video is longer than the {settings.max_duration_sec // 60}-minute limit.")


def _require_job(job_id: str) -> Job:
    if parse_job_id(job_id) is None:
        raise HTTPException(400, "Invalid job ID.")
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


def _discard(job_id: str) -> None:
    delete_job_dir(job_id)
    job_store.delete(job_id)


@router.post("/upload", status_code=201, response_model=JobOut)
async def upload(request: Request) -> JobOut:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    too_large = HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
    # Cheap early reject when the client declares the size; streaming enforces it regardless.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes + MULTIPART_OVERHEAD:
        raise too_large

    job = job_store.create()
    dest = create_job_dir(job.id) / "source"
    try:
        try:
            await stream_upload(request, dest, max_bytes)
            info = await run_in_threadpool(probe, dest)
        except UploadTooLarge:
            raise too_large
        except (UploadMalformed, ClientDisconnect) as exc:
            log.info("upload %s malformed: %r", job.id, exc)
            raise HTTPException(400, "Send the video as a file in the 'file' field.")
        except ProbeError as exc:
            log.info("upload %s is not a supported video: %s", job.id, exc)
            raise HTTPException(415, "That file isn't a supported video.")
        if info.duration > settings.max_duration_sec:
            raise _too_long()
    except BaseException:
        # Nothing of a rejected upload stays on disk or in the store.
        _discard(job.id)
        raise

    job_store.update(
        job.id, status="ready", progress=100, duration=info.duration,
        width=info.width, height=info.height, video_path=dest, media_type=info.media_type,
    )
    return _out(job_store.get(job.id))


# Sync handler: yt-dlp's metadata call blocks, so FastAPI runs this in its threadpool.
@router.post("/youtube", status_code=202, response_model=JobOut)
def from_youtube(body: YoutubeIn, background: BackgroundTasks) -> JobOut:
    url = youtube.canonical_url(body.url)
    if url is None:
        raise HTTPException(400, "Only YouTube video links are supported.")
    try:
        meta = youtube.fetch_metadata(url)
    except youtube.YoutubeError as exc:
        log.warning("youtube metadata failed for %s: %s", url, exc)
        raise HTTPException(400, "Couldn't read that YouTube video. It may be private or unavailable.")
    if meta.is_live:
        raise HTTPException(422, "Live streams aren't supported.")
    if meta.duration is None:
        raise HTTPException(422, "Couldn't determine the video's length.")
    if meta.duration > settings.max_duration_sec:
        raise _too_long()

    job = job_store.create()
    create_job_dir(job.id)
    background.add_task(youtube.download_job, job_store, job.id, url)
    return _out(job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    return _out(_require_job(job_id))


@router.get("/{job_id}/video")
def get_video(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    # video_path is set once the job is ready and stays valid while segmenting and after.
    if job.video_path is None:
        raise HTTPException(409, "Video isn't ready yet.")
    # FileResponse handles Range requests, so the preview can seek without downloading it all.
    return FileResponse(job.video_path, media_type=job.media_type)


@router.post("/{job_id}/segment", status_code=202, response_model=JobOut)
def segment(job_id: str, background: BackgroundTasks) -> JobOut:
    _require_job(job_id)
    if not job_store.transition(job_id, "ready", status="segmenting", progress=0, error=None):
        raise HTTPException(409, "The video must be ready before finding clips.")
    background.add_task(segmenter.segment_job, job_store, job_id)
    return _out(job_store.get(job_id))


@router.get("/{job_id}/clips", response_model=list[ClipOut])
def list_clips(job_id: str) -> list[ClipOut]:
    job = _require_job(job_id)
    if job.status != "segmented":
        raise HTTPException(409, "Clips aren't ready yet.")
    return [
        ClipOut(
            index=c.index, start=c.start, end=c.end, duration=c.duration,
            thumbnail_url=f"/api/jobs/{job.id}/clips/{c.index}/thumbnail",
        )
        for c in job.clips
    ]


@router.get("/{job_id}/clips/{index}/thumbnail")
def clip_thumbnail(job_id: str, index: str) -> FileResponse:
    job = _require_job(job_id)
    # ASCII digits only; the file name is then built from the int, never from the raw string.
    if not (index.isascii() and index.isdigit()):
        raise HTTPException(400, "Invalid clip index.")
    i = int(index)
    if job.status != "segmented" or i >= len(job.clips):
        raise HTTPException(404, "Clip not found.")
    return FileResponse(job_dir(job.id) / "thumbs" / f"{i}.jpg", media_type="image/jpeg")
