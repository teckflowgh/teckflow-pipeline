"""
Draait de volledige pipeline OP de pod en levert het resultaat af.
Wordt aangeroepen door pod_autorun.sh als de pod opstart.

Flow:
  1. Pipeline draaien (orchestrator.run_pipeline)
  2. Finale video + metadata per e-mail naar info@teckflow.be
  3. Pod zichzelf laten termineren (stopt facturatie)

Geen SSH, geen API-server nodig — alles draait autonoom op de pod.
"""

import os
import smtplib
import sys
import time
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "output"
FINAL_VIDEO = OUTPUT_DIR / "final_video.mp4"
METADATA = OUTPUT_DIR / "youtube_metadata.json"


def send_email(subject: str, body: str, attachment: Path | None = None):
    """Stuur e-mail via Office 365 SMTP, optioneel met video-bijlage."""
    smtp_host = os.environ.get("SMTP_HOST", "smtp.office365.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "info@teckflow.be")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    to_addr = os.environ.get("ALERT_EMAIL_TO", "info@teckflow.be")

    if not smtp_pass:
        print("Geen SMTP_PASSWORD — e-mail overgeslagen.")
        return

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Video als bijlage (indien klein genoeg, <20MB)
    if attachment and attachment.exists():
        size_mb = attachment.stat().st_size / (1024 * 1024)
        if size_mb < 20:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read_bytes())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attachment.name}",
            )
            msg.attach(part)
            print(f"Video bijgevoegd ({size_mb:.1f} MB)")
        else:
            body += f"\n\n[Video te groot voor e-mail: {size_mb:.1f} MB — staat op de pod output]"

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"E-mail verstuurd naar {to_addr}")
    except Exception as e:
        print(f"E-mail mislukt: {e}")


def _ntfy(msg: str):
    """Publiceer bericht naar ntfy-kanaal."""
    try:
        import requests
        requests.post("https://ntfy.sh/teckflow-vid-7k3m9", data=msg.encode("utf-8"), timeout=15)
    except Exception:
        pass


def upload_to_transfer(video: Path) -> str | None:
    """Upload video naar gratis bestandsdienst (meerdere fallbacks)."""
    if not video.exists():
        return None
    import requests

    # 1. catbox.moe via requests
    try:
        with video.open("rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (video.name, f)},
                timeout=300,
            )
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
        print(f"catbox respons: {resp.text[:100]}")
    except Exception as e:
        print(f"catbox mislukt: {e}")

    # 2. tmpfiles.org fallback
    try:
        with video.open("rb") as f:
            resp = requests.post("https://tmpfiles.org/api/v1/upload",
                                 files={"file": (video.name, f)}, timeout=300)
        if resp.status_code == 200:
            url = resp.json().get("data", {}).get("url", "")
            if url:
                return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as e:
        print(f"tmpfiles mislukt: {e}")

    # 3. 0x0.st fallback
    try:
        with video.open("rb") as f:
            resp = requests.post("https://0x0.st", files={"file": (video.name, f)}, timeout=300)
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
    except Exception as e:
        print(f"0x0 mislukt: {e}")

    return None


def terminate_self():
    """Pod zichzelf laten termineren via RunPod API (stopt facturatie)."""
    api_key = os.environ.get("RUNPOD_API_KEY", "")
    pod_id = os.environ.get("RUNPOD_POD_ID", "")
    if not api_key or not pod_id:
        print("Geen RunPod credentials — pod niet zelf-getermineerd.")
        return
    try:
        import requests
        requests.post(
            f"https://api.runpod.io/graphql?api_key={api_key}",
            json={"query": f'mutation {{ podTerminate(input: {{podId: "{pod_id}"}}) }}'},
            timeout=30,
        )
        print(f"Pod {pod_id} termineert zichzelf.")
    except Exception as e:
        print(f"Zelf-terminatie mislukt: {e}")


def main():
    print("=" * 50)
    print("TeckFlow autonome pipeline-run")
    print("=" * 50)

    mode = os.environ.get("VIDEO_MODE", "short")
    result = None

    try:
        from pipeline.orchestrator import run_pipeline
        print(f"Pipeline starten (modus: {mode})...")
        result = run_pipeline()
        status = result.get("status", "unknown")
        topic = result.get("topic", "?")
        print(f"Pipeline klaar: {status} — {topic}")
    except Exception as e:
        import traceback
        print(f"Pipeline crash: {e}")
        traceback.print_exc()
        send_email(
            f"❌ TeckFlow pipeline gecrasht",
            f"De pipeline is gecrasht:\n\n{e}\n\n{traceback.format_exc()[:1000]}",
        )
        # NIET zelf termineren — autorun.sh uploadt eerst de log, dan pas terminate
        sys.exit(1)

    # Resultaat afleveren
    if result and result.get("status") == "completed" and FINAL_VIDEO.exists():
        topic = result.get("topic", "")
        script_preview = result.get("script_preview", "")

        size_mb = FINAL_VIDEO.stat().st_size / (1024 * 1024)
        print(f"Video gevonden: {FINAL_VIDEO} ({size_mb:.1f} MB)")
        _ntfy(f"📤 Video uploaden ({size_mb:.0f} MB)...")

        # Upload via Python (betrouwbaar, meerdere fallbacks)
        video_url = upload_to_transfer(FINAL_VIDEO)
        if video_url:
            _ntfy(f"✅ VIDEO KLAAR! Onderwerp: {topic[:40]} | Download: {video_url}")
            print(f"VIDEO URL: {video_url}")
        else:
            _ntfy("⚠️ Video gemaakt maar upload mislukt op alle diensten.")

        body = f"""De dagelijkse TeckFlow-video is klaar! 🎬

Onderwerp: {topic}

Script-preview:
{script_preview}

"""
        if video_url:
            body += f"Download de video: {video_url}\n"
        if METADATA.exists():
            body += f"\nYouTube metadata (titel/beschrijving/tags):\n{METADATA.read_text(encoding='utf-8')}\n"

        body += "\nValideer de video en zet hem online. Succes!"

        send_email(
            f"✅ TeckFlow video klaar — {topic[:50]}",
            body,
            attachment=FINAL_VIDEO,
        )
    else:
        err = result.get("error", "onbekend") if result else "geen resultaat"
        send_email(
            "❌ TeckFlow pipeline mislukt",
            f"De pipeline is mislukt:\n\n{err[:1000]}",
        )

    # NIET zelf termineren — autorun.sh doet dat ná het uploaden van de debug-log
    print("Pipeline-stap klaar. Autorun handelt log + terminatie af.")


if __name__ == "__main__":
    main()
