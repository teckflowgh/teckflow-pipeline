"""
Stage 1 — Topic Research: YouTube Data API v3
Fetches the top trending videos in a given category and returns
a normalised list of topic dicts for Claude to evaluate.
"""

import logging
import os
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"


def fetch_trending_topics(
    api_key: str,
    category_id: str = "28",
    region_code: str = "US",
    max_results: int = 10,
) -> list[dict]:
    """
    Fetch trending YouTube videos in the given category.

    Returns a list of dicts:
        { title, description, view_count, like_count, tags, channel_title }
    """
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is not set.")

    youtube = build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, developerKey=api_key)

    try:
        response = (
            youtube.videos()
            .list(
                part="snippet,statistics",
                chart="mostPopular",
                regionCode=region_code,
                videoCategoryId=category_id,
                maxResults=max_results,
            )
            .execute()
        )
    except HttpError as e:
        logger.error("YouTube API error: %s", e)
        raise

    topics = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        topics.append(
            {
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:500],
                "channel_title": snippet.get("channelTitle", ""),
                "tags": snippet.get("tags", [])[:10],
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
            }
        )

    logger.info("Fetched %d trending topics from YouTube.", len(topics))
    return topics


def get_top_topics(
    api_key: Optional[str] = None,
    category_id: Optional[str] = None,
    top_n: int = 3,
) -> list[dict]:
    """
    Fetches trending topics relevant to TeckFlow's niche:
    KMO-automatisatie voor Vlaanderen/Nederland.

    Tries category 28 (Science & Tech) first; adds category 22 (People & Blogs)
    as a second pass to broaden entrepreneurship/business content.
    Topics are filtered and ranked by KMO/automation relevance keywords.
    """
    key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
    cat = category_id or os.environ.get("YOUTUBE_CATEGORY_ID", "28")

    all_topics = fetch_trending_topics(api_key=key, category_id=cat)

    # Also pull from business/entrepreneurship category (22 = People & Blogs)
    if cat == "28":
        try:
            business_topics = fetch_trending_topics(api_key=key, category_id="22", max_results=5)
            all_topics.extend(business_topics)
        except Exception:
            pass

    # Score by KMO/automation relevance — topics that Claude can translate into
    # a useful automation insight for SME owners score higher.
    RELEVANCE_KEYWORDS = [
        "ai", "automatisatie", "automation", "workflow", "no-code", "nocode",
        "make", "zapier", "n8n", "chatgpt", "software", "digitaal", "digital",
        "kmo", "sme", "small business", "ondernemer", "entrepreneur", "productiviteit",
        "productivity", "time-saving", "efficiency", "tool", "app", "saas",
        "business", "bedrijf", "crm", "invoice", "facturatie", "planning",
    ]

    def relevance_score(t: dict) -> int:
        text = (t["title"] + " " + t["description"] + " " + " ".join(t["tags"])).lower()
        return sum(1 for kw in RELEVANCE_KEYWORDS if kw in text)

    # Sort: relevance first, then view_count as tiebreaker
    sorted_topics = sorted(
        all_topics,
        key=lambda t: (relevance_score(t), t["view_count"]),
        reverse=True,
    )
    return sorted_topics[:top_n]
