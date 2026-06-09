# ============================================================
# Local Windows Install Script — PowerShell
# Run from the project root:
#   cd "C:\TeckFlow AI Solutions\SocialMediaVideoCreation"
#   .\scripts\install_local.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent

Write-Host "`n=== Video Pipeline — Local Windows Setup ===" -ForegroundColor Cyan

# --- Clone third-party repos ---
Push-Location $ProjectRoot
if (-not (Test-Path "third_party\LivePortrait\.git")) {
    Write-Host "`nCloning LivePortrait (primary avatar engine)..." -ForegroundColor Yellow
    git clone https://github.com/KwaiVision/LivePortrait third_party/LivePortrait
} else {
    Write-Host "[skip] LivePortrait already cloned."
}

if (-not (Test-Path "third_party\SadTalker\.git")) {
    Write-Host "`nCloning SadTalker (fallback)..." -ForegroundColor Yellow
    git clone https://github.com/OpenTalker/SadTalker third_party/SadTalker
} else {
    Write-Host "[skip] SadTalker already cloned."
}

if (-not (Test-Path "third_party\Wav2Lip\.git")) {
    Write-Host "Cloning Wav2Lip..." -ForegroundColor Yellow
    git clone https://github.com/Rudrabha/Wav2Lip third_party/Wav2Lip
} else {
    Write-Host "[skip] Wav2Lip already cloned."
}

# --- Python virtual environment ---
Write-Host "`nCreating Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& ".\venv\Scripts\Activate.ps1"

# --- PyTorch with CUDA ---
Write-Host "`nInstalling PyTorch with CUDA 12.4..." -ForegroundColor Yellow
pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu124

# --- Main dependencies ---
Write-Host "`nInstalling requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt

# --- Playwright browsers ---
Write-Host "`nInstalling Playwright Chromium..." -ForegroundColor Yellow
playwright install chromium

# --- SadTalker requirements ---
Write-Host "`nInstalling SadTalker requirements..." -ForegroundColor Yellow
pip install -r third_party\SadTalker\requirements.txt

# --- Download model checkpoints ---
Write-Host "`nDownloading model checkpoints..." -ForegroundColor Yellow
python scripts\download_models.py

# --- Environment file ---
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "`n[!] .env created from template. Fill in your API keys!" -ForegroundColor Red
} else {
    Write-Host "[skip] .env already exists."
}

# --- Verify assets ---
if (-not (Test-Path "assets\reference_voice.wav")) {
    Write-Host "[!] MISSING: assets\reference_voice.wav — place a 10-30s clean voice recording here." -ForegroundColor Red
}
if (-not (Test-Path "assets\avatar_image.jpg")) {
    Write-Host "[!] MISSING: assets\avatar_image.jpg — place a frontal face photo here." -ForegroundColor Red
}

# --- Next.js dashboard ---
Write-Host "`nInstalling Next.js dashboard dependencies..." -ForegroundColor Yellow
Push-Location dashboard
npm install
Pop-Location

Pop-Location

Write-Host @"

=== Setup complete! ===

Next steps:
  1. Edit .env and fill in ANTHROPIC_API_KEY, YOUTUBE_API_KEY, PICTORY_* keys
  2. Place assets\reference_voice.wav   (10-30s clean voice sample)
  3. Place assets\reference_clip.mp4   (5-10s video van jezelf, recht in de camera)
  4. Optioneel: assets\avatar_image.jpg (foto als fallback)
  4. Start the API:   uvicorn api.main:app --reload --port 8000
  5. Start dashboard: cd dashboard; npm run dev
  6. Test stage 1:    python scripts\test_pipeline.py --stage 1

"@ -ForegroundColor Green
