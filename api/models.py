from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class RunRecord(BaseModel):
    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    status: str  # running | completed | failed
    current_stage: Optional[str] = None
    topic: Optional[str] = None
    script_preview: Optional[str] = None
    pictory_draft_url: Optional[str] = None
    stage_timings: dict[str, float] = {}
    error: Optional[str] = None


class RunTriggerResponse(BaseModel):
    run_id: str
    message: str


class SettingsPayload(BaseModel):
    schedule_time: Optional[str] = None
    timezone: Optional[str] = None
    topic_source: Optional[str] = None
    youtube_category_id: Optional[str] = None
    script_language: Optional[str] = None
    alert_email: Optional[str] = None
    alert_webhook_url: Optional[str] = None
    cleanup_days: Optional[int] = None
    history_max_entries: Optional[int] = None


class LogsResponse(BaseModel):
    lines: list[str]
