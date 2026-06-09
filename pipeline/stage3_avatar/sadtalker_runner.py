"""
Stage 3 — Avatar Generation: SadTalker
Drives a still portrait image with synthesized audio to produce
a talking-head video via the SadTalker subprocess.

SadTalker has no pip package; it runs from its cloned repo directory.
Clone it at:  third_party/SadTalker
Checkpoints:  run scripts/download_models.py
"""

import glob
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_avatar_video(
    audio_path: str | Path,
    image_path: str | Path,
    output_path: str | Path,
    sadtalker_dir: str | Path | None = None,
    use_enhancer: bool = True,
    use_gpu: bool | None = None,
) -> Path:
    """
    Run SadTalker to produce a talking-avatar video.

    Args:
        audio_path:     Path to generated_speech.mp3 (Stage 2 output).
        image_path:     Path to avatar_image.jpg.
        output_path:    Desired path for avatar_talking.mp4.
        sadtalker_dir:  Root of the SadTalker clone (defaults to env SADTALKER_PATH).
        use_enhancer:   Apply GFPGAN face restoration (sharper, needs extra VRAM).
        use_gpu:        Defaults to USE_GPU env var.

    Returns:
        Path to the generated MP4 file.
    """
    audio_path = Path(audio_path).resolve()
    image_path = Path(image_path).resolve()
    output_path = Path(output_path).resolve()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if not image_path.exists():
        raise FileNotFoundError(
            f"Avatar image not found: {image_path}\n"
            "Place a 512x512+ frontal face photo at assets/avatar_image.jpg"
        )

    if use_gpu is None:
        use_gpu = os.environ.get("USE_GPU", "true").lower() in ("true", "1", "yes")

    sad_dir = Path(
        sadtalker_dir
        or os.environ.get("SADTALKER_PATH", "third_party/SadTalker")
    ).resolve()

    if not sad_dir.exists():
        raise FileNotFoundError(
            f"SadTalker directory not found: {sad_dir}\n"
            "Run: git clone https://github.com/OpenTalker/SadTalker third_party/SadTalker"
        )

    result_dir = output_path.parent
    result_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "inference.py",
        "--driven_audio", str(audio_path),
        "--source_image", str(image_path),
        "--result_dir", str(result_dir),
        "--still",
        "--preprocess", "full",
    ]
    if use_enhancer:
        cmd += ["--enhancer", "gfpgan"]
    if not use_gpu:
        cmd += ["--cpu"]

    logger.info("Running SadTalker: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        cwd=str(sad_dir),
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        logger.error("SadTalker stderr:\n%s", proc.stderr[-2000:])
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)

    # SadTalker writes a timestamped filename; find the newest mp4 in result_dir
    mp4_files = sorted(
        glob.glob(str(result_dir / "*.mp4")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not mp4_files:
        raise RuntimeError("SadTalker completed but no .mp4 found in output directory.")

    latest = Path(mp4_files[0])
    if latest != output_path:
        shutil.move(str(latest), str(output_path))

    size_mb = output_path.stat().st_size // (1024 * 1024)
    logger.info("Avatar video generated: %s (%d MB)", output_path.name, size_mb)
    return output_path
