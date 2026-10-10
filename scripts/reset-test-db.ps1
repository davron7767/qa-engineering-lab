<#
.SYNOPSIS
    Reset the dedicated backend TEST database (qa_commerce_test) to the deterministic seed state.

.DESCRIPTION
    Runs `python -m app.db.reset`, which applies migrations, truncates the project's tables and
    re-seeds. It refuses any database whose name does not end in "_test", so it cannot touch the
    development database. To reset the development database, see README "Resetting data".
#>
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
Push-Location $ProjectRoot
try {
    & $Python -m app.db.reset
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
