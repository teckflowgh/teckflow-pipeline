"""
Stage 5 — Scheduler
APScheduler BackgroundScheduler that triggers the pipeline daily.
Must run inside the FastAPI process (single uvicorn worker).
Also handles email + webhook failure alerts.
"""

import json
import logging
import os
import smtplib
import uuid
from email.mime.text import MIMEText
from pathlib import Path

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "settings.json"

scheduler = BackgroundScheduler()
_scheduler_started = False


# ---------------------------------------------------------------------------
# Alert helpers
# ---------------------------------------------------------------------------

def _send_email_alert(subject: str, body: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("ALERT_EMAIL_FROM", smtp_user)
    to_addr = os.environ.get("ALERT_EMAIL_TO", "")

    if not all([smtp_host, smtp_user, smtp_pass, to_addr]):
        return

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr

        with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT", "587"))) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("Alert email sent to %s", to_addr)
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)


def _send_webhook_alert(payload: dict) -> None:
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json=payload, timeout=10)
        logger.info("Webhook alert sent.")
    except Exception as e:
        logger.error("Failed to send webhook alert: %s", e)


def send_failure_alert(stage: str, error: str, run_id: str) -> None:
    import datetime
    subject = f"[Video Pipeline] FAILED at {stage} — {datetime.date.today().isoformat()}"
    body = f"Run ID: {run_id}\nStage: {stage}\n\nError:\n{error}"
    _send_email_alert(subject, body)
    _send_webhook_alert({"run_id": run_id, "status": "failed", "stage": stage, "error": error[:500]})


# ---------------------------------------------------------------------------
# Scheduler job
# ---------------------------------------------------------------------------

def run_pipeline_job() -> None:
    from pipeline.orchestrator import run_pipeline
    run_id = str(uuid.uuid4())[:8]
    logger.info("Scheduled pipeline run started. run_id=%s", run_id)
    try:
        run_pipeline(run_id)
    except Exception as e:
        logger.error("Scheduled pipeline run failed: %s", e, exc_info=True)
        send_failure_alert("orchestrator", str(e), run_id)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def _load_schedule() -> tuple[int, int]:
    """Return (hour, minute) from settings.json or env."""
    try:
        with SETTINGS_FILE.open() as f:
            settings = json.load(f)
        time_str = settings.get("schedule_time", "06:00")
    except Exception:
        time_str = os.environ.get("SCHEDULE_TIME", "06:00")

    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def _load_timezone() -> str:
    try:
        with SETTINGS_FILE.open() as f:
            settings = json.load(f)
        return settings.get("timezone", "Europe/Brussels")
    except Exception:
        return os.environ.get("TIMEZONE", "Europe/Brussels")


def start_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return

    hour, minute = _load_schedule()
    tz = _load_timezone()

    scheduler.configure(timezone=tz)
    scheduler.add_job(
        run_pipeline_job,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
        id="daily_video",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler_started = True
    logger.info("Scheduler started — daily run at %02d:%02d %s", hour, minute, tz)


def reschedule(time_str: str, timezone: str) -> None:
    """Called by the settings API endpoint after settings are updated."""
    parts = time_str.split(":")
    hour, minute = int(parts[0]), int(parts[1])
    scheduler.reschedule_job(
        "daily_video",
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
    )
    logger.info("Rescheduled daily run to %s %s", time_str, timezone)


def stop_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started and scheduler.running:
        scheduler.shutdown(wait=False)
        _scheduler_started = False
        logger.info("Scheduler stopped.")
