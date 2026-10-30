import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import yt_dlp

from app.core.config import settings
from app.services.jobs import JobStore
from app.services.probe import probe
from app.services.storage import delete_job_dir, job_dir

log = logging.getLogger(__name__)

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
# Applied to the extracted ID only, never to the raw URL.
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
ID_PATH_PREFIXES = {"shorts", "embed", "live", "v"}

# H.264 first: YouTube's default 1080p mp4 is often AV1, which OpenCV's bundled ffmpeg may not
# decode in later steps. Then any mp4 + m4a, then anything ≤1080p merged into mp4. No re-encoding.
FORMAT = (
    "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]"
    "/bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]"
    "/bv*[height<=1080]+ba/b[height<=1080]"
)

BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "noplaylist": True,
    "socket_timeout": 30,
    "logger": logging.getLogger("yt_dlp"),
}


class YoutubeError(Exception):
    pass


@dataclass
class Metadata:
    duration: float | None
    is_live: bool


def canonical_url(raw: str) -> str | None:
    """Return https://www.youtube.com/watch?v=<id>, or None if raw isn't a YouTube video link.

    yt-dlp only ever receives this rebuilt URL, so nothing else from user input reaches it.
    """
    try:
        parts = urlsplit(raw.strip())
        port = parts.port  # raises ValueError on a malformed port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.username or parts.password or port:
        return None
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        return None

    segments = [s for s in parts.path.split("/") if s]
    video_id = None
    if host == "youtu.be":
        video_id = segments[0] if len(segments) == 1 else None
    elif segments == ["watch"]:
        video_id = parse_qs(parts.query).get("v", [None])[0]
    elif len(segments) == 2 and segments[0] in ID_PATH_PREFIXES:
        video_id = segments[1]

    if not video_id or not VIDEO_ID.fullmatch(video_id):
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_metadata(url: str) -> Metadata:
    try:
        with yt_dlp.YoutubeDL(BASE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
    except yt_dlp.utils.YoutubeDLError as exc:
        raise YoutubeError(str(exc)) from exc
    return Metadata(
        duration=info.get("duration"),
        is_live=bool(info.get("is_live")) or info.get("live_status") in ("is_live", "is_upcoming"),
    )


def download_job(store: JobStore, job_id: str, url: str) -> None:
    """Background task: download, probe, and mark the job ready or failed."""
    folder = job_dir(job_id)
    store.update(job_id, status="downloading", progress=0)
    finished_streams: set[str] = set()

    def on_progress(d: dict) -> None:
        # Video and audio download separately; spread 0–95% across both. The rest is merge + probe.
        streams = len(d.get("info_dict", {}).get("requested_formats") or []) or 1
        if d["status"] == "finished":
            finished_streams.add(d.get("filename", ""))
            fraction = 0.0
        elif d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            fraction = (d.get("downloaded_bytes") or 0) / total if total else 0.0
        else:
            return
        overall = (len(finished_streams) + fraction) / streams
        store.update(job_id, progress=min(95, int(overall * 95)))

    opts = {
        **BASE_OPTS,
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "source.%(ext)s"),
        "max_filesize": settings.max_upload_mb * 1024 * 1024,
        "progress_hooks": [on_progress],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        path = Path(info["requested_downloads"][0]["filepath"]).resolve()
        if path.parent != folder.resolve():
            raise YoutubeError(f"unexpected output path {path}")
        video = probe(path)
        # Metadata was checked before downloading; re-check what actually arrived.
        if video.duration > settings.max_duration_sec:
            raise YoutubeError(f"downloaded duration {video.duration}s over limit")
    except Exception:
        log.exception("youtube download failed for job %s (%s)", job_id, url)
        delete_job_dir(job_id)
        store.update(job_id, status="failed", error="Download failed. Try another video.")
        return

    store.update(
        job_id,
        status="ready",
        progress=100,
        duration=video.duration,
        width=video.width,
        height=video.height,
        video_path=path,
        media_type=video.media_type,
    )
