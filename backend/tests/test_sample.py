import pytest

from app.core.config import settings
from app.services.probe import probe
from app.services.storage import jobs_root

MB = 1024 * 1024


def job_folders() -> list:
    return list(jobs_root().iterdir()) if jobs_root().is_dir() else []


@pytest.fixture
def small_sample(tmp_path, monkeypatch, make_video):
    """A tiny stand-in for the bundled file, so these tests don't copy 20 MB each."""
    path = tmp_path / "sample.mp4"
    path.write_bytes(make_video(seconds=2, size="320x240"))
    monkeypatch.setattr(settings, "sample_video", path)
    return path


def test_bundled_sample_is_a_short_small_video():
    """The README promises a 1-3 minute sample under 30 MB; the build must ship it."""
    path = settings.sample_video
    assert path.is_file()
    assert path.stat().st_size < 30 * MB
    info = probe(path)
    assert 60 <= info.duration <= 180
    assert info.width > info.height  # horizontal source, so there is something to make vertical


def test_sample_starts_a_ready_job(client, small_sample):
    res = client.post("/api/jobs/sample")
    assert res.status_code == 201
    job = res.json()
    assert job["status"] == "ready" and job["progress"] == 100
    assert (job["width"], job["height"]) == (320, 240)
    assert job["duration"] == pytest.approx(2, abs=0.2)

    video = client.get(f"/api/jobs/{job['id']}/video")
    assert video.status_code == 200 and video.content == small_sample.read_bytes()


def test_sample_job_is_a_normal_job(client, small_sample):
    """It segments like any upload, and its folder is its own copy."""
    job = client.post("/api/jobs/sample").json()
    assert client.post(f"/api/jobs/{job['id']}/segment").status_code == 202
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "segmented"

    other = client.post("/api/jobs/sample").json()
    assert other["id"] != job["id"]
    assert len(job_folders()) == 2
    assert small_sample.is_file()  # never moved or consumed by a job


def test_missing_sample_is_404_and_leaves_nothing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sample_video", tmp_path / "missing.mp4")
    res = client.post("/api/jobs/sample")
    assert res.status_code == 404
    assert res.json()["detail"] == "The sample video isn't available."
    assert job_folders() == []


def test_unreadable_sample_is_500_and_leaves_nothing(client, tmp_path, monkeypatch):
    broken = tmp_path / "sample.mp4"
    broken.write_bytes(b"not a video")
    monkeypatch.setattr(settings, "sample_video", broken)
    res = client.post("/api/jobs/sample")
    assert res.status_code == 500
    assert res.json()["detail"] == "The sample video couldn't be read."
    assert job_folders() == []


def test_config_says_whether_the_sample_exists(client, tmp_path, monkeypatch, small_sample):
    assert client.get("/api/config").json()["sample_available"] is True
    monkeypatch.setattr(settings, "sample_video", tmp_path / "missing.mp4")
    assert client.get("/api/config").json()["sample_available"] is False
