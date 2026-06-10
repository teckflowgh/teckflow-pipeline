"""
Stage 3 — Eenvoudige Avatar (betrouwbare fallback)
Maakt een talking-head video door je referentieclip te lussen tot de lengte
van de gegenereerde stem. Geen lip-sync, maar 100% betrouwbaar en snel —
ideaal om de pijplijn end-to-end werkend te krijgen.

Upgrade-pad: vervang door Wav2Lip/SadTalker/LivePortrait voor echte lip-sync.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def generate_simple_avatar(
    audio_path: str | Path,
    reference_clip: str | Path,
    output_path: str | Path,
) -> Path:
    """
    Lust de referentieclip tot de audio-lengte en zet de stem eronder.
    """
    audio_path = Path(audio_path).resolve()
    reference_clip = Path(reference_clip).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not reference_clip.exists():
        raise FileNotFoundError(f"Referentieclip niet gevonden: {reference_clip}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio niet gevonden: {audio_path}")

    audio_dur = _ffprobe_duration(audio_path)
    if audio_dur <= 0:
        audio_dur = 60.0

    logger.info("Eenvoudige avatar: clip lussen tot %.1fs", audio_dur)

    # Lus de video, knip op audio-lengte, plak de stem eronder
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(reference_clip),  # video oneindig lussen
        "-i", str(audio_path),                             # stem
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("ffmpeg avatar fout:\n%s", proc.stderr[-1500:])
        raise RuntimeError(f"Eenvoudige avatar mislukt: {proc.stderr[-300:]}")

    size_mb = output_path.stat().st_size // (1024 * 1024)
    logger.info("Avatar-video klaar: %s (%d MB)", output_path.name, size_mb)
    return output_path
