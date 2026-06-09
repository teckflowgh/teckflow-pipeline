"""
TeckFlow RunPod Scheduler
Draait lokaal op Windows via Taakplanner.
Elke dag om 06:00:
  1. Start de RunPod GPU pod
  2. Wacht tot die klaar is
  3. Triggert de pipeline via HTTP
  4. Wacht tot pipeline klaar is
  5. Stopt de pod
  6. Stuurt e-mailmelding met resultaat

Kosten: ~€0.03/dag (enkel tijdens de 8 minuten dat de pipeline draait)
"""

import json
import logging
import os
import smtplib
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests

# ─── Config ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
POD_ID         = os.environ.get("RUNPOD_POD_ID", "amstht1ip2g8bi")
GPU_TYPE       = os.environ.get("RUNPOD_GPU_TYPE", "NVIDIA GeForce RTX 3090")
VIDEO_MODE     = os.environ.get("VIDEO_MODE_DEFAULT", "short")
RUNPOD_API_URL = "https://api.runpod.io/graphql"

LOG_FILE = BASE_DIR / "logs" / "runpod_scheduler.log"

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ─── RunPod API helpers ────────────────────────────────────────────────────────

def runpod_query(query: str) -> dict:
    resp = requests.post(
        f"{RUNPOD_API_URL}?api_key={RUNPOD_API_KEY}",
        json={"query": query},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_pod_status() -> dict:
    data = runpod_query(
        f'{{ pod(input: {{podId: "{POD_ID}"}}) {{ '
        f'id desiredStatus runtime {{ uptimeInSeconds '
        f'ports {{ ip isIpPublic privatePort publicPort type }} }} }} }}'
    )
    return data.get("data", {}).get("pod", {})


def start_pod() -> bool:
    logger.info("Pod starten...")
    data = runpod_query(
        f'mutation {{ podResume(input: {{podId: "{POD_ID}", gpuCount: 1}}) '
        f'{{ id desiredStatus }} }}'
    )
    status = data.get("data", {}).get("podResume", {}).get("desiredStatus", "")
    logger.info("Pod status na start: %s", status)
    return status == "RUNNING"


def stop_pod() -> None:
    logger.info("Pod stoppen...")
    runpod_query(f'mutation {{ podStop(input: {{podId: "{POD_ID}"}}) {{ id desiredStatus }} }}')
    logger.info("Pod gestopt.")


def wait_for_pod_ready(timeout_sec: int = 300) -> str | None:
    """Wacht tot de pod draait en geeft de API URL terug."""
    logger.info("Wachten tot pod klaar is (max %d sec)...", timeout_sec)
    start = time.time()

    while time.time() - start < timeout_sec:
        pod = get_pod_status()
        if pod.get("desiredStatus") == "RUNNING" and pod.get("runtime"):
            ports = pod["runtime"].get("ports", [])
            for p in ports:
                if p.get("privatePort") == 8000 and p.get("publicPort"):
                    api_url = f"https://{POD_ID}-8000.proxy.runpod.net"
                    # Test of API bereikbaar is
                    try:
                        r = requests.get(f"{api_url}/", timeout=10)
                        if r.status_code == 200:
                            logger.info("Pod klaar! API: %s", api_url)
                            return api_url
                    except Exception:
                        pass
        time.sleep(15)

    logger.error("Pod niet klaar binnen %d seconden.", timeout_sec)
    return None


# ─── Pipeline helpers ──────────────────────────────────────────────────────────

def trigger_pipeline(api_url: str, mode: str = "short") -> str | None:
    logger.info("Pipeline triggeren (modus: %s)...", mode)
    try:
        resp = requests.post(
            f"{api_url}/api/run",
            json={"mode": mode},
            timeout=30,
        )
        resp.raise_for_status()
        run_id = resp.json().get("run_id")
        logger.info("Run gestart: %s", run_id)
        return run_id
    except Exception as e:
        logger.error("Pipeline trigger mislukt: %s", e)
        return None


def wait_for_pipeline(api_url: str, run_id: str, timeout_min: int = 30) -> dict:
    logger.info("Wachten op pipeline run %s...", run_id)
    timeout_sec = timeout_min * 60
    start = time.time()

    while time.time() - start < timeout_sec:
        try:
            resp = requests.get(f"{api_url}/api/status", timeout=15)
            data = resp.json()

            if data.get("run_id") == run_id or True:
                status = data.get("status", "")
                stage = data.get("current_stage", "")
                logger.info("Pipeline: stage=%s status=%s", stage, status)

                if status == "completed":
                    logger.info("Pipeline succesvol! Topic: %s", data.get("topic"))
                    return data
                elif status == "failed":
                    logger.error("Pipeline mislukt: %s", data.get("error", "")[:200])
                    return data
        except Exception as e:
            logger.warning("Status check mislukt: %s", e)

        time.sleep(30)

    logger.error("Pipeline timeout na %d minuten.", timeout_min)
    return {"status": "timeout", "error": "Pipeline timeout"}


# ─── E-mail notificatie ────────────────────────────────────────────────────────

def send_notification(result: dict) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    to_addr   = os.environ.get("ALERT_EMAIL_TO", smtp_user)

    if not all([smtp_host, smtp_user, smtp_pass, to_addr]):
        return

    status = result.get("status", "unknown")
    topic  = result.get("topic", "?")
    date   = datetime.now().strftime("%d/%m/%Y")

    if status == "completed":
        subject = f"✅ TeckFlow Video Klaar — {topic[:50]} ({date})"
        body = (
            f"De dagelijkse video is klaar!\n\n"
            f"Topic: {topic}\n"
            f"Script: {result.get('script_preview', '')}\n\n"
            f"Timings: {json.dumps(result.get('stage_timings', {}), indent=2)}\n\n"
            f"Video staat op: /workspace/project/output/final_video.mp4\n"
            f"Dashboard: https://{POD_ID}-3000.proxy.runpod.net (tijdelijk offline — pod gestopt)"
        )
    else:
        subject = f"❌ TeckFlow Pipeline Mislukt ({date})"
        body = (
            f"De pipeline is mislukt.\n\n"
            f"Fout: {result.get('error', 'Onbekend')[:500]}\n\n"
            f"Controleer de logs."
        )

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = to_addr
        with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        logger.info("E-mailmelding verstuurd naar %s", to_addr)
    except Exception as e:
        logger.error("E-mail mislukt: %s", e)


# ─── Hoofdprogramma ────────────────────────────────────────────────────────────

def main():
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("TeckFlow dagelijkse pipeline gestart: %s", datetime.now().strftime("%d/%m/%Y %H:%M"))
    logger.info("=" * 60)

    result = {"status": "failed", "error": "Onbekende fout"}

    try:
        # 1. Pod starten
        start_pod()
        time.sleep(10)

        # 2. Wachten tot klaar
        api_url = wait_for_pod_ready(timeout_sec=300)
        if not api_url:
            raise RuntimeError("Pod kon niet gestart worden binnen 5 minuten.")

        # Extra wachttijd voor PM2 services
        time.sleep(15)

        # 3. Pipeline triggeren
        mode = os.environ.get("VIDEO_MODE_DEFAULT", "short")
        run_id = trigger_pipeline(api_url, mode=mode)
        if not run_id:
            raise RuntimeError("Pipeline kon niet gestart worden.")

        # 4. Wachten op resultaat
        result = wait_for_pipeline(api_url, run_id, timeout_min=45)

    except Exception as e:
        logger.error("Kritieke fout: %s", e)
        result = {"status": "failed", "error": str(e)}

    finally:
        # 5. Pod altijd stoppen (ook bij fout) → kostenbesparing
        try:
            stop_pod()
        except Exception as e:
            logger.error("Pod stoppen mislukt: %s", e)

        elapsed = round((time.time() - start_time) / 60, 1)
        logger.info("Totale tijd: %s minuten", elapsed)

        # 6. E-mail sturen
        send_notification(result)

    logger.info("Pipeline klaar. Status: %s", result.get("status"))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
