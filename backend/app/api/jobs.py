import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.config import settings
from app.services import editor, exporter, segmenter, youtube
from app.services.jobs import Clip, Job, job_store
from app.services.renderer import render_job_clip, render_queue
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
    original_start: float
    original_end: float
    edited: bool
    thumbnail_url: str


class ClipEditIn(BaseModel):
    # NaN and infinity pass here and are refused by editor.check_range: FastAPI's own 422 would
    # echo the NaN back and fail to encode it as JSON.
    start: float
    end: float


class RenderOut(BaseModel):
    index: int
    status: str  # idle | queued | rendering | done | failed
    progress: int
    error: str | None
    video_url: str | None
    download_url: str | None


class ExportOut(BaseModel):
    status: str  # idle | rendering | zipping | done | failed
    progress: int
    error: str | None
    download_url: str | None


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


def _clip_out(job_id: str, clip: Clip) -> ClipOut:
    return ClipOut(
        index=clip.index, start=clip.start, end=clip.end, duration=clip.duration,
        original_start=clip.original_start, original_end=clip.original_end, edited=clip.edited,
        # The revision changes the URL on every edit, so the browser never shows a cached old frame.
        thumbnail_url=f"/api/jobs/{job_id}/clips/{clip.index}/thumbnail?v={clip.revision}",
    )


@router.get("/{job_id}/clips", response_model=list[ClipOut])
def list_clips(job_id: str) -> list[ClipOut]:
    job = _require_job(job_id)
    if job.status != "segmented":
        raise HTTPException(409, "Clips aren't ready yet.")
    return [_clip_out(job.id, c) for c in job.clips]


def _require_segmented(job_id: str) -> Job:
    job = _require_job(job_id)
    if job.status != "segmented":
        raise HTTPException(409, "Find clips first.")
    return job


def _require_clip(job_id: str, index: str) -> tuple[Job, Clip]:
    job = _require_segmented(job_id)
    # ASCII digits only; file names are then built from the int, never from the raw string.
    if not (index.isascii() and index.isdigit()):
        raise HTTPException(400, "Invalid clip index.")
    i = int(index)
    if i >= len(job.clips):
        raise HTTPException(404, "Clip not found.")
    return job, job.clips[i]


def _render_out(job: Job, index: int) -> RenderOut:
    render = job.renders.get(index)
    status = render.status if render else "idle"
    done = status == "done"
    # Versioned like the thumbnail: an edited clip's new render must not play from cache.
    version = f"?v={job.clips[index].revision}"
    return RenderOut(
        index=index, status=status,
        progress=render.progress if render else 0,
        error=render.error if render else None,
        video_url=f"/api/jobs/{job.id}/clips/{index}/video{version}" if done else None,
        download_url=f"/api/jobs/{job.id}/clips/{index}/download{version}" if done else None,
    )


@router.get("/{job_id}/clips/{index}/thumbnail")
def clip_thumbnail(job_id: str, index: str) -> FileResponse:
    job, clip = _require_clip(job_id, index)
    return FileResponse(job_dir(job.id) / "thumbs" / f"{clip.index}.jpg", media_type="image/jpeg")


# Sync handlers: drawing the new thumbnail runs ffmpeg, so FastAPI runs these in its threadpool.
@router.patch("/{job_id}/clips/{index}", response_model=ClipOut)
def edit_clip(job_id: str, index: str, body: ClipEditIn) -> ClipOut:
    job, clip = _require_clip(job_id, index)
    try:
        moved = editor.edit_clip(job_store, job.id, clip.index, body.start, body.end)
    except editor.InvalidRange as exc:
        raise HTTPException(422, str(exc))
    except editor.ClipBusy as exc:
        raise HTTPException(409, str(exc))
    return _clip_out(job.id, moved)


@router.post("/{job_id}/clips/{index}/reset", response_model=ClipOut)
def reset_clip(job_id: str, index: str) -> ClipOut:
    job, clip = _require_clip(job_id, index)
    try:
        moved = editor.reset_clip(job_store, job.id, clip.index)
    except editor.ClipBusy as exc:
        raise HTTPException(409, str(exc))
    return _clip_out(job.id, moved)


@router.post("/{job_id}/clips/{index}/render", response_model=RenderOut)
def render_clip(job_id: str, index: str, response: Response) -> RenderOut:
    job, clip = _require_clip(job_id, index)
    render, queued = job_store.claim_render(job.id, clip.index)
    if queued:
        render_queue.submit(job.id, render_job_clip, job_store, job.id, clip.index)
    # Already rendered: 200 with the existing file. Otherwise 202, accepted and in progress.
    response.status_code = 200 if render.status == "done" else 202
    return _render_out(job_store.get(job.id), clip.index)


@router.get("/{job_id}/clips/{index}", response_model=RenderOut)
def clip_render_status(job_id: str, index: str) -> RenderOut:
    job, clip = _require_clip(job_id, index)
    return _render_out(job, clip.index)


@router.get("/{job_id}/clips/{index}/video")
def clip_video(job_id: str, index: str) -> FileResponse:
    job, clip = _require_clip(job_id, index)
    render = job.renders.get(clip.index)
    if render is None or render.status != "done":
        raise HTTPException(409, "This clip hasn't been made vertical yet.")
    # FileResponse serves Range requests, so the player can seek.
    return FileResponse(render.path, media_type="video/mp4")


@router.get("/{job_id}/clips/{index}/download")
def clip_download(job_id: str, index: str) -> FileResponse:
    job, clip = _require_clip(job_id, index)
    render = job.renders.get(clip.index)
    if render is None or render.status != "done":
        raise HTTPException(404, "This clip hasn't been made vertical yet.")
    # filename= makes it an attachment, so the browser saves it instead of playing it.
    return FileResponse(render.path, media_type="video/mp4",
                        filename=exporter.clip_filename(clip.index, len(job.clips)))


def _export_out(job: Job) -> ExportOut:
    export = job.export
    return ExportOut(
        status=export.status, progress=exporter.export_progress(job), error=export.error,
        download_url=f"/api/jobs/{job.id}/export/download" if export.status == "done" else None,
    )


@router.post("/{job_id}/export", response_model=ExportOut)
def start_export(job_id: str, response: Response) -> ExportOut:
    job = _require_segmented(job_id)
    exporter.start_export(job_store, render_queue, job.id)
    job = job_store.get(job.id)
    # Already exported: 200 with the existing zip. Otherwise 202, accepted and in progress.
    response.status_code = 200 if job.export.status == "done" else 202
    return _export_out(job)


@router.get("/{job_id}/export", response_model=ExportOut)
def export_status(job_id: str) -> ExportOut:
    return _export_out(_require_segmented(job_id))


@router.get("/{job_id}/export/download")
def export_download(job_id: str) -> FileResponse:
    job = _require_segmented(job_id)
    if job.export.status != "done":
        raise HTTPException(404, "The export isn't ready yet.")
    # FileResponse streams the zip from disk in chunks. Its URL survives an edit while its
    # contents don't, so the browser must check back instead of reusing a cached copy.
    return FileResponse(job.export.path, media_type="application/zip", filename=exporter.ZIP_NAME,
                        headers={"Cache-Control": "no-cache"})
