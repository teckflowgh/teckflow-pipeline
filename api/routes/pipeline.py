import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.models import RunRecord, RunTriggerResponse
from pipeline.orchestrator import run_pipeline, get_latest_run

router = APIRouter(prefix="/api")

SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "settings.json"

_running: set[str] = set()


class RunRequest(BaseModel):
    mode: Optional[str] = None  # "short" | "long" | None (gebruikt settings.json)


def _background_run(run_id: str, mode: str | None) -> None:
    _running.add(run_id)
    try:
        # Tijdelijk de modus overschrijven als meegegeven
        if mode:
            try:
                with SETTINGS_FILE.open(encoding="utf-8") as f:
                    settings = json.load(f)
                settings["video_mode"] = mode
                with SETTINGS_FILE.open("w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2)
            except Exception:
                pass
        run_pipeline(run_id)
    finally:
        _running.discard(run_id)


@router.post("/run", response_model=RunTriggerResponse)
async def trigger_run(background_tasks: BackgroundTasks, req: RunRequest = RunRequest()):
    if _running:
        raise HTTPException(status_code=409, detail="Een pipeline run is al bezig.")
    run_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(_background_run, run_id, req.mode)
    mode_label = req.mode or "uit settings"
    return RunTriggerResponse(run_id=run_id, message=f"Pipeline gestart (modus: {mode_label}).")


@router.get("/status", response_model=RunRecord | None)
async def get_status():
    return get_latest_run()
