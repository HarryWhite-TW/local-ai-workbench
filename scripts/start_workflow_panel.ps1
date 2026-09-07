<#
.SYNOPSIS
Starts the localhost-only, read-only Workflow Panel in the foreground.

.DESCRIPTION
Reads existing Bridge Operator lifecycle files and the Workflow observation
store. This launcher does not invoke Bridge Operator, Dispatcher, Runner,
Codex, GitHub, or any write/control route.

.EXAMPLE
.\scripts\start_workflow_panel.ps1

.EXAMPLE
.\scripts\start_workflow_panel.ps1 -StateDir C:\temp\workflow-fixture -Port 8765
#>

[CmdletBinding()]
param(
    [string]$StateDir = "",
    [string]$ObservationStore = "",
    [ValidateRange(0, 65535)]
    [int]$Port = 8765
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = [System.IO.Path]::GetFullPath(
    (Join-Path -Path $PSScriptRoot -ChildPath "..")
).TrimEnd("\")

if ([string]::IsNullOrWhiteSpace($StateDir)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "local_app_data_unavailable"
    }
    $StateDir = Join-Path -Path $env:LOCALAPPDATA -ChildPath "LocalAIWorkbench\BridgeOperator"
}
$ResolvedStateDir = [System.IO.Path]::GetFullPath($StateDir)

if ([string]::IsNullOrWhiteSpace($ObservationStore)) {
    $ObservationStore = Join-Path -Path $ResolvedStateDir -ChildPath "observability\events.jsonl"
}
$ResolvedObservationStore = [System.IO.Path]::GetFullPath($ObservationStore)

$ReviewedPython = Join-Path -Path $RepoRoot -ChildPath ".venv-course\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ReviewedPython -PathType Leaf)) {
    $PythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $PythonCommand) {
        throw "python_unavailable"
    }
    $ReviewedPython = $PythonCommand.Source
}

$PreviousPythonPath = $env:PYTHONPATH
$SourcePath = Join-Path -Path $RepoRoot -ChildPath "src"
try {
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) {
        $SourcePath
    }
    else {
        "$SourcePath;$PreviousPythonPath"
    }
    & $ReviewedPython -m local_runner_bridge.workflow_panel `
        --state-dir $ResolvedStateDir `
        --store $ResolvedObservationStore `
        --host 127.0.0.1 `
        --port $Port
    $PanelExitCode = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}

if ($PanelExitCode -ne 0) {
    throw "workflow_panel_failed_exit_code_$PanelExitCode"
}
