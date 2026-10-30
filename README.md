# FlipClip

FlipClip turns long horizontal (16:9) videos into vertical (9:16) clips for Shorts, Reels and TikTok.
Planned pipeline: YouTube download → scene segmentation → face-tracked cropping → export.

> Status: video input. Upload a video file or paste a YouTube link; the backend stores it and the UI
> shows a preview with duration and resolution. Uploaded and downloaded videos are deleted after 2 hours.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose. Nothing else is needed.

## Start

```bash
docker compose up
```

Open **http://localhost:5173**. The API is at http://localhost:8000 (e.g. `/api/health`).

To change limits or CORS origins, copy `.env.example` to `.env` and edit it.

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
| `GET /api/config` | upload and duration limits, so the UI can check before uploading |

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
    services/        business logic: job store, uploads, ffprobe, YouTube, storage cleanup
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
