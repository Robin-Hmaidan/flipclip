import logging
import os
import subprocess
import tempfile
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings
from app.services import tracker
from app.services.jobs import JobStore
from app.services.storage import job_dir

log = logging.getLogger(__name__)

OUT_W, OUT_H = 1080, 1920
# Tracking gets this share of the progress bar; encoding the rest.
TRACK_SHARE = 25


class RenderError(Exception):
    pass


def render_clip(src: Path, start: float, end: float, cuts: Sequence[float], dest: Path,
                on_progress: Callable[[int], None]) -> None:
    track = tracker.track_clip(src, start, end, cuts, settings.track_fps,
                               lambda f: on_progress(int(f * TRACK_SHARE)))

    cap = cv2.VideoCapture(str(src))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps <= 0 or frame_w <= 0:
            raise RenderError(f"bad stream info: fps={fps} size={frame_w}x{frame_h}")
        crop_w, crop_h = tracker.crop_size(frame_w, frame_h)
        top = (frame_h - crop_h) // 2

        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        ok, frame = cap.read()
        if not ok:
            raise RenderError(f"no frame at {start}s")
        # Audio starts at the first frame we actually got, not the requested time, so a
        # slightly imprecise seek can't put sound and picture out of sync.
        first_t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        total = max(1, round((end - first_t) * fps))
        tmp = dest.with_name(dest.stem + ".part.mp4")
        cmd = [
            "ffmpeg", "-v", "error", "-y",
            # Input 0: our cropped frames, raw, on stdin.
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{crop_w}x{crop_h}",
            "-framerate", f"{fps:.6f}", "-i", "pipe:0",
            # Input 1: the source, for its audio over exactly the same span.
            "-protocol_whitelist", "file",
            "-ss", f"{first_t:.6f}", "-t", f"{total / fps:.6f}", "-i", str(src),
            "-map", "0:v:0", "-map", "1:a:0?",  # "?": sources without audio still render
            "-vf", f"scale={OUT_W}:{OUT_H}:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",  # index up front so the browser can seek right away
            str(tmp),
        ]
        # stderr to a file: a full pipe would block ffmpeg while we block writing frames.
        with tempfile.TemporaryFile() as errlog:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errlog)
            try:
                for n in range(total):
                    if not ok:
                        break
                    t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                    x = int(round(track.center_at(t) - crop_w / 2))
                    x = min(max(x, 0), frame_w - crop_w)
                    proc.stdin.write(np.ascontiguousarray(frame[top:top + crop_h, x:x + crop_w]).tobytes())
                    if n % 15 == 0:
                        on_progress(TRACK_SHARE + (99 - TRACK_SHARE) * n // total)
                    ok, frame = cap.read()
                proc.stdin.close()
                code = proc.wait(timeout=600)
            except BrokenPipeError:
                code = proc.wait(timeout=60)  # ffmpeg died; its log says why
            except BaseException:
                proc.kill()
                proc.wait()
                raise
            if code != 0:
                errlog.seek(0)
                raise RenderError(f"ffmpeg exited {code}: {errlog.read().decode(errors='replace')[-2000:]}")
    finally:
        cap.release()
    # Rename only when complete, so a half-written file is never served.
    os.replace(tmp, dest)


def render_job_clip(store: JobStore, job_id: str, index: int) -> None:
    """Queue worker: render one clip and record the outcome on the job."""
    job = store.get(job_id)
    if job is None:  # cleaned up while waiting in the queue
        return
    clip = job.clips[index]
    dest = job_dir(job_id) / "renders" / f"{index}.mp4"
    store.update_render(job_id, index, status="rendering", progress=0)
    try:
        dest.parent.mkdir(exist_ok=True)
        render_clip(job.video_path, clip.start, clip.end, job.cuts, dest,
                    lambda p: store.update_render(job_id, index, progress=p))
    except Exception:
        log.exception("render failed for job %s clip %d", job_id, index)
        store.update_render(job_id, index, status="failed", progress=0,
                            error="Couldn't make this clip vertical. Please try again.")
        return
    log.info("job %s clip %d rendered", job_id, index)
    store.update_render(job_id, index, status="done", progress=100, path=dest)


class RenderQueue:
    """One worker thread per job: a job's clips render one at a time, in order, so a user
    clicking every clip can't start a dozen encoders at once."""

    def __init__(self) -> None:
        self._workers: dict[str, ThreadPoolExecutor] = {}
        self._lock = threading.Lock()

    def submit(self, job_id: str, fn: Callable, *args) -> None:
        with self._lock:
            worker = self._workers.get(job_id)
            if worker is None:
                worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"render-{job_id[:8]}")
                self._workers[job_id] = worker
        worker.submit(fn, *args)

    def discard(self, job_id: str) -> None:
        with self._lock:
            worker = self._workers.pop(job_id, None)
        if worker:
            worker.shutdown(wait=False, cancel_futures=True)


render_queue = RenderQueue()
