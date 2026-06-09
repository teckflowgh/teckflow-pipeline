"""
GitHub Actions runner - TeckFlow dagelijkse video pipeline.
Elke run: maak een verse pod aan, doe setup, draai pipeline, termineer pod.
Kost: ~€0.05/run (25 min × €0.12/uur RTX 3090)
"""

import os, sys, time, json, subprocess, tempfile
import requests

API_KEY   = os.environ["RUNPOD_API_KEY"]
SSH_KEY   = os.environ.get("SSH_PRIVATE_KEY", "")
MODE      = os.environ.get("VIDEO_MODE", "short")
REPO      = "https://github.com/teckflowgh/teckflow-pipeline.git"
GPU_TYPE  = "NVIDIA GeForce RTX 3090"
GQL       = f"https://api.runpod.io/graphql?api_key={API_KEY}"

# SSH public key voor de nieuwe pod
SSH_PUB_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILN/G3I/f3Xgv9XtPyIf9rFZS/FjUWbknaUMMaX6Q7zm olivierteck@gmail.com"

KEY_FILE  = None
POD_ID    = None  # Wordt ingevuld bij aanmaken


def gql(q):
    r = requests.post(GQL, json={"query": q}, timeout=30)
    r.raise_for_status()
    return r.json()


def create_pod():
    """Maak een nieuwe pod aan met SSH public key."""
    global POD_ID
    print("Nieuwe pod aanmaken...")
    mutation = (
        'mutation { podFindAndDeployOnDemand(input: { '
        f'cloudType: COMMUNITY gpuCount: 1 '
        f'volumeInGb: 5 containerDiskInGb: 50 '
        f'gpuTypeId: "{GPU_TYPE}" '
        f'name: "TeckFlow-Daily" '
        f'imageName: "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04" '
        f'ports: "8000/http,22/tcp" '
        f'volumeMountPath: "/workspace" '
        f'startSsh: true '
        f'env: [{{key: "PUBLIC_KEY", value: "{SSH_PUB_KEY}"}}] '
        f'}}) {{ id name }} }}'
    )
    r = gql(mutation)
    if r.get("errors"):
        print(f"Fout bij aanmaken pod: {r['errors']}")
        # Probeer RTX 4090 als fallback
        mutation2 = mutation.replace(GPU_TYPE, "NVIDIA GeForce RTX 4090")
        r = gql(mutation2)
    pod = r["data"]["podFindAndDeployOnDemand"]
    POD_ID = pod["id"]
    print(f"Pod aangemaakt: {POD_ID}")
    return POD_ID


def terminate_pod():
    """Verwijder de pod volledig."""
    if not POD_ID:
        return
    try:
        gql(f'mutation {{ podTerminate(input: {{podId: "{POD_ID}"}}) }}')
        print(f"Pod {POD_ID} getermineerd.")
    except Exception as e:
        print(f"Termineren mislukt: {e}")


def wait_for_pod(timeout=600):
    """Wacht tot de pod RUNNING is en SSH beschikbaar is."""
    print("Wachten op pod (max 10 min)...")
    deadline = time.time() + timeout

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

            ssh_host = ssh_port = None
            for p in runtime.get("ports", []):
                if p.get("privatePort") == 22 and p.get("isIpPublic"):
                    ssh_host = p["ip"]
                    ssh_port = p["publicPort"]

            print(f"Status: {status} | Uptime: {uptime}s | SSH: {ssh_host}:{ssh_port}")

            if status == "RUNNING" and uptime > 20 and ssh_host:
                return ssh_host, int(ssh_port)
        except Exception as e:
            print(f"Poll fout: {e}")
        time.sleep(15)

    return None, None


def ssh_run(host, port, cmd, timeout=120):
    """SSH commando uitvoeren met keepalive tegen broken pipe."""
    args = ["ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15", "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=10"]
    if KEY_FILE:
        args += ["-i", KEY_FILE]
    args += ["-p", str(port), f"root@{host}", cmd]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  ⏱ Commando timeout na {timeout}s (gaat door op achtergrond)")
        return False, ""
    if result.stdout.strip():
        print(f"  → {result.stdout.strip()[-400:]}")
    if result.returncode != 0 and result.stderr.strip():
        print(f"  ✗ {result.stderr.strip()[-200:]}")
    return result.returncode == 0, result.stdout


def wait_for_ssh(host, port, attempts=25):
    print(f"Wachten op SSH {host}:{port}...")
    for i in range(attempts):
        ok, out = ssh_run(host, port, "echo SSH_OK", timeout=15)
        if ok and "SSH_OK" in out:
            print("✅ SSH bereikbaar!")
            return True
        print(f"SSH poging {i+1}/{attempts}...")
        time.sleep(12)
    return False


def setup_pod(host, port):
    """
    Volledige pod setup via één achtergrond-script.
    Voorkomt 'broken pipe' door SSH niet minutenlang open te houden:
    we schrijven één setup.sh, draaien die met nohup, en pollen de marker.
    """
    print("\n=== Pod setup (achtergrond-script) ===")

    # .env inhoud
    env_lines = "\\n".join([
        f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
        f"YOUTUBE_API_KEY={os.environ.get('YOUTUBE_API_KEY', '')}",
        "YOUTUBE_CATEGORY_ID=28",
        f"PEXELS_API_KEY={os.environ.get('PEXELS_API_KEY', '')}",
        f"VIDIQ_EMAIL={os.environ.get('VIDIQ_EMAIL', '')}",
        f"VIDIQ_PASSWORD={os.environ.get('VIDIQ_PASSWORD', '')}",
        "YOUTUBE_CATEGORY_ID=28",
        "SCHEDULE_TIME=02:00", "TIMEZONE=Europe/Brussels",
        "TOPIC_SOURCE=vidiq", "SCRIPT_LANGUAGE=nl", "USE_GPU=true",
        "API_HOST=0.0.0.0", "API_PORT=8000",
    ])

    # Het volledige setup-script dat OP de pod draait
    setup_script = f"""#!/bin/bash
set -e
echo "START" > /tmp/setup_status
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq && apt-get install -y -qq ffmpeg git curl wget 2>/dev/null
echo "PACKAGES_OK" > /tmp/setup_status

pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124 -q 2>/dev/null
echo "TORCH_OK" > /tmp/setup_status

pip install fastapi==0.115.0 uvicorn 'pydantic==2.8.0' 'pydantic-settings==2.4.0' 'pydantic-core==2.20.0' python-dotenv apscheduler requests httpx anthropic google-api-python-client aiofiles python-multipart rich gdown 'numpy==1.26.4' scipy openai-whisper pydub edge-tts -q 2>/dev/null
echo "PIP_OK" > /tmp/setup_status

git clone {REPO} /workspace/project -q 2>/dev/null || (cd /workspace/project && git pull -q)
mkdir -p /workspace/project/assets /workspace/project/output /workspace/project/logs /workspace/project/data /workspace/project/third_party
echo "CLONE_OK" > /tmp/setup_status

# SadTalker (optioneel, mag falen)
git clone -q https://github.com/OpenTalker/SadTalker /workspace/project/third_party/SadTalker 2>/dev/null || true
mkdir -p /workspace/project/third_party/SadTalker/checkpoints
wget -q --tries=2 --timeout=120 https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors -O /workspace/project/third_party/SadTalker/checkpoints/SadTalker_V0.0.2_256.safetensors 2>/dev/null || true
echo "MODELS_OK" > /tmp/setup_status

# .env schrijven
printf '{env_lines}\\n' > /workspace/project/.env

# API starten
cd /workspace/project
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 &
sleep 8
echo "DONE" > /tmp/setup_status
"""

    # Schrijf het script naar de pod via base64 (geen quoting problemen)
    import base64
    b64 = base64.b64encode(setup_script.encode()).decode()
    print("  Setup-script uploaden...")
    ssh_run(host, port,
        f"echo '{b64}' | base64 -d > /tmp/setup.sh && chmod +x /tmp/setup.sh && "
        f"nohup bash /tmp/setup.sh > /tmp/setup.log 2>&1 & disown && echo SCRIPT_STARTED",
        timeout=30)

    # Poll de setup_status marker (max 20 min)
    print("  Setup draait op achtergrond, voortgang volgen...")
    last_status = ""
    for i in range(80):  # 80 × 15s = 20 min
        time.sleep(15)
        ok, out = ssh_run(host, port, "cat /tmp/setup_status 2>/dev/null", timeout=20)
        status = out.strip()
        if status and status != last_status:
            print(f"  📍 {status}")
            last_status = status
        if status == "DONE":
            print("✅ Setup klaar!")
            ssh_run(host, port, "tail -8 /tmp/api.log 2>/dev/null", timeout=15)
            return True
    print("⚠️ Setup timeout, toch verder proberen...")
    return False


def wait_for_api(pod_id, timeout=180):
    api_url = f"https://{pod_id}-8000.proxy.runpod.net"
    print(f"Wachten op API ({api_url})...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{api_url}/", timeout=10)
            if r.status_code == 200:
                print("✅ API bereikbaar!")
                return api_url
        except Exception:
            pass
        time.sleep(10)
    print("API timeout — toch proberen...")
    return api_url


def run_pipeline(api_url):
    r = requests.post(f"{api_url}/api/run", json={"mode": MODE}, timeout=30)
    data = r.json()
    run_id = data.get("run_id")
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
                print(f"❌ Mislukt: {s.get('error','')[:400]}")
                return False
        except Exception as e:
            print(f"Poll fout: {e}")
    return False


def main():
    global KEY_FILE, POD_ID
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

    success = False
    try:
        # Verse pod aanmaken
        create_pod()

        # Wachten op SSH
        host, port = wait_for_pod(timeout=600)
        if not host:
            print("FOUT: Pod niet gestart.")
            sys.exit(1)

        if not wait_for_ssh(host, port, attempts=25):
            print("FOUT: SSH niet bereikbaar.")
            sys.exit(1)

        # Setup uitvoeren
        setup_pod(host, port)

        # API wachten
        api_url = wait_for_api(POD_ID, timeout=180)

        # Pipeline draaien
        run_id = run_pipeline(api_url)
        if not run_id:
            sys.exit(1)

        success = poll_pipeline(api_url, timeout_min=45)

    finally:
        if KEY_FILE and os.path.exists(KEY_FILE):
            os.unlink(KEY_FILE)
        terminate_pod()  # Pod volledig verwijderen

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
