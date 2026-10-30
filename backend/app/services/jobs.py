import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

ACTIVE_STATUSES = ("queued", "downloading", "segmenting")


@dataclass(frozen=True)
class Clip:
    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


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
            return replace(job) if job else None

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

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def is_active(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.status in ACTIVE_STATUSES)

    def expired_ids(self, cutoff: float) -> list[str]:
        with self._lock:
            return [
                j.id
                for j in self._jobs.values()
                if j.created_at < cutoff and j.status not in ACTIVE_STATUSES
            ]


job_store = JobStore()
