# GCP Auto Deployment Script for AI Marketing Factory
param(
  [string]$ProjectId = "",
  [string]$Region = "asia-east1",
  [string]$Zone = "asia-east1-a",
  [string]$VmName = "ai-marketing-factory",
  [string]$RepoUrl = "",
  [string]$DeepSeekKey = "",
  [string]$GeminiKey = "",
  [switch]$SkipSecrets,
  [switch]$Force   # skip confirmation prompt
)

$ErrorActionPreference = "Stop"

# Add gcloud to PATH if not present
$gcloudBin = "C:\Users\User\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
$gcloudCmd = "$gcloudBin\gcloud.cmd"
if (Test-Path $gcloudCmd) {
  $env:PATH = "$gcloudBin;$env:PATH"
}

function Write-Step { param([string]$m) Write-Host "[STEP] $m" -ForegroundColor Cyan }
function Write-Success { param([string]$m) Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Warn { param([string]$m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err { param([string]$m) Write-Host "[ERR]  $m" -ForegroundColor Red }
function Write-Info { param([string]$m) Write-Host "       $m" }
function Gcloud {
  $cmd = if (Test-Path $gcloudCmd) { $gcloudCmd } else { "gcloud" }
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $cmd
  $psi.Arguments = $args -join ' '
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.EnvironmentVariables["CLOUDSDK_CONFIG"] = "$env:APPDATA\Google\Cloud SDK"
  $psi.EnvironmentVariables["CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"] = "$env:APPDATA\gcloud\credentials.db"
  $proc = [System.Diagnostics.Process]::Start($psi)
  $stdout = $proc.StandardOutput.ReadToEnd()
  $stderr = $proc.StandardError.ReadToEnd()
  $proc.WaitForExit()
  $script:LASTEXITCODE = $proc.ExitCode
  return $stdout + $stderr
}
function Rand-Password {
  $c = [char[]](48..57 + 97..122 + 65..90)
  return -join ($c | Get-Random -Count 32)
}
function Rand-Token {
  $c = [char[]](48..57 + 97..122)
  return -join ($c | Get-Random -Count 48)
}

Write-Host ""
Write-Host "========================================" -ForegroundColor White
Write-Host " AI Marketing Factory - GCP Auto Deploy" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host ""

# ---- Pre-checks ----
Write-Step "Checking prerequisites..."
try {
  $gv = (gcloud --version 2>&1 | Select-Object -First 1)
  Write-Info "gcloud: $gv"
} catch {
  Write-Err "gcloud CLI not found."
  exit 1
}

# ---- Collect params ----
Write-Step "Collecting parameters..."

if (-not $ProjectId) { $ProjectId = Read-Host "GCP Project ID (e.g. market-factory)" }
$ProjectId = $ProjectId.Trim()
if (-not $ProjectId) { Write-Err "Project ID required." ; exit 1 }

if (-not $DeepSeekKey) { $DeepSeekKey = Read-Host "DeepSeek API Key (copy generation)" }
$DeepSeekKey = $DeepSeekKey.Trim()
if (-not $DeepSeekKey) { Write-Err "DeepSeek API Key required." ; exit 1 }

if (-not $GeminiKey) { $GeminiKey = Read-Host "Google AI Studio API Key (Gemini+Veo)" }
$GeminiKey = $GeminiKey.Trim()
if (-not $GeminiKey) { Write-Err "Gemini API Key required." ; exit 1 }

$RepoUrl = $RepoUrl.Trim()

Write-Host ""
Write-Info "Project: $ProjectId | Region: $Region/$Zone"
Write-Info "VM    : $VmName (e2-standard-4, 100GB SSD)"
Write-Info "Repo  : $(if ($RepoUrl) { $RepoUrl } else { '(skip)' })"
if (-not $Force) {
  $cont = Read-Host "Continue? ( y / n )"
  if ($cont -ne "y") { Write-Info "Cancelled." ; exit 0 }
}

# ---- Set project ----
Write-Step "Setting gcloud project..."
Gcloud "config" "set" "project" $ProjectId | Out-Null
Gcloud "config" "set" "region" $Region | Out-Null
Gcloud "config" "set" "zone" $Zone | Out-Null
Write-Success "Project set"

# ---- Enable APIs (already done) ----
Write-Step "APIs already enabled, skipping..."

# ---- Generate secrets ----
Write-Step "Generating secrets..."
$dbPassword  = Rand-Password
$jwtSecret   = Rand-Token
$platAdmin   = Rand-Token
$chatPending = Rand-Token
$chatActor   = Rand-Token
$chatbotApi  = Rand-Token
$chatAudit   = Rand-Token
Write-Success "Secrets generated"

# ---- Static IP ----
Write-Step "Creating static IP..."
$check = Gcloud "compute" "addresses" "describe" "${VmName}-ip" "--region" $Region
if ($LASTEXITCODE -eq 0) {
  $vmIp = (Gcloud "compute" "addresses" "describe" "${VmName}-ip" "--region" $Region "--format=value(address)").Trim()
  Write-Info "  Existing: $vmIp"
} else {
  Gcloud "compute" "addresses" "create" "${VmName}-ip" "--region" $Region "--quiet" | Out-Null
  $vmIp = (Gcloud "compute" "addresses" "describe" "${VmName}-ip" "--region" $Region "--format=value(address)").Trim()
  Write-Info "  New IP: $vmIp"
}
Write-Success "Static IP: $vmIp"

# ---- Firewall ----
Write-Step "Setting up firewall..."
$fw = Gcloud "compute" "firewall-rules" "describe" "allow-http-https"
if ($LASTEXITCODE -ne 0) {
  Gcloud "compute" "firewall-rules" "create" "allow-http-https" `
    "--network=default" "--allow=tcp:80,tcp:443" "--target-tags=$VmName" "--quiet" | Out-Null
  Write-Info "  HTTP/HTTPS rule created"
} else {
  Write-Info "  HTTP/HTTPS rule exists"
}
Write-Success "Firewall done"

# ---- Create VM ----
Write-Step "Creating Compute Engine VM..."
$vmChk = Gcloud "compute" "instances" "describe" $VmName "--zone" $Zone
if ($LASTEXITCODE -eq 0) {
  Write-Warn "  VM $VmName already exists!"
  $vmIp = (Gcloud "compute" "instances" "describe" $VmName "--zone" $Zone "--format=value(networkInterfaces[0].accessConfigs[0].natIP)").Trim()
  $vmInternalIp = (Gcloud "compute" "instances" "describe" $VmName "--zone" $Zone "--format=value(networkInterfaces[0].networkIP)").Trim()
} else {
  Write-Info "  Creating VM..."
  Gcloud "compute" "instances" "create" $VmName `
    "--zone=$Zone" "--machine-type=e2-standard-4" `
    "--image-family=ubuntu-2204-lts" "--image-project=ubuntu-os-cloud" `
    "--boot-disk-size=100GB" "--boot-disk-type=pd-balanced" `
    "--network=default" "--tags=$VmName" "--metadata=enable-oslogin=true" "--quiet" | Out-Null
  Write-Info "  Waiting 30 sec..."
  Start-Sleep -Seconds 30
  $vmIp = (Gcloud "compute" "instances" "describe" $VmName "--zone" $Zone "--format=value(networkInterfaces[0].accessConfigs[0].natIP)").Trim()
  $vmInternalIp = (Gcloud "compute" "instances" "describe" $VmName "--zone" $Zone "--format=value(networkInterfaces[0].networkIP)").Trim()
  Gcloud "compute" "firewall-rules" "create" "allow-ssh" "--network=default" "--allow=tcp:22" "--source-ranges=0.0.0.0/0" "--target-tags=$VmName" "--quiet" 2>$null | Out-Null
}
$vmSa = (Gcloud "compute" "instances" "describe" $VmName "--zone" $Zone "--format=value(serviceAccounts[0].email)").Trim()
Write-Success "VM ready"
Write-Info "  Public IP : $vmIp"
Write-Info "  Private IP: $vmInternalIp"
Write-Info "  SA       : $vmSa"

Write-Info "  Waiting for SSH..."
for ($i = 0; $i -lt 24; $i++) {
  $ok = Test-NetConnection -ComputerName $vmIp -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
  if ($ok) { Write-Info "  SSH ready"; break }
  Start-Sleep -Seconds 5
}

# ---- Secret Manager ----
if (-not $SkipSecrets) {
  Write-Step "Creating Secret Manager secrets..."
  $secrets = @{
    "jwt-secret"          = $jwtSecret
    "platform-admin-key"  = $platAdmin
    "database-password"   = $dbPassword
    "deepseek-api-key"   = $DeepSeekKey
    "gemini-api-key"      = $GeminiKey
  }
  foreach ($kv in $secrets.GetEnumerator()) {
    $n = $kv.Key; $v = $kv.Value
    $ex = Gcloud "secrets" "describe" $n
    if ($LASTEXITCODE -eq 0) {
      $v | gcloud secrets versions add $n --data-file=- --quiet 2>&1 | Out-Null
      Write-Info "  Updated: $n"
    } else {
      $v | gcloud secrets create $n --data-file=- --quiet 2>&1 | Out-Null
      Write-Info "  Created: $n"
    }
  }
  Gcloud "projects" "add-iam-policy-binding" $ProjectId "--member=serviceAccount:$vmSa" "--role=roles/secretmanager.secretAccessor" "--quiet" | Out-Null
  Write-Success "Secrets done"
}

# ---- Cloud SQL ----
Write-Step "Creating Cloud SQL PostgreSQL..."
$sqlChk = Gcloud "sql" "instances" "describe" "ai-marketing-postgres"
if ($LASTEXITCODE -eq 0) {
  Write-Warn "  Cloud SQL already exists"
  $sqlIp = (Gcloud "sql" "instances" "describe" "ai-marketing-postgres" "--format=value(ipAddresses[0].ipAddress)").Trim()
} else {
  Write-Info "  Creating (db-custom-2-7680, ~3-5 min)..."
  Gcloud "sql" "instances" "create" "ai-marketing-postgres" `
    "--database-version=POSTGRES_16" "--tier=db-custom-2-7680" "--region=$Region" `
    "--storage-type=SSD" "--storage-size=50" "--storage-auto-increase" `
    "--backup-start-time=03:00" "--enable-point-in-time-recovery" "--quiet" | Out-Null
  Write-Info "  Waiting 90 sec..."
  Start-Sleep -Seconds 90
  $sqlIp = (Gcloud "sql" "instances" "describe" "ai-marketing-postgres" "--format=value(ipAddresses[0].ipAddress)").Trim()
}
Write-Info "  Cloud SQL IP: $sqlIp"
Write-Info "  Creating databases..."
Gcloud "sql" "databases" "create" "marketing_ai" "--instance=ai-marketing-postgres" "--quiet" 2>$null | Out-Null
Gcloud "sql" "databases" "create" "membership" "--instance=ai-marketing-postgres" "--quiet" 2>$null | Out-Null
Write-Info "  Creating DB user..."
$userChk = Gcloud "sql" "users" "describe" "app" "--instance=ai-marketing-postgres"
if ($LASTEXITCODE -ne 0) {
  Gcloud "sql" "users" "create" "app" "--instance=ai-marketing-postgres" "--password=$dbPassword" "--quiet" | Out-Null
}
Write-Success "Cloud SQL done: $sqlIp"

# ---- Memorystore Redis ----
Write-Step "Creating Memorystore Redis..."
$redisChk = Gcloud "redis" "instances" "describe" "ai-marketing-redis" "--region=$Region"
if ($LASTEXITCODE -eq 0) {
  Write-Warn "  Redis already exists"
  $redisIp = (Gcloud "redis" "instances" "describe" "ai-marketing-redis" "--region=$Region" "--format=value(host)").Trim()
} else {
  Write-Info "  Creating (5GB, ~2-3 min)..."
  Gcloud "redis" "instances" "create" "ai-marketing-redis" `
    "--region=$Region" "--zone=$Zone" "--tier=basic" "--size=5" `
    "--redis-version=redis_7_2" "--network=default" "--quiet" | Out-Null
  Write-Info "  Waiting 120 sec..."
  Start-Sleep -Seconds 120
  $redisIp = (Gcloud "redis" "instances" "describe" "ai-marketing-redis" "--region=$Region" "--format=value(host)").Trim()
}
Write-Success "Redis done: $redisIp"

# ---- Write remote bash script via Python (bypasses PowerShell parser completely) ----
Write-Step "Writing VM setup script via Python..."

$repoClonePython = if ($RepoUrl) { "subprocess.run(['git', 'clone', '$RepoUrl', '/opt/ai-marketing-factory'], check=True)" } else { "print('No repo URL - skipping clone')" }

$pythonCode = @"
import os, subprocess, sys, tempfile

vm_ip = "$vmIp"
db_password = "$dbPassword"
sql_ip = "$sqlIp"
redis_ip = "$redisIp"
jwt_secret = "$jwtSecret"
plat_admin = "$platAdmin"
chat_pending = "$chatPending"
chat_actor = "$chatActor"
chatbot_api = "$chatbotApi"
chat_audit = "$chatAudit"
deepseek_key = "$DeepSeekKey"
gemini_key = "$GeminiKey"
repo_clone = "$repoClonePython"

env_local = f"""APP_ENV=production
CAMPAIGN_REQUIRE_POSTGRES=true
POSTGRES_DSN=postgresql://app:{db_password}@{sql_ip}:5432/marketing_ai
MEMBERSHIP_DB_DSN=postgresql://app:{db_password}@{sql_ip}:5432/membership
REDIS_URL=redis://{redis_ip}:6379/0
JWT_SECRET={jwt_secret}
PLATFORM_ADMIN_KEY={plat_admin}
CHAT_PENDING_ACTION_SECRET={chat_pending}
CHAT_ACTOR_TOKEN_SECRET={chat_actor}
CHATBOT_INTERNAL_API_KEY={chatbot_api}
CHAT_AUDIT_API_KEY={chat_audit}
DEEPSEEK_R1_API_KEY={deepseek_key}
DEEPSEEK_V3_API_KEY={deepseek_key}
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-flash
GEMINI_API_KEY={gemini_key}
IMAGE_WORKER_PROVIDER=gemini
VIDEO_WORKER_PROVIDER=veo
WORKER_STRICT_REAL_MODE=true
WORKER_REQUEST_TIMEOUT_SECONDS=180
PUBLISHING_ENABLED=false
SLA_SCAN_ENABLED=true
TRACE_RETENTION_DAYS=90
"""

bash_script = f"""#!/bin/bash
set -e
LOG='/tmp/vm-setup.log'
exec > >(tee -a "$LOG") 2>&1

echo "=== VM Setup Started ==="
echo "Time: $(date)"

echo "[1/7] Installing Docker..."
if ! command -v docker &> /dev/null; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git jq unzip rsync
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker $(whoami)
fi
docker version | head -1
echo "Docker done"

echo "[2/7] Creating directories..."
sudo mkdir -p /opt/ai-marketing-factory
sudo mkdir -p /var/lib/ai-marketing-factory/campaign_references
sudo mkdir -p /var/lib/ai-marketing-factory/generated_assets
sudo chown -R $(whoami):$(whoami) /opt/ai-marketing-factory
sudo chown -R $(whoami):$(whoami) /var/lib/ai-marketing-factory
echo "Directories done"

echo "[3/7] Getting source code..."
if [ -d '/opt/ai-marketing-factory/.git' ]; then
  echo "Repo exists, pulling..."
  cd /opt/ai-marketing-factory && git pull
else
  {repo_clone}
fi
echo "Source done"

echo "[4/7] Writing .env.local..."
cat > /opt/ai-marketing-factory/.env.local << 'ENVEOF'
{env_local}
ENVEOF
chmod 600 /opt/ai-marketing-factory/.env.local
echo ".env.local done"

echo "[5/7] Starting services..."
cd /opt/ai-marketing-factory
(docker compose -f deploy/docker-compose.gcp.yml down --remove-orphans 2>/dev/null || true)
docker compose -f deploy/docker-compose.gcp.yml up -d
echo "Services started"

echo "[6/7] Waiting for services (40 sec)..."
sleep 40

echo "=== Container Status ==="
docker compose -f deploy/docker-compose.gcp.yml ps

echo "=== Recent Logs ==="
docker compose -f deploy/docker-compose.gcp.yml logs --tail=20

echo "[7/7] Health check..."
for i in 1 2 3 4 5; do
  HTTP_CODE=$(curl -sL -o /dev/null -w '%{{http_code}}' http://localhost/ 2>/dev/null)
  CURL_RET=$?
  if [ $CURL_RET -ne 0 ]; then
    HTTP_CODE='000'
  fi
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "307" ] || [ "$HTTP_CODE" = "301" ]; then
    echo "HTTP $HTTP_CODE - Services UP!"
    echo ""
    echo "=== Deployment Complete ==="
    echo "Open http://{vm_ip}"
    exit 0
  fi
  echo "Waiting... ($i/5)"
  sleep 15
done

echo "Warning: health check did not pass."
echo "Run: docker compose -f deploy/docker-compose.gcp.yml ps"
"""

tmp = os.path.join(os.environ['TEMP'], 'gcp-vm-setup-' + str(os.getpid()) + '.sh')
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(bash_script)
print('SCRIPT_WRITTEN:' + tmp)
"@

$tmpPy = "$env:TEMP\gcp_deploy_w_$(Get-Random).py"
[System.IO.File]::WriteAllText($tmpPy, $pythonCode, [System.Text.UTF8Encoding]::new($false))
$pyOut = python $tmpPy 2>&1
Remove-Item $tmpPy -Force -EA SilentlyContinue

if (-not $pyOut.StartsWith("SCRIPT_WRITTEN:")) {
    Write-Err "Python failed to write script: $pyOut"
    exit 1
}
$tmpScript = $pyOut -replace 'SCRIPT_WRITTEN:', ''
Write-Info "  Script written: $tmpScript"

# ---- Upload to VM ----
Write-Step "Uploading setup script to VM..."
$scp = Gcloud "compute" "scp" $tmpScript "${VmName}:/tmp/gcp-vm-setup.sh" "--zone=$Zone" "--quiet"
if ($LASTEXITCODE -ne 0) {
  Write-Err "SCP failed: $scp"
  Write-Info "Manual: gcloud compute scp $tmpScript ${VmName}:/tmp/gcp-vm-setup.sh --zone=$Zone"
  exit 1
}
Write-Success "Script uploaded"
Remove-Item $tmpScript -Force -EA SilentlyContinue

# ---- Execute on VM ----
Write-Step "Running VM setup on $VmName (5-10 min - DO NOT interrupt)..."
Write-Warn "Longest step..."

$sshOut = Gcloud "compute" "ssh" $VmName "--zone=$Zone" "--command=chmod +x /tmp/gcp-vm-setup.sh && bash /tmp/gcp-vm-setup.sh"

Write-Host ""
Write-Host "========== VM Output ==========" -ForegroundColor White
Write-Host $sshOut
Write-Host "================================" -ForegroundColor White

$ok = $sshOut -match "Deployment Complete|deployment complete"
if ($ok) {
  Write-Success "Deployment completed!"
} else {
  Write-Warn "Script finished but success marker not found."
  Write-Info "Check manually: gcloud compute ssh $VmName --zone=$Zone"
}

# ---- Summary ----
Write-Host ""
Write-Host "========================================" -ForegroundColor White
Write-Host " Deployment Summary" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host ""
Write-Info "VM Public IP    : $vmIp"
Write-Info "Cloud SQL       : $sqlIp"
Write-Info "Redis           : $redisIp"
Write-Info "VM Service Acct : $vmSa"
Write-Host ""
Write-Info "NEXT STEPS:"
Write-Info "  1. Set DNS A record -> $vmIp"
Write-Info "  2. Open http://$vmIp"
Write-Info "  3. Login: regression.admin@example.com / Regress!2026Pass#A"
Write-Host ""
Write-Info "VM commands:"
Write-Info "  SSH   : gcloud compute ssh $VmName --zone=$Zone"
Write-Info "  Status: docker compose -f deploy/docker-compose.gcp.yml ps"
Write-Info "  Logs  : docker compose -f deploy/docker-compose.gcp.yml logs --tail=50"
Write-Host ""
