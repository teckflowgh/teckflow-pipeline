from pathlib import Path
from fastapi import APIRouter, Query
from api.models import LogsResponse

router = APIRouter(prefix="/api")

LOG_FILE = Path(__file__).parent.parent.parent / "logs" / "pipeline.log"


@router.get("/logs", response_model=LogsResponse)
async def get_logs(lines: int = Query(default=200, ge=1, le=1000)):
    if not LOG_FILE.exists():
        return LogsResponse(lines=[])
    with LOG_FILE.open(encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    return LogsResponse(lines=[l.rstrip() for l in all_lines[-lines:]])
