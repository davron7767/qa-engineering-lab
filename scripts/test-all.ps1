<#
.SYNOPSIS
    Run the same checks as the pull-request workflow, locally, in order.

.DESCRIPTION
    Requires the application to be running (docker compose up -d, or scripts\local-app.ps1) and
    PostgreSQL to be reachable on POSTGRES_HOST_PORT. Stops at the first failing stage.

.EXAMPLE
    .\scripts\test-all.ps1
    .\scripts\test-all.ps1 -SkipLint
#>
param([switch]$SkipLint)

# Native tools (npm, pytest) report failure via exit codes; npm also writes notices to stderr,
# which 'Stop' would turn into terminating errors. Every stage checks $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$env:npm_config_loglevel = 'warn'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Automation = Join-Path $ProjectRoot 'automation'

function Invoke-Stage([string]$Name, [scriptblock]$Command) {
    Write-Host "`n=== $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $Name" -ForegroundColor Red; exit $LASTEXITCODE }
}

Push-Location $ProjectRoot
try {
    & (Join-Path $PSScriptRoot 'wait-for-health.ps1') -TimeoutSeconds 30
    if ($LASTEXITCODE -ne 0) { exit 1 }
    if (-not $SkipLint) {
        Invoke-Stage 'Python lint' { & $Python -m ruff check . }
        Invoke-Stage 'Python format check' { & $Python -m ruff format --check . }
        Invoke-Stage 'TypeScript lint and type check' { Push-Location $Automation; npm run lint; if ($LASTEXITCODE -eq 0) { npm run typecheck }; Pop-Location }
    }
    Invoke-Stage 'Backend unit tests' { & $Python -m pytest backend-tests/unit -q --junitxml=reports/backend-unit.xml }
    Invoke-Stage 'Backend integration tests' { & $Python -m pytest backend-tests/integration -q --junitxml=reports/backend-integration.xml }
    Invoke-Stage 'Playwright API, regression, UI and e2e (Chromium)' { Push-Location $Automation; npm test; Pop-Location }
    Write-Host "`nAll stages passed. HTML report: automation\playwright-report\index.html" -ForegroundColor Green
}
finally {
    Pop-Location
}
