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

# 3. Python dependencies (geen PyTorch nodig voor simple-avatar modus)
echo ">>> Kern-packages installeren..."
pip install --no-input python-dotenv requests anthropic google-api-python-client 'numpy==1.26.4' -q 2>&1 | tail -2
beacon "🐍 Kern-packages klaar"

echo ">>> Audio/video packages..."
pip install --no-input edge-tts pydub pexels-api 'pydantic==2.8.0' -q 2>&1 | tail -2
beacon "🔊 Audio packages klaar"

# Whisper (ondertitels) optioneel — faster-whisper compileert niet, veel sneller
echo ">>> Ondertitels (faster-whisper, optioneel)..."
timeout 180 pip install --no-input faster-whisper -q 2>&1 | tail -2 || echo "Whisper overgeslagen (niet kritiek)"
beacon "📝 Ondertitels-stap klaar"

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

# 5. Avatar: simple ffmpeg-modus (geen zware modeldownloads nodig)
export AVATAR_MODE=simple
echo ">>> Avatar-modus: simple (ffmpeg)"

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
