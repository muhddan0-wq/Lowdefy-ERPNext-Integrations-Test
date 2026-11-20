param(
  [int]$Port = 3010,
  [int]$ApiPort = 4010,
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot

if (-not (Test-Path (Join-Path $AppRoot ".env"))) {
  Write-Host "No .env found - running setup-env.ps1 first." -ForegroundColor Yellow
  & (Join-Path $AppRoot "setup-env.ps1")
}

Write-Host "Preparing local SQLite database (audit log + settings)..."
node (Join-Path $AppRoot "scripts\init-db.mjs")
if ($LASTEXITCODE -ne 0) { throw "Database initialisation failed." }

$health = $null
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 5
} catch {
  $health = $null
}

if ($health -and $health.ok) {
  Write-Host "Copilot data service already running on port $ApiPort." -ForegroundColor Green
} else {
  Write-Host "Starting Copilot data service on port $ApiPort..."
  $apiLog = Join-Path $AppRoot "data\api.log"
  $apiErr = Join-Path $AppRoot "data\api.err.log"
  Start-Process -FilePath "node" -ArgumentList "server\copilot-api.mjs" -WorkingDirectory $AppRoot `
    -WindowStyle Hidden -RedirectStandardOutput $apiLog -RedirectStandardError $apiErr | Out-Null
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 3
      if ($health.ok) { $ready = $true; break }
    } catch { }
  }
  if (-not $ready) {
    Write-Host "Copilot data service did not report healthy. Check data\api.log and data\api.err.log." -ForegroundColor Red
  } else {
    Write-Host "Copilot data service ready (ERPNext $($health.erpnext.erpnext_version))." -ForegroundColor Green
  }
}

$cliArgs = @("lowdefy@7.1.0", "dev", "--port", "$Port")
if ($NoOpen) { $cliArgs += "--no-open" }

Write-Host "Starting Lowdefy (pinned 7.1.0). Watch the log for the real URL." -ForegroundColor Green
npx -y @cliArgs
