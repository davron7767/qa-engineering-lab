<#
.SYNOPSIS
    Poll the readiness endpoint until it returns HTTP 200 or the timeout expires.
.EXAMPLE
    .\scripts\wait-for-health.ps1
    .\scripts\wait-for-health.ps1 -Url http://localhost:8000/api/v1/health -TimeoutSeconds 90
#>
param(
    [string]$Url = 'http://localhost:8000/api/v1/health',
    [int]$TimeoutSeconds = 90
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $code = & curl.exe -s -o NUL -m 5 -w '%{http_code}' $Url
    if ($code -eq '200') {
        Write-Host "Ready: $Url"
        exit 0
    }
    Start-Sleep -Milliseconds 1000
}
Write-Error "Not ready after $TimeoutSeconds s: $Url (last status: $code)"
exit 1
