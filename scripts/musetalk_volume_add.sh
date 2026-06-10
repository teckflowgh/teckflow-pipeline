#!/bin/bash
# ============================================================
# TeckFlow — MuseTalk toevoegen aan het bestaande network volume
# Draait op een pod met het volume gekoppeld op /workspace.
# Gebruikt de bestaande venv (/workspace/venv).
# ============================================================

set +e
exec > /workspace/musetalk_setup.log 2>&1
echo "=== MuseTalk setup gestart: $(date) ==="

NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
beacon "🎬 MuseTalk-installatie gestart..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq ffmpeg git curl wget

# Bestaande venv op het volume gebruiken
source /workspace/venv/bin/activate
beacon "🐍 Volume-venv geactiveerd"

cd /workspace/repos 2>/dev/null || { mkdir -p /workspace/repos && cd /workspace/repos; }

# 1. MuseTalk klonen
git clone -q https://github.com/TMElyralab/MuseTalk 2>/dev/null || (cd MuseTalk && git pull -q && cd ..)
beacon "📦 MuseTalk gekloond"

# 2. mmlab-stack via openmim (de lastige stap)
pip install --no-cache-dir -U openmim -q 2>&1 | tail -1
mim install mmengine 2>&1 | tail -1
beacon "🔧 mmengine klaar"
mim install "mmcv==2.1.0" 2>&1 | tail -2
beacon "🔧 mmcv klaar"
mim install "mmdet==3.2.0" 2>&1 | tail -1
mim install "mmpose==1.3.1" 2>&1 | tail -1
beacon "🔧 mmpose/mmdet klaar"

# 3. MuseTalk requirements
cd /workspace/repos/MuseTalk
pip install -r requirements.txt -q 2>&1 | tail -2
pip install huggingface_hub "diffusers>=0.27" accelerate omegaconf -q 2>&1 | tail -1
beacon "📚 MuseTalk requirements klaar"

# 4. Modelgewichten downloaden
mkdir -p models
huggingface-cli download TMElyralab/MuseTalk --local-dir models/ 2>&1 | tail -2
beacon "⬇️ MuseTalk hoofdmodel gedownload"

# 5. Extra sub-modellen (sd-vae, whisper, dwpose, face-parse) via hun script
if [ -f download_weights.sh ]; then
  bash download_weights.sh 2>&1 | tail -3
else
  # Handmatige fallback voor de belangrijkste sub-modellen
  huggingface-cli download stabilityai/sd-vae-ft-mse --local-dir models/sd-vae-ft-mse 2>&1 | tail -1
  huggingface-cli download yzd-v/DWPose dw-ll_ucoco_384.pth --local-dir models/dwpose 2>&1 | tail -1
fi
beacon "⬇️ MuseTalk sub-modellen gedownload"

# 6. Verificatie
echo "--- models inhoud ---"
ls -la models/
du -sh models/ 2>/dev/null
echo "MUSETALK_READY $(date)" > /workspace/MUSETALK_COMPLETE
beacon "✅ MUSETALK COMPLEET! Permanent op volume. Pod sluit af."

# 7. Pod termineren
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
echo "=== MuseTalk setup klaar: $(date) ==="
