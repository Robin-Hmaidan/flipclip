# Dev image for the backend; the production image is the root Dockerfile.
FROM python:3.11-slim-trixie

# ffmpeg does the actual video work. libgl1/libglib2.0-0: opencv-contrib-python (needed by
# mediapipe) is a non-headless build and fails at "import cv2" without them.
# libegl1/libgles2: libmediapipe.so links libEGL.so.1 and libGLESv2.so.2 and won't load otherwise.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp needs a JavaScript runtime for YouTube; without one some formats go missing.
# 2.9.5 is the version yt-dlp 2026.8.19 pins in its "pin-deno" extra. Keep the two in step.
COPY --from=denoland/deno:bin-2.9.5 /deno /usr/local/bin/deno

# MediaPipe 1.x ships no models. Full-range BlazeFace also finds small faces in wide shots
# (talks, interviews); the checksum pins the exact file.
ADD --checksum=sha256:3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b --chmod=644 \
    https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite \
    /opt/models/blaze_face_full_range.tflite

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies before source so code edits don't invalidate the pip layer.
COPY requirements.txt requirements-nodeps.txt requirements-dev.txt ./
# The cache mount keeps downloaded wheels between builds (outside the image), so a rebuild or a
# retry after a network timeout doesn't fetch ~1 GB again. Long timeout + retries for slow links.
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt \
    && pip install --no-deps -r requirements-nodeps.txt \
    && pip install -r requirements-dev.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
