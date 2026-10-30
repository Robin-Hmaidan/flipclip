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

# See backend/Dockerfile for why the GL libs are needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# JavaScript runtime for yt-dlp; see backend/Dockerfile for the version choice.
COPY --from=denoland/deno:bin-2.9.5 /deno /usr/local/bin/deno

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/data \
    ALLOWED_ORIGINS=http://localhost:7860

# Spaces runs containers as uid 1000, so the app and its data dir must not need root.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data && chown app /data

WORKDIR /app
COPY backend/requirements.txt backend/requirements-nodeps.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps -r requirements-nodeps.txt

COPY backend/app ./app
# main.py mounts /app/static when it exists.
COPY --from=frontend /src/dist ./static

USER app
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
