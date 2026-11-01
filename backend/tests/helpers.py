import time

from app.core.config import settings


def segmented_job(client, monkeypatch, video: bytes) -> dict:
    # 6 s with no cuts and max 4 s -> two even 3 s clips, so clip 1 starts mid-video.
    monkeypatch.setattr(settings, "min_clip_sec", 1)
    monkeypatch.setattr(settings, "max_clip_sec", 4)
    job = client.post("/api/jobs/upload", files={"file": ("av.mp4", video, "video/mp4")}).json()
    client.post(f"/api/jobs/{job['id']}/segment")
    return job


def wait_for_render(client, url: str, timeout: float = 120) -> dict:
    """Poll a render or export status URL until it is done or failed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(url).json()
        if state["status"] in ("done", "failed"):
            return state
        time.sleep(0.25)
    raise AssertionError(f"did not finish in {timeout}s: {state}")
