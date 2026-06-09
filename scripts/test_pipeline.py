"""
Smoke-test individual pipeline stages.
Usage:
  python scripts/test_pipeline.py --stage 1
  python scripts/test_pipeline.py --stage 2
  python scripts/test_pipeline.py --stage 3
  python scripts/test_pipeline.py --stage 4
  python scripts/test_pipeline.py --all
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from pipeline.orchestrator import setup_logging
setup_logging()


SAMPLE_SCRIPT = (
    "AI is changing everything right now. Here's what you need to know. "
    "Large language models can now write code, generate images, and hold conversations "
    "that feel completely human. The biggest companies on earth are racing to deploy these "
    "systems into their products. If you're not paying attention to this shift, you're already "
    "falling behind. Here's the one thing you must do this week to stay ahead."
)

SAMPLE_TOPICS = [
    {
        "title": "ChatGPT-5 is here and it's terrifying",
        "description": "OpenAI releases their most powerful model yet",
        "channel_title": "TechNews",
        "tags": ["AI", "ChatGPT", "OpenAI", "technology"],
        "view_count": 2_500_000,
        "like_count": 120_000,
    },
    {
        "title": "Google Gemini beats everything",
        "description": "Google's new AI model scores top on all benchmarks",
        "channel_title": "AIWeekly",
        "tags": ["Google", "Gemini", "AI", "LLM"],
        "view_count": 1_800_000,
        "like_count": 89_000,
    },
    {
        "title": "The AI job apocalypse is real",
        "description": "Which jobs are being replaced by AI in 2025?",
        "channel_title": "FutureWork",
        "tags": ["jobs", "AI", "automation", "economy"],
        "view_count": 3_100_000,
        "like_count": 210_000,
    },
]


def test_stage1():
    print("\n=== Stage 1: Topic Research + Claude Script Writing ===")
    from pipeline.stage1_research.youtube_trending import get_top_topics
    from pipeline.stage1_research.claude_selector import select_topic_and_write_script

    print("Fetching trending topics from YouTube...")
    try:
        topics = get_top_topics(top_n=3)
        print(f"  Got {len(topics)} topics from YouTube.")
    except Exception as e:
        print(f"  YouTube fetch failed ({e}). Using sample topics.")
        topics = SAMPLE_TOPICS

    print("Calling Claude Haiku to select topic + write script...")
    result = select_topic_and_write_script(topics)
    print(f"\n  Chosen topic : {result['chosen_topic']}")
    print(f"  Rationale    : {result['rationale']}")
    print(f"  Script ({len(result['script'].split())} words):\n")
    print(result["script"])
    print("\n[PASS] Stage 1 complete.")
    return result["script"]


def test_stage2(script: str = SAMPLE_SCRIPT):
    print("\n=== Stage 2: XTTS v2 Voice Synthesis ===")
    from pipeline.stage2_voice.xtts_synthesizer import synthesize_speech
    output = BASE_DIR / "output" / "generated_speech.mp3"
    reference = BASE_DIR / "assets" / "reference_voice.wav"
    if not reference.exists():
        print(f"  [SKIP] Reference voice not found at {reference}")
        print("  Place a 10-30 second clean WAV recording at assets/reference_voice.wav")
        return
    path = synthesize_speech(script=script, reference_wav=reference, output_path=output)
    print(f"  Output: {path} ({path.stat().st_size // 1024} KB)")
    print("\n[PASS] Stage 2 complete.")


def test_stage3():
    print("\n=== Stage 3: SadTalker Avatar Generation ===")
    from pipeline.stage3_avatar.sadtalker_runner import generate_avatar_video
    audio = BASE_DIR / "output" / "generated_speech.mp3"
    image = BASE_DIR / "assets" / "avatar_image.jpg"
    output = BASE_DIR / "output" / "avatar_talking.mp4"

    if not audio.exists():
        print(f"  [SKIP] Audio not found: {audio}. Run --stage 2 first.")
        return
    if not image.exists():
        print(f"  [SKIP] Avatar image not found: {image}")
        print("  Place a frontal face photo at assets/avatar_image.jpg")
        return

    try:
        path = generate_avatar_video(audio_path=audio, image_path=image, output_path=output)
        print(f"  Output: {path} ({path.stat().st_size // (1024*1024)} MB)")
        print("\n[PASS] Stage 3 complete.")
    except Exception as e:
        print(f"  SadTalker failed: {e}\n  Trying Wav2Lip fallback...")
        from pipeline.stage3_avatar.wav2lip_runner import generate_avatar_video_wav2lip
        path = generate_avatar_video_wav2lip(audio_path=audio, image_path=image, output_path=output)
        print(f"  Output: {path}")
        print("\n[PASS] Stage 3 complete (via Wav2Lip).")


def test_stage4():
    print("\n=== Stage 4: Pictory Upload ===")
    from pipeline.stage4_pictory.pictory_uploader import upload_to_pictory
    video = BASE_DIR / "output" / "avatar_talking.mp4"
    url_file = BASE_DIR / "output" / "final_draft_url.txt"

    if not video.exists():
        print(f"  [SKIP] Video not found: {video}. Run --stage 3 first.")
        return

    url = upload_to_pictory(
        video_path=video,
        script=SAMPLE_SCRIPT,
        topic="AI Technology Test",
        output_url_file=url_file,
    )
    if url:
        print(f"  Pictory draft URL: {url}")
        print("\n[PASS] Stage 4 complete.")
    else:
        print("  Running in stub mode (PICTORY_CLIENT_ID not set). Skipped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["1", "2", "3", "4"], help="Run a specific stage")
    parser.add_argument("--all", action="store_true", help="Run all stages end-to-end")
    args = parser.parse_args()

    if args.all:
        script = test_stage1()
        test_stage2(script)
        test_stage3()
        test_stage4()
    elif args.stage == "1":
        test_stage1()
    elif args.stage == "2":
        test_stage2()
    elif args.stage == "3":
        test_stage3()
    elif args.stage == "4":
        test_stage4()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
