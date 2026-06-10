#!/bin/bash
# ============================================================
# TeckFlow — EENMALIGE setup van het network volume (/workspace)
# Installeert alle zware AI-modellen permanent op de schijf:
#   - Python venv met torch (CUDA), XTTS v2, Whisper, SadTalker deps
#   - XTTS v2 modelgewichten (~2 GB)
#   - SadTalker + checkpoints (~2 GB)
#   - Wav2Lip + checkpoints (fallback)
# Draai dit ÉÉN keer. Daarna mount elke dagelijkse run dit volume.
# ============================================================

set +e
exec > /workspace/volume_setup.log 2>&1
echo "=== Volume setup gestart: $(date) ==="

NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
beacon "🏗️ Volume setup gestart (eenmalig, ~15-20 min)..."

export DEBIAN_FRONTEND=noninteractive
cd /workspace

# 1. Systeem packages
apt-get update -qq
apt-get install -y -qq ffmpeg git curl wget build-essential
beacon "🔧 Systeem packages klaar"

# 2. Python venv op het VOLUME (persistent)
python3 -m venv /workspace/venv
source /workspace/venv/bin/activate
pip install --upgrade pip -q
beacon "🐍 Venv aangemaakt op volume"

# 3. PyTorch met CUDA
pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124 -q
beacon "🔥 PyTorch (CUDA) geïnstalleerd"

# 4. Kern pipeline-packages
pip install fastapi uvicorn 'pydantic==2.8.0' 'pydantic-settings==2.4.0' 'pydantic-core==2.20.0' \
  python-dotenv apscheduler requests httpx anthropic google-api-python-client \
  aiofiles python-multipart rich gdown 'numpy==1.26.4' scipy edge-tts pydub -q
beacon "📦 Kern-packages klaar"

# 5. XTTS v2 (echte stemkloon) — coqui TTS
pip install coqui-tts -q 2>/dev/null || pip install TTS -q
beacon "🎙️ TTS geïnstalleerd"

# XTTS modelcache op het volume zetten (persistent) via symlink
mkdir -p /workspace/tts_data
mkdir -p /root/.local/share
ln -sfn /workspace/tts_data /root/.local/share/tts
# Model vooraf downloaden door TTS te initialiseren
export COQUI_TOS_AGREED=1
python -c "
from TTS.api import TTS
print('XTTS v2 downloaden...')
tts = TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('XTTS v2 klaar')
" 2>&1 | tail -3
beacon "🎙️ XTTS v2 stemkloon-model gedownload"

# 6. Whisper (ondertitels)
pip install openai-whisper -q 2>&1 | tail -1
python -c "import whisper; whisper.load_model('base'); print('whisper base klaar')" 2>&1 | tail -1
beacon "📝 Whisper ondertitel-model klaar"

# 7. SadTalker (lip-sync vanuit foto) + checkpoints
cd /workspace
git clone -q https://github.com/OpenTalker/SadTalker repos/SadTalker 2>/dev/null
pip install -q -r repos/SadTalker/requirements.txt 2>&1 | tail -1
mkdir -p repos/SadTalker/checkpoints repos/SadTalker/gfpgan/weights
cd repos/SadTalker
wget -q https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00109-model.pth.tar -O checkpoints/mapping_00109-model.pth.tar
wget -q https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00229-model.pth.tar -O checkpoints/mapping_00229-model.pth.tar
wget -q https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors -O checkpoints/SadTalker_V0.0.2_256.safetensors
wget -q https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_512.safetensors -O checkpoints/SadTalker_V0.0.2_512.safetensors
wget -q https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth -O gfpgan/weights/alignment_WFLW_4HG.pth
wget -q https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth -O gfpgan/weights/detection_Resnet50_Final.pth
wget -q https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth -O gfpgan/weights/GFPGANv1.4.pth
cd /workspace
beacon "🎭 SadTalker + checkpoints klaar"

# 8. Wav2Lip (lip-sync op video, fallback)
git clone -q https://github.com/Rudrabha/Wav2Lip repos/Wav2Lip 2>/dev/null
mkdir -p repos/Wav2Lip/checkpoints
# Wav2Lip gewichten via mirror (origineel Google Drive is vaak dood)
wget -q "https://huggingface.co/numz/wav2lip_studio/resolve/main/Wav2lip/wav2lip_gan.pth" -O repos/Wav2Lip/checkpoints/wav2lip_gan.pth 2>/dev/null || true
beacon "👄 Wav2Lip klaar"

# 9. Markeer setup compleet
echo "VOLUME_READY $(date)" > /workspace/SETUP_COMPLETE
df -h /workspace | tail -1
beacon "✅ VOLUME SETUP COMPLEET! Modellen permanent opgeslagen. Pod sluit af."

# 10. Pod termineren
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
echo "=== Volume setup klaar: $(date) ==="
