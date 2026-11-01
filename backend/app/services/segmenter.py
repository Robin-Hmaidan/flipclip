import logging
import math
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from scenedetect import ContentDetector, SceneManager, open_video

from app.core.config import settings
from app.services.jobs import Clip, JobStore
from app.services.storage import job_dir

log = logging.getLogger(__name__)

# Detection gets most of the progress bar; thumbnails fill the rest.
DETECT_SHARE = 90
# Progress updates per video, regardless of length.
DETECT_STEPS = 50


def plan_clips(
    scenes: Sequence[tuple[float, float]], duration: float, min_sec: float, max_sec: float
) -> list[tuple[float, float]]:
    """Turn (start, end) scenes into contiguous clips covering [0, duration].

    Pure function: no video needed, so the rules are unit-tested with fake scene lists.
    Every clip is at least min_sec (unless the whole video is shorter) and at most max_sec.
    """
    if duration <= 0:
        return []
    # Only scene starts matter: they are the cut points. Ignore anything outside the video.
    cuts = sorted({round(start, 3) for start, _ in scenes if 0 < start < duration})

    # 1. Merge consecutive scenes until each clip reaches min_sec.
    merged: list[tuple[float, float]] = []
    start = 0.0
    for boundary in [*cuts, duration]:
        if boundary - start >= min_sec:
            merged.append((start, boundary))
            start = boundary
    if start < duration:
        # A short tail joins the previous clip; splitting below fixes it if that is now too long.
        if merged:
            merged[-1] = (merged[-1][0], duration)
        else:
            merged.append((0.0, duration))

    # 2. Split anything over max_sec.
    clips = [piece for s, e in merged for piece in _split(s, e, cuts, min_sec, max_sec)]
    return [(round(s, 3), round(e, 3)) for s, e in clips]


def _split(
    start: float, end: float, cuts: list[float], min_sec: float, max_sec: float
) -> list[tuple[float, float]]:
    pieces = []
    while end - start > max_sec:
        # Cuts that keep this piece within [min, max] and leave at least min_sec after it.
        usable = [c for c in cuts if start + min_sec <= c <= start + max_sec and end - c >= min_sec]
        if not usable:
            break
        # The cut nearest the max length gives the fewest, longest clips.
        cut = max(usable)
        pieces.append((start, cut))
        start = cut
    # No usable cut left: split the rest evenly. Pieces are > max/2, which config keeps >= min.
    count = math.ceil((end - start) / max_sec)
    step = (end - start) / count
    bounds = [start + i * step for i in range(count)] + [end]
    pieces.extend(zip(bounds, bounds[1:]))
    return pieces


def detect_scenes(path: Path, on_progress: Callable[[float], None]) -> list[tuple[float, float]]:
    video = open_video(str(path))
    total = video.duration.get_seconds() if video.duration else 0.0
    manager = SceneManager()  # downscales large frames automatically, which keeps 1080p fast
    manager.add_detector(ContentDetector())
    # detect_scenes continues from the current position, so chunks give us progress updates.
    chunk = max(total / DETECT_STEPS, 2.0)
    while manager.detect_scenes(video, duration=chunk) > 0:
        if total:
            on_progress(min(1.0, video.position.get_seconds() / total))
    scenes = manager.get_scene_list(start_in_scene=True)
    return [(s.get_seconds(), e.get_seconds()) for s, e in scenes]


def thumbnail_time(start: float, end: float) -> float:
    # Just after the cut, so the frame isn't a transition blend.
    return start + min(1.0, (end - start) / 2)


def make_thumbnail(src: Path, at: float, dest: Path) -> None:
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-protocol_whitelist", "file",
        "-ss", f"{at:.3f}",  # before -i: fast keyframe seek instead of decoding from the start
        "-i", str(src),
        "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)


def segment_job(store: JobStore, job_id: str) -> None:
    """Background task: detect scenes, plan clips, write thumbnails."""
    job = store.get(job_id)
    thumbs = job_dir(job_id) / "thumbs"
    try:
        scenes = detect_scenes(
            job.video_path, lambda f: store.update(job_id, progress=int(f * DETECT_SHARE))
        )
        ranges = plan_clips(scenes, job.duration, settings.min_clip_sec, settings.max_clip_sec)
        thumbs.mkdir(exist_ok=True)
        clips = []
        for i, (start, end) in enumerate(ranges):
            make_thumbnail(job.video_path, thumbnail_time(start, end), thumbs / f"{i}.jpg")
            clips.append(Clip(i, start, end))
            store.update(job_id, progress=DETECT_SHARE + (100 - DETECT_SHARE) * (i + 1) // len(ranges) - 1)
    except Exception:
        log.exception("segmentation failed for job %s", job_id)
        shutil.rmtree(thumbs, ignore_errors=True)
        # Back to ready: the video is still fine, so the user can retry.
        store.update(job_id, status="ready", progress=100,
                     error="Couldn't find clips in this video. Please try again.")
        return
    log.info("job %s: %d scenes -> %d clips", job_id, len(scenes), len(clips))
    cuts = sorted(start for start, _ in scenes if start > 0)
    store.update(job_id, status="segmented", progress=100, clips=clips, cuts=cuts, error=None)
