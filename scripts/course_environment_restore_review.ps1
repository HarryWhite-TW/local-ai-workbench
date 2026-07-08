param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [switch]$Apply,

    [string]$ExpectedRepository = "HarryWhite-TW/local-ai-workbench",

    [string]$ExpectedBranch,

    [string]$ExpectedHead,

    [string]$EvidenceRoot
)

$ErrorActionPreference = "Stop"

$StopMarker = "COURSE_ENVIRONMENT_RESTORE_REVIEW_DONE"
$SafetyStopMarker = "NO_LIVE_ACCEPTANCE_NO_DISPATCHER_NO_RUNNER_NO_CODEX_TASK_NO_GITHUB_WRITE"

function Resolve-PowerShellExe {
    $command = Get-Command "powershell.exe" -ErrorAction SilentlyContinue
    if ($command -and $command.Source) { return $command.Source }
    $command = Get-Command "powershell" -ErrorAction SilentlyContinue
    if ($command -and $command.Source) { return $command.Source }
    throw "PowerShell executable was not found."
}

function New-EvidenceRoot([string]$RequestedRoot) {
    if ($RequestedRoot) {
        New-Item -ItemType Directory -Force -Path $RequestedRoot | Out-Null
        return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $RequestedRoot).Path)
    }
    $name = "lawb-course-restore-review-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $path = Join-Path ([System.IO.Path]::GetTempPath()) $name
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return [System.IO.Path]::GetFullPath($path)
}

function Invoke-FileCapturedCommand([string]$CommandPath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$StdoutPath, [string]$StderrPath) {
    Push-Location $WorkingDirectory
    try {
        $launchError = $null
        try {
            & $CommandPath @Arguments 1> $StdoutPath 2> $StderrPath
            $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        }
        catch {
            $exitCode = 3
            $launchError = $_.Exception.GetType().Name
            [System.IO.File]::WriteAllText($StderrPath, $_.Exception.Message)
        }
        return [ordered]@{
            exit_code = $exitCode
            stdout_path = $StdoutPath
            stderr_path = $StderrPath
            launch_error = $launchError
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-GitText([string]$GitPath, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        $output = & $GitPath @Arguments 2>$null
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        return [ordered]@{
            exit_code = $exitCode
            text = (@($output) -join "`n").Trim()
        }
    }
    finally {
        Pop-Location
    }
}

function Read-JsonFileIfPossible([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if (-not $text.Trim()) { return $null }
    try {
        return $text | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Test-RepositoryUrl([string]$Url, [string]$Expected) {
    if (-not $Url) { return $false }
    $escaped = [regex]::Escape($Expected).Replace("/", "[\\/]")
    return $Url -match "$escaped(\.git)?$"
}

function Get-LayerOneStatus($AuditPayload, $ApplyPayload, $PostAuditPayload) {
    if ($ApplyPayload -and $ApplyPayload.overall_status -eq "BLOCKED") { return "BLOCKED" }
    if ($PostAuditPayload -and $PostAuditPayload.overall_status) { return [string]$PostAuditPayload.overall_status }
    if ($AuditPayload -and $AuditPayload.overall_status) { return [string]$AuditPayload.overall_status }
    return "UNKNOWN"
}

function Get-HostCheckStatus($CheckPayload, [string]$SkipReason) {
    if ($SkipReason) { return "SKIPPED: $SkipReason" }
    if ($CheckPayload -and $CheckPayload.status) { return [string]$CheckPayload.status }
    return "UNKNOWN"
}

function Get-DriftReasons($CheckPayload) {
    if (-not $CheckPayload -or -not $CheckPayload.status_reasons) { return @() }
    $known = @(
        "git_identity_missing",
        "manifest_venv_not_gitignored"
    )
    $reasons = @()
    foreach ($reason in @($CheckPayload.status_reasons)) {
        $text = [string]$reason
        if ($known -contains $text -or $text -like "path_*_differs_from_reviewed_*" -or $text -like "fresh_shell_*_differs_from_reviewed_*") {
            $reasons += $text
        }
    }
    return $reasons
}

$resolvedRepoRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $RepoRoot).Path)
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRepoRoot ".git") -PathType Container)) {
    throw "RepoRoot is not a Git repository root: $resolvedRepoRoot"
}

$evidenceRootPath = New-EvidenceRoot $EvidenceRoot
$safeTempRoot = Join-Path $evidenceRootPath "temp"
New-Item -ItemType Directory -Force -Path $safeTempRoot | Out-Null

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bootstrapScript = Join-Path $scriptRoot "bootstrap_course_environment.ps1"
$hostCheckScript = Join-Path $scriptRoot "host_check_v1.ps1"
$manifestPath = Join-Path $scriptRoot "bootstrap_manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$powerShellPath = Resolve-PowerShellExe
$gitPath = (Get-Command "git" -ErrorAction Stop).Source

$startingState = [ordered]@{
    origin = (Invoke-GitText -GitPath $gitPath -Arguments @("remote", "get-url", "origin") -WorkingDirectory $resolvedRepoRoot)
    branch = (Invoke-GitText -GitPath $gitPath -Arguments @("branch", "--show-current") -WorkingDirectory $resolvedRepoRoot)
    head = (Invoke-GitText -GitPath $gitPath -Arguments @("rev-parse", "HEAD") -WorkingDirectory $resolvedRepoRoot)
    origin_master = (Invoke-GitText -GitPath $gitPath -Arguments @("rev-parse", "origin/master") -WorkingDirectory $resolvedRepoRoot)
    divergence = (Invoke-GitText -GitPath $gitPath -Arguments @("rev-list", "--left-right", "--count", "HEAD...origin/master") -WorkingDirectory $resolvedRepoRoot)
    working_tree = (Invoke-GitText -GitPath $gitPath -Arguments @("status", "--porcelain=v1", "-uall") -WorkingDirectory $resolvedRepoRoot)
    staged = (Invoke-GitText -GitPath $gitPath -Arguments @("diff", "--cached", "--name-only") -WorkingDirectory $resolvedRepoRoot)
}
$startingStatePath = Join-Path $evidenceRootPath "starting_git_state.json"
$startingState | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $startingStatePath -Encoding UTF8

if (-not (Test-RepositoryUrl -Url $startingState.origin.text -Expected $ExpectedRepository)) {
    throw "Starting-state gate blocked: origin does not match $ExpectedRepository"
}
if ($ExpectedBranch -and $startingState.branch.text -ne $ExpectedBranch) {
    throw "Starting-state gate blocked: branch '$($startingState.branch.text)' does not match '$ExpectedBranch'"
}
if ($ExpectedHead -and $startingState.head.text -ne $ExpectedHead) {
    throw "Starting-state gate blocked: HEAD '$($startingState.head.text)' does not match '$ExpectedHead'"
}

$auditStdout = Join-Path $evidenceRootPath "bootstrap_audit.json"
$auditStderr = Join-Path $evidenceRootPath "bootstrap_audit.stderr.txt"
$auditRun = Invoke-FileCapturedCommand -CommandPath $powerShellPath -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $bootstrapScript, "-RepoRoot", $resolvedRepoRoot, "-Json") -WorkingDirectory $resolvedRepoRoot -StdoutPath $auditStdout -StderrPath $auditStderr
$auditPayload = Read-JsonFileIfPossible $auditStdout

$applyRun = $null
$applyPayload = $null
$applyStdout = $null
$applyStderr = $null
if ($Apply) {
    $applyStdout = Join-Path $evidenceRootPath "bootstrap_apply.json"
    $applyStderr = Join-Path $evidenceRootPath "bootstrap_apply.stderr.txt"
    $applyRun = Invoke-FileCapturedCommand -CommandPath $powerShellPath -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $bootstrapScript, "-RepoRoot", $resolvedRepoRoot, "-Json", "-Apply") -WorkingDirectory $resolvedRepoRoot -StdoutPath $applyStdout -StderrPath $applyStderr
    $applyPayload = Read-JsonFileIfPossible $applyStdout
}

$postAuditStdout = Join-Path $evidenceRootPath "bootstrap_post_restore_audit.json"
$postAuditStderr = Join-Path $evidenceRootPath "bootstrap_post_restore_audit.stderr.txt"
$postAuditRun = Invoke-FileCapturedCommand -CommandPath $powerShellPath -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $bootstrapScript, "-RepoRoot", $resolvedRepoRoot, "-Json") -WorkingDirectory $resolvedRepoRoot -StdoutPath $postAuditStdout -StderrPath $postAuditStderr
$postAuditPayload = Read-JsonFileIfPossible $postAuditStdout

$localAppData = if ($env:LAWB_BOOTSTRAP_LOCALAPPDATA) { $env:LAWB_BOOTSTRAP_LOCALAPPDATA } else { $env:LOCALAPPDATA }
$reviewedPythonPath = Join-Path $resolvedRepoRoot (Join-Path $Manifest.paths.venv "Scripts\python.exe")
$reviewedGhPath = Join-Path $localAppData "LocalAIWorkbench\gh\current\gh.exe"
$reviewedCodexPath = Join-Path (Join-Path $localAppData "LocalAIWorkbench\npm") "codex.cmd"

$pytestStdout = Join-Path $evidenceRootPath "focused_pytest.stdout.txt"
$pytestStderr = Join-Path $evidenceRootPath "focused_pytest.stderr.txt"
$pytestRun = [ordered]@{
    exit_code = $null
    stdout_path = $pytestStdout
    stderr_path = $pytestStderr
    skipped_reason = $null
}
if (Test-Path -LiteralPath $reviewedPythonPath -PathType Leaf) {
    $pytestBaseTemp = Join-Path $safeTempRoot "pytest"
    New-Item -ItemType Directory -Force -Path $pytestBaseTemp | Out-Null
    $pytestArgs = @(
        "-m", "pytest",
        "-q",
        "-p", "no:cacheprovider",
        "tests/test_bootstrap_course_environment.py",
        "tests/test_host_check_v1_script.py",
        "--basetemp", $pytestBaseTemp
    )
    $pytestRun = Invoke-FileCapturedCommand -CommandPath $reviewedPythonPath -Arguments $pytestArgs -WorkingDirectory $resolvedRepoRoot -StdoutPath $pytestStdout -StderrPath $pytestStderr
}
else {
    $pytestRun.skipped_reason = "reviewed_python_missing"
    Set-Content -LiteralPath $pytestStdout -Value "" -Encoding UTF8
    Set-Content -LiteralPath $pytestStderr -Value "reviewed_python_missing" -Encoding UTF8
}

$hostCheckStdout = Join-Path $evidenceRootPath "host_check.json"
$hostCheckStderr = Join-Path $evidenceRootPath "host_check.stderr.txt"
$hostCheckRun = [ordered]@{
    exit_code = $null
    stdout_path = $hostCheckStdout
    stderr_path = $hostCheckStderr
    skipped_reason = $null
}
$hostCheckPayload = $null
$missingReviewedPaths = @()
foreach ($path in @($reviewedPythonPath, $reviewedGhPath, $reviewedCodexPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $missingReviewedPaths += $path
    }
}
if ($missingReviewedPaths.Count -eq 0) {
    $hostBranch = if ($ExpectedBranch) { $ExpectedBranch } else { $startingState.branch.text }
    $hostHead = if ($ExpectedHead) { $ExpectedHead } else { $startingState.head.text }
    $hostCheckArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $hostCheckScript,
        "-RepoRoot", $resolvedRepoRoot,
        "-ExpectedRepository", $ExpectedRepository,
        "-ExpectedBranch", $hostBranch,
        "-ExpectedHead", $hostHead,
        "-ReviewedPythonPath", $reviewedPythonPath,
        "-ReviewedGhPath", $reviewedGhPath,
        "-ReviewedCodexPath", $reviewedCodexPath,
        "-Json"
    )
    $hostCheckRun = Invoke-FileCapturedCommand -CommandPath $powerShellPath -Arguments $hostCheckArgs -WorkingDirectory $resolvedRepoRoot -StdoutPath $hostCheckStdout -StderrPath $hostCheckStderr
    $hostCheckPayload = Read-JsonFileIfPossible $hostCheckStdout
}
else {
    $hostCheckRun.skipped_reason = "reviewed_paths_missing"
    Set-Content -LiteralPath $hostCheckStdout -Value "" -Encoding UTF8
    Set-Content -LiteralPath $hostCheckStderr -Value ($missingReviewedPaths -join "`n") -Encoding UTF8
}

$summaryPath = Join-Path $evidenceRootPath "course_environment_restore_review_summary.json"
$layerOneStatus = Get-LayerOneStatus -AuditPayload $auditPayload -ApplyPayload $applyPayload -PostAuditPayload $postAuditPayload
$layerTwoStatus = Get-HostCheckStatus -CheckPayload $hostCheckPayload -SkipReason $hostCheckRun.skipped_reason
$driftReasons = Get-DriftReasons $hostCheckPayload
$finalGitState = [ordered]@{
    status_porcelain = (Invoke-GitText -GitPath $gitPath -Arguments @("status", "--porcelain=v1", "-uall") -WorkingDirectory $resolvedRepoRoot)
    staged_files = (Invoke-GitText -GitPath $gitPath -Arguments @("diff", "--cached", "--name-only") -WorkingDirectory $resolvedRepoRoot)
    head = (Invoke-GitText -GitPath $gitPath -Arguments @("rev-parse", "HEAD") -WorkingDirectory $resolvedRepoRoot)
    branch = (Invoke-GitText -GitPath $gitPath -Arguments @("branch", "--show-current") -WorkingDirectory $resolvedRepoRoot)
}

$summary = [ordered]@{
    protocol = "lawb.course_environment_restore_review.v1"
    evidence_root = $evidenceRootPath
    paths = [ordered]@{
        starting_git_state = $startingStatePath
        bootstrap_audit = $auditStdout
        bootstrap_apply = $applyStdout
        bootstrap_post_restore_audit = $postAuditStdout
        focused_pytest_stdout = $pytestStdout
        focused_pytest_stderr = $pytestStderr
        host_check = $hostCheckStdout
        summary = $summaryPath
    }
    reviewed_paths = [ordered]@{
        python = $reviewedPythonPath
        gh = $reviewedGhPath
        codex = $reviewedCodexPath
    }
    exit_codes = [ordered]@{
        bootstrap_audit = $auditRun.exit_code
        bootstrap_apply = if ($applyRun) { $applyRun.exit_code } else { $null }
        bootstrap_post_restore_audit = $postAuditRun.exit_code
        focused_pytest = $pytestRun.exit_code
        host_check = $hostCheckRun.exit_code
    }
    statuses = [ordered]@{
        layer_1_tool_restore = $layerOneStatus
        layer_2_host_check = $layerTwoStatus
        layer_3_drift_reasons = $driftReasons
    }
    final_git_state = $finalGitState
    safety = [ordered]@{
        live_acceptance_invoked = $false
        dispatcher_invoked = $false
        runner_invoked = $false
        codex_task_invoked = $false
        github_write_performed = $false
        gh_auth_token_invoked = $false
        permanent_path_modified = $false
        git_identity_written = $false
    }
    stop_marker = $StopMarker
    safety_stop_marker = $SafetyStopMarker
}

$summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Host "Evidence root: $evidenceRootPath"
Write-Host "Bootstrap AUDIT JSON: $auditStdout"
if ($Apply) {
    Write-Host "Bootstrap APPLY JSON: $applyStdout"
}
Write-Host "Post-restore AUDIT JSON: $postAuditStdout"
Write-Host "Focused pytest stdout: $pytestStdout"
Write-Host "Focused pytest stderr: $pytestStderr"
Write-Host "Host Check JSON: $hostCheckStdout"
Write-Host "Summary JSON: $summaryPath"
Write-Host "Layer 1 restore status: $layerOneStatus"
Write-Host "Layer 2 Host Check status: $layerTwoStatus"
Write-Host "Layer 3 drift reasons: $($driftReasons -join ', ')"
Write-Host $StopMarker
Write-Host $SafetyStopMarker
