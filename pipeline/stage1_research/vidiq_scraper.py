"""
Stage 1 — Topic Research: VidIQ Scraper (Playwright)
Scrapes trending topic data from the VidIQ dashboard.
This is a FALLBACK — use YouTube API as the primary source.
VidIQ's UI updates can break CSS selectors; maintain accordingly.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

VIDIQ_URL = "https://app.vidiq.com/trending"


def scrape_trending_topics(
    email: Optional[str] = None,
    password: Optional[str] = None,
    top_n: int = 3,
    headless: bool = True,
) -> list[dict]:
    """
    Logs into VidIQ and scrapes trending topic cards.
    Requires VIDIQ_EMAIL and VIDIQ_PASSWORD environment variables.

    Returns list of dicts: { title, score, keywords }
    Falls back to empty list on any failure so the caller can use YouTube data.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        logger.warning("Playwright not installed. Skipping VidIQ scrape.")
        return []

    _email = email or os.environ.get("VIDIQ_EMAIL", "")
    _password = password or os.environ.get("VIDIQ_PASSWORD", "")

    if not _email or not _password:
        logger.warning("VIDIQ_EMAIL / VIDIQ_PASSWORD not set. Skipping VidIQ scrape.")
        return []

    topics: list[dict] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()

            # --- Login ---
            page.goto("https://app.vidiq.com/auth/signin", wait_until="networkidle")
            page.fill("input[name='email']", _email)
            page.fill("input[name='password']", _password)
            page.click("button[type='submit']")
            page.wait_for_url("**/dashboard**", timeout=20_000)
            logger.info("VidIQ login successful.")

            # --- Navigate to trending page ---
            page.goto(VIDIQ_URL, wait_until="networkidle")
            page.wait_for_timeout(3000)

            # --- Extract trending cards ---
            # NOTE: these selectors are approximate and may need updating
            cards = page.query_selector_all("[data-testid='trending-topic-card']")
            if not cards:
                # Broader fallback selector
                cards = page.query_selector_all(".trending-topic, .topic-card")

            for card in cards[:top_n]:
                try:
                    title_el = card.query_selector("h3, .topic-title, [data-testid='topic-title']")
                    score_el = card.query_selector(".score, .trend-score, [data-testid='trend-score']")
                    keyword_els = card.query_selector_all(".keyword, .tag, [data-testid='keyword']")

                    title = title_el.inner_text().strip() if title_el else ""
                    score = score_el.inner_text().strip() if score_el else ""
                    keywords = [k.inner_text().strip() for k in keyword_els]

                    if title:
                        topics.append(
                            {"title": title, "score": score, "keywords": keywords}
                        )
                except Exception as e:
                    logger.debug("Error parsing VidIQ card: %s", e)

            browser.close()

    except Exception as e:
        logger.error("VidIQ scrape failed: %s", e)
        return []

    # Normalise to same format as YouTube data
    normalised = [
        {
            "title": t["title"],
            "description": f"Trending on VidIQ — keywords: {', '.join(t['keywords'])}",
            "channel_title": "VidIQ",
            "tags": t["keywords"],
            "view_count": 0,
            "like_count": 0,
        }
        for t in topics
    ]

    logger.info("Scraped %d topics from VidIQ.", len(normalised))
    return normalised
