import logging
import os
import time
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

from app.services.jobs import ACTIVE_RENDERS, Job, JobStore, Render
from app.services.renderer import RenderQueue, render_job_clip
from app.services.storage import job_dir

log = logging.getLogger(__name__)

# Rendering gets this share of the export's progress bar; zipping (a plain copy) the rest.
RENDER_SHARE = 95
CHUNK = 1024 * 1024
# Pause before the zip step re-queues itself behind a render, so it can never spin.
REQUEUE_DELAY_SEC = 0.2
ZIP_NAME = "flipclip_clips.zip"


def clip_filename(index: int, count: int) -> str:
    """Download name for a clip: 1-based and zero-padded, so files sort in clip order."""
    width = max(2, len(str(count)))
    return f"flipclip_clip{index + 1:0{width}d}.mp4"


def export_progress(job: Job) -> int:
    """While rendering, progress comes from the clips the export is waiting on."""
    export = job.export
    if export.status != "rendering":
        return export.progress
    renders = [job.renders.get(i, Render()) for i in export.pending]
    done = sum(100 if r.status == "done" else r.progress for r in renders)
    return done * RENDER_SHARE // (100 * len(renders))


def build_zip(files: Sequence[tuple[Path, str]], dest: Path, on_progress: Callable[[float], None]) -> None:
    """Zip (path, name) pairs into dest, copying in chunks so no clip is held in memory."""
    total = sum(path.stat().st_size for path, _ in files) or 1
    copied = 0
    tmp = dest.with_name(dest.name + ".part")
    try:
        # Stored, not deflated: H.264/AAC is already compressed, so deflate would only burn CPU.
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
            for path, name in files:
                info = zipfile.ZipInfo.from_file(path, name)
                with path.open("rb") as src, zf.open(info, "w") as out:
                    while chunk := src.read(CHUNK):
                        out.write(chunk)
                        copied += len(chunk)
                        on_progress(copied / total)
        # Rename only when complete, so a half-written zip is never served.
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def start_export(store: JobStore, queue: RenderQueue, job_id: str, max_active: int | None = None) -> None:
    """Queue every clip that isn't rendered yet, then the zip step behind them. Raises JobsFull
    (from claim_export) if max_active other jobs are busy."""
    export, started = store.claim_export(job_id, max_active)
    if not started:
        return
    for index in export.pending:
        # Renders the user already queued are in the queue; claim_render won't add them twice.
        _, queued = store.claim_render(job_id, index)
        if queued:
            queue.submit(job_id, render_job_clip, store, job_id, index)
    queue.submit(job_id, zip_job, store, queue, job_id)


def zip_job(store: JobStore, queue: RenderQueue, job_id: str) -> None:
    """Queue worker: zip the rendered clips once every render the export waited on has finished."""
    job = store.get(job_id)
    if job is None:  # cleaned up while waiting in the queue
        return
    renders = {i: job.renders.get(i, Render()) for i in job.export.pending}
    if any(r.status in ACTIVE_RENDERS for r in renders.values()):
        # A render the user started was claimed before this export but submitted after it,
        # so it's still behind us in the queue. Go to the back and wait for it.
        time.sleep(REQUEUE_DELAY_SEC)
        queue.submit(job_id, zip_job, store, queue, job_id)
        return
    failed = [i for i, r in renders.items() if r.status != "done"]
    if failed:
        which = ("clip " if len(failed) == 1 else "clips ") + ", ".join(str(i + 1) for i in failed)
        store.update_export(job_id, status="failed", progress=0,
                            error=f"Couldn't make {which} vertical. Export again to retry.")
        return

    store.update_export(job_id, status="zipping", progress=RENDER_SHARE)
    dest = job_dir(job_id) / "export.zip"
    files = [(job.renders[c.index].path, clip_filename(c.index, len(job.clips))) for c in job.clips]
    try:
        build_zip(files, dest, lambda f: store.update_export(
            job_id, progress=RENDER_SHARE + int(f * (99 - RENDER_SHARE))))
    except Exception:
        log.exception("zip failed for job %s", job_id)
        store.update_export(job_id, status="failed", progress=0,
                            error="Couldn't build the zip. Please try again.")
        return
    log.info("job %s exported %d clip(s)", job_id, len(files))
    store.update_export(job_id, status="done", progress=100, path=dest)
