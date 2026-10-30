# Dev image for the backend; the production image is the root Dockerfile.
FROM python:3.11-slim-trixie

# ffmpeg does the actual video work. libgl1/libglib2.0-0: opencv-contrib-python (needed by
# mediapipe) is a non-headless build and fails at "import cv2" without them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies before source so code edits don't invalidate the pip layer.
COPY requirements.txt requirements-nodeps.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps -r requirements-nodeps.txt \
    && pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
