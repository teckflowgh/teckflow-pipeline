"""
Stage 4 — FFmpeg Video Editor
Monteert de finale video met:
  - Jouw avatar als hoofdpersoon (talking head)
  - Automatische B-roll wissels passend bij het script
  - Ondertitels van Whisper
  - Achtergrondmuziek (optioneel)

Videostructuur (Optie A — meest professioneel):
  [0-5s]    Avatar fullscreen — hook
  [5-Xs]    B-roll wissels + jouw stem + ondertitels
  [Laatste 5s] Avatar fullscreen — call-to-action TeckFlow
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Standaard videoresolutie: 1080x1920 (9:16 voor Shorts/Reels)
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


def _find_ffmpeg() -> str:
    """Zoekt ffmpeg executable op het systeem."""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # Zoek in WinGet installatiemap
    import glob
    patterns = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\*\bin\ffmpeg.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\*\ffmpeg.exe"),
    ]
    for p in patterns:
        matches = glob.glob(p)
        if matches:
            return matches[0]
    raise FileNotFoundError(
        "ffmpeg niet gevonden. Installeer via: winget install Gyan.FFmpeg"
    )


def _run_ffmpeg(args: list[str], label: str = "") -> None:
    """Voert een ffmpeg commando uit met foutafhandeling."""
    ffmpeg = _find_ffmpeg()
    cmd = [ffmpeg, "-y"] + args
    logger.debug("FFmpeg %s: %s", label, " ".join(cmd))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("FFmpeg fout bij %s:\n%s", label, proc.stderr[-2000:])
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stderr)


def _get_video_duration(path: Path) -> float:
    """Haal de duur van een video op via ffprobe."""
    ffmpeg = _find_ffmpeg()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    proc = subprocess.run([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ], capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 10.0


def _prepare_clip(
    clip_path: Path,
    output_path: Path,
    target_duration: float,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> Path:
    """
    Schaalt en knipt een B-roll clip naar het juiste formaat (9:16).
    Loopt de clip als hij te kort is.
    """
    dur = _get_video_duration(clip_path)

    # Loop als clip te kort is
    loops = max(1, int(target_duration / dur) + 1)

    filter_chain = (
        f"loop={loops}:size=32767:start=0,"
        f"trim=duration={target_duration},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"setsar=1"
    )

    _run_ffmpeg([
        "-i", str(clip_path),
        "-vf", filter_chain,
        "-an",  # geen audio van B-roll
        "-t", str(target_duration),
        str(output_path),
    ], label=f"clip voorbereiden {clip_path.name}")

    return output_path


def _prepare_avatar(
    avatar_path: Path,
    output_path: Path,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> Path:
    """Schaalt de avatar video naar 9:16 formaat."""
    _run_ffmpeg([
        "-i", str(avatar_path),
        "-vf", (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        ),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        str(output_path),
    ], label="avatar voorbereiden")
    return output_path


def assemble_video(
    avatar_path: str | Path,
    audio_path: str | Path,
    broll_clips: list[Path | None],
    scene_durations: list[float],
    subtitle_path: str | Path | None,
    output_path: str | Path,
    background_music: str | Path | None = None,
    music_volume: float = 0.08,
    output_width: int = OUTPUT_WIDTH,
    output_height: int = OUTPUT_HEIGHT,
    chapter_titles: list[str | None] | None = None,
) -> Path:
    """
    Monteert de finale video (Optie A: talking head + B-roll wissels).

    Structuur:
      - Eerste 5s: avatar fullscreen (hook)
      - Middenstuk: B-roll clips met avatar stem eroverheen
      - Laatste 5s: avatar fullscreen (CTA)

    Args:
        avatar_path:       avatar_talking.mp4
        audio_path:        generated_speech.mp3
        broll_clips:       lijst van B-roll paden per scene (of None)
        scene_durations:   duur van elke scene in seconden
        subtitle_path:     .srt bestand van Whisper (of None)
        output_path:       finale output video
        background_music:  optioneel muziekbestand
        music_volume:      volume van achtergrondmuziek (0.0-1.0)
    """
    avatar_path = Path(avatar_path).resolve()
    audio_path = Path(audio_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = output_path.parent / "_tmp_assembly"
    tmp_dir.mkdir(exist_ok=True)

    total_duration = _get_video_duration(avatar_path)
    logger.info("Avatar duur: %.1fs, scenes: %d", total_duration, len(scene_durations))

    # --- Stap 1: Avatar schalen ---
    avatar_scaled = tmp_dir / "avatar_scaled.mp4"
    _prepare_avatar(avatar_path, avatar_scaled, output_width, output_height)

    # --- Stap 2: Videosequentie opbouwen ---
    # Verdeel het middengedeelte over B-roll scenes
    hook_duration = min(5.0, total_duration * 0.15)
    cta_duration = min(5.0, total_duration * 0.15)
    middle_duration = total_duration - hook_duration - cta_duration

    # Bouw lijst van videosegmenten
    segments = []  # (video_path, start_in_avatar, duration)

    # Hook: avatar fullscreen
    segments.append(("avatar", 0, hook_duration))

    # Midden: wissel tussen B-roll en avatar
    current_time = hook_duration
    remaining = middle_duration
    clip_index = 0

    for i, (clip, dur) in enumerate(zip(broll_clips, scene_durations)):
        if remaining <= 0:
            break
        actual_dur = min(dur, remaining)

        if clip and clip.exists():
            segments.append(("broll", clip, current_time, actual_dur))
        else:
            # Geen B-roll: avatar blijft zichtbaar
            segments.append(("avatar", current_time, actual_dur))

        current_time += actual_dur
        remaining -= actual_dur
        clip_index += 1

    # CTA: avatar fullscreen
    segments.append(("avatar", total_duration - cta_duration, cta_duration))

    # --- Stap 3: Video segmenten uitknippen en samenvoegen ---
    segment_files = []

    for idx, seg in enumerate(segments):
        seg_out = tmp_dir / f"seg_{idx:03d}.mp4"

        if seg[0] == "avatar":
            start_t = seg[1]
            dur = seg[2]
            _run_ffmpeg([
                "-ss", str(start_t),
                "-i", str(avatar_scaled),
                "-t", str(dur),
                "-c:v", "libx264",
                "-an",
                "-preset", "fast",
                str(seg_out),
            ], label=f"avatar segment {idx}")

        elif seg[0] == "broll":
            clip_path = seg[1]
            dur = seg[3]
            prepared = tmp_dir / f"broll_prep_{idx:03d}.mp4"
            _prepare_clip(clip_path, prepared, dur, output_width, output_height)
            _run_ffmpeg([
                "-i", str(prepared),
                "-t", str(dur),
                "-c:v", "libx264",
                "-an",
                "-preset", "fast",
                str(seg_out),
            ], label=f"B-roll segment {idx}")

        segment_files.append(seg_out)

    # --- Stap 4: Segmenten samenvoegen ---
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{str(f)}'" for f in segment_files if f.exists()),
        encoding="utf-8"
    )

    video_no_audio = tmp_dir / "video_no_audio.mp4"
    _run_ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-preset", "fast",
        str(video_no_audio),
    ], label="video samenvoegen")

    # --- Stap 5: Audio toevoegen ---
    video_with_audio = tmp_dir / "video_with_audio.mp4"

    if background_music and Path(background_music).exists():
        # Mix stem + achtergrondmuziek
        _run_ffmpeg([
            "-i", str(video_no_audio),
            "-i", str(audio_path),
            "-i", str(background_music),
            "-filter_complex",
            f"[1:a]volume=1.0[voice];[2:a]volume={music_volume},afade=t=out:st={total_duration-3}:d=3[music];[voice][music]amix=inputs=2:duration=first[audio]",
            "-map", "0:v",
            "-map", "[audio]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(video_with_audio),
        ], label="audio mixen")
    else:
        # Alleen stem
        _run_ffmpeg([
            "-i", str(video_no_audio),
            "-i", str(audio_path),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(video_with_audio),
        ], label="stem toevoegen")

    # --- Stap 6: Hoofdstuktitels inbranden (long mode) ---
    if chapter_titles and any(t for t in chapter_titles if t):
        video_with_chapters = tmp_dir / "video_with_chapters.mp4"
        # Bouw drawtext filters voor elk hoofdstuk
        filter_parts = []
        current_time = 0.0
        for i, (title, dur) in enumerate(zip(chapter_titles, scene_durations)):
            if title:
                safe_title = title.replace("'", "\\'").replace(":", "\\:")
                filter_parts.append(
                    f"drawtext=text='{safe_title}'"
                    f":fontsize=52:fontcolor=white:borderw=3:bordercolor=black"
                    f":x=(w-text_w)/2:y=h*0.08"
                    f":enable='between(t,{current_time:.1f},{current_time+3:.1f})'"
                )
            current_time += dur

        if filter_parts:
            vf_filter = ",".join(filter_parts)
            _run_ffmpeg([
                "-i", str(video_with_audio),
                "-vf", vf_filter,
                "-c:a", "copy",
                "-c:v", "libx264",
                "-preset", "fast",
                str(video_with_chapters),
            ], label="hoofdstuktitels")
            video_with_audio = video_with_chapters

    # --- Stap 7: Ondertitels inbranden ---
    if subtitle_path and Path(subtitle_path).exists():
        sub_path_str = str(Path(subtitle_path).resolve()).replace("\\", "/").replace(":", "\\:")
        _run_ffmpeg([
            "-i", str(video_with_audio),
            "-vf", (
                f"subtitles='{sub_path_str}'"
                f":force_style='FontName=Arial,FontSize=44,PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,Outline=3,Bold=1,"
                f"Alignment=2,MarginV=80'"
            ),
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "fast",
            str(output_path),
        ], label="ondertitels inbranden")
    else:
        import shutil
        shutil.copy(str(video_with_audio), str(output_path))

    # Opruimen tijdelijke bestanden
    import shutil as _shutil
    _shutil.rmtree(tmp_dir, ignore_errors=True)

    size_mb = output_path.stat().st_size // (1024 * 1024)
    logger.info("Finale video klaar: %s (%d MB, %.1fs)",
                output_path.name, size_mb, total_duration)
    return output_path
