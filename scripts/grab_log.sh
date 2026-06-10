#!/bin/bash
set +e
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1
# Upload de volledige MuseTalk inference-log
URL=$(curl -s -F "reqtype=fileupload" -F "fileToUpload=@/workspace/test_musetalk.log" https://catbox.moe/user/api.php 2>/dev/null)
beacon "LOG-URL: $URL"
# Ook musetalk_out inhoud tonen
beacon "OUT-MAP: $(ls -laR /workspace/musetalk_out 2>/dev/null | head -30 | tr '\n' '|' | cut -c1-400)"
beacon "GRAB-KLAAR"
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
