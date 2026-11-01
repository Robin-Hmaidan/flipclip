import os
import subprocess
import tempfile

# Settings are read at import time, so storage must point somewhere disposable before app import.
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="flipclip-test-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    # A fresh storage dir per test, so job folders one test leaves behind can't fail another's checks.
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")


@pytest.fixture
def client():
    # Context manager runs the lifespan, same as a real server start.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_video(tmp_path):
    """Generate a real, tiny H.264 mp4 so tests exercise ffprobe on genuine input."""
    def _make(seconds: float = 1, size: str = "320x240"):
        out = tmp_path / f"clip-{seconds}s.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10",
             "-t", str(seconds), "-pix_fmt", "yuv420p", str(out)],
            check=True,
        )
        return out.read_bytes()
    return _make


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
