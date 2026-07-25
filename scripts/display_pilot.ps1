param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("setup", "verify", "start")]
    [string]$Action,
    [Parameter(Mandatory = $true)]
    [string]$StateRoot,
    [string]$LawbRoot = "",
    [string]$LawbBranch = "",
    [string]$LawbHead = "",
    [string[]]$LawbExpectedModifiedFile = @(),
    [string]$HgwRoot = "",
    [string]$TargetRepoRoot = "",
    [string]$PythonPath = "",
    [string]$PowerShellPath = "",
    [string]$GhPath = "",
    [string]$CodexPath = "",
    [string]$RunnerPath = "",
    [ValidateRange(1, 1000)]
    [int]$MaxCycles = 100,
    [ValidateRange(0, 3600)]
    [double]$PollIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$repoPython = Join-Path $repoRoot ".venv-course\Scripts\python.exe"
$repoSrc = Join-Path $repoRoot "src"
$moduleBootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]='display_pilot_operator_cli'; runpy.run_module('local_runner_bridge.display_pilot_operator_cli',run_name='__main__')"
$arguments = @(
    "-c",
    $moduleBootstrap,
    $repoSrc,
    $Action,
    "--state-root",
    $StateRoot,
    "--max-cycles",
    [string]$MaxCycles,
    "--poll-interval-seconds",
    [string]$PollIntervalSeconds
)

foreach ($binding in @(
    @("--lawb-root", $LawbRoot),
    @("--lawb-branch", $LawbBranch),
    @("--lawb-head", $LawbHead),
    @("--hgw-root", $HgwRoot),
    @("--target-repo-root", $TargetRepoRoot),
    @("--python-path", $PythonPath),
    @("--powershell-path", $PowerShellPath),
    @("--gh-path", $GhPath),
    @("--codex-path", $CodexPath),
    @("--runner-path", $RunnerPath)
)) {
    if (-not [string]::IsNullOrWhiteSpace([string]$binding[1])) {
        $arguments += [string]$binding[0]
        $arguments += [string]$binding[1]
    }
}

foreach ($path in $LawbExpectedModifiedFile) {
    if (-not [string]::IsNullOrWhiteSpace($path)) {
        $arguments += "--lawb-expected-modified-file"
        $arguments += $path
    }
}

& $repoPython @arguments
exit $LASTEXITCODE
