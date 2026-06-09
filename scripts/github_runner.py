"""
GitHub Actions runner - TeckFlow dagelijkse video pipeline.
GEEN SSH. De pod draait alles zelf via een opstart-commando (dockerArgs)
en termineert zichzelf na afloop. Wij maken enkel de pod aan en wachten.
"""

import os, sys, time, json
import requests

API_KEY  = os.environ["RUNPOD_API_KEY"]
MODE     = os.environ.get("VIDEO_MODE", "short")
GPU_TYPE = "NVIDIA GeForce RTX 3090"
GQL      = f"https://api.runpod.io/graphql?api_key={API_KEY}"

# Assets (privé catbox-links)
ASSET_VOICE_URL = "https://files.catbox.moe/bmmymj.wav"
ASSET_CLIP_URL  = "https://files.catbox.moe/cjg64m.mp4"

# Het opstart-commando dat de pod ZELF uitvoert bij boot
AUTORUN_URL = "https://raw.githubusercontent.com/teckflowgh/teckflow-pipeline/main/scripts/pod_autorun.sh"


def gql(q):
    r = requests.post(GQL, json={"query": q}, timeout=30)
    r.raise_for_status()
    return r.json()


def env_pair(key, val):
    """Maak een GraphQL env-paar (escape quotes)."""
    safe = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'{{key: "{key}", value: "{safe}"}}'


def create_pod():
    """Maak pod aan met dockerArgs die autorun.sh uitvoert."""
    # Het docker-commando: download autorun en voer uit
    docker_cmd = (
        f"bash -c 'apt-get update -qq && apt-get install -y -qq curl && "
        f"curl -sL {AUTORUN_URL} -o /autorun.sh && bash /autorun.sh'"
    )
    docker_cmd_escaped = docker_cmd.replace("\\", "\\\\").replace('"', '\\"')

    # Env vars die de pod nodig heeft
    envs = [
        env_pair("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "")),
        env_pair("YOUTUBE_API_KEY", os.environ.get("YOUTUBE_API_KEY", "")),
        env_pair("PEXELS_API_KEY", os.environ.get("PEXELS_API_KEY", "")),
        env_pair("VIDIQ_EMAIL", os.environ.get("VIDIQ_EMAIL", "")),
        env_pair("VIDIQ_PASSWORD", os.environ.get("VIDIQ_PASSWORD", "")),
        env_pair("SMTP_USER", os.environ.get("SMTP_USER", "info@teckflow.be")),
        env_pair("SMTP_PASSWORD", os.environ.get("SMTP_PASSWORD", "")),
        env_pair("VIDEO_MODE", MODE),
        env_pair("TOPIC_SOURCE", "vidiq"),
        env_pair("ASSET_VOICE_URL", ASSET_VOICE_URL),
        env_pair("ASSET_CLIP_URL", ASSET_CLIP_URL),
        env_pair("RUNPOD_API_KEY", API_KEY),
        # RUNPOD_POD_ID wordt automatisch door RunPod als env var gezet
    ]
    env_block = "[" + ", ".join(envs) + "]"

    mutation = (
        'mutation { podFindAndDeployOnDemand(input: { '
        f'cloudType: COMMUNITY gpuCount: 1 volumeInGb: 5 containerDiskInGb: 50 '
        f'gpuTypeId: "{GPU_TYPE}" name: "TeckFlow-Auto" '
        f'imageName: "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04" '
        f'dockerArgs: "{docker_cmd_escaped}" '
        f'volumeMountPath: "/workspace" '
        f'env: {env_block} '
        f'}}) {{ id }} }}'
    )

    r = gql(mutation)
    if r.get("errors"):
        print(f"RTX 3090 niet beschikbaar ({r['errors'][0].get('message','')}), probeer 4090...")
        mutation = mutation.replace(GPU_TYPE, "NVIDIA GeForce RTX 4090")
        r = gql(mutation)
        if r.get("errors"):
            print(f"Fout: {r['errors']}")
            return None
    pod_id = r["data"]["podFindAndDeployOnDemand"]["id"]
    print(f"✅ Pod aangemaakt: {pod_id}")
    return pod_id


def pod_status(pod_id):
    try:
        r = gql(f'{{ pod(input: {{podId: "{pod_id}"}}) {{ desiredStatus runtime {{ uptimeInSeconds }} }} }}')
        pod = r["data"].get("pod")
        if not pod:
            return "TERMINATED", 0  # Pod bestaat niet meer = zelf-getermineerd = klaar
        status = pod.get("desiredStatus", "")
        uptime = int((pod.get("runtime") or {}).get("uptimeInSeconds") or 0)
        return status, uptime
    except Exception as e:
        print(f"Status fout: {e}")
        return "UNKNOWN", 0


def terminate_pod(pod_id):
    try:
        gql(f'mutation {{ podTerminate(input: {{podId: "{pod_id}"}}) }}')
        print(f"Pod {pod_id} getermineerd.")
    except Exception:
        pass


def main():
    print("=" * 50)
    print("TeckFlow Autonome Pipeline")
    print("=" * 50)

    pod_id = create_pod()
    if not pod_id:
        print("FOUT: Pod kon niet aangemaakt worden.")
        sys.exit(1)

    print("\nDe pod draait nu volledig autonoom:")
    print("  1. Installeert dependencies")
    print("  2. Haalt assets op")
    print("  3. Draait pipeline (research → stem → avatar → montage)")
    print("  4. Stuurt video per e-mail naar info@teckflow.be")
    print("  5. Termineert zichzelf\n")

    # Wacht tot de pod zichzelf termineert (= klaar) of timeout (60 min)
    print("Voortgang volgen (de pod e-mailt het eindresultaat)...")
    deadline = time.time() + 60 * 60
    last_uptime = 0

    while time.time() < deadline:
        status, uptime = pod_status(pod_id)

        if status in ("TERMINATED", "EXITED"):
            print(f"\n✅ Pod is klaar en heeft zichzelf afgesloten (na {uptime}s).")
            print("Check je e-mail (info@teckflow.be) voor de video!")
            sys.exit(0)

        if uptime != last_uptime:
            mins = uptime // 60
            print(f"  Pod draait... {mins}m {uptime % 60}s (status: {status})")
            last_uptime = uptime

        time.sleep(30)

    # Timeout: forceer terminatie
    print("\n⚠️ Timeout na 60 min — pod forceren te stoppen.")
    terminate_pod(pod_id)
    print("Check /workspace/autorun.log op de pod of je e-mail voor details.")
    sys.exit(1)


if __name__ == "__main__":
    main()
