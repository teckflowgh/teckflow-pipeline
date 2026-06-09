# Cloud GPU Deployment Guide

## RunPod (Recommended)

### 1. Create a Pod
- Go to [runpod.io](https://runpod.io) → **Deploy**
- Template: **RunPod PyTorch 2.4** (Ubuntu 22.04, CUDA 12.4 pre-installed)
- GPU: **RTX 4090 24 GB** (~$0.50/hr) or **RTX 3090 24 GB** (~$0.25/hr)
- Disk: 50 GB container + 20 GB volume (for model weights)
- Expose HTTP ports: **8000** and **3000**

### 2. Upload your assets
In the RunPod file manager (or via `scp`):
```bash
scp assets/reference_voice.wav root@<pod-ip>:/workspace/project/assets/
scp assets/avatar_image.jpg    root@<pod-ip>:/workspace/project/assets/
```

### 3. Clone the project and run bootstrap
```bash
git clone <your-repo-url> /workspace/project
cd /workspace/project
chmod +x scripts/install_gpu_cloud.sh
./scripts/install_gpu_cloud.sh
```

### 4. Configure environment
```bash
nano .env   # Fill in ANTHROPIC_API_KEY, YOUTUBE_API_KEY, PICTORY_* etc.
```

### 5. Download model checkpoints
```bash
python scripts/download_models.py
```

### 6. Start services with PM2
```bash
pm2 start "uvicorn api.main:app --host 0.0.0.0 --port 8000" --name api
pm2 start "npm start" --name dashboard --cwd /workspace/project/dashboard
pm2 save
pm2 startup   # Auto-restart on pod reboot
```

### 7. Access the dashboard
RunPod provides a public URL per exposed port:
- API: `https://<pod-id>-8000.proxy.runpod.net`
- Dashboard: `https://<pod-id>-3000.proxy.runpod.net`

Update `dashboard/.env.local`:
```
NEXT_PUBLIC_API_URL=https://<pod-id>-8000.proxy.runpod.net
```
Then rebuild: `cd dashboard && npm run build && pm2 restart dashboard`

---

## Vast.ai

### 1. Find an instance
- Go to [vast.ai](https://vast.ai) → **Search**
- Filter: **PyTorch** template, CUDA 12.x, ≥24 GB VRAM
- Recommended: RTX 3090 or 4090, ~$0.20–0.50/hr

### 2. Connect and setup
```bash
# vast.ai gives you SSH access
ssh -p <port> root@<host>

git clone <your-repo-url> ~/project
cd ~/project
./scripts/install_gpu_cloud.sh
```

### 3. Port forwarding
Vast.ai instances expose ports via SSH tunneling. Add to your `.ssh/config`:
```
LocalForward 8000 localhost:8000
LocalForward 3000 localhost:3000
```
Then access locally at `http://localhost:3000`.

---

## Cost Optimisation: Serverless / Scheduled GPU

Instead of leaving a GPU pod running 24/7 (~$6–15/day), use RunPod Serverless:

1. Package the pipeline as a serverless function (RunPod handler)
2. The APScheduler triggers the serverless endpoint instead of running locally
3. The GPU spins up only for the ~3–5 minute pipeline run
4. Cost: ~$0.02–0.05 per daily run

This approach requires refactoring the pipeline into a RunPod serverless handler — documented as a future enhancement.

---

## Environment Checklist

Before starting on cloud:

- [ ] `.env` filled with all API keys
- [ ] `assets/reference_voice.wav` uploaded (10–30s clean voice)
- [ ] `assets/avatar_image.jpg` uploaded (512x512+ frontal face)
- [ ] SadTalker checkpoints downloaded (`python scripts/download_models.py`)
- [ ] GFPGAN checkpoint present (`third_party/SadTalker/gfpgan/weights/GFPGANv1.4.pth`)
- [ ] PM2 services running (`pm2 list`)
- [ ] Dashboard accessible in browser
- [ ] Test run triggered via dashboard → "Run Now"
