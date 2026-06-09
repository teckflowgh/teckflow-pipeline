"""
Stage 3 — Avatar Generation: Wav2Lip (fallback)
Used when SadTalker fails or is unavailable.
Clone at:  third_party/Wav2Lip
Checkpoint: checkpoints/wav2lip_gan.pth (download from Wav2Lip releases)
"""

import glob
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_avatar_video_wav2lip(
    audio_path: str | Path,
    image_path: str | Path,
    output_path: str | Path,
    wav2lip_dir: str | Path | None = None,
    checkpoint: str = "checkpoints/wav2lip_gan.pth",
) -> Path:
    """
    Run Wav2Lip to lip-sync a portrait image to audio.

    Args:
        audio_path:   Path to the generated speech MP3.
        image_path:   Path to the avatar face image.
        output_path:  Desired path for the output MP4.
        wav2lip_dir:  Wav2Lip clone directory (env WAV2LIP_PATH or third_party/Wav2Lip).
        checkpoint:   Relative path to the Wav2Lip checkpoint inside wav2lip_dir.

    Returns:
        Path to the generated MP4 file.
    """
    audio_path = Path(audio_path).resolve()
    image_path = Path(image_path).resolve()
    output_path = Path(output_path).resolve()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if not image_path.exists():
        raise FileNotFoundError(f"Avatar image not found: {image_path}")

    w2l_dir = Path(
        wav2lip_dir or os.environ.get("WAV2LIP_PATH", "third_party/Wav2Lip")
    ).resolve()

    if not w2l_dir.exists():
        raise FileNotFoundError(
            f"Wav2Lip directory not found: {w2l_dir}\n"
            "Run: git clone https://github.com/Rudrabha/Wav2Lip third_party/Wav2Lip"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "inference.py",
        "--checkpoint_path", checkpoint,
        "--face", str(image_path),
        "--audio", str(audio_path),
        "--outfile", str(output_path),
    ]

    logger.info("Running Wav2Lip: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        cwd=str(w2l_dir),
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        logger.error("Wav2Lip stderr:\n%s", proc.stderr[-2000:])
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)

    if not output_path.exists():
        # Check for default output filename Wav2Lip sometimes uses
        defaults = sorted(glob.glob(str(w2l_dir / "results" / "*.mp4")), key=os.path.getmtime, reverse=True)
        if defaults:
            shutil.move(defaults[0], str(output_path))
        else:
            raise RuntimeError("Wav2Lip completed but output file not found.")

    size_mb = output_path.stat().st_size // (1024 * 1024)
    logger.info("Wav2Lip avatar video generated: %s (%d MB)", output_path.name, size_mb)
    return output_path
