#!/bin/bash
# Gecombineerde fix: XTTS transformers-pin + mmcv-situatie verifieren in alle venvs
set +e
exec > /workspace/combined_fix.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
beacon "🔧 Gecombineerde fix gestart..."

# ===== DEEL 1: venv_tts — XTTS transformers pin =====
source /workspace/venv_tts/bin/activate
pip install "transformers==4.40.2" -q 2>&1 | tail -1
beacon "📌 venv_tts transformers: $(python -c 'import transformers; print(transformers.__version__)' 2>&1 | tail -1)"
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
RES=$(python -c "
import os; os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
print('XTTS DOWNLOAD OK')
" 2>&1 | tail -3)
beacon "🎙️ $RES"
XKB=$(du -sk /workspace/tts_data 2>/dev/null | cut -f1)
if [ -n "$XKB" ] && [ "$XKB" -gt 500000 ]; then beacon "✅ XTTS ok ($(du -sh /workspace/tts_data|cut -f1))"; else beacon "❌ XTTS te klein (${XKB}KB)"; fi
deactivate

# ===== DEEL 2: mmcv check in beide kandidaat-venvs =====
# 2a. originele venv
if [ -d /workspace/venv ]; then
  source /workspace/venv/bin/activate
  R=$(python -c "import mmcv, mmpose, mmdet; print('mmcv', mmcv.__version__)" 2>&1 | tail -1)
  beacon "🔎 originele venv: $R"
  deactivate
else
  beacon "🔎 originele venv: bestaat niet"
fi
# 2b. nieuwe venv_musetalk
source /workspace/venv_musetalk/bin/activate
R2=$(python -c "import mmcv, mmpose, mmdet; print('mmcv', mmcv.__version__)" 2>&1 | tail -1)
beacon "🔎 venv_musetalk: $R2"
deactivate

beacon "🏁 GECOMBINEERDE FIX KLAAR"

if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
