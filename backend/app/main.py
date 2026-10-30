from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health
from app.core.config import settings

# Only present in the production image; in dev the Vite server serves the UI.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A fresh volume (or a run outside Docker) may not have the folder yet.
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="FlipClip", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")

# Mounted last so /api routes take precedence over the catch-all static mount.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
