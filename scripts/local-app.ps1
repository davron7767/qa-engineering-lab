<#
.SYNOPSIS
    Docker-free fallback: run the QA Commerce app on the host from the project virtualenv.

.DESCRIPTION
    Starts `python -m app.serve` in the background (migrations + seed + uvicorn) using the
    settings in .env, logs to .local\app.log, and waits for /api/v1/health to report ready.
    Extra environment variables (e.g. DEFECT_MODE) can be passed with -Env.

.EXAMPLE
    .\scripts\local-app.ps1 start
    .\scripts\local-app.ps1 start -Env @{ DEFECT_MODE = 'wrong_total' }
    .\scripts\local-app.ps1 stop
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart')]
    [string]$Command = 'start',
    [int]$Port = 8000,
    [hashtable]$Env = @{}
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDir = Join-Path $ProjectRoot '.local'

function Stop-App {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($l in $listeners) {
        Stop-Process -Id $l.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped process $($l.OwningProcess) listening on port $Port"
    }
}

function Start-App {
    if (-not (Test-Path $Python)) { throw "Virtualenv not found. Run: py -3.13 -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt" }
    New-Item -ItemType Directory -Force $LogDir | Out-Null
    $saved = @{}
    foreach ($key in $Env.Keys) { $saved[$key] = [Environment]::GetEnvironmentVariable($key); [Environment]::SetEnvironmentVariable($key, [string]$Env[$key]) }
    try {
        Start-Process -FilePath $Python -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
            -ArgumentList @('-m', 'app.serve', '--port', $Port) `
            -RedirectStandardOutput (Join-Path $LogDir 'app.out.log') -RedirectStandardError (Join-Path $LogDir 'app.log') | Out-Null
    }
    finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key]) }
    }
    & (Join-Path $PSScriptRoot 'wait-for-health.ps1') -Url "http://localhost:$Port/api/v1/health" -TimeoutSeconds 60
}

switch ($Command) {
    'start' { Stop-App; Start-App }
    'restart' { Stop-App; Start-App }
    'stop' { Stop-App }
}
