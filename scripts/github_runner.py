"""
GitHub Actions runner - TeckFlow dagelijkse video pipeline.
Gebruikt SSH key authenticatie op de nieuwe pod (aangemaakt NA key toevoeging).
"""

import os, sys, time, json, subprocess, tempfile
import requests

API_KEY  = os.environ["RUNPOD_API_KEY"]
POD_ID   = os.environ["RUNPOD_POD_ID"]
MODE     = os.environ.get("VIDEO_MODE", "short")
SSH_KEY  = os.environ.get("SSH_PRIVATE_KEY", "")
REPO     = "https://github.com/teckflowgh/teckflow-pipeline.git"
GQL      = f"https://api.runpod.io/graphql?api_key={API_KEY}"

KEY_FILE = None  # Globale key file path


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
    print("Wachten op pod SSH (max 10 min)...")
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

            for p in runtime.get("ports", []):
                if p.get("privatePort") == 22 and p.get("isIpPublic"):
                    ssh_host = p["ip"]
                    ssh_port = p["publicPort"]

            print(f"Status: {status} | Uptime: {uptime}s | SSH: {ssh_host}:{ssh_port}")

            if status == "RUNNING" and uptime > 30 and ssh_host:
                return ssh_host, int(ssh_port)
        except Exception as e:
            print(f"Poll fout: {e}")
        time.sleep(15)

    return None, None


def ssh_cmd(host, port, cmd, timeout=120):
    """SSH commando uitvoeren via key authenticatie."""
    args = ["ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=30"]
    if KEY_FILE:
        args += ["-i", KEY_FILE]
    args += ["-p", str(port), f"root@{host}", cmd]

    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    out = result.stdout.strip()
    err = result.stderr.strip()
    if out:
        print(f"  → {out[-400:]}")
    if result.returncode != 0 and err:
        print(f"  ✗ {err[-200:]}")
    return result.returncode == 0, out


def wait_for_ssh(host, port, attempts=30):
    """Wacht tot SSH bereikbaar is."""
    print(f"Wachten op SSH {host}:{port}...")
    for i in range(attempts):
        ok, out = ssh_cmd(host, port, "echo SSH_OK", timeout=20)
        if ok and "SSH_OK" in out:
            print("SSH bereikbaar!")
            return True
        print(f"SSH poging {i+1}/{attempts}...")
        time.sleep(15)
    return False


def setup_fresh_pod(host, port):
    """Volledige setup voor een verse pod."""
    print("\n=== Verse pod setup ===")

    steps = [
        ("Systeem packages", "apt-get update -qq && apt-get install -y -qq ffmpeg git curl wget", 120),
        ("PyTorch CUDA",
         "pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124 -q",
         300),
        ("Python packages",
         "pip install fastapi==0.115.0 uvicorn 'pydantic==2.8.0' 'pydantic-settings==2.4.0' 'pydantic-core==2.20.0' "
         "python-dotenv apscheduler requests httpx anthropic google-api-python-client "
         "aiofiles python-multipart rich gdown 'numpy==1.26.4' scipy "
         "playwright openai-whisper pydub edge-tts -q",
         300),
        ("Playwright", "playwright install chromium --with-deps -q 2>/dev/null || true", 120),
        ("Project klonen", f"git clone {REPO} /workspace/project -q 2>/dev/null || (cd /workspace/project && git pull origin main -q)", 60),
        ("Mappen", "mkdir -p /workspace/project/assets /workspace/project/output /workspace/project/logs", 10),
        ("SadTalker", "git clone -q https://github.com/OpenTalker/SadTalker /workspace/project/third_party/SadTalker 2>/dev/null || true", 120),
    ]

    for name, cmd, timeout in steps:
        print(f"  {name}...")
        ssh_cmd(host, port, cmd, timeout=timeout)

    # .env aanmaken
    env_lines = [
        f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
        f"YOUTUBE_API_KEY={os.environ.get('YOUTUBE_API_KEY', '')}",
        "YOUTUBE_CATEGORY_ID=28",
        f"PEXELS_API_KEY={os.environ.get('PEXELS_API_KEY', '')}",
        f"VIDIQ_EMAIL={os.environ.get('VIDIQ_EMAIL', '')}",
        f"VIDIQ_PASSWORD={os.environ.get('VIDIQ_PASSWORD', '')}",
        "SCHEDULE_TIME=06:00", "TIMEZONE=Europe/Brussels",
        "TOPIC_SOURCE=vidiq", "SCRIPT_LANGUAGE=nl", "USE_GPU=true",
        "API_HOST=0.0.0.0", "API_PORT=8000",
    ]
    env_content = "\n".join(env_lines)

    # Schrijf .env via Python op de pod
    env_escaped = env_content.replace("'", "'\"'\"'")
    ssh_cmd(host, port, f"printf '%s\\n' '{env_escaped}' > /workspace/project/.env", timeout=10)

    # Node.js + dashboard
    print("  Dashboard bouwen...")
    ssh_cmd(host, port,
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - -qq 2>/dev/null && "
        "apt-get install -y -qq nodejs && "
        "npm install -g pm2 --silent 2>/dev/null && "
        "cd /workspace/project/dashboard && npm install --silent && npm run build 2>/dev/null || true",
        timeout=300)

    # API starten via nohup (geen pm2 nodig)
    print("  API starten...")
    ssh_cmd(host, port,
        "pkill -f uvicorn 2>/dev/null; sleep 2; "
        "cd /workspace/project && "
        "nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 & "
        "echo API_STARTED",
        timeout=30)

    print("Setup klaar!")


def setup_existing_pod(host, port):
    """Bestaande pod updaten: git pull + pydantic fix + restart."""
    print("\n=== Bestaande pod updaten ===")
    # Fix pydantic versie + edge-tts + git pull
    ssh_cmd(host, port,
        "pip install 'pydantic==2.8.0' 'pydantic-core==2.20.0' 'pydantic-settings==2.4.0' edge-tts -q",
        timeout=60)
    ssh_cmd(host, port,
        f"cd /workspace/project && git pull origin main -q 2>/dev/null || true",
        timeout=30)
    # Stop + start uvicorn
    ssh_cmd(host, port,
        "pkill -f uvicorn 2>/dev/null; sleep 3; "
        "cd /workspace/project && "
        "nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 & "
        "sleep 5 && tail -5 /tmp/api.log",
        timeout=30)


def wait_for_api(timeout=180):
    api_url = f"https://{POD_ID}-8000.proxy.runpod.net"
    print(f"Wachten op API ({api_url})...")
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
    r = requests.post(f"{api_url}/api/run", json={"mode": MODE}, timeout=30)
    run_id = r.json().get("run_id")
    print(f"Run gestart: {run_id}")
    return run_id


def poll_pipeline(api_url, timeout_min=45):
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        time.sleep(30)
        try:
            s = requests.get(f"{api_url}/api/status", timeout=15).json()
            status = s.get("status", "")
            print(f"Stage: {s.get('current_stage')} | {status} | {str(s.get('topic',''))[:50]}")
            if status == "completed":
                print("✅ Pipeline klaar!")
                print(json.dumps(s, indent=2, ensure_ascii=False))
                return True
            if status == "failed":
                print(f"❌ Mislukt: {s.get('error','')[:300]}")
                return False
        except Exception as e:
            print(f"Poll fout: {e}")
    return False


def main():
    global KEY_FILE
    print("=" * 50)
    print("TeckFlow Video Pipeline")
    print("=" * 50)

    # SSH key aanmaken
    if SSH_KEY:
        KEY_FILE = tempfile.mktemp(suffix=".pem")
        clean = SSH_KEY.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
        with open(KEY_FILE, "w", newline="\n") as f:
            f.write(clean)
        os.chmod(KEY_FILE, 0o600)
        print(f"SSH key geladen ({len(clean)} chars)")
    else:
        print("WAARSCHUWING: Geen SSH key!")

    success = False
    try:
        start_pod()
        host, port = wait_for_pod(timeout=600)
        if not host:
            print("FOUT: Pod niet bereikbaar.")
            sys.exit(1)

        if not wait_for_ssh(host, port, attempts=20):
            print("FOUT: SSH niet bereikbaar.")
            sys.exit(1)

        # Check of pod vers is
        ok, out = ssh_cmd(host, port, "test -f /workspace/project/api/main.py && echo EXISTS || echo FRESH")
        is_fresh = "FRESH" in out or not ok
        print(f"Pod: {'VERS' if is_fresh else 'BESTAAND'}")

        if is_fresh:
            setup_fresh_pod(host, port)
        else:
            setup_existing_pod(host, port)

        # Check API log voor debuggen
        time.sleep(10)
        ssh_cmd(host, port, "tail -15 /tmp/api.log 2>/dev/null || echo 'Geen log'", timeout=15)

        api_url = wait_for_api(timeout=180)
        run_id = run_pipeline(api_url)
        if not run_id:
            sys.exit(1)
        success = poll_pipeline(api_url)

    finally:
        if KEY_FILE and os.path.exists(KEY_FILE):
            os.unlink(KEY_FILE)
        stop_pod()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
