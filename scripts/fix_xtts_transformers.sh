#!/bin/bash
# Gerichte fix: transformers==4.40.2 in venv_tts + XTTS opnieuw downloaden
set +e
exec > /workspace/fix_xtts_tf.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
beacon "🔧 XTTS transformers-pin fix..."

source /workspace/venv_tts/bin/activate

# Pin transformers naar 4.40.2 (officieel aanbevolen voor coqui-tts XTTS)
pip install "transformers==4.40.2" -q 2>&1 | tail -2
beacon "📌 transformers: $(python -c 'import transformers; print(transformers.__version__)' 2>&1 | tail -1)"

# Test import
IMP=$(python -c "from TTS.api import TTS; print('TTS import ok')" 2>&1 | tail -1)
beacon "🧪 $IMP"

# XTTS downloaden
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
RES=$(python -c "
import os; os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('DOWNLOAD OK')
" 2>&1 | tail -3)
beacon "🎙️ XTTS: $RES"

KB=$(du -sk /workspace/tts_data 2>/dev/null | cut -f1)
if [ -n "$KB" ] && [ "$KB" -gt 500000 ]; then
  echo "XTTS_OK $(date)" > /workspace/XTTS_OK
  beacon "🎉 XTTS COMPLEET ($(du -sh /workspace/tts_data | cut -f1)) — VOLUME 100% KLAAR!"
else
  beacon "❌ XTTS nog te klein (${KB}KB)"
fi

if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
