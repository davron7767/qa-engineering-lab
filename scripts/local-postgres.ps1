<#
.SYNOPSIS
    Docker-free fallback: run a portable PostgreSQL 17 for QA Commerce on this machine.

.DESCRIPTION
    Use this ONLY when Docker Desktop is unavailable. It downloads the official EDB Windows
    binaries into .local\pgsql (git-ignored), initialises a cluster in .local\pgdata, and serves it
    on the same port, user and database names as the Docker Compose "db" service, so the same
    .env works for both paths. Nothing is installed system-wide and no Windows service is created.

.EXAMPLE
    .\scripts\local-postgres.ps1 start     # download (first run), init (first run), start
    .\scripts\local-postgres.ps1 status
    .\scripts\local-postgres.ps1 stop
    .\scripts\local-postgres.ps1 destroy   # stop and delete .local\pgdata (project data only)
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'destroy')]
    [string]$Command = 'status',
    [int]$Port = 5433,
    [string]$User = 'qa_commerce',
    [string]$Password = 'qa_commerce_local',
    [string]$Version = '17.9-1'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LocalDir = Join-Path $ProjectRoot '.local'
$PgHome = Join-Path $LocalDir 'pgsql'
$PgBin = Join-Path $PgHome 'bin'
$PgData = Join-Path $LocalDir 'pgdata'
$PgLog = Join-Path $LocalDir 'postgres.log'
$Databases = @('qa_commerce', 'qa_commerce_test')

function Install-Binaries {
    if (Test-Path (Join-Path $PgBin 'pg_ctl.exe')) { return }
    New-Item -ItemType Directory -Force $LocalDir | Out-Null
    $zip = Join-Path $LocalDir "postgresql-$Version-windows-x64-binaries.zip"
    if (-not (Test-Path $zip)) {
        $url = "https://get.enterprisedb.com/postgresql/postgresql-$Version-windows-x64-binaries.zip"
        Write-Host "Downloading PostgreSQL $Version binaries (~330 MB) from $url"
        & curl.exe --fail --location --silent --show-error --output $zip $url
        if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit $LASTEXITCODE)" }
    }
    Write-Host 'Extracting (skipping pgAdmin and debug symbols)...'
    & tar.exe -xf $zip -C $LocalDir --exclude 'pgsql/pgAdmin 4' --exclude 'pgsql/symbols' --exclude 'pgsql/doc'
    if ($LASTEXITCODE -ne 0) { throw "Extraction failed (tar exit $LASTEXITCODE)" }
    Remove-Item $zip
}

function Initialize-Cluster {
    if (Test-Path (Join-Path $PgData 'PG_VERSION')) { return }
    Write-Host "Initialising cluster in $PgData"
    $pwFile = Join-Path $LocalDir 'initdb-pw.tmp'
    Set-Content -Path $pwFile -Value $Password -NoNewline -Encoding ascii
    try {
        & (Join-Path $PgBin 'initdb.exe') -D $PgData -U $User --pwfile=$pwFile -A scram-sha-256 -E UTF8 --no-locale | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "initdb failed (exit $LASTEXITCODE)" }
    }
    finally {
        Remove-Item $pwFile -ErrorAction SilentlyContinue
    }
}

function Test-Running {
    & (Join-Path $PgBin 'pg_ctl.exe') -D $PgData status *> $null
    return ($LASTEXITCODE -eq 0)
}

function New-Databases {
    $env:PGPASSWORD = $Password
    try {
        foreach ($db in $Databases) {
            $exists = & (Join-Path $PgBin 'psql.exe') -h localhost -p $Port -U $User -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'"
            if ($exists -ne '1') {
                & (Join-Path $PgBin 'createdb.exe') -h localhost -p $Port -U $User $db
                if ($LASTEXITCODE -ne 0) { throw "createdb $db failed" }
                Write-Host "Created database $db"
            }
        }
    }
    finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

switch ($Command) {
    'start' {
        Install-Binaries
        Initialize-Cluster
        if (Test-Running) {
            Write-Host 'PostgreSQL is already running.'
        }
        else {
            # Start-Process keeps the long-lived postgres child from inheriting this shell's
            # stdout handle (which would make the calling pipeline wait forever).
            $proc = Start-Process -FilePath (Join-Path $PgBin 'pg_ctl.exe') -WindowStyle Hidden -PassThru `
                -ArgumentList @('-D', "`"$PgData`"", '-l', "`"$PgLog`"", '-o', "`"-p $Port`"", '-w', 'start')
            $proc.WaitForExit()
            if ($proc.ExitCode -ne 0) { throw "pg_ctl start failed; see $PgLog" }
        }
        New-Databases
        Write-Host "PostgreSQL ready on localhost:$Port (databases: $($Databases -join ', '))"
    }
    'stop' {
        if ((Test-Path $PgData) -and (Test-Running)) {
            & (Join-Path $PgBin 'pg_ctl.exe') -D $PgData -m fast -w stop | Out-Host
        }
        else {
            Write-Host 'PostgreSQL is not running.'
        }
    }
    'status' {
        if (-not (Test-Path (Join-Path $PgBin 'pg_ctl.exe'))) { Write-Host 'Not installed.'; break }
        if ((Test-Path $PgData) -and (Test-Running)) { Write-Host "Running on port $Port." }
        else { Write-Host 'Stopped.' }
    }
    'destroy' {
        if ((Test-Path $PgData) -and (Test-Running)) {
            & (Join-Path $PgBin 'pg_ctl.exe') -D $PgData -m fast -w stop | Out-Host
        }
        if (Test-Path $PgData) {
            Remove-Item -Recurse -Force $PgData
            Write-Host "Deleted $PgData"
        }
    }
}
