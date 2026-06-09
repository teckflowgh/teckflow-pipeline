#!/bin/bash
# ============================================================
# TeckFlow Pod Autorun
# Draait automatisch wanneer de RunPod pod opstart.
# Installeert alles, draait de pipeline, levert af, termineert zichzelf.
# GEEN SSH NODIG — volledig autonoom.
# ============================================================

set +e  # Niet afbreken bij kleine fouten
exec > /workspace/autorun.log 2>&1  # Alle output naar log
echo "=== TeckFlow Autorun gestart: $(date) ==="

export DEBIAN_FRONTEND=noninteractive
REPO="https://github.com/teckflowgh/teckflow-pipeline.git"
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"

# Beacon-functie: stuur voortgang naar ntfy (zichtbaar op gsm + in GitHub log)
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }

beacon "🚀 Pod gestart, setup begint..."

# 1. Systeem packages
echo ">>> Systeem packages..."
apt-get update -qq
apt-get install -y -qq ffmpeg git curl wget

# 2. Project klonen
echo ">>> Project klonen..."
cd /workspace
git clone "$REPO" project -q 2>/dev/null || (cd project && git pull -q)
cd /workspace/project
mkdir -p assets output logs data third_party
beacon "📦 Project gekloond"

# 3. Python dependencies
echo ">>> PyTorch installeren..."
pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124 -q 2>/dev/null
beacon "🔥 PyTorch klaar"

echo ">>> Python packages installeren..."
pip install fastapi==0.115.0 uvicorn 'pydantic==2.8.0' 'pydantic-settings==2.4.0' \
  'pydantic-core==2.20.0' python-dotenv apscheduler requests httpx anthropic \
  google-api-python-client aiofiles python-multipart rich gdown 'numpy==1.26.4' \
  scipy openai-whisper pydub edge-tts -q 2>/dev/null
beacon "🐍 Python packages klaar"

# 4. Assets ophalen (van GitHub release of meegegeven via env)
# Assets worden meegegeven als base64 env vars door de orchestrator,
# of gedownload van een vaste URL. Voor nu: check of ze al op het volume staan.
echo ">>> Assets controleren..."
if [ ! -f assets/reference_voice.wav ] && [ -n "$ASSET_VOICE_URL" ]; then
  wget -q "$ASSET_VOICE_URL" -O assets/reference_voice.wav
fi
if [ ! -f assets/reference_clip.mp4 ] && [ -n "$ASSET_CLIP_URL" ]; then
  wget -q "$ASSET_CLIP_URL" -O assets/reference_clip.mp4
fi

# 5. SadTalker checkpoints (optioneel)
echo ">>> SadTalker..."
git clone -q https://github.com/OpenTalker/SadTalker third_party/SadTalker 2>/dev/null || true
mkdir -p third_party/SadTalker/checkpoints
wget -q --tries=2 --timeout=120 \
  https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors \
  -O third_party/SadTalker/checkpoints/SadTalker_V0.0.2_256.safetensors 2>/dev/null || true

# 6. .env aanmaken uit env vars (meegegeven door RunPod)
echo ">>> .env aanmaken..."
cat > .env << ENVEOF
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
YOUTUBE_API_KEY=${YOUTUBE_API_KEY}
YOUTUBE_CATEGORY_ID=28
PEXELS_API_KEY=${PEXELS_API_KEY}
VIDIQ_EMAIL=${VIDIQ_EMAIL}
VIDIQ_PASSWORD=${VIDIQ_PASSWORD}
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
ALERT_EMAIL_TO=info@teckflow.be
SCHEDULE_TIME=02:00
TIMEZONE=Europe/Brussels
TOPIC_SOURCE=${TOPIC_SOURCE:-vidiq}
SCRIPT_LANGUAGE=nl
USE_GPU=true
VIDEO_MODE=${VIDEO_MODE:-short}
RUNPOD_API_KEY=${RUNPOD_API_KEY}
RUNPOD_POD_ID=${RUNPOD_POD_ID}
ENVEOF

# 7. Pipeline draaien + afleveren
beacon "🎬 Pipeline start (research → stem → avatar → montage)..."
echo ">>> Pipeline draaien..."
python scripts/run_and_deliver.py
beacon "🎬 Pipeline-stap afgerond"

echo "=== Autorun klaar: $(date) ==="

# 8. Log + video uploaden naar catbox (altijd, ook bij falen)
echo ">>> Log uploaden..."
LOG_URL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@/workspace/autorun.log" https://catbox.moe/user/api.php 2>/dev/null)
beacon "📋 Debug-log: $LOG_URL"

if [ -f /workspace/project/output/final_video.mp4 ]; then
  VID_URL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@/workspace/project/output/final_video.mp4" https://catbox.moe/user/api.php 2>/dev/null)
  beacon "✅ VIDEO KLAAR! Download: $VID_URL"
else
  beacon "⚠️ Geen video gegenereerd — check debug-log hierboven"
fi

# 9. Pod termineren (ná uploads)
beacon "💤 Pod sluit zichzelf af."
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
