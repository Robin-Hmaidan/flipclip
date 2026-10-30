import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Demuxers we accept. The whitelist also stops playlist formats (HLS, concat) from making
# ffprobe open other files or URLs named inside an uploaded file, and rejects images.
ALLOWED_FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,flv,mpegts,mpeg"

MEDIA_TYPES = {
    "mov,mp4,m4a,3gp,3g2,mj2": "video/mp4",
    "matroska,webm": "video/webm",
}


class ProbeError(Exception):
    """The file is not a usable video. The message is for logs, not users."""


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    media_type: str


def probe(path: Path) -> VideoInfo:
    cmd = [
        "ffprobe", "-v", "error",
        "-protocol_whitelist", "file",
        "-format_whitelist", ALLOWED_FORMATS,
        "-select_streams", "v:0",
        "-show_entries", "format=duration,format_name:stream=width,height",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("ffprobe timed out") from exc
    if result.returncode != 0:
        raise ProbeError(result.stderr.strip()[:500] or f"ffprobe exited {result.returncode}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    if not streams:
        raise ProbeError("no video stream")
    try:
        info = VideoInfo(
            duration=float(fmt["duration"]),
            width=int(streams[0]["width"]),
            height=int(streams[0]["height"]),
            media_type=MEDIA_TYPES.get(fmt.get("format_name"), "application/octet-stream"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProbeError(f"incomplete metadata: {data}") from exc
    if info.duration <= 0 or info.width <= 0 or info.height <= 0:
        raise ProbeError(f"invalid metadata: {data}")
    return info
