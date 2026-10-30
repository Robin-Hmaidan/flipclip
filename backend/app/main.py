import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import config, health, jobs
from app.core.config import settings
from app.services.jobs import job_store
from app.services.storage import cleanup_expired, cleanup_loop, jobs_root

# uvicorn only configures its own loggers; without this, app logs (the detailed errors) are dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Only present in the production image; in dev the Vite server serves the UI.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A fresh volume (or a run outside Docker) may not have the folder yet.
    jobs_root().mkdir(parents=True, exist_ok=True)
    # Folders left by a previous run are never tracked again, so sweep them now.
    cleanup_expired(job_store)
    sweeper = asyncio.create_task(cleanup_loop(job_store))
    yield
    sweeper.cancel()
    with suppress(asyncio.CancelledError):
        await sweeper


app = FastAPI(title="FlipClip", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")

# Mounted last so /api routes take precedence over the catch-all static mount.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
