<#
.SYNOPSIS
Starts the managed Workflow runtime without persistent visible consoles.

.DESCRIPTION
Uses the existing local routing file to locate the canonical stable runtime,
starts or reuses its loopback-only Workflow Panel, then starts the existing
Bridge Operator launcher. The existing Operator lock and lifecycle contracts
remain the sole authority for whether one effective Operator may run.

This helper does not create persistence, change routing, modify lifecycle
files, kill processes, select another port, or invoke GitHub directly.
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
    [ValidateSet("", "free", "workflow_panel", "unknown")]
    [string]$TestOnlyPortState = "",
    [string]$TestOnlyTargetRepoRoot = "",
    [string]$TestOnlyControlRepoRoot = "",
    [string]$TestOnlyPanelCommandLine = "",
    [string]$TestOnlyPanelLineagePath = "",
    [ValidateSet(
        "",
        "panel_verification_failed",
        "operator_launch_failed_owned",
        "operator_launch_failed_reused",
        "owned_lifecycle_complete"
    )]
    [string]$TestOnlyScenario = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Protocol = "lawb.workflow_runtime_startup.v1"
$Repository = "HarryWhite-TW/local-ai-workbench"
$RoutingProtocolV1 = "lawb.bridge_operator_local_routing.v1"
$RoutingProtocolV2 = "lawb.bridge_operator_local_routing.v2"
$ControlRepoRoot = if ([string]::IsNullOrWhiteSpace($TestOnlyControlRepoRoot)) {
    [System.IO.Path]::GetFullPath(
        (Join-Path -Path $PSScriptRoot -ChildPath "..")
    ).TrimEnd("\")
}
else {
    [System.IO.Path]::GetFullPath($TestOnlyControlRepoRoot).TrimEnd("\")
}
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
        [AllowEmptyString()][string]$TargetRepoRoot = "",
        [ValidateSet("none", "owned", "reused")]
        [string]$PanelOwnership = "none",
        [int]$PanelProcessId = 0,
        [ValidateSet("not_needed", "scheduled", "stopped", "residual_unverified", "not_owned")]
        [string]$PanelCleanup = "not_needed",
        [int]$OperatorProcessId = 0
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
        target_repo_root = $TargetRepoRoot
        panel_ownership = $PanelOwnership
        panel_process_id = $PanelProcessId
        panel_cleanup = $PanelCleanup
        operator_process_id = $OperatorProcessId
        panel_host = "127.0.0.1"
        panel_port = $PanelPort
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

function Get-ExactPropertyNames {
    param([Parameter(Mandatory = $true)][object]$Value)
    return @($Value.PSObject.Properties.Name | Sort-Object)
}

function Test-FullyQualifiedLocalWindowsPath {
    param([AllowNull()][object]$Path)
    if ($Path -isnot [string] -or [string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }
    return [System.Text.RegularExpressions.Regex]::IsMatch(
        $Path,
        "\A[A-Za-z]:[\\/]"
    )
}

function Resolve-TargetRuntime {
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyTargetRepoRoot)) {
        return [System.IO.Path]::GetFullPath($TestOnlyTargetRepoRoot).TrimEnd("\")
    }

    $routingPath = Join-Path -Path $ResolvedStateDir -ChildPath "repository_routing.json"
    if (-not (Test-Path -LiteralPath $routingPath)) {
        return Test-TargetRuntime `
            -TargetRoot $ControlRepoRoot -ExpectedBranch "" -ExpectedHead ""
    }
    if (-not (Test-Path -LiteralPath $routingPath -PathType Leaf)) {
        throw "repository_routing_invalid"
    }
    try {
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $routingText = $strictUtf8.GetString(
            [System.IO.File]::ReadAllBytes($routingPath)
        )
        $routing = $routingText | ConvertFrom-Json
    }
    catch {
        throw "repository_routing_invalid"
    }
    $rootNames = @(Get-ExactPropertyNames -Value $routing)
    if (-not [string]::Equals(
        [string]$routing.repository,
        $Repository,
        [System.StringComparison]::Ordinal
    )) {
        throw "repository_routing_repository_mismatch"
    }
    if ([string]::Equals(
        [string]$routing.protocol,
        $RoutingProtocolV1,
        [System.StringComparison]::Ordinal
    )) {
        if (($rootNames -join ",") -ne "protocol,repository,target_repo_root" -or
            [string]::IsNullOrWhiteSpace([string]$routing.target_repo_root)) {
            throw "repository_routing_invalid"
        }
        return Test-TargetRuntime `
            -TargetRoot ([string]$routing.target_repo_root) `
            -ExpectedBranch "" -ExpectedHead ""
    }
    if (-not [string]::Equals(
            [string]$routing.protocol,
            $RoutingProtocolV2,
            [System.StringComparison]::Ordinal
        ) -or
        ($rootNames -join ",") -ne "protocol,repository,selected_target") {
        throw "repository_routing_invalid"
    }
    $selected = $routing.selected_target
    if ($null -eq $selected) { throw "repository_routing_no_safe_target" }
    $selectedNames = @(Get-ExactPropertyNames -Value $selected)
    if (($selectedNames -join ",") -ne "branch,head,selection_id,target_repo_root" -or
        [string]$selected.selection_id -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' -or
        [string]$selected.branch -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$' -or
        [string]$selected.head -notmatch '^[0-9a-fA-F]{40}$' -or
        [string]::IsNullOrWhiteSpace([string]$selected.target_repo_root)) {
        throw "repository_routing_invalid"
    }
    return Test-TargetRuntime `
        -TargetRoot ([string]$selected.target_repo_root) `
        -ExpectedBranch ([string]$selected.branch) `
        -ExpectedHead ([string]$selected.head).ToLowerInvariant()
}

function Test-TargetRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$TargetRoot,
        [AllowEmptyString()][string]$ExpectedBranch,
        [AllowEmptyString()][string]$ExpectedHead
    )
    try {
        if (-not (Test-FullyQualifiedLocalWindowsPath -Path $TargetRoot)) {
            throw "target_runtime_path_invalid"
        }
        $targetRoot = [System.IO.Path]::GetFullPath($TargetRoot).TrimEnd("\")
    }
    catch {
        throw "target_runtime_path_invalid"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $targetRoot ".git"))) {
        throw "target_runtime_not_git_repository"
    }
    $head = (& git -C $targetRoot rev-parse HEAD 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-fA-F]{40}$') {
        throw "target_runtime_head_unavailable"
    }
    $branch = (& git -C $targetRoot branch --show-current 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "target_runtime_branch_unavailable" }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedBranch) -and
        $branch -cne $ExpectedBranch) {
        throw "target_runtime_branch_mismatch"
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedHead) -and
        $head -cne $ExpectedHead) {
        throw "target_runtime_head_mismatch"
    }
    $status = @(& git -C $targetRoot status --porcelain=v1 --untracked-files=all 2>$null)
    if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) {
        throw "target_runtime_not_clean"
    }
    return $targetRoot
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

function Test-ExactWindowsPath {
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Observed,
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

function Test-PathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Observed,
        [Parameter(Mandatory = $true)][string]$Root
    )
    try {
        if (-not [System.IO.Path]::IsPathRooted($Observed)) { return $false }
        $observedPath = [System.IO.Path]::GetFullPath($Observed).TrimEnd("\", "/")
        $rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd("\", "/")
        return (
            [string]::Equals(
                $observedPath,
                $rootPath,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -or
            $observedPath.StartsWith(
                $rootPath + [System.IO.Path]::DirectorySeparatorChar,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        )
    }
    catch {
        return $false
    }
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
    $stateDirValue = Get-UniqueOptionValue -Arguments $arguments -Name "--state-dir"
    $storeValue = Get-UniqueOptionValue -Arguments $arguments -Name "--store"
    $observedPort = 0
    if ($moduleMatches -ne 1 -or $hostValue -ne "127.0.0.1" -or
        -not [int]::TryParse(
            $portValue,
            [System.Globalization.NumberStyles]::None,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$observedPort
        ) -or
        $observedPort -ne $PanelPort -or
        -not (Test-ExactWindowsPath `
            -Observed $stateDirValue -Expected $ExpectedStateDir) -or
        -not (Test-ExactWindowsPath `
            -Observed $storeValue -Expected $ExpectedObservationStore)) {
        return $false
    }
    return $true
}

function Test-CanonicalPanelProcess {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$TargetRepoRoot,
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" `
        -ErrorAction SilentlyContinue
    if ($null -eq $process -or [string]::IsNullOrWhiteSpace($process.CommandLine)) {
        return $false
    }
    if (-not (Test-CanonicalPanelCommandLine `
        -CommandLine ([string]$process.CommandLine) `
        -ExpectedStateDir $ExpectedStateDir `
        -ExpectedObservationStore $ExpectedObservationStore)) {
        return $false
    }

    $targetObserved = $false
    $current = $process
    for ($depth = 0; $depth -lt 5 -and $null -ne $current; $depth++) {
        $candidatePaths = @([string]$current.ExecutablePath)
        if (-not [string]::IsNullOrWhiteSpace([string]$current.CommandLine)) {
            try {
                $candidatePaths += @(
                    [Lawb.WindowsCommandLine]::Parse([string]$current.CommandLine)
                )
            }
            catch {}
        }
        if (@($candidatePaths | Where-Object {
            Test-PathWithinRoot -Observed $_ -Root $TargetRepoRoot
        }).Count -gt 0) {
            $targetObserved = $true
            break
        }
        if ([int]$current.ParentProcessId -le 0) { break }
        $current = Get-CimInstance Win32_Process `
            -Filter "ProcessId=$([int]$current.ParentProcessId)" `
            -ErrorAction SilentlyContinue
    }
    return $targetObserved
}

function Get-PanelPortState {
    param(
        [Parameter(Mandatory = $true)][string]$TargetRepoRoot,
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyPortState)) {
        if ($TestOnlyPortState -ne "workflow_panel") {
            return $TestOnlyPortState
        }
        if ([string]::IsNullOrWhiteSpace($TestOnlyPanelLineagePath) -or
            -not (Test-PathWithinRoot `
                -Observed $TestOnlyPanelLineagePath -Root $TargetRepoRoot) -or
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
        $health.bind -ne "loopback") {
        return "unknown"
    }
    if (-not (Test-CanonicalPanelProcess `
        -ProcessId ([int]$listeners[0].OwningProcess) `
        -TargetRepoRoot $TargetRepoRoot `
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

function Get-LoopbackPanelListenerProcessId {
    $listeners = @(
        Get-NetTCPConnection -LocalPort $PanelPort -State Listen `
            -ErrorAction SilentlyContinue
    )
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne "127.0.0.1") {
        return 0
    }
    return [int]$listeners[0].OwningProcess
}

function Test-ProcessDescendsFrom {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int]$ExpectedAncestorProcessId
    )
    $currentId = $ProcessId
    for ($depth = 0; $depth -lt 8 -and $currentId -gt 0; $depth++) {
        if ($currentId -eq $ExpectedAncestorProcessId) { return $true }
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$currentId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $current) { return $false }
        $currentId = [int]$current.ParentProcessId
    }
    return $false
}

function Stop-OwnedPanelRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$LauncherProcess,
        [Parameter(Mandatory = $true)][string]$TargetRepoRoot,
        [Parameter(Mandatory = $true)][string]$ExpectedStateDir,
        [Parameter(Mandatory = $true)][string]$ExpectedObservationStore
    )
    try {
        $listenerProcessId = Get-LoopbackPanelListenerProcessId
        if ($listenerProcessId -gt 0 -and
            (Test-ProcessDescendsFrom `
                -ProcessId $listenerProcessId `
                -ExpectedAncestorProcessId $LauncherProcess.Id) -and
            (Test-CanonicalPanelProcess `
                -ProcessId $listenerProcessId `
                -TargetRepoRoot $TargetRepoRoot `
                -ExpectedStateDir $ExpectedStateDir `
                -ExpectedObservationStore $ExpectedObservationStore)) {
            [System.Diagnostics.Process]::GetProcessById($listenerProcessId).Kill()
        }
        if (-not $LauncherProcess.HasExited) {
            $LauncherProcess.Kill()
        }
        [void]$LauncherProcess.WaitForExit(2000)
        Start-Sleep -Milliseconds 100
        $remainingListeners = @(
            Get-NetTCPConnection -LocalPort $PanelPort -State Listen `
                -ErrorAction SilentlyContinue
        )
        if ($remainingListeners.Count -eq 0) { return "stopped" }
    }
    catch {}
    return "residual_unverified"
}

$testOverrideRequested = (
    -not [string]::IsNullOrWhiteSpace($TestOnlyPortState) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyTargetRepoRoot) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyControlRepoRoot) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyPanelCommandLine) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyPanelLineagePath) -or
    -not [string]::IsNullOrWhiteSpace($TestOnlyScenario)
)
if ($testOverrideRequested -and
    [Environment]::GetEnvironmentVariable("LAWB_WORKFLOW_RUNTIME_TEST_ONLY") -ne "1") {
    Write-Summary -Result "blocked" -Reason "test_only_override_rejected" `
        -PanelAction "blocked" -OperatorAction "blocked" `
        -ProcessesStarted $false
    exit 2
}

$targetRoot = ""
$panelAction = "not_started"
$operatorAction = "not_started"
$processesStarted = $false
$panelOwnership = "none"
$panelProcessId = 0
$operatorProcessId = 0
$panelCleanup = "not_needed"
$panelLauncherProcess = $null

try {
    if ([string]::IsNullOrWhiteSpace($StateDir)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
            throw "local_app_data_unavailable"
        }
        $StateDir = Join-Path $env:LOCALAPPDATA "LocalAIWorkbench\BridgeOperator"
    }
    $ResolvedStateDir = [System.IO.Path]::GetFullPath($StateDir)
    if (-not (Test-SafeArgument -Value $ResolvedStateDir) -or
        -not (Test-Path -LiteralPath $OperatorLauncher -PathType Leaf)) {
        throw "canonical_operator_launcher_invalid"
    }

    $targetRoot = Resolve-TargetRuntime
    $panelLauncher = [System.IO.Path]::GetFullPath(
        (Join-Path $targetRoot "scripts\start_workflow_panel.ps1")
    )
    if (-not (Test-SafeArgument -Value $targetRoot) -or
        -not (Test-Path -LiteralPath $panelLauncher -PathType Leaf)) {
        throw "canonical_panel_launcher_invalid"
    }
    $storePath = Join-Path $ResolvedStateDir "observability\events.jsonl"
    if (-not [string]::IsNullOrWhiteSpace($TestOnlyScenario)) {
        if ($TestOnlyScenario -eq "panel_verification_failed") {
            Write-Summary -Result "blocked" `
                -Reason "workflow_panel_start_not_verified" `
                -PanelAction "started_unverified" -OperatorAction "not_started" `
                -ProcessesStarted $true -TargetRepoRoot $targetRoot `
                -PanelOwnership "owned" -PanelProcessId 41001 `
                -PanelCleanup "residual_unverified"
            exit 2
        }
        if ($TestOnlyScenario -eq "operator_launch_failed_owned") {
            Write-Summary -Result "blocked" -Reason "operator_launch_failed" `
                -PanelAction "started" -OperatorAction "launch_failed" `
                -ProcessesStarted $true -TargetRepoRoot $targetRoot `
                -PanelOwnership "owned" -PanelProcessId 41001 `
                -PanelCleanup "stopped"
            exit 2
        }
        if ($TestOnlyScenario -eq "operator_launch_failed_reused") {
            Write-Summary -Result "blocked" -Reason "operator_launch_failed" `
                -PanelAction "reused" -OperatorAction "launch_failed" `
                -ProcessesStarted $false -TargetRepoRoot $targetRoot `
                -PanelOwnership "reused" -PanelProcessId 41002 `
                -PanelCleanup "not_owned"
            exit 2
        }
        Write-Summary -Result "completed" -Reason "operator_exited" `
            -PanelAction "started" -OperatorAction "completed" `
            -ProcessesStarted $true -TargetRepoRoot $targetRoot `
            -PanelOwnership "owned" -PanelProcessId 41001 `
            -PanelCleanup "stopped" -OperatorProcessId 41003
        exit 0
    }
    $portState = Get-PanelPortState `
        -TargetRepoRoot $targetRoot `
        -ExpectedStateDir $ResolvedStateDir `
        -ExpectedObservationStore $storePath
    if ($portState -eq "unknown") {
        Write-Summary -Result "blocked" -Reason "panel_port_occupied_unknown" `
            -PanelAction "blocked" -OperatorAction "not_started" `
            -ProcessesStarted $false -TargetRepoRoot $targetRoot
        exit 2
    }

    if ($testOverrideRequested) {
        $panelPlan = if ($portState -eq "free") { "would_start" } else { "would_reuse" }
        Write-Summary -Result "ready" -Reason "test_plan_only" `
            -PanelAction $panelPlan -OperatorAction "would_start" `
            -ProcessesStarted $false -TargetRepoRoot $targetRoot
        exit 0
    }

    $panelAction = "reused"
    $panelOwnership = "reused"
    $panelCleanup = "not_owned"
    if ($portState -eq "free") {
        $panelArguments = (
            "-StateDir " + (ConvertTo-QuotedArgument -Value $ResolvedStateDir) +
            " -ObservationStore " + (ConvertTo-QuotedArgument -Value $storePath) +
            " -Port " + $PanelPort
        )
        $panelLauncherProcess = Start-HiddenPowerShell `
            -LauncherPath $panelLauncher -Arguments $panelArguments
        $processesStarted = $true
        $panelOwnership = "owned"
        $panelCleanup = "scheduled"
        $panelAction = "started_unverified"
        $verified = $false
        for ($attempt = 0; $attempt -lt 50; $attempt++) {
            Start-Sleep -Milliseconds 200
            if ((Get-PanelPortState `
                -TargetRepoRoot $targetRoot `
                -ExpectedStateDir $ResolvedStateDir `
                -ExpectedObservationStore $storePath) -eq "workflow_panel") {
                $verified = $true
                break
            }
        }
        if (-not $verified) {
            throw "workflow_panel_start_not_verified"
        }
        $panelProcessId = Get-LoopbackPanelListenerProcessId
        if ($panelProcessId -le 0 -or
            -not (Test-ProcessDescendsFrom `
                -ProcessId $panelProcessId `
                -ExpectedAncestorProcessId $panelLauncherProcess.Id)) {
            throw "workflow_panel_ownership_not_verified"
        }
        $panelAction = "started"
    }
    else {
        $panelProcessId = Get-LoopbackPanelListenerProcessId
    }

    $operatorArguments = (
        "-StartForeground -PublishStatus" +
        " -MaxCycles " + $MaxCycles +
        " -PollIntervalSeconds " + $PollIntervalSeconds +
        " -TimeoutSeconds " + $TimeoutSeconds +
        " -StateDir " + (ConvertTo-QuotedArgument -Value $ResolvedStateDir)
    )
    $operatorAction = "launching"
    $operatorProcess = Start-HiddenPowerShell `
        -LauncherPath $OperatorLauncher -Arguments $operatorArguments
    $operatorProcessId = $operatorProcess.Id
    $operatorAction = "started"
    $processesStarted = $true
    if ($operatorProcess.WaitForExit(500) -and $operatorProcess.ExitCode -ne 0) {
        $operatorAction = "launch_failed"
        throw "operator_launcher_failed_exit_code_$($operatorProcess.ExitCode)"
    }
    Write-Summary -Result "started" -Reason "none" `
        -PanelAction $panelAction -OperatorAction "started" `
        -ProcessesStarted $processesStarted -TargetRepoRoot $targetRoot `
        -PanelOwnership $panelOwnership -PanelProcessId $panelProcessId `
        -PanelCleanup $panelCleanup -OperatorProcessId $operatorProcessId
    if (-not $operatorProcess.HasExited) { $operatorProcess.WaitForExit() }
    if ($panelOwnership -eq "owned") {
        $panelCleanup = Stop-OwnedPanelRuntime `
            -LauncherProcess $panelLauncherProcess `
            -TargetRepoRoot $targetRoot `
            -ExpectedStateDir $ResolvedStateDir `
            -ExpectedObservationStore $storePath
    }
    $finalResult = "completed"
    $finalReason = "operator_exited"
    $operatorAction = "completed"
    $finalExitCode = 0
    if ($operatorProcess.ExitCode -ne 0) {
        $finalResult = "blocked"
        $finalReason = "operator_launcher_failed_exit_code_$($operatorProcess.ExitCode)"
        $operatorAction = "failed"
        $finalExitCode = 2
    }
    Write-Summary -Result $finalResult -Reason $finalReason `
        -PanelAction $panelAction -OperatorAction $operatorAction `
        -ProcessesStarted $processesStarted -TargetRepoRoot $targetRoot `
        -PanelOwnership $panelOwnership -PanelProcessId $panelProcessId `
        -PanelCleanup $panelCleanup -OperatorProcessId $operatorProcessId
    exit $finalExitCode
}
catch {
    if ($panelOwnership -eq "owned" -and $null -ne $panelLauncherProcess) {
        $panelCleanup = Stop-OwnedPanelRuntime `
            -LauncherProcess $panelLauncherProcess `
            -TargetRepoRoot $targetRoot `
            -ExpectedStateDir $ResolvedStateDir `
            -ExpectedObservationStore $storePath
    }
    Write-Summary -Result "blocked" -Reason $_.Exception.Message `
        -PanelAction $panelAction -OperatorAction $operatorAction `
        -ProcessesStarted $processesStarted -TargetRepoRoot $targetRoot `
        -PanelOwnership $panelOwnership -PanelProcessId $panelProcessId `
        -PanelCleanup $panelCleanup -OperatorProcessId $operatorProcessId
    exit 2
}
