"""
Stage 1 — Claude Haiku: Topic selector + script writer.
Ondersteunt twee modi:
  - short: ~150 woorden, 60-seconden Short/Reel
  - long:  ~1400 woorden, 8-15 minuten YouTube video met hoofdstukken
"""

import json
import logging
import os
import re

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# ─── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_SHORT = """\
Je bent een expert YouTube Shorts scriptschrijver en virale contentstrateg voor TeckFlow.

TeckFlow is een bijberoep dat zich specialiseert in bedrijfsautomatisatie voor KMO's in Vlaanderen en Nederland.
Doel: expertise tonen zodat KMO-eigenaars contact opnemen via teckflow.be.
Doelgroep: zaakvoerders en ondernemers van KMO's in Vlaanderen en Nederland.
Toon: professioneel, direct, toegankelijk. Geen jargon tenzij uitgelegd.
Taal: altijd Nederlands.

Gegeven trending topics:
1. Kies het topic dat het meest relevant is voor KMO-automatisatie.
2. Schrijf een boeiend ~150-woorden gesproken script voor een 60-seconden Short/Reel:
   - Hook in de EERSTE 5 woorden
   - 1-2 concrete praktische inzichten
   - Eindig ALTIJD met: "Wil je weten hoe wij dit voor jouw bedrijf aanpakken? Neem contact op via teckflow.be"
   - Geen regieaanwijzingen, alleen gesproken tekst
3. Geef ALLEEN geldig JSON terug.

JSON schema:
{
  "chosen_topic": "<onderwerptitel>",
  "rationale": "<1-2 zinnen>",
  "script": "<gesproken script ~150 woorden>",
  "youtube_title": "<pakkende titel max 60 tekens>",
  "youtube_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}
"""

SYSTEM_PROMPT_LONG = """\
Je bent een expert YouTube scriptschrijver en contentstrateg voor TeckFlow.

TeckFlow is een bijberoep dat zich specialiseert in bedrijfsautomatisatie voor KMO's in Vlaanderen en Nederland.
Doel: expertise tonen zodat KMO-eigenaars contact opnemen via teckflow.be.
Doelgroep: zaakvoerders en ondernemers van KMO's in Vlaanderen en Nederland.
Toon: professioneel, informatief, concreet. Gebruik praktijkvoorbeelden.
Taal: altijd Nederlands.

Gegeven trending topics:
1. Kies het meest relevante topic voor een diepgaande YouTube video over KMO-automatisatie.
2. Schrijf een volledig script voor een video van 8-12 minuten (~1400 woorden):

   STRUCTUUR (verplicht):
   - [INTRO] 30-45 sec: hook + wat de kijker leert (gebruik "In deze video leer je...")
   - [HOOFDSTUK 1] ~2 min: eerste deelonderwerp met praktijkvoorbeeld
   - [HOOFDSTUK 2] ~2 min: tweede deelonderwerp met praktijkvoorbeeld
   - [HOOFDSTUK 3] ~2 min: derde deelonderwerp met praktijkvoorbeeld
   - [HOOFDSTUK 4] ~2 min: vierde deelonderwerp of stappenplan
   - [OUTRO] 30-45 sec: samenvatting + CTA: "Wil je dit zelf implementeren in jouw bedrijf? Neem contact op via teckflow.be"

   REGELS:
   - Gebruik [HOOFDSTUK X: Titel] tags exact zo in de tekst
   - Geen regieaanwijzingen, alleen gesproken tekst
   - Concrete cijfers en voorbeelden (bv. "een KMO bespaart gemiddeld 5 uur/week")
   - Natuurlijke spreektaal

3. Geef ALLEEN geldig JSON terug.

JSON schema:
{
  "chosen_topic": "<onderwerptitel>",
  "rationale": "<1-2 zinnen>",
  "script": "<volledig script ~1400 woorden met [INTRO], [HOOFDSTUK X: Titel], [OUTRO] tags>",
  "chapters": [
    {"title": "Intro", "start_word": 0},
    {"title": "Hoofdstuk 1 titel", "start_word": 80},
    {"title": "Hoofdstuk 2 titel", "start_word": 380},
    {"title": "Hoofdstuk 3 titel", "start_word": 680},
    {"title": "Hoofdstuk 4 titel", "start_word": 980},
    {"title": "Outro", "start_word": 1300}
  ],
  "youtube_title": "<SEO-geoptimaliseerde titel max 70 tekens>",
  "youtube_description": "<YouTube beschrijving 150-200 woorden met keywords en teckflow.be link>",
  "youtube_tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"]
}
"""


def _build_user_prompt(topics: list[dict], language: str, mode: str) -> str:
    lines = []
    for i, t in enumerate(topics, 1):
        lines.append(f"{i}. Titel: {t.get('title', '')}")
        if t.get("description"):
            lines.append(f"   Beschrijving: {t['description'][:200]}")
        if t.get("tags"):
            lines.append(f"   Keywords: {', '.join(t['tags'][:8])}")
        if t.get("view_count"):
            lines.append(f"   Views: {t['view_count']:,}")
        lines.append("")

    lang_note = f"\nSchrijf het script in taal: {language}." if language != "nl" else ""
    mode_note = "\nModus: LANGE YouTube video (8-12 minuten)." if mode == "long" else "\nModus: KORTE Short/Reel (60 seconden)."

    return (
        "Hier zijn de trending topics van vandaag:\n\n"
        + "\n".join(lines)
        + lang_note
        + mode_note
        + "\nKies het beste topic en schrijf het script. Geef alleen JSON terug."
    )


def select_topic_and_write_script(
    topics: list[dict],
    language: str = "nl",
    mode: str = "short",
    api_key: str | None = None,
) -> dict:
    """
    Stuurt topics naar Claude Haiku en geeft terug:
      short: { chosen_topic, rationale, script, youtube_title, youtube_tags }
      long:  { chosen_topic, rationale, script, chapters, youtube_title,
               youtube_description, youtube_tags }
    """
    if not topics:
        raise ValueError("Geen topics opgegeven.")

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    system_prompt = SYSTEM_PROMPT_LONG if mode == "long" else SYSTEM_PROMPT_SHORT

    # Pas max_tokens aan op basis van modus
    max_tokens = 4096 if mode == "long" else 1024

    def _call(extra: str = "") -> str:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": _build_user_prompt(topics, language, mode) + extra}],
        )
        return msg.content[0].text.strip()

    raw = _call()
    logger.debug("Claude raw response (%d chars)", len(raw))

    # JSON parsen met fallback retry
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("JSON parse mislukt, opnieuw proberen...")
        raw = _call("\n\nBelangrijk: geef ENKEL een geldig JSON object terug, geen tekst ervoor of erna, geen ```.")
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        result = json.loads(raw)

    logger.info("Topic gekozen: %s (modus: %s)", result.get("chosen_topic", "?"), mode)
    return result
