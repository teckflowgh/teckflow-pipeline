#!/bin/bash
# MuseTalk lip-sync test: reference_clip + gekloonde stem -> pratend hoofd
set +e
exec > /workspace/test_musetalk.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
beacon "MTTEST start"

# MuseTalk-code zit in image (/opt/MuseTalk); modellen op volume
cd /opt/MuseTalk
# Koppel volume-modellen aan de verwachte ./models map
rm -rf models
ln -sfn /workspace/repos/MuseTalk/models models
beacon "MTTEST models-link: $(ls models/ 2>/dev/null | tr '\n' ' ')"

# Inputs ophalen/klaarzetten
wget -q --timeout=120 https://files.catbox.moe/cjg64m.mp4 -O /workspace/reference_clip.mp4
# Stem van vorige test hergebruiken; anders opnieuw genereren
if [ ! -f /workspace/test_stem.wav ]; then
  source /opt/venv_tts/bin/activate
  export TTS_HOME=/workspace/tts_data COQUI_TOS_AGREED=1
  python -c "
from TTS.api import TTS
t=TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
t.tts_to_file(text='Automatisatie bespaart jouw KMO elke week kostbare uren. Ontdek hoe.', speaker_wav='/workspace/reference_voice.wav', language='nl', file_path='/workspace/test_stem.wav')
"
  deactivate
fi
beacon "MTTEST inputs klaar: clip=$(du -sh /workspace/reference_clip.mp4|cut -f1) stem=$(du -sh /workspace/test_stem.wav|cut -f1)"

# Inference-config aanmaken
mkdir -p configs/inference
cat > configs/inference/teckflow.yaml << 'YAML'
task_0:
  video_path: "/workspace/reference_clip.mp4"
  audio_path: "/workspace/test_stem.wav"
YAML

# MuseTalk draaien (v1.5)
beacon "MTTEST inference draait (kan paar min duren)..."
OUT=$(python -m scripts.inference \
  --inference_config configs/inference/teckflow.yaml \
  --result_dir /workspace/musetalk_out \
  --unet_model_path models/musetalkV15/unet.pth \
  --unet_config models/musetalkV15/musetalk.json \
  --version v15 2>&1 | tail -6)
beacon "MTTEST inference-output: $OUT"

# Resultaat zoeken en uploaden
VID=$(find /workspace/musetalk_out -name "*.mp4" 2>/dev/null | head -1)
if [ -n "$VID" ] && [ -f "$VID" ]; then
  URL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@$VID" https://catbox.moe/user/api.php 2>/dev/null)
  beacon "✅ MUSETALK VIDEO KLAAR ($(du -sh "$VID"|cut -f1)): $URL"
else
  beacon "❌ Geen MuseTalk-video gegenereerd — zie inference-output hierboven"
fi
beacon "MTTEST-KLAAR"

if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
