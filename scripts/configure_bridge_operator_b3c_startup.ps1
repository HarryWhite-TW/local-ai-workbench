<#
.SYNOPSIS
Manages the current user's visible Bridge Operator B3-C Startup-folder entry.

.DESCRIPTION
Exactly one of -Enable, -Status, or -Disable is required. The adapter owns one
deterministic file and refuses to replace or remove content it does not exactly
recognize. It never starts the Bridge Operator itself.
#>

[CmdletBinding()]
param(
    [switch]$Enable,
    [switch]$Status,
    [switch]$Disable,
    [string]$TestOnlyStartupDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Protocol = "lawb.bridge_operator_b3c_startup.v1"
$ManagedFileName = "LocalAIWorkbench-BridgeOperator-B3C.cmd"
$OwnershipMarker = "LAWBRIDGE-B3C-STARTUP-MANAGED protocol=lawb.bridge_operator_b3c_startup.v1"
$MaxCycles = 960
$PollIntervalSeconds = 30
$TimeoutSeconds = 600

function Write-Summary {
    param(
        [Parameter(Mandatory = $true)][string]$Operation,
        [Parameter(Mandatory = $true)][string]$State,
        [Parameter(Mandatory = $true)][bool]$Changed,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ManagedPath
    )
    $summary = [ordered]@{
        protocol = $Protocol
        operation = $Operation
        state = $State
        changed = $Changed
        reason = $Reason
        managed_file = $ManagedFileName
        managed_path = $ManagedPath
        max_cycles = $MaxCycles
        poll_interval_seconds = $PollIntervalSeconds
        timeout_seconds = $TimeoutSeconds
    }
    $json = $summary | ConvertTo-Json -Compress
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes(
        $json + [Environment]::NewLine
    )
    [Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
}

function ConvertTo-CmdQuotedLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains('"') -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "unsafe_windows_path"
    }
    return '"' + $Value.Replace("%", "%%") + '"'
}

function Get-ManagedBytes {
    param([Parameter(Mandatory = $true)][string]$LauncherPath)
    $powerShellPath = Join-Path $env:SystemRoot `
        "System32\WindowsPowerShell\v1.0\powershell.exe"
    $launcher = ConvertTo-CmdQuotedLiteral -Value $LauncherPath
    $powershell = ConvertTo-CmdQuotedLiteral -Value $powerShellPath
    $lines = @(
        "@echo off",
        "REM $OwnershipMarker",
        "REM managed-file-name=$ManagedFileName",
        "start `"Local AI Workbench Bridge Operator`" $powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $launcher -StartForeground -PublishStatus -MaxCycles $MaxCycles -PollIntervalSeconds $PollIntervalSeconds -TimeoutSeconds $TimeoutSeconds -StateDir `"%LOCALAPPDATA%\LocalAIWorkbench\BridgeOperator`"",
        ""
    )
    return (New-Object System.Text.UTF8Encoding($false)).GetBytes(
        ($lines -join "`r`n")
    )
}

function Test-ExactBytes {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Left,
        [Parameter(Mandatory = $true)][byte[]]$Right
    )
    if ($Left.Length -ne $Right.Length) { return $false }
    for ($index = 0; $index -lt $Left.Length; $index++) {
        if ($Left[$index] -ne $Right[$index]) { return $false }
    }
    return $true
}

$operationCount = [int][bool]$Enable + [int][bool]$Status + [int][bool]$Disable
$operation = if ($Enable) { "enable" } elseif ($Status) { "status" } `
    elseif ($Disable) { "disable" } else { "none" }
if ($operationCount -ne 1) {
    Write-Summary -Operation $operation -State "blocked" -Changed $false `
        -Reason "exactly_one_operation_required" -ManagedPath ""
    exit 2
}

$startupDirectory = ""
try {
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyStartupDirectory)) {
        $testGuard = [Environment]::GetEnvironmentVariable(
            "LAWB_STARTUP_ADAPTER_TEST_ONLY"
        )
        if ($testGuard -ne "1") {
            throw "test_only_startup_override_rejected"
        }
        $startupDirectory = [System.IO.Path]::GetFullPath(
            $TestOnlyStartupDirectory
        )
    }
    else {
        $startupDirectory = [Environment]::GetFolderPath(
            [Environment+SpecialFolder]::Startup
        )
        if ([string]::IsNullOrWhiteSpace($startupDirectory)) {
            throw "current_user_startup_folder_unavailable"
        }
        $startupDirectory = [System.IO.Path]::GetFullPath($startupDirectory)
    }
}
catch {
    Write-Summary -Operation $operation -State "blocked" -Changed $false `
        -Reason $_.Exception.Message -ManagedPath ""
    exit 2
}

$managedPath = Join-Path $startupDirectory $ManagedFileName
$repoRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
).TrimEnd("\")
$launcherPath = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "start_bridge_operator_b3c.ps1")
)
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".git")) -or
    -not (Test-Path -LiteralPath $launcherPath -PathType Leaf) -or
    -not [string]::Equals(
        [System.IO.Path]::GetFullPath($PSScriptRoot),
        [System.IO.Path]::GetFullPath((Join-Path $repoRoot "scripts")),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    Write-Summary -Operation $operation -State "blocked" -Changed $false `
        -Reason "repository_or_canonical_launcher_invalid" -ManagedPath $managedPath
    exit 2
}

try {
    $expectedBytes = Get-ManagedBytes -LauncherPath $launcherPath
    if (-not (Test-Path -LiteralPath $managedPath)) {
        $observedState = "absent"
    }
    elseif (-not (Test-Path -LiteralPath $managedPath -PathType Leaf)) {
        $observedState = "unrecognized"
    }
    else {
        $actualBytes = [System.IO.File]::ReadAllBytes($managedPath)
        if (Test-ExactBytes -Left $actualBytes -Right $expectedBytes) {
            $observedState = "exact_enabled"
        }
        else {
            $actualText = (New-Object System.Text.UTF8Encoding($false, $true)).GetString(
                $actualBytes
            )
            $observedState = if ($actualText.Contains($OwnershipMarker)) {
                "drifted_invalid"
            } else {
                "unrecognized"
            }
        }
    }

    if ($Status) {
        Write-Summary -Operation $operation -State $observedState `
            -Changed $false -Reason "none" -ManagedPath $managedPath
        exit 0
    }

    if ($Enable) {
        if ($observedState -eq "exact_enabled") {
            Write-Summary -Operation $operation -State $observedState `
                -Changed $false -Reason "already_enabled" -ManagedPath $managedPath
            exit 0
        }
        if ($observedState -ne "absent") {
            Write-Summary -Operation $operation -State $observedState `
                -Changed $false -Reason "existing_file_not_exact" `
                -ManagedPath $managedPath
            exit 2
        }
        if (-not (Test-Path -LiteralPath $startupDirectory -PathType Container)) {
            Write-Summary -Operation $operation -State "blocked" -Changed $false `
                -Reason "startup_folder_missing" -ManagedPath $managedPath
            exit 2
        }
        [System.IO.File]::WriteAllBytes($managedPath, $expectedBytes)
        $readback = [System.IO.File]::ReadAllBytes($managedPath)
        if (-not (Test-ExactBytes -Left $readback -Right $expectedBytes)) {
            Write-Summary -Operation $operation -State "blocked" -Changed $true `
                -Reason "exact_readback_failed" -ManagedPath $managedPath
            exit 2
        }
        Write-Summary -Operation $operation -State "exact_enabled" -Changed $true `
            -Reason "enabled" -ManagedPath $managedPath
        exit 0
    }

    if ($observedState -eq "absent") {
        Write-Summary -Operation $operation -State "absent" -Changed $false `
            -Reason "already_absent" -ManagedPath $managedPath
        exit 0
    }
    if ($observedState -ne "exact_enabled") {
        Write-Summary -Operation $operation -State $observedState `
            -Changed $false -Reason "existing_file_not_exact" `
            -ManagedPath $managedPath
        exit 2
    }
    Remove-Item -LiteralPath $managedPath
    if (Test-Path -LiteralPath $managedPath) {
        Write-Summary -Operation $operation -State "blocked" -Changed $false `
            -Reason "disable_readback_failed" -ManagedPath $managedPath
        exit 2
    }
    Write-Summary -Operation $operation -State "absent" -Changed $true `
        -Reason "disabled" -ManagedPath $managedPath
    exit 0
}
catch {
    Write-Summary -Operation $operation -State "blocked" -Changed $false `
        -Reason "managed_file_io_failed" -ManagedPath $managedPath
    exit 2
}
