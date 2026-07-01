param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-RepositoryRoot {
    $current = (Get-Location).Path
    while ($true) {
        if ((Test-Path (Join-Path $current "manage.py")) -and (Test-Path (Join-Path $current ".git"))) {
            return $current
        }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) {
            throw "Could not locate repository root containing manage.py and .git."
        }
        $current = $parent
    }
}

function Redact-Line {
    param([string]$Line)
    $redacted = $Line
    $redacted = $redacted -replace "(?i)(DJANGO_SECRET_KEY|SECRET_KEY|DATABASE_URL|CACHE_URL|PASSWORD|TOKEN|DSN)\s*=\s*[^ \r\n]+", '$1=<redacted>'
    $redacted = $redacted -replace "(?i)(postgres|postgresql|redis|rediss)://[^ \r\n]+", '<redacted-url>'
    return $redacted
}

function Invoke-SafeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    Write-Host ""
    Write-Host ("$ " + $Executable + " " + ($Arguments -join " "))
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $Executable @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    foreach ($line in $output) {
        if ($line -is [System.Management.Automation.ErrorRecord]) {
            $text = [string]$line.Exception.Message
        } else {
            $text = [string]$line
        }
        if ($text -eq "System.Management.Automation.RemoteException") {
            continue
        }
        Write-Host (Redact-Line -Line $text)
    }
    if ($exitCode -ne 0) {
        throw "Command failed with exit code ${exitCode}: $Executable $($Arguments -join ' ')"
    }
}

$repoRoot = Get-RepositoryRoot
Set-Location $repoRoot

Write-Host "Local release validation for Dr. Khaled Badran Clinic"
Write-Host "Repository root: $repoRoot"
Invoke-SafeCommand git "branch" "--show-current"
Invoke-SafeCommand git "rev-parse" "HEAD"

Invoke-SafeCommand python "manage.py" "makemigrations" "--check" "--dry-run"
Invoke-SafeCommand python "manage.py" "migrate"
Invoke-SafeCommand python "manage.py" "check"
Invoke-SafeCommand python "manage.py" "deployment_smoke"
Invoke-SafeCommand python "manage.py" "project_status_report"
Invoke-SafeCommand python "manage.py" "test"

Write-Host ""
Write-Host "Local release validation completed."
