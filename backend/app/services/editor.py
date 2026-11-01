"""Clip editing: new bounds for one clip, or back to the ones segmentation chose.

An edit drops the clip's render and the job's zip, since neither matches any more, and redraws
its thumbnail. Clips are independent, so an edited clip may overlap its neighbours.
"""
import logging
import math
import os
import uuid

from app.core.config import settings
from app.services import segmenter
from app.services.jobs import ACTIVE_EXPORTS, ACTIVE_RENDERS, Clip, JobStore, Render
from app.services.storage import job_dir

log = logging.getLogger(__name__)


class InvalidRange(ValueError):
    pass


class ClipBusy(Exception):
    pass


BUSY_MESSAGES = {
    "rendering": "This clip is being made vertical. Edit it once that has finished.",
    "exporting": "An export is running. Edit clips once it has finished.",
}


def check_range(start: float, end: float, duration: float, min_sec: float, max_sec: float) -> None:
    """Raise InvalidRange with a message for the user unless [start, end] is a valid clip.

    Bounds are compared in milliseconds, the precision clips are stored in.
    """
    if not (math.isfinite(start) and math.isfinite(end)):
        raise InvalidRange("The start and end must be numbers of seconds.")
    start, end, duration = round(start, 3), round(end, 3), round(duration, 3)
    if start < 0 or end > duration:
        raise InvalidRange(f"The clip must stay within the video (0 to {duration:.1f} s).")
    if start >= end:
        raise InvalidRange("The start must be before the end.")
    length = round(end - start, 3)
    if length < min_sec:
        raise InvalidRange(f"A clip must be at least {min_sec:g} s long (this one is {length:.1f} s).")
    if length > max_sec:
        raise InvalidRange(f"A clip can be at most {max_sec:g} s long (this one is {length:.1f} s).")


def edit_clip(store: JobStore, job_id: str, index: int, start: float, end: float) -> Clip:
    job = store.get(job_id)
    check_range(start, end, job.duration, settings.edit_min_sec, settings.max_clip_sec)
    return _move(store, job_id, index, round(start, 3), round(end, 3))


def reset_clip(store: JobStore, job_id: str, index: int) -> Clip:
    clip = store.get(job_id).clips[index]
    return _move(store, job_id, index, clip.original_start, clip.original_end)


def _move(store: JobStore, job_id: str, index: int, start: float, end: float) -> Clip:
    job = store.get(job_id)
    clip = job.clips[index]
    if (clip.start, clip.end) == (start, end):
        return clip
    # Checked again atomically by move_clip; this only avoids drawing a thumbnail for nothing.
    if job.export.status in ACTIVE_EXPORTS:
        raise ClipBusy(BUSY_MESSAGES["exporting"])
    if job.renders.get(index, Render()).status in ACTIVE_RENDERS:
        raise ClipBusy(BUSY_MESSAGES["rendering"])

    thumbs = job_dir(job_id) / "thumbs"
    # Drawn under a unique name first, so the clip's current thumbnail stays valid until the swap.
    tmp = thumbs / f"{index}.{uuid.uuid4().hex}.jpg"
    try:
        segmenter.make_thumbnail(job.video_path, segmenter.thumbnail_time(start, end), tmp)
        result = store.move_clip(job_id, index, start, end)
        if isinstance(result, str):
            raise ClipBusy(BUSY_MESSAGES[result])
        moved, stale = result
        os.replace(tmp, thumbs / f"{index}.jpg")
    finally:
        tmp.unlink(missing_ok=True)
    for path in stale:
        path.unlink(missing_ok=True)
    log.info("job %s clip %d: %.3f-%.3f -> %.3f-%.3f", job_id, index, clip.start, clip.end, start, end)
    return moved
