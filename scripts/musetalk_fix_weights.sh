#!/bin/bash
# Stap A.2 — Ontbrekende MuseTalk sub-modellen downloaden naar juiste paden + verifiëren
set +e
exec > /workspace/musetalk_fix.log 2>&1
echo "=== MuseTalk weights fix: $(date) ==="

NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
beacon "🔧 MuseTalk sub-modellen repareren..."

apt-get update -qq && apt-get install -y -qq curl wget git
source /workspace/venv/bin/activate
pip install -q huggingface_hub gdown 2>&1 | tail -1

cd /workspace/repos/MuseTalk
M=/workspace/repos/MuseTalk/models

# sd-vae
huggingface-cli download stabilityai/sd-vae-ft-mse --local-dir "$M/sd-vae" \
  --include "config.json" "diffusion_pytorch_model.bin" 2>&1 | tail -1
beacon "⬇️ sd-vae gedownload"

# dwpose
huggingface-cli download yzd-v/DWPose dw-ll_ucoco_384.pth --local-dir "$M/dwpose" 2>&1 | tail -1
beacon "⬇️ dwpose gedownload"

# whisper (tiny)
huggingface-cli download openai/whisper-tiny --local-dir "$M/whisper" \
  --include "config.json" "pytorch_model.bin" "preprocessor_config.json" 2>&1 | tail -1
beacon "⬇️ whisper gedownload"

# face-parse-bisent
mkdir -p "$M/face-parse-bisent"
gdown 154JgKpzCPW82qINcVieuPH3fZ2e0P812 -O "$M/face-parse-bisent/79999_iter.pth" 2>&1 | tail -1
wget -q https://download.pytorch.org/models/resnet18-5c106cde.pth -O "$M/face-parse-bisent/resnet18-5c106cde.pth"
beacon "⬇️ face-parse gedownload"

# --- Verificatie: elke map moet > 1MB zijn (niet leeg) ---
echo "=== Verificatie ==="
ALL_OK=1
check() {
  local name=$1 path=$2 minkb=$3
  local kb=$(du -sk "$path" 2>/dev/null | cut -f1)
  if [ -z "$kb" ] || [ "$kb" -lt "$minkb" ]; then
    beacon "❌ $name nog te klein/leeg (${kb}KB)"
    ALL_OK=0
  else
    beacon "✅ $name ok ($(du -sh "$path" | cut -f1))"
  fi
}
check "sd-vae" "$M/sd-vae" 100000
check "dwpose" "$M/dwpose" 100000
check "whisper" "$M/whisper" 50000
check "face-parse" "$M/face-parse-bisent" 50000
check "musetalk" "$M/musetalk" 100000
check "musetalkV15" "$M/musetalkV15" 100000

if [ "$ALL_OK" = "1" ]; then
  echo "MUSETALK_VERIFIED $(date)" > /workspace/MUSETALK_VERIFIED
  beacon "✅ ALLES COMPLEET EN GEVERIFIEERD! Totaal: $(du -sh $M | cut -f1)"
else
  beacon "⚠️ Sommige modellen nog niet ok — zie hierboven"
fi

# Pod termineren
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
echo "=== Fix klaar: $(date) ==="
