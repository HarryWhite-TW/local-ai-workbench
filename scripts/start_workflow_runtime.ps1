<#
.SYNOPSIS
Starts the bounded Workflow Panel and canonical Bridge Operator without visible
consoles.

.DESCRIPTION
This login helper is deliberately not a routing or lifecycle authority. It
verifies its trusted control checkout, starts a new read-only Workflow Panel,
then starts the canonical Bridge Operator launcher. Only the Operator launcher
may interpret repository_routing.json or choose an execution target.

The Panel receives a finite lifetime and stops itself. This helper never waits
for, supervises, or terminates Panel or Operator processes. Any listener on the
fixed Panel port fails closed before the Operator is started.
#>

[CmdletBinding()]
param(
    [string]$StateDir = "",
    [ValidateRange(1, 960)]
    [int]$MaxCycles = 960,
    [ValidateRange(0, 3600)]
    [double]$PollIntervalSeconds = 30,
    [ValidateRange(1, 86400)]
    [int]$TimeoutSeconds = 600,
    [ValidateRange(1, 65535)]
    [int]$PanelPort = 8765,
    [ValidateRange(60, 86400)]
    [int]$PanelLifetimeSeconds = 43200,
    [ValidateSet("", "free", "occupied")]
    [string]$TestOnlyPortState = "",
    [ValidateSet("", "owned", "competing")]
    [string]$TestOnlyPostLaunchState = "",
    [string]$TestOnlyPanelCommandLine = "",
    [string]$TestOnlyPanelLineagePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Protocol = "lawb.workflow_runtime_startup.v1"
$Repository = "HarryWhite-TW/local-ai-workbench"
$ControlRepoRoot = [System.IO.Path]::GetFullPath(
    (Join-Path -Path $PSScriptRoot -ChildPath "..")
).TrimEnd("\")
$PanelLauncher = [System.IO.Path]::GetFullPath(
    (Join-Path -Path $PSScriptRoot -ChildPath "start_workflow_panel.ps1")
)
$OperatorLauncher = [System.IO.Path]::GetFullPath(
    (Join-Path -Path $PSScriptRoot -ChildPath "start_bridge_operator_b3c.ps1")
)

if ($null -eq ("Lawb.WindowsCommandLine" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace Lawb {
    public static class WindowsCommandLine {
        [DllImport("shell32.dll", SetLastError = true)]
        private static extern IntPtr CommandLineToArgvW(
            [MarshalAs(UnmanagedType.LPWStr)] string commandLine,
            out int argumentCount
        );

        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr memory);

        public static string[] Parse(string commandLine) {
            int argumentCount;
            IntPtr argumentVector = CommandLineToArgvW(commandLine, out argumentCount);
            if (argumentVector == IntPtr.Zero) {
                throw new InvalidOperationException("command_line_parse_failed");
            }
            try {
                string[] arguments = new string[argumentCount];
                for (int index = 0; index < argumentCount; index++) {
                    IntPtr argument = Marshal.ReadIntPtr(
                        argumentVector,
                        index * IntPtr.Size
                    );
                    arguments[index] = Marshal.PtrToStringUni(argument);
                }
                return arguments;
            }
            finally {
                LocalFree(argumentVector);
            }
        }
    }
}
"@
}

function Write-Summary {
    param(
        [Parameter(Mandatory = $true)][string]$Result,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)][string]$PanelAction,
        [Parameter(Mandatory = $true)][string]$OperatorAction,
        [Parameter(Mandatory = $true)][bool]$ProcessesStarted,
        [AllowEmptyString()][string]$ResolvedStateDir = "",
        [AllowEmptyString()][string]$ObservationStore = ""
    )
    $summary = [ordered]@{
        protocol = $Protocol
        result = $Result
        reason = $Reason
        panel_action = $PanelAction
        operator_action = $OperatorAction
        processes_started = $ProcessesStarted
        repository = $Repository
        control_repo_root = $ControlRepoRoot
        state_dir = $ResolvedStateDir
        observation_store = $ObservationStore
        routing_authority = "start_bridge_operator_b3c.ps1"
        panel_host = "127.0.0.1"
        panel_port = $PanelPort
        panel_lifetime_seconds = $PanelLifetimeSeconds
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

function Test-SafeArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return -not (
        $Value.Contains('"') -or
        $Value.Contains("`r") -or
        $Value.Contains("`n")
    )
}

function ConvertTo-QuotedArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if (-not (Test-SafeArgument -Value $Value)) {
        throw "unsafe_process_argument"
    }
    return '"' + $Value + '"'
}

function Test-ExactWindowsPath {
    param(
        [AllowNull()][AllowEmptyString()][string]$Observed,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    try {
        if (-not [System.IO.Path]::IsPathRooted($Observed) -or
            -not [System.IO.Path]::IsPathRooted($Expected)) {
            return $false
        }
        $observedPath = [System.IO.Path]::GetFullPath($Observed).TrimEnd("\", "/")
        $expectedPath = [System.IO.Path]::GetFullPath($Expected).TrimEnd("\", "/")
        return [string]::Equals(
            $observedPath,
            $expectedPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
    catch {
        return $false
    }
}

function ConvertTo-NormalizedRepository {
    param([AllowNull()][string]$Origin)
    if ([string]::IsNullOrWhiteSpace($Origin)) { return "" }
    $value = $Origin.Trim()
    if ($value -match '^(?i)https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$') {
        return $Matches[1]
    }
    if ($value -match '^(?i)(?:ssh://)?git@github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$') {
        return $Matches[1]
    }
    return ""
}

function Invoke-ControlGitRead {
    param(
        [Parameter(Mandatory = $true)][string]$GitPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $output = @(& $GitPath -C $ControlRepoRoot @Arguments 2>$null)
    return [pscustomobject]@{
        exit_code = $LASTEXITCODE
        stdout = ($output -join [Environment]::NewLine)
    }
}

function Assert-ControlRuntimeIntegrity {
    $gitCommand = Get-Command git.exe -CommandType Application `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $gitCommand) {
        throw "control_repository_git_unavailable"
    }

    $rootResult = Invoke-ControlGitRead -GitPath $gitCommand.Source `
        -Arguments @("rev-parse", "--show-toplevel")
    if ($rootResult.exit_code -ne 0) {
        throw "control_repository_root_unreadable"
    }
    if (-not (Test-ExactWindowsPath `
        -Observed $rootResult.stdout.Trim() -Expected $ControlRepoRoot)) {
        throw "control_repository_root_mismatch"
    }

    $originResult = Invoke-ControlGitRead -GitPath $gitCommand.Source `
        -Arguments @("remote", "get-url", "origin")
    if ($originResult.exit_code -ne 0 -or
        -not [string]::Equals(
            (ConvertTo-NormalizedRepository -Origin $originResult.stdout),
            $Repository,
            [System.StringComparison]::Ordinal
        )) {
        throw "control_repository_origin_mismatch"
    }

    $headResult = Invoke-ControlGitRead -GitPath $gitCommand.Source `
        -Arguments @("rev-parse", "HEAD")
    if ($headResult.exit_code -ne 0 -or
        $headResult.stdout.Trim() -notmatch '^[0-9a-fA-F]{40}$') {
        throw "control_repository_head_unreadable"
    }

    $statusResult = Invoke-ControlGitRead -GitPath $gitCommand.Source `
        -Arguments @("status", "--porcelain=v1", "--untracked-files=all")
    if ($statusResult.exit_code -ne 0) {
        throw "control_repository_status_unreadable"
    }
    if (-not [string]::IsNullOrWhiteSpace($statusResult.stdout)) {
        throw "control_repository_worktree_dirty"
    }
}

function Get-UniqueOptionValue {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $values = @()
    for ($index = 0; $index -lt $Arguments.Count; $index++) {
        if ([string]::Equals(
            $Arguments[$index],
            $Name,
            [System.StringComparison]::Ordinal
        )) {
            if ($index + 1 -ge $Arguments.Count) { return $null }
            $values += $Arguments[$index + 1]
            $index++
        }
        elseif ($Arguments[$index].StartsWith(
            $Name + "=",
            [System.StringComparison]::Ordinal
        )) {
            $values += $Arguments[$index].Substring($Name.Length + 1)
        }
    }
    if ($values.Count -ne 1 -or [string]::IsNullOrWhiteSpace($values[0])) {
        return $null
    }
    return [string]$values[0]
}

function Test-CanonicalPanelCommandLine {
    param(
        [Parameter(Mandatory = $true)][string]$CommandLine,
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    try {
        $arguments = @([Lawb.WindowsCommandLine]::Parse($CommandLine))
    }
    catch {
        return $false
    }
    $moduleMatches = 0
    for ($index = 0; $index + 1 -lt $arguments.Count; $index++) {
        if ($arguments[$index] -eq "-m" -and
            $arguments[$index + 1] -eq "local_runner_bridge.workflow_panel") {
            $moduleMatches++
        }
    }
    $hostValue = Get-UniqueOptionValue -Arguments $arguments -Name "--host"
    $portValue = Get-UniqueOptionValue -Arguments $arguments -Name "--port"
    $stateValue = Get-UniqueOptionValue -Arguments $arguments -Name "--state-dir"
    $storeValue = Get-UniqueOptionValue -Arguments $arguments -Name "--store"
    $lifetimeValue = Get-UniqueOptionValue `
        -Arguments $arguments -Name "--lifetime-seconds"
    $observedPort = 0
    $observedLifetime = 0
    if ($moduleMatches -ne 1 -or $hostValue -ne "127.0.0.1" -or
        -not [int]::TryParse(
            $portValue,
            [System.Globalization.NumberStyles]::None,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$observedPort
        ) -or
        $observedPort -ne $PanelPort -or
        -not [int]::TryParse(
            $lifetimeValue,
            [System.Globalization.NumberStyles]::None,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$observedLifetime
        ) -or
        $observedLifetime -ne $PanelLifetimeSeconds -or
        -not (Test-ExactWindowsPath `
            -Observed $stateValue -Expected $ExpectedStateDir) -or
        -not (Test-ExactWindowsPath `
            -Observed $storeValue -Expected $ExpectedObservationStore)) {
        return $false
    }
    return $true
}

function Test-PanelLauncherLineage {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    $currentId = $ProcessId
    for ($depth = 0; $depth -lt 6 -and $currentId -gt 0; $depth++) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$currentId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $process) { return $false }
        if (-not [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) {
            try {
                foreach ($argument in @(
                    [Lawb.WindowsCommandLine]::Parse([string]$process.CommandLine)
                )) {
                    if (Test-ExactWindowsPath `
                        -Observed $argument -Expected $PanelLauncher) {
                        return $true
                    }
                }
            }
            catch {}
        }
        $currentId = [int]$process.ParentProcessId
    }
    return $false
}

function Test-ProcessDescendsFrom {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int]$AncestorProcessId
    )
    $currentId = $ProcessId
    for ($depth = 0; $depth -lt 6 -and $currentId -gt 0; $depth++) {
        if ($currentId -eq $AncestorProcessId) { return $true }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$currentId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $process) { return $false }
        $currentId = [int]$process.ParentProcessId
    }
    return $false
}

function Test-CanonicalPanelProcess {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" `
        -ErrorAction SilentlyContinue
    if ($null -eq $process -or
        [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) {
        return $false
    }
    return (
        (Test-CanonicalPanelCommandLine `
            -CommandLine ([string]$process.CommandLine) `
            -ExpectedStateDir $ExpectedStateDir `
            -ExpectedObservationStore $ExpectedObservationStore) -and
        (Test-PanelLauncherLineage -ProcessId $ProcessId)
    )
}

function Test-PanelPortFree {
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyPortState)) {
        return $TestOnlyPortState -eq "free"
    }
    if ($null -eq (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        throw "tcp_listener_inspection_unavailable"
    }
    try {
        $listeners = @(
            Get-NetTCPConnection -LocalPort $PanelPort -State Listen `
                -ErrorAction Stop
        )
    }
    catch {
        throw "tcp_listener_inspection_failed"
    }
    return $listeners.Count -eq 0
}

function Test-OwnedPanelListener {
    param(
        [Parameter(Mandatory = $true)][int]$LaunchProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyPostLaunchState)) {
        if ($TestOnlyPostLaunchState -ne "owned") { return $false }
        if (-not (Test-ExactWindowsPath `
                -Observed $TestOnlyPanelLineagePath `
                -Expected $PanelLauncher) -or
            -not (Test-CanonicalPanelCommandLine `
                -CommandLine $TestOnlyPanelCommandLine `
                -ExpectedStateDir $ExpectedStateDir `
                -ExpectedObservationStore $ExpectedObservationStore)) {
            return $false
        }
        return $true
    }
    $listeners = @(
        Get-NetTCPConnection -LocalPort $PanelPort -State Listen `
            -ErrorAction SilentlyContinue
    )
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne "127.0.0.1") {
        return $false
    }
    try {
        $response = Invoke-WebRequest `
            -Uri ("http://127.0.0.1:{0}/health" -f $PanelPort) `
            -Method Get -UseBasicParsing -TimeoutSec 2
        $health = $response.Content | ConvertFrom-Json
    }
    catch {
        return $false
    }
    $listenerProcessId = [int]$listeners[0].OwningProcess
    if ([int]$response.StatusCode -ne 200 -or
        $health.protocol -ne "lawb.workflow_panel.v1" -or
        $health.status -ne "ready" -or
        $health.mode -ne "read_only" -or
        $health.bind -ne "loopback" -or
        -not (Test-CanonicalPanelProcess `
            -ProcessId $listenerProcessId `
            -ExpectedStateDir $ExpectedStateDir `
            -ExpectedObservationStore $ExpectedObservationStore) -or
        -not (Test-ProcessDescendsFrom `
            -ProcessId $listenerProcessId `
            -AncestorProcessId $LaunchProcessId)) {
        return $false
    }
    return $true
}

function Start-HiddenPowerShell {
    param(
        [Parameter(Mandatory = $true)][string]$LauncherPath,
        [Parameter(Mandatory = $true)][string]$Arguments
    )
    $powerShellPath = Join-Path $env:SystemRoot `
        "System32\WindowsPowerShell\v1.0\powershell.exe"
    $argumentLine = (
        "-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden " +
        "-ExecutionPolicy Bypass -File " +
        (ConvertTo-QuotedArgument -Value $LauncherPath) + " " +
        $Arguments
    )
    return Start-Process -FilePath $powerShellPath `
        -ArgumentList $argumentLine -WindowStyle Hidden -PassThru
}

$testOverrideRequested = (
    -not [string]::IsNullOrWhiteSpace($TestOnlyPortState) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyPostLaunchState) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyPanelCommandLine) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyPanelLineagePath)
)
if ($testOverrideRequested -and
    [Environment]::GetEnvironmentVariable("LAWB_WORKFLOW_RUNTIME_TEST_ONLY") -ne "1") {
    Write-Summary -Result "blocked" -Reason "test_only_override_rejected" `
        -PanelAction "blocked" -OperatorAction "not_started" `
        -ProcessesStarted $false
    exit 2
}

$resolvedStateDir = ""
$storePath = ""
$panelAction = "not_started"
$operatorAction = "not_started"
$processesStarted = $false

try {
    if ([string]::IsNullOrWhiteSpace($StateDir)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
            throw "local_app_data_unavailable"
        }
        $StateDir = Join-Path $env:LOCALAPPDATA "LocalAIWorkbench\BridgeOperator"
    }
    $resolvedStateDir = [System.IO.Path]::GetFullPath($StateDir)
    $storePath = [System.IO.Path]::GetFullPath(
        (Join-Path $resolvedStateDir "observability\events.jsonl")
    )
    Assert-ControlRuntimeIntegrity
    if (-not (Test-SafeArgument -Value $resolvedStateDir) -or
        -not (Test-SafeArgument -Value $storePath) -or
        -not (Test-Path -LiteralPath $PanelLauncher -PathType Leaf) -or
        -not (Test-Path -LiteralPath $OperatorLauncher -PathType Leaf)) {
        throw "canonical_control_runtime_invalid"
    }

    if (-not (Test-PanelPortFree)) {
        $panelAction = "blocked"
        Write-Summary -Result "blocked" -Reason "panel_port_occupied" `
            -PanelAction $panelAction -OperatorAction $operatorAction `
            -ProcessesStarted $false -ResolvedStateDir $resolvedStateDir `
            -ObservationStore $storePath
        exit 2
    }

    if ($testOverrideRequested -and
        [string]::IsNullOrWhiteSpace($TestOnlyPostLaunchState)) {
        Write-Summary -Result "ready" -Reason "test_plan_only" `
            -PanelAction "would_start" -OperatorAction "would_start" `
            -ProcessesStarted $false -ResolvedStateDir $resolvedStateDir `
            -ObservationStore $storePath
        exit 0
    }

    $panelAction = if ($testOverrideRequested) { "would_start" } else { "starting" }
    $panelArguments = (
        "-StateDir " + (ConvertTo-QuotedArgument -Value $resolvedStateDir) +
        " -ObservationStore " + (ConvertTo-QuotedArgument -Value $storePath) +
        " -Port " + $PanelPort +
        " -LifetimeSeconds " + $PanelLifetimeSeconds
    )
    if ($testOverrideRequested) {
        $panelLaunchProcess = [pscustomobject]@{ Id = 41001 }
        $panelAction = "would_start_unverified"
    }
    else {
        $panelLaunchProcess = Start-HiddenPowerShell `
            -LauncherPath $PanelLauncher -Arguments $panelArguments
        $processesStarted = $true
        $panelAction = "started_unverified"
    }
    $verified = $false
    $verificationAttempts = if ($testOverrideRequested) { 1 } else { 50 }
    for ($attempt = 0; $attempt -lt $verificationAttempts; $attempt++) {
        if (-not $testOverrideRequested) {
            Start-Sleep -Milliseconds 200
        }
        if (Test-OwnedPanelListener `
            -LaunchProcessId ([int]$panelLaunchProcess.Id) `
            -ExpectedStateDir $resolvedStateDir `
            -ExpectedObservationStore $storePath) {
            $verified = $true
            break
        }
    }
    if (-not $verified) {
        throw "workflow_panel_start_not_verified"
    }
    if ($testOverrideRequested) {
        Write-Summary -Result "ready" -Reason "test_plan_only" `
            -PanelAction "would_start_verified" -OperatorAction "would_start" `
            -ProcessesStarted $false -ResolvedStateDir $resolvedStateDir `
            -ObservationStore $storePath
        exit 0
    }
    $panelAction = "started"

    $operatorArguments = (
        "-StartForeground -PublishStatus" +
        " -MaxCycles " + $MaxCycles +
        " -PollIntervalSeconds " + $PollIntervalSeconds +
        " -TimeoutSeconds " + $TimeoutSeconds +
        " -StateDir " + (ConvertTo-QuotedArgument -Value $resolvedStateDir)
    )
    try {
        [void](Start-HiddenPowerShell `
            -LauncherPath $OperatorLauncher -Arguments $operatorArguments)
    }
    catch {
        $operatorAction = "launch_failed"
        throw "operator_launch_failed"
    }
    $processesStarted = $true
    $operatorAction = "started"
    Write-Summary -Result "started" -Reason "launches_dispatched" `
        -PanelAction $panelAction -OperatorAction $operatorAction `
        -ProcessesStarted $processesStarted -ResolvedStateDir $resolvedStateDir `
        -ObservationStore $storePath
    exit 0
}
catch {
    Write-Summary -Result "blocked" -Reason $_.Exception.Message `
        -PanelAction $panelAction -OperatorAction $operatorAction `
        -ProcessesStarted $processesStarted -ResolvedStateDir $resolvedStateDir `
        -ObservationStore $storePath
    exit 2
}
