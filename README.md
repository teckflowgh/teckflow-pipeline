# Automated Daily Video Generation Pipeline

Fully automated pipeline that runs daily to produce a short-form video draft in Pictory — without manual effort.

## Pipeline Stages

| Stage | Technology | What it does |
|-------|-----------|--------------|
| 1 | YouTube API + Claude Haiku | Fetches trending topics, picks best one, writes 60s script |
| 2 | XTTS v2 (coqui-tts) | Clones your voice and synthesizes the script |
| 3 | SadTalker / Wav2Lip | Animates your portrait photo in sync with the audio |
| 4 | Pictory API | Adds B-roll, captions, transitions — saves as Draft |
| 5 | APScheduler | Runs everything automatically at 06:00 every day |

## Quick Start (Windows Local)

### Prerequisites
- Python 3.11+
- Node.js 20+
- NVIDIA GPU (recommended: RTX 3060+, 8 GB VRAM minimum)
- Git

### 1. Install
```powershell
cd "C:\TeckFlow AI Solutions\SocialMediaVideoCreation"
.\scripts\install_local.ps1
```

### 2. Configure
```powershell
# Edit .env with your API keys
notepad .env
```

Required keys:
- `ANTHROPIC_API_KEY` — [console.anthropic.com](https://console.anthropic.com)
- `YOUTUBE_API_KEY` — [console.cloud.google.com](https://console.cloud.google.com) → YouTube Data API v3
- `PICTORY_CLIENT_ID` / `PICTORY_CLIENT_SECRET` — Pictory Teams plan (optional, stub mode if absent)

### 3. Add your assets
```
assets/reference_voice.wav   ← 10–30 seconds of clean voice recording (mono, 22050 Hz+)
assets/avatar_image.jpg      ← Frontal face photo, 512×512 px minimum
```

### 4. Start
```powershell
# Terminal 1: API + scheduler
.\venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --port 8000

# Terminal 2: Dashboard
cd dashboard
npm run dev
```

Open **http://localhost:3000** in your browser.

### 5. Test stages individually
```powershell
python scripts\test_pipeline.py --stage 1   # Research + Claude script
python scripts\test_pipeline.py --stage 2   # Voice synthesis
python scripts\test_pipeline.py --stage 3   # Avatar video
python scripts\test_pipeline.py --stage 4   # Pictory upload
python scripts\test_pipeline.py --all       # Full end-to-end
```

## Project Structure

```
SocialMediaVideoCreation/
├── assets/                   # Your voice & face assets (not committed)
├── output/                   # Generated files (not committed)
├── logs/pipeline.log         # Rotating log file
├── data/
│   ├── run_history.json      # All pipeline runs
│   └── settings.json         # Runtime settings
├── pipeline/
│   ├── orchestrator.py       # Master runner
│   ├── stage1_research/      # YouTube + VidIQ + Claude
│   ├── stage2_voice/         # XTTS v2
│   ├── stage3_avatar/        # SadTalker + Wav2Lip fallback
│   ├── stage4_pictory/       # Pictory REST API
│   └── stage5_scheduler/     # APScheduler + alerts
├── api/                      # FastAPI backend
├── dashboard/                # Next.js dashboard
├── third_party/              # SadTalker, Wav2Lip (clone manually)
└── scripts/                  # Setup & test scripts
```

## Dashboard Pages

- **/** — Live pipeline status, stage stepper, Run Now button, recent logs
- **/history** — Paginated table of all runs with Pictory draft links
- **/settings** — Schedule time, topic source, alert configuration

## Cloud GPU Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for RunPod / Vast.ai instructions.

## Cost Estimate

| Component | Cost |
|-----------|------|
| Claude Haiku (script) | ~$0.002/day |
| YouTube Data API | Free (10k units/day) |
| XTTS v2 voice | Free (local) |
| SadTalker avatar | Free (local) |
| Pictory API | ~$99/mo (Teams plan) |
| RunPod GPU (if cloud) | ~$0.25–0.60/hr |

Without Pictory: entirely free after hardware.

## Troubleshooting

**XTTS fails on first run**: It downloads ~2.2 GB of model weights. Ensure internet access and 5 GB free disk space.

**SadTalker output not found**: Run `python scripts/download_models.py` to fetch checkpoints.

**Windows path error in XTTS**: The project path contains a space (`TeckFlow AI Solutions`). All file paths use `pathlib.Path.resolve()` to handle this — ensure you run from within the virtual environment.

**Pictory 401 error**: Your token expired (1 hour TTL). The uploader re-authenticates on each run automatically.

**Scheduler not running**: Do NOT use `uvicorn --workers N`. The scheduler requires a single process.
