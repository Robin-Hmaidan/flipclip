import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services import editor, renderer
from app.services.jobs import job_store
from app.services.storage import job_dir
from app.services.tracker import shot_bounds
from tests.helpers import segmented_job, wait_for_render
from tests.test_render import ffprobe


# --- Validation ---------------------------------------------------------------------------

@pytest.mark.parametrize("start,end,message", [
    (10, 11.5, "at least 3 s long (this one is 1.5 s)"),  # too short
    (10, 70.001, "at most 60 s long (this one is 60.0 s)"),  # too long by a millisecond
    (-0.5, 10, "within the video"),  # before the start
    (90, 100.5, "within the video"),  # past the end
    (20, 20, "before the end"),
    (25, 20, "before the end"),
])
def test_invalid_ranges(start, end, message):
    with pytest.raises(editor.InvalidRange, match=re.escape(message)):
        editor.check_range(start, end, duration=100.0, min_sec=3, max_sec=60)


@pytest.mark.parametrize("start,end", [(0, 3), (40, 100), (0.0004, 3.0004), (97, 100.0004)])
def test_valid_ranges_including_the_limits(start, end):
    # Exactly min, exactly max, and sub-millisecond noise at the video's edges are accepted.
    editor.check_range(start, end, duration=100.0, min_sec=3, max_sec=60)


@pytest.mark.parametrize("value", [0, -1, 61])
def test_edit_min_must_fit_the_clip_limits(value):
    with pytest.raises(ValidationError, match="EDIT_MIN_SEC"):
        Settings(edit_min_sec=value, max_clip_sec=60)


# --- Routes -------------------------------------------------------------------------------

@pytest.fixture
def job(client, monkeypatch, av_video):
    """The 6 s test video as two 3 s clips (max 4 s), editable down to 1 s."""
    monkeypatch.setattr(settings, "edit_min_sec", 1)
    return segmented_job(client, monkeypatch, av_video)["id"]


def fake_done_render(job_id, index):
    path = job_dir(job_id) / "renders" / f"{index}.mp4"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"rendered")
    job_store.update_render(job_id, index, status="done", progress=100, path=path)
    return path


def fake_done_export(job_id):
    path = job_dir(job_id) / "export.zip"
    path.write_bytes(b"zip")
    job_store.update_export(job_id, status="done", progress=100, path=path)
    return path


def test_clips_list_original_bounds(client, job):
    clips = client.get(f"/api/jobs/{job}/clips").json()
    assert clips[1] | {"thumbnail_url": None} == {
        "index": 1, "start": 3.0, "end": 6.0, "duration": 3.0,
        "original_start": 3.0, "original_end": 6.0, "edited": False, "thumbnail_url": None,
    }


def test_edit_extends_into_neighbour_and_invalidates(client, job):
    base = f"/api/jobs/{job}"
    before = client.get(f"{base}/clips").json()[1]
    old_thumb = client.get(before["thumbnail_url"]).content
    kept = fake_done_render(job, 0)
    stale = fake_done_render(job, 1)
    zipped = fake_done_export(job)

    # Starts inside clip 0: overlapping a neighbour is allowed.
    res = client.patch(f"{base}/clips/1", json={"start": 1.5, "end": 5.0})
    assert res.status_code == 200, res.json()
    clip = res.json()
    assert (clip["start"], clip["end"], clip["duration"]) == (1.5, 5.0, 3.5)
    assert (clip["original_start"], clip["original_end"], clip["edited"]) == (3.0, 6.0, True)
    assert client.get(f"{base}/clips").json()[1] == clip
    assert client.get(f"{base}/clips").json()[0]["edited"] is False

    # This clip's render and the zip are gone; the other clip's render stays.
    assert not stale.exists() and not zipped.exists()
    assert kept.exists() and client.get(f"{base}/clips/0").json()["status"] == "done"
    assert client.get(f"{base}/clips/1").json()["status"] == "idle"
    assert client.get(f"{base}/export").json()["status"] == "idle"

    # A new thumbnail at a new URL, so the browser can't show the cached one.
    assert clip["thumbnail_url"] != before["thumbnail_url"]
    new_thumb = client.get(clip["thumbnail_url"])
    assert new_thumb.status_code == 200 and new_thumb.content[:2] == b"\xff\xd8"
    assert new_thumb.content != old_thumb
    assert sorted(p.name for p in (job_dir(job) / "thumbs").iterdir()) == ["0.jpg", "1.jpg"]


def test_reset_restores_original_bounds_and_invalidates(client, job):
    base = f"/api/jobs/{job}/clips/0"
    client.patch(base, json={"start": 0.5, "end": 2.0})
    stale = fake_done_render(job, 0)
    zipped = fake_done_export(job)

    res = client.post(f"{base}/reset")
    assert res.status_code == 200
    clip = res.json()
    assert (clip["start"], clip["end"], clip["edited"]) == (0.0, 3.0, False)
    assert not stale.exists() and not zipped.exists()
    assert client.get(base).json()["status"] == "idle"


def test_unchanged_bounds_keep_the_render(client, job):
    base = f"/api/jobs/{job}/clips/1"
    path = fake_done_render(job, 1)
    assert client.patch(base, json={"start": 3, "end": 6}).json()["edited"] is False
    assert client.post(f"{base}/reset").status_code == 200  # never edited: nothing to reset
    assert path.exists() and client.get(base).json()["status"] == "done"


@pytest.mark.parametrize("body", [
    {"start": 1, "end": 1.5},  # too short (min 1 s)
    {"start": 0, "end": 4.5},  # too long (max 4 s)
    {"start": -1, "end": 2},  # before the video
    {"start": 3, "end": 6.5},  # past the end (6 s)
    {"start": 4, "end": 3},  # backwards
    {"start": "a", "end": 3},
    {"start": 1},
])
def test_invalid_edit_is_422_and_changes_nothing(client, job, body):
    base = f"/api/jobs/{job}/clips/1"
    path = fake_done_render(job, 1)
    res = client.patch(base, json=body)
    assert res.status_code == 422
    clip = client.get(f"/api/jobs/{job}/clips").json()[1]
    assert (clip["start"], clip["end"], clip["edited"]) == (3.0, 6.0, False)
    assert path.exists()


def test_validation_message_is_readable(client, job):
    res = client.patch(f"/api/jobs/{job}/clips/1", json={"start": 1, "end": 1.5})
    assert res.json()["detail"] == "A clip must be at least 1 s long (this one is 0.5 s)."


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_is_422(client, job, raw):
    # Python's JSON parser accepts these; the error must still be a clean 422, not a 500.
    res = client.patch(f"/api/jobs/{job}/clips/1", content=f'{{"start": 1, "end": {raw}}}',
                       headers={"Content-Type": "application/json"})
    assert res.status_code == 422 and res.json()["detail"] == "The start and end must be numbers of seconds."


@pytest.mark.parametrize("status", ["queued", "rendering"])
def test_edit_while_rendering_is_409(client, job, status):
    job_store.update_render(job, 1, status=status)
    base = f"/api/jobs/{job}/clips/1"
    res = client.patch(base, json={"start": 2, "end": 5})
    assert res.status_code == 409 and "being made vertical" in res.json()["detail"]
    # Another clip can still be edited.
    assert client.patch(f"/api/jobs/{job}/clips/0", json={"start": 0, "end": 2}).status_code == 200


@pytest.mark.parametrize("status", ["rendering", "zipping"])
def test_edit_or_reset_during_export_is_409(client, job, status):
    client.patch(f"/api/jobs/{job}/clips/0", json={"start": 0, "end": 2})
    job_store.update_export(job, status=status)
    assert client.patch(f"/api/jobs/{job}/clips/1", json={"start": 2, "end": 5}).status_code == 409
    res = client.post(f"/api/jobs/{job}/clips/0/reset")
    assert res.status_code == 409 and "export is running" in res.json()["detail"]
    assert client.get(f"/api/jobs/{job}/clips").json()[0]["end"] == 2.0
    assert not list((job_dir(job) / "thumbs").glob("*.*.jpg")), "temp thumbnail must be gone"


@pytest.mark.parametrize("index,status", [("abc", 400), ("-1", 400), ("²", 400), ("5", 404)])
def test_edit_index_validated(client, job, index, status):
    assert client.patch(f"/api/jobs/{job}/clips/{index}", json={"start": 0, "end": 2}).status_code == status
    assert client.post(f"/api/jobs/{job}/clips/{index}/reset").status_code == status


def test_edit_requires_segmented_job(client, make_video):
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    assert client.patch(f"/api/jobs/{job['id']}/clips/0", json={"start": 0, "end": 1}).status_code == 409
    assert client.post(f"/api/jobs/{job['id']}/clips/0/reset").status_code == 409


# --- Rendering an edited clip -------------------------------------------------------------

def test_render_uses_the_stored_cuts_inside_the_new_range(client, job, monkeypatch):
    # The test video has no cuts; pretend segmentation found two.
    job_store.update(job, cuts=[2.0, 4.5])
    client.patch(f"/api/jobs/{job}/clips/1", json={"start": 1.5, "end": 5.0})
    seen = {}

    def fake_render_clip(src, start, end, cuts, dest, on_progress):
        seen["shots"] = shot_bounds(start, end, cuts)
        dest.write_bytes(b"rendered")

    monkeypatch.setattr(renderer, "render_clip", fake_render_clip)
    renderer.render_job_clip(job_store, job, 1)
    # Both cuts now fall inside the clip; before the edit (3-6 s) only 4.5 did.
    assert seen["shots"] == [(1.5, 2.0), (2.0, 4.5), (4.5, 5.0)]


def test_edited_clip_renders_the_edited_range(client, job, tmp_path):
    base = f"/api/jobs/{job}/clips/1"
    assert client.patch(base, json={"start": 1.5, "end": 5.0}).status_code == 200
    assert client.post(f"{base}/render").status_code == 202
    state = wait_for_render(client, base)
    assert state["status"] == "done", state

    info = ffprobe(client.get(state["video_url"]).content, tmp_path)
    assert float(info["format"]["duration"]) == pytest.approx(3.5, abs=0.1)
    for stream in info["streams"]:
        assert float(stream["duration"]) == pytest.approx(3.5, abs=0.1), stream["codec_type"]
