param(
    [switch]$Strict,
    [switch]$Json
)

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

function Test-StagingEnvironmentContract {
    $required = @(
        "DJANGO_SETTINGS_MODULE",
        "DJANGO_SECRET_KEY",
        "DJANGO_DEBUG",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DATABASE_URL",
        "CACHE_URL",
        "DJANGO_CACHE_KEY_PREFIX"
    )

    $missing = @()
    Write-Host ""
    Write-Host "Staging environment contract presence check; values are not printed."
    foreach ($name in $required) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ([string]::IsNullOrWhiteSpace($value)) {
            $missing += $name
            Write-Host "${name}: missing"
        } else {
            Write-Host "${name}: present"
        }
    }

    $debugValue = [Environment]::GetEnvironmentVariable("DJANGO_DEBUG")
    if ($debugValue -and $debugValue.ToLowerInvariant() -ne "false") {
        $missing += "DJANGO_DEBUG=false"
        Write-Host "DJANGO_DEBUG: not false"
    }

    if ($Strict -and $missing.Count -gt 0) {
        throw "Strict staging validation failed environment contract presence checks: $($missing -join ', ')"
    }
}

$repoRoot = Get-RepositoryRoot
Set-Location $repoRoot

Write-Host "Restricted staging environment validation for Dr. Khaled Badran Clinic"
Write-Host "Repository root: $repoRoot"
Write-Host "Strict mode: $($Strict.IsPresent)"
Write-Host "JSON command output mode: $($Json.IsPresent)"

Invoke-SafeCommand git "branch" "--show-current"
Invoke-SafeCommand git "rev-parse" "HEAD"
Test-StagingEnvironmentContract

Invoke-SafeCommand python "manage.py" "makemigrations" "--check" "--dry-run"
Invoke-SafeCommand python "manage.py" "migrate" "--check"
Invoke-SafeCommand python "manage.py" "check"
Invoke-SafeCommand python "manage.py" "check" "--deploy"

$smokeArgs = @("manage.py", "deployment_smoke")
if ($Strict) { $smokeArgs += "--strict" }
if ($Json) { $smokeArgs += "--json" }
Invoke-SafeCommand python @smokeArgs

$reportArgs = @("manage.py", "project_status_report")
if ($Json) { $reportArgs += "--json" }
Invoke-SafeCommand python @reportArgs

Invoke-SafeCommand python "manage.py" "test"

Write-Host ""
Write-Host "Restricted staging environment validation completed."
