"""
FastAPI application entry point.
Run with: uvicorn api.main:app --host 0.0.0.0 --port 8000
IMPORTANT: do NOT use --workers N — APScheduler requires a single process.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)

from pipeline.orchestrator import setup_logging, recover_stale_runs
from pipeline.stage5_scheduler.scheduler import start_scheduler, stop_scheduler
from api.routes import pipeline, history, settings, logs

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    recover_stale_runs()
    start_scheduler()
    logger.info("FastAPI started. Scheduler running.")
    yield
    stop_scheduler()
    logger.info("FastAPI shutdown.")


app = FastAPI(
    title="Video Pipeline API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow Next.js dev server and optional production origin
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
extra_origin = os.environ.get("DASHBOARD_ORIGIN", "")
if extra_origin:
    origins.append(extra_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router)
app.include_router(history.router)
app.include_router(settings.router)
app.include_router(logs.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Video Pipeline API"}
