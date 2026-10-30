import subprocess
import uuid

import pytest

from app.core.config import settings
from app.services import youtube
from app.services.storage import job_dir, jobs_root

MB = 1024 * 1024


def job_folders() -> list:
    return list(jobs_root().iterdir()) if jobs_root().is_dir() else []


def upload(client, data: bytes, filename: str = "clip.mp4"):
    return client.post("/api/jobs/upload", files={"file": (filename, data, "video/mp4")})


# --- YouTube URL validation ---------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://evil.example/watch?v=jNQXAC9IVRw",
    "https://youtube.com.evil.example/watch?v=jNQXAC9IVRw",
    "https://youtube.com@evil.example/watch?v=jNQXAC9IVRw",
    "https://user:pass@www.youtube.com/watch?v=jNQXAC9IVRw",
    "https://www.youtube.com:8080/watch?v=jNQXAC9IVRw",
    "http://127.0.0.1/watch?v=jNQXAC9IVRw",
    "http://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd",
    "ftp://youtube.com/watch?v=jNQXAC9IVRw",
    "https://www.youtube.com/playlist?list=PL123",
    "https://www.youtube.com/watch?v=../../etc",
    "not a url",
])
def test_non_youtube_url_rejected(client, monkeypatch, url):
    def must_not_run(_):
        raise AssertionError("yt-dlp must not be called for a rejected URL")
    monkeypatch.setattr(youtube, "fetch_metadata", must_not_run)

    res = client.post("/api/jobs/youtube", json={"url": url})
    assert res.status_code == 400
    assert res.json()["detail"] == "Only YouTube video links are supported."


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "https://youtube.com/watch?v=jNQXAC9IVRw&t=10s",
    "https://m.youtube.com/watch?v=jNQXAC9IVRw",
    "https://youtu.be/jNQXAC9IVRw?si=abc",
    "https://www.youtube.com/shorts/jNQXAC9IVRw",
    "  HTTPS://WWW.YOUTUBE.COM/watch?v=jNQXAC9IVRw  ",
])
def test_youtube_urls_canonicalised(url):
    assert youtube.canonical_url(url) == "https://www.youtube.com/watch?v=jNQXAC9IVRw"


# --- Upload limits and type checks --------------------------------------------------------

def test_oversized_upload_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    res = upload(client, b"\0" * (2 * MB))
    assert res.status_code == 413
    assert job_folders() == []


def test_oversized_upload_rejected_while_streaming(client, monkeypatch):
    """No Content-Length (chunked), so only the streaming counter can catch it."""
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    boundary = "flipclipboundary"
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.mp4"\r\n'
            "Content-Type: video/mp4\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()

    def body():
        yield head
        for _ in range(32):  # 2 MB in 64 KB chunks
            yield b"\0" * (64 * 1024)
        yield tail

    res = client.post(
        "/api/jobs/upload",
        content=body(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert res.status_code == 413
    assert job_folders() == []


@pytest.mark.parametrize("data,filename", [
    (b"just some text, renamed to look like a video", "notes.mp4"),
    (b"\x00\x01\x02" * 1000, "random.mkv"),
    # An HLS playlist would make ffprobe fetch URLs it names, if the format weren't whitelisted.
    (b"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://169.254.169.254/seg.ts\n#EXT-X-ENDLIST\n",
     "playlist.mp4"),
])
def test_non_video_rejected(client, data, filename):
    res = upload(client, data, filename)
    assert res.status_code == 415
    assert res.json()["detail"] == "That file isn't a supported video."
    assert job_folders() == []


def test_image_rejected(client, tmp_path):
    png = tmp_path / "frame.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64",
                    "-frames:v", "1", str(png)], check=True)
    assert upload(client, png.read_bytes(), "frame.mp4").status_code == 415


def test_too_long_video_rejected(client, monkeypatch, make_video):
    monkeypatch.setattr(settings, "max_duration_sec", 1)
    res = upload(client, make_video(seconds=2))
    assert res.status_code == 422
    assert job_folders() == []


def test_valid_upload_is_ready(client, make_video):
    res = upload(client, make_video(seconds=1, size="320x240"))
    assert res.status_code == 201
    job = res.json()
    assert job["status"] == "ready" and job["progress"] == 100
    assert (job["width"], job["height"]) == (320, 240)
    assert job["duration"] == pytest.approx(1, abs=0.2)

    assert client.get(f"/api/jobs/{job['id']}").json() == job
    video = client.get(f"/api/jobs/{job['id']}/video")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"


# --- Job ID validation --------------------------------------------------------------------

@pytest.mark.parametrize("job_id", [
    "not-a-uuid",
    "%2e%2e",  # a literal ".." would be collapsed by the HTTP client before reaching us
    str(uuid.uuid1()),                 # valid UUID, wrong version
    str(uuid.uuid4()).upper(),         # non-canonical spelling
    str(uuid.uuid4()).replace("-", ""),
])
@pytest.mark.parametrize("suffix", ["", "/video"])
def test_bad_job_id_rejected(client, job_id, suffix):
    res = client.get(f"/api/jobs/{job_id}{suffix}")
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid job ID."


def test_path_traversal_job_id_never_served(client):
    res = client.get("/api/jobs/..%2F..%2F..%2Fetc%2Fpasswd")
    assert res.status_code in (400, 404)
    assert "root:" not in res.text


def test_unknown_job_id_not_found(client):
    assert client.get(f"/api/jobs/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize("job_id", ["../etc", "/etc/passwd", str(uuid.uuid1())])
def test_job_dir_refuses_invalid_ids(job_id):
    with pytest.raises(ValueError):
        job_dir(job_id)
