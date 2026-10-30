import json
import subprocess
import time

import pytest

from app.core.config import settings


def ffprobe(data: bytes, tmp_path) -> dict:
    path = tmp_path / "out.mp4"
    path.write_bytes(data)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,duration:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


@pytest.fixture
def av_video(tmp_path):
    """6 s, 1280x720, 25 fps, with a sine-wave audio track."""
    out = tmp_path / "av.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
         "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
        check=True,
    )
    return out.read_bytes()


def segmented_job(client, monkeypatch, video: bytes) -> dict:
    # 6 s with no cuts and max 4 s -> two even 3 s clips, so clip 1 starts mid-video.
    monkeypatch.setattr(settings, "min_clip_sec", 1)
    monkeypatch.setattr(settings, "max_clip_sec", 4)
    job = client.post("/api/jobs/upload", files={"file": ("av.mp4", video, "video/mp4")}).json()
    client.post(f"/api/jobs/{job['id']}/segment")
    return job


def wait_for_render(client, url: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(url).json()
        if state["status"] in ("done", "failed"):
            return state
        time.sleep(0.25)
    raise AssertionError(f"render did not finish in {timeout}s: {state}")


def test_render_vertical_clip(client, monkeypatch, av_video, tmp_path):
    job = segmented_job(client, monkeypatch, av_video)
    clips = client.get(f"/api/jobs/{job['id']}/clips").json()
    assert len(clips) == 2
    clip = clips[1]
    base = f"/api/jobs/{job['id']}/clips/1"

    assert client.get(base).json()["status"] == "idle"
    res = client.post(f"{base}/render")
    assert res.status_code == 202 and res.json()["status"] in ("queued", "rendering")

    state = wait_for_render(client, base)
    assert state["status"] == "done", state
    assert state["progress"] == 100

    video = client.get(state["video_url"])
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    info = ffprobe(video.content, tmp_path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert (v["codec_name"], v["width"], v["height"]) == ("h264", 1080, 1920)
    assert a and a[0]["codec_name"] == "aac", "original audio must be kept"
    assert float(info["format"]["duration"]) == pytest.approx(clip["duration"], abs=0.1)
    assert float(v["duration"]) == pytest.approx(clip["duration"], abs=0.1)
    assert float(a[0]["duration"]) == pytest.approx(clip["duration"], abs=0.1)

    # Range requests work, so the player can seek.
    partial = client.get(state["video_url"], headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206 and len(partial.content) == 100

    # Rendering again returns the existing file instead of re-encoding.
    again = client.post(f"{base}/render")
    assert again.status_code == 200 and again.json()["video_url"] == state["video_url"]


def test_render_requires_segmented_job(client, make_video):
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    base = f"/api/jobs/{job['id']}/clips/0"
    assert client.post(f"{base}/render").status_code == 409
    assert client.get(base).status_code == 409
    assert client.get(f"{base}/video").status_code == 409


@pytest.mark.parametrize("index,status", [("abc", 400), ("-1", 400), ("²", 400), ("5", 404)])
def test_render_index_validated(client, make_video, index, status):
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    client.post(f"/api/jobs/{job['id']}/segment")
    assert client.post(f"/api/jobs/{job['id']}/clips/{index}/render").status_code == status


def test_video_before_render_is_409(client, make_video):
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    client.post(f"/api/jobs/{job['id']}/segment")
    assert client.get(f"/api/jobs/{job['id']}/clips/0/video").status_code == 409
