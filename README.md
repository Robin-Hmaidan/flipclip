# FlipClip

FlipClip turns long horizontal (16:9) videos into vertical (9:16) clips for Shorts, Reels and TikTok.
Planned pipeline: YouTube download → scene segmentation → face-tracked cropping → export.

> Status: video input, segmentation, clip editor, vertical crop and export. Upload a video, paste a
> YouTube link or try the bundled sample; "Find clips" splits it at scene cuts into 15–60 s candidates, "Edit" moves a clip's start
> and end, and "Make vertical" renders any clip as a 1080x1920 video whose crop follows the speaker's
> face. Each rendered clip downloads on its own, and "Export all (zip)" renders whatever is left and
> downloads every clip in one zip. Videos are deleted after 2 hours.

## Live demo

**https://marvelous-pronto-unwieldy.ngrok-free.dev**

Hosted from my machine since the brief excludes paid services: the production container runs on my
PC and an ngrok tunnel makes it public, so it's only up while that PC is on. It's one machine shared
by everyone, so it works on at most 3 videos at a time (`MAX_ACTIVE_JOBS`); while it's full, starting
another one says so and asks you to try again in a minute. Uploads are capped at 500 MB and videos at
60 minutes, and links must be YouTube video links.

## Run it yourself

With [Docker](https://docs.docker.com/get-docker/) installed:

```bash
docker compose -f docker-compose.prod.yml up
```

Then open **http://localhost:7860**. This is the same single production container as the live demo
(API and built frontend on one port), with a named volume for job data.

## Screenshots

| Phone (375 px) | Desktop |
|---|---|
| ![Input screen on a phone](docs/screenshots/mobile-01-input.png) | ![Input screen](docs/screenshots/desktop-01-input.png) |
| ![Clips on a phone](docs/screenshots/mobile-04-clips.png) | ![Clips](docs/screenshots/desktop-04-clips.png) |
| ![Before and after on a phone](docs/screenshots/mobile-05-before-after.png) | ![Before and after](docs/screenshots/desktop-05-before-after.png) |
| ![Clip editor on a phone](docs/screenshots/mobile-06-edit.png) | ![Clip editor](docs/screenshots/desktop-06-edit.png) |
| ![Export on a phone](docs/screenshots/mobile-08-exported.png) | ![Export](docs/screenshots/desktop-08-exported.png) |

All shots, including loading, error and dark-mode states, are in [docs/screenshots/](docs/screenshots/).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose. Nothing else is needed.

## Development setup

```bash
docker compose up
```

Open **http://localhost:5173**. The API is at http://localhost:8000 (e.g. `/api/health`).

**Quickest look:** click **Try a sample video**. It starts a normal job from a bundled 3-minute
interview and goes straight on to finding clips, so there's nothing to upload or paste.

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

### Sample video

`backend/app/assets/sample.mp4` is the three answers (20.4–85.0 s, 95.25–140.1 s, 150.3–206.4 s) of
[*Amber Straughn Canned Interview JWST 2023*](https://commons.wikimedia.org/wiki/File:NASA_Interview_Opportunity-_Celebrate_the_James_Webb_Space_Telescope%E2%80%99s_First_Year_Of_Amazing_Science_With_a_New_Observation_Live_Shots_(SVS14349_-_Amber_Straughn_Canned_Interview_JWST_2023).webm)
by NASA's Scientific Visualization Studio ([source page](https://svs.gsfc.nasa.gov/14349)), joined with the
question cards between them removed and re-encoded to H.264 1080p (2:46, 26 MB).

**License: public domain.** It is a work of the US federal government (NASA), so it carries no
copyright in the US and needs no attribution. NASA's
[media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/) still apply: don't use
it to suggest that NASA or the person shown endorses FlipClip. The credit above is a courtesy.

`SAMPLE_VIDEO` points the route at another file; the button hides when the file is missing.

### Tests

```bash
docker compose exec backend python -m pytest tests
```

### API

| Route | Purpose |
|---|---|
| `POST /api/jobs/upload` | multipart field `file`. 413 too big, 415 not a video, 422 too long |
| `POST /api/jobs/youtube` | `{"url": "..."}`. YouTube links only (400 otherwise); 422 too long |
| `POST /api/jobs/sample` | new job from the bundled sample video (201, `ready`); 404 if the file is missing |
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
| `GET /api/config` | upload, duration and clip-length limits, and `sample_available`, so the UI can check before sending |

All `/clips/...` and `/export...` routes answer 409 until the job is `segmented`.

Starting work (upload, YouTube, sample, segment, render, export) answers **429** with
`Retry-After: 60` while `MAX_ACTIVE_JOBS` (default 3) jobs are busy: uploading, downloading,
finding clips, rendering or exporting. A job that is already busy can still queue more renders, since
they share its one worker; finished files are always served.

### Production image

`docker-compose.prod.yml` builds the root `Dockerfile` (non-root uid 1000, API and built UI on
:7860), restarts it unless stopped, keeps `/data` in a named volume and pins public DNS resolvers like
the dev backend. Without Compose:

```bash
docker build -t flipclip .
docker run -p 7860:7860 flipclip
```

### Hosting the live demo

```powershell
.\scripts\start-demo.ps1            # add -NoBuild to skip rebuilding the image
```

Starts the production stack, waits for it to answer, then opens the ngrok tunnel on the static domain.
It needs ngrok (`winget install Ngrok.Ngrok`) with an authtoken (`ngrok config add-authtoken <token>`).
Ctrl+C closes the tunnel; the app keeps running until
`docker compose -f docker-compose.prod.yml down`.

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
    assets/          sample.mp4 for "Try a sample video" (public domain, see above)
  requirements.txt   pinned Python dependencies
  requirements-nodeps.txt  scenedetect, installed with --no-deps
  requirements-dev.txt     pytest + httpx (dev image only)
  tests/             pytest suite, run inside the backend container
  Dockerfile         dev backend image
frontend/            Vite + React UI (plain CSS, light and dark from the system setting)
docs/screenshots/    UI at 375 px and desktop, for this README
docker-compose.yml   dev: backend :8000 + Vite :5173, hot reload
docker-compose.prod.yml  production: the root Dockerfile on :7860
Dockerfile           production: single container on :7860
scripts/start-demo.ps1   production stack + ngrok tunnel for the live demo
```
