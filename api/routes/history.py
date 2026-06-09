from fastapi import APIRouter, Query
from pipeline.orchestrator import _load_history

router = APIRouter(prefix="/api")


@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    history = list(reversed(_load_history()))
    total = len(history)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": history[start:end],
    }
