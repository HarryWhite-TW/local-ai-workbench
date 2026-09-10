<#
.SYNOPSIS
Starts the bounded Workflow Panel and canonical Bridge Operator without visible
consoles.

.DESCRIPTION
This login helper is deliberately not a routing or lifecycle authority. It
starts or reuses the read-only Workflow Panel from this trusted control
checkout, then starts the canonical Bridge Operator launcher. Only the Operator
launcher may interpret repository_routing.json or choose an execution target.

The Panel receives a finite lifetime and stops itself. This helper never waits
for, supervises, or terminates Panel or Operator processes. An unknown listener
on the fixed Panel port fails closed before the Operator is started.
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
    [ValidateSet("", "free", "workflow_panel", "unknown")]
    [string]$TestOnlyPortState = "",
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
        $observedLifetime -lt 60 -or $observedLifetime -gt 86400 -or
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

function Get-PanelPortState {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyPortState)) {
        if ($TestOnlyPortState -ne "workflow_panel") {
            return $TestOnlyPortState
        }
        if (-not (Test-ExactWindowsPath `
                -Observed $TestOnlyPanelLineagePath `
                -Expected $PanelLauncher) -or
            -not (Test-CanonicalPanelCommandLine `
                -CommandLine $TestOnlyPanelCommandLine `
                -ExpectedStateDir $ExpectedStateDir `
                -ExpectedObservationStore $ExpectedObservationStore)) {
            return "unknown"
        }
        return "workflow_panel"
    }
    if ($null -eq (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        throw "tcp_listener_inspection_unavailable"
    }
    $listeners = @(
        Get-NetTCPConnection -LocalPort $PanelPort -State Listen `
            -ErrorAction SilentlyContinue
    )
    if ($listeners.Count -eq 0) { return "free" }
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne "127.0.0.1") {
        return "unknown"
    }
    try {
        $response = Invoke-WebRequest `
            -Uri ("http://127.0.0.1:{0}/health" -f $PanelPort) `
            -Method Get -UseBasicParsing -TimeoutSec 2
        $health = $response.Content | ConvertFrom-Json
    }
    catch {
        return "unknown"
    }
    if ([int]$response.StatusCode -ne 200 -or
        $health.protocol -ne "lawb.workflow_panel.v1" -or
        $health.status -ne "ready" -or
        $health.mode -ne "read_only" -or
        $health.bind -ne "loopback" -or
        -not (Test-CanonicalPanelProcess `
            -ProcessId ([int]$listeners[0].OwningProcess) `
            -ExpectedStateDir $ExpectedStateDir `
            -ExpectedObservationStore $ExpectedObservationStore)) {
        return "unknown"
    }
    return "workflow_panel"
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
    if (-not (Test-SafeArgument -Value $resolvedStateDir) -or
        -not (Test-SafeArgument -Value $storePath) -or
        -not (Test-Path -LiteralPath (Join-Path $ControlRepoRoot ".git")) -or
        -not (Test-Path -LiteralPath $PanelLauncher -PathType Leaf) -or
        -not (Test-Path -LiteralPath $OperatorLauncher -PathType Leaf)) {
        throw "canonical_control_runtime_invalid"
    }

    $portState = Get-PanelPortState `
        -ExpectedStateDir $resolvedStateDir `
        -ExpectedObservationStore $storePath
    if ($portState -eq "unknown") {
        $panelAction = "blocked"
        Write-Summary -Result "blocked" -Reason "panel_port_occupied_unknown" `
            -PanelAction $panelAction -OperatorAction $operatorAction `
            -ProcessesStarted $false -ResolvedStateDir $resolvedStateDir `
            -ObservationStore $storePath
        exit 2
    }

    if ($testOverrideRequested) {
        $panelPlan = if ($portState -eq "free") { "would_start" } else { "would_reuse" }
        Write-Summary -Result "ready" -Reason "test_plan_only" `
            -PanelAction $panelPlan -OperatorAction "would_start" `
            -ProcessesStarted $false -ResolvedStateDir $resolvedStateDir `
            -ObservationStore $storePath
        exit 0
    }

    if ($portState -eq "free") {
        $panelAction = "starting"
        $panelArguments = (
            "-StateDir " + (ConvertTo-QuotedArgument -Value $resolvedStateDir) +
            " -ObservationStore " + (ConvertTo-QuotedArgument -Value $storePath) +
            " -Port " + $PanelPort +
            " -LifetimeSeconds " + $PanelLifetimeSeconds
        )
        [void](Start-HiddenPowerShell `
            -LauncherPath $PanelLauncher -Arguments $panelArguments)
        $processesStarted = $true
        $panelAction = "started_unverified"
        $verified = $false
        for ($attempt = 0; $attempt -lt 50; $attempt++) {
            Start-Sleep -Milliseconds 200
            if ((Get-PanelPortState `
                -ExpectedStateDir $resolvedStateDir `
                -ExpectedObservationStore $storePath) -eq "workflow_panel") {
                $verified = $true
                break
            }
        }
        if (-not $verified) {
            throw "workflow_panel_start_not_verified"
        }
        $panelAction = "started"
    }
    else {
        $panelAction = "reused"
    }

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
