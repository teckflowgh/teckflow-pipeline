"""
TeckFlow volledige pipeline — draait IN het Docker-image op de pod.
Stage 1 (Claude) -> Stage 2 (XTTS via venv_tts) -> Stage 3 (MuseTalk) -> Stage 4 (montage).
Alle I/O naar /tmp (volume-writes zijn onbetrouwbaar); modellen LEZEN van /workspace.
"""
import os, sys, subprocess, glob, traceback
sys.path.insert(0, "/tmp/project")
import requests

NTFY = "https://ntfy.sh/teckflow-vid-7k3m9"
def beacon(m):
    try: requests.post(NTFY, data=str(m).encode("utf-8"), timeout=10)
    except Exception: pass

def upload(path):
    for url, data, field in [
        ("https://catbox.moe/user/api.php", {"reqtype": "fileupload"}, "fileToUpload"),
        ("https://0x0.st", {}, "file"),
    ]:
        try:
            with open(path, "rb") as f:
                r = requests.post(url, data=data, files={field: (os.path.basename(path), f)}, timeout=600)
            if r.status_code == 200 and r.text.strip().startswith("http"):
                return r.text.strip()
        except Exception as e:
            print("upload fout", e)
    return None

def main():
    mode = os.environ.get("VIDEO_MODE", "short")

    # ---------- Stage 1: topic + script ----------
    beacon("🧠 Stage 1: trending topic + script...")
    from pipeline.stage1_research.youtube_trending import get_top_topics
    from pipeline.stage1_research.claude_selector import select_topic_and_write_script
    try:
        topics = get_top_topics(top_n=3)
    except Exception as e:
        print("youtube faalde:", e)
        topics = [{"title": "AI-automatisering voor KMO's", "description": "",
                   "tags": ["AI", "automatisering", "KMO"], "view_count": 0}]
    result = select_topic_and_write_script(topics, language="nl", mode=mode)
    script = result["script"]; topic = result["chosen_topic"]
    with open("/tmp/script.txt", "w", encoding="utf-8") as f:
        f.write(script)
    beacon(f"📝 Topic: {topic[:60]}")

    # ---------- Stage 2: XTTS stem (venv_tts) ----------
    beacon("🎙️ Stage 2: stem (XTTS)...")
    tts_code = (
        'import os\n'
        'os.environ["TTS_HOME"]="/workspace/tts_data"; os.environ["COQUI_TOS_AGREED"]="1"\n'
        'from TTS.api import TTS\n'
        't=TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)\n'
        'txt=open("/tmp/script.txt",encoding="utf-8").read()\n'
        't.tts_to_file(text=txt, speaker_wav="/tmp/reference_voice.wav", language="nl", file_path="/tmp/speech.wav")\n'
        'print("TTS_OK")\n'
    )
    r = subprocess.run(["/opt/venv_tts/bin/python", "-c", tts_code], capture_output=True, text=True)
    if not os.path.exists("/tmp/speech.wav"):
        beacon(f"❌ Stage 2 FOUT: {r.stderr[-300:]}"); sys.exit(1)
    beacon(f"🔊 Stem klaar: {os.path.getsize('/tmp/speech.wav')//1024}KB")

    # ---------- Stage 3: MuseTalk lip-sync ----------
    beacon("🎭 Stage 3: lip-sync (MuseTalk)...")
    os.chdir("/opt/MuseTalk")
    subprocess.run("rm -rf models && ln -sfn /workspace/repos/MuseTalk/models models", shell=True)
    os.makedirs("configs/inference", exist_ok=True)
    with open("configs/inference/tf.yaml", "w") as f:
        f.write('task_0:\n  video_path: "/tmp/refclip720.mp4"\n  audio_path: "/tmp/speech.wav"\n')
    mt = subprocess.run(
        ["python", "-m", "scripts.inference",
         "--inference_config", "configs/inference/tf.yaml",
         "--result_dir", "/tmp/mt_out",
         "--unet_model_path", "models/musetalkV15/unet.pth",
         "--unet_config", "models/musetalkV15/musetalk.json",
         "--version", "v15"],
        capture_output=True, text=True)
    vids = [v for v in glob.glob("/tmp/mt_out/**/*.mp4", recursive=True) if "temp_" not in os.path.basename(v)]
    if not vids:
        beacon(f"❌ Stage 3 FOUT: {(mt.stdout + mt.stderr)[-300:]}"); sys.exit(1)
    talking = vids[0]
    beacon(f"🎬 Lip-sync klaar: {os.path.getsize(talking)//1024}KB")

    # ---------- Stage 4: montage v2 (9:16 fill + script-ondertitels + outro) ----------
    beacon("🎞️ Stage 4: montage (9:16 + ondertitels + outro)...")
    os.chdir("/tmp/project")
    from pipeline.stage4_assembly.montage_v2 import assemble
    final = assemble(talking_path=talking, script=script, topic=topic,
                     output_path="/tmp/final_video.mp4")
    beacon(f"📦 Montage klaar: {os.path.getsize(final)//1024//1024}MB")

    # ---------- Afleveren ----------
    url = upload("/tmp/final_video.mp4")
    if url:
        beacon(f"✅ VOLLEDIGE VIDEO KLAAR! Topic: {topic[:45]} | Download: {url}")
    else:
        beacon("⚠️ Video gemaakt maar upload mislukt op alle diensten.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        beacon(f"❌ Pipeline crash: {str(e)[:200]}")
        traceback.print_exc()
        sys.exit(1)
