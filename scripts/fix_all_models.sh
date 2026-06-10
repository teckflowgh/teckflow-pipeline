#!/bin/bash
# Stap A.3 — Definitieve reparatie: XTTS + MuseTalk sub-modellen via DIRECTE downloads
set +e
exec > /workspace/fix_all.log 2>&1
echo "=== Fix all models: $(date) ==="
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
beacon "🔧 Definitieve reparatie gestart..."

apt-get update -qq && apt-get install -y -qq curl wget git
source /workspace/venv/bin/activate

M=/workspace/repos/MuseTalk/models

# --- 1. sd-vae (directe wget) ---
mkdir -p "$M/sd-vae"
wget -q https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/diffusion_pytorch_model.bin -O "$M/sd-vae/diffusion_pytorch_model.bin"
wget -q https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/config.json -O "$M/sd-vae/config.json"
beacon "⬇️ sd-vae: $(du -sh $M/sd-vae | cut -f1)"

# --- 2. dwpose (directe wget) ---
mkdir -p "$M/dwpose"
wget -q https://huggingface.co/yzd-v/DWPose/resolve/main/dw-ll_ucoco_384.pth -O "$M/dwpose/dw-ll_ucoco_384.pth"
beacon "⬇️ dwpose: $(du -sh $M/dwpose | cut -f1)"

# --- 3. whisper-tiny (directe wget) ---
mkdir -p "$M/whisper"
wget -q https://huggingface.co/openai/whisper-tiny/resolve/main/pytorch_model.bin -O "$M/whisper/pytorch_model.bin"
wget -q https://huggingface.co/openai/whisper-tiny/resolve/main/config.json -O "$M/whisper/config.json"
wget -q https://huggingface.co/openai/whisper-tiny/resolve/main/preprocessor_config.json -O "$M/whisper/preprocessor_config.json"
beacon "⬇️ whisper: $(du -sh $M/whisper | cut -f1)"

# --- 4. XTTS v2 stemkloon naar TTS_HOME op het volume ---
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
python -c "
from TTS.api import TTS
print('XTTS v2 downloaden naar TTS_HOME...')
TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('klaar')
" 2>&1 | tail -3
beacon "🎙️ XTTS: $(du -sh /workspace/tts_data | cut -f1)"

# --- VERIFICATIE op bestandsgrootte (KB) ---
ALLOK=1
chk() {
  local n=$1 p=$2 min=$3
  local kb=$(du -sk "$p" 2>/dev/null | cut -f1)
  if [ -z "$kb" ] || [ "$kb" -lt "$min" ]; then beacon "❌ $n te klein (${kb}KB)"; ALLOK=0
  else beacon "✅ $n ok ($(du -sh $p | cut -f1))"; fi
}
chk "sd-vae"  "$M/sd-vae"  100000
chk "dwpose"  "$M/dwpose"  100000
chk "whisper" "$M/whisper" 50000
chk "XTTS"    "/workspace/tts_data" 500000

if [ "$ALLOK" = "1" ]; then
  echo "ALL_MODELS_OK $(date)" > /workspace/ALL_MODELS_OK
  beacon "🎉 ALLE MODELLEN COMPLEET EN GEVERIFIEERD!"
else
  beacon "⚠️ Nog iets niet ok — zie hierboven"
fi

# Pod termineren
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
echo "=== klaar: $(date) ==="
