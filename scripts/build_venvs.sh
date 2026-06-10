#!/bin/bash
# Twee geïsoleerde venvs op het volume: venv_tts (XTTS) en venv_musetalk (MuseTalk)
# Lost dependency-conflict definitief op. Modellen staan al op het volume.
set +e
exec > /workspace/build_venvs.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl git ffmpeg build-essential >/dev/null 2>&1
beacon "🏗️ Aparte venvs bouwen..."

TORCH="torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124"

# ============ VENV 1: XTTS (stem) ============
rm -rf /workspace/venv_tts
python3 -m venv /workspace/venv_tts
source /workspace/venv_tts/bin/activate
pip install --upgrade pip -q
pip install $TORCH -q 2>&1 | tail -1
beacon "🔥 venv_tts: torch klaar"
# coqui-tts pint zelf compatibele transformers + huggingface-hub
pip install coqui-tts -q 2>&1 | tail -2
beacon "🎙️ venv_tts: coqui-tts geïnstalleerd ($(python -c 'import TTS; print(TTS.__version__)' 2>&1 | tail -1))"
# XTTS downloaden naar TTS_HOME
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
RES=$(python -c "
import os; os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('OK')
" 2>&1 | tail -3)
beacon "🎙️ venv_tts XTTS-download: $RES"
KB=$(du -sk /workspace/tts_data 2>/dev/null | cut -f1)
if [ -n "$KB" ] && [ "$KB" -gt 500000 ]; then beacon "✅ XTTS ok ($(du -sh /workspace/tts_data | cut -f1))"; else beacon "❌ XTTS te klein (${KB}KB)"; fi
deactivate

# ============ VENV 2: MuseTalk (lip-sync) ============
rm -rf /workspace/venv_musetalk
python3 -m venv /workspace/venv_musetalk
source /workspace/venv_musetalk/bin/activate
pip install --upgrade pip -q
pip install $TORCH -q 2>&1 | tail -1
beacon "🔥 venv_musetalk: torch klaar"
pip install --no-cache-dir -U openmim -q 2>&1 | tail -1
mim install mmengine 2>&1 | tail -1
mim install "mmcv==2.1.0" 2>&1 | tail -1
mim install "mmdet==3.2.0" "mmpose==1.3.1" 2>&1 | tail -1
beacon "🔧 venv_musetalk: mmlab klaar"
pip install -r /workspace/repos/MuseTalk/requirements.txt -q 2>&1 | tail -2
pip install "diffusers>=0.27" accelerate omegaconf "huggingface_hub" -q 2>&1 | tail -1
beacon "📚 venv_musetalk: requirements klaar"
# Test MuseTalk import
MT=$(python -c "import mmcv, mmpose, diffusers; print('imports ok')" 2>&1 | tail -1)
beacon "🎭 venv_musetalk import-test: $MT"
deactivate

echo "VENVS_READY $(date)" > /workspace/VENVS_READY
beacon "🎉 BEIDE VENVS KLAAR! Volume volledig compleet."

if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
