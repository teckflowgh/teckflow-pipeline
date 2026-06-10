#!/bin/bash
# MuseTalk lip-sync test met GEGARANDEERDE log-opvang (upload vóór terminatie)
set +e
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
LOG=/workspace/mt_run.log
: > "$LOG"
beacon "MTTEST start (v3, log-fix)"

cd /opt/MuseTalk
rm -rf models
ln -sfn /workspace/repos/MuseTalk/models models

# Stabiele 720p clip ophalen (met retry + verificatie)
for i in 1 2 3; do
  curl -sL --max-time 120 https://files.catbox.moe/37d5qm.mp4 -o /workspace/reference_clip_720.mp4
  SZ=$(stat -c%s /workspace/reference_clip_720.mp4 2>/dev/null || echo 0)
  [ "$SZ" -gt 100000 ] && break
  sleep 5
done
beacon "MTTEST clip720 grootte: $(du -sh /workspace/reference_clip_720.mp4 2>/dev/null|cut -f1) | RAM: $(free -h | awk '/Mem:/{print $2}')"

if [ ! -f /workspace/test_stem.wav ]; then
  source /opt/venv_tts/bin/activate
  export TTS_HOME=/workspace/tts_data COQUI_TOS_AGREED=1
  python -c "
from TTS.api import TTS
t=TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
t.tts_to_file(text='Automatisatie bespaart jouw KMO elke week kostbare uren. Ontdek hoe.', speaker_wav='/workspace/reference_voice.wav', language='nl', file_path='/workspace/test_stem.wav')
" >>"$LOG" 2>&1
  deactivate
fi
mkdir -p configs/inference
cat > configs/inference/teckflow.yaml << 'YAML'
task_0:
  video_path: "/workspace/reference_clip_720.mp4"
  audio_path: "/workspace/test_stem.wav"
YAML

# Inference — VOLLEDIGE output naar log
beacon "MTTEST inference draait..."
python -m scripts.inference \
  --inference_config configs/inference/teckflow.yaml \
  --result_dir /workspace/musetalk_out \
  --unet_model_path models/musetalkV15/unet.pth \
  --unet_config models/musetalkV15/musetalk.json \
  --version v15 >>"$LOG" 2>&1
echo "=== inference exit code: $? ===" >> "$LOG"
echo "=== musetalk_out inhoud: ===" >> "$LOG"
find /workspace/musetalk_out -type f -exec ls -la {} \; >> "$LOG" 2>&1

sync; sleep 3   # volume flushen

# Volledige log uploaden VOOR terminatie
LOGURL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@$LOG" https://catbox.moe/user/api.php 2>/dev/null)
beacon "📋 VOLLEDIGE LOG: $LOGURL"

# Eventuele video uploaden
VID=$(find /workspace/musetalk_out -name "*.mp4" ! -name "temp_*" 2>/dev/null | head -1)
if [ -n "$VID" ] && [ -s "$VID" ]; then
  URL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@$VID" https://catbox.moe/user/api.php 2>/dev/null)
  beacon "✅ MUSETALK VIDEO ($(du -sh "$VID"|cut -f1)): $URL"
else
  beacon "❌ Geen geldige video — zie VOLLEDIGE LOG hierboven"
fi
beacon "MTTEST-KLAAR"

sync; sleep 3
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
