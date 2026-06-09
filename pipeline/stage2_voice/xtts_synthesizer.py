"""
Stage 2 — Voice Synthesis
Primair: edge-tts (Microsoft Azure Neural TTS — geen GPU, geen model download)
Fallback: XTTS v2 (coqui TTS — vereist GPU + 2.2GB download)

edge-tts voordelen:
  - Directe installatie: pip install edge-tts
  - Hoge kwaliteit Nederlandse stemmen
  - Geen GPU vereist
  - Geen model downloads

Installatie: pip install edge-tts
"""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


async def _synthesize_edge_tts(script: str, output_path: Path, language: str = "nl") -> Path:
    """Synthesize speech via Microsoft Edge TTS (cloud, gratis)."""
    import edge_tts

    # Nederlandse/Belgische stemmen
    VOICE_MAP = {
        "nl": "nl-NL-ColetteNeural",   # Professionele Nederlandse vrouwenstem
        "nl-BE": "nl-BE-DenaNeural",    # Belgisch-Nederlandse stem
        "en": "en-US-JennyNeural",
        "fr": "fr-FR-DeniseNeural",
        "de": "de-DE-KatjaNeural",
    }

    voice = VOICE_MAP.get(language, VOICE_MAP.get(language[:2], "nl-NL-ColetteNeural"))
    logger.info("Edge TTS: stem=%s, taal=%s, %d tekens", voice, language, len(script))

    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(str(output_path))

    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise RuntimeError(f"Edge TTS output te klein of niet aangemaakt: {output_path}")

    return output_path


def synthesize_speech(
    script: str,
    reference_wav: str | Path,
    output_path: str | Path,
    language: str = "nl",
    use_gpu: bool | None = None,
) -> Path:
    """
    Syntheseert spraak vanuit het script.
    Probeert eerst edge-tts (snel, geen GPU), daarna XTTS v2 (GPU, hoge kwaliteit klonen).

    Args:
        script:        Te synthetiseren tekst.
        reference_wav: Pad naar referentiestem WAV (enkel gebruikt door XTTS v2).
        output_path:   Uitvoerbestandspad (.mp3 of .wav).
        language:      Taalcode ('nl', 'en', 'fr', ...).
        use_gpu:       Forceert GPU aan/uit (leest USE_GPU env var als None).

    Returns:
        Path naar het gegenereerde audiobestand.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not script.strip():
        raise ValueError("Script is leeg — kan geen spraak synthetiseren.")

    # --- Probeer edge-tts eerst (snel, geen GPU) ---
    try:
        import edge_tts
        logger.info("Stage 2: edge-tts gebruiken...")
        asyncio.run(_synthesize_edge_tts(script, output_path, language))
        size_kb = output_path.stat().st_size // 1024
        logger.info("Spraak gesynthetiseerd via edge-tts: %s (%d KB)", output_path.name, size_kb)
        return output_path
    except ImportError:
        logger.warning("edge-tts niet geïnstalleerd. Probeer: pip install edge-tts")
    except Exception as e:
        logger.warning("edge-tts mislukt: %s — fallback naar XTTS v2", e)

    # --- Fallback: XTTS v2 (vereist GPU + 2.2GB download) ---
    reference_wav = Path(reference_wav).resolve()

    if not reference_wav.exists():
        raise FileNotFoundError(
            f"Referentiestem niet gevonden: {reference_wav}\n"
            "Zet een 10-30 seconden stemopname op assets/reference_voice.wav"
        )

    if use_gpu is None:
        use_gpu = os.environ.get("USE_GPU", "true").lower() in ("true", "1", "yes")

    try:
        from TTS.api import TTS
    except ImportError as e:
        raise ImportError(
            "Noch edge-tts noch TTS (coqui) is geïnstalleerd.\n"
            "Installeer edge-tts: pip install edge-tts"
        ) from e

    global _tts_instance
    if "_tts_instance" not in globals() or _tts_instance is None:
        logger.info("XTTS v2 laden (eerste keer ~2.2GB download)...")
        _tts_instance = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", gpu=use_gpu)

    logger.info("Stage 2: XTTS v2 gebruiken...")
    _tts_instance.tts_to_file(
        text=script,
        speaker_wav=str(reference_wav),
        language=language,
        file_path=str(output_path),
    )

    if not output_path.exists():
        raise RuntimeError(f"XTTS synthese klaar maar uitvoerbestand niet gevonden: {output_path}")

    size_kb = output_path.stat().st_size // 1024
    logger.info("Spraak gesynthetiseerd via XTTS v2: %s (%d KB)", output_path.name, size_kb)
    return output_path


_tts_instance = None
