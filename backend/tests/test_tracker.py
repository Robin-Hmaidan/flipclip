import pytest

from app.services.tracker import (
    Face, Shot, clamp_center, crop_size, pick_subject, plan_track, sample_times, shot_bounds, smooth,
)

W, H = 1920, 1080
CROP_W = crop_size(W, H)[0]  # 608
DZ = 0.10 * CROP_W  # the tracker's default dead zone in pixels


def face(cx, size=200):
    return Face(cx=cx, width=size, height=size)


def shot(start, xs, fps=5):
    """One shot sampled at fps; xs gives the face centre per sample (None = no face)."""
    return Shot(times=[start + i / fps for i in range(len(xs))],
                faces=[[face(x)] if x is not None else [] for x in xs])


def centres(track):
    return [c for _, cs in track.samples for c in cs]


# --- Crop geometry -------------------------------------------------------------------------

@pytest.mark.parametrize("size,expected", [
    ((1920, 1080), (608, 1080)),   # landscape: full height, 9:16 width
    ((1280, 720), (404, 718)),     # 405 isn't even; height follows to stay 9:16
    ((1080, 1920), (1080, 1920)),  # already vertical: whole frame
    ((1000, 1000), (562, 998)),    # square: even-sized 9:16 window
])
def test_crop_size_is_even_and_inside_frame(size, expected):
    crop = crop_size(*size)
    assert crop == expected
    assert crop[0] <= size[0] and crop[1] <= size[1]
    assert crop[0] % 2 == 0 and crop[1] % 2 == 0


def test_crop_clamped_inside_frame():
    assert clamp_center(10, W, CROP_W) == CROP_W / 2
    assert clamp_center(W - 5, W, CROP_W) == W - CROP_W / 2
    assert clamp_center(900, W, CROP_W) == 900

    track = plan_track([shot(0, [5, 5, W - 1, W - 1])], W, CROP_W)
    for c in centres(track):
        assert CROP_W / 2 <= c <= W - CROP_W / 2


# --- Dead zone and smoothing ----------------------------------------------------------------

def test_dead_zone_ignores_small_moves():
    jitter = [900, 900 + DZ * 0.9, 900 - DZ * 0.9, 900 + DZ * 0.5, 900]
    assert smooth(jitter, DZ, 0.35) == [900] * 5


def test_smoothing_approaches_large_moves_gradually():
    positions = smooth([500] + [1300] * 6, DZ, 0.35)
    assert positions[0] == 500
    steps = [b - a for a, b in zip(positions, positions[1:])]
    assert all(s > 0 for s in steps), "moves steadily towards the face"
    assert steps == sorted(steps, reverse=True), "and slows down as it gets close"
    assert positions[1] == pytest.approx(500 + 0.35 * 800)
    assert all(p < 1300 for p in positions), "never overshoots"


def test_first_face_snaps_instead_of_gliding_from_centre():
    assert smooth([None, 1500, 1500], DZ, 0.35) == [None, 1500, 1500]


# --- Cuts -----------------------------------------------------------------------------------

def test_smoothing_resets_at_cuts():
    # The same 200 px move (past the dead zone, but still the same person) is smoothed inside
    # a shot and snapped across a cut.
    within = centres(plan_track([shot(0, [400, 400, 600])], W, CROP_W))
    across = centres(plan_track([shot(0, [400, 400]), shot(0.4, [600])], W, CROP_W))
    assert within[-1] == pytest.approx(400 + 0.35 * 200)
    assert across[-1] == 600


def test_new_shot_snaps_to_a_different_person():
    # A cut to someone on the other side of the frame: no glide across the image.
    track = plan_track([shot(0, [400, 400]), shot(0.4, [1400, 1400])], W, CROP_W)
    assert track.samples[1][1] == [1400, 1400]


def test_interpolates_within_shot_but_not_across_cut():
    track = plan_track([shot(0, [600, 600, 1000]), shot(1.0, [1400])], W, CROP_W)
    a, b = track.samples[0][1][1], track.samples[0][1][2]
    assert track.center_at(0.3) == pytest.approx((a + b) / 2)  # halfway between samples
    assert track.center_at(0.99) == pytest.approx(b)  # holds until the cut...
    assert track.center_at(1.0) == 1400  # ...then jumps with it


def test_shot_bounds_and_samples():
    assert shot_bounds(10, 20, [5, 12, 15.5, 20, 25]) == [(10, 12), (12, 15.5), (15.5, 20)]
    assert sample_times(12, 13, 5) == pytest.approx([12, 12.2, 12.4, 12.6, 12.8])
    assert sample_times(12, 12.05, 5) == [12]  # even a tiny shot gets one sample


# --- No face --------------------------------------------------------------------------------

def test_no_face_ever_uses_frame_centre():
    assert set(centres(plan_track([shot(0, [None] * 4)], W, CROP_W))) == {W / 2}


def test_lost_face_holds_last_position():
    assert centres(plan_track([shot(0, [1500, None, None])], W, CROP_W)) == [1500] * 3


def test_shot_without_face_holds_previous_shot_position():
    track = plan_track([shot(0, [1500, 1500]), shot(0.4, [None, None])], W, CROP_W)
    assert track.samples[1][1] == [1500, 1500]


def test_shot_holds_previous_position_until_its_face_appears():
    track = plan_track([shot(0, [1500]), shot(0.2, [None, None, 400])], W, CROP_W)
    assert track.samples[1][1] == [1500, 1500, 400]


# --- Subject choice -------------------------------------------------------------------------

def test_prefers_persistent_face_over_one_that_flashes_past():
    regular = [[face(500, 120)] for _ in range(10)]
    regular[4] = regular[4] + [face(1500, 250)]  # bigger, but only in one sample
    assert pick_subject(regular, W) == [500] * 10


def test_prefers_larger_of_two_persistent_faces():
    samples = [[face(400, 100), face(1400, 220)] for _ in range(6)]
    assert pick_subject(samples, W) == [1400] * 6


def test_subject_followed_as_it_moves_and_others_ignored():
    samples = [[face(600 + 40 * i, 200), face(1600, 120)] for i in range(8)]
    assert pick_subject(samples, W) == [600 + 40 * i for i in range(8)]


def test_subject_missing_sample_is_none_not_other_person():
    samples = [[face(500, 200), face(1500, 100)], [face(1500, 100)], [face(500, 200), face(1500, 100)]]
    assert pick_subject(samples, W) == [500, None, 500]
