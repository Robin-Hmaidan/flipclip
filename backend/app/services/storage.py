import asyncio
import logging
import shutil
import time
import uuid
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.jobs import JobStore

log = logging.getLogger(__name__)

JOB_TTL_SEC = 2 * 60 * 60
CLEANUP_INTERVAL_SEC = 30 * 60


def parse_job_id(raw: str) -> str | None:
    """Return raw if it is a canonical uuid4 string, else None.

    Only strings that pass this ever become path segments, which rules out traversal.
    """
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, TypeError, AttributeError):
        return None
    if parsed.version != 4 or str(parsed) != raw:
        return None
    return raw


def jobs_root() -> Path:
    return settings.storage_dir / "jobs"


def job_dir(job_id: str) -> Path:
    # Defence in depth: callers validate too, but no unchecked string may reach the filesystem.
    if parse_job_id(job_id) is None:
        raise ValueError("invalid job id")
    return jobs_root() / job_id


def create_job_dir(job_id: str) -> Path:
    folder = job_dir(job_id)
    folder.mkdir(parents=True)
    return folder


def delete_job_dir(job_id: str) -> None:
    shutil.rmtree(job_dir(job_id), ignore_errors=True)


def cleanup_expired(store: JobStore, max_age: float = JOB_TTL_SEC) -> int:
    cutoff = time.time() - max_age
    removed = 0
    root = jobs_root()
    if root.is_dir():
        for folder in root.iterdir():
            # Ignore anything that isn't one of our job folders.
            if not folder.is_dir() or parse_job_id(folder.name) is None:
                continue
            if store.is_active(folder.name) or folder.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(folder, ignore_errors=True)
            store.delete(folder.name)
            removed += 1
    # Failed jobs have no folder left but still hold state.
    for job_id in store.expired_ids(cutoff):
        store.delete(job_id)
    return removed


async def cleanup_loop(store: JobStore) -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
        try:
            removed = await run_in_threadpool(cleanup_expired, store)
            log.info("cleanup removed %d expired job folder(s)", removed)
        except Exception:
            # A failed sweep must not kill the loop; the next one retries.
            log.exception("job cleanup failed")
