"""
Stage 4 — Video Assembler (hoofdmodule)
Ondersteunt twee modi:

  short: 60-sec Short/Reel (9:16)
    - Avatar talking head + B-roll wissels
    - Auto-ondertitels via Whisper
    - Pexels B-roll per scene

  long: 8-15 min YouTube video (16:9)
    - Gestructureerd met hoofdstukken
    - Hoofdstuktitels als tekstoverlay
    - Meer B-roll scenes
    - YouTube metadata opgeslagen
    - Intro/outro met branding
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"
BROLL_CACHE = OUTPUT_DIR / "broll_cache"
BACKGROUND_MUSIC = ASSETS_DIR / "background_music.mp3"

# Videodimensies per modus
VIDEO_DIMENSIONS = {
    "short": (1080, 1920),   # 9:16 portrait
    "long":  (1920, 1080),   # 16:9 landscape
}


def _parse_short_script(script: str, topic: str) -> list[dict]:
    """Verdeelt een kort script (~150w) in 4 scenes."""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', script) if s.strip()]
    chunk_size = max(1, len(sentences) // 4)
    chunks = [" ".join(sentences[i:i + chunk_size]) + "." for i in range(0, len(sentences), chunk_size)]
    stopwords = {"de","het","een","en","van","in","is","dat","te","je","we","ze","op","aan","met","voor","dit","er","zijn","heeft","wordt","ook","al","maar","als","wat"}

    scenes = []
    for chunk in chunks[:4]:
        words = [w.lower().strip(".,!?") for w in chunk.split()]
        keywords = [w for w in words if len(w) > 4 and w not in stopwords][:3]
        scenes.append({
            "text": chunk,
            "keywords": f"{topic} {' '.join(keywords)}",
            "duration": max(5.0, len(chunk.split()) * 0.5),
            "chapter_title": None,
        })
    return scenes


def _parse_long_script(script: str, topic: str, chapters: list[dict] | None = None) -> list[dict]:
    """
    Verdeelt een lang script (~1400w) in scenes per hoofdstuk.
    Detecteert [INTRO], [HOOFDSTUK X: Titel] en [OUTRO] tags.
    """
    stopwords = {"de","het","een","en","van","in","is","dat","te","je","we","ze","op","aan","met","voor","dit","er","zijn","heeft","wordt","ook","al","maar","als","wat","hoe","wil","kan","bij","uit","naar","door"}

    # Splits op hoofdstuk-tags
    parts = re.split(r'\[(INTRO|HOOFDSTUK\s+\d+[:\s][^]]*|OUTRO)\]', script, flags=re.IGNORECASE)

    scenes = []
    current_title = "Intro"

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        # Detecteer of dit een tag is
        tag_match = re.match(r'(INTRO|HOOFDSTUK\s+\d+[:\s].*|OUTRO)', part, re.IGNORECASE)
        if tag_match:
            current_title = tag_match.group(0).strip()
            # Verwijder "HOOFDSTUK X: " prefix voor weergave
            current_title = re.sub(r'^HOOFDSTUK\s+\d+[:\s]+', '', current_title, flags=re.IGNORECASE).strip()
            if current_title.upper() == "INTRO":
                current_title = "Intro"
            elif current_title.upper() == "OUTRO":
                current_title = "Outro"
            continue

        # Verwerk tekstblok: splits in sub-scenes van ~60 woorden elk
        words_all = part.split()
        chunk_size = 60  # ~30 sec per sub-scene bij ~2 woorden/sec
        chunks = [" ".join(words_all[i:i+chunk_size]) for i in range(0, len(words_all), chunk_size) if words_all[i:i+chunk_size]]

        for j, chunk in enumerate(chunks):
            words = [w.lower().strip(".,!?") for w in chunk.split()]
            keywords = [w for w in words if len(w) > 4 and w not in stopwords][:4]
            duration = max(8.0, len(chunk.split()) * 0.5)

            scenes.append({
                "text": chunk,
                "keywords": f"{topic} {' '.join(keywords)}",
                "duration": duration,
                "chapter_title": current_title if j == 0 else None,  # Titel enkel bij eerste chunk van hoofdstuk
            })

    logger.info("Script opgesplitst in %d scenes voor lange video.", len(scenes))
    return scenes


def _save_youtube_metadata(result: dict, output_dir: Path) -> None:
    """Sla YouTube metadata op als JSON bestand."""
    metadata = {
        "title": result.get("youtube_title", ""),
        "description": result.get("youtube_description", ""),
        "tags": result.get("youtube_tags", []),
        "chapters": result.get("chapters", []),
    }
    meta_path = output_dir / "youtube_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("YouTube metadata opgeslagen: %s", meta_path.name)


def assemble_final_video(
    avatar_path: str | Path,
    audio_path: str | Path,
    script: str,
    topic: str,
    output_path: str | Path,
    mode: str = "short",
    script_result: dict | None = None,
    pexels_api_key: str | None = None,
    language: str = "nl",
    use_subtitles: bool = True,
) -> Path:
    """
    Volledige Stage 4 pipeline.

    Args:
        mode: "short" (60-sec 9:16) of "long" (8-15 min 16:9)
        script_result: volledig Claude resultaat dict (voor metadata + chapters)
    """
    avatar_path = Path(avatar_path).resolve()
    audio_path = Path(audio_path).resolve()
    output_path = Path(output_path).resolve()

    _key = pexels_api_key or os.environ.get("PEXELS_API_KEY", "")
    width, height = VIDEO_DIMENSIONS.get(mode, (1080, 1920))

    # --- Stap 1: Script → scenes ---
    logger.info("Script analyseren in scenes (modus: %s)...", mode)
    if mode == "long":
        chapters = script_result.get("chapters") if script_result else None
        scenes = _parse_long_script(script, topic, chapters)
    else:
        scenes = _parse_short_script(script, topic)
    logger.info("%d scenes gevonden.", len(scenes))

    # --- Stap 2: Pexels B-roll ---
    broll_clips = []
    if _key:
        from pipeline.stage4_assembly.pexels_client import fetch_broll_for_scenes
        BROLL_CACHE.mkdir(parents=True, exist_ok=True)
        logger.info("B-roll ophalen voor %d scenes...", len(scenes))
        broll_clips = fetch_broll_for_scenes(
            scenes=scenes,
            api_key=_key,
            output_dir=BROLL_CACHE,
        )
        found = sum(1 for c in broll_clips if c is not None)
        logger.info("B-roll: %d/%d clips gevonden.", found, len(scenes))
    else:
        broll_clips = [None] * len(scenes)

    while len(broll_clips) < len(scenes):
        broll_clips.append(None)

    # --- Stap 3: Whisper ondertitels ---
    subtitle_path = None
    if use_subtitles:
        try:
            from pipeline.stage4_assembly.whisper_subtitles import generate_subtitles
            srt_path = OUTPUT_DIR / "subtitles.srt"
            subtitle_path = generate_subtitles(
                audio_path=audio_path,
                output_path=srt_path,
                language=language,
                model_size="base" if mode == "short" else "small",
            )
            logger.info("Ondertitels gegenereerd: %s", srt_path.name)
        except Exception as e:
            logger.warning("Whisper mislukt: %s — verder zonder ondertitels.", e)

    # --- Stap 4: FFmpeg montage ---
    from pipeline.stage4_assembly.ffmpeg_editor import assemble_video

    scene_durations = [s["duration"] for s in scenes]
    chapter_titles = [s.get("chapter_title") for s in scenes]
    music = BACKGROUND_MUSIC if BACKGROUND_MUSIC.exists() else None

    logger.info("Video monteren met FFmpeg (modus: %s, %dx%d)...", mode, width, height)
    final_path = assemble_video(
        avatar_path=avatar_path,
        audio_path=audio_path,
        broll_clips=broll_clips,
        scene_durations=scene_durations,
        subtitle_path=subtitle_path,
        output_path=output_path,
        background_music=music,
        music_volume=0.05 if mode == "long" else 0.08,
        output_width=width,
        output_height=height,
        chapter_titles=chapter_titles if mode == "long" else None,
    )

    # --- Stap 5: YouTube metadata opslaan (long only) ---
    if mode == "long" and script_result:
        _save_youtube_metadata(script_result, OUTPUT_DIR)

    logger.info("Stage 4 klaar: %s (modus: %s)", final_path.name, mode)
    return final_path
