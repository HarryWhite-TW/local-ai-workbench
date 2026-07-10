param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [switch]$Apply,

    [switch]$CompleteRecovery,

    [string]$GitUserName = "HarryWhite-TW",

    [string]$GitUserEmail = "harry061892@gmail.com",

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
    New-Item -ItemType File -Force -Path $StdoutPath | Out-Null
    New-Item -ItemType File -Force -Path $StderrPath | Out-Null
    $startedAt = (Get-Date).ToUniversalTime().ToString("o")
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
            command_path = $CommandPath
            arguments = $Arguments
            started_at = $startedAt
            ended_at = (Get-Date).ToUniversalTime().ToString("o")
            exit_code = $exitCode
            stdout_path = $StdoutPath
            stderr_path = $StderrPath
            launch_error = $launchError
            timed_out = $false
            stdout_bytes = (Get-Item -LiteralPath $StdoutPath).Length
            stderr_bytes = (Get-Item -LiteralPath $StderrPath).Length
            first_safe_error = if ($launchError) { $launchError } elseif ($exitCode -ne 0) { "exit_code=$exitCode" } else { $null }
        }
    }
    finally {
        Pop-Location
    }
}

function Add-PathEntry([string]$Entry) {
    $existing = @($env:PATH -split ";" | Where-Object { $_ })
    if (-not ($existing | Where-Object { $_.TrimEnd("\\") -ieq $Entry.TrimEnd("\\") })) {
        $env:PATH = "$Entry;$env:PATH"
        return $true
    }
    return $false
}

function Invoke-SafeAuthStatus([string]$GhPath, [string]$WorkingDirectory, [string]$StdoutPath, [string]$StderrPath) {
    New-Item -ItemType File -Force -Path $StdoutPath | Out-Null
    New-Item -ItemType File -Force -Path $StderrPath | Out-Null
    Push-Location $WorkingDirectory
    try {
        & $GhPath auth status 1>$null 2>$null
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
    }
    catch { $exitCode = 3 }
    finally { Pop-Location }
    return [ordered]@{ exit_code = $exitCode; stdout_path = $StdoutPath; stderr_path = $StderrPath; stdout_bytes = 0; stderr_bytes = 0; first_safe_error = if ($exitCode -ne 0) { "gh_auth_status_failed" } else { $null } }
}

function Get-ActionFailures($Payload) {
    if (-not $Payload -or -not $Payload.failure) { return @() }
    if ($Payload.failure.failed_action) { return @([string]$Payload.failure.failed_action) }
    return @()
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
if ($CompleteRecovery -and $auditPayload -and $auditPayload.overall_status -ne "READY") {
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

$historicalActionFailures = Get-ActionFailures $applyPayload
$supersededActionFailures = @()
$currentBlockers = @()
if ($postAuditPayload -and $postAuditPayload.overall_status -ne "READY") {
    $currentBlockers += @($postAuditPayload.blockers)
}
elseif ($historicalActionFailures.Count -gt 0) {
    $supersededActionFailures = $historicalActionFailures
}

$pathActions = @()
if ($CompleteRecovery) {
    foreach ($entry in @((Split-Path -Parent $reviewedPythonPath), (Split-Path -Parent $reviewedGhPath), (Split-Path -Parent $reviewedCodexPath))) {
        if (Add-PathEntry -Entry $entry) { $pathActions += $entry }
    }
}

$gitIdentityBefore = [ordered]@{ name = (Invoke-GitText -GitPath $gitPath -Arguments @("config", "--local", "user.name") -WorkingDirectory $resolvedRepoRoot).text; email = (Invoke-GitText -GitPath $gitPath -Arguments @("config", "--local", "user.email") -WorkingDirectory $resolvedRepoRoot).text }
$gitIdentityAction = "none"
if ($CompleteRecovery -and ($gitIdentityBefore.name -ne $GitUserName -or $gitIdentityBefore.email -ne $GitUserEmail)) {
    & $gitPath config --local user.name $GitUserName
    & $gitPath config --local user.email $GitUserEmail
    $gitIdentityAction = "set_repo_local"
}
$gitIdentityAfter = [ordered]@{ name = (Invoke-GitText -GitPath $gitPath -Arguments @("config", "--local", "user.name") -WorkingDirectory $resolvedRepoRoot).text; email = (Invoke-GitText -GitPath $gitPath -Arguments @("config", "--local", "user.email") -WorkingDirectory $resolvedRepoRoot).text }
$gitIdentityReady = ($gitIdentityAfter.name -eq $GitUserName -and $gitIdentityAfter.email -eq $GitUserEmail)

$authRun = $null
$repoReadRun = $null
$needsUserInteraction = $null
if ($CompleteRecovery -and (Test-Path -LiteralPath $reviewedGhPath -PathType Leaf)) {
    $authRun = Invoke-SafeAuthStatus -GhPath $reviewedGhPath -WorkingDirectory $resolvedRepoRoot -StdoutPath (Join-Path $evidenceRootPath "gh_auth.stdout.txt") -StderrPath (Join-Path $evidenceRootPath "gh_auth.stderr.txt")
    if ($authRun.exit_code -ne 0) {
        $needsUserInteraction = "gh_browser_auth"
        & $reviewedGhPath auth login --web
        if ($LASTEXITCODE -eq 0) { $authRun = Invoke-SafeAuthStatus -GhPath $reviewedGhPath -WorkingDirectory $resolvedRepoRoot -StdoutPath (Join-Path $evidenceRootPath "gh_auth_recheck.stdout.txt") -StderrPath (Join-Path $evidenceRootPath "gh_auth_recheck.stderr.txt") }
    }
    if ($authRun.exit_code -eq 0) {
        $repoReadRun = Invoke-FileCapturedCommand -CommandPath $reviewedGhPath -Arguments @("repo", "view", $ExpectedRepository, "--json", "nameWithOwner") -WorkingDirectory $resolvedRepoRoot -StdoutPath (Join-Path $evidenceRootPath "gh_repo_read.stdout.txt") -StderrPath (Join-Path $evidenceRootPath "gh_repo_read.stderr.txt")
        if ($repoReadRun.exit_code -ne 0) { $currentBlockers += "gh_repository_read_failed" }
    }
    else { $currentBlockers += "gh_auth_failed" }
}

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
    protocol = "lawb.course_environment_restore_review.v2"
    verdict = if ($currentBlockers.Count -eq 0 -and $layerOneStatus -eq "READY") { "READY" } else { "BLOCKED" }
    blocking_reason = ($currentBlockers -join ",")
    needs_user_interaction = $needsUserInteraction
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
    components = [ordered]@{
        python = if (Test-Path -LiteralPath $reviewedPythonPath) { "READY" } else { "BLOCKED" }
        dependencies = if ($postAuditPayload -and $postAuditPayload.dependencies.ready) { "READY" } else { "BLOCKED" }
        gh = if (Test-Path -LiteralPath $reviewedGhPath) { "READY" } else { "BLOCKED" }
        gh_auth = if ($authRun -and $authRun.exit_code -eq 0) { "READY" } elseif ($CompleteRecovery) { "BLOCKED" } else { "NOT_CHECKED" }
        gh_repository_read = if ($repoReadRun -and $repoReadRun.exit_code -eq 0) { "READY" } elseif ($CompleteRecovery) { "NOT_CHECKED" } else { "NOT_CHECKED" }
        codex = if (Test-Path -LiteralPath $reviewedCodexPath) { "READY" } else { "BLOCKED" }
        git_identity = if ($gitIdentityReady) { "READY" } else { "BLOCKED" }
        path = if ($pathActions.Count -eq 0) { "UNCHANGED" } else { "CURRENT_PROCESS_UPDATED" }
    }
    git_identity_before = $gitIdentityBefore
    git_identity_action = $gitIdentityAction
    git_identity_after = $gitIdentityAfter
    git_identity_ready = $gitIdentityReady
    historical_action_failures = $historicalActionFailures
    superseded_action_failures = $supersededActionFailures
    current_blockers = $currentBlockers
    final_git_state = $finalGitState
    safety = [ordered]@{
        live_acceptance_invoked = $false
        dispatcher_invoked = $false
        runner_invoked = $false
        codex_task_invoked = $false
        github_write_performed = $false
        gh_auth_token_invoked = $false
        permanent_path_modified = $false
        git_identity_written = ($gitIdentityAction -ne "none")
        global_git_identity_modified = $false
    }
    stop_marker = $StopMarker
    safety_stop_marker = $SafetyStopMarker
}

$summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

Write-Host "Evidence root: $evidenceRootPath"
Write-Host "Bootstrap AUDIT JSON: $auditStdout"
if ($CompleteRecovery -and $applyRun) {
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
Write-Host "Verdict: $($summary.verdict)"
Write-Host $StopMarker
Write-Host $SafetyStopMarker

if ($summary.verdict -eq "BLOCKED") { exit 2 }
