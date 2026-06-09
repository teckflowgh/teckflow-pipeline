"""
GitHub Actions runner script voor de TeckFlow dagelijkse video pipeline.
Wordt aangeroepen door .github/workflows/daily_video.yml
"""

import os
import sys
import time
import json
import subprocess
import tempfile

import requests

API_KEY  = os.environ["RUNPOD_API_KEY"]
POD_ID   = os.environ["RUNPOD_POD_ID"]
MODE     = os.environ.get("VIDEO_MODE", "short")
SSH_KEY  = os.environ.get("SSH_PRIVATE_KEY", "")
GQL_URL  = f"https://api.runpod.io/graphql?api_key={API_KEY}"


def gql(query):
    r = requests.post(GQL_URL, json={"query": query}, timeout=30)
    r.raise_for_status()
    return r.json()


def start_pod():
    print("Pod starten...")
    gql(f'mutation {{ podResume(input: {{podId: "{POD_ID}", gpuCount: 1}}) {{ id }} }}')
    time.sleep(15)


def stop_pod():
    print("Pod stoppen...")
    try:
        gql(f'mutation {{ podStop(input: {{podId: "{POD_ID}"}}) {{ id }} }}')
        print("Pod gestopt.")
    except Exception as e:
        print(f"Pod stoppen mislukt: {e}")


def wait_for_pod(timeout=300):
    print("Wachten tot pod klaar is...")
    start = time.time()
    api_url = None
    ssh_host = None
    ssh_port = None

    while time.time() - start < timeout:
        pod = gql(
            f'{{ pod(input: {{podId: "{POD_ID}"}}) {{'
            f'desiredStatus runtime {{ ports {{ ip isIpPublic privatePort publicPort type }} }} }} }}'
        )
        runtime = pod["data"]["pod"].get("runtime") or {}
        ports = runtime.get("ports", [])

        for p in ports:
            if p.get("privatePort") == 8000 and p.get("publicPort"):
                api_url = f"https://{POD_ID}-8000.proxy.runpod.net"
            if p.get("privatePort") == 22 and p.get("isIpPublic"):
                ssh_host = p.get("ip")
                ssh_port = p.get("publicPort")

        if api_url:
            try:
                r = requests.get(f"{api_url}/", timeout=10)
                if r.status_code == 200:
                    print(f"Pod klaar! API: {api_url}")
                    return api_url, ssh_host, ssh_port
            except Exception:
                pass

        print("Nog wachten...")
        time.sleep(20)

    return None, None, None


def deploy_edge_tts(ssh_host, ssh_port):
    if not SSH_KEY or not ssh_host:
        print("Geen SSH key — edge-tts fix overgeslagen.")
        return False

    print(f"edge-tts deployen via SSH {ssh_host}:{ssh_port}...")

    # Schrijf SSH key
    key_file = tempfile.mktemp(suffix=".pem")
    with open(key_file, "w") as f:
        f.write(SSH_KEY)
    os.chmod(key_file, 0o600)

    # Minimale synthesizer met edge-tts
    synth_code = (
        "import asyncio\n"
        "from pathlib import Path\n"
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "async def _synth(text, out, lang):\n"
        "    import edge_tts\n"
        "    voices = {'nl': 'nl-NL-ColetteNeural', 'en': 'en-US-JennyNeural', 'fr': 'fr-FR-DeniseNeural'}\n"
        "    voice = voices.get(lang, 'nl-NL-ColetteNeural')\n"
        "    await edge_tts.Communicate(text, voice).save(str(out))\n"
        "def synthesize_speech(script, reference_wav, output_path, language='nl', use_gpu=None):\n"
        "    output_path = Path(output_path).resolve()\n"
        "    output_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    try:\n"
        "        import edge_tts\n"
        "    except ImportError:\n"
        "        import subprocess\n"
        "        subprocess.run(['pip', 'install', 'edge-tts', '-q'], check=True)\n"
        "    asyncio.run(_synth(script, output_path, language))\n"
        "    logger.info('Spraak: %s (%d KB)', output_path.name, output_path.stat().st_size // 1024)\n"
        "    return output_path\n"
    )

    # Schrijf Python script dat de fix uitvoert
    fix_script = (
        "import subprocess, os\n"
        "subprocess.run(['pip', 'install', 'edge-tts', '-q'])\n"
        f"code = {repr(synth_code)}\n"
        "with open('/workspace/project/pipeline/stage2_voice/xtts_synthesizer.py', 'w') as f:\n"
        "    f.write(code)\n"
        "subprocess.run(['pm2', 'restart', 'teckflow-api'])\n"
        "print('FIX_DONE')\n"
    )

    fix_file = tempfile.mktemp(suffix=".py")
    with open(fix_file, "w") as f:
        f.write(fix_script)

    # Kopieer fix script naar pod
    scp_result = subprocess.run([
        "scp", "-i", key_file, "-o", "StrictHostKeyChecking=no",
        "-P", str(ssh_port), fix_file, f"root@{ssh_host}:/tmp/fix.py"
    ], capture_output=True, text=True, timeout=30)

    if scp_result.returncode == 0:
        # Voer het uit
        ssh_result = subprocess.run([
            "ssh", "-i", key_file, "-o", "StrictHostKeyChecking=no",
            "-p", str(ssh_port), f"root@{ssh_host}",
            "python3 /tmp/fix.py"
        ], capture_output=True, text=True, timeout=60)
        print("SSH output:", ssh_result.stdout)
        if ssh_result.returncode != 0:
            print("SSH fout:", ssh_result.stderr[-200:])
    else:
        print("SCP fout:", scp_result.stderr)

    os.unlink(key_file)
    os.unlink(fix_file)
    time.sleep(10)
    return True


def trigger_pipeline(api_url):
    print(f"Pipeline starten (modus: {MODE})...")
    r = requests.post(f"{api_url}/api/run", json={"mode": MODE}, timeout=30)
    run_id = r.json().get("run_id")
    print(f"Run ID: {run_id}")
    return run_id


def wait_for_pipeline(api_url, timeout_min=45):
    print("Wachten op pipeline resultaat...")
    for _ in range(timeout_min * 2):
        time.sleep(30)
        try:
            status = requests.get(f"{api_url}/api/status", timeout=15).json()
            s = status.get("status", "")
            topic = status.get("topic", "")
            stage = status.get("current_stage", "")
            print(f"Stage: {stage} | Status: {s} | Topic: {topic[:50]}")

            if s == "completed":
                print("\nPipeline succesvol!")
                print(json.dumps(status, indent=2, ensure_ascii=False))
                return True
            elif s == "failed":
                print("\nPipeline mislukt!")
                print(status.get("error", "")[:500])
                return False
        except Exception as e:
            print(f"Status check fout: {e}")

    print("Timeout!")
    return False


def main():
    print("=" * 50)
    print("TeckFlow dagelijkse video pipeline")
    print("=" * 50)

    success = False
    try:
        start_pod()
        api_url, ssh_host, ssh_port = wait_for_pod(timeout=300)

        if not api_url:
            print("FOUT: Pod niet bereikbaar.")
            sys.exit(1)

        # Fix edge-tts
        deploy_edge_tts(ssh_host, ssh_port)
        time.sleep(15)

        # Pipeline uitvoeren
        run_id = trigger_pipeline(api_url)
        if not run_id:
            sys.exit(1)

        success = wait_for_pipeline(api_url)

    finally:
        stop_pod()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
