#!/bin/bash
# Diagnose: waarom downloadt XTTS niet naar het volume?
set +e
exec > /workspace/diagnose_xtts.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1

beacon "XTTSDIAG start"
source /workspace/venv/bin/activate

# 1. Is TTS importeerbaar? Welke versie?
VER=$(python -c "import TTS; print(TTS.__version__)" 2>&1 | tail -1)
beacon "XTTSDIAG TTS-versie: $VER"

# 2. Download poging met volledige foutopvang
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
ERR=$(python -c "
import os, traceback
os.environ['COQUI_TOS_AGREED']='1'
try:
    from TTS.api import TTS
    t = TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)
    print('SUCCES model geladen')
except Exception as e:
    print('FOUT:', repr(e)[:300])
    traceback.print_exc()
" 2>&1 | tail -5)
beacon "XTTSDIAG resultaat: $ERR"

# 3. Waar staan eventuele bestanden?
beacon "XTTSDIAG tts_data: $(du -sh /workspace/tts_data 2>/dev/null | cut -f1) | inhoud: $(find /workspace/tts_data -maxdepth 3 -type d 2>/dev/null | tr '\n' ' ' | cut -c1-200)"
beacon "XTTSDIAG home-cache: $(du -sh /root/.local/share/tts 2>/dev/null | cut -f1)"
beacon "XTTSDIAG-KLAAR"

if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
