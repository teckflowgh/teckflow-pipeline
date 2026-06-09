#!/usr/bin/env bash
# ============================================================
# TeckFlow Video Pipeline — Cloud GPU Bootstrap
# Getest op: RunPod PyTorch 2.4 template (Ubuntu 22.04, CUDA 12.4)
# GPU aanbeveling: RTX 3090 24GB (~€0.20/uur)
#
# Stack:
#   Stem:   F5-TTS (sneller en beter dan XTTS v2)
#   Avatar: MuseTalk (sneller dan SadTalker/LivePortrait)
#   B-roll: Wan2.2 5B (open-source AI video generatie)
#   Subs:   Whisper
#   Edit:   FFmpeg
# ============================================================

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "=== TeckFlow Video Pipeline — Cloud GPU Setup ==="
echo "Project: $PROJECT_DIR"

# --- Systeem packages ---
apt-get update -qq
apt-get install -y -qq ffmpeg libsm6 libxext6 git curl wget unzip aria2

# --- Python dependencies ---
echo ""
echo ">>> PyTorch CUDA 12.4 installeren..."
pip install -q torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124

echo ">>> Core requirements installeren..."
pip install -q fastapi uvicorn pydantic pydantic-settings python-dotenv apscheduler \
    requests httpx anthropic google-api-python-client aiofiles python-multipart \
    rich gdown numpy==1.26.4 scipy

echo ">>> Playwright installeren..."
pip install -q playwright
playwright install chromium --with-deps

echo ">>> Whisper installeren..."
pip install -q openai-whisper

echo ">>> pydub installeren..."
pip install -q pydub

# --- F5-TTS (stem synthese) ---
echo ""
echo ">>> F5-TTS installeren..."
pip install -q git+https://github.com/SWivid/F5-TTS.git 2>/dev/null || \
    pip install -q f5-tts 2>/dev/null || \
    echo "WARN: F5-TTS installatie mislukt, fallback naar XTTS v2"

# Fallback: XTTS v2
if ! python -c "import f5_tts" 2>/dev/null; then
    echo ">>> F5-TTS niet beschikbaar, XTTS v2 installeren als fallback..."
    pip install -q TTS
fi

# --- MuseTalk klonen ---
echo ""
echo ">>> MuseTalk klonen..."
if [ ! -d "third_party/MuseTalk/.git" ]; then
    git clone https://github.com/TMElyralab/MuseTalk third_party/MuseTalk
    pip install -q -r third_party/MuseTalk/requirements.txt 2>/dev/null || true
else
    echo "[skip] MuseTalk al gekloond."
fi

# --- Wan2.2 klonen ---
echo ""
echo ">>> Wan2.2 klonen..."
if [ ! -d "third_party/Wan2.2/.git" ]; then
    git clone https://github.com/Wan-Video/Wan2.2 third_party/Wan2.2
    pip install -q -r third_party/Wan2.2/requirements.txt 2>/dev/null || true
else
    echo "[skip] Wan2.2 al gekloond."
fi

# --- SadTalker als fallback avatar ---
echo ""
echo ">>> SadTalker klonen (fallback)..."
if [ ! -d "third_party/SadTalker/.git" ]; then
    git clone https://github.com/OpenTalker/SadTalker third_party/SadTalker
fi

# --- Model checkpoints downloaden ---
echo ""
echo ">>> Model checkpoints downloaden..."
python scripts/download_models.py

# --- MuseTalk checkpoints ---
echo ">>> MuseTalk checkpoints downloaden..."
MUSETALK_CKPT="third_party/MuseTalk/models"
mkdir -p "$MUSETALK_CKPT"
if [ ! -f "$MUSETALK_CKPT/musetalk.json" ]; then
    cd third_party/MuseTalk
    python -c "
import os
try:
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id='TMElyralab/MuseTalk', local_dir='models')
    print('MuseTalk modellen gedownload.')
except Exception as e:
    print(f'MuseTalk download mislukt: {e}')
" 2>/dev/null || echo "WARN: MuseTalk modellen manueel downloaden via huggingface.co/TMElyralab/MuseTalk"
    cd "$PROJECT_DIR"
fi

# --- Wan2.2 5B checkpoints ---
echo ">>> Wan2.2 5B checkpoints downloaden (~10 GB, even geduld)..."
WAN_CKPT="third_party/Wan2.2/Wan2.2-T2V-5B"
if [ ! -d "$WAN_CKPT" ]; then
    python -c "
try:
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id='Wan-AI/Wan2.2-T2V-5B', local_dir='third_party/Wan2.2/Wan2.2-T2V-5B')
    print('Wan2.2 5B gedownload.')
except Exception as e:
    print(f'Wan2.2 download mislukt: {e}')
" 2>/dev/null || echo "WARN: Wan2.2 manueel downloaden via huggingface.co/Wan-AI/Wan2.2-T2V-5B"
fi

# --- huggingface_hub installeren voor downloads ---
pip install -q huggingface_hub

# --- Next.js dashboard ---
echo ""
echo ">>> Next.js dashboard bouwen..."
if command -v npm &>/dev/null; then
    cd dashboard && npm install --silent && npm run build && cd ..
else
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
    cd dashboard && npm install --silent && npm run build && cd ..
fi

# --- PM2 installeren ---
echo ">>> PM2 installeren..."
npm install -g pm2 --silent

# --- .env aanmaken ---
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "╔════════════════════════════════════════════╗"
    echo "║  .env aangemaakt — vul je API keys in!     ║"
    echo "║  nano .env                                  ║"
    echo "╚════════════════════════════════════════════╝"
fi

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║        Setup klaar!                        ║"
echo "║                                            ║"
echo "║  Start services:                           ║"
echo "║  pm2 start scripts/start_all.sh            ║"
echo "║                                            ║"
echo "║  Of manueel:                               ║"
echo "║  uvicorn api.main:app --host 0.0.0.0 \     ║"
echo "║    --port 8000                             ║"
echo "╚════════════════════════════════════════════╝"
