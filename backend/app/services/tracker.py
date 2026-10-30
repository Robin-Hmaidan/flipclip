"""Face tracking for the 9:16 crop.

The math (subject choice, dead zone + smoothing, interpolation, clamping) is pure and unit-tested
with fake detections. track_clip feeds it real MediaPipe detections from sampled frames.
"""
import bisect
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

FACE_MODEL = Path("/opt/models/blaze_face_full_range.tflite")
# Detection runs on a downscaled copy: the model's input is 192 px wide, so more is wasted work.
DETECT_WIDTH = 640
MIN_CONFIDENCE = 0.5

# The face may drift this share of the crop width before the camera follows.
DEAD_ZONE = 0.10
# Each sample, the camera covers this share of the distance to the face.
SMOOTHING = 0.35
# Faces closer than this share of the frame width in consecutive samples count as one person.
MATCH_DISTANCE = 0.12


@dataclass(frozen=True)
class Face:
    cx: float  # centre x in source pixels
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class Shot:
    times: list[float]  # absolute sample times in seconds, starting at the shot's first frame
    faces: list[list[Face]]  # detections per sample


@dataclass
class Track:
    """Crop centre over time. Interpolates within a shot, never across a cut."""

    shot_starts: list[float]
    samples: list[tuple[list[float], list[float]]]  # per shot: (times, centres)

    def center_at(self, t: float) -> float:
        i = max(0, bisect.bisect_right(self.shot_starts, t) - 1)
        times, centres = self.samples[i]
        return float(np.interp(t, times, centres))


def crop_size(frame_w: int, frame_h: int) -> tuple[int, int]:
    """Largest 9:16 window inside the frame, even-sized as yuv420p needs."""
    crop_w = int(round(min(frame_w, frame_h * 9 / 16))) // 2 * 2
    crop_h = int(round(min(frame_h, crop_w * 16 / 9))) // 2 * 2
    return crop_w, crop_h


def clamp_center(cx: float, frame_w: float, crop_w: float) -> float:
    return min(max(cx, crop_w / 2), frame_w - crop_w / 2)


def shot_bounds(start: float, end: float, cuts: Sequence[float]) -> list[tuple[float, float]]:
    edges = [start, *sorted(c for c in cuts if start < c < end), end]
    return list(zip(edges, edges[1:]))


def sample_times(shot_start: float, shot_end: float, fps: float) -> list[float]:
    # Always includes the shot's first instant, so every shot has at least one sample.
    count = max(1, math.ceil((shot_end - shot_start) * fps))
    return [shot_start + i / fps for i in range(count)]


def pick_subject(faces_per_sample: Sequence[Sequence[Face]], frame_w: float) -> list[float | None]:
    """Follow one person through a shot: centre x per sample, or None where they weren't seen.

    Detections are linked into tracks by position. The track with the largest total face area
    wins, so a big face that stays beats one that flashes past, and the crop never jumps
    between people mid-shot.
    """
    tracks: list[dict] = []
    for i, faces in enumerate(faces_per_sample):
        for face in sorted(faces, key=lambda f: -f.area):  # big faces claim tracks first
            candidates = [
                t for t in tracks
                if i not in t["xs"] and abs(t["last"] - face.cx) <= MATCH_DISTANCE * frame_w
            ]
            track = min(candidates, key=lambda t: abs(t["last"] - face.cx), default=None)
            if track is None:
                track = {"xs": {}, "last": face.cx, "score": 0.0}
                tracks.append(track)
            track["xs"][i] = face.cx
            track["last"] = face.cx
            track["score"] += face.area
    if not tracks:
        return [None] * len(faces_per_sample)
    subject = max(tracks, key=lambda t: t["score"])
    return [subject["xs"].get(i) for i in range(len(faces_per_sample))]


def smooth(targets: Sequence[float | None], dead_zone: float, alpha: float) -> list[float | None]:
    """Dead zone + exponential smoothing. Snaps to the first face seen, then follows gently.

    None targets hold the current position; positions stay None until a face appears.
    """
    pos = None
    out = []
    for target in targets:
        if target is not None:
            if pos is None:
                pos = target
            elif abs(target - pos) > dead_zone:
                pos += alpha * (target - pos)
        out.append(pos)
    return out


def plan_track(shots: Sequence[Shot], frame_w: float, crop_w: float,
               dead_zone: float = DEAD_ZONE, alpha: float = SMOOTHING) -> Track:
    last = None  # carried across shots: a shot with no face holds the previous position
    samples = []
    for shot in shots:
        # Fresh smoothing per shot, so a cut snaps straight to the new subject.
        positions = smooth(pick_subject(shot.faces, frame_w), dead_zone * crop_w, alpha)
        centres = []
        for pos in positions:
            if pos is None:
                pos = last if last is not None else frame_w / 2
            last = pos
            centres.append(clamp_center(pos, frame_w, crop_w))
        samples.append((shot.times, centres))
    return Track(shot_starts=[s.times[0] for s in shots], samples=samples)


# --- Detection on real frames -------------------------------------------------------------

class FaceDetector:
    def __init__(self) -> None:
        # Imported here so the pure functions above can be tested without loading MediaPipe.
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        self._mp = mp
        self._detector = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(FACE_MODEL)),
            running_mode=vision.RunningMode.IMAGE,
            min_detection_confidence=MIN_CONFIDENCE,
        ))

    def detect(self, frame_bgr: np.ndarray) -> list[Face]:
        h, w = frame_bgr.shape[:2]
        scale = min(1.0, DETECT_WIDTH / w)
        small = cv2.resize(frame_bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                               data=cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        faces = []
        for d in self._detector.detect(image).detections:
            box = d.bounding_box
            faces.append(Face(cx=(box.origin_x + box.width / 2) / scale,
                              width=box.width / scale, height=box.height / scale))
        return faces

    def close(self) -> None:
        self._detector.close()

    def __enter__(self) -> "FaceDetector":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def track_clip(path: Path, start: float, end: float, cuts: Sequence[float], fps: float,
               on_progress: Callable[[float], None]) -> Track:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV can't open {path}")
    try:
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        shots = [Shot(times=sample_times(a, b, fps), faces=[]) for a, b in shot_bounds(start, end, cuts)]
        pending = [(t, shot) for shot in shots for t in shot.times]  # in time order

        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        with FaceDetector() as detector:
            done = 0
            # grab() decodes without converting; only sampled frames are retrieved and detected.
            while done < len(pending) and cap.grab():
                t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if t < pending[done][0] - 1e-3:
                    continue
                ok, frame = cap.retrieve()
                faces = detector.detect(frame) if ok else []
                # One frame can serve several sample times when the source fps is low.
                while done < len(pending) and pending[done][0] <= t + 1e-3:
                    pending[done][1].faces.append(faces)
                    done += 1
                on_progress(done / len(pending))
        # Samples past the last decodable frame see no faces (and so hold position).
        for shot in shots:
            shot.faces.extend([[]] * (len(shot.times) - len(shot.faces)))
    finally:
        cap.release()
    return plan_track(shots, frame_w, crop_size(frame_w, frame_h)[0])
