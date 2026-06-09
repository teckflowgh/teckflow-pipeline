import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from api.models import SettingsPayload

router = APIRouter(prefix="/api")

SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "settings.json"


def _load() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    with SETTINGS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _save(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


@router.get("/settings")
async def get_settings():
    return _load()


@router.post("/settings")
async def update_settings(payload: SettingsPayload):
    current = _load()
    updates = payload.model_dump(exclude_none=True)
    current.update(updates)
    _save(current)

    # Reschedule APScheduler if time/timezone changed
    if "schedule_time" in updates or "timezone" in updates:
        try:
            from pipeline.stage5_scheduler.scheduler import reschedule
            reschedule(
                time_str=current.get("schedule_time", "06:00"),
                timezone=current.get("timezone", "Europe/Brussels"),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Settings saved but reschedule failed: {e}")

    return {"ok": True, "settings": current}
