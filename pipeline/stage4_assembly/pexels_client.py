"""
Stage 4 — Pexels B-roll Client
Zoekt automatisch relevante stockvideo's op via de gratis Pexels API
op basis van keywords uit het script.

Gratis API key aanvragen: https://www.pexels.com/api/
Geen limieten, commercieel gebruik toegestaan, geen watermark.
"""

import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PEXELS_API = "https://api.pexels.com/videos"


def _get_headers(api_key: str) -> dict:
    return {"Authorization": api_key}


def search_broll(
    query: str,
    api_key: str,
    min_duration: int = 5,
    max_duration: int = 15,
    orientation: str = "portrait",  # portrait = 9:16 voor Shorts/Reels
    per_page: int = 5,
) -> list[dict]:
    """
    Zoekt B-roll video's op Pexels voor een gegeven zoekterm.
    Geeft een lijst van video-dicts terug met download URL.
    """
    params = {
        "query": query,
        "orientation": orientation,
        "size": "medium",
        "per_page": per_page,
    }

    try:
        resp = requests.get(
            f"{PEXELS_API}/search",
            headers=_get_headers(api_key),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except Exception as e:
        logger.warning("Pexels zoekopdracht mislukt voor '%s': %s", query, e)
        return []

    results = []
    for v in videos:
        duration = v.get("duration", 0)
        if not (min_duration <= duration <= max_duration):
            continue

        # Kies de beste resolutie: HD portrait of landscape
        best_file = None
        for f in v.get("video_files", []):
            w, h = f.get("width", 0), f.get("height", 0)
            # Liefst portrait HD (1080x1920) of landscape (1920x1080)
            if w >= 720:
                if best_file is None or f.get("width", 0) > best_file.get("width", 0):
                    best_file = f

        if best_file:
            results.append({
                "id": v["id"],
                "duration": duration,
                "url": best_file["link"],
                "width": best_file.get("width"),
                "height": best_file.get("height"),
                "query": query,
            })

    logger.info("Pexels: %d resultaten voor '%s'", len(results), query)
    return results


def download_broll(
    videos: list[dict],
    output_dir: Path,
    max_clips: int = 1,
) -> list[Path]:
    """
    Download B-roll clips naar output_dir.
    Geeft lijst van gedownloade bestandspaden terug.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for v in videos[:max_clips]:
        dest = output_dir / f"broll_{v['id']}.mp4"
        if dest.exists():
            downloaded.append(dest)
            continue

        try:
            logger.info("Downloaden B-roll %s (%dx%d, %ds)...",
                        v['id'], v.get('width', 0), v.get('height', 0), v['duration'])
            with requests.get(v["url"], stream=True, timeout=60) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 64):
                        f.write(chunk)
            downloaded.append(dest)
        except Exception as e:
            logger.warning("Download mislukt voor clip %s: %s", v['id'], e)

    return downloaded


def fetch_broll_for_scenes(
    scenes: list[dict],
    api_key: str,
    output_dir: Path,
) -> list[Path | None]:
    """
    Haalt voor elke scene één passende B-roll clip op.
    scenes = [{"keywords": "automatisatie software", "duration": 8}, ...]
    Geeft lijst terug van Path of None (als geen clip gevonden).
    """
    clips = []
    for scene in scenes:
        keywords = scene.get("keywords", "")
        duration = scene.get("duration", 8)

        # Probeer eerst specifieke zoekterm, dan algemenere term
        videos = search_broll(
            query=keywords,
            api_key=api_key,
            min_duration=max(3, duration - 3),
            max_duration=duration + 5,
        )

        # Fallback: bredere zoekterm
        if not videos:
            fallback = keywords.split()[0] if keywords else "business technology"
            videos = search_broll(query=fallback, api_key=api_key)

        if videos:
            paths = download_broll(videos, output_dir, max_clips=1)
            clips.append(paths[0] if paths else None)
        else:
            clips.append(None)

        time.sleep(0.3)  # Pexels rate limiting respect

    return clips
