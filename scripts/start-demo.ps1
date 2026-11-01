<#
.SYNOPSIS
  Starts the public FlipClip demo: the production app on :7860 plus its ngrok tunnel, both in Docker.

.DESCRIPTION
  Needs NGROK_AUTHTOKEN=<token> in .env.ngrok at the repo root. Both containers restart with Docker until
  stopped with:  docker compose -f docker-compose.prod.yml --profile tunnel down

.EXAMPLE
  .\scripts\start-demo.ps1
  .\scripts\start-demo.ps1 -NoBuild
#>
param(
    # Skip rebuilding the image, for a restart without code changes.
    [switch]$NoBuild
)

# Not 'Stop': Windows PowerShell turns any stderr of a native command (docker) into an error
# then. Every native call below is checked through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$compose = @('compose', '-f', (Join-Path $root 'docker-compose.prod.yml'), '--profile', 'tunnel')
$tokenFile = Join-Path $root '.env.ngrok'
$appEnvFile = Join-Path $root '.env'
$tokenLine = '^\s*NGROK_AUTHTOKEN\s*=\s*\S+'

function Fail($message) {
    Write-Host "start-demo: $message" -ForegroundColor Red
    exit 1
}

# Only tests that a value is set; the token itself is never printed. Compose would also refuse a
# missing file, but not an empty one.
$hasToken = (Test-Path $tokenFile) -and (Select-String -Path $tokenFile -Pattern $tokenLine -Quiet)
if (-not $hasToken) { Fail "NGROK_AUTHTOKEN is not set. Add this line to $tokenFile : NGROK_AUTHTOKEN=<your token>" }
# .env is read by the app container, so a token there would leak into it.
if ((Test-Path $appEnvFile) -and (Select-String -Path $appEnvFile -Pattern $tokenLine -Quiet)) {
    Fail "Move the NGROK_AUTHTOKEN line out of $appEnvFile into $tokenFile (.env reaches the app container)."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is not running. Start Docker Desktop and try again.' }

# --wait returns once the app is healthy and the tunnel container is running, or fails if not.
Write-Host 'Starting the app and the tunnel...' -ForegroundColor Cyan
$upArgs = $compose + @('up', '-d', '--wait', '--wait-timeout', '180')
if (-not $NoBuild) { $upArgs += '--build' }
& docker @upArgs
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed (see above).' }

# The container running doesn't mean ngrok got online (bad token, domain in use): ask its API.
$deadline = (Get-Date).AddSeconds(60)
$url = $null
while ((Get-Date) -lt $deadline -and -not $url) {
    try {
        $tunnels = Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 5 -ErrorAction Stop
        $url = $tunnels.tunnels | Where-Object { $_.public_url -like 'https://*' } | Select-Object -First 1 -ExpandProperty public_url
    } catch { }
    if (-not $url) { Start-Sleep -Seconds 2 }
}
if (-not $url) {
    & docker @($compose + @('logs', '--tail', '20', 'ngrok'))
    Fail 'The tunnel did not come online within a minute (ngrok log above).'
}

Write-Host "FlipClip is live at $url (local: http://localhost:7860)" -ForegroundColor Green
Write-Host 'Stop it with: docker compose -f docker-compose.prod.yml --profile tunnel down'
