"""
GitHub Actions runner - TeckFlow dagelijkse video pipeline.
Gebruikt wachtwoord-SSH (sshpass) — betrouwbaarder dan key-based SSH.
Pod heeft ROOT_ACCESS_PASSWORD=TeckFlow2024! als env var ingesteld.
"""

import os, sys, time, json, subprocess
import requests

API_KEY  = os.environ["RUNPOD_API_KEY"]
POD_ID   = os.environ["RUNPOD_POD_ID"]
MODE     = os.environ.get("VIDEO_MODE", "short")
SSH_PASS = os.environ.get("SSH_PASSWORD", "TeckFlow2024!")
REPO     = "https://github.com/teckflowgh/teckflow-pipeline.git"
GQL      = f"https://api.runpod.io/graphql?api_key={API_KEY}"


def gql(q):
    r = requests.post(GQL, json={"query": q}, timeout=30)
    r.raise_for_status()
    return r.json()


def stop_pod():
    try:
        gql(f'mutation {{ podStop(input: {{podId: "{POD_ID}"}}) {{ id }} }}')
        print("Pod gestopt.")
    except Exception as e:
        print(f"Stop mislukt: {e}")


def start_pod():
    print("Pod starten...")
    gql(f'mutation {{ podResume(input: {{podId: "{POD_ID}", gpuCount: 1}}) {{ id }} }}')
    time.sleep(20)


def wait_for_pod(timeout=600):
    print("Wachten op pod (max 10 min)...")
    deadline = time.time() + timeout
    ssh_host = ssh_port = None

    while time.time() < deadline:
        try:
            r = gql(
                f'{{ pod(input: {{podId: "{POD_ID}"}}) {{'
                f'desiredStatus runtime {{ uptimeInSeconds '
                f'ports {{ ip isIpPublic privatePort publicPort }} }} }} }}'
            )
            pod = r["data"]["pod"]
            status = pod.get("desiredStatus", "")
            runtime = pod.get("runtime") or {}
            uptime = int(runtime.get("uptimeInSeconds") or 0)
            ports = runtime.get("ports", [])

            for p in ports:
                if p.get("privatePort") == 22 and p.get("isIpPublic"):
                    ssh_host = p["ip"]
                    ssh_port = p["publicPort"]

            print(f"Status: {status} | Uptime: {uptime}s | SSH: {ssh_host}:{ssh_port}")

            if status == "RUNNING" and uptime > 30 and ssh_host:
                print(f"Pod klaar! SSH: {ssh_host}:{ssh_port}")
                return ssh_host, int(ssh_port)
        except Exception as e:
            print(f"Poll fout: {e}")

        time.sleep(15)

    return None, None


def ssh(host, port, cmd, timeout=120):
    """SSH commando uitvoeren via sshpass (wachtwoord auth)."""
    result = subprocess.run(
        ["sshpass", "-p", SSH_PASS,
         "ssh", "-o", "StrictHostKeyChecking=no",
         "-o", "ConnectTimeout=15",
         "-p", str(port), f"root@{host}", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    if result.stdout.strip():
        print(f"SSH: {result.stdout.strip()[-300:]}")
    if result.returncode != 0 and result.stderr:
        print(f"SSH err: {result.stderr.strip()[-200:]}")
    return result.returncode == 0


def setup_pod(host, port):
    """Volledige pod setup: dependencies, code, services."""
    print(f"\n=== Pod setup via {host}:{port} ===")

    # Wachten tot SSH beschikbaar is
    print("Wachten op SSH...")
    for i in range(20):
        result = subprocess.run(
            ["sshpass", "-p", SSH_PASS,
             "ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=10",
             "-p", str(port), f"root@{host}", "echo SSH_READY"],
            capture_output=True, text=True, timeout=15
        )
        if "SSH_READY" in result.stdout:
            print("SSH bereikbaar!")
            break
        print(f"SSH poging {i+1}/20...")
        time.sleep(15)
    else:
        print("SSH niet bereikbaar na 20 pogingen.")
        return False

    # Systeem packages
    print("Packages installeren...")
    ssh(host, port, "apt-get install -y -qq ffmpeg git curl wget nodejs npm 2>/dev/null || true", timeout=120)

    # Python deps
    print("Python dependencies installeren...")
    cmds = [
        "pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124 -q",
        "pip install fastapi==0.115.0 uvicorn pydantic==2.8.0 pydantic-settings==2.4.0 pydantic-core==2.20.0 python-dotenv apscheduler requests httpx anthropic google-api-python-client aiofiles python-multipart rich gdown numpy==1.26.4 scipy playwright openai-whisper pydub edge-tts -q",
        "playwright install chromium --with-deps -q 2>/dev/null || true",
    ]
    for cmd in cmds:
        ssh(host, port, cmd, timeout=300)

    # Project van GitHub halen
    print("Project van GitHub halen...")
    ssh(host, port,
        f"if [ -d /workspace/project/.git ]; then "
        f"cd /workspace/project && git pull origin main -q; "
        f"else git clone {REPO} /workspace/project -q; fi",
        timeout=60)

    # Assets kopiëren als ze al op volume staan
    ssh(host, port, "mkdir -p /workspace/project/assets /workspace/project/output /workspace/project/logs /workspace/project/data")

    # .env aanmaken
    env_content = "\n".join([
        f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
        f"YOUTUBE_API_KEY={os.environ.get('YOUTUBE_API_KEY', '')}",
        "YOUTUBE_CATEGORY_ID=28",
        f"PEXELS_API_KEY={os.environ.get('PEXELS_API_KEY', '')}",
        f"VIDIQ_EMAIL={os.environ.get('VIDIQ_EMAIL', '')}",
        f"VIDIQ_PASSWORD={os.environ.get('VIDIQ_PASSWORD', '')}",
        "SCHEDULE_TIME=06:00",
        "TIMEZONE=Europe/Brussels",
        "TOPIC_SOURCE=vidiq",
        "SCRIPT_LANGUAGE=nl",
        "USE_GPU=true",
        "API_HOST=0.0.0.0",
        "API_PORT=8000",
    ])
    ssh(host, port, f"cat > /workspace/project/.env << 'ENVEOF'\n{env_content}\nENVEOF")

    # AI model repos klonen
    print("AI modellen klonen...")
    model_cmds = [
        "git clone -q https://github.com/TMElyralab/MuseTalk /workspace/project/third_party/MuseTalk 2>/dev/null || true",
        "git clone -q https://github.com/Wan-Video/Wan2.2 /workspace/project/third_party/Wan2.2 2>/dev/null || true",
        "git clone -q https://github.com/OpenTalker/SadTalker /workspace/project/third_party/SadTalker 2>/dev/null || true",
    ]
    for cmd in model_cmds:
        ssh(host, port, cmd, timeout=120)

    # SadTalker checkpoints
    print("SadTalker checkpoints downloaden...")
    ssh(host, port,
        "mkdir -p /workspace/project/third_party/SadTalker/checkpoints && "
        "wget -q https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors "
        "-O /workspace/project/third_party/SadTalker/checkpoints/SadTalker_V0.0.2_256.safetensors 2>/dev/null || true",
        timeout=120)

    # Node.js en dashboard
    print("Dashboard bouwen...")
    ssh(host, port,
        "cd /workspace/project/dashboard && npm install --silent && npm run build 2>/dev/null || true",
        timeout=300)

    # PM2 installeren en services starten
    print("Services starten met PM2...")
    ssh(host, port, "npm install -g pm2 --silent 2>/dev/null || true")
    ssh(host, port,
        "pm2 delete all 2>/dev/null; "
        "cd /workspace/project && "
        "pm2 start 'uvicorn api.main:app --host 0.0.0.0 --port 8000' --name teckflow-api && "
        "pm2 save",
        timeout=30)

    print("Setup klaar!")
    return True


def wait_for_api(timeout=180):
    """Wacht tot de FastAPI bereikbaar is."""
    api_url = f"https://{POD_ID}-8000.proxy.runpod.net"
    print(f"Wachten op API: {api_url}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{api_url}/", timeout=10)
            if r.status_code == 200:
                print("API bereikbaar!")
                return api_url
        except Exception:
            pass
        time.sleep(10)
    print("API timeout — toch proberen...")
    return api_url


def run_pipeline(api_url):
    print(f"Pipeline starten (modus: {MODE})...")
    r = requests.post(f"{api_url}/api/run", json={"mode": MODE}, timeout=30)
    data = r.json()
    run_id = data.get("run_id")
    print(f"Run ID: {run_id} | {data.get('message', '')}")
    return run_id


def poll_pipeline(api_url, timeout_min=45):
    print("Pipeline volgen...")
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        time.sleep(30)
        try:
            s = requests.get(f"{api_url}/api/status", timeout=15).json()
            status = s.get("status", "")
            print(f"Stage: {s.get('current_stage')} | Status: {status} | Topic: {str(s.get('topic',''))[:50]}")
            if status == "completed":
                print("\n✅ Pipeline succesvol!")
                print(json.dumps(s, indent=2, ensure_ascii=False))
                return True
            if status == "failed":
                print(f"\n❌ Pipeline mislukt: {s.get('error','')[:300]}")
                return False
        except Exception as e:
            print(f"Poll fout: {e}")
    print("Timeout")
    return False


def main():
    print("=" * 50)
    print("TeckFlow dagelijkse video pipeline")
    print("=" * 50)

    # sshpass installeren
    subprocess.run(["apt-get", "install", "-y", "-qq", "sshpass"], capture_output=True)

    success = False
    try:
        start_pod()
        host, port = wait_for_pod(timeout=600)
        if not host:
            print("FOUT: Pod SSH niet bereikbaar.")
            sys.exit(1)

        # Check of dit een verse pod is (geen project aanwezig)
        r = subprocess.run(
            ["sshpass", "-p", SSH_PASS,
             "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
             "-p", str(port), f"root@{host}",
             "test -f /workspace/project/api/main.py && echo EXISTS || echo FRESH"],
            capture_output=True, text=True, timeout=20
        )
        is_fresh = "FRESH" in r.stdout or r.returncode != 0
        print(f"Pod status: {'VERS (setup nodig)' if is_fresh else 'BESTAAND'}")

        if is_fresh:
            print("Eerste keer setup uitvoeren (~15 min)...")
            setup_pod(host, port)
        else:
            # Bestaande pod: alleen code updaten
            print("Code updaten via git pull...")
            ssh(host, port,
                f"cd /workspace/project && git pull origin main -q && "
                "pip install edge-tts -q && "
                "pm2 restart teckflow-api",
                timeout=60)

        api_url = wait_for_api(timeout=120)
        run_id = run_pipeline(api_url)
        if not run_id:
            sys.exit(1)

        success = poll_pipeline(api_url, timeout_min=45)

    finally:
        stop_pod()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
