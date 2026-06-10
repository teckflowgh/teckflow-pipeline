#!/bin/bash
# MuseTalk lip-sync test — clip van GitHub raw, log via ntfy (betrouwbaar)
set +e
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
LOG=/tmp/mt_run.log; : > "$LOG"
beacon "MTTEST start (v4, github-clip)"

cd /opt/MuseTalk
rm -rf models; ln -sfn /workspace/repos/MuseTalk/models models

# Clip van GitHub raw (rotsvast)
RAW="https://raw.githubusercontent.com/teckflowgh/teckflow-pipeline/main/assets/refclip720.mp4"
for i in 1 2 3; do
  curl -sL --max-time 60 "$RAW" -o /tmp/refclip720.mp4
  SZ=$(stat -c%s /tmp/refclip720.mp4 2>/dev/null || echo 0)
  [ "$SZ" -gt 100000 ] && break; sleep 3
done
beacon "MTTEST clip: $(du -h /tmp/refclip720.mp4 2>/dev/null|cut -f1)"

# Stem genereren in-pod
source /opt/venv_tts/bin/activate
export TTS_HOME=/workspace/tts_data COQUI_TOS_AGREED=1
python -c "
from TTS.api import TTS
t=TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
t.tts_to_file(text='Automatisatie bespaart jouw KMO elke week kostbare uren. Ontdek hoe.', speaker_wav='/workspace/reference_voice.wav', language='nl', file_path='/tmp/stem.wav')
" >>"$LOG" 2>&1
deactivate
[ -f /workspace/reference_voice.wav ] || wget -q "https://files.catbox.moe/bmmymj.wav" -O /workspace/reference_voice.wav
beacon "MTTEST stem: $(du -h /tmp/stem.wav 2>/dev/null|cut -f1)"

mkdir -p configs/inference
cat > configs/inference/teckflow.yaml << 'YAML'
task_0:
  video_path: "/tmp/refclip720.mp4"
  audio_path: "/tmp/stem.wav"
YAML

beacon "MTTEST inference draait..."
python -m scripts.inference \
  --inference_config configs/inference/teckflow.yaml \
  --result_dir /tmp/musetalk_out \
  --unet_model_path models/musetalkV15/unet.pth \
  --unet_config models/musetalkV15/musetalk.json \
  --version v15 >>"$LOG" 2>&1
EC=$?
echo "=== inference exit: $EC ===" >> "$LOG"
find /tmp/musetalk_out -type f >> "$LOG" 2>&1

# Log-staart via ntfy (betrouwbaar, geen catbox)
beacon "MTTEST exit=$EC | RAM-vrij: $(free -h|awk '/Mem:/{print $7}')"
beacon "LOGTAIL: $(tail -c 1400 "$LOG" | tr '\n' '|')"

# Video zoeken + uploaden via meerdere diensten
VID=$(find /tmp/musetalk_out -name "*.mp4" ! -name "temp_*" 2>/dev/null | head -1)
if [ -n "$VID" ] && [ -s "$VID" ]; then
  U=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@$VID" https://catbox.moe/user/api.php 2>/dev/null)
  echo "$U" | grep -q "http" || U=$(curl -s -F "file=@$VID" https://0x0.st 2>/dev/null)
  beacon "✅ MUSETALK VIDEO ($(du -h "$VID"|cut -f1)): $U"
else
  beacon "❌ Geen video — zie LOGTAIL"
fi
beacon "MTTEST-KLAAR"

sync; sleep 2
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
