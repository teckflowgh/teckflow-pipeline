"""
Download all required model checkpoints.
Run once after cloning the repo:  python scripts/download_models.py

Downloads:
  - SadTalker checkpoints (from GitHub releases)
  - GFPGAN face enhancer checkpoint
  - Wav2Lip GAN checkpoint (fallback)

XTTS v2 weights are downloaded automatically by coqui-tts on first synthesis call.
"""

import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

LIVEPORTRAIT_DIR = BASE_DIR / "third_party" / "LivePortrait"
SADTALKER_DIR = BASE_DIR / "third_party" / "SadTalker"
WAV2LIP_DIR = BASE_DIR / "third_party" / "Wav2Lip"


def download(url: str, dest: Path, label: str) -> None:
    if dest.exists():
        print(f"  [skip] {label} already exists.")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {label}...")
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress)
        print(f"  Saved → {dest}")
    except Exception as e:
        print(f"  ERROR downloading {label}: {e}")
        print(f"  Download manually from: {url}")


def _progress(count, block_size, total_size):
    if total_size > 0:
        pct = min(100, count * block_size * 100 // total_size)
        sys.stdout.write(f"\r  Progress: {pct}%   ")
        sys.stdout.flush()
    if count * block_size >= total_size:
        print()


def download_gdown(gdrive_id: str, dest: Path, label: str) -> None:
    if dest.exists():
        print(f"  [skip] {label} already exists.")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {label} from Google Drive...")
    try:
        import gdown
        gdown.download(id=gdrive_id, output=str(dest), quiet=False)
        print(f"  Saved → {dest}")
    except ImportError:
        print("  gdown not installed. Run: pip install gdown")
    except Exception as e:
        print(f"  ERROR: {e}\n  Download manually: https://drive.google.com/file/d/{gdrive_id}")


SADTALKER_CHECKPOINTS = [
    # (gdrive_file_id, relative_path_inside_SadTalker, label)
    ("1zXoUAMrw_FTBgCbdYVrQYvp8BHbsioTl", "checkpoints/SadTalker_V0.0.2_256.safetensors", "SadTalker 256 weights"),
    ("1OSmDFNxT6jBZxBXyHsrPjbMuHNTsOQIm", "checkpoints/mapping_00109-model.pth.tar", "SadTalker mapping"),
    ("1G4KDs3a-8ue0Sf4pIl9xJjKGMvMcX5lG", "checkpoints/BFM_Fitting/01_MorphableModel.mat", "BFM morphable model"),
]

WAV2LIP_CHECKPOINTS = [
    ("https://github.com/Rudrabha/Wav2Lip/releases/download/v1.0/wav2lip_gan.pth",
     WAV2LIP_DIR / "checkpoints" / "wav2lip_gan.pth",
     "Wav2Lip GAN checkpoint"),
]

GFPGAN_CHECKPOINTS = [
    ("https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
     SADTALKER_DIR / "gfpgan" / "weights" / "GFPGANv1.4.pth",
     "GFPGAN v1.4 face restoration"),
]


def main():
    print("=== Downloading model checkpoints ===\n")

    # --- LivePortrait (primary avatar engine) ---
    if LIVEPORTRAIT_DIR.exists():
        print("LivePortrait pretrained weights:")
        lp_weights_dir = LIVEPORTRAIT_DIR / "pretrained_weights"
        lp_weights_dir.mkdir(parents=True, exist_ok=True)

        # LivePortrait hosts weights on HuggingFace
        # The setup.py / download script inside the repo handles this cleanly
        lp_setup = LIVEPORTRAIT_DIR / "scripts" / "download_models.py"
        if lp_setup.exists():
            print("  Running LivePortrait's own download script...")
            import subprocess
            subprocess.run([sys.executable, str(lp_setup)], check=False)
        else:
            print("  LivePortrait weights are fetched automatically on first run.")
            print("  Or run manually inside third_party/LivePortrait:")
            print("    python scripts/download_models.py")
    else:
        print(f"[WARN] LivePortrait not cloned at {LIVEPORTRAIT_DIR}.")
        print("  Run: git clone https://github.com/KwaiVision/LivePortrait third_party/LivePortrait\n")

    if SADTALKER_DIR.exists():
        print("SadTalker checkpoints:")
        for gdrive_id, rel_path, label in SADTALKER_CHECKPOINTS:
            download_gdown(gdrive_id, SADTALKER_DIR / rel_path, label)
    else:
        print(f"[WARN] SadTalker not cloned at {SADTALKER_DIR}. Skipping its checkpoints.")
        print("       Run: git clone https://github.com/OpenTalker/SadTalker third_party/SadTalker\n")

    print("\nGFPGAN face enhancer:")
    for url, dest, label in GFPGAN_CHECKPOINTS:
        download(url, dest, label)

    if WAV2LIP_DIR.exists():
        print("\nWav2Lip checkpoints (fallback):")
        for url, dest, label in WAV2LIP_CHECKPOINTS:
            download(url, dest, label)
    else:
        print(f"\n[WARN] Wav2Lip not cloned at {WAV2LIP_DIR}. Skipping.")
        print("       Run: git clone https://github.com/Rudrabha/Wav2Lip third_party/Wav2Lip")

    print("\n=== Done. XTTS v2 weights will download automatically on first voice synthesis. ===")


if __name__ == "__main__":
    main()
