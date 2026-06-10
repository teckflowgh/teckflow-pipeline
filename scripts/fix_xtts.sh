#!/bin/bash
# XTTS-fix: huggingface-hub downgraden naar <1.0 + XTTS downloaden naar TTS_HOME
set +e
exec > /workspace/fix_xtts.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
beacon "XTTSFIX start"

source /workspace/venv/bin/activate

# 1. huggingface-hub downgraden naar compatibele versie
pip install "huggingface-hub==0.25.2" -q 2>&1 | tail -2
beacon "XTTSFIX hub-versie: $(python -c 'import huggingface_hub; print(huggingface_hub.__version__)' 2>&1 | tail -1)"

# 2. Bevestig dat TTS nu importeert
VER=$(python -c "import TTS; print(TTS.__version__)" 2>&1 | tail -1)
beacon "XTTSFIX TTS-import: $VER"

# 3. XTTS downloaden naar TTS_HOME op het volume
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
RES=$(python -c "
import os
os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('OK')
" 2>&1 | tail -3)
beacon "XTTSFIX download: $RES"

# 4. Verifieer grootte
KB=$(du -sk /workspace/tts_data 2>/dev/null | cut -f1)
if [ -n "$KB" ] && [ "$KB" -gt 500000 ]; then
  echo "XTTS_OK $(date)" > /workspace/XTTS_OK
  beacon "🎉 XTTS COMPLEET op volume ($(du -sh /workspace/tts_data | cut -f1)) — ALLES KLAAR!"
else
  beacon "❌ XTTS nog te klein (${KB}KB) — zie log"
fi

if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
