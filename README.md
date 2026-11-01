# FlipClip

FlipClip turns long horizontal (16:9) videos into vertical (9:16) clips for Shorts, Reels and TikTok.
Planned pipeline: YouTube download → scene segmentation → face-tracked cropping → export.

> Status: video input, segmentation, clip editor, vertical crop and export. Upload a video or paste a
> YouTube link, "Find clips" splits it at scene cuts into 15–60 s candidates, "Edit" moves a clip's start
> and end, and "Make vertical" renders any clip as a 1080x1920 video whose crop follows the speaker's
> face. Each rendered clip downloads on its own, and "Export all (zip)" renders whatever is left and
> downloads every clip in one zip. Videos are deleted after 2 hours.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose. Nothing else is needed.

## Start

```bash
docker compose up
```

Open **http://localhost:5173**. The API is at http://localhost:8000 (e.g. `/api/health`).

To change limits, clip lengths or CORS origins, copy `.env.example` to `.env` and edit it.

### How clips are chosen

PySceneDetect finds scene cuts. Consecutive scenes are merged until a clip reaches `MIN_CLIP_SEC`
(a short tail joins the previous clip). A clip longer than `MAX_CLIP_SEC` is split at a scene cut
when both parts stay within the limits, otherwise evenly.

### How editing works

"Edit" on a clip opens a range slider over the clip plus 30 s either side (clamped to the video), with
±1 s buttons for each end and a preview that plays only the selection. A clip can be shortened or
extended into neighbouring footage. Clips are independent, so an edited clip may overlap the next one.
Its length must stay between `EDIT_MIN_SEC` (default 3 s) and `MAX_CLIP_SEC`; the editor says why
when it can't save.

Saving deletes the clip's rendered file and the export zip (neither matches any more) and redraws its
thumbnail. Segmentation's bounds are kept, so "Reset to original" restores them. Rendering uses the scene
cuts stored at segmentation that fall inside the new range, so detection never runs again. Edits are
refused (409) while that clip is waiting or rendering, or while an export runs, so a render never mixes
old and new bounds. Thumbnail and render URLs carry the clip's revision (`?v=`), so the browser can't
show a cached old version.

### How the vertical crop follows the face

MediaPipe (BlazeFace full-range model) looks for faces `TRACK_FPS` times per second. In each shot the
tracker follows one person: the face with the largest total area across samples, so it doesn't jump
between people. A dead zone ignores small movements and smoothing eases the larger ones; both reset at
scene cuts so a new shot snaps to its subject. With no face it holds the last position (frame centre
at the start). The crop centre is interpolated between samples for every frame, then frames are cropped
in OpenCV and piped to ffmpeg with the clip's original audio. A job renders one clip at a time.

### How export works

Export queues every clip that isn't rendered yet on the job's render queue, then the zip step behind
them, so the zip only starts once those renders are finished. Its progress is the renders' progress
(95%) plus the zip copy (5%). Clips are stored uncompressed (H.264 is already compressed) and copied
into the zip in 1 MB chunks, written to the job folder, which cleanup deletes with the rest of the job.
Files are named `flipclip_clip01.mp4`, `flipclip_clip02.mp4`, … in clip order.

### Tests

```bash
docker compose exec backend python -m pytest tests
```

### API

| Route | Purpose |
|---|---|
| `POST /api/jobs/upload` | multipart field `file`. 413 too big, 415 not a video, 422 too long |
| `POST /api/jobs/youtube` | `{"url": "..."}`. YouTube links only (400 otherwise); 422 too long |
| `GET /api/jobs/{id}` | `{id, status, progress, error, duration, width, height}` |
| `GET /api/jobs/{id}/video` | the stored video, for the preview |
| `POST /api/jobs/{id}/segment` | start scene detection (job must be `ready`, else 409) |
| `GET /api/jobs/{id}/clips` | `[{index, start, end, duration, original_start, original_end, edited, thumbnail_url}]` once `segmented` |
| `PATCH /api/jobs/{id}/clips/{index}` | `{"start": s, "end": e}` new bounds; returns the clip. 422 outside the video, start ≥ end, or length outside `EDIT_MIN_SEC`–`MAX_CLIP_SEC`; 409 while that clip renders or an export runs. Drops its render and the zip |
| `POST /api/jobs/{id}/clips/{index}/reset` | back to segmentation's bounds; same invalidation and 409s |
| `GET /api/jobs/{id}/clips/{index}/thumbnail` | JPEG thumbnail for one clip |
| `POST /api/jobs/{id}/clips/{index}/render` | queue a 9:16 render (202); 200 with the file if already rendered |
| `GET /api/jobs/{id}/clips/{index}` | render `{status, progress, error, video_url, download_url}` |
| `GET /api/jobs/{id}/clips/{index}/video` | the rendered 1080x1920 mp4 (seekable) |
| `GET /api/jobs/{id}/clips/{index}/download` | the same file as an attachment, `flipclip_clipNN.mp4`; 404 until rendered |
| `POST /api/jobs/{id}/export` | render the missing clips, then zip all of them (202); 200 if already exported |
| `GET /api/jobs/{id}/export` | `{status, progress, error, download_url}`; status `idle`/`rendering`/`zipping`/`done`/`failed` |
| `GET /api/jobs/{id}/export/download` | `flipclip_clips.zip`; 404 until the export is done |
| `GET /api/config` | upload, duration and clip-length limits, so the UI can check before sending |

All `/clips/...` and `/export...` routes answer 409 until the job is `segmented`.

### Production image

```bash
docker build -t flipclip .
docker run -p 7860:7860 flipclip
```

Open **http://localhost:7860**. One container serves both the API and the built frontend.

## Local setup (editor autocomplete only)

The app runs in Docker. A local venv is only for IDE autocomplete. Install in **two steps**:
scenedetect goes in with `--no-deps`, so it can't pull in a second OpenCV package.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt               # Windows (macOS/Linux: .venv/bin/python)
.venv/Scripts/python -m pip install --no-deps -r requirements-nodeps.txt
```

`pip check` will report that scenedetect needs `opencv-python`. That's expected: `opencv-contrib-python`
provides the same `cv2` module.

## Project structure

```
backend/
  app/
    main.py          FastAPI app: CORS, routers, static frontend (prod)
    api/             HTTP routes: health, config, jobs
    services/        business logic: job store, uploads, ffprobe, YouTube, segmenter,
                     editor (clip bounds + invalidation), tracker (face-follow crop),
                     renderer (9:16 encode + queue), exporter (zip of all clips), cleanup
    core/config.py   settings read from env
  requirements.txt   pinned Python dependencies
  requirements-nodeps.txt  scenedetect, installed with --no-deps
  requirements-dev.txt     pytest + httpx (dev image only)
  tests/             pytest suite, run inside the backend container
  Dockerfile         dev backend image
frontend/            Vite + React UI (plain CSS)
docker-compose.yml   dev: backend :8000 + Vite :5173, hot reload
Dockerfile           production: single container on :7860
```
