import pytest
import yt_dlp

from app.services import youtube
from app.services.jobs import job_store
from app.services.storage import job_dir

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: records the options and runs a scripted download."""

    seen_opts: list[dict] = []
    script = None  # callable(opts, ydl) -> info dict

    def __init__(self, opts):
        self.opts = opts
        FakeYDL.seen_opts.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True, process=True):
        return FakeYDL.script(self.opts)


@pytest.fixture
def fake_ydl(monkeypatch):
    FakeYDL.seen_opts = []
    FakeYDL.script = lambda opts: {"duration": 60, "is_live": False}
    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_download_retries_stalled_connections(fake_ydl):
    def stop(opts):
        raise yt_dlp.utils.DownloadError("stop")

    fake_ydl.script = stop
    job = job_store.create()
    youtube.download_job(job_store, job.id, URL)

    opts = fake_ydl.seen_opts[0]
    assert opts["retries"] == 10
    assert opts["fragment_retries"] == 10
    assert opts["socket_timeout"] == 60
    # Resume the .part file on retry rather than starting the stream over.
    assert opts["continuedl"] is True
    assert set(opts["retry_sleep_functions"]) == {"http", "fragment"}


def test_metadata_uses_the_longer_socket_timeout(fake_ydl):
    youtube.fetch_metadata(URL)
    assert fake_ydl.seen_opts[0]["socket_timeout"] == 60


def test_retry_backoff_grows_then_caps():
    # yt-dlp calls it as sleep_func(n=count - 1), so the keyword must be n.
    assert [youtube.retry_backoff(n=n) for n in range(6)] == [1, 2, 4, 8, 10, 10]


def test_progress_survives_a_resumed_retry(fake_ydl, make_video):
    job = job_store.create()
    folder = job_dir(job.id)
    data = make_video(1)
    seen = []

    def script(opts):
        hook = opts["progress_hooks"][0]
        info = {"requested_formats": [{}]}

        def report(**d):
            hook({"info_dict": info, **d})
            seen.append(job_store.get(job.id).progress)

        report(status="downloading", downloaded_bytes=40, total_bytes=100)
        # Connection stalls, yt-dlp retries and resumes from byte 40 rather than 0.
        report(status="downloading", downloaded_bytes=70, total_bytes=100)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "source.mp4"
        path.write_bytes(data)
        report(status="finished", filename=str(path))
        return {"requested_downloads": [{"filepath": str(path)}]}

    fake_ydl.script = script
    youtube.download_job(job_store, job.id, URL)

    assert seen == [38, 66, 95]
    done = job_store.get(job.id)
    assert done.status == "ready"
    assert done.progress == 100


def test_failure_after_retries_is_reported(fake_ydl):
    job = job_store.create()

    def script(opts):
        job_dir(job.id).mkdir(parents=True, exist_ok=True)
        (job_dir(job.id) / "source.f137.mp4.part").write_bytes(b"partial")
        raise yt_dlp.utils.DownloadError("Connection refused. Giving up after 10 retries")

    fake_ydl.script = script
    youtube.download_job(job_store, job.id, URL)

    failed = job_store.get(job.id)
    assert failed.status == "failed"
    assert failed.error == "Download failed. Try another video."
    assert not job_dir(job.id).exists()
