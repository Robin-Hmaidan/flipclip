# Production: one container, one port (7860 is what Hugging Face Spaces expects).

# --- Stage 1: build the React app to static files ---
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python backend + ffmpeg, serving the built UI ---
FROM python:3.11-slim-trixie

# See backend/Dockerfile for why the GL/EGL libs are needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

# JavaScript runtime for yt-dlp; see backend/Dockerfile for the version choice.
COPY --from=denoland/deno:bin-2.9.5 /deno /usr/local/bin/deno

# Face detection model; see backend/Dockerfile.
ADD --checksum=sha256:3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b --chmod=644 \
    https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite \
    /opt/models/blaze_face_full_range.tflite

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/data \
    ALLOWED_ORIGINS=http://localhost:7860

# Spaces runs containers as uid 1000, so the app and its data dir must not need root.
# ADD creates /opt/models without access for other users; the app user must be able to read it.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data && chown app /data \
    && chmod 755 /opt/models

WORKDIR /app
COPY backend/requirements.txt backend/requirements-nodeps.txt ./
# Wheel cache between builds and network retries; see backend/Dockerfile.
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt \
    && pip install --no-deps -r requirements-nodeps.txt

COPY backend/app ./app
# main.py mounts /app/static when it exists.
COPY --from=frontend /src/dist ./static

USER app
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
