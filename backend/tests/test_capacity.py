import threading

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services import youtube
from app.services.jobs import Clip, JobsFull, JobStore, job_store
from app.services.renderer import render_queue
from app.services.storage import create_job_dir, jobs_root

BUSY = "Too many videos are being worked on right now (the limit is 1 at a time). Please try again in a minute."


@pytest.fixture
def one_slot(monkeypatch):
    monkeypatch.setattr(settings, "max_active_jobs", 1)
    # Renders stay queued (busy) instead of running, so no test here encodes video.
    submitted = []
    monkeypatch.setattr(render_queue, "submit", lambda job_id, fn, *args: submitted.append((job_id, fn)))
    return submitted


def busy_job() -> str:
    """A job that holds a slot: queued, as while it uploads or downloads."""
    return job_store.create().id


def segmented(clips: int = 2) -> str:
    """An idle job with clips found; it holds no slot until something renders."""
    job = job_store.create()
    create_job_dir(job.id)
    job_store.update(job.id, status="segmented", clips=[Clip(i, i * 20, (i + 1) * 20) for i in range(clips)])
    return job.id


def assert_busy(res) -> None:
    assert res.status_code == 429
    assert res.json()["detail"] == BUSY
    assert res.headers["retry-after"] == "60"


def job_folders() -> list:
    return list(jobs_root().iterdir()) if jobs_root().is_dir() else []


# --- Config -------------------------------------------------------------------------------

def test_default_is_three():
    assert Settings().max_active_jobs == 3


def test_limit_must_be_positive(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_JOBS", "0")
    with pytest.raises(ValidationError):
        Settings()


# --- Starting a job -----------------------------------------------------------------------

def test_sample_refused_when_full(client, one_slot):
    busy_job()
    assert_busy(client.post("/api/jobs/sample"))
    assert job_folders() == []


def test_upload_refused_when_full_and_leaves_nothing(client, one_slot, make_video):
    busy_job()
    res = client.post("/api/jobs/upload", files={"file": ("a.mp4", make_video(), "video/mp4")})
    assert_busy(res)
    assert job_folders() == []


def test_youtube_refused_when_full(client, one_slot, monkeypatch):
    monkeypatch.setattr(youtube, "fetch_metadata", lambda url: youtube.Metadata(duration=30, is_live=False))
    downloads = []
    monkeypatch.setattr(youtube, "download_job", lambda store, job_id, url: downloads.append(job_id))

    # The first link takes the only slot: it stays queued because the download is faked.
    first = client.post("/api/jobs/youtube", json={"url": "https://youtu.be/jNQXAC9IVRw"})
    assert first.status_code == 202
    assert_busy(client.post("/api/jobs/youtube", json={"url": "https://youtu.be/jNQXAC9IVRw"}))
    assert downloads == [first.json()["id"]]


def test_slot_frees_when_a_job_settles(client, one_slot):
    job_id = busy_job()
    assert_busy(client.post("/api/jobs/sample"))
    # Ready (or failed) jobs aren't working, so they don't count.
    job_store.update(job_id, status="failed", error="x")
    assert client.post("/api/jobs/sample").status_code == 201


def test_idle_jobs_dont_count(client, monkeypatch):
    monkeypatch.setattr(settings, "max_active_jobs", 2)
    for _ in range(4):
        assert client.post("/api/jobs/sample").status_code == 201


# --- Starting work on an existing job -----------------------------------------------------

def test_find_clips_refused_when_full(client, one_slot):
    job = client.post("/api/jobs/sample").json()
    busy_job()
    assert_busy(client.post(f"/api/jobs/{job['id']}/segment"))
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "ready"


def test_render_refused_when_full(client, one_slot):
    job_id = segmented()
    busy_job()
    assert_busy(client.post(f"/api/jobs/{job_id}/clips/0/render"))
    assert client.get(f"/api/jobs/{job_id}/clips/0").json()["status"] == "idle"
    assert one_slot == []


def test_export_refused_when_full(client, one_slot):
    job_id = segmented()
    busy_job()
    assert_busy(client.post(f"/api/jobs/{job_id}/export"))
    assert client.get(f"/api/jobs/{job_id}/export").json()["status"] == "idle"
    assert one_slot == []


def test_busy_job_can_queue_more_work(client, one_slot):
    # Its renders share one worker, so they add no concurrency: the job keeps its single slot.
    job_id = segmented()
    assert client.post(f"/api/jobs/{job_id}/clips/0/render").status_code == 202
    assert client.post(f"/api/jobs/{job_id}/clips/1/render").status_code == 202
    assert client.post(f"/api/jobs/{job_id}/export").status_code == 202
    # Meanwhile nobody else can start.
    assert_busy(client.post("/api/jobs/sample"))


def test_finished_render_is_served_even_when_full(client, one_slot):
    job_id = segmented()
    job_store.update_render(job_id, 0, status="done", progress=100)
    busy_job()
    assert client.post(f"/api/jobs/{job_id}/clips/0/render").status_code == 200


# --- Store --------------------------------------------------------------------------------

def test_concurrent_creates_never_exceed_the_limit():
    store = JobStore()
    barrier = threading.Barrier(20)
    results = []

    def attempt():
        barrier.wait()
        try:
            store.create(max_active=3)
            results.append("ok")
        except JobsFull:
            results.append("full")

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 3


def test_store_without_limit_never_refuses():
    store = JobStore()
    for _ in range(10):
        store.create()
