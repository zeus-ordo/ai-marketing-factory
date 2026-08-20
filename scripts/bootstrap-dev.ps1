$ErrorActionPreference = "Stop"

function Step([string]$Message) {
  Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Ensure-Command([string]$Name, [string]$InstallHint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $Name`nInstall hint: $InstallHint"
  }
}

try {
  $projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
  Set-Location $projectRoot

  Step "Checking required commands"
  Ensure-Command "node" "Install Node.js 20+ from https://nodejs.org/"
  Ensure-Command "npm" "Install Node.js (npm is bundled)"
  Ensure-Command "python" "Install Python 3.11+ from https://www.python.org/downloads/"

  Step "Installing frontend dependencies (npm install)"
  npm install

  Step "Installing backend dependencies (pip requirements)"
  python -m pip install -r "services/campaign_service/requirements.txt"

  $envLocalPath = Join-Path $projectRoot ".env.local"
  $envExamplePath = Join-Path $projectRoot ".env.example"

  if (-not (Test-Path $envLocalPath)) {
    Step "Creating .env.local from .env.example"
    if (-not (Test-Path $envExamplePath)) {
      throw "Missing .env.example; cannot create .env.local"
    }
    Copy-Item $envExamplePath $envLocalPath
    Write-Host "Created .env.local. Please update keys before production use." -ForegroundColor Yellow
  }

  Step "Running environment doctor"
  npm run dev:doctor

  Step "Starting frontend + backend (dev:up)"
  npm run dev:up
}
catch {
  Write-Host "`n[bootstrap] FAILED" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  exit 1
}
