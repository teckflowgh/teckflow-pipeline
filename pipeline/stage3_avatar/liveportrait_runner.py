"""
Stage 3 — Avatar Generation: LivePortrait
Drives a short reference video clip of yourself with the synthesized audio.
Much more realistic than a still-image approach — your natural head movements,
blinking and expressions are preserved; only the lip sync is driven by the audio.

Clone at:  third_party/LivePortrait
  git clone https://github.com/KwaiVision/LivePortrait third_party/LivePortrait

Checkpoints:  run scripts/download_models.py
  (downloads to third_party/LivePortrait/pretrained_weights/)

Reference clip requirements:
  - 5-10 seconds of yourself looking straight into the camera
  - Good lighting, neutral background
  - MP4 or MOV, minimum 512x512
  - Saved at: assets/reference_clip.mp4
"""

import glob
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

LIVEPORTRAIT_DIR_DEFAULT = "third_party/LivePortrait"
REFERENCE_CLIP_DEFAULT = "assets/reference_clip.mp4"


def generate_avatar_video(
    audio_path: str | Path,
    reference_clip: str | Path | None = None,
    output_path: str | Path = "output/avatar_talking.mp4",
    liveportrait_dir: str | Path | None = None,
    use_gpu: bool | None = None,
) -> Path:
    """
    Run LivePortrait to lip-sync your reference video clip with the generated audio.

    Args:
        audio_path:       Path to generated_speech.mp3 (Stage 2 output).
        reference_clip:   Path to your 5-10 sec reference video (assets/reference_clip.mp4).
        output_path:      Desired output path for avatar_talking.mp4.
        liveportrait_dir: LivePortrait clone directory.
        use_gpu:          Defaults to USE_GPU env var.

    Returns:
        Path to the generated MP4.
    """
    audio_path = Path(audio_path).resolve()
    reference_clip = Path(
        reference_clip or os.environ.get("REFERENCE_CLIP", REFERENCE_CLIP_DEFAULT)
    ).resolve()
    output_path = Path(output_path).resolve()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if not reference_clip.exists():
        raise FileNotFoundError(
            f"Reference clip not found: {reference_clip}\n"
            "Record a 5-10 second video of yourself looking straight into the camera\n"
            "and save it at assets/reference_clip.mp4"
        )

    if use_gpu is None:
        use_gpu = os.environ.get("USE_GPU", "true").lower() in ("true", "1", "yes")

    lp_dir = Path(
        liveportrait_dir
        or os.environ.get("LIVEPORTRAIT_PATH", LIVEPORTRAIT_DIR_DEFAULT)
    ).resolve()

    if not lp_dir.exists():
        raise FileNotFoundError(
            f"LivePortrait directory not found: {lp_dir}\n"
            "Run: git clone https://github.com/KwaiVision/LivePortrait third_party/LivePortrait"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # LivePortrait inference script
    # --source: your reference video clip
    # --driving_audio: the generated speech MP3
    # --output_dir: where to save the result
    cmd = [
        sys.executable,
        "inference.py",
        "--source", str(reference_clip),
        "--driving_audio", str(audio_path),
        "--output_dir", str(output_path.parent),
        "--flag_relative_motion",          # preserve natural head movement scale
        "--flag_remap_input",              # remap lip motion to match audio
        "--flag_stitching",                # seamless face stitching
    ]

    if not use_gpu:
        cmd += ["--flag_force_cpu"]

    logger.info("Running LivePortrait: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        cwd=str(lp_dir),
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        logger.error("LivePortrait stderr:\n%s", proc.stderr[-3000:])
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, proc.stdout, proc.stderr
        )

    # LivePortrait writes a timestamped output — find the newest mp4
    mp4_files = sorted(
        glob.glob(str(output_path.parent / "*.mp4")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not mp4_files:
        raise RuntimeError(
            "LivePortrait completed but no .mp4 found in output directory."
        )

    latest = Path(mp4_files[0])
    if latest.resolve() != output_path.resolve():
        shutil.move(str(latest), str(output_path))

    size_mb = output_path.stat().st_size // (1024 * 1024)
    logger.info(
        "LivePortrait avatar video generated: %s (%d MB)", output_path.name, size_mb
    )
    return output_path
