#!/bin/bash
# Volledige TeckFlow-pipeline op de pod (Docker-image + volume)
set +e
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl git >/dev/null 2>&1
beacon "🚀 Volledige pipeline gestart"

# Project clonen naar /tmp (container fs)
rm -rf /tmp/project
git clone -q https://github.com/teckflowgh/teckflow-pipeline /tmp/project
RAW="https://raw.githubusercontent.com/teckflowgh/teckflow-pipeline/main/assets"

# Inputs naar /tmp (betrouwbaar)
for i in 1 2 3; do curl -sL --max-time 60 "$RAW/reference_voice.wav" -o /tmp/reference_voice.wav; [ "$(stat -c%s /tmp/reference_voice.wav 2>/dev/null||echo 0)" -gt 100000 ] && break; sleep 3; done
for i in 1 2 3; do curl -sL --max-time 60 "$RAW/refclip720.mp4" -o /tmp/refclip720.mp4; [ "$(stat -c%s /tmp/refclip720.mp4 2>/dev/null||echo 0)" -gt 100000 ] && break; sleep 3; done
beacon "📥 Inputs: stem=$(du -h /tmp/reference_voice.wav 2>/dev/null|cut -f1) clip=$(du -h /tmp/refclip720.mp4 2>/dev/null|cut -f1)"

# Pipeline draaien (env vars zijn door RunPod meegegeven)
python /tmp/project/scripts/image_pipeline.py
beacon "🏁 PIPELINE-KLAAR"

sync; sleep 2
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
