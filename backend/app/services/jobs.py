import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

ACTIVE_STATUSES = ("queued", "downloading", "segmenting")
ACTIVE_RENDERS = ("queued", "rendering")
ACTIVE_EXPORTS = ("rendering", "zipping")


@dataclass(frozen=True)
class Clip:
    index: int
    start: float
    end: float
    # Bounds from segmentation, kept so an edit can be reset. Default to start/end.
    original_start: float | None = None
    original_end: float | None = None
    # Bumped on every edit, so URLs of the clip's thumbnail and render change with it.
    revision: int = 0

    def __post_init__(self) -> None:
        if self.original_start is None:
            object.__setattr__(self, "original_start", self.start)
        if self.original_end is None:
            object.__setattr__(self, "original_end", self.end)

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    @property
    def edited(self) -> bool:
        return (self.start, self.end) != (self.original_start, self.original_end)


@dataclass(frozen=True)
class Render:
    status: str = "idle"  # idle | queued | rendering | done | failed
    progress: int = 0
    error: str | None = None
    path: Path | None = None


@dataclass(frozen=True)
class Export:
    status: str = "idle"  # idle | rendering | zipping | done | failed
    progress: int = 0
    error: str | None = None
    # Clips this export had to render; its progress during "rendering" is theirs.
    pending: tuple[int, ...] = ()
    path: Path | None = None


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued | downloading | ready | failed | segmenting | segmented
    progress: int = 0
    error: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    # Server-side only; never serialized to the client.
    video_path: Path | None = None
    media_type: str | None = None
    clips: list[Clip] | None = None
    # Scene cut times from segmentation; the tracker resets its smoothing at each one.
    cuts: list[float] = field(default_factory=list)
    renders: dict[int, Render] = field(default_factory=dict)
    export: Export = field(default_factory=Export)
    created_at: float = field(default_factory=time.time)


class JobStore:
    """In-memory job state. Routes only use this interface, so it can be swapped for Redis."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # Downloads update jobs from worker threads while requests read them.
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(id=str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.id] = job
        return replace(job)

    def get(self, job_id: str) -> Job | None:
        # Return a copy so callers can't mutate shared state, matching how Redis would behave.
        with self._lock:
            job = self._jobs.get(job_id)
            # renders is the one mutable container, so copy it too.
            return replace(job, renders=dict(job.renders)) if job else None

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for key, value in fields.items():
                    setattr(job, key, value)

    def transition(self, job_id: str, expected: str, **fields) -> bool:
        """Apply fields only if the job is in the expected status. Atomic, so two requests can't
        both start the same work (Redis would do this with WATCH/MULTI)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != expected:
                return False
            for key, value in fields.items():
                setattr(job, key, value)
            return True

    def claim_render(self, job_id: str, index: int) -> tuple[Render, bool]:
        """Queue a render unless one is queued, running or done. Returns (render, newly_queued)."""
        with self._lock:
            job = self._jobs[job_id]
            current = job.renders.get(index, Render())
            if current.status in (*ACTIVE_RENDERS, "done"):
                return current, False
            job.renders[index] = Render(status="queued")
            return job.renders[index], True

    def update_render(self, job_id: str, index: int, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.renders[index] = replace(job.renders.get(index, Render()), **fields)

    def claim_export(self, job_id: str) -> tuple[Export, bool]:
        """Start an export unless one is running or done. Returns (export, newly_started).
        pending is every clip not rendered yet, including renders already queued or running."""
        with self._lock:
            job = self._jobs[job_id]
            if job.export.status in (*ACTIVE_EXPORTS, "done"):
                return job.export, False
            pending = tuple(
                c.index for c in job.clips
                if job.renders.get(c.index, Render()).status != "done"
            )
            job.export = Export(status="rendering" if pending else "zipping", pending=pending)
            return job.export, True

    def update_export(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.export = replace(job.export, **fields)

    def move_clip(self, job_id: str, index: int, start: float, end: float
                  ) -> tuple[Clip, list[Path]] | Literal["rendering", "exporting"]:
        """Give a clip new bounds, unless its render is queued or running or an export is running
        (returns which). Its render and the export no longer match, so both go back to idle; the
        files they leave behind are returned for the caller to delete. Same bounds: no change."""
        with self._lock:
            job = self._jobs[job_id]
            clip = job.clips[index]
            if (clip.start, clip.end) == (start, end):
                return clip, []
            if job.export.status in ACTIVE_EXPORTS:
                return "exporting"
            render = job.renders.get(index, Render())
            if render.status in ACTIVE_RENDERS:
                return "rendering"
            # Copy the list: get() hands out shallow copies that share it.
            job.clips = list(job.clips)
            job.clips[index] = replace(clip, start=start, end=end, revision=clip.revision + 1)
            stale = [p for p in (job.renders.pop(index, Render()).path, job.export.path) if p]
            job.export = Export()
            return job.clips[index], stale

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    @staticmethod
    def _busy(job: Job) -> bool:
        return (
            job.status in ACTIVE_STATUSES
            or job.export.status in ACTIVE_EXPORTS
            or any(r.status in ACTIVE_RENDERS for r in job.renders.values())
        )

    def is_active(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job) and self._busy(job)

    def expired_ids(self, cutoff: float) -> list[str]:
        with self._lock:
            return [j.id for j in self._jobs.values() if j.created_at < cutoff and not self._busy(j)]


job_store = JobStore()
