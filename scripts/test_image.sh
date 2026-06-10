#!/bin/bash
# Test het nieuwe image op GPU: XTTS (stem) + MuseTalk (lip-sync) runtime-check
# Downloadt meteen het XTTS-model naar het volume.
set +e
exec > /workspace/test_image.log 2>&1
NTFY="https://ntfy.sh/teckflow-vid-7k3m9"
beacon() { curl -s -d "$1" "$NTFY" >/dev/null 2>&1 || true; }
beacon "TEST start (nieuw image)"

# GPU bevestigen
GPU=$(python -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'geen')" 2>&1 | tail -1)
beacon "TEST GPU: $GPU"

# MuseTalk-omgeving (basis): imports + modellen op volume
MM=$(python -c "import mmcv, mmpose, diffusers; print('mmcv', mmcv.__version__, 'diffusers', diffusers.__version__)" 2>&1 | tail -1)
beacon "TEST MuseTalk-omgeving: $MM"
M=/workspace/repos/MuseTalk/models
beacon "TEST MuseTalk-modellen: musetalk=$(du -sh $M/musetalk 2>/dev/null|cut -f1) sd-vae=$(du -sh $M/sd-vae 2>/dev/null|cut -f1) dwpose=$(du -sh $M/dwpose 2>/dev/null|cut -f1)"

# XTTS (venv_tts): model downloaden naar volume + GPU-laadtest + mini-synth
source /opt/venv_tts/bin/activate
export TTS_HOME=/workspace/tts_data
export COQUI_TOS_AGREED=1
mkdir -p /workspace/tts_data
# referentiestem ophalen
wget -q --timeout=60 https://files.catbox.moe/bmmymj.wav -O /workspace/reference_voice.wav
RES=$(python -c "
import os; os.environ['COQUI_TOS_AGREED']='1'
from TTS.api import TTS
t = TTS(model_name='tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
t.tts_to_file(text='Dit is een test van mijn gekloonde stem voor TeckFlow.',
              speaker_wav='/workspace/reference_voice.wav', language='nl',
              file_path='/workspace/test_stem.wav')
print('XTTS SYNTH OK')
" 2>&1 | tail -3)
beacon "TEST XTTS: $RES"
beacon "TEST XTTS-model op volume: $(du -sh /workspace/tts_data 2>/dev/null|cut -f1) | sample: $(du -sh /workspace/test_stem.wav 2>/dev/null|cut -f1)"
deactivate

beacon "TEST-KLAAR"
if [ -n "$RUNPOD_API_KEY" ] && [ -n "$RUNPOD_POD_ID" ]; then
  curl -s "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" -H "Content-Type: application/json" \
    -d "{\"query\":\"mutation { podTerminate(input: {podId: \\\"$RUNPOD_POD_ID\\\"}) }\"}" >/dev/null 2>&1
fi
