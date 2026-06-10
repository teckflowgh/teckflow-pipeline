#!/bin/bash
# Schone verificatie van alle modellen op het volume
set +e
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }

apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq curl >/dev/null 2>&1

M=/workspace/repos/MuseTalk/models
beacon "CHECK2 === MuseTalk modellen ==="
for d in sd-vae dwpose whisper face-parse-bisent musetalk musetalkV15; do
  if [ -d "$M/$d" ]; then
    sz=$(du -sh "$M/$d" 2>/dev/null | cut -f1)
    cnt=$(find "$M/$d" -type f 2>/dev/null | wc -l)
    beacon "CHECK2 $d = $sz ($cnt bestanden)"
  else
    beacon "CHECK2 $d = ONTBREEKT"
  fi
done

# Ook de andere modellen checken
beacon "CHECK2 === Overige modellen ==="
[ -d /workspace/venv ] && beacon "CHECK2 venv = $(du -sh /workspace/venv 2>/dev/null | cut -f1)" || beacon "CHECK2 venv = ONTBREEKT"
[ -d /workspace/tts_data ] && beacon "CHECK2 XTTS-stem = $(du -sh /workspace/tts_data 2>/dev/null | cut -f1)" || beacon "CHECK2 XTTS = ONTBREEKT"
[ -d /workspace/repos/SadTalker/checkpoints ] && beacon "CHECK2 SadTalker = $(du -sh /workspace/repos/SadTalker/checkpoints 2>/dev/null | cut -f1)" || beacon "CHECK2 SadTalker = ONTBREEKT"
beacon "CHECK2-KLAAR totaal-volume: $(du -sh /workspace 2>/dev/null | cut -f1)"

# Zelf termineren
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
