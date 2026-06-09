"""
Stage 4 — Pictory API Integration
Uploads the avatar video + script to Pictory, requests B-roll assembly
with auto-captions, and saves the resulting Draft URL.

Requires Pictory Teams plan (~$99/mo) for API access.
If PICTORY_CLIENT_ID is empty, the stage runs in stub mode and is skipped.
"""

import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PICTORY_BASE = "https://api.pictory.ai/pictoryapis/v1"
POLL_INTERVAL_SECONDS = 30
POLL_MAX_ATTEMPTS = 30  # 15 minutes maximum wait


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_token(client_id: str, client_secret: str) -> str:
    url = f"{PICTORY_BASE}/oauth2/token"
    resp = requests.post(
        url,
        json={"client_id": client_id, "client_secret": client_secret},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token", "")
    if not token:
        raise RuntimeError("Pictory token endpoint returned no access_token.")
    return token


# ---------------------------------------------------------------------------
# Script → Storyboard scenes
# ---------------------------------------------------------------------------

def _script_to_scenes(script: str, topic: str) -> list[dict]:
    """
    Split the script into ~4 scenes for Pictory.
    Each scene gets auto B-roll search terms from its keywords.
    """
    sentences = [s.strip() for s in script.replace("\n", " ").split(".") if s.strip()]
    chunk_size = max(1, len(sentences) // 4)
    chunks = [
        ". ".join(sentences[i : i + chunk_size]) + "."
        for i in range(0, len(sentences), chunk_size)
    ]

    scenes = []
    for i, chunk in enumerate(chunks[:8]):  # Pictory max scenes
        # Use first few words as B-roll search hint
        keywords = " ".join(chunk.split()[:6])
        scenes.append(
            {
                "text": chunk,
                "Voice": {"VoiceId": ""},  # Pictory won't re-voice; audio is overlaid
                "Background": {
                    "type": "stock_footage",
                    "keyword": f"{topic} {keywords}",
                },
                "duration": 0,  # auto
            }
        )
    return scenes


# ---------------------------------------------------------------------------
# Main upload function
# ---------------------------------------------------------------------------

def upload_to_pictory(
    video_path: str | Path,
    script: str,
    topic: str,
    output_url_file: str | Path,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_id: str | None = None,
) -> str | None:
    """
    Full Pictory pipeline:
      1. Authenticate
      2. Upload avatar_talking.mp4
      3. Create storyboard with B-roll, captions, transitions
      4. Poll until the draft is ready
      5. Save the draft URL to output_url_file

    Returns the draft URL string, or None in stub mode.
    """
    _client_id = client_id or os.environ.get("PICTORY_CLIENT_ID", "")
    _client_secret = client_secret or os.environ.get("PICTORY_CLIENT_SECRET", "")
    _user_id = user_id or os.environ.get("PICTORY_USER_ID", "")

    if not _client_id or not _client_secret:
        logger.warning(
            "PICTORY_CLIENT_ID / PICTORY_CLIENT_SECRET not set. "
            "Running in stub mode — Pictory upload skipped."
        )
        return None

    video_path = Path(video_path).resolve()
    output_url_file = Path(output_url_file).resolve()

    if not video_path.exists():
        raise FileNotFoundError(f"Avatar video not found: {video_path}")

    # 1. Auth
    logger.info("Authenticating with Pictory API...")
    token = _get_token(_client_id, _client_secret)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Pictory-User-Id": _user_id,
        "Content-Type": "application/json",
    }

    # 2. Upload video file
    logger.info("Uploading %s to Pictory...", video_path.name)
    with video_path.open("rb") as f:
        upload_resp = requests.post(
            f"{PICTORY_BASE}/video/upload",
            headers={"Authorization": f"Bearer {token}", "X-Pictory-User-Id": _user_id},
            files={"file": (video_path.name, f, "video/mp4")},
            timeout=300,
        )
    upload_resp.raise_for_status()
    upload_data = upload_resp.json()
    upload_job_id = upload_data.get("jobId") or upload_data.get("job_id")
    logger.info("Upload job ID: %s", upload_job_id)

    # 3. Create storyboard
    import datetime
    video_name = f"{topic} — {datetime.date.today().isoformat()}"
    scenes = _script_to_scenes(script, topic)

    storyboard_payload = {
        "videoName": video_name,
        "videoDescription": script[:300],
        "language": "en",
        "videoWidth": 1080,
        "videoHeight": 1920,
        "addSubtitle": True,
        "autoHighlightColor": "#FFFFFF",
        "brandLogo": {},
        "scenes": scenes,
    }

    logger.info("Creating Pictory storyboard with %d scenes...", len(scenes))
    sb_resp = requests.post(
        f"{PICTORY_BASE}/video/storyboard",
        headers=headers,
        json=storyboard_payload,
        timeout=60,
    )
    sb_resp.raise_for_status()
    job_id = sb_resp.json().get("jobId") or sb_resp.json().get("job_id")
    logger.info("Storyboard job ID: %s", job_id)

    # 4. Poll for completion
    logger.info("Polling Pictory for render completion (up to %d min)...", POLL_MAX_ATTEMPTS * POLL_INTERVAL_SECONDS // 60)
    draft_url = None
    for attempt in range(POLL_MAX_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        status_resp = requests.get(
            f"{PICTORY_BASE}/video/jobs/{job_id}",
            headers=headers,
            timeout=30,
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        status = status_data.get("status", "").lower()
        logger.info("Pictory job status [attempt %d/%d]: %s", attempt + 1, POLL_MAX_ATTEMPTS, status)

        if status in ("done", "completed", "success"):
            draft_url = (
                status_data.get("data", {}).get("projectUrl")
                or status_data.get("projectUrl")
                or status_data.get("videoUrl")
            )
            break
        elif status in ("error", "failed"):
            raise RuntimeError(f"Pictory render failed: {status_data}")

    if not draft_url:
        raise TimeoutError("Pictory render did not complete within the polling window.")

    # 5. Save URL
    output_url_file.parent.mkdir(parents=True, exist_ok=True)
    output_url_file.write_text(draft_url, encoding="utf-8")
    logger.info("Pictory draft URL saved to %s: %s", output_url_file.name, draft_url)
    return draft_url
