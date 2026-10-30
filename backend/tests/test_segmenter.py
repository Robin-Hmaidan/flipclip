import random
import subprocess

import pytest

from app.core.config import settings
from app.services.jobs import job_store
from app.services.segmenter import _split, plan_clips

MIN, MAX = 15, 60


def scenes_from_lengths(*lengths):
    """[4, 4, 4] -> [(0, 4), (4, 8), (8, 12)], the shape PySceneDetect returns."""
    scenes, t = [], 0.0
    for length in lengths:
        scenes.append((t, t + length))
        t += length
    return scenes, t


ROUNDING = 1e-3  # plan_clips rounds times to milliseconds


def assert_valid(clips, duration, min_sec=MIN, max_sec=MAX):
    assert clips[0][0] == 0 and clips[-1][1] == pytest.approx(duration, abs=ROUNDING)
    for (_, end), (start, _) in zip(clips, clips[1:]):
        assert end == start, "clips must be contiguous"
    for start, end in clips:
        assert end - start <= max_sec + ROUNDING
        if duration >= min_sec:
            assert end - start >= min_sec - ROUNDING


# --- Merge -------------------------------------------------------------------------------

def test_short_scenes_merge_until_min():
    scenes, duration = scenes_from_lengths(*[4] * 10)  # 40 s of 4 s scenes
    # 0-16 reaches 15 s; 16-32 too; the 8 s tail joins the last clip.
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 16), (16, 40)]


def test_scene_exactly_min_stands_alone():
    scenes, duration = scenes_from_lengths(15, 15, 15)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 15), (15, 30), (30, 45)]


def test_short_tail_joins_previous_clip():
    scenes, duration = scenes_from_lengths(20, 20, 5)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 20), (20, 45)]


# --- Split -------------------------------------------------------------------------------

def test_long_scene_splits_evenly():
    scenes, duration = scenes_from_lengths(150)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 50), (50, 100), (100, 150)]


def test_clip_exactly_max_is_not_split():
    scenes, duration = scenes_from_lengths(60)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 60)]


def test_clip_just_over_max_splits():
    scenes, duration = scenes_from_lengths(60.5)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 30.25), (30.25, 60.5)]


def test_short_scene_before_long_one_splits_evenly():
    # The only cut (5 s) would leave a 5 s clip, below MIN, so it can't be used.
    scenes, duration = scenes_from_lengths(5, 100)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 52.5), (52.5, 105)]


def test_split_prefers_cut_nearest_max_that_keeps_both_sides_valid():
    # 70 is too far (> MAX); 45 is the latest usable cut.
    assert _split(0, 100, [10, 30, 45, 70], MIN, MAX) == [(0, 45), (45, 100)]


def test_split_skips_cut_that_leaves_short_remainder():
    # 55 would leave only 10 s after it, so fall back to an even split.
    assert _split(0, 65, [55], MIN, MAX) == [(0, 32.5), (32.5, 65)]


# --- Edges -------------------------------------------------------------------------------

def test_no_scenes_detected_gives_one_clip():
    assert plan_clips([], 40, MIN, MAX) == [(0, 40)]


def test_video_shorter_than_min_is_one_clip():
    scenes, duration = scenes_from_lengths(3, 4, 2)
    assert plan_clips(scenes, duration, MIN, MAX) == [(0, 9)]


def test_zero_duration_gives_no_clips():
    assert plan_clips([], 0, MIN, MAX) == []


def test_unsorted_duplicate_and_out_of_range_scenes_are_ignored():
    scenes = [(30, 45), (0, 15), (15, 30), (15.0001, 30), (-5, 0), (45, 60), (99, 120)]
    assert plan_clips(scenes, 45, MIN, MAX) == [(0, 15), (15, 30), (30, 45)]


def test_random_scene_lists_always_produce_valid_clips():
    rng = random.Random(1234)
    for _ in range(500):
        lengths = [rng.choice([rng.uniform(0.5, 5), rng.uniform(5, 30), rng.uniform(30, 200)])
                   for _ in range(rng.randint(1, 40))]
        scenes, duration = scenes_from_lengths(*lengths)
        assert_valid(plan_clips(scenes, duration, MIN, MAX), duration)


# --- Integration: real video, real PySceneDetect, real thumbnails -------------------------

@pytest.fixture
def scene_video(tmp_path):
    """31 s of solid colours: cuts at 2, 4, 7 and 27 s."""
    colours = [("red", 2), ("blue", 2), ("green", 3), ("yellow", 20), ("magenta", 4)]
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for colour, seconds in colours:
        cmd += ["-f", "lavfi", "-i", f"color=c={colour}:s=160x120:r=10:d={seconds}"]
    inputs = "".join(f"[{i}:v]" for i in range(len(colours)))
    out = tmp_path / "scenes.mp4"
    cmd += ["-filter_complex", f"{inputs}concat=n={len(colours)}:v=1:a=0", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    return out.read_bytes()


def test_segment_real_video(client, monkeypatch, scene_video):
    monkeypatch.setattr(settings, "min_clip_sec", 5)
    monkeypatch.setattr(settings, "max_clip_sec", 12)
    job = client.post("/api/jobs/upload", files={"file": ("s.mp4", scene_video, "video/mp4")}).json()

    # TestClient runs background tasks before returning, so segmentation is done here.
    res = client.post(f"/api/jobs/{job['id']}/segment")
    assert res.status_code == 202 and res.json()["status"] == "segmenting"
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "segmented"

    clips = client.get(f"/api/jobs/{job['id']}/clips").json()
    # Merge: 0-7 (2+2+3 s). 7-27 plus the 4 s tail = 24 s > 12 s, no usable cut -> two 12 s halves.
    expected = [(0, 7), (7, 19), (19, 31)]
    assert [c["index"] for c in clips] == [0, 1, 2]
    for clip, (start, end) in zip(clips, expected):
        assert clip["start"] == pytest.approx(start, abs=0.25)
        assert clip["end"] == pytest.approx(end, abs=0.25)
        assert clip["duration"] == pytest.approx(clip["end"] - clip["start"], abs=0.01)

    thumb = client.get(clips[1]["thumbnail_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert thumb.content[:2] == b"\xff\xd8"  # JPEG magic bytes

    # Already segmented: a second run is refused.
    assert client.post(f"/api/jobs/{job['id']}/segment").status_code == 409


@pytest.mark.parametrize("index,status", [("abc", 400), ("-1", 400), ("1.5", 400), ("%31", 404),
                                          ("²", 400), ("3", 404), ("999999999999", 404)])
def test_thumbnail_index_validated(client, make_video, index, status):
    job = client.post("/api/jobs/upload", files={"file": ("c.mp4", make_video(2), "video/mp4")}).json()
    client.post(f"/api/jobs/{job['id']}/segment")
    assert client.get(f"/api/jobs/{job['id']}/clips/{index}/thumbnail").status_code == status


def test_segment_requires_ready_job(client):
    job = job_store.create()  # still "queued"
    assert client.post(f"/api/jobs/{job.id}/segment").status_code == 409
    assert client.get(f"/api/jobs/{job.id}/clips").status_code == 409
