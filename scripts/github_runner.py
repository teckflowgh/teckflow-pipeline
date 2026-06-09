"""
GitHub Actions runner - TeckFlow dagelijkse video pipeline.
Strategie: pod start, haalt laatste code van GitHub via git pull,
installeert ontbrekende packages, en draait de pipeline.
Geen lokale SSH vanuit Windows nodig.
"""

import os, sys, time, json, subprocess, tempfile
import requests

API_KEY = os.environ["RUNPOD_API_KEY"]
POD_ID  = os.environ["RUNPOD_POD_ID"]
MODE    = os.environ.get("VIDEO_MODE", "short")
SSH_KEY = os.environ.get("SSH_PRIVATE_KEY", "")
REPO    = os.environ.get("GITHUB_REPO", "https://github.com/teckflowgh/teckflow-pipeline.git")
GQL     = f"https://api.runpod.io/graphql?api_key={API_KEY}"

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
            r = gql(f'{{ pod(input: {{podId: "{POD_ID}"}}) {{ desiredStatus runtime {{ uptimeInSeconds ports {{ ip isIpPublic privatePort publicPort }} }} }} }}')
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
                return ssh_host, int(ssh_port)
        except Exception as e:
            print(f"Poll fout: {e}")
        time.sleep(15)

    return None, None

def ssh_run(host, port, key_file, cmd, timeout=120):
    """Voer een commando uit via SSH. Geeft True terug bij succes."""
    result = subprocess.run(
        ["ssh", "-i", key_file, "-o", "StrictHostKeyChecking=no",
         "-o", f"ConnectTimeout=15", "-p", str(port), f"root@{host}", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    print(f"SSH stdout: {result.stdout[-300:]}")
    if result.returncode != 0:
        print(f"SSH stderr: {result.stderr[-200:]}")
    return result.returncode == 0

def setup_pod(host, port, key_file):
    """Update de pod code via git pull en installeer ontbrekende packages."""
    print(f"Pod setup via SSH {host}:{port}...")

    # Stap 1: Git remote instellen en code updaten
    git_cmd = (
        f"cd /workspace/project && "
        f"git remote set-url origin {REPO} 2>/dev/null || git remote add origin {REPO} && "
        f"git fetch origin main -q && "
        f"git checkout origin/main -- pipeline/stage2_voice/xtts_synthesizer.py && "
        f"echo GIT_OK"
    )
    if not ssh_run(host, port, key_file, git_cmd, timeout=60):
        print("Git pull mislukt - probeer directe installatie...")

    # Stap 2: edge-tts installeren (klein pakket, snel)
    pip_cmd = "pip install edge-tts -q && echo PIP_OK"
    ssh_run(host, port, key_file, pip_cmd, timeout=60)

    # Stap 3: API herstarten
    pm2_cmd = "pm2 restart teckflow-api && sleep 5 && pm2 list"
    ssh_run(host, port, key_file, pm2_cmd, timeout=30)

def wait_for_api(timeout=180):
    """Wacht tot de FastAPI bereikbaar is via de proxy URL."""
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
    return api_url  # Probeer toch

def run_pipeline(api_url):
    print(f"Pipeline starten (modus: {MODE})...")
    r = requests.post(f"{api_url}/api/run", json={"mode": MODE}, timeout=30)
    run_id = r.json().get("run_id")
    print(f"Run ID: {run_id}")
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
                print(json.dumps(s, indent=2, ensure_ascii=False))
                return True
            if status == "failed":
                print("MISLUKT:", s.get("error","")[:300])
                return False
        except Exception as e:
            print(f"Poll fout: {e}")
    print("Timeout")
    return False

def main():
    print("=" * 50)
    print("TeckFlow dagelijkse video pipeline")
    print("=" * 50)

    key_file = None
    success = False

    try:
        # SSH key aanmaken
        if SSH_KEY:
            key_file = tempfile.mktemp(suffix=".pem")
            clean = SSH_KEY.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
            with open(key_file, "w", newline="\n") as f:
                f.write(clean)
            os.chmod(key_file, 0o600)

        # Pod starten
        start_pod()

        # Wachten op SSH
        host, port = wait_for_pod(timeout=600)
        if not host:
            print("FOUT: Pod niet bereikbaar via SSH.")
            sys.exit(1)

        print(f"SSH bereikbaar: {host}:{port}")

        # Pod setup (git pull + edge-tts + PM2 restart)
        if key_file:
            setup_pod(host, port, key_file)
        else:
            print("Geen SSH key — setup overgeslagen.")

        # Wachten op API
        api_url = wait_for_api(timeout=120)

        # Pipeline triggeren
        run_id = run_pipeline(api_url)
        if not run_id:
            sys.exit(1)

        # Wachten op resultaat
        success = poll_pipeline(api_url, timeout_min=45)

    finally:
        if key_file and os.path.exists(key_file):
            os.unlink(key_file)
        stop_pod()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
