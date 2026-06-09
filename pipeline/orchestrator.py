"""
Pipeline Orchestrator
Runs all 5 stages in sequence, maintains run_history.json,
and cleans up old output files.
"""

import json
import logging
import logging.handlers
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
HISTORY_FILE = DATA_DIR / "run_history.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

REFERENCE_VOICE = ASSETS_DIR / "reference_voice.wav"
REFERENCE_CLIP = ASSETS_DIR / "reference_clip.mp4"   # video-based avatar (preferred)
AVATAR_IMAGE = ASSETS_DIR / "avatar_image.jpg"        # fallback: still image
SPEECH_OUTPUT = OUTPUT_DIR / "generated_speech.mp3"
AVATAR_OUTPUT = OUTPUT_DIR / "avatar_talking.mp4"
FINAL_VIDEO = OUTPUT_DIR / "final_video.mp4"
DRAFT_URL_FILE = OUTPUT_DIR / "final_draft_url.txt"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "pipeline.log"
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    # Also log to console
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)


# ---------------------------------------------------------------------------
# Run history helpers
# ---------------------------------------------------------------------------

def _load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(history: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    # Cap at max_entries
    try:
        with SETTINGS_FILE.open(encoding="utf-8") as f:
            settings = json.load(f)
        max_entries = int(settings.get("history_max_entries", 365))
    except Exception:
        max_entries = 365
    history = history[-max_entries:]
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _upsert_run(record: dict) -> None:
    history = _load_history()
    for i, r in enumerate(history):
        if r.get("run_id") == record["run_id"]:
            history[i] = record
            break
    else:
        history.append(record)
    _save_history(history)


def get_latest_run() -> dict | None:
    history = _load_history()
    return history[-1] if history else None


# ---------------------------------------------------------------------------
# Cleanup old output files
# ---------------------------------------------------------------------------

def _cleanup_old_outputs() -> None:
    try:
        with SETTINGS_FILE.open(encoding="utf-8") as f:
            settings = json.load(f)
        days = int(settings.get("cleanup_days", 7))
    except Exception:
        days = 7

    cutoff = time.time() - days * 86400
    for p in OUTPUT_DIR.glob("*"):
        if p.suffix in (".mp3", ".mp4", ".wav", ".txt") and p.stat().st_mtime < cutoff:
            p.unlink(missing_ok=True)
            logger.info("Cleaned up old file: %s", p.name)


# ---------------------------------------------------------------------------
# Startup recovery: mark any dangling 'running' records as failed
# ---------------------------------------------------------------------------

def recover_stale_runs() -> None:
    history = _load_history()
    changed = False
    for r in history:
        if r.get("status") == "running":
            r["status"] = "failed"
            r["error"] = "Process was restarted mid-run."
            changed = True
    if changed:
        _save_history(history)
        logger.warning("Marked stale running records as failed.")


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(run_id: str | None = None) -> dict:
    setup_logging()

    if run_id is None:
        run_id = str(uuid.uuid4())[:8]

    now = datetime.now(timezone.utc).isoformat()
    record: dict = {
        "run_id": run_id,
        "started_at": now,
        "finished_at": None,
        "status": "running",
        "current_stage": "init",
        "topic": None,
        "script_preview": None,
        "pictory_draft_url": None,
        "stage_timings": {},
        "error": None,
    }
    _upsert_run(record)

    def _stage(name: str):
        record["current_stage"] = name
        _upsert_run(record)
        return time.time()

    def _done(name: str, t0: float):
        record["stage_timings"][name] = round(time.time() - t0, 1)
        _upsert_run(record)

    # Load settings
    try:
        with SETTINGS_FILE.open(encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        settings = {}

    topic_source = settings.get("topic_source", os.environ.get("TOPIC_SOURCE", "youtube"))
    language = settings.get("script_language", os.environ.get("SCRIPT_LANGUAGE", "nl"))
    use_gpu = os.environ.get("USE_GPU", "true").lower() in ("true", "1", "yes")
    video_mode = settings.get("video_mode", "short")  # "short" of "long"

    logger.info("Video modus: %s", video_mode)

    try:
        # --- Stage 1: Research ---
        t0 = _stage("stage1_research")
        from pipeline.stage1_research.youtube_trending import get_top_topics
        from pipeline.stage1_research.vidiq_scraper import scrape_trending_topics
        from pipeline.stage1_research.claude_selector import select_topic_and_write_script

        topics = []
        if topic_source == "vidiq":
            topics = scrape_trending_topics(top_n=3)
        if not topics:  # primary or fallback
            topics = get_top_topics(top_n=3)

        result = select_topic_and_write_script(topics, language=language, mode=video_mode)
        chosen_topic = result["chosen_topic"]
        script = result["script"]
        record["topic"] = chosen_topic
        record["script_preview"] = script[:200]
        record["video_mode"] = video_mode
        _done("stage1_research", t0)
        logger.info("Stage 1 complete. Topic: %s", chosen_topic)

        # --- Stage 2: Voice synthesis ---
        t0 = _stage("stage2_voice")
        from pipeline.stage2_voice.xtts_synthesizer import synthesize_speech
        synthesize_speech(
            script=script,
            reference_wav=REFERENCE_VOICE,
            output_path=SPEECH_OUTPUT,
            language=language,
            use_gpu=use_gpu,
        )
        _done("stage2_voice", t0)
        logger.info("Stage 2 complete. Audio: %s", SPEECH_OUTPUT.name)

        # --- Stage 3: Avatar video ---
        # Priority: LivePortrait (video ref) → SadTalker (image ref) → Wav2Lip (image ref)
        t0 = _stage("stage3_avatar")

        if REFERENCE_CLIP.exists():
            # Best quality: drive your own video clip with the generated audio
            try:
                from pipeline.stage3_avatar.liveportrait_runner import generate_avatar_video
                generate_avatar_video(
                    audio_path=SPEECH_OUTPUT,
                    reference_clip=REFERENCE_CLIP,
                    output_path=AVATAR_OUTPUT,
                    use_gpu=use_gpu,
                )
                logger.info("Stage 3 complete via LivePortrait.")
            except Exception as lp_err:
                logger.warning("LivePortrait failed (%s). Trying Wav2Lip fallback...", lp_err)
                from pipeline.stage3_avatar.wav2lip_runner import generate_avatar_video_wav2lip
                generate_avatar_video_wav2lip(
                    audio_path=SPEECH_OUTPUT,
                    image_path=REFERENCE_CLIP,   # Wav2Lip also accepts video as --face
                    output_path=AVATAR_OUTPUT,
                )
                logger.info("Stage 3 complete via Wav2Lip (video input).")
        else:
            # Fallback: still image → SadTalker → Wav2Lip
            logger.warning(
                "No reference_clip.mp4 found. Falling back to still-image mode. "
                "For best results, record a 5-10 sec clip and save to assets/reference_clip.mp4"
            )
            try:
                from pipeline.stage3_avatar.sadtalker_runner import generate_avatar_video as st_gen
                st_gen(
                    audio_path=SPEECH_OUTPUT,
                    image_path=AVATAR_IMAGE,
                    output_path=AVATAR_OUTPUT,
                    use_gpu=use_gpu,
                )
                logger.info("Stage 3 complete via SadTalker (still image).")
            except Exception as sadtalker_err:
                logger.warning("SadTalker failed (%s). Trying Wav2Lip...", sadtalker_err)
                from pipeline.stage3_avatar.wav2lip_runner import generate_avatar_video_wav2lip
                generate_avatar_video_wav2lip(
                    audio_path=SPEECH_OUTPUT,
                    image_path=AVATAR_IMAGE,
                    output_path=AVATAR_OUTPUT,
                )
                logger.info("Stage 3 complete via Wav2Lip (still image).")

        _done("stage3_avatar", t0)
        logger.info("Stage 3 complete. Video: %s", AVATAR_OUTPUT.name)

        # --- Stage 4: Video montage (Pexels + Whisper + FFmpeg) ---
        t0 = _stage("stage4_assembly")
        from pipeline.stage4_assembly.video_assembler import assemble_final_video
        final_video = assemble_final_video(
            avatar_path=AVATAR_OUTPUT,
            audio_path=SPEECH_OUTPUT,
            script=script,
            topic=chosen_topic,
            output_path=FINAL_VIDEO,
            mode=video_mode,
            script_result=result,
            language=language,
        )
        record["final_video_path"] = str(final_video)
        _done("stage4_assembly", t0)
        logger.info("Stage 4 klaar. Finale video: %s", final_video.name)

        # --- Finalise ---
        record["status"] = "completed"
        record["current_stage"] = "done"
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        _upsert_run(record)
        _cleanup_old_outputs()
        logger.info("Pipeline completed successfully. run_id=%s", run_id)

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("Pipeline failed at stage '%s': %s\n%s", record.get("current_stage"), exc, tb)
        record["status"] = "failed"
        record["error"] = f"{exc}\n\n{tb}"[-2000:]
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        _upsert_run(record)
        raise

    return record
