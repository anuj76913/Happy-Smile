<#
.SYNOPSIS
  Run the HappySmile backend locally: Postgres, migrations, seed data, worker and web server.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\run-dev.ps1           # start everything
  powershell -ExecutionPolicy Bypass -File .\run-dev.ps1 -Demo     # also create simulated assistant calls
  powershell -ExecutionPolicy Bypass -File .\run-dev.ps1 -VoiceDemo # the assistant calls your browser after the form
  powershell -ExecutionPolicy Bypass -File .\run-dev.ps1 -Stop     # stop the local Postgres
  powershell -ExecutionPolicy Bypass -File .\run-dev.ps1 -NoServer # set up only (no worker/web server)
#>
param(
  [int]$Port = 8000,
  [switch]$Demo,
  [switch]$VoiceDemo,
  [switch]$Stop,
  [switch]$NoServer
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$data = Join-Path $PSScriptRoot ".localdb\data"
$log = Join-Path $PSScriptRoot ".localdb\postgres.log"
$pgPort = 54329

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

if ($Stop) {
  & pg_ctl stop -D $data -m fast
  exit 0
}

Step "Checking tools"
foreach ($c in "uv", "pg_ctl", "initdb", "psql") {
  if (-not (Get-Command $c -ErrorAction SilentlyContinue)) {
    throw "'$c' not found. Install uv (https://docs.astral.sh/uv/) and PostgreSQL 15+ with its bin folder on PATH."
  }
}
$envArgs = @()
if (Test-Path (Join-Path $PSScriptRoot ".env")) { $envArgs = @("--env-file", ".env"); Write-Host "Using backend\.env" }
else { Write-Host "No .env found: running without Groq (rules-only understanding)." }

Step "Postgres on 127.0.0.1:$pgPort"
if (-not (Test-Path $data)) {
  New-Item -ItemType Directory -Force (Split-Path $data) | Out-Null
  & initdb -D $data -U postgres --auth=trust -E UTF8 --locale=C | Out-Null
  Write-Host "Created a private database cluster in backend\.localdb"
}
& pg_ctl status -D $data *> $null
if ($LASTEXITCODE -ne 0) {
  Start-Process -FilePath pg_ctl -WindowStyle Hidden `
    -ArgumentList @("start", "-D", "`"$data`"", "-l", "`"$log`"", "-o", "`"-p $pgPort -c listen_addresses=127.0.0.1`"")
}
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
  & psql -h 127.0.0.1 -p $pgPort -U postgres -w -tAc "SELECT 1" *> $null
  if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw "Postgres didn't start. See $log" }
$exists = & psql -h 127.0.0.1 -p $pgPort -U postgres -w -tAc "SELECT 1 FROM pg_database WHERE datname='happysmile'"
if ("$exists".Trim() -ne "1") { & psql -h 127.0.0.1 -p $pgPort -U postgres -w -qc "CREATE DATABASE happysmile" }
Write-Host "Postgres is running."

Step "Python dependencies"
& uv sync --quiet

Step "Database schema and seed data"
& uv run @envArgs python -m happysmile.migrate
& uv run @envArgs python -m happysmile.seed | Out-Null
Write-Host "Clinics, dentists, a week of slots and demo staff are in place."

if ($Demo) {
  Step "Simulated assistant calls (demo data)"
  $env:VOICE_AGENT_ENABLED = "true"
  & uv run @envArgs python -m happysmile.simulate
  Remove-Item Env:VOICE_AGENT_ENABLED
}

$marker = Join-Path $PSScriptRoot ".localdb\voice-demo-on"
if ($VoiceDemo) {
  Step "Browser voice demo (development only)"
  # Inherited by the worker window and the web server started below.
  $env:VOICE_AGENT_ENABLED = "true"
  $env:TELEPHONY_PROVIDER = "browser"      # the worker 'dials' the patient's browser tab
  $env:CALLING_WINDOW_START = "00:00"      # works at any hour, including late at night
  $env:CALLING_WINDOW_END = "23:59"
  $env:LAST_CALL_CUTOFF_MIN = "0"
  $env:STAFF_HOURS_START = "00:00"
  $env:STAFF_HOURS_END = "23:59"
  $env:DEDUPE_HOURS = "0"                  # try again with the same mobile number
  $env:RATE_LIMIT_PHONE_PER_HOUR = "100"
  $env:AUTO_KILL_SWITCH = "false"          # nobody is on the console at night to answer urgent handovers
  $env:OPEN_CONSOLE = "true"               # console opens without a login (demo visitor, no Ops rights)
  & uv run @envArgs python -m happysmile.demo_mode on
  New-Item -ItemType File -Force $marker | Out-Null
  Write-Host "Submit the form with 'Call me now': this tab rings in a few seconds. Use Chrome or Edge and allow the microphone."
} elseif (Test-Path $marker) {
  # The last run was a voice demo: put the pilot clinics back to 0% so normal runs aren't affected.
  & uv run @envArgs python -m happysmile.demo_mode off
  Remove-Item $marker
}

if ($NoServer) { Write-Host "`nSetup done (-NoServer)."; exit 0 }

Step "Worker (calls, WhatsApp, alerts) in a separate window"
$workerCmd = "Set-Location '$PSScriptRoot'; uv run $($envArgs -join ' ') python -m happysmile.orchestrator"
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $workerCmd) | Out-Null

Write-Host ""
Write-Host "  Enquiry form   http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "  Staff console  http://127.0.0.1:$Port/console" -ForegroundColor Green
Write-Host "  API docs       http://127.0.0.1:$Port/v1/docs" -ForegroundColor Green
Write-Host "  Logins: kavya / riverside-demo (front desk) · ops / manager-demo · admin / admin-demo"
Write-Host "  Stop: Ctrl+C here, close the worker window, then run .\run-dev.ps1 -Stop"
Write-Host ""

Step "Web server (Ctrl+C to stop)"
& uv run @envArgs uvicorn happysmile.main:app --host 127.0.0.1 --port $Port --reload --timeout-graceful-shutdown 3
