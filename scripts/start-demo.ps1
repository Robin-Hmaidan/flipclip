<#
.SYNOPSIS
  Starts the public FlipClip demo: the production stack on :7860, then an ngrok tunnel to it.

.DESCRIPTION
  The app keeps running in Docker after the tunnel is closed (Ctrl+C); stop it with
  docker compose -f docker-compose.prod.yml down

.EXAMPLE
  .\scripts\start-demo.ps1
  .\scripts\start-demo.ps1 -NoBuild
#>
param(
    [string]$Domain = 'marvelous-pronto-unwieldy.ngrok-free.dev',
    # Skip rebuilding the image, for a restart without code changes.
    [switch]$NoBuild
)

# Not 'Stop': Windows PowerShell turns any stderr of a native command (docker, ngrok) into an
# error then. Every native call below is checked through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'docker-compose.prod.yml'
$port = 7860

function Fail($message) {
    Write-Host "start-demo: $message" -ForegroundColor Red
    exit 1
}

# winget adds ngrok to PATH only for shells opened after the install.
$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    $ngrok = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_*\ngrok.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
}
if (-not $ngrok) { Fail 'ngrok not found. Install it with: winget install Ngrok.Ngrok' }
$ngrokExe = if ($ngrok.Source) { $ngrok.Source } else { $ngrok.FullName }

& $ngrokExe config check *> $null
if ($LASTEXITCODE -ne 0) { Fail 'ngrok has no authtoken yet. Run: ngrok config add-authtoken <YOUR_TOKEN>' }

docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is not running. Start Docker Desktop and try again.' }

Write-Host 'Starting the production stack...' -ForegroundColor Cyan
$upArgs = @('compose', '-f', $compose, 'up', '-d')
if (-not $NoBuild) { $upArgs += '--build' }
& docker @upArgs
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed (see above).' }

Write-Host "Waiting for http://localhost:$port ..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(120)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $res = Invoke-WebRequest "http://localhost:$port/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($res.StatusCode -eq 200) { $healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $healthy) { Fail "The app did not answer on port $port within 2 minutes. Check: docker compose -f docker-compose.prod.yml logs" }

Write-Host "FlipClip is up. Public URL: https://$Domain (Ctrl+C closes the tunnel; the app keeps running)" -ForegroundColor Green
& $ngrokExe http $port --domain=$Domain
# A script's exit code ignores its last native command, so pass ngrok's failure on (bad token,
# old agent, domain in use: ngrok prints which above).
if ($LASTEXITCODE -ne 0) { Fail "ngrok exited with code $LASTEXITCODE (see above)." }
