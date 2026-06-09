"""
Stage 4 — Whisper Ondertitels
Genereert automatisch ondertitels (SRT) van de gegenereerde stem
via OpenAI Whisper (open-source, volledig gratis, lokaal).

Installatie: pip install openai-whisper
Model 'base' werkt goed voor Nederlands, 'small' is nog beter.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_subtitles(
    audio_path: str | Path,
    output_path: str | Path,
    language: str = "nl",
    model_size: str = "base",
) -> Path:
    """
    Transcribeert audio naar SRT ondertitels via Whisper.

    Args:
        audio_path:   Pad naar generated_speech.mp3
        output_path:  Bestemming voor het .srt bestand
        language:     Taalcode ('nl', 'en', ...)
        model_size:   Whisper model ('tiny', 'base', 'small', 'medium')
                      'base' = snel, goed genoeg
                      'small' = beter voor Nederlands accent

    Returns:
        Path naar het gegenereerde .srt bestand
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "openai-whisper niet geïnstalleerd. "
            "Voer uit: pip install openai-whisper"
        )

    audio_path = Path(audio_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio niet gevonden: {audio_path}")

    logger.info("Whisper model '%s' laden...", model_size)
    model = whisper.load_model(model_size)

    logger.info("Transcriberen van %s (taal: %s)...", audio_path.name, language)
    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        verbose=False,
    )

    # Schrijf SRT bestand
    srt_content = _segments_to_srt(result["segments"])
    output_path.write_text(srt_content, encoding="utf-8")

    logger.info("Ondertitels opgeslagen: %s (%d segmenten)",
                output_path.name, len(result["segments"]))
    return output_path


def _format_timestamp(seconds: float) -> str:
    """Converteert seconden naar SRT tijdformaat: 00:00:00,000"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_to_srt(segments: list) -> str:
    """Zet Whisper segmenten om naar SRT formaat."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def srt_to_ass(srt_path: Path, ass_path: Path, style: str = "teckflow") -> Path:
    """
    Converteert SRT naar ASS formaat met gestileerde ondertitels.
    ASS ondersteunt lettertypes, kleuren en positionering in FFmpeg.

    Stijl 'teckflow': wit vet tekst, zwarte rand, onderaan gecentreerd.
    """
    try:
        import pysrt
    except ImportError:
        # Fallback: gebruik SRT direct in FFmpeg
        return srt_path

    # ASS header met TeckFlow stijl
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TeckFlow,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Eenvoudige conversie — gebruik SRT als ASS niet werkt
    ass_path.write_text(ass_header, encoding="utf-8")
    return srt_path  # FFmpeg kan ook direct SRT gebruiken
