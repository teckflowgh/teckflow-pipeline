"""
Stage 4 v2 — Schone montage met fixes:
  1. Avatar gevuld naar 9:16 (1080x1920, geen zwarte balken)
  2. Ondertitels UIT HET SCRIPT (correcte spelling, incl. TeckFlow) — geen Whisper-fouten
  3. Ondertitels klein + netjes afgebroken (binnen beeld)
  4. TeckFlow-outro (~3.5 sec) met call-to-action
"""
import os
import subprocess
from pathlib import Path

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1080, 1920


def _dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 30.0


def _ass_t(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _make_ass(script, duration, ass_path):
    """Ondertitels uit het scripttekst zelf, getimed op audiolengte. Correcte spelling."""
    words = script.replace("\n", " ").split()
    if not words:
        words = [""]
    # Cues van ~3 woorden (vertical: kort houden zodat het binnen beeld past)
    chunks = [" ".join(words[i:i + 3]) for i in range(0, len(words), 3)]
    total = max(1, len(words))
    header = (
        "[Script Info]\n"
        f"PlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Fontsize 64 op 1920-canvas = leesbaar maar niet gigantisch; dikke rand; onderaan
        "Style: TF,DejaVu Sans,64,&H00FFFFFF,&H00000000,&H00000000,-1,1,5,0,2,80,80,280,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines, t = [], 0.0
    for c in chunks:
        d = max(0.7, (len(c.split()) / total) * duration)
        start, end = t, t + d
        t = end
        lines.append(f"Dialogue: 0,{_ass_t(start)},{_ass_t(end)},TF,,0,0,0,,{c}")
    Path(ass_path).write_text(header + "\n".join(lines), encoding="utf-8")


def _run(args, label=""):
    r = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg {label} fout: {r.stderr[-600:]}")


def assemble(talking_path, script, topic, output_path):
    """
    talking_path: MuseTalk lip-sync video (bevat al de stem-audio)
    Geeft pad naar finale 9:16 video terug.
    """
    talking_path = str(Path(talking_path).resolve())
    output_path = Path(output_path).resolve()
    tmp = output_path.parent
    dur = _dur(talking_path)

    # 1. Ondertitels (ASS) uit script
    ass = tmp / "subs.ass"
    _make_ass(script, dur, ass)
    ass_esc = str(ass).replace(":", "\\:")

    # 2. Avatar vullen naar 9:16 + ondertitels inbranden
    main = tmp / "main.mp4"
    _run([
        "-i", talking_path,
        "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},subtitles='{ass_esc}'"),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(main),
    ], "main")

    # 3. TeckFlow-outro (3.5s) met CTA
    outro = tmp / "outro.mp4"
    drawtexts = (
        f"drawtext=fontfile={FONT}:text='TeckFlow':fontcolor=white:fontsize=130:"
        f"x=(w-tw)/2:y=680:box=0,"
        f"drawtext=fontfile={FONT}:text='Automatisatie voor jouw KMO':fontcolor=white:"
        f"fontsize=52:x=(w-tw)/2:y=860,"
        f"drawtext=fontfile={FONT}:text='teckflow.be':fontcolor=0x4FC3F7:fontsize=78:"
        f"x=(w-tw)/2:y=1000"
    )
    _run([
        "-f", "lavfi", "-i", f"color=c=0x0B1020:s={W}x{H}:d=3.5",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", drawtexts,
        "-t", "3.5", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(outro),
    ], "outro")

    # 4. Samenvoegen (main + outro)
    concat = tmp / "concat.txt"
    concat.write_text(f"file '{main}'\nfile '{outro}'\n", encoding="utf-8")
    _run([
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ], "concat")

    # opruimen
    for f in [main, outro, concat, ass]:
        try: f.unlink()
        except Exception: pass

    return str(output_path)
