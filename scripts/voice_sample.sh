#!/bin/bash
# Genereer een XTTS-stemsample met de NIEUWE referentie (om te beoordelen)
set +e
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
beacon "VOICE sample start"

# Nieuwe referentie naar /tmp (container fs, betrouwbaar)
curl -sL --max-time 60 "https://files.catbox.moe/fdnjl6.wav" -o /tmp/ref_new.wav
beacon "VOICE ref: $(du -h /tmp/ref_new.wav 2>/dev/null|cut -f1)"

source /opt/venv_tts/bin/activate
export TTS_HOME=/workspace/tts_data COQUI_TOS_AGREED=1

# Twee samples: standaard + getrouwer (lagere temperature)
python << 'PY' 2>/tmp/voice.log
import os; os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
t = TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
txt = "Wist je dat de meeste KMO's elke week uren verliezen aan taken die perfect automatisch kunnen? Bij TeckFlow lossen we dat voor je op."
# standaard
t.tts_to_file(text=txt, speaker_wav='/tmp/ref_new.wav', language='nl', file_path='/tmp/sample_standaard.wav')
# getrouwer: lagere temperature
t.tts_to_file(text=txt, speaker_wav='/tmp/ref_new.wav', language='nl', file_path='/tmp/sample_getrouw.wav', temperature=0.3)
print("OK")
PY
deactivate
beacon "VOICE samples: std=$(du -h /tmp/sample_standaard.wav 2>/dev/null|cut -f1) getrouw=$(du -h /tmp/sample_getrouw.wav 2>/dev/null|cut -f1)"

# Uploaden
U1=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@/tmp/sample_standaard.wav" https://catbox.moe/user/api.php 2>/dev/null)
echo "$U1" | grep -q http || U1=$(curl -s -F "file=@/tmp/sample_standaard.wav" https://0x0.st 2>/dev/null)
U2=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@/tmp/sample_getrouw.wav" https://catbox.moe/user/api.php 2>/dev/null)
echo "$U2" | grep -q http || U2=$(curl -s -F "file=@/tmp/sample_getrouw.wav" https://0x0.st 2>/dev/null)
beacon "🔊 SAMPLE STANDAARD: $U1"
beacon "🔊 SAMPLE GETROUW (temp 0.3): $U2"
beacon "VOICE-KLAAR"

sync; sleep 2
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
