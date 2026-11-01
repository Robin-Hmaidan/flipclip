import io
import zipfile
from collections import deque

import pytest

from app.services import exporter
from app.services.jobs import Clip, JobStore
from app.services.storage import create_job_dir, job_dir
from tests.helpers import segmented_job, wait_for_render


class InlineQueue:
    """Stands in for RenderQueue: one FIFO per test, run on demand in the calling thread."""

    def __init__(self) -> None:
        self.tasks = deque()

    def submit(self, job_id, fn, *args) -> None:
        self.tasks.append((fn, args))

    def run(self) -> None:
        while self.tasks:
            fn, args = self.tasks.popleft()
            fn(*args)


def fake_render(store, job_id, index):
    """Writes recognisable bytes instead of encoding, so zip contents can be checked exactly."""
    dest = job_dir(job_id) / "renders" / f"{index}.mp4"
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(f"clip {index}".encode() * 1000)
    store.update_render(job_id, index, status="done", progress=100, path=dest)


@pytest.fixture
def store_job(monkeypatch):
    """A fresh store holding one segmented 3-clip job, with rendering faked."""
    monkeypatch.setattr(exporter, "render_job_clip", fake_render)
    store = JobStore()
    job = store.create()
    create_job_dir(job.id)
    store.update(job.id, status="segmented", clips=[Clip(i, i * 20, (i + 1) * 20) for i in range(3)])
    return store, job.id


# --- Service ------------------------------------------------------------------------------

def test_zip_contains_exactly_the_rendered_clips(store_job):
    store, job_id = store_job
    queue = InlineQueue()
    fake_render(store, job_id, 1)  # rendered before the export; the other two aren't
    (job_dir(job_id) / "renders" / "0.part.mp4").write_bytes(b"half-written")  # must not be zipped

    exporter.start_export(store, queue, job_id)
    assert store.get(job_id).export.status == "rendering"
    assert store.get(job_id).export.pending == (0, 2)
    queue.run()

    export = store.get(job_id).export
    assert (export.status, export.progress, export.error) == ("done", 100, None)
    assert export.path == job_dir(job_id) / "export.zip", "zip must live in the job folder"
    with zipfile.ZipFile(export.path) as zf:
        assert zf.namelist() == ["flipclip_clip01.mp4", "flipclip_clip02.mp4", "flipclip_clip03.mp4"]
        for i, name in enumerate(zf.namelist()):
            assert zf.read(name) == f"clip {i}".encode() * 1000
    assert not list(job_dir(job_id).glob("*.part")), "temp zip must be gone"


def test_failed_render_fails_export_and_retry_works(store_job, monkeypatch):
    store, job_id = store_job
    queue = InlineQueue()

    def flaky(s, jid, index):
        if index == 1:
            s.update_render(jid, index, status="failed", error="boom")
        else:
            fake_render(s, jid, index)

    monkeypatch.setattr(exporter, "render_job_clip", flaky)
    exporter.start_export(store, queue, job_id)
    queue.run()
    export = store.get(job_id).export
    assert export.status == "failed" and "clip 2" in export.error
    assert not (job_dir(job_id) / "export.zip").exists()

    # Exporting again re-queues only the clip that failed.
    monkeypatch.setattr(exporter, "render_job_clip", fake_render)
    exporter.start_export(store, queue, job_id)
    assert store.get(job_id).export.pending == (1,)
    queue.run()
    assert store.get(job_id).export.status == "done"


def test_zip_waits_for_render_submitted_after_it(store_job):
    """A user's render claimed before the export but submitted after the zip step."""
    store, job_id = store_job
    queue = InlineQueue()
    for i in (0, 2):
        fake_render(store, job_id, i)
    store.claim_render(job_id, 1)  # claimed (queued) by the render route...
    exporter.start_export(store, queue, job_id)  # ...export starts in between...
    queue.submit(job_id, fake_render, store, job_id, 1)  # ...then the route submits it
    queue.run()
    assert store.get(job_id).export.status == "done"


def test_export_started_once(store_job):
    store, job_id = store_job
    queue = InlineQueue()
    exporter.start_export(store, queue, job_id)
    exporter.start_export(store, queue, job_id)
    # 3 renders + 1 zip step; a second click adds nothing.
    assert len(queue.tasks) == 4


def test_export_progress_follows_its_renders(store_job):
    store, job_id = store_job
    fake_render(store, job_id, 0)
    store.claim_export(job_id)  # pending: clips 1 and 2
    store.update_render(job_id, 1, status="rendering", progress=50)
    # (50 + 0) / 2 clips = 25% of the render share.
    assert exporter.export_progress(store.get(job_id)) == 25 * exporter.RENDER_SHARE // 100
    store.update_render(job_id, 1, status="done", progress=100)
    store.update_render(job_id, 2, status="done", progress=100)
    assert exporter.export_progress(store.get(job_id)) == exporter.RENDER_SHARE


def test_running_export_keeps_job_from_cleanup(store_job):
    store, job_id = store_job
    for i in range(3):
        fake_render(store, job_id, i)
    store.claim_export(job_id)
    assert store.is_active(job_id)
    assert job_id not in store.expired_ids(cutoff=float("inf"))
    store.update_export(job_id, status="done")
    assert not store.is_active(job_id)


@pytest.mark.parametrize("index,count,name", [
    (0, 5, "flipclip_clip01.mp4"),
    (2, 5, "flipclip_clip03.mp4"),
    (9, 100, "flipclip_clip010.mp4"),
    (99, 100, "flipclip_clip100.mp4"),
])
def test_clip_filename(index, count, name):
    assert exporter.clip_filename(index, count) == name


# --- Routes -------------------------------------------------------------------------------

def segmented(client, make_video) -> str:
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    client.post(f"/api/jobs/{job['id']}/segment")
    return job["id"]


@pytest.mark.parametrize("method,path", [
    ("post", "export"), ("get", "export"), ("get", "export/download"), ("get", "clips/0/download"),
])
def test_unsegmented_job_is_409(client, make_video, method, path):
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    res = getattr(client, method)(f"/api/jobs/{job['id']}/{path}")
    assert res.status_code == 409


def test_unrendered_clip_download_is_404(client, make_video):
    job_id = segmented(client, make_video)
    assert client.get(f"/api/jobs/{job_id}/clips/0/download").status_code == 404


def test_export_download_before_export_is_404(client, make_video):
    job_id = segmented(client, make_video)
    assert client.get(f"/api/jobs/{job_id}/export").json() == {
        "status": "idle", "progress": 0, "error": None, "download_url": None,
    }
    assert client.get(f"/api/jobs/{job_id}/export/download").status_code == 404


@pytest.mark.parametrize("index,status", [("abc", 400), ("-1", 400), ("²", 400), ("5", 404)])
def test_download_index_validated(client, make_video, index, status):
    job_id = segmented(client, make_video)
    assert client.get(f"/api/jobs/{job_id}/clips/{index}/download").status_code == status


# --- End to end ---------------------------------------------------------------------------

def test_export_end_to_end(client, monkeypatch, av_video):
    job = segmented_job(client, monkeypatch, av_video)
    clips = client.get(f"/api/jobs/{job['id']}/clips").json()
    base = f"/api/jobs/{job['id']}"

    res = client.post(f"{base}/export")
    assert res.status_code == 202 and res.json()["status"] in ("rendering", "zipping")
    state = wait_for_render(client, f"{base}/export", timeout=240)
    assert state["status"] == "done", state
    assert state["progress"] == 100

    zipped = client.get(state["download_url"])
    assert zipped.status_code == 200 and zipped.headers["content-type"] == "application/zip"
    assert zipped.headers["content-disposition"] == 'attachment; filename="flipclip_clips.zip"'
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as zf:
        assert zf.testzip() is None
        names = zf.namelist()
        assert len(names) == len(clips) == 2
        assert names == ["flipclip_clip01.mp4", "flipclip_clip02.mp4"]
        second = zf.read(names[1])

    # Every clip was rendered by the export, and each downloads on its own under the same name.
    render = client.get(f"{base}/clips/1").json()
    assert render["status"] == "done"
    one = client.get(render["download_url"])
    assert one.status_code == 200 and one.headers["content-type"] == "video/mp4"
    assert one.headers["content-disposition"] == 'attachment; filename="flipclip_clip02.mp4"'
    assert one.content == second

    # Exporting again returns the existing zip.
    again = client.post(f"{base}/export")
    assert again.status_code == 200 and again.json()["download_url"] == state["download_url"]
