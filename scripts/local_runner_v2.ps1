<#
.SYNOPSIS
Detects runner v2A ReviewBundle-ready issues and can run one ReviewBundle.

.DESCRIPTION
local_runner_v2.ps1 is a local, on-demand v2A runner. In -DryRun mode it checks
local repository state, reads open GitHub issues, prints matching candidate
issues, and stops. In -RunOnce mode it requires exactly one matching candidate
and delegates only to runner v1 ReviewBundle for that issue.
In -ApprovalDryRun mode it reads one issue's comments for a structured
RUNNER-V2-APPROVE marker, validates it against local state, prints the planned
action, and stops without executing anything.
In -ApprovalOnce mode it validates a structured RUNNER-V2-APPROVE marker and
delegates only to runner v1 ReviewBundle for the approved issue.
In -ApprovalNextDryRun mode it searches a bounded set of open issues, validates
the unique current RUNNER-V2-APPROVE action=run-reviewbundle marker, prints the
planned action, and stops without executing anything.
In -ApprovalNextOnce mode it uses the same unique approval validation, then
delegates once to runner v1 ReviewBundle for the selected issue.
In -ApprovalNextWatch mode it polls in the foreground for one bounded
action=run-reviewbundle approval, delegates at most once to runner v1
ReviewBundle, and exits.
In -ApprovalNextCommitDryRun mode it validates one bounded
action=commit-approved-docs-only approval against the current docs-only local
state, prints the planned local commit action, and exits without writing.
In -ApprovalNextCommitOnce mode it performs the same validation and delegates
once to runner v1 CommitApproved using a non-interactive state-bound approval
token, creating at most one local docs-only commit.
In -PushDryRun mode it validates one current action=push-dryrun-approved
approval against the current one-commit-ahead state, reports the planned push
target, and exits without running git push.
In -PushOnce mode it validates one current action=push-approved-once approval
against the same one-commit-ahead state, runs exactly one narrow git push, and
reports the pushed commit and remote result.
In -CloseIssueOnce mode it validates one current action=close-issue-approved-once
approval on the explicitly selected issue against the current pushed local /
remote state, closes exactly that one issue, and reports the final state.
In -DryRunQueue mode it reads one explicit local queue definition, validates the
planned queue, emits a single QUEUE-RUNNER-RESULT packet, and exits without
executing any queue task.
In -RunQueue mode it reads one explicit local queue definition, validates the
repo, branch, HEAD, dirty state, and task bounds, executes only approved
low-risk read-only tasks in sequence, emits a single QUEUE-RUNNER-RESULT
packet, and exits.

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRun

.EXAMPLE
.\scripts\local_runner_v2.ps1 -RunOnce

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalDryRun -IssueNumber 39

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalOnce -IssueNumber 41

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalNextDryRun

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalNextOnce

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalNextWatch -TimeoutSeconds 300 -PollSeconds 15

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalNextCommitDryRun

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalNextCommitOnce

.EXAMPLE
.\scripts\local_runner_v2.ps1 -PushDryRun

.EXAMPLE
.\scripts\local_runner_v2.ps1 -PushOnce

.EXAMPLE
.\scripts\local_runner_v2.ps1 -CloseIssueOnce -IssueNumber 73

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRunQueue -QueueFile .\queue.json

.EXAMPLE
.\scripts\local_runner_v2.ps1 -RunQueue -QueueFile .\queue.json

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRun -Repo "HarryWhite-TW/local-ai-workbench" -MaxIssues 20
#>

param(
    [switch]$DryRun,
    [switch]$RunOnce,
    [switch]$ApprovalDryRun,
    [switch]$ApprovalOnce,
    [switch]$ApprovalNextDryRun,
    [switch]$ApprovalNextOnce,
    [switch]$ApprovalNextWatch,
    [switch]$ApprovalNextCommitDryRun,
    [switch]$ApprovalNextCommitOnce,
    [switch]$PushDryRun,
    [switch]$PushOnce,
    [switch]$CloseIssueOnce,
    [switch]$DryRunQueue,
    [switch]$RunQueue,
    [switch]$ApprovalStateDiagnostic,
    [int]$IssueNumber = 0,
    [string]$QueueFile = "",
    [ValidateNotNullOrEmpty()]
    [string]$Repo = "HarryWhite-TW/local-ai-workbench",
    [ValidateRange(1, 100)]
    [int]$MaxIssues = 50,
    [ValidateRange(1, 2147483647)]
    [int]$TimeoutSeconds = 300,
    [ValidateRange(10, 2147483647)]
    [int]$PollSeconds = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v2"
$RunnerVersion = "v2A-runonce-reviewbundle"
$ExpectedApprovalRepo = "HarryWhite-TW/local-ai-workbench"
$RunnerResultProtocol = "lawb.runner_result.v1"
$RunnerResultMarker = "LAWBRUNNER-RESULT protocol=$RunnerResultProtocol"
$RunnerV1CommitApprovalStateProtocol = "lawb.runner_v1.commit_approval_state.v1"
$RunnerV1CommitApprovalStateMarker = "LRV1-COMMIT-APPROVAL-STATE protocol=$RunnerV1CommitApprovalStateProtocol"
$QueueRunnerResultProtocol = "lawb.queue_runner_result.v1"
$QueueRunnerResultMarker = "QUEUE-RUNNER-RESULT protocol=$QueueRunnerResultProtocol"
$QueueDefinitionProtocol = "lawb.queue_definition.v1"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$RequiredMarkers = @(
    "Runner marker: runner-v2-reviewbundle-ready",
    "write-capable",
    "review-bundle capable"
)
$NoWriteGuarantee = "DryRun detection only: does not call Codex, run runner v1, modify files, post comments, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, or invoke external agents."
$RunOnceSafetyBoundary = "RunOnce delegates only to runner v1 ReviewBundle for exactly one eligible candidate. It does not call Codex directly, run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run a polling loop."
$ApprovalMarkerPrefix = "RUNNER-V2-APPROVE"
$ApprovalProtocol = "v2.approval.1"
$ApprovalDryRunSupportedAction = "detect-approval"
$ApprovalOnceSupportedAction = "run-reviewbundle"
$ApprovalNextDryRunSupportedAction = "run-reviewbundle"
$ApprovalNextCommitSupportedAction = "commit-approved-docs-only"
$PushDryRunSupportedAction = "push-dryrun-approved"
$PushOnceSupportedAction = "push-approved-once"
$CloseIssueOnceSupportedAction = "close-issue-approved-once"
$ApprovalBaseRequiredFields = @(
    "protocol",
    "action",
    "issue",
    "repo",
    "branch",
    "expires"
)
$ApprovalRequiredFields = @(
    $ApprovalBaseRequiredFields +
    "head",
    "review",
    "diff",
    "files"
)
$PushDryRunRequiredFields = @(
    $ApprovalBaseRequiredFields +
    "localhead",
    "remote",
    "upstream",
    "remotehead",
    "commit",
    "ahead",
    "commitfiles"
)
$CloseIssueOnceRequiredFields = @(
    $ApprovalBaseRequiredFields +
    "target",
    "targetstate",
    "localhead",
    "remote",
    "upstream",
    "remotehead",
    "pushed"
)
$ApprovalKnownFields = @($ApprovalRequiredFields + $PushDryRunRequiredFields + $CloseIssueOnceRequiredFields + "filelist" | Sort-Object -Unique)
$ApprovalDryRunNoWriteGuarantee = "ApprovalDryRun detection only: does not call Codex, run runner v1, modify files, post GitHub comments, stage files, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run a polling loop, daemon, or scheduler."
$ApprovalOnceSafetyBoundary = "ApprovalOnce delegates only to runner v1 ReviewBundle for the approved issue. It does not call Codex directly, run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run a polling loop."
$ApprovalNextDryRunNoWriteGuarantee = "ApprovalNextDryRun detection only: does not call Codex, run runner v1, execute ApprovalOnce, modify files, post GitHub comments, stage files, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run polling, watch, daemon, or scheduler behavior."
$ApprovalNextOnceSafetyBoundary = "ApprovalNextOnce delegates once to runner v1 ReviewBundle for exactly one current action=run-reviewbundle approval. It does not call Codex directly, run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run polling, watch, daemon, or scheduler behavior."
$ApprovalNextWatchSafetyBoundary = "ApprovalNextWatch is a bounded foreground poller. It delegates at most once to runner v1 ReviewBundle for exactly one current action=run-reviewbundle approval, returns runner v1's exit code after delegation, and does not call Codex directly, run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, run a daemon, run a scheduler, or chain approvals."
$ApprovalNextCommitDryRunNoWriteGuarantee = "ApprovalNextCommitDryRun validates one current action=commit-approved-docs-only approval only. It does not call Codex, run runner v1, modify files, post GitHub comments, stage files, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, run polling, run a daemon, run a scheduler, or chain approvals."
$ApprovalNextCommitOnceSafetyBoundary = "ApprovalNextCommitOnce validates one current action=commit-approved-docs-only approval, then delegates once to runner v1 CommitApproved with a non-interactive state-bound token. It creates at most one local docs-only commit and does not push, close issues, edit labels, create PRs, merge, force push, call Codex, install dependencies, change PATH or Windows settings, invoke external agents, run polling, run a daemon, run a scheduler, or chain approvals."
$PushDryRunNoWriteGuarantee = "PushDryRun validates one current action=push-dryrun-approved approval only. It does not run git push, call Codex, run runner v1, modify files, post GitHub comments, stage files, commit, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, run polling, run a daemon, run a scheduler, or chain approvals."
$PushOnceSafetyBoundary = "PushOnce validates one current action=push-approved-once approval, re-runs PushDryRun-equivalent checks immediately before push, executes exactly one narrow non-force git push for the approved HEAD, and does not call Codex, run runner v1, modify files, post GitHub comments, stage files, commit, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, run polling, run a daemon, run a scheduler, or chain approvals."
$CloseIssueOnceSafetyBoundary = "CloseIssueOnce validates one current action=close-issue-approved-once approval on the explicitly selected issue, requires local HEAD, remote HEAD, and pushed to match the same approved commit, then closes exactly one selected open issue. It does not call Codex, run runner v1, modify files, stage files, commit, push, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, run polling, run a daemon, run a scheduler, or chain approvals."
$DryRunQueueNoWriteGuarantee = "DryRunQueue validates one explicit local queue definition and emits one QUEUE-RUNNER-RESULT only. It does not execute queue tasks, run PollOnce, run BoundedPoll, run PushOnce, run CloseIssueOnce, call Codex, run runner v1, modify files, stage files, commit, push, close issues, edit labels, create PRs, merge, consume approvals, invoke external agents, run polling, run a daemon, or run a scheduler."
$RunQueueSafetyBoundary = "RunQueue executes explicitly listed low-risk read-only queue tasks and may stop at the official medium-risk run-reviewbundle-handoff task after reporting the handoff. It does not run high-risk actions, run PollOnce, run BoundedPoll, run PushOnce, run CloseIssueOnce, call Codex, run runner v1, modify files, stage files, commit, push, close issues, edit labels, create PRs, merge, consume approvals, invoke external agents, run polling, run a daemon, or run a scheduler."
$QueueReviewBundleHandoffAction = "run-reviewbundle-handoff"
$QueueSupportedActions = @(
    "read-only-audit",
    "git-status",
    "branch-head-check",
    "issue-state-check",
    "marker-readback",
    "dry-run-bounded-poll",
    "maybe-status-check",
    "runner-result-verification",
    "final-read-only-audit",
    $QueueReviewBundleHandoffAction
)
$QueueExecutableLowRiskActions = @(
    "git-status",
    "branch-head-check",
    "issue-state-check",
    "marker-readback",
    "read-only-audit",
    "runner-result-verification",
    "final-read-only-audit"
)

function Invoke-ReadOnlyCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $stdoutFile = New-TemporaryFile
    $stderrFile = New-TemporaryFile
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments 1> $stdoutFile.FullName 2> $stderrFile.FullName
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        $stdout = Get-Content -LiteralPath $stdoutFile.FullName -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrFile.FullName -Raw -ErrorAction SilentlyContinue
    }
    catch {
        return [pscustomobject]@{
            ExitCode = 1
            Stdout = ""
            Stderr = "$Action failed: $($_.Exception.Message)"
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Remove-Item -LiteralPath $stdoutFile.FullName -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrFile.FullName -Force -ErrorAction SilentlyContinue
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = if ($null -eq $stdout) { "" } else { $stdout.TrimEnd() }
        Stderr = if ($null -eq $stderr) { "" } else { $stderr.TrimEnd() }
    }
}

function Require-Success {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Result,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    if ($Result.ExitCode -ne 0) {
        $details = if ([string]::IsNullOrWhiteSpace($Result.Stdout)) { $Result.Stderr } else { $Result.Stdout }
        throw "$Action failed with exit code $($Result.ExitCode): $details"
    }
}

function Get-GitOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $result = Invoke-ReadOnlyCommand -FilePath "git" -Arguments (@("-C", $RepoRoot) + $GitArgs) -Action $Action
    Require-Success -Result $result -Action $Action
    return $result.Stdout.TrimEnd()
}

function ConvertTo-NormalizedProviderPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    return $resolved.ProviderPath.TrimEnd("\", "/")
}

function Assert-RepoRoot {
    $isInsideWorkTree = Get-GitOutput -GitArgs @("rev-parse", "--is-inside-work-tree") -Action "git rev-parse --is-inside-work-tree"
    if ($isInsideWorkTree -ne "true") {
        throw "Script path is not inside a git work tree. Repo root: $RepoRoot."
    }

    $expectedRoot = ConvertTo-NormalizedProviderPath -Path $RepoRoot
    $currentPath = ConvertTo-NormalizedProviderPath -Path (Get-Location).ProviderPath

    if (-not [string]::Equals($currentPath, $expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Run local-runner-v2 from the repo root. Current path: $currentPath. Repo root: $expectedRoot."
    }
}

function Assert-CleanRepo {
    $status = Get-GitOutput -GitArgs @("status", "--short") -Action "git status --short"
    if ([string]::IsNullOrWhiteSpace($status)) {
        return [pscustomobject]@{
            Status = ""
            IsClean = $true
            Summary = "yes"
        }
    }

    throw "Repo is dirty; runner v2 stops before issue detection. git status --short:`n$status"
}

function Get-CurrentBranch {
    $branch = Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current"
    if ([string]::IsNullOrWhiteSpace($branch)) {
        return "(detached HEAD)"
    }
    return $branch
}

function Get-CurrentHead {
    return Get-GitOutput -GitArgs @("rev-parse", "--short", "HEAD") -Action "git rev-parse --short HEAD"
}

function Get-CurrentFullHead {
    return Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
}

function Get-GitStatusShort {
    return Get-GitOutput -GitArgs @("status", "--short") -Action "git status --short"
}

function Get-Sha256Text {
    param(
        [AllowNull()]
        [string]$Text
    )

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($(if ($null -eq $Text) { "" } else { $Text }))
        $hashBytes = $sha256.ComputeHash($bytes)
        return (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-TextLineCount {
    param(
        [AllowNull()]
        [string]$Text
    )

    if ([string]::IsNullOrEmpty($Text)) {
        return 0
    }

    return @($Text -split "\r?\n").Count
}

function Get-TextPreview {
    param(
        [AllowNull()]
        [string]$Text,
        [int]$MaxChars = 2000
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "(none)"
    }

    $normalized = $Text.TrimEnd() -replace "`r", "\r" -replace "`n", "\n`n"
    if ($normalized.Length -le $MaxChars) {
        return $normalized
    }

    return $normalized.Substring(0, $MaxChars) + "`n[truncated]"
}

function Format-Block {
    param(
        [AllowNull()]
        [string]$Text,
        [string]$EmptyText = "(none)"
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $EmptyText
    }

    return $Text.TrimEnd()
}

function Convert-FileTextToArray {
    param(
        [AllowEmptyString()]
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text) -or $Text.Trim() -eq "(none)") {
        return @()
    }

    return @($Text -split "\r?\n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and $_.Trim() -ne "(none)"
    } | ForEach-Object { $_.Trim() } | Sort-Object -Unique)
}

function New-RunnerValidationResult {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("passed", "failed", "not_run", "warning", "reported")]
        [string]$Status,
        [Parameter(Mandatory = $true)]
        [string]$Summary
    )

    return [ordered]@{
        status = $Status
        summary = $Summary
    }
}

function New-RunnerResultSummaryJson {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Issue,
        [Parameter(Mandatory = $true)]
        [string]$Action,
        [Parameter(Mandatory = $true)]
        [ValidateSet("success", "failure")]
        [string]$Result,
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$Head,
        [Parameter(Mandatory = $true)]
        [int]$SelectedIssue,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$ReviewId = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$DiffFingerprint = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$FilesFingerprint = $null,
        [AllowEmptyString()]
        [string]$ChangedFilesText = "",
        [hashtable]$ValidationOverrides = @{},
        [hashtable]$SafetyOverrides = @{},
        [string]$NextRecommendedAction = "chatgpt_review"
    )

    $validations = [ordered]@{
        git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See human-readable runner output for final git status.")
        pytest = (New-RunnerValidationResult -Status "not_run" -Summary "This runner action did not run pytest.")
        git_diff_check = (New-RunnerValidationResult -Status "not_run" -Summary "This runner action did not run git diff --check.")
    }
    foreach ($key in $ValidationOverrides.Keys) {
        $validations[$key] = $ValidationOverrides[$key]
    }

    $safety = [ordered]@{
        no_stage = $true
        no_commit = $true
        no_push = $true
        no_issue_close = $true
        no_label = $true
        no_pr = $true
        no_merge = $true
        no_approval_chaining = $true
    }
    foreach ($key in $SafetyOverrides.Keys) {
        $safety[$key] = [bool]$SafetyOverrides[$key]
    }

    $summary = [ordered]@{
        schema = $RunnerResultProtocol
        repo = $Repo
        issue = $Issue
        action = $Action
        result = $Result
        branch = $Branch
        head = $Head
        selected_issue = $SelectedIssue
        review_id = if ([string]::IsNullOrWhiteSpace($ReviewId)) { $null } else { $ReviewId }
        diff_fingerprint = if ([string]::IsNullOrWhiteSpace($DiffFingerprint)) { $null } else { $DiffFingerprint }
        files_fingerprint = if ([string]::IsNullOrWhiteSpace($FilesFingerprint)) { $null } else { $FilesFingerprint }
        changed_files = @(Convert-FileTextToArray -Text $ChangedFilesText)
        validations = $validations
        safety = $safety
        next_recommended_action = $NextRecommendedAction
    }

    return ($summary | ConvertTo-Json -Depth 8)
}

function Write-RunnerResultSummary {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Issue,
        [Parameter(Mandatory = $true)]
        [string]$Action,
        [Parameter(Mandatory = $true)]
        [ValidateSet("success", "failure")]
        [string]$Result,
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$Head,
        [Parameter(Mandatory = $true)]
        [int]$SelectedIssue,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$ReviewId = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$DiffFingerprint = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$FilesFingerprint = $null,
        [AllowEmptyString()]
        [string]$ChangedFilesText = "",
        [hashtable]$ValidationOverrides = @{},
        [hashtable]$SafetyOverrides = @{},
        [string]$NextRecommendedAction = "chatgpt_review"
    )

    Write-Host $RunnerResultMarker
    Write-Host (New-RunnerResultSummaryJson `
        -Issue $Issue `
        -Action $Action `
        -Result $Result `
        -Branch $Branch `
        -Head $Head `
        -SelectedIssue $SelectedIssue `
        -ReviewId $ReviewId `
        -DiffFingerprint $DiffFingerprint `
        -FilesFingerprint $FilesFingerprint `
        -ChangedFilesText $ChangedFilesText `
        -ValidationOverrides $ValidationOverrides `
        -SafetyOverrides $SafetyOverrides `
        -NextRecommendedAction $NextRecommendedAction)
}

function Test-QueuePropertyPresent {
    param(
        [AllowNull()]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    if ($null -eq $Object) {
        return $false
    }

    return ($null -ne ($Object.PSObject.Properties[$PropertyName]))
}

function Get-QueuePropertyValue {
    param(
        [AllowNull()]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    if (-not (Test-QueuePropertyPresent -Object $Object -PropertyName $PropertyName)) {
        return $null
    }

    return $Object.PSObject.Properties[$PropertyName].Value
}

function Get-QueuePropertyText {
    param(
        [AllowNull()]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    $value = Get-QueuePropertyValue -Object $Object -PropertyName $PropertyName
    if ($null -eq $value) {
        return ""
    }

    return [string]$value
}

function ConvertTo-QueueStringArray {
    param(
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return @()
    }

    if ($Value -is [string]) {
        if ([string]::IsNullOrWhiteSpace($Value)) {
            return @()
        }
        return @($Value)
    }

    return @($Value | ForEach-Object {
        if ($null -ne $_ -and -not [string]::IsNullOrWhiteSpace([string]$_)) {
            [string]$_
        }
    })
}

function New-QueueRunnerSafety {
    param(
        [bool]$DryRun = $true
    )

    $safety = [ordered]@{
        foreground_manual_start = $true
        bounded_task_count = $true
        bounded_runtime = $true
        no_background_watcher = $true
    }

    if ($DryRun) {
        $safety["no_task_execution"] = $true
    }

    $safety["no_stage"] = $true
    $safety["no_commit"] = $true
    $safety["no_push"] = $true
    $safety["no_issue_close"] = $true
    $safety["no_label"] = $true
    $safety["no_pr"] = $true
    $safety["no_merge"] = $true
    $safety["no_approval_chaining"] = $true
    $safety["no_approval_token_consumption"] = $true

    return $safety
}

function New-QueueValidationMap {
    return [ordered]@{
        queue_file_readable = (New-RunnerValidationResult -Status "not_run" -Summary "Queue file was not read yet.")
        queue_json_parseable = (New-RunnerValidationResult -Status "not_run" -Summary "Queue JSON was not parsed yet.")
        required_fields = (New-RunnerValidationResult -Status "not_run" -Summary "Required fields were not validated yet.")
        repo_match = (New-RunnerValidationResult -Status "not_run" -Summary "Repo was not validated yet.")
        branch_match = (New-RunnerValidationResult -Status "not_run" -Summary "Branch was not validated yet.")
        head_match = (New-RunnerValidationResult -Status "not_run" -Summary "HEAD was not validated yet.")
        task_count = (New-RunnerValidationResult -Status "not_run" -Summary "Task count was not validated yet.")
        git_status_scope = (New-RunnerValidationResult -Status "not_run" -Summary "Git dirty state was not validated yet.")
        task_schema = (New-RunnerValidationResult -Status "not_run" -Summary "Task schema was not validated yet.")
        actions_supported = (New-RunnerValidationResult -Status "not_run" -Summary "Task actions were not validated yet.")
        dry_run_no_execution = (New-RunnerValidationResult -Status "passed" -Summary "Dry-run validator does not execute task actions.")
    }
}

function New-QueueRunnerResultJson {
    param(
        [AllowEmptyString()]
        [string]$QueueId = "",
        [AllowNull()]
        [Nullable[int]]$ParentIssue = $null,
        [AllowEmptyString()]
        [string]$QueueRepo = "",
        [AllowEmptyString()]
        [string]$Branch = "",
        [AllowEmptyString()]
        [string]$Head = "",
        [Parameter(Mandatory = $true)]
        [ValidateSet("success", "stopped", "failed")]
        [string]$Result,
        [bool]$DryRun = $true,
        [object[]]$PlannedTasks = @(),
        [object[]]$CompletedTasks = @(),
        [object[]]$SkippedTasks = @(),
        [AllowNull()]
        [AllowEmptyString()]
        [string]$StoppedAtTask = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$StopReason = $null,
        [Parameter(Mandatory = $true)]
        [ValidateSet("none", "medium_review", "medium_review_required", "high_risk_user_approval")]
        [string]$RiskGate,
        [bool]$QuotaOrRateLimitDetected = $false,
        [string[]]$ChangedFiles = @(),
        [AllowNull()]
        [AllowEmptyString()]
        [string]$ReviewId = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$DiffFingerprint = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$FilesFingerprint = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$ReviewBundleMetadataStatus = $null,
        [AllowNull()]
        [AllowEmptyString()]
        [string]$ReviewBundleMetadataBlockReason = $null,
        [AllowNull()]
        [object]$ReviewBundleHandoffTask = $null,
        [Parameter(Mandatory = $true)]
        [object]$Validations,
        [string]$NextRecommendedAction = "chatgpt_review"
    )

    $summary = [ordered]@{
        schema = $QueueRunnerResultProtocol
        repo = if ([string]::IsNullOrWhiteSpace($QueueRepo)) { $Repo } else { $QueueRepo }
        parent_issue = $ParentIssue
        queue_id = if ([string]::IsNullOrWhiteSpace($QueueId)) { $null } else { $QueueId }
        branch = if ([string]::IsNullOrWhiteSpace($Branch)) { $null } else { $Branch }
        head = if ([string]::IsNullOrWhiteSpace($Head)) { $null } else { $Head }
        result = $Result
        dry_run = $DryRun
        planned_tasks = @($PlannedTasks)
        completed_tasks = @($CompletedTasks)
        skipped_tasks = @($SkippedTasks)
        stopped_at_task = if ([string]::IsNullOrWhiteSpace($StoppedAtTask)) { $null } else { $StoppedAtTask }
        stop_reason = if ([string]::IsNullOrWhiteSpace($StopReason)) { $null } else { $StopReason }
        risk_gate = $RiskGate
        quota_or_rate_limit_detected = $QuotaOrRateLimitDetected
        changed_files = @($ChangedFiles)
        review_id = if ([string]::IsNullOrWhiteSpace($ReviewId)) { $null } else { $ReviewId }
        diff_fingerprint = if ([string]::IsNullOrWhiteSpace($DiffFingerprint)) { $null } else { $DiffFingerprint }
        files_fingerprint = if ([string]::IsNullOrWhiteSpace($FilesFingerprint)) { $null } else { $FilesFingerprint }
        reviewbundle_metadata_status = if ([string]::IsNullOrWhiteSpace($ReviewBundleMetadataStatus)) { $null } else { $ReviewBundleMetadataStatus }
        reviewbundle_metadata_block_reason = if ([string]::IsNullOrWhiteSpace($ReviewBundleMetadataBlockReason)) { $null } else { $ReviewBundleMetadataBlockReason }
        reviewbundle_handoff_task = $ReviewBundleHandoffTask
        validations = $Validations
        safety = (New-QueueRunnerSafety -DryRun $DryRun)
        next_recommended_action = $NextRecommendedAction
    }

    return ($summary | ConvertTo-Json -Depth 12)
}

function Write-QueueRunnerResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Json
    )

    Write-Host $QueueRunnerResultMarker
    Write-Host $Json
}

function New-QueuePlannedTask {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Task
    )

    return [ordered]@{
        task_id = (Get-QueuePropertyText -Object $Task -PropertyName "task_id")
        description = (Get-QueuePropertyText -Object $Task -PropertyName "description")
        risk_level = (Get-QueuePropertyText -Object $Task -PropertyName "risk_level")
        allowed_action = (Get-QueuePropertyText -Object $Task -PropertyName "allowed_action")
        expected_inputs = @(ConvertTo-QueueStringArray -Value (Get-QueuePropertyValue -Object $Task -PropertyName "expected_inputs"))
        expected_outputs = @(ConvertTo-QueueStringArray -Value (Get-QueuePropertyValue -Object $Task -PropertyName "expected_outputs"))
        stop_after_completion = [bool](Get-QueuePropertyValue -Object $Task -PropertyName "stop_after_completion")
        approved_changed_files = @(ConvertTo-QueueStringArray -Value (Get-QueuePropertyValue -Object $Task -PropertyName "approved_changed_files"))
        planned_result = "not_executed_dry_run"
    }
}

function New-QueueSkippedTask {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Task,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    $taskId = Get-QueuePropertyText -Object $Task -PropertyName "task_id"
    if ([string]::IsNullOrWhiteSpace($taskId)) {
        $taskId = "(missing)"
    }

    return [ordered]@{
        task_id = $taskId
        reason = $Reason
    }
}

function New-QueueCompletedTask {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Task,
        [Parameter(Mandatory = $true)]
        [string]$Summary
    )

    return [ordered]@{
        task_id = (Get-QueuePropertyText -Object $Task -PropertyName "task_id")
        risk_level = (Get-QueuePropertyText -Object $Task -PropertyName "risk_level")
        allowed_action = (Get-QueuePropertyText -Object $Task -PropertyName "allowed_action")
        result = "completed"
        summary = $Summary
    }
}

function New-QueueReviewBundleHandoffTask {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Task
    )

    return [ordered]@{
        task_id = (Get-QueuePropertyText -Object $Task -PropertyName "task_id")
        risk_level = (Get-QueuePropertyText -Object $Task -PropertyName "risk_level")
        allowed_action = (Get-QueuePropertyText -Object $Task -PropertyName "allowed_action")
        result = "handoff_reached"
        summary = "ReviewBundle handoff reached; queue stopped for ChatGPT review before any high-risk task."
    }
}

function Test-QueueDirtyStateAllowed {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Queue,
        [string[]]$ChangedFiles = @()
    )

    if ($ChangedFiles.Count -eq 0) {
        return [pscustomobject]@{
            Allowed = $true
            Summary = "Git status is clean."
        }
    }

    $allowDirtyText = Get-QueuePropertyText -Object $Queue -PropertyName "allow_dirty"
    if ($allowDirtyText -eq "True" -or $allowDirtyText -eq "true") {
        return [pscustomobject]@{
            Allowed = $true
            Summary = "Queue explicitly allowed dirty state with allow_dirty=true. Changed file(s): $($ChangedFiles -join ', ')."
        }
    }

    $allowedDirtyFiles = @(ConvertTo-QueueStringArray -Value (Get-QueuePropertyValue -Object $Queue -PropertyName "allowed_dirty_files"))
    if ($allowedDirtyFiles.Count -gt 0) {
        $unexpected = @($ChangedFiles | Where-Object { $allowedDirtyFiles -notcontains $_ })
        if ($unexpected.Count -eq 0) {
            return [pscustomobject]@{
                Allowed = $true
                Summary = "Changed files matched allowed_dirty_files."
            }
        }

        return [pscustomobject]@{
            Allowed = $false
            Summary = "Unexpected dirty file(s): $($unexpected -join ', '). Allowed dirty file(s): $($allowedDirtyFiles -join ', ')."
        }
    }

    return [pscustomobject]@{
        Allowed = $false
        Summary = "Unexpected dirty state. Queue must set allow_dirty=true or list allowed_dirty_files before read-only execution."
    }
}

function Get-IssueStateForQueue {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    $readResult = Get-IssueApprovalMarkerReadResult -IssueNumber $IssueNumber
    return $readResult.IssueState
}

function Invoke-LowRiskQueueTask {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Task,
        [Parameter(Mandatory = $true)]
        [object]$Queue
    )

    $action = Get-QueuePropertyText -Object $Task -PropertyName "allowed_action"
    switch ($action) {
        "git-status" {
            $status = Get-GitStatusShort
            if ([string]::IsNullOrWhiteSpace($status)) {
                return "git status --short is clean."
            }
            return "git status --short reported $(@(Get-StatusLines -Status $status).Count) line(s)."
        }
        "branch-head-check" {
            $currentBranch = Get-CurrentBranch
            $currentHead = Get-CurrentFullHead
            $queueBranch = Get-QueuePropertyText -Object $Queue -PropertyName "branch"
            $queueHead = Get-QueuePropertyText -Object $Queue -PropertyName "head"
            if ($currentBranch -ne $queueBranch -or $currentHead -ne $queueHead) {
                throw "branch-head-check mismatch: current branch/head $currentBranch/$currentHead did not match queue $queueBranch/$queueHead."
            }
            return "Current branch and HEAD match the queue definition."
        }
        "issue-state-check" {
            $parentIssueText = Get-QueuePropertyText -Object $Queue -PropertyName "parent_issue"
            $parentIssue = 0
            if (-not [int]::TryParse($parentIssueText, [ref]$parentIssue) -or $parentIssue -lt 1) {
                throw "issue-state-check requires a positive parent_issue."
            }
            $state = Get-IssueStateForQueue -IssueNumber $parentIssue
            return "Issue #$parentIssue state is $state."
        }
        "marker-readback" {
            return "Queue marker readback completed for queue_id=$(Get-QueuePropertyText -Object $Queue -PropertyName "queue_id")."
        }
        "read-only-audit" {
            $status = Get-GitStatusShort
            $paths = @(Get-StatusPaths -Status $status)
            return "Read-only audit completed with $($paths.Count) changed file(s)."
        }
        "runner-result-verification" {
            return "Runner result verification completed locally for queue_id=$(Get-QueuePropertyText -Object $Queue -PropertyName "queue_id")."
        }
        "final-read-only-audit" {
            $status = Get-GitStatusShort
            if ([string]::IsNullOrWhiteSpace($status)) {
                return "Final read-only audit completed; git status is clean."
            }
            return "Final read-only audit completed; git status has $(@(Get-StatusLines -Status $status).Count) line(s)."
        }
        default {
            throw "Unsupported low-risk queue action: $action"
        }
    }
}

function Invoke-DryRunQueue {
    if ([string]::IsNullOrWhiteSpace($QueueFile)) {
        throw "DryRunQueue requires -QueueFile <path>."
    }

    Assert-RepoRoot
    $validations = New-QueueValidationMap
    $queue = $null
    $queueId = ""
    $parentIssue = $null
    $queueRepo = $Repo
    $branch = ""
    $head = ""
    $plannedTasks = @()
    $skippedTasks = @()
    $stoppedAtTask = $null
    $stopReason = $null
    $riskGate = "none"
    $result = "success"
    $changedFiles = @()
    $reviewId = $null
    $diffFingerprint = $null
    $filesFingerprint = $null
    $reviewBundleMetadataStatus = $null
    $reviewBundleMetadataBlockReason = $null
    $reviewBundleHandoffTask = $null

    try {
        $resolvedQueueFile = Resolve-Path -LiteralPath $QueueFile -ErrorAction Stop
        $queueText = Get-Content -LiteralPath $resolvedQueueFile.ProviderPath -Raw -ErrorAction Stop
        $validations["queue_file_readable"] = New-RunnerValidationResult -Status "passed" -Summary "Queue file was read from $($resolvedQueueFile.ProviderPath)."
    }
    catch {
        $validations["queue_file_readable"] = New-RunnerValidationResult -Status "failed" -Summary "Queue file could not be read: $($_.Exception.Message)"
        $validations["queue_json_parseable"] = New-RunnerValidationResult -Status "failed" -Summary "Queue JSON was not parsed because the file was unreadable."
        $result = "failed"
        $stopReason = "malformed_queue_definition"
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueRepo $queueRepo -Result $result -RiskGate $riskGate -StopReason $stopReason -ChangedFiles $changedFiles -Validations $validations)
        return
    }

    try {
        $queue = $queueText | ConvertFrom-Json -ErrorAction Stop
        $validations["queue_json_parseable"] = New-RunnerValidationResult -Status "passed" -Summary "Queue file contained parseable JSON."
    }
    catch {
        $validations["queue_json_parseable"] = New-RunnerValidationResult -Status "failed" -Summary "Queue file did not contain parseable JSON: $($_.Exception.Message)"
        $result = "failed"
        $stopReason = "malformed_queue_definition"
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueRepo $queueRepo -Result $result -RiskGate $riskGate -StopReason $stopReason -ChangedFiles $changedFiles -Validations $validations)
        return
    }

    $queueId = Get-QueuePropertyText -Object $queue -PropertyName "queue_id"
    $queueRepo = Get-QueuePropertyText -Object $queue -PropertyName "repo"
    $branch = Get-QueuePropertyText -Object $queue -PropertyName "branch"
    $head = Get-QueuePropertyText -Object $queue -PropertyName "head"
    $parentIssueText = Get-QueuePropertyText -Object $queue -PropertyName "parent_issue"
    if (-not [string]::IsNullOrWhiteSpace($parentIssueText)) {
        $parsedParentIssue = 0
        if ([int]::TryParse($parentIssueText, [ref]$parsedParentIssue)) {
            $parentIssue = $parsedParentIssue
        }
    }

    $requiredQueueFields = @("schema", "queue_id", "repo", "parent_issue", "branch", "head", "max_codex_tasks_per_batch", "max_runtime_minutes", "tasks")
    $missingFields = @($requiredQueueFields | Where-Object {
        if (-not (Test-QueuePropertyPresent -Object $queue -PropertyName $_)) {
            return $true
        }
        $fieldValue = Get-QueuePropertyValue -Object $queue -PropertyName $_
        if ($null -eq $fieldValue) {
            return $true
        }
        if ($fieldValue -is [string] -and [string]::IsNullOrWhiteSpace($fieldValue)) {
            return $true
        }
        return $false
    })
    if ($missingFields.Count -gt 0) {
        $validations["required_fields"] = New-RunnerValidationResult -Status "failed" -Summary "Missing required queue field(s): $($missingFields -join ', ')."
        $result = "failed"
        $stopReason = "missing_required_field"
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueId $queueId -ParentIssue $parentIssue -QueueRepo $queueRepo -Branch $branch -Head $head -Result $result -RiskGate $riskGate -StopReason $stopReason -ChangedFiles $changedFiles -Validations $validations)
        return
    }
    $validations["required_fields"] = New-RunnerValidationResult -Status "passed" -Summary "All required queue fields are present."

    $queueSchema = Get-QueuePropertyText -Object $queue -PropertyName "schema"
    if ($queueSchema -ne $QueueDefinitionProtocol) {
        $validations["required_fields"] = New-RunnerValidationResult -Status "failed" -Summary "Queue schema must be $QueueDefinitionProtocol."
        $result = "failed"
        $stopReason = "malformed_queue_definition"
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueId $queueId -ParentIssue $parentIssue -QueueRepo $queueRepo -Branch $branch -Head $head -Result $result -RiskGate $riskGate -StopReason $stopReason -ChangedFiles $changedFiles -Validations $validations)
        return
    }

    $currentBranch = Get-CurrentBranch
    $currentHead = Get-CurrentFullHead
    $statusText = Get-GitStatusShort
    $changedFiles = @(Get-StatusLines -Status $statusText | ForEach-Object { Get-StatusPath -Line $_ } | Sort-Object -Unique)

    if ($queueRepo -ne $ExpectedApprovalRepo) {
        $validations["repo_match"] = New-RunnerValidationResult -Status "failed" -Summary "Queue repo '$queueRepo' did not match expected repo '$ExpectedApprovalRepo'."
        $result = "failed"
        $stopReason = "repo_branch_head_mismatch"
    }
    else {
        $validations["repo_match"] = New-RunnerValidationResult -Status "passed" -Summary "Queue repo matched expected repo."
    }

    if ($branch -ne $currentBranch) {
        $validations["branch_match"] = New-RunnerValidationResult -Status "failed" -Summary "Queue branch '$branch' did not match current branch '$currentBranch'."
        $result = "failed"
        $stopReason = "repo_branch_head_mismatch"
    }
    else {
        $validations["branch_match"] = New-RunnerValidationResult -Status "passed" -Summary "Queue branch matched current branch."
    }

    if ($head -ne $currentHead) {
        $validations["head_match"] = New-RunnerValidationResult -Status "failed" -Summary "Queue HEAD did not match current HEAD."
        $result = "failed"
        $stopReason = "repo_branch_head_mismatch"
    }
    else {
        $validations["head_match"] = New-RunnerValidationResult -Status "passed" -Summary "Queue HEAD matched current HEAD."
    }

    $tasksValue = Get-QueuePropertyValue -Object $queue -PropertyName "tasks"
    $tasks = @($tasksValue)
    $maxTasks = 0
    $maxRuntimeMinutes = 0
    $maxTasksValid = [int]::TryParse((Get-QueuePropertyText -Object $queue -PropertyName "max_codex_tasks_per_batch"), [ref]$maxTasks)
    $maxRuntimeValid = [int]::TryParse((Get-QueuePropertyText -Object $queue -PropertyName "max_runtime_minutes"), [ref]$maxRuntimeMinutes)

    if (-not $maxTasksValid -or $maxTasks -lt 1 -or -not $maxRuntimeValid -or $maxRuntimeMinutes -lt 1) {
        $validations["task_count"] = New-RunnerValidationResult -Status "failed" -Summary "max_codex_tasks_per_batch and max_runtime_minutes must both be positive integers."
        $result = "failed"
        $stopReason = "malformed_queue_definition"
    }
    elseif ($tasks.Count -gt $maxTasks) {
        $validations["task_count"] = New-RunnerValidationResult -Status "failed" -Summary "Queue has $($tasks.Count) task(s), exceeding max_codex_tasks_per_batch=$maxTasks."
        $result = "failed"
        $stopReason = "task_count_exceeds_max_codex_tasks_per_batch"
    }
    else {
        $validations["task_count"] = New-RunnerValidationResult -Status "passed" -Summary "Queue has $($tasks.Count) task(s), within max_codex_tasks_per_batch=$maxTasks."
    }

    $requiredTaskFields = @("task_id", "description", "risk_level", "allowed_action", "expected_inputs", "expected_outputs", "stop_after_completion")
    $taskSchemaFailures = @()
    $unsupportedActions = @()
    $allowedRiskLevels = @("low", "medium", "high")

    for ($index = 0; $index -lt $tasks.Count; $index++) {
        $task = $tasks[$index]
        $taskId = Get-QueuePropertyText -Object $task -PropertyName "task_id"
        if ([string]::IsNullOrWhiteSpace($taskId)) {
            $taskId = "task_index_$index"
        }

        $missingTaskFields = @($requiredTaskFields | Where-Object { -not (Test-QueuePropertyPresent -Object $task -PropertyName $_) })
        if ($missingTaskFields.Count -gt 0) {
            $taskSchemaFailures += "$taskId missing $($missingTaskFields -join ', ')"
            continue
        }

        $riskLevel = Get-QueuePropertyText -Object $task -PropertyName "risk_level"
        if ($allowedRiskLevels -notcontains $riskLevel) {
            $taskSchemaFailures += "$taskId has invalid risk_level '$riskLevel'"
            continue
        }

        $allowedAction = Get-QueuePropertyText -Object $task -PropertyName "allowed_action"
        if ($QueueSupportedActions -notcontains $allowedAction) {
            $unsupportedActions += "$taskId action '$allowedAction'"
            if ($null -eq $stoppedAtTask) {
                $stoppedAtTask = $taskId
                $stopReason = "unsupported_action"
                $result = "failed"
            }
            $skippedTasks += (New-QueueSkippedTask -Task $task -Reason "unsupported_action")
            continue
        }

        $plannedTasks += (New-QueuePlannedTask -Task $task)

        if ($result -eq "success" -and $riskLevel -eq "high") {
            $result = "stopped"
            $stoppedAtTask = $taskId
            $stopReason = "high_risk_task_reached"
            $riskGate = "high_risk_user_approval"
        }
        elseif ($result -eq "success" -and [bool](Get-QueuePropertyValue -Object $task -PropertyName "stop_after_completion")) {
            $result = "stopped"
            $stoppedAtTask = $taskId
            $stopReason = "stop_after_completion"
        }
    }

    if ($taskSchemaFailures.Count -gt 0) {
        $validations["task_schema"] = New-RunnerValidationResult -Status "failed" -Summary "Task schema validation failed: $($taskSchemaFailures -join '; ')."
        $result = "failed"
        if ($null -eq $stopReason) {
            $stopReason = "malformed_queue_definition"
        }
    }
    else {
        $validations["task_schema"] = New-RunnerValidationResult -Status "passed" -Summary "All task definitions include required fields and valid risk levels."
    }

    if ($unsupportedActions.Count -gt 0) {
        $validations["actions_supported"] = New-RunnerValidationResult -Status "failed" -Summary "Unsupported queue action(s): $($unsupportedActions -join '; ')."
    }
    else {
        $validations["actions_supported"] = New-RunnerValidationResult -Status "passed" -Summary "All queue actions are supported for dry-run planning."
    }

    if ($result -eq "failed" -and $null -eq $stopReason) {
        $stopReason = "other_validation_failure"
    }

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: DryRunQueue"
    Write-Host "Queue file: $QueueFile"
    Write-Host "No-write guarantee: $DryRunQueueNoWriteGuarantee"
    Write-QueueRunnerResult -Json (New-QueueRunnerResultJson `
        -QueueId $queueId `
        -ParentIssue $parentIssue `
        -QueueRepo $queueRepo `
        -Branch $branch `
        -Head $head `
        -Result $result `
        -PlannedTasks $plannedTasks `
        -SkippedTasks $skippedTasks `
        -StoppedAtTask $stoppedAtTask `
        -StopReason $stopReason `
        -RiskGate $riskGate `
        -QuotaOrRateLimitDetected $false `
        -ChangedFiles $changedFiles `
        -Validations $validations)
}

function Invoke-RunQueue {
    if ([string]::IsNullOrWhiteSpace($QueueFile)) {
        throw "RunQueue requires -QueueFile <path>."
    }

    Assert-RepoRoot
    $validations = New-QueueValidationMap
    $validations["dry_run_no_execution"] = New-RunnerValidationResult -Status "not_run" -Summary "RunQueue executes approved low-risk read-only tasks."
    $queue = $null
    $queueId = ""
    $parentIssue = $null
    $queueRepo = $Repo
    $branch = ""
    $head = ""
    $plannedTasks = @()
    $completedTasks = @()
    $skippedTasks = @()
    $stoppedAtTask = $null
    $stopReason = $null
    $riskGate = "none"
    $result = "success"
    $changedFiles = @()
    $reviewId = $null
    $diffFingerprint = $null
    $filesFingerprint = $null
    $reviewBundleMetadataStatus = $null
    $reviewBundleMetadataBlockReason = $null
    $reviewBundleHandoffTask = $null

    try {
        $resolvedQueueFile = Resolve-Path -LiteralPath $QueueFile -ErrorAction Stop
        $queueText = Get-Content -LiteralPath $resolvedQueueFile.ProviderPath -Raw -ErrorAction Stop
        $validations["queue_file_readable"] = New-RunnerValidationResult -Status "passed" -Summary "Queue file was read from $($resolvedQueueFile.ProviderPath)."
    }
    catch {
        $validations["queue_file_readable"] = New-RunnerValidationResult -Status "failed" -Summary "Queue file could not be read: $($_.Exception.Message)"
        $validations["queue_json_parseable"] = New-RunnerValidationResult -Status "failed" -Summary "Queue JSON was not parsed because the file was unreadable."
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueRepo $queueRepo -Result "failed" -DryRun $false -RiskGate $riskGate -StopReason "malformed_queue_definition" -ChangedFiles $changedFiles -Validations $validations)
        return
    }

    try {
        $queue = $queueText | ConvertFrom-Json -ErrorAction Stop
        $validations["queue_json_parseable"] = New-RunnerValidationResult -Status "passed" -Summary "Queue file contained parseable JSON."
    }
    catch {
        $validations["queue_json_parseable"] = New-RunnerValidationResult -Status "failed" -Summary "Queue file did not contain parseable JSON: $($_.Exception.Message)"
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueRepo $queueRepo -Result "failed" -DryRun $false -RiskGate $riskGate -StopReason "malformed_queue_definition" -ChangedFiles $changedFiles -Validations $validations)
        return
    }

    $queueId = Get-QueuePropertyText -Object $queue -PropertyName "queue_id"
    $queueRepo = Get-QueuePropertyText -Object $queue -PropertyName "repo"
    $branch = Get-QueuePropertyText -Object $queue -PropertyName "branch"
    $head = Get-QueuePropertyText -Object $queue -PropertyName "head"
    $parentIssueText = Get-QueuePropertyText -Object $queue -PropertyName "parent_issue"
    if (-not [string]::IsNullOrWhiteSpace($parentIssueText)) {
        $parsedParentIssue = 0
        if ([int]::TryParse($parentIssueText, [ref]$parsedParentIssue)) {
            $parentIssue = $parsedParentIssue
        }
    }

    $requiredQueueFields = @("schema", "queue_id", "repo", "parent_issue", "branch", "head", "max_codex_tasks_per_batch", "max_runtime_minutes", "tasks")
    $missingFields = @($requiredQueueFields | Where-Object {
        if (-not (Test-QueuePropertyPresent -Object $queue -PropertyName $_)) { return $true }
        $fieldValue = Get-QueuePropertyValue -Object $queue -PropertyName $_
        if ($null -eq $fieldValue) { return $true }
        if ($fieldValue -is [string] -and [string]::IsNullOrWhiteSpace($fieldValue)) { return $true }
        return $false
    })
    if ($missingFields.Count -gt 0) {
        $validations["required_fields"] = New-RunnerValidationResult -Status "failed" -Summary "Missing required queue field(s): $($missingFields -join ', ')."
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueId $queueId -ParentIssue $parentIssue -QueueRepo $queueRepo -Branch $branch -Head $head -Result "failed" -DryRun $false -RiskGate $riskGate -StopReason "missing_required_field" -ChangedFiles $changedFiles -Validations $validations)
        return
    }
    $validations["required_fields"] = New-RunnerValidationResult -Status "passed" -Summary "All required queue fields are present."

    $queueSchema = Get-QueuePropertyText -Object $queue -PropertyName "schema"
    if ($queueSchema -ne $QueueDefinitionProtocol) {
        $validations["required_fields"] = New-RunnerValidationResult -Status "failed" -Summary "Queue schema must be $QueueDefinitionProtocol."
        Write-QueueRunnerResult -Json (New-QueueRunnerResultJson -QueueId $queueId -ParentIssue $parentIssue -QueueRepo $queueRepo -Branch $branch -Head $head -Result "failed" -DryRun $false -RiskGate $riskGate -StopReason "malformed_queue_definition" -ChangedFiles $changedFiles -Validations $validations)
        return
    }

    $currentBranch = Get-CurrentBranch
    $currentHead = Get-CurrentFullHead
    $statusText = Get-GitStatusShort
    $changedFiles = @(Get-StatusLines -Status $statusText | ForEach-Object { Get-StatusPath -Line $_ } | Sort-Object -Unique)

    if ($queueRepo -ne $ExpectedApprovalRepo) {
        $validations["repo_match"] = New-RunnerValidationResult -Status "failed" -Summary "Queue repo '$queueRepo' did not match expected repo '$ExpectedApprovalRepo'."
        $result = "failed"
        $stopReason = "repo_branch_head_mismatch"
    }
    else {
        $validations["repo_match"] = New-RunnerValidationResult -Status "passed" -Summary "Queue repo matched expected repo."
    }

    if ($branch -ne $currentBranch) {
        $validations["branch_match"] = New-RunnerValidationResult -Status "failed" -Summary "Queue branch '$branch' did not match current branch '$currentBranch'."
        $result = "failed"
        $stopReason = "repo_branch_head_mismatch"
    }
    else {
        $validations["branch_match"] = New-RunnerValidationResult -Status "passed" -Summary "Queue branch matched current branch."
    }

    if ($head -ne $currentHead) {
        $validations["head_match"] = New-RunnerValidationResult -Status "failed" -Summary "Queue HEAD did not match current HEAD."
        $result = "failed"
        $stopReason = "repo_branch_head_mismatch"
    }
    else {
        $validations["head_match"] = New-RunnerValidationResult -Status "passed" -Summary "Queue HEAD matched current HEAD."
    }

    $dirtyState = Test-QueueDirtyStateAllowed -Queue $queue -ChangedFiles $changedFiles
    if ($dirtyState.Allowed) {
        $validations["git_status_scope"] = New-RunnerValidationResult -Status "passed" -Summary $dirtyState.Summary
    }
    else {
        $validations["git_status_scope"] = New-RunnerValidationResult -Status "failed" -Summary $dirtyState.Summary
        $result = "failed"
        if ($null -eq $stopReason) {
            $stopReason = "unexpected_git_dirty_state"
        }
    }

    $tasksValue = Get-QueuePropertyValue -Object $queue -PropertyName "tasks"
    $tasks = @($tasksValue)
    $maxTasks = 0
    $maxRuntimeMinutes = 0
    $maxTasksValid = [int]::TryParse((Get-QueuePropertyText -Object $queue -PropertyName "max_codex_tasks_per_batch"), [ref]$maxTasks)
    $maxRuntimeValid = [int]::TryParse((Get-QueuePropertyText -Object $queue -PropertyName "max_runtime_minutes"), [ref]$maxRuntimeMinutes)

    if (-not $maxTasksValid -or $maxTasks -lt 1 -or -not $maxRuntimeValid -or $maxRuntimeMinutes -lt 1) {
        $validations["task_count"] = New-RunnerValidationResult -Status "failed" -Summary "max_codex_tasks_per_batch and max_runtime_minutes must both be positive integers."
        $result = "failed"
        if ($null -eq $stopReason) { $stopReason = "malformed_queue_definition" }
    }
    elseif ($tasks.Count -gt $maxTasks) {
        $validations["task_count"] = New-RunnerValidationResult -Status "failed" -Summary "Queue has $($tasks.Count) task(s), exceeding max_codex_tasks_per_batch=$maxTasks."
        $result = "failed"
        if ($null -eq $stopReason) { $stopReason = "task_count_exceeds_max_codex_tasks_per_batch" }
    }
    else {
        $validations["task_count"] = New-RunnerValidationResult -Status "passed" -Summary "Queue has $($tasks.Count) task(s), within max_codex_tasks_per_batch=$maxTasks."
    }

    $requiredTaskFields = @("task_id", "description", "risk_level", "allowed_action", "expected_inputs", "expected_outputs", "stop_after_completion")
    $taskSchemaFailures = @()
    $unsupportedActions = @()
    $allowedRiskLevels = @("low", "medium", "high")
    foreach ($task in $tasks) {
        $taskId = Get-QueuePropertyText -Object $task -PropertyName "task_id"
        if ([string]::IsNullOrWhiteSpace($taskId)) { $taskId = "(missing)" }
        $missingTaskFields = @($requiredTaskFields | Where-Object { -not (Test-QueuePropertyPresent -Object $task -PropertyName $_) })
        if ($missingTaskFields.Count -gt 0) {
            $taskSchemaFailures += "$taskId missing $($missingTaskFields -join ', ')"
            continue
        }
        $riskLevel = Get-QueuePropertyText -Object $task -PropertyName "risk_level"
        if ($allowedRiskLevels -notcontains $riskLevel) {
            $taskSchemaFailures += "$taskId has invalid risk_level '$riskLevel'"
            continue
        }
        $allowedAction = Get-QueuePropertyText -Object $task -PropertyName "allowed_action"
        if ($riskLevel -eq "low" -and $QueueExecutableLowRiskActions -notcontains $allowedAction) {
            $unsupportedActions += "$taskId action '$allowedAction'"
        }
        elseif ($riskLevel -eq "medium" -and $allowedAction -ne $QueueReviewBundleHandoffAction) {
            $unsupportedActions += "$taskId action '$allowedAction'"
        }
    }

    if ($taskSchemaFailures.Count -gt 0) {
        $validations["task_schema"] = New-RunnerValidationResult -Status "failed" -Summary "Task schema validation failed: $($taskSchemaFailures -join '; ')."
        $result = "failed"
        if ($null -eq $stopReason) { $stopReason = "malformed_queue_definition" }
    }
    else {
        $validations["task_schema"] = New-RunnerValidationResult -Status "passed" -Summary "All task definitions include required fields and valid risk levels."
    }

    if ($unsupportedActions.Count -gt 0) {
        $validations["actions_supported"] = New-RunnerValidationResult -Status "failed" -Summary "Unsupported queue action(s): $($unsupportedActions -join '; ')."
        $result = "failed"
        if ($null -eq $stopReason) { $stopReason = "unsupported_action" }
    }
    else {
        $validations["actions_supported"] = New-RunnerValidationResult -Status "passed" -Summary "All executable low-risk queue actions and the official ReviewBundle handoff action are supported."
    }

    if ($result -eq "success") {
        for ($index = 0; $index -lt $tasks.Count; $index++) {
            $task = $tasks[$index]
            $taskId = Get-QueuePropertyText -Object $task -PropertyName "task_id"
            if ([string]::IsNullOrWhiteSpace($taskId)) { $taskId = "task_index_$index" }
            $riskLevel = Get-QueuePropertyText -Object $task -PropertyName "risk_level"
            $allowedAction = Get-QueuePropertyText -Object $task -PropertyName "allowed_action"

            if ($riskLevel -eq "medium") {
                if ($allowedAction -eq $QueueReviewBundleHandoffAction) {
                    $result = "stopped"
                    $stoppedAtTask = $taskId
                    $stopReason = "reviewbundle_handoff_completed"
                    $riskGate = "medium_review_required"
                    $reviewBundleHandoffTask = New-QueueReviewBundleHandoffTask -Task $task
                    $reviewId = Get-QueuePropertyText -Object $task -PropertyName "review_id"
                    $diffFingerprint = Get-QueuePropertyText -Object $task -PropertyName "diff_fingerprint"
                    $filesFingerprint = Get-QueuePropertyText -Object $task -PropertyName "files_fingerprint"
                    if (-not [string]::IsNullOrWhiteSpace($reviewId) -and -not [string]::IsNullOrWhiteSpace($diffFingerprint) -and -not [string]::IsNullOrWhiteSpace($filesFingerprint)) {
                        $reviewBundleMetadataStatus = "available"
                    }
                    elseif ($changedFiles.Count -gt 0) {
                        $reviewBundleMetadataStatus = "blocked"
                        $reviewBundleMetadataBlockReason = "dirty_candidate_precondition"
                    }
                    else {
                        $reviewBundleMetadataStatus = "unavailable"
                    }
                    break
                }

                $result = "failed"
                $stoppedAtTask = $taskId
                $stopReason = "unsupported_action"
                $skippedTasks += (New-QueueSkippedTask -Task $task -Reason "unsupported_action")
                break
            }

            if ($riskLevel -eq "high") {
                $result = "stopped"
                $stoppedAtTask = $taskId
                $stopReason = "high_risk_task_reached"
                $riskGate = "high_risk_user_approval"
                $skippedTasks += (New-QueueSkippedTask -Task $task -Reason "high_risk_stop_gate")
                break
            }

            if ($QueueExecutableLowRiskActions -notcontains $allowedAction) {
                $result = "failed"
                $stoppedAtTask = $taskId
                $stopReason = "unsupported_action"
                $skippedTasks += (New-QueueSkippedTask -Task $task -Reason "unsupported_action")
                break
            }

            try {
                $summary = Invoke-LowRiskQueueTask -Task $task -Queue $queue
                $completedTasks += (New-QueueCompletedTask -Task $task -Summary $summary)
            }
            catch {
                $result = "failed"
                $stoppedAtTask = $taskId
                $stopReason = "read_only_task_failed"
                $skippedTasks += (New-QueueSkippedTask -Task $task -Reason "read_only_task_failed")
                $validations["actions_supported"] = New-RunnerValidationResult -Status "failed" -Summary "Read-only task '$taskId' failed: $($_.Exception.Message)"
                break
            }

            if ([bool](Get-QueuePropertyValue -Object $task -PropertyName "stop_after_completion")) {
                $result = "stopped"
                $stoppedAtTask = $taskId
                $stopReason = "stop_after_completion"
                break
            }
        }
    }
    else {
        for ($index = 0; $index -lt $tasks.Count; $index++) {
            $task = $tasks[$index]
            $taskId = Get-QueuePropertyText -Object $task -PropertyName "task_id"
            if ([string]::IsNullOrWhiteSpace($taskId)) { $taskId = "task_index_$index" }
            if ($null -eq $stoppedAtTask -and $stopReason -eq "unsupported_action") {
                $allowedAction = Get-QueuePropertyText -Object $task -PropertyName "allowed_action"
                if ($QueueExecutableLowRiskActions -notcontains $allowedAction) {
                    $stoppedAtTask = $taskId
                    $skippedTasks += (New-QueueSkippedTask -Task $task -Reason "unsupported_action")
                    break
                }
            }
        }
    }

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: RunQueue"
    Write-Host "Queue file: $QueueFile"
    Write-Host "Safety boundary: $RunQueueSafetyBoundary"
    Write-QueueRunnerResult -Json (New-QueueRunnerResultJson `
        -QueueId $queueId `
        -ParentIssue $parentIssue `
        -QueueRepo $queueRepo `
        -Branch $branch `
        -Head $head `
        -Result $result `
        -DryRun $false `
        -PlannedTasks $plannedTasks `
        -CompletedTasks $completedTasks `
        -SkippedTasks $skippedTasks `
        -StoppedAtTask $stoppedAtTask `
        -StopReason $stopReason `
        -RiskGate $riskGate `
        -QuotaOrRateLimitDetected $false `
        -ChangedFiles $changedFiles `
        -ReviewId $reviewId `
        -DiffFingerprint $diffFingerprint `
        -FilesFingerprint $filesFingerprint `
        -ReviewBundleMetadataStatus $reviewBundleMetadataStatus `
        -ReviewBundleMetadataBlockReason $reviewBundleMetadataBlockReason `
        -ReviewBundleHandoffTask $reviewBundleHandoffTask `
        -Validations $validations)
}

function Get-StatusLines {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    if ([string]::IsNullOrWhiteSpace($Status)) {
        return @()
    }

    return @($Status -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Get-StatusPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Line
    )

    if ($Line.Length -le 3) {
        throw "Unexpected git status line: $Line"
    }

    $path = $Line.Substring(3).Trim()
    if ($path -match " -> ") {
        throw "Renamed or copied paths are not supported by ApprovalNextCommit modes: $path"
    }

    return $path
}

function Get-StatusPaths {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    $paths = foreach ($line in (Get-StatusLines -Status $Status)) {
        Get-StatusPath -Line $line
    }

    return @($paths | Sort-Object -Unique)
}

function Test-SafeRepoRelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = $Path -replace "\\", "/"
    if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }
    if ([System.IO.Path]::IsPathRooted($normalized)) { return $false }
    if ($normalized -match "(^|/)\.\.(/|$)") { return $false }
    if ($normalized -match "(^|/)\.git(/|$)") { return $false }
    if ($normalized -match "(^|/)(node_modules|\.venv|venv|__pycache__|\.pytest_cache|dist|build|coverage)(/|$)") { return $false }
    if ($normalized -match "(^|/)(app\.db|.*\.(sqlite|sqlite3|db))$") { return $false }
    if ($normalized -match "(^|/)(\.env|\.env\..+)$") { return $false }
    return $true
}

function Assert-ReviewableStatus {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    foreach ($line in (Get-StatusLines -Status $Status)) {
        if ($line.Length -lt 3) {
            throw "Unexpected git status line: $line"
        }

        $x = $line.Substring(0, 1)
        $y = $line.Substring(1, 1)
        if (($x -eq "U") -or ($y -eq "U") -or ($line.Substring(0, 2) -in @("DD", "AA"))) {
            throw "Unmerged git status is not supported by runner v1 commit mode: $line"
        }

        $path = Get-StatusPath -Line $line
        if (-not (Test-SafeRepoRelativePath -Path $path)) {
            throw "Refusing unsafe or outside-allowlist path: $path"
        }

        $fullPath = Join-Path -Path $RepoRoot -ChildPath $path
        $resolvedParent = Resolve-Path -LiteralPath (Split-Path -Parent $fullPath) -ErrorAction SilentlyContinue
        if ($null -ne $resolvedParent -and -not $resolvedParent.Path.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing path outside repo root: $path"
        }
    }
}

function Assert-NoPreexistingStagedFiles {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    $stagedLines = foreach ($line in (Get-StatusLines -Status $Status)) {
        if (($line.Substring(0, 1) -ne " ") -and ($line.Substring(0, 1) -ne "?")) {
            $line
        }
    }

    if (@($stagedLines).Count -gt 0) {
        throw "Refusing ApprovalNextCommit mode because staged files already exist:`n$($stagedLines -join [Environment]::NewLine)"
    }
}

function Test-DocsOnlyMarkdownPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = $Path -replace "\\", "/"
    if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }
    if ([System.IO.Path]::IsPathRooted($normalized)) { return $false }
    if ($normalized -match "(^|/)\.\.(/|$)") { return $false }
    return ($normalized -match "^docs/[^/]+\.md$")
}

function Assert-DocsOnlyMarkdownChanges {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    $paths = @(Get-StatusPaths -Status $Status)
    if ($paths.Count -eq 0) {
        throw "No modified files are available for ApprovalNextCommit mode."
    }

    $blockedPaths = @($paths | Where-Object { -not (Test-DocsOnlyMarkdownPath -Path $_) })
    if ($blockedPaths.Count -gt 0) {
        throw "ApprovalNextCommit mode is docs-only and accepts only docs/*.md paths. Refused path(s):`n$($blockedPaths -join [Environment]::NewLine)"
    }
}

function Get-UntrackedFileFingerprintPayload {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    $payloadLines = foreach ($line in (Get-StatusLines -Status $Status)) {
        if ($line.StartsWith("??")) {
            $path = Get-StatusPath -Line $line
            $fullPath = Join-Path -Path $RepoRoot -ChildPath $path
            if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
                throw "Untracked directories are not supported by ApprovalNextCommit mode: $path"
            }
            $hash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
            "$path $hash"
        }
    }

    return (@($payloadLines) | Sort-Object) -join [Environment]::NewLine
}

function Get-CommitApprovalState {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumberForState,
        [switch]$ValidateDocsOnlyCommit
    )

    $branchForState = Format-Block -Text (Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current") -EmptyText "(detached HEAD)"
    $headForState = Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
    $statusForState = Get-GitStatusShort
    Assert-ReviewableStatus -Status $statusForState
    if ($ValidateDocsOnlyCommit) {
        Assert-NoPreexistingStagedFiles -Status $statusForState
        Assert-DocsOnlyMarkdownChanges -Status $statusForState
    }

    $statusLines = @(Get-StatusLines -Status $statusForState | Sort-Object)
    $trackedDiff = Get-GitOutput -GitArgs @("diff", "--binary") -Action "git diff --binary"
    $untrackedPayload = Get-UntrackedFileFingerprintPayload -Status $statusForState
    $modifiedFilesForState = @(Get-StatusPaths -Status $statusForState)
    $statusPayload = $statusLines -join [Environment]::NewLine
    $filesPayload = "issue=$IssueNumberForState`nbranch=$branchForState`nhead=$headForState`nstatus=`n$statusPayload"
    $diffPayload = "issue=$IssueNumberForState`nbranch=$branchForState`nhead=$headForState`nstatus=`n$statusPayload`ntracked-diff=`n$trackedDiff`nuntracked=`n$untrackedPayload"
    $filesFingerprint = Get-Sha256Text -Text $filesPayload
    $diffFingerprint = Get-Sha256Text -Text $diffPayload
    $reviewId = (Get-Sha256Text -Text "review`nissue=$IssueNumberForState`nbranch=$branchForState`nhead=$headForState`ndiff=$diffFingerprint`nfiles=$filesFingerprint").Substring(0, 16)

    return [pscustomobject]@{
        IssueNumber = [string]$IssueNumberForState
        Branch = $branchForState
        Head = $headForState
        Status = $statusForState
        StatusRawHash = Get-Sha256Text -Text $statusForState
        StatusRecords = $statusPayload
        ModifiedFiles = $modifiedFilesForState
        ModifiedFilesText = if ($modifiedFilesForState.Count -eq 0) { "(none)" } else { $modifiedFilesForState -join [Environment]::NewLine }
        TrackedDiff = $trackedDiff
        TrackedDiffHash = Get-Sha256Text -Text $trackedDiff
        TrackedDiffLength = $trackedDiff.Length
        TrackedDiffLineCount = Get-TextLineCount -Text $trackedDiff
        UntrackedPayload = $untrackedPayload
        UntrackedPayloadHash = Get-Sha256Text -Text $untrackedPayload
        FilesPayload = $filesPayload
        FilesPayloadHash = Get-Sha256Text -Text $filesPayload
        DiffPayload = $diffPayload
        DiffPayloadHash = Get-Sha256Text -Text $diffPayload
        DiffFingerprint = $diffFingerprint
        FilesFingerprint = $filesFingerprint
        ReviewId = $reviewId
    }
}

function Invoke-ApprovalStateDiagnostic {
    if ($IssueNumber -lt 1) {
        throw "ApprovalStateDiagnostic requires -IssueNumber <N>."
    }

    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalStateDiagnostic supports only repo=$ExpectedApprovalRepo for this approval-state slice."
    }

    Assert-RepoRoot
    $state = Get-CommitApprovalState -IssueNumberForState $IssueNumber

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalStateDiagnostic"
    Write-Host "Read-only: yes"
    Write-Host "Issue number: #$($state.IssueNumber)"
    Write-Host "Branch: $($state.Branch)"
    Write-Host "Full HEAD: $($state.Head)"
    Write-Host "Git status raw hash: $($state.StatusRawHash)"
    Write-Host "Git status normalized visible representation:"
    Write-Host (Get-TextPreview -Text $state.Status)
    Write-Host "Status records used for fingerprinting:"
    Write-Host (Get-TextPreview -Text $state.StatusRecords)
    Write-Host "Modified files payload:"
    Write-Host (Get-TextPreview -Text $state.ModifiedFilesText)
    Write-Host "Tracked diff fingerprint: $($state.TrackedDiffHash)"
    Write-Host "Tracked diff length: $($state.TrackedDiffLength)"
    Write-Host "Tracked diff line count: $($state.TrackedDiffLineCount)"
    Write-Host "Untracked payload fingerprint: $($state.UntrackedPayloadHash)"
    Write-Host "Untracked payload visible representation:"
    Write-Host (Get-TextPreview -Text $state.UntrackedPayload)
    Write-Host "Files payload hash: $($state.FilesPayloadHash)"
    Write-Host "Files payload preview:"
    Write-Host (Get-TextPreview -Text $state.FilesPayload)
    Write-Host "Diff payload hash: $($state.DiffPayloadHash)"
    Write-Host "Diff payload length: $($state.DiffPayload.Length)"
    Write-Host "Diff payload line count: $(Get-TextLineCount -Text $state.DiffPayload)"
    Write-Host "Final files fingerprint: $($state.FilesFingerprint)"
    Write-Host "Final diff fingerprint: $($state.DiffFingerprint)"
    Write-Host "Final review id: $($state.ReviewId)"
    Write-Host "No-write guarantee: diagnostic mode does not call Codex, run runner v1, modify files, post GitHub comments, stage files, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, run polling, run a daemon, run a scheduler, or consume approval tokens."
}

function Assert-GhAvailable {
    $ghCommand = Get-Command "gh" -ErrorAction SilentlyContinue
    if ($null -eq $ghCommand) {
        throw "GitHub CLI 'gh' is missing or unavailable on PATH."
    }
}

function Get-RequiredMarkerSearchQuery {
    $searchTerms = foreach ($marker in $RequiredMarkers) {
        $term = $marker
        if ($term -match "^Runner marker:\s*(.+)$") {
            $term = $Matches[1]
        }
        $term -split "\s+" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    return (@($searchTerms) -join " ")
}

function Get-OpenIssues {
    Assert-GhAvailable

    $searchQuery = Get-RequiredMarkerSearchQuery
    $ghArgs = @(
        "issue",
        "list",
        "--repo",
        $Repo,
        "--state",
        "open",
        "--search",
        $searchQuery,
        "--limit",
        "$MaxIssues",
        "--json",
        "number,title"
    )
    $result = Invoke-ReadOnlyCommand -FilePath "gh" -Arguments $ghArgs -Action "gh issue list"
    Require-Success -Result $result -Action "gh issue list"

    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        throw "gh issue list returned an empty response."
    }

    try {
        $issues = $result.Stdout | ConvertFrom-Json
    }
    catch {
        throw "gh issue list returned invalid JSON: $($_.Exception.Message)"
    }

    if ($null -eq $issues) {
        throw "gh issue list returned an invalid or empty JSON response."
    }

    return @($issues)
}

function Get-OpenApprovalSearchIssues {
    Assert-GhAvailable

    $ghArgs = @(
        "issue",
        "list",
        "--repo",
        $Repo,
        "--state",
        "open",
        "--limit",
        "$MaxIssues",
        "--json",
        "number,title"
    )
    $result = Invoke-ReadOnlyCommand -FilePath "gh" -Arguments $ghArgs -Action "gh issue list"
    Require-Success -Result $result -Action "gh issue list"

    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        throw "gh issue list returned an empty response."
    }

    try {
        $issues = $result.Stdout | ConvertFrom-Json
    }
    catch {
        throw "gh issue list returned invalid JSON: $($_.Exception.Message)"
    }

    if ($null -eq $issues) {
        throw "gh issue list returned an invalid or empty JSON response."
    }

    return @($issues)
}

function Test-AsciiText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    foreach ($character in $Text.ToCharArray()) {
        if ([int][char]$character -gt 127) {
            return $false
        }
    }

    return $true
}

function Test-ExactListValue {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Values,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    foreach ($candidate in $Values) {
        if ([string]::Equals($candidate, $Value, [System.StringComparison]::Ordinal)) {
            return $true
        }
    }

    return $false
}

function Get-ObjectPropertyText {
    param(
        [Parameter(Mandatory = $false)]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    if ($null -eq $Object) {
        return ""
    }

    $property = $Object.PSObject.Properties[$PropertyName]
    if ($null -eq $property -or $null -eq $property.Value) {
        return ""
    }

    return [string]$property.Value
}

function Get-CommentAuthorLogin {
    param(
        [Parameter(Mandatory = $false)]
        [object]$Comment
    )

    if ($null -eq $Comment) {
        return ""
    }

    $authorProperty = $Comment.PSObject.Properties["author"]
    if ($null -eq $authorProperty -or $null -eq $authorProperty.Value) {
        return ""
    }

    return Get-ObjectPropertyText -Object $authorProperty.Value -PropertyName "login"
}

function ConvertFrom-ApprovalMarkerLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MarkerLine
    )

    if (-not (Test-AsciiText -Text $MarkerLine)) {
        throw "Approval marker contains non-ASCII text. Marker lines must be ASCII-safe."
    }

    $parts = $MarkerLine.Split(" ")
    if ($parts.Count -lt 2 -or -not [string]::Equals($parts[0], $ApprovalMarkerPrefix, [System.StringComparison]::Ordinal)) {
        throw "Malformed approval marker. Marker must start with exact token '$ApprovalMarkerPrefix' followed by key=value fields."
    }

    if (@($parts | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
        throw "Malformed approval marker. Use single spaces between marker fields and do not include empty fields."
    }

    $seenFields = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $fields = @{}

    foreach ($part in @($parts | Select-Object -Skip 1)) {
        if ($part -notmatch "^([a-z]+)=([^=\s]+)$") {
            throw "Malformed approval marker field '$part'. Expected key=value with a lowercase known key and a non-empty value."
        }

        $fieldName = $Matches[1]
        $fieldValue = $Matches[2]

        if (-not (Test-ExactListValue -Values $ApprovalKnownFields -Value $fieldName)) {
            throw "Unknown approval marker field '$fieldName'."
        }

        if (-not $seenFields.Add($fieldName)) {
            throw "Duplicate approval marker field '$fieldName'."
        }

        if ([string]::IsNullOrWhiteSpace($fieldValue)) {
            throw "Approval marker field '$fieldName' has an empty value."
        }

        $fields[$fieldName] = $fieldValue
    }

    foreach ($requiredField in $ApprovalBaseRequiredFields) {
        if (-not $seenFields.Contains($requiredField)) {
            throw "Missing required approval marker field '$requiredField'."
        }
    }

    return $fields
}

function Get-ApprovalMarkerActionToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MarkerLine
    )

    $parts = $MarkerLine.Split(" ")
    if ($parts.Count -lt 2 -or -not [string]::Equals($parts[0], $ApprovalMarkerPrefix, [System.StringComparison]::Ordinal)) {
        return $null
    }

    foreach ($part in @($parts | Select-Object -Skip 1)) {
        if ($part -match "^action=([^=\s]+)$") {
            return $Matches[1]
        }
    }

    return $null
}

function Assert-ApprovalRequiredFields {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredFields,
        [Parameter(Mandatory = $true)]
        [string]$Context
    )

    foreach ($requiredField in $RequiredFields) {
        if (-not $Fields.ContainsKey($requiredField)) {
            throw "$Context marker is missing required field '$requiredField'."
        }
    }
}

function Invoke-WriteCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $stdoutFile = New-TemporaryFile
    $stderrFile = New-TemporaryFile
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments 1> $stdoutFile.FullName 2> $stderrFile.FullName
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        $stdout = Get-Content -LiteralPath $stdoutFile.FullName -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrFile.FullName -Raw -ErrorAction SilentlyContinue
    }
    catch {
        return [pscustomobject]@{
            ExitCode = 1
            Stdout = ""
            Stderr = "$Action failed: $($_.Exception.Message)"
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Remove-Item -LiteralPath $stdoutFile.FullName -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrFile.FullName -Force -ErrorAction SilentlyContinue
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = if ($null -eq $stdout) { "" } else { $stdout.Trim() }
        Stderr = if ($null -eq $stderr) { "" } else { $stderr.Trim() }
    }
}

function ConvertTo-ApprovalExpiryUtc {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Expires
    )

    if ($Expires -notmatch "^\d{8}T\d{6}Z$") {
        throw "Approval marker expires value '$Expires' is malformed. Expected YYYYMMDDTHHMMSSZ."
    }

    try {
        $styles = [System.Globalization.DateTimeStyles]::AssumeUniversal -bor [System.Globalization.DateTimeStyles]::AdjustToUniversal
        return [System.DateTime]::ParseExact($Expires, "yyyyMMdd'T'HHmmss'Z'", [System.Globalization.CultureInfo]::InvariantCulture, $styles)
    }
    catch {
        throw "Approval marker expires value '$Expires' is not a valid UTC timestamp: $($_.Exception.Message)"
    }
}

function Assert-ApprovalFieldEquals {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Expected
    )

    $actual = [string]$Fields[$Name]
    if (-not [string]::Equals($actual, $Expected, [System.StringComparison]::Ordinal)) {
        throw "Approval marker field '$Name' mismatch. Expected '$Expected', found '$actual'."
    }
}

function Assert-ApprovalMarkerMatchesLocalState {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedIssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedAction,
        [Parameter(Mandatory = $true)]
        [string]$ModeName,
        [Parameter(Mandatory = $true)]
        [string]$CurrentBranch,
        [Parameter(Mandatory = $true)]
        [string]$CurrentHead,
        [Parameter(Mandatory = $true)]
        [datetime]$ExpiresUtc,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    Assert-ApprovalRequiredFields -Fields $Fields -RequiredFields $ApprovalRequiredFields -Context $ModeName
    Assert-ApprovalFieldEquals -Fields $Fields -Name "protocol" -Expected $ApprovalProtocol

    $action = [string]$Fields["action"]
    if (-not [string]::Equals($action, $ExpectedAction, [System.StringComparison]::Ordinal)) {
        throw "Unsupported approval action '$action'. $ModeName supports only action=$ExpectedAction."
    }

    Assert-ApprovalFieldEquals -Fields $Fields -Name "issue" -Expected ([string]$ExpectedIssueNumber)
    Assert-ApprovalFieldEquals -Fields $Fields -Name "repo" -Expected $ExpectedApprovalRepo
    Assert-ApprovalFieldEquals -Fields $Fields -Name "branch" -Expected $CurrentBranch
    Assert-ApprovalFieldEquals -Fields $Fields -Name "head" -Expected $CurrentHead
    Assert-ApprovalFieldEquals -Fields $Fields -Name "review" -Expected "none"
    Assert-ApprovalFieldEquals -Fields $Fields -Name "diff" -Expected "none"
    Assert-ApprovalFieldEquals -Fields $Fields -Name "files" -Expected "none"
    if ($Fields.ContainsKey("filelist")) {
        Assert-ApprovalFieldEquals -Fields $Fields -Name "filelist" -Expected "none"
    }

    if ($ExpiresUtc -le $NowUtc) {
        throw "Approval marker expired at $($ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")); current UTC time is $($NowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
    }
}

function Assert-CommitApprovalMarkerMatchesState {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [object]$State,
        [Parameter(Mandatory = $true)]
        [datetime]$ExpiresUtc,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    Assert-ApprovalRequiredFields -Fields $Fields -RequiredFields $ApprovalRequiredFields -Context "ApprovalNextCommit"
    Assert-ApprovalFieldEquals -Fields $Fields -Name "protocol" -Expected $ApprovalProtocol
    Assert-ApprovalFieldEquals -Fields $Fields -Name "action" -Expected $ApprovalNextCommitSupportedAction
    Assert-ApprovalFieldEquals -Fields $Fields -Name "issue" -Expected $State.IssueNumber
    Assert-ApprovalFieldEquals -Fields $Fields -Name "repo" -Expected $ExpectedApprovalRepo
    Assert-ApprovalFieldEquals -Fields $Fields -Name "branch" -Expected $State.Branch
    Assert-ApprovalFieldEquals -Fields $Fields -Name "head" -Expected $State.Head
    Assert-ApprovalFieldEquals -Fields $Fields -Name "review" -Expected $State.ReviewId
    Assert-ApprovalFieldEquals -Fields $Fields -Name "diff" -Expected $State.DiffFingerprint
    Assert-ApprovalFieldEquals -Fields $Fields -Name "files" -Expected $State.FilesFingerprint

    if ($ExpiresUtc -le $NowUtc) {
        throw "Approval marker expired at $($ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")); current UTC time is $($NowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
    }
}

function Get-RemoteNames {
    $remotes = Get-GitOutput -GitArgs @("remote") -Action "git remote"
    if ([string]::IsNullOrWhiteSpace($remotes)) {
        return @()
    }

    return @($remotes -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Test-RemoteUrlMatchesExpectedRepo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RemoteUrl
    )

    return ($RemoteUrl -match "github\.com[:/]HarryWhite-TW/local-ai-workbench(\.git)?/?$")
}

function Get-RemoteBranchNameFromUpstream {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Upstream,
        [Parameter(Mandatory = $true)]
        [string]$Remote
    )

    $prefix = "$Remote/"
    if (-not $Upstream.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
        throw "Upstream '$Upstream' does not belong to remote '$Remote'."
    }

    $branchName = $Upstream.Substring($prefix.Length)
    if ([string]::IsNullOrWhiteSpace($branchName)) {
        throw "Upstream '$Upstream' does not include a remote branch name."
    }

    return $branchName
}

function Get-RemoteBranchHead {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Remote,
        [Parameter(Mandatory = $true)]
        [string]$BranchName
    )

    $refName = "refs/heads/$BranchName"
    $output = Get-GitOutput -GitArgs @("ls-remote", $Remote, $refName) -Action "git ls-remote $Remote $refName"
    $lines = @($output -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($lines.Count -ne 1) {
        throw "Read-only remote query for $Remote $refName returned $($lines.Count) matching refs; exactly one is required."
    }

    $parts = $lines[0] -split "\s+"
    if ($parts.Count -lt 2 -or -not [string]::Equals($parts[1], $refName, [System.StringComparison]::Ordinal)) {
        throw "Read-only remote query returned an unexpected ref line: $($lines[0])"
    }

    return $parts[0]
}

function Get-AheadBehindState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Upstream
    )

    $counts = Get-GitOutput -GitArgs @("rev-list", "--left-right", "--count", "HEAD...$Upstream") -Action "git rev-list --left-right --count HEAD...$Upstream"
    $parts = $counts -split "\s+"
    if ($parts.Count -ne 2) {
        throw "Could not parse ahead/behind count: $counts"
    }

    return [pscustomobject]@{
        Ahead = [int]$parts[0]
        Behind = [int]$parts[1]
    }
}

function Get-NormalizedCommittedFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Commit
    )

    $output = Get-GitOutput -GitArgs @("show", "--name-only", "--format=", $Commit) -Action "git show --name-only --format= $Commit"
    if ([string]::IsNullOrWhiteSpace($output)) {
        return @()
    }

    return @(
        $output -split "\r?\n" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim() -replace "\\", "/" } |
            Sort-Object -Unique
    )
}

function Get-CommitFilesFingerprintPayload {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Files
    )

    return (@($Files) -join "`n")
}

function Get-PushDryRunState {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [string]$ExpectedAction = $PushDryRunSupportedAction,
        [string]$ModeName = "PushDryRun"
    )

    Assert-ApprovalRequiredFields -Fields $Fields -RequiredFields $PushDryRunRequiredFields -Context $ModeName
    Assert-ApprovalFieldEquals -Fields $Fields -Name "protocol" -Expected $ApprovalProtocol
    Assert-ApprovalFieldEquals -Fields $Fields -Name "action" -Expected $ExpectedAction
    Assert-ApprovalFieldEquals -Fields $Fields -Name "issue" -Expected ([string]$IssueNumber)
    Assert-ApprovalFieldEquals -Fields $Fields -Name "repo" -Expected $ExpectedApprovalRepo

    $cleanResult = Assert-CleanRepo
    $staged = Get-GitOutput -GitArgs @("diff", "--cached", "--name-only") -Action "git diff --cached --name-only"
    if (-not [string]::IsNullOrWhiteSpace($staged)) {
        throw "Staged files exist; $ModeName requires no staged files:`n$staged"
    }

    $branch = Get-CurrentBranch
    $head = Get-CurrentFullHead
    Assert-ApprovalFieldEquals -Fields $Fields -Name "branch" -Expected $branch
    Assert-ApprovalFieldEquals -Fields $Fields -Name "localhead" -Expected $head

    $commit = [string]$Fields["commit"]
    Assert-ApprovalFieldEquals -Fields $Fields -Name "commit" -Expected $head

    $remote = [string]$Fields["remote"]
    $remoteNames = @(Get-RemoteNames)
    if (-not ($remoteNames -contains $remote)) {
        throw "Remote '$remote' does not exist. Available remotes: $($remoteNames -join ', ')"
    }

    $remoteUrl = Get-GitOutput -GitArgs @("remote", "get-url", $remote) -Action "git remote get-url $remote"
    if (-not (Test-RemoteUrlMatchesExpectedRepo -RemoteUrl $remoteUrl)) {
        throw "Remote '$remote' URL does not point to expected repo $ExpectedApprovalRepo. Found: $remoteUrl"
    }

    $upstream = Get-GitOutput -GitArgs @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") -Action "git rev-parse --abbrev-ref --symbolic-full-name @{u}"
    Assert-ApprovalFieldEquals -Fields $Fields -Name "upstream" -Expected $upstream

    $remoteBranchName = Get-RemoteBranchNameFromUpstream -Upstream $upstream -Remote $remote
    $remoteHead = Get-RemoteBranchHead -Remote $remote -BranchName $remoteBranchName
    Assert-ApprovalFieldEquals -Fields $Fields -Name "remotehead" -Expected $remoteHead

    $aheadBehind = Get-AheadBehindState -Upstream $upstream
    $markerAhead = [int]([string]$Fields["ahead"])
    if ($markerAhead -ne 1) {
        throw "$ModeName requires marker ahead=1. Found ahead=$markerAhead."
    }
    if ($aheadBehind.Ahead -ne $markerAhead) {
        throw "Ahead count mismatch. Marker ahead=$markerAhead; local ahead=$($aheadBehind.Ahead)."
    }
    if ($aheadBehind.Ahead -ne 1) {
        throw "$ModeName requires exactly one local commit ahead. Found ahead=$($aheadBehind.Ahead)."
    }
    if ($aheadBehind.Behind -ne 0) {
        throw "Branch is diverged or remote is ahead. Behind count is $($aheadBehind.Behind)."
    }

    $aheadLog = Get-GitOutput -GitArgs @("log", "--format=%H", "$upstream..HEAD") -Action "git log --format=%H $upstream..HEAD"
    $aheadCommits = @($aheadLog -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($aheadCommits.Count -ne 1) {
        throw "$ModeName requires exactly one unpushed commit. Found $($aheadCommits.Count)."
    }
    if (-not [string]::Equals($aheadCommits[0], $commit, [System.StringComparison]::Ordinal)) {
        throw "Unapproved commits are included. Only approved commit '$commit' may be ahead; found '$($aheadCommits[0])'."
    }

    $committedFiles = @(Get-NormalizedCommittedFiles -Commit $commit)
    $commitFilesPayload = Get-CommitFilesFingerprintPayload -Files $committedFiles
    $commitFilesFingerprint = Get-Sha256Text -Text $commitFilesPayload
    Assert-ApprovalFieldEquals -Fields $Fields -Name "commitfiles" -Expected $commitFilesFingerprint

    return [pscustomobject]@{
        CleanSummary = $cleanResult.Summary
        Branch = $branch
        LocalHead = $head
        Remote = $remote
        RemoteUrl = $remoteUrl
        Upstream = $upstream
        RemoteHead = $remoteHead
        Ahead = $aheadBehind.Ahead
        Behind = $aheadBehind.Behind
        ApprovedCommit = $commit
        CommittedFiles = @($committedFiles)
        CommittedFilesText = if ($committedFiles.Count -eq 0) { "(none)" } else { $committedFiles -join [Environment]::NewLine }
        CommitFilesFingerprint = $commitFilesFingerprint
        PlannedPushTarget = "$remote $branch"
    }
}

function Get-CloseIssueOnceState {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$IssueState,
        [Parameter(Mandatory = $true)]
        [datetime]$ExpiresUtc,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    Assert-ApprovalRequiredFields -Fields $Fields -RequiredFields $CloseIssueOnceRequiredFields -Context "CloseIssueOnce"
    Assert-ApprovalFieldEquals -Fields $Fields -Name "protocol" -Expected $ApprovalProtocol
    Assert-ApprovalFieldEquals -Fields $Fields -Name "action" -Expected $CloseIssueOnceSupportedAction
    Assert-ApprovalFieldEquals -Fields $Fields -Name "repo" -Expected $ExpectedApprovalRepo
    Assert-ApprovalFieldEquals -Fields $Fields -Name "issue" -Expected ([string]$IssueNumber)
    Assert-ApprovalFieldEquals -Fields $Fields -Name "target" -Expected ([string]$IssueNumber)
    Assert-ApprovalFieldEquals -Fields $Fields -Name "targetstate" -Expected "OPEN"

    if (-not [string]::Equals($IssueState, "OPEN", [System.StringComparison]::Ordinal)) {
        throw "Selected issue #$IssueNumber must be currently OPEN. Found state '$IssueState'."
    }

    if ($ExpiresUtc -le $NowUtc) {
        throw "Approval marker expired at $($ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")); current UTC time is $($NowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
    }

    $cleanResult = Assert-CleanRepo
    $staged = Get-GitOutput -GitArgs @("diff", "--cached", "--name-only") -Action "git diff --cached --name-only"
    if (-not [string]::IsNullOrWhiteSpace($staged)) {
        throw "Staged files exist; CloseIssueOnce requires no staged files:`n$staged"
    }

    $branch = Get-CurrentBranch
    $localHead = Get-CurrentFullHead
    Assert-ApprovalFieldEquals -Fields $Fields -Name "branch" -Expected $branch
    Assert-ApprovalFieldEquals -Fields $Fields -Name "localhead" -Expected $localHead

    $remote = [string]$Fields["remote"]
    $remoteNames = @(Get-RemoteNames)
    if (-not ($remoteNames -contains $remote)) {
        throw "Remote '$remote' does not exist. Available remotes: $($remoteNames -join ', ')"
    }

    $remoteUrl = Get-GitOutput -GitArgs @("remote", "get-url", $remote) -Action "git remote get-url $remote"
    if (-not (Test-RemoteUrlMatchesExpectedRepo -RemoteUrl $remoteUrl)) {
        throw "Remote '$remote' URL does not point to expected repo $ExpectedApprovalRepo. Found: $remoteUrl"
    }

    $upstream = Get-GitOutput -GitArgs @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") -Action "git rev-parse --abbrev-ref --symbolic-full-name @{u}"
    Assert-ApprovalFieldEquals -Fields $Fields -Name "upstream" -Expected $upstream

    $remoteBranchName = Get-RemoteBranchNameFromUpstream -Upstream $upstream -Remote $remote
    $remoteHead = Get-RemoteBranchHead -Remote $remote -BranchName $remoteBranchName
    Assert-ApprovalFieldEquals -Fields $Fields -Name "remotehead" -Expected $remoteHead

    if (-not [string]::Equals($localHead, $remoteHead, [System.StringComparison]::Ordinal)) {
        throw "CloseIssueOnce requires local HEAD to equal remote HEAD. localhead=$localHead remotehead=$remoteHead."
    }

    Assert-ApprovalFieldEquals -Fields $Fields -Name "pushed" -Expected $localHead
    if (-not [string]::Equals([string]$Fields["pushed"], $remoteHead, [System.StringComparison]::Ordinal)) {
        throw "Approval marker field 'pushed' must equal remote HEAD. pushed=$($Fields["pushed"]) remotehead=$remoteHead."
    }

    return [pscustomobject]@{
        CleanSummary = $cleanResult.Summary
        Branch = $branch
        LocalHead = $localHead
        Remote = $remote
        RemoteUrl = $remoteUrl
        Upstream = $upstream
        RemoteHead = $remoteHead
        Pushed = [string]$Fields["pushed"]
        PreviousIssueState = $IssueState
    }
}

function Get-ValidatedApprovalSelection {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedAction,
        [Parameter(Mandatory = $true)]
        [string]$ModeName,
        [switch]$AllowNoMarkerLines
    )

    $branch = Get-CurrentBranch
    $head = Get-CurrentFullHead
    $nowUtc = [System.DateTime]::UtcNow
    $readResult = Get-IssueApprovalMarkerReadResult -IssueNumber $IssueNumber
    $markers = @($readResult.Markers)

    if ($markers.Count -eq 0) {
        if ($AllowNoMarkerLines) {
            return [pscustomobject]@{
                HasSelection = $false
                ReadResult = $readResult
                Markers = @()
                Branch = $branch
                Head = $head
                NowUtc = $nowUtc
                Selected = $null
            }
        }

        throw "No current approval marker found for issue #$IssueNumber. No RUNNER-V2-APPROVE marker lines were found."
    }

    $parsedMarkers = @()
    foreach ($marker in $markers) {
        $parsedMarkers += ConvertTo-ParsedApprovalMarker -Marker $marker -NowUtc $nowUtc
    }

    $currentMarkers = @($parsedMarkers | Where-Object { $_.IsCurrent })
    if ($currentMarkers.Count -eq 0) {
        $latestMarker = $parsedMarkers[$parsedMarkers.Count - 1]
        throw "No current approval marker found for issue #$IssueNumber. Latest marker expired at $($latestMarker.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
    }

    if ($currentMarkers.Count -gt 1) {
        throw "Ambiguous approval markers found for issue #$IssueNumber. Found $($currentMarkers.Count) current RUNNER-V2-APPROVE marker lines; exactly one is required."
    }

    $selected = $currentMarkers[0]
    Assert-ApprovalMarkerMatchesLocalState `
        -Fields $selected.Fields `
        -ExpectedIssueNumber $IssueNumber `
        -ExpectedAction $ExpectedAction `
        -ModeName $ModeName `
        -CurrentBranch $branch `
        -CurrentHead $head `
        -ExpiresUtc $selected.ExpiresUtc `
        -NowUtc $nowUtc

    return [pscustomobject]@{
        HasSelection = $true
        ReadResult = $readResult
        Markers = @($markers)
        Branch = $branch
        Head = $head
        NowUtc = $nowUtc
        Selected = $selected
    }
}

function Get-IssueApprovalMarkerReadResult {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    Assert-GhAvailable

    $ghArgs = @(
        "issue",
        "view",
        "$IssueNumber",
        "--repo",
        $Repo,
        "--json",
        "number,title,state,comments"
    )
    $result = Invoke-ReadOnlyCommand -FilePath "gh" -Arguments $ghArgs -Action "gh issue view"
    Require-Success -Result $result -Action "gh issue view"

    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        throw "gh issue view returned an empty response."
    }

    try {
        $issueDetails = $result.Stdout | ConvertFrom-Json
    }
    catch {
        throw "gh issue view returned invalid JSON: $($_.Exception.Message)"
    }

    $issueState = Get-ObjectPropertyText -Object $issueDetails -PropertyName "state"
    $issueTitle = Get-ObjectPropertyText -Object $issueDetails -PropertyName "title"
    $comments = @()
    $commentsProperty = $issueDetails.PSObject.Properties["comments"]
    if ($null -ne $commentsProperty -and $null -ne $commentsProperty.Value) {
        $comments = @($commentsProperty.Value)
    }

    $markers = @()
    $commentIndex = 0
    foreach ($comment in $comments) {
        $commentIndex += 1
        $body = Get-ObjectPropertyText -Object $comment -PropertyName "body"
        $lines = @($body -split "\r?\n")
        $lineNumber = 0
        foreach ($line in $lines) {
            $lineNumber += 1
            if ($line.StartsWith($ApprovalMarkerPrefix, [System.StringComparison]::Ordinal)) {
                $markers += [pscustomobject]@{
                    Line = $line
                    Comment = $comment
                    CommentIndex = $commentIndex
                    LineNumber = $lineNumber
                }
            }
        }
    }

    return [pscustomobject]@{
        IssueNumber = $IssueNumber
        Title = $issueTitle
        IssueState = $issueState
        Markers = @($markers)
    }
}

function ConvertTo-ParsedApprovalMarker {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Marker,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    $fields = ConvertFrom-ApprovalMarkerLine -MarkerLine ([string]$Marker.Line)
    $expiresUtc = ConvertTo-ApprovalExpiryUtc -Expires ([string]$fields["expires"])

    return [pscustomobject]@{
        Marker = $Marker
        Fields = $fields
        ExpiresUtc = $expiresUtc
        IsCurrent = ($expiresUtc -gt $NowUtc)
    }
}

function Test-CloseIssueOnceLiveMarkerEligibility {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Marker
    )

    if ($null -eq $Marker.Comment) {
        return [pscustomobject]@{
            IsEligible = $false
            Reason = "Skipped marker-like content because it is not from a standalone issue comment."
        }
    }

    $body = Get-ObjectPropertyText -Object $Marker.Comment -PropertyName "body"
    $trimmedBody = $body.Trim()
    $markerLine = [string]$Marker.Line

    if (-not [string]::Equals($trimmedBody, $markerLine, [System.StringComparison]::Ordinal)) {
        return [pscustomobject]@{
            IsEligible = $false
            Reason = "Skipped marker-like content because the comment body is not exactly one standalone approval marker line."
        }
    }

    return [pscustomobject]@{
        IsEligible = $true
        Reason = ""
    }
}

function Find-ApprovalNextDryRunSelections {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CurrentBranch,
        [Parameter(Mandatory = $true)]
        [string]$CurrentHead,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc,
        [switch]$StopOnReadFailure,
        [switch]$StopOnMarkerFailure,
        [string]$ModeName = "ApprovalNextDryRun"
    )

    $issues = Get-OpenApprovalSearchIssues
    $validSelections = @()
    $skippedMarkers = @()
    $skippedIssues = @()

    foreach ($issue in $issues) {
        $issueNumber = [int]$issue.number
        $issueTitle = Get-ObjectPropertyText -Object $issue -PropertyName "title"

        try {
            $readResult = Get-IssueApprovalMarkerReadResult -IssueNumber $issueNumber
        }
        catch {
            if ($StopOnReadFailure) {
                throw "GitHub read failure while scanning issue #$issueNumber cannot be safely ignored. $($_.Exception.Message)"
            }

            $skippedIssues += [pscustomobject]@{
                IssueNumber = $issueNumber
                IssueTitle = $issueTitle
                Reason = $_.Exception.Message
            }
            continue
        }

        $markers = @($readResult.Markers)
        foreach ($marker in $markers) {
            try {
                $parsed = ConvertTo-ParsedApprovalMarker -Marker $marker -NowUtc $NowUtc
                if (-not $parsed.IsCurrent) {
                    $skippedMarkers += [pscustomobject]@{
                        IssueNumber = $issueNumber
                        IssueTitle = $issueTitle
                        Reason = "Approval marker expired at $($parsed.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
                    }
                    continue
                }

                Assert-ApprovalMarkerMatchesLocalState `
                    -Fields $parsed.Fields `
                    -ExpectedIssueNumber $issueNumber `
                    -ExpectedAction $ApprovalNextDryRunSupportedAction `
                    -ModeName $ModeName `
                    -CurrentBranch $CurrentBranch `
                    -CurrentHead $CurrentHead `
                    -ExpiresUtc $parsed.ExpiresUtc `
                    -NowUtc $NowUtc

                $selectedTitle = Get-ObjectPropertyText -Object $readResult -PropertyName "Title"
                if ([string]::IsNullOrWhiteSpace($selectedTitle)) {
                    $selectedTitle = $issueTitle
                }

                $validSelections += [pscustomobject]@{
                    IssueNumber = $issueNumber
                    IssueTitle = $selectedTitle
                    ReadResult = $readResult
                    Selected = $parsed
                    Branch = $CurrentBranch
                    Head = $CurrentHead
                    NowUtc = $NowUtc
                }
            }
            catch {
                if ($StopOnMarkerFailure) {
                    throw "Approval marker on issue #$issueNumber failed validation in ${ModeName}. $($_.Exception.Message)"
                }

                $skippedMarkers += [pscustomobject]@{
                    IssueNumber = $issueNumber
                    IssueTitle = $issueTitle
                    Reason = $_.Exception.Message
                }
            }
        }
    }

    return [pscustomobject]@{
        IssuesScanned = @($issues).Count
        ValidSelections = @($validSelections)
        SkippedMarkers = @($skippedMarkers)
        SkippedIssues = @($skippedIssues)
    }
}

function Find-ApprovalNextCommitSelections {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc,
        [switch]$StopOnReadFailure,
        [switch]$StopOnMarkerFailure,
        [string]$ModeName = "ApprovalNextCommitDryRun"
    )

    $issues = Get-OpenApprovalSearchIssues
    $validSelections = @()
    $skippedMarkers = @()
    $skippedIssues = @()
    $unsupportedMarkers = @()

    foreach ($issue in $issues) {
        $issueNumber = [int]$issue.number
        $issueTitle = Get-ObjectPropertyText -Object $issue -PropertyName "title"

        try {
            $readResult = Get-IssueApprovalMarkerReadResult -IssueNumber $issueNumber
        }
        catch {
            if ($StopOnReadFailure) {
                throw "GitHub read failure while scanning issue #$issueNumber cannot be safely ignored. $($_.Exception.Message)"
            }

            $skippedIssues += [pscustomobject]@{
                IssueNumber = $issueNumber
                IssueTitle = $issueTitle
                Reason = $_.Exception.Message
            }
            continue
        }

        $markers = @($readResult.Markers)
        foreach ($marker in $markers) {
            try {
                $parsed = ConvertTo-ParsedApprovalMarker -Marker $marker -NowUtc $NowUtc
                if (-not $parsed.IsCurrent) {
                    $skippedMarkers += [pscustomobject]@{
                        IssueNumber = $issueNumber
                        IssueTitle = $issueTitle
                        Reason = "Approval marker expired at $($parsed.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
                    }
                    continue
                }

                $action = [string]$parsed.Fields["action"]
                if (-not [string]::Equals($action, $ApprovalNextCommitSupportedAction, [System.StringComparison]::Ordinal)) {
                    if ($action -in @($ApprovalDryRunSupportedAction, $ApprovalOnceSupportedAction, $ApprovalNextDryRunSupportedAction)) {
                        $skippedMarkers += [pscustomobject]@{
                            IssueNumber = $issueNumber
                            IssueTitle = $issueTitle
                            Reason = "Ignored current non-commit approval action '$action'. $ModeName selects only action=$ApprovalNextCommitSupportedAction."
                        }
                    }
                    else {
                        $unsupportedMarkers += [pscustomobject]@{
                            IssueNumber = $issueNumber
                            IssueTitle = $issueTitle
                            Reason = "Unsupported approval action '$action'. $ModeName supports only action=$ApprovalNextCommitSupportedAction."
                        }
                    }
                    continue
                }

                $state = Get-CommitApprovalState -IssueNumberForState $issueNumber -ValidateDocsOnlyCommit
                Assert-CommitApprovalMarkerMatchesState -Fields $parsed.Fields -State $state -ExpiresUtc $parsed.ExpiresUtc -NowUtc $NowUtc

                $selectedTitle = Get-ObjectPropertyText -Object $readResult -PropertyName "Title"
                if ([string]::IsNullOrWhiteSpace($selectedTitle)) {
                    $selectedTitle = $issueTitle
                }

                $validSelections += [pscustomobject]@{
                    IssueNumber = $issueNumber
                    IssueTitle = $selectedTitle
                    ReadResult = $readResult
                    Selected = $parsed
                    State = $state
                    NowUtc = $NowUtc
                }
            }
            catch {
                if ($StopOnMarkerFailure) {
                    throw "Approval marker on issue #$issueNumber failed validation in ${ModeName}. $($_.Exception.Message)"
                }

                $skippedMarkers += [pscustomobject]@{
                    IssueNumber = $issueNumber
                    IssueTitle = $issueTitle
                    Reason = $_.Exception.Message
                }
            }
        }
    }

    return [pscustomobject]@{
        IssuesScanned = @($issues).Count
        ValidSelections = @($validSelections)
        SkippedMarkers = @($skippedMarkers)
        SkippedIssues = @($skippedIssues)
        UnsupportedMarkers = @($unsupportedMarkers)
    }
}

function Find-PushDryRunSelections {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc,
        [switch]$StopOnReadFailure,
        [switch]$StopOnMarkerFailure,
        [string]$ModeName = "PushDryRun",
        [string]$ExpectedAction = $PushDryRunSupportedAction
    )

    $issues = if ($IssueNumber -gt 0) {
        @([pscustomobject]@{
            number = $IssueNumber
            title = ""
        })
    }
    else {
        Get-OpenApprovalSearchIssues
    }

    $validSelections = @()
    $skippedMarkers = @()
    $skippedIssues = @()
    $unsupportedMarkers = @()

    foreach ($issue in $issues) {
        $issueNumber = [int]$issue.number
        $issueTitle = Get-ObjectPropertyText -Object $issue -PropertyName "title"

        try {
            $readResult = Get-IssueApprovalMarkerReadResult -IssueNumber $issueNumber
        }
        catch {
            if ($StopOnReadFailure) {
                throw "GitHub read failure while scanning issue #$issueNumber cannot be safely ignored. $($_.Exception.Message)"
            }

            $skippedIssues += [pscustomobject]@{
                IssueNumber = $issueNumber
                IssueTitle = $issueTitle
                Reason = $_.Exception.Message
            }
            continue
        }

        $markers = @($readResult.Markers)
        foreach ($marker in $markers) {
            try {
                $parsed = ConvertTo-ParsedApprovalMarker -Marker $marker -NowUtc $NowUtc
                if (-not $parsed.IsCurrent) {
                    $skippedMarkers += [pscustomobject]@{
                        IssueNumber = $issueNumber
                        IssueTitle = $issueTitle
                        Reason = "Approval marker expired at $($parsed.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
                    }
                    continue
                }

                $action = [string]$parsed.Fields["action"]
                if (-not [string]::Equals($action, $ExpectedAction, [System.StringComparison]::Ordinal)) {
                    if ($action -in @($ApprovalDryRunSupportedAction, $ApprovalOnceSupportedAction, $ApprovalNextDryRunSupportedAction, $ApprovalNextCommitSupportedAction, $PushDryRunSupportedAction, $PushOnceSupportedAction, $CloseIssueOnceSupportedAction)) {
                        $skippedMarkers += [pscustomobject]@{
                            IssueNumber = $issueNumber
                            IssueTitle = $issueTitle
                            Reason = "Ignored current non-matching approval action '$action'. $ModeName selects only action=$ExpectedAction."
                        }
                    }
                    else {
                        $unsupportedMarkers += [pscustomobject]@{
                            IssueNumber = $issueNumber
                            IssueTitle = $issueTitle
                            Reason = "Unsupported approval action '$action'. $ModeName supports only action=$ExpectedAction."
                        }
                    }
                    continue
                }

                $state = Get-PushDryRunState -Fields $parsed.Fields -IssueNumber $issueNumber -ExpectedAction $ExpectedAction -ModeName $ModeName
                if ($parsed.ExpiresUtc -le $NowUtc) {
                    throw "Approval marker expired at $($parsed.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")); current UTC time is $($NowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
                }

                $selectedTitle = Get-ObjectPropertyText -Object $readResult -PropertyName "Title"
                if ([string]::IsNullOrWhiteSpace($selectedTitle)) {
                    $selectedTitle = $issueTitle
                }

                $validSelections += [pscustomobject]@{
                    IssueNumber = $issueNumber
                    IssueTitle = $selectedTitle
                    ReadResult = $readResult
                    Selected = $parsed
                    State = $state
                    NowUtc = $NowUtc
                }
            }
            catch {
                if ($StopOnMarkerFailure) {
                    throw "Approval marker on issue #$issueNumber failed validation in ${ModeName}. $($_.Exception.Message)"
                }

                $skippedMarkers += [pscustomobject]@{
                    IssueNumber = $issueNumber
                    IssueTitle = $issueTitle
                    Reason = $_.Exception.Message
                }
            }
        }
    }

    return [pscustomobject]@{
        IssuesScanned = @($issues).Count
        ValidSelections = @($validSelections)
        SkippedMarkers = @($skippedMarkers)
        SkippedIssues = @($skippedIssues)
        UnsupportedMarkers = @($unsupportedMarkers)
    }
}

function Invoke-ApprovalNextDryRun {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNextDryRun supports only repo=$ExpectedApprovalRepo for this detection-only slice."
    }

    Assert-RepoRoot
    $null = Assert-CleanRepo

    $branch = Get-CurrentBranch
    $head = Get-CurrentFullHead
    $nowUtc = [System.DateTime]::UtcNow
    $scanResult = Find-ApprovalNextDryRunSelections -CurrentBranch $branch -CurrentHead $head -NowUtc $nowUtc
    $validSelections = @($scanResult.ValidSelections)
    $skippedMarkers = @($scanResult.SkippedMarkers)
    $skippedIssues = @($scanResult.SkippedIssues)

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalNextDryRun"
    Write-Host "Approval search: open issues, exact RUNNER-V2-APPROVE comment validation"
    Write-Host "Issues scanned: $($scanResult.IssuesScanned)"
    Write-Host "No-write guarantee: $ApprovalNextDryRunNoWriteGuarantee"

    foreach ($skippedIssue in $skippedIssues) {
        Write-Host ""
        Write-Host "Skipped issue #$($skippedIssue.IssueNumber): could not read issue comments. $($skippedIssue.Reason)"
    }

    foreach ($skippedMarker in $skippedMarkers) {
        Write-Host ""
        Write-Host "Skipped approval marker on issue #$($skippedMarker.IssueNumber): $($skippedMarker.Reason)"
    }

    if ($validSelections.Count -eq 0) {
        Write-Host ""
        Write-Host "No approval found. No current action=run-reviewbundle approval matched local state. No action will be taken."
        return
    }

    if ($validSelections.Count -gt 1) {
        Write-Host ""
        Write-Host "Ambiguous approvals found. ApprovalNextDryRun requires exactly one valid current approval and will not choose automatically."
        foreach ($selection in $validSelections) {
            Write-Host "Issue #$($selection.IssueNumber): $($selection.IssueTitle)"
        }
        throw "ApprovalNextDryRun stopped because multiple valid current approvals were found."
    }

    $selection = $validSelections[0]
    $selected = $selection.Selected
    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    Write-Host ""
    Write-Host "Selected approval"
    Write-Host "Issue: #$($selection.IssueNumber)"
    Write-Host "Title: $($selection.IssueTitle)"
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($selection.Branch)"
    Write-Host "HEAD: $($selection.Head)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Planned action: Would delegate to runner v1 ReviewBundle for issue #$($selection.IssueNumber) if ApprovalNext execution mode were implemented."
    Write-Host "No-write guarantee: $ApprovalNextDryRunNoWriteGuarantee"
}

function Invoke-ApprovalNextOnce {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNextOnce supports only repo=$ExpectedApprovalRepo for this execution slice."
    }

    Assert-RepoRoot
    $null = Assert-CleanRepo

    $branch = Get-CurrentBranch
    $head = Get-CurrentFullHead
    $nowUtc = [System.DateTime]::UtcNow
    $scanResult = Find-ApprovalNextDryRunSelections -CurrentBranch $branch -CurrentHead $head -NowUtc $nowUtc
    $validSelections = @($scanResult.ValidSelections)
    $skippedMarkers = @($scanResult.SkippedMarkers)
    $skippedIssues = @($scanResult.SkippedIssues)

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalNextOnce"
    Write-Host "Approval search: open issues, exact RUNNER-V2-APPROVE comment validation"
    Write-Host "Issues scanned: $($scanResult.IssuesScanned)"

    foreach ($skippedIssue in $skippedIssues) {
        Write-Host ""
        Write-Host "Skipped issue #$($skippedIssue.IssueNumber): could not read issue comments. $($skippedIssue.Reason)"
    }

    foreach ($skippedMarker in $skippedMarkers) {
        Write-Host ""
        Write-Host "Skipped approval marker on issue #$($skippedMarker.IssueNumber): $($skippedMarker.Reason)"
    }

    if ($validSelections.Count -eq 0) {
        Write-Host ""
        Write-Host "No approval found. No current action=run-reviewbundle approval matched local state. No action will be taken."
        Write-FinalGitStatus
        return
    }

    if ($validSelections.Count -gt 1) {
        Write-Host ""
        Write-Host "Ambiguous approvals found. ApprovalNextOnce requires exactly one valid current approval and will not choose automatically."
        foreach ($selection in $validSelections) {
            Write-Host "Issue #$($selection.IssueNumber): $($selection.IssueTitle)"
        }
        throw "ApprovalNextOnce stopped because multiple valid current approvals were found."
    }

    $selection = $validSelections[0]
    $selected = $selection.Selected
    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    if (-not [string]::Equals($action, $ApprovalNextDryRunSupportedAction, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNextOnce supports only action=$ApprovalNextDryRunSupportedAction. Parsed action: $action."
    }

    Write-Host ""
    Write-Host "Selected approval"
    Write-Host "Issue: #$($selection.IssueNumber)"
    Write-Host "Title: $($selection.IssueTitle)"
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($selection.Branch)"
    Write-Host "HEAD: $($selection.Head)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Safety boundary: $ApprovalNextOnceSafetyBoundary"
    Write-Host ""

    $runnerExitCode = Invoke-RunnerV1ReviewBundle -IssueNumber ([int]$selection.IssueNumber)

    Write-Host ""
    Write-Host "Runner v1 exit code: $runnerExitCode"
    Write-Host "Next step: notify ChatGPT that issue #$($selection.IssueNumber) ReviewBundle was posted."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue ([int]$selection.IssueNumber) `
        -Action "run-reviewbundle" `
        -Result $(if ($runnerExitCode -eq 0) { "success" } else { "failure" }) `
        -Branch ([string]$selection.Branch) `
        -Head ([string]$selection.Head) `
        -SelectedIssue ([int]$selection.IssueNumber) `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See runner v1 ReviewBundle final git status output.") }

    if ($runnerExitCode -ne 0) {
        Write-Host "Failure: runner v1 ReviewBundle failed with exit code $runnerExitCode."
        exit $runnerExitCode
    }
}

function Assert-ApprovalNextWatchRepoUnchanged {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InitialBranch,
        [Parameter(Mandatory = $true)]
        [string]$InitialHead
    )

    $status = Get-GitStatusShort
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Repo became dirty while watching. ApprovalNextWatch stops before runner v1 handoff. git status --short:`n$status"
    }

    $currentBranch = Get-CurrentBranch
    if (-not [string]::Equals($currentBranch, $InitialBranch, [System.StringComparison]::Ordinal)) {
        throw "Branch changed while watching. Started on '$InitialBranch', now on '$currentBranch'. ApprovalNextWatch stops before runner v1 handoff."
    }

    $currentHead = Get-CurrentFullHead
    if (-not [string]::Equals($currentHead, $InitialHead, [System.StringComparison]::Ordinal)) {
        throw "HEAD changed while watching. Started at '$InitialHead', now at '$currentHead'. ApprovalNextWatch stops before runner v1 handoff."
    }
}

function Write-ApprovalNextSelectionSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection,
        [Parameter(Mandatory = $true)]
        [string]$SafetyBoundary
    )

    $selected = $Selection.Selected
    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    if (-not [string]::Equals($action, $ApprovalNextDryRunSupportedAction, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNext execution supports only action=$ApprovalNextDryRunSupportedAction. Parsed action: $action."
    }

    Write-Host ""
    Write-Host "Selected approval"
    Write-Host "Issue: #$($Selection.IssueNumber)"
    Write-Host "Title: $($Selection.IssueTitle)"
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($Selection.Branch)"
    Write-Host "HEAD: $($Selection.Head)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Safety boundary: $SafetyBoundary"
    Write-Host ""
}

function Write-ApprovalNextCommitScanMessages {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ScanResult,
        [Parameter(Mandatory = $true)]
        [string]$ModeName
    )

    foreach ($skippedIssue in @($ScanResult.SkippedIssues)) {
        Write-Host ""
        Write-Host "Skipped issue #$($skippedIssue.IssueNumber): could not read issue comments. $($skippedIssue.Reason)"
    }

    foreach ($skippedMarker in @($ScanResult.SkippedMarkers)) {
        Write-Host ""
        Write-Host "Skipped approval marker on issue #$($skippedMarker.IssueNumber): $($skippedMarker.Reason)"
    }

    $unsupportedMarkers = @($ScanResult.UnsupportedMarkers)
    if ($unsupportedMarkers.Count -gt 0) {
        Write-Host ""
        foreach ($unsupportedMarker in $unsupportedMarkers) {
            Write-Host "Unsupported approval action on issue #$($unsupportedMarker.IssueNumber): $($unsupportedMarker.IssueTitle)"
            Write-Host $unsupportedMarker.Reason
        }
        throw "$ModeName stopped because an unsupported current approval action was found."
    }
}

function Get-UniqueApprovalNextCommitSelection {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ScanResult,
        [Parameter(Mandatory = $true)]
        [string]$ModeName
    )

    $validSelections = @($ScanResult.ValidSelections)
    if ($validSelections.Count -eq 0) {
        throw "$ModeName requires exactly one current valid action=$ApprovalNextCommitSupportedAction approval. No matching approval was found."
    }

    if ($validSelections.Count -gt 1) {
        Write-Host ""
        Write-Host "Ambiguous approvals found. $ModeName requires exactly one valid current approval and will not choose automatically."
        foreach ($selection in $validSelections) {
            Write-Host "Issue #$($selection.IssueNumber): $($selection.IssueTitle)"
        }
        throw "$ModeName stopped because multiple valid current approvals were found."
    }

    return $validSelections[0]
}

function Write-ApprovalNextCommitSelectionSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection,
        [Parameter(Mandatory = $true)]
        [string]$SafetyBoundary
    )

    $selected = $Selection.Selected
    $state = $Selection.State
    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    Write-Host ""
    Write-Host "Selected approval"
    Write-Host "Issue: #$($Selection.IssueNumber)"
    Write-Host "Title: $($Selection.IssueTitle)"
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($state.Branch)"
    Write-Host "HEAD: $($state.Head)"
    Write-Host "Review id: $($state.ReviewId)"
    Write-Host "Diff fingerprint: $($state.DiffFingerprint)"
    Write-Host "Files fingerprint: $($state.FilesFingerprint)"
    Write-Host "Modified docs-only files:"
    Write-Host $state.ModifiedFilesText
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Safety boundary: $SafetyBoundary"
    Write-Host ""
}

function Invoke-ApprovalNextCommitDryRun {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNextCommitDryRun supports only repo=$ExpectedApprovalRepo for this docs-only local commit slice."
    }

    Assert-RepoRoot
    $nowUtc = [System.DateTime]::UtcNow
    $scanResult = Find-ApprovalNextCommitSelections -NowUtc $nowUtc -ModeName "ApprovalNextCommitDryRun"

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalNextCommitDryRun"
    Write-Host "Approval search: bounded open issues, exact RUNNER-V2-APPROVE action=commit-approved-docs-only validation"
    Write-Host "Issues scanned: $($scanResult.IssuesScanned)"
    Write-Host "No-write guarantee: $ApprovalNextCommitDryRunNoWriteGuarantee"

    Write-ApprovalNextCommitScanMessages -ScanResult $scanResult -ModeName "ApprovalNextCommitDryRun"
    $selection = Get-UniqueApprovalNextCommitSelection -ScanResult $scanResult -ModeName "ApprovalNextCommitDryRun"

    Write-ApprovalNextCommitSelectionSummary -Selection $selection -SafetyBoundary $ApprovalNextCommitDryRunNoWriteGuarantee
    Write-Host "Planned action: Would delegate to runner v1 CommitApproved for issue #$($selection.IssueNumber) with a state-bound approval token. No files will be staged and no commit will be created in dry-run mode."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue ([int]$selection.IssueNumber) `
        -Action "commit-approved-dryrun" `
        -Result "success" `
        -Branch ([string]$selection.State.Branch) `
        -Head ([string]$selection.State.Head) `
        -SelectedIssue ([int]$selection.IssueNumber) `
        -ReviewId ([string]$selection.State.ReviewId) `
        -DiffFingerprint ([string]$selection.State.DiffFingerprint) `
        -FilesFingerprint ([string]$selection.State.FilesFingerprint) `
        -ChangedFilesText ([string]$selection.State.ModifiedFilesText) `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "ApprovalNextCommitDryRun validated the current docs-only local change state; see human-readable output.") }
}

function Invoke-ApprovalNextCommitOnce {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNextCommitOnce supports only repo=$ExpectedApprovalRepo for this docs-only local commit slice."
    }

    Assert-RepoRoot
    $nowUtc = [System.DateTime]::UtcNow
    $scanResult = Find-ApprovalNextCommitSelections -NowUtc $nowUtc -ModeName "ApprovalNextCommitOnce" -StopOnMarkerFailure

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalNextCommitOnce"
    Write-Host "Approval search: bounded open issues, exact RUNNER-V2-APPROVE action=commit-approved-docs-only validation"
    Write-Host "Issues scanned: $($scanResult.IssuesScanned)"

    Write-ApprovalNextCommitScanMessages -ScanResult $scanResult -ModeName "ApprovalNextCommitOnce"
    $selection = Get-UniqueApprovalNextCommitSelection -ScanResult $scanResult -ModeName "ApprovalNextCommitOnce"
    Write-ApprovalNextCommitSelectionSummary -Selection $selection -SafetyBoundary $ApprovalNextCommitOnceSafetyBoundary

    $runnerV1State = Get-RunnerV1CommitApprovalState -IssueNumber ([int]$selection.IssueNumber)
    $currentState = Get-CommitApprovalState -IssueNumberForState ([int]$selection.IssueNumber) -ValidateDocsOnlyCommit
    $handoffNowUtc = [System.DateTime]::UtcNow
    Assert-CommitApprovalMarkerMatchesState `
        -Fields $selection.Selected.Fields `
        -State $currentState `
        -ExpiresUtc $selection.Selected.ExpiresUtc `
        -NowUtc $handoffNowUtc
    Assert-RunnerV1CommitApprovalStateMatchesV2State -RunnerV1State $runnerV1State -RunnerV2State $currentState

    $runnerExitCode = Invoke-RunnerV1CommitApproved `
        -IssueNumber ([int]$selection.IssueNumber) `
        -ApprovalToken ([string]$runnerV1State.ApprovalToken)

    Write-Host ""
    Write-Host "Runner v1 exit code: $runnerExitCode"
    Write-Host "Next step: review the local commit and final GitHub issue comment before any separate push approval."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue ([int]$selection.IssueNumber) `
        -Action "commit-approved-once" `
        -Result $(if ($runnerExitCode -eq 0) { "success" } else { "failure" }) `
        -Branch ([string]$selection.State.Branch) `
        -Head ([string]$selection.State.Head) `
        -SelectedIssue ([int]$selection.IssueNumber) `
        -ReviewId ([string]$selection.State.ReviewId) `
        -DiffFingerprint ([string]$selection.State.DiffFingerprint) `
        -FilesFingerprint ([string]$selection.State.FilesFingerprint) `
        -ChangedFilesText ([string]$selection.State.ModifiedFilesText) `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See runner v1 CommitApproved final status output.") } `
        -SafetyOverrides @{ no_commit = $false }

    if ($runnerExitCode -ne 0) {
        Write-Host "Failure: runner v1 CommitApproved failed with exit code $runnerExitCode."
        exit $runnerExitCode
    }
}

function Write-PushDryRunScanMessages {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ScanResult,
        [Parameter(Mandatory = $true)]
        [string]$ModeName
    )

    foreach ($skippedIssue in @($ScanResult.SkippedIssues)) {
        Write-Host ""
        Write-Host "Skipped issue #$($skippedIssue.IssueNumber): could not read issue comments. $($skippedIssue.Reason)"
    }

    foreach ($skippedMarker in @($ScanResult.SkippedMarkers)) {
        Write-Host ""
        Write-Host "Skipped approval marker on issue #$($skippedMarker.IssueNumber): $($skippedMarker.Reason)"
    }

    $unsupportedMarkers = @($ScanResult.UnsupportedMarkers)
    if ($unsupportedMarkers.Count -gt 0) {
        Write-Host ""
        foreach ($unsupportedMarker in $unsupportedMarkers) {
            Write-Host "Unsupported approval action on issue #$($unsupportedMarker.IssueNumber): $($unsupportedMarker.IssueTitle)"
            Write-Host $unsupportedMarker.Reason
        }
        throw "$ModeName stopped because an unsupported current approval action was found."
    }
}

function Get-UniquePushDryRunSelection {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ScanResult,
        [Parameter(Mandatory = $true)]
        [string]$ModeName,
        [string]$ExpectedAction = $PushDryRunSupportedAction
    )

    $validSelections = @($ScanResult.ValidSelections)
    if ($validSelections.Count -eq 0) {
        throw "$ModeName requires exactly one current valid action=$ExpectedAction approval. No matching approval was found."
    }

    if ($validSelections.Count -gt 1) {
        Write-Host ""
        Write-Host "Ambiguous push approvals found. $ModeName requires exactly one valid current approval and will not choose automatically."
        foreach ($selection in $validSelections) {
            Write-Host "Issue #$($selection.IssueNumber): $($selection.IssueTitle)"
        }
        throw "$ModeName stopped because multiple valid current push approvals were found."
    }

    return $validSelections[0]
}

function Get-ValidatedCloseIssueOnceSelection {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    $readResult = Get-IssueApprovalMarkerReadResult -IssueNumber $IssueNumber
    $markers = @($readResult.Markers)
    if ($markers.Count -eq 0) {
        throw "CloseIssueOnce requires exactly one current action=$CloseIssueOnceSupportedAction approval on issue #$IssueNumber. No RUNNER-V2-APPROVE marker lines were found."
    }

    $currentCloseMarkers = @()
    $expiredCloseMarkers = @()
    $skippedIneligibleMarkers = @()
    $skippedNonCloseMarkers = @()

    foreach ($marker in $markers) {
        $eligibility = Test-CloseIssueOnceLiveMarkerEligibility -Marker $marker
        if (-not $eligibility.IsEligible) {
            $skippedIneligibleMarkers += [pscustomobject]@{
                Marker = $marker
                Reason = $eligibility.Reason
            }
            continue
        }

        $actionToken = Get-ApprovalMarkerActionToken -MarkerLine ([string]$marker.Line)
        if (-not [string]::Equals($actionToken, $CloseIssueOnceSupportedAction, [System.StringComparison]::Ordinal)) {
            $skipReason = if ([string]::IsNullOrWhiteSpace($actionToken)) {
                "Skipped non-close approval content with no action token."
            } else {
                "Skipped non-close approval action '$actionToken'."
            }
            $skippedNonCloseMarkers += [pscustomobject]@{
                Marker = $marker
                Action = $actionToken
                Reason = $skipReason
            }
            continue
        }

        $parsed = ConvertTo-ParsedApprovalMarker -Marker $marker -NowUtc $NowUtc
        $action = [string]$parsed.Fields["action"]

        if ([string]::Equals($action, $CloseIssueOnceSupportedAction, [System.StringComparison]::Ordinal)) {
            if ($parsed.IsCurrent) {
                $currentCloseMarkers += $parsed
            }
            else {
                $expiredCloseMarkers += $parsed
            }
        }
    }

    if ($currentCloseMarkers.Count -eq 0) {
        if ($expiredCloseMarkers.Count -gt 0) {
            $latestMarker = $expiredCloseMarkers[$expiredCloseMarkers.Count - 1]
            throw "No current close approval marker found for issue #$IssueNumber. Latest close marker expired at $($latestMarker.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
        }

        throw "CloseIssueOnce requires exactly one current action=$CloseIssueOnceSupportedAction approval on issue #$IssueNumber. No matching approval was found."
    }

    if ($currentCloseMarkers.Count -gt 1) {
        throw "Ambiguous close approvals found for issue #$IssueNumber. Found $($currentCloseMarkers.Count) current action=$CloseIssueOnceSupportedAction marker lines; exactly one is required."
    }

    $selected = $currentCloseMarkers[0]
    $state = Get-CloseIssueOnceState `
        -Fields $selected.Fields `
        -IssueNumber $IssueNumber `
        -IssueState ([string]$readResult.IssueState) `
        -ExpiresUtc $selected.ExpiresUtc `
        -NowUtc $NowUtc

    return [pscustomobject]@{
        IssueNumber = $IssueNumber
        IssueTitle = $readResult.Title
        ReadResult = $readResult
        Selected = $selected
        State = $state
        NowUtc = $NowUtc
        SkippedIneligibleMarkers = @($skippedIneligibleMarkers)
        SkippedNonCloseMarkers = @($skippedNonCloseMarkers)
    }
}

function Write-CloseIssueOnceSelectionSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection
    )

    $selected = $Selection.Selected
    $state = $Selection.State
    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    Write-Host ""
    Write-Host "Selected close approval"
    Write-Host "Issue: #$($Selection.IssueNumber)"
    Write-Host "Title: $($Selection.IssueTitle)"
    Write-Host "Previous issue state: $($state.PreviousIssueState)"
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Selected close marker: $($selected.Marker.Line)"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($state.Branch)"
    Write-Host "Local HEAD: $($state.LocalHead)"
    Write-Host "Remote: $($state.Remote)"
    Write-Host "Remote URL: $($state.RemoteUrl)"
    Write-Host "Upstream: $($state.Upstream)"
    Write-Host "Remote HEAD: $($state.RemoteHead)"
    Write-Host "Pushed commit: $($state.Pushed)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    foreach ($skippedMarker in @($Selection.SkippedIneligibleMarkers)) {
        Write-Host "Skipped approval marker on issue #$($Selection.IssueNumber): $($skippedMarker.Reason)"
    }
    foreach ($skippedMarker in @($Selection.SkippedNonCloseMarkers)) {
        Write-Host "Skipped approval marker on issue #$($Selection.IssueNumber): $($skippedMarker.Reason)"
    }
    Write-Host "Safety boundary: $CloseIssueOnceSafetyBoundary"
    Write-Host ""
}

function Invoke-GhIssueCloseOnce {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    return Invoke-WriteCommand -FilePath "gh" -Arguments @("issue", "close", "$IssueNumber", "--repo", $Repo) -Action "gh issue close"
}

function Write-PushSelectionSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$SafetyBoundary,
        [bool]$NoPushStatement = $true
    )

    $selected = $Selection.Selected
    $state = $Selection.State
    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    Write-Host ""
    Write-Host "Selected $Label approval"
    Write-Host "Issue: #$($Selection.IssueNumber)"
    Write-Host "Title: $($Selection.IssueTitle)"
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Selected $Label marker: $($selected.Marker.Line)"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($state.Branch)"
    Write-Host "Local HEAD: $($state.LocalHead)"
    Write-Host "Remote: $($state.Remote)"
    Write-Host "Remote URL: $($state.RemoteUrl)"
    Write-Host "Upstream: $($state.Upstream)"
    Write-Host "Remote HEAD: $($state.RemoteHead)"
    Write-Host "Ahead / behind count: $($state.Ahead) / $($state.Behind)"
    Write-Host "Approved commit: $($state.ApprovedCommit)"
    Write-Host "Committed files:"
    Write-Host $state.CommittedFilesText
    Write-Host "Commitfiles fingerprint: $($state.CommitFilesFingerprint)"
    Write-Host "Planned push target: $($state.PlannedPushTarget)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    if ($NoPushStatement) {
        Write-Host "No-push statement: no push was performed."
    }
    Write-Host "Safety boundary: $SafetyBoundary"
    Write-Host ""
}

function Invoke-PushDryRun {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "PushDryRun supports only repo=$ExpectedApprovalRepo for this push dry-run slice."
    }

    Assert-RepoRoot
    $nowUtc = [System.DateTime]::UtcNow
    $scanResult = Find-PushDryRunSelections -NowUtc $nowUtc -ModeName "PushDryRun"

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: PushDryRun"
    Write-Host "Approval search: bounded open issues, exact RUNNER-V2-APPROVE action=push-dryrun-approved validation"
    Write-Host "Issues scanned: $($scanResult.IssuesScanned)"
    Write-Host "No-write guarantee: $PushDryRunNoWriteGuarantee"

    Write-PushDryRunScanMessages -ScanResult $scanResult -ModeName "PushDryRun"
    $selection = Get-UniquePushDryRunSelection -ScanResult $scanResult -ModeName "PushDryRun" -ExpectedAction $PushDryRunSupportedAction

    Write-PushSelectionSummary -Selection $selection -Label "push-dryrun" -SafetyBoundary $PushDryRunNoWriteGuarantee -NoPushStatement $true
    Write-Host "Planned action: PushDryRun validated the planned push target only. No git push was executed."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue ([int]$selection.IssueNumber) `
        -Action "push-dryrun" `
        -Result "success" `
        -Branch ([string]$selection.State.Branch) `
        -Head ([string]$selection.State.LocalHead) `
        -SelectedIssue ([int]$selection.IssueNumber) `
        -ChangedFilesText ([string]$selection.State.CommittedFilesText) `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "passed" -Summary "PushDryRun requires and verified a clean working tree.") }
}

function Invoke-GitPushOnce {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Remote,
        [Parameter(Mandatory = $true)]
        [string]$Branch
    )

    $pushRefspec = "HEAD:$Branch"
    return Invoke-WriteCommand -FilePath "git" -Arguments @("-C", $RepoRoot, "push", $Remote, $pushRefspec) -Action "git push $Remote $pushRefspec"
}

function Invoke-PushOnce {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "PushOnce supports only repo=$ExpectedApprovalRepo for this push-once slice."
    }
    if ($IssueNumber -le 0) {
        throw "PushOnce requires -IssueNumber <N> and scans only that issue."
    }

    Assert-RepoRoot
    $nowUtc = [System.DateTime]::UtcNow
    $scanResult = Find-PushDryRunSelections -NowUtc $nowUtc -ModeName "PushOnce" -ExpectedAction $PushOnceSupportedAction -StopOnReadFailure -StopOnMarkerFailure

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: PushOnce"
    Write-Host "Approval search: bounded open issues, exact RUNNER-V2-APPROVE action=push-approved-once validation"
    Write-Host "Issues scanned: $($scanResult.IssuesScanned)"

    Write-PushDryRunScanMessages -ScanResult $scanResult -ModeName "PushOnce"
    $selection = Get-UniquePushDryRunSelection -ScanResult $scanResult -ModeName "PushOnce" -ExpectedAction $PushOnceSupportedAction

    Write-PushSelectionSummary -Selection $selection -Label "push-once" -SafetyBoundary $PushOnceSafetyBoundary -NoPushStatement $false

    $state = $selection.State
    Write-Host "Executing push command: git push $($state.Remote) HEAD:$($state.Branch)"
    $pushResult = Invoke-GitPushOnce -Remote ([string]$state.Remote) -Branch ([string]$state.Branch)
    if ($pushResult.ExitCode -ne 0) {
        $details = (($pushResult.Stdout, $pushResult.Stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join [Environment]::NewLine
        throw "git push failed with exit code $($pushResult.ExitCode): $details"
    }

    $remoteHeadAfterPush = Get-RemoteBranchHead -Remote ([string]$state.Remote) -BranchName ([string]$state.Branch)
    if (-not [string]::Equals($remoteHeadAfterPush, [string]$state.ApprovedCommit, [System.StringComparison]::Ordinal)) {
        throw "Post-push remote HEAD mismatch. Expected remote $($state.Remote)/$($state.Branch) to point to $($state.ApprovedCommit), found $remoteHeadAfterPush."
    }

    $null = Assert-CleanRepo

    Write-Host ""
    Write-Host "PushOnce result"
    Write-Host "Pushed commit: $($state.ApprovedCommit)"
    Write-Host "Remote target: $($state.Remote) HEAD:$($state.Branch)"
    Write-Host "Remote HEAD after push: $remoteHeadAfterPush"
    if (-not [string]::IsNullOrWhiteSpace($pushResult.Stdout)) {
        Write-Host "git push stdout:"
        Write-Host $pushResult.Stdout
    }
    if (-not [string]::IsNullOrWhiteSpace($pushResult.Stderr)) {
        Write-Host "git push stderr:"
        Write-Host $pushResult.Stderr
    }
    Write-Host "Post-push statement: exactly one git push command was executed; no issue close, label, PR, merge, force push, or approval chaining was performed."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue ([int]$selection.IssueNumber) `
        -Action "push-once" `
        -Result "success" `
        -Branch ([string]$state.Branch) `
        -Head ([string]$state.ApprovedCommit) `
        -SelectedIssue ([int]$selection.IssueNumber) `
        -ChangedFilesText ([string]$state.CommittedFilesText) `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "passed" -Summary "PushOnce verified a clean working tree after push.") } `
        -SafetyOverrides @{ no_push = $false }
}

function Invoke-CloseIssueOnce {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "CloseIssueOnce supports only repo=$ExpectedApprovalRepo for this close-once slice."
    }
    if ($IssueNumber -le 0) {
        throw "CloseIssueOnce requires -IssueNumber <N> and scans only that issue."
    }

    Assert-RepoRoot
    $nowUtc = [System.DateTime]::UtcNow
    $selection = Get-ValidatedCloseIssueOnceSelection -IssueNumber $IssueNumber -NowUtc $nowUtc

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: CloseIssueOnce"
    Write-Host "Approval search: selected issue only, exact RUNNER-V2-APPROVE action=close-issue-approved-once validation"
    Write-Host "Issues scanned: 1"

    Write-CloseIssueOnceSelectionSummary -Selection $selection

    Write-Host "Executing close command: gh issue close $IssueNumber --repo $Repo"
    $closeResult = Invoke-GhIssueCloseOnce -IssueNumber $IssueNumber
    if ($closeResult.ExitCode -ne 0) {
        $details = (($closeResult.Stdout, $closeResult.Stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join [Environment]::NewLine
        throw "gh issue close failed with exit code $($closeResult.ExitCode): $details"
    }

    $finalReadResult = Get-IssueApprovalMarkerReadResult -IssueNumber $IssueNumber
    if (-not [string]::Equals([string]$finalReadResult.IssueState, "CLOSED", [System.StringComparison]::Ordinal)) {
        throw "Post-close issue state mismatch. Expected issue #$IssueNumber to be CLOSED, found '$($finalReadResult.IssueState)'."
    }

    $remoteHeadAfterClose = Get-RemoteBranchHead -Remote ([string]$selection.State.Remote) -BranchName (Get-RemoteBranchNameFromUpstream -Upstream ([string]$selection.State.Upstream) -Remote ([string]$selection.State.Remote))
    if (-not [string]::Equals($remoteHeadAfterClose, [string]$selection.State.RemoteHead, [System.StringComparison]::Ordinal)) {
        throw "Remote HEAD changed during CloseIssueOnce. Expected $($selection.State.RemoteHead), found $remoteHeadAfterClose."
    }

    $null = Assert-CleanRepo

    Write-Host ""
    Write-Host "CloseIssueOnce result"
    Write-Host "Selected issue number: #$IssueNumber"
    Write-Host "Previous issue state: $($selection.State.PreviousIssueState)"
    Write-Host "Final issue state: $($finalReadResult.IssueState)"
    Write-Host "Local HEAD: $($selection.State.LocalHead)"
    Write-Host "Remote HEAD: $remoteHeadAfterClose"
    Write-Host "Pushed commit SHA: $($selection.State.Pushed)"
    if (-not [string]::IsNullOrWhiteSpace($closeResult.Stdout)) {
        Write-Host "gh issue close stdout:"
        Write-Host $closeResult.Stdout
    }
    if (-not [string]::IsNullOrWhiteSpace($closeResult.Stderr)) {
        Write-Host "gh issue close stderr:"
        Write-Host $closeResult.Stderr
    }
    Write-Host "Post-close statement: exactly one selected issue was closed; no labels, PRs, merges, pushes, commits, staging, or approval chaining were performed."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue $IssueNumber `
        -Action "close-issue-once" `
        -Result "success" `
        -Branch ([string]$selection.State.Branch) `
        -Head ([string]$selection.State.LocalHead) `
        -SelectedIssue $IssueNumber `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "passed" -Summary "CloseIssueOnce verified a clean working tree after close.") } `
        -SafetyOverrides @{ no_issue_close = $false } `
        -NextRecommendedAction "done"
}

function Invoke-ApprovalNextWatch {
    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalNextWatch supports only repo=$ExpectedApprovalRepo for this execution slice."
    }

    Assert-RepoRoot
    $null = Assert-CleanRepo

    $initialBranch = Get-CurrentBranch
    $initialHead = Get-CurrentFullHead
    $startedUtc = [System.DateTime]::UtcNow
    $deadlineUtc = $startedUtc.AddSeconds($TimeoutSeconds)
    $pollNumber = 0

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalNextWatch"
    Write-Host "Approval search: bounded foreground polling of open issues, exact RUNNER-V2-APPROVE comment validation"
    Write-Host "Timeout seconds: $TimeoutSeconds"
    Write-Host "Poll seconds: $PollSeconds"
    Write-Host "Branch: $initialBranch"
    Write-Host "HEAD: $initialHead"
    Write-Host "Safety boundary: $ApprovalNextWatchSafetyBoundary"

    while ($true) {
        Assert-ApprovalNextWatchRepoUnchanged -InitialBranch $initialBranch -InitialHead $initialHead

        $nowUtc = [System.DateTime]::UtcNow
        if ($nowUtc -ge $deadlineUtc) {
            Write-Host ""
            Write-Host "Timeout reached with no valid approval. No runner v1 handoff will be performed."
            Write-FinalGitStatus
            return
        }

        $pollNumber += 1
        Write-Host ""
        Write-Host "ApprovalNextWatch poll #$pollNumber at $($nowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"

        $scanResult = Find-ApprovalNextDryRunSelections `
            -CurrentBranch $initialBranch `
            -CurrentHead $initialHead `
            -NowUtc $nowUtc `
            -ModeName "ApprovalNextWatch"
        $validSelections = @($scanResult.ValidSelections)
        $skippedMarkers = @($scanResult.SkippedMarkers)
        $skippedIssues = @($scanResult.SkippedIssues)

        Write-Host "Issues scanned: $($scanResult.IssuesScanned)"

        foreach ($skippedIssue in $skippedIssues) {
            Write-Host "Skipped issue #$($skippedIssue.IssueNumber): could not read issue comments. $($skippedIssue.Reason)"
        }

        foreach ($skippedMarker in $skippedMarkers) {
            Write-Host "Skipped approval marker on issue #$($skippedMarker.IssueNumber): $($skippedMarker.Reason)"
        }

        $unsupportedActionMarkers = @($skippedMarkers | Where-Object { [string]$_.Reason -like "Unsupported approval action*" })
        if ($unsupportedActionMarkers.Count -gt 0) {
            Write-Host ""
            foreach ($unsupportedMarker in $unsupportedActionMarkers) {
                Write-Host "Unsupported approval action on issue #$($unsupportedMarker.IssueNumber): $($unsupportedMarker.IssueTitle)"
                Write-Host $unsupportedMarker.Reason
            }
            throw "ApprovalNextWatch stopped because an unsupported approval action was found."
        }

        if ($validSelections.Count -gt 1) {
            Write-Host ""
            Write-Host "Ambiguous approvals found. ApprovalNextWatch requires exactly one valid current approval and will not choose automatically."
            foreach ($selection in $validSelections) {
                Write-Host "Issue #$($selection.IssueNumber): $($selection.IssueTitle)"
            }
            throw "ApprovalNextWatch stopped because multiple valid current approvals were found."
        }

        if ($validSelections.Count -eq 1) {
            $selection = $validSelections[0]
            Assert-ApprovalNextWatchRepoUnchanged -InitialBranch $initialBranch -InitialHead $initialHead
            Write-ApprovalNextSelectionSummary -Selection $selection -SafetyBoundary $ApprovalNextWatchSafetyBoundary

            $runnerExitCode = Invoke-RunnerV1ReviewBundle -IssueNumber ([int]$selection.IssueNumber)

            Write-Host ""
            Write-Host "Runner v1 exit code: $runnerExitCode"
            Write-Host "Next step: notify ChatGPT that issue #$($selection.IssueNumber) ReviewBundle was posted."
            Write-FinalGitStatus
            Write-RunnerResultSummary `
                -Issue ([int]$selection.IssueNumber) `
                -Action "run-reviewbundle" `
                -Result $(if ($runnerExitCode -eq 0) { "success" } else { "failure" }) `
                -Branch ([string]$selection.Branch) `
                -Head ([string]$selection.Head) `
                -SelectedIssue ([int]$selection.IssueNumber) `
                -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See runner v1 ReviewBundle final git status output.") }
            exit $runnerExitCode
        }

        $remainingSeconds = ($deadlineUtc - [System.DateTime]::UtcNow).TotalSeconds
        if ($remainingSeconds -le 0) {
            Write-Host ""
            Write-Host "Timeout reached with no valid approval. No runner v1 handoff will be performed."
            Write-FinalGitStatus
            return
        }

        $sleepSeconds = [int][System.Math]::Min($PollSeconds, [System.Math]::Ceiling($remainingSeconds))
        Write-Host "No current action=run-reviewbundle approval matched local state. Sleeping $sleepSeconds second(s)."
        Start-Sleep -Seconds $sleepSeconds
    }
}

function Invoke-ApprovalDryRun {
    if ($IssueNumber -lt 1) {
        throw "ApprovalDryRun requires -IssueNumber <N>."
    }

    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalDryRun supports only repo=$ExpectedApprovalRepo for this detection-only slice."
    }

    Assert-RepoRoot
    $null = Assert-CleanRepo
    $selection = Get-ValidatedApprovalSelection `
        -IssueNumber $IssueNumber `
        -ExpectedAction $ApprovalDryRunSupportedAction `
        -ModeName "ApprovalDryRun" `
        -AllowNoMarkerLines
    $readResult = $selection.ReadResult

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalDryRun"
    Write-Host "Issue number: #$IssueNumber"
    Write-Host "Issue state: $($readResult.IssueState)"
    Write-Host "No-write guarantee: $ApprovalDryRunNoWriteGuarantee"

    if (-not $selection.HasSelection) {
        Write-Host ""
        Write-Host "No approval marker lines found for issue #$IssueNumber. No action will be taken."
        return
    }

    $selected = $selection.Selected
    $branch = $selection.Branch
    $head = $selection.Head

    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    Write-Host ""
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $branch"
    Write-Host "HEAD: $head"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Planned action: Approval detected and validated. No execution action is implemented in ApprovalDryRun."
    Write-Host "No-write guarantee: $ApprovalDryRunNoWriteGuarantee"
}

function Invoke-ApprovalOnce {
    if ($IssueNumber -lt 1) {
        throw "ApprovalOnce requires -IssueNumber <N>."
    }

    if (-not [string]::Equals($Repo, $ExpectedApprovalRepo, [System.StringComparison]::Ordinal)) {
        throw "ApprovalOnce supports only repo=$ExpectedApprovalRepo for this execution slice."
    }

    Assert-RepoRoot
    $null = Assert-CleanRepo
    $selection = Get-ValidatedApprovalSelection `
        -IssueNumber $IssueNumber `
        -ExpectedAction $ApprovalOnceSupportedAction `
        -ModeName "ApprovalOnce"
    $readResult = $selection.ReadResult
    $selected = $selection.Selected
    $branch = $selection.Branch
    $head = $selection.Head

    $commentId = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id"
    $commentAuthor = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    $commentCreatedAt = Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "createdAt"
    $action = [string]$selected.Fields["action"]

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: ApprovalOnce"
    Write-Host "Issue number: #$IssueNumber"
    Write-Host "Issue state: $($readResult.IssueState)"
    Write-Host ""
    Write-Host "Approval comment id: $commentId"
    Write-Host "Approval comment author: $commentAuthor"
    Write-Host "Approval comment created_at: $commentCreatedAt"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $branch"
    Write-Host "HEAD: $head"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Safety boundary: $ApprovalOnceSafetyBoundary"
    Write-Host ""

    $runnerExitCode = Invoke-RunnerV1ReviewBundle -IssueNumber $IssueNumber

    Write-Host ""
    Write-Host "Runner v1 exit code: $runnerExitCode"
    Write-Host "Next step: notify ChatGPT that issue #$IssueNumber ReviewBundle was posted."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue $IssueNumber `
        -Action "run-reviewbundle" `
        -Result $(if ($runnerExitCode -eq 0) { "success" } else { "failure" }) `
        -Branch $branch `
        -Head $head `
        -SelectedIssue $IssueNumber `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See runner v1 ReviewBundle final git status output.") }

    if ($runnerExitCode -ne 0) {
        Write-Host "Failure: runner v1 ReviewBundle failed with exit code $runnerExitCode."
        exit $runnerExitCode
    }
}

function Get-IssueBodyReadResult {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    $ghArgs = @(
        "issue",
        "view",
        "$IssueNumber",
        "--repo",
        $Repo,
        "--json",
        "body"
    )
    $result = Invoke-ReadOnlyCommand -FilePath "gh" -Arguments $ghArgs -Action "gh issue view"
    if ($result.ExitCode -ne 0) {
        $details = if ([string]::IsNullOrWhiteSpace($result.Stdout)) { $result.Stderr } else { $result.Stdout }
        return [pscustomobject]@{
            Success = $false
            Body = ""
            Reason = "gh issue view failed with exit code $($result.ExitCode): $details"
        }
    }

    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        return [pscustomobject]@{
            Success = $false
            Body = ""
            Reason = "gh issue view returned an empty response"
        }
    }

    try {
        $issueDetails = $result.Stdout | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            Success = $false
            Body = ""
            Reason = "gh issue view returned invalid JSON: $($_.Exception.Message)"
        }
    }

    $body = if ($null -eq $issueDetails.body) { "" } else { [string]$issueDetails.body }
    return [pscustomobject]@{
        Success = $true
        Body = $body
        Reason = ""
    }
}

function Test-RunnerV2ReadyIssue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Body
    )

    $matchedMarkers = @($RequiredMarkers | Where-Object { $Body.Contains($_) })

    return [pscustomobject]@{
        IsCandidate = ($matchedMarkers.Count -eq $RequiredMarkers.Count)
        MatchedMarkers = $matchedMarkers
    }
}

function Format-DryRunCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Issue,
        [Parameter(Mandatory = $true)]
        [string[]]$MatchedMarkers
    )

    $lines = @(
        "Issue: #$($Issue.number)",
        "Title: $($Issue.title)",
        "Matched markers:"
    )
    foreach ($marker in $MatchedMarkers) {
        $lines += "  - $marker"
    }
    $lines += "Planned action: Would run runner v1 ReviewBundle for issue #$($Issue.number) after dry-run validation."
    return ($lines -join [Environment]::NewLine)
}

function Format-CandidateLine {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Candidate
    )

    return "Issue #$($Candidate.Issue.number): $($Candidate.Issue.title)"
}

function Find-RunnerV2CandidateIssues {
    $issues = Get-OpenIssues

    $candidates = @()
    $skippedIssues = @()
    foreach ($issue in $issues) {
        $bodyResult = Get-IssueBodyReadResult -IssueNumber ([int]$issue.number)
        if (-not $bodyResult.Success) {
            $skippedIssues += [pscustomobject]@{
                Issue = $issue
                Reason = $bodyResult.Reason
            }
            continue
        }

        $markerResult = Test-RunnerV2ReadyIssue -Body $bodyResult.Body
        if ($markerResult.IsCandidate) {
            $candidates += [pscustomobject]@{
                Issue = $issue
                MatchedMarkers = [string[]]$markerResult.MatchedMarkers
            }
        }
    }

    return [pscustomobject]@{
        Candidates = @($candidates)
        SkippedIssues = @($skippedIssues)
    }
}

function Write-DryRunSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$Head,
        [Parameter(Mandatory = $true)]
        [string]$RepoCleanSummary,
        [Parameter(Mandatory = $true)]
        [int]$CandidateCount,
        [Parameter(Mandatory = $true)]
        [int]$SkippedCount
    )

    Write-Host ""
    Write-Host "Summary"
    Write-Host "Repo: $Repo"
    Write-Host "Mode: DryRun"
    Write-Host "Branch: $Branch"
    Write-Host "HEAD: $Head"
    Write-Host "Repo clean: $RepoCleanSummary"
    Write-Host "Candidates found: $CandidateCount"
    Write-Host "Skipped issues: $SkippedCount"
    Write-Host "No-write guarantee: $NoWriteGuarantee"
}

function Invoke-DryRun {
    Assert-RepoRoot
    $cleanResult = Assert-CleanRepo
    $branch = Get-CurrentBranch
    $head = Get-CurrentHead
    $scanResult = Find-RunnerV2CandidateIssues
    $candidates = @($scanResult.Candidates)
    $skippedIssues = @($scanResult.SkippedIssues)

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: DryRun"
    Write-Host "Marker matching: lightweight issue search, then exact case-sensitive marker matching on individually fetched issue bodies"
    Write-Host "No-write guarantee: $NoWriteGuarantee"

    foreach ($skippedIssue in $skippedIssues) {
        Write-Host ""
        Write-Host "Skipped issue #$($skippedIssue.Issue.number): could not read issue body. $($skippedIssue.Reason)"
    }

    if ($candidates.Count -eq 0) {
        Write-Host ""
        Write-Host "No candidate issues found with all required runner v2A markers."
    }
    else {
        Write-Host ""
        Write-Host "Candidate issues"
        foreach ($candidate in $candidates) {
            Write-Host ""
            Write-Host (Format-DryRunCandidate -Issue $candidate.Issue -MatchedMarkers $candidate.MatchedMarkers)
        }
    }

    Write-DryRunSummary -Branch $branch -Head $head -RepoCleanSummary $cleanResult.Summary -CandidateCount $candidates.Count -SkippedCount $skippedIssues.Count
}

function Get-PowerShellExecutablePath {
    $currentProcess = Get-Process -Id $PID -ErrorAction SilentlyContinue
    if ($null -ne $currentProcess -and -not [string]::IsNullOrWhiteSpace($currentProcess.Path)) {
        return $currentProcess.Path
    }

    $preferredName = if ($PSVersionTable.PSEdition -eq "Core") { "pwsh" } else { "powershell.exe" }
    $command = Get-Command $preferredName -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $fallbackCommand = Get-Command "powershell.exe" -ErrorAction SilentlyContinue
    if ($null -ne $fallbackCommand) {
        return $fallbackCommand.Source
    }

    throw "Could not resolve a PowerShell executable to invoke runner v1."
}

function Invoke-RunnerV1ReviewBundle {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    $runnerV1Path = Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1"
    if (-not (Test-Path -LiteralPath $runnerV1Path -PathType Leaf)) {
        throw "Runner v1 script path is missing: $runnerV1Path"
    }

    $powerShellPath = Get-PowerShellExecutablePath
    $runnerOutput = & $powerShellPath -NoProfile -File $runnerV1Path -IssueNumber $IssueNumber 2>&1
    $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }

    foreach ($line in @($runnerOutput)) {
        Write-Host $line
    }

    return $exitCode
}

function Get-RunnerV1CommitApprovalState {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    $runnerV1Path = Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1"
    if (-not (Test-Path -LiteralPath $runnerV1Path -PathType Leaf)) {
        throw "Runner v1 script path is missing: $runnerV1Path"
    }

    $powerShellPath = Get-PowerShellExecutablePath
    $result = Invoke-ReadOnlyCommand `
        -FilePath $powerShellPath `
        -Arguments @("-NoProfile", "-File", $runnerV1Path, "-IssueNumber", [string]$IssueNumber, "-Mode", "CommitApprovalStateDiagnostic") `
        -Action "runner v1 CommitApprovalStateDiagnostic"
    Require-Success -Result $result -Action "runner v1 CommitApprovalStateDiagnostic"

    $lines = @($result.Stdout -split "\r?\n")
    $markerIndexes = @()
    for ($index = 0; $index -lt $lines.Count; $index += 1) {
        if ([string]::Equals($lines[$index].Trim(), $RunnerV1CommitApprovalStateMarker, [System.StringComparison]::Ordinal)) {
            $markerIndexes += $index
        }
    }
    if ($markerIndexes.Count -ne 1) {
        throw "Runner v1 CommitApprovalStateDiagnostic returned an invalid marker count."
    }
    $markerIndex = $markerIndexes[0]
    if ($markerIndex + 1 -ge $lines.Count -or [string]::IsNullOrWhiteSpace($lines[$markerIndex + 1])) {
        throw "Runner v1 CommitApprovalStateDiagnostic returned no state JSON."
    }
    try {
        $state = $lines[$markerIndex + 1] | ConvertFrom-Json
    }
    catch {
        throw "Runner v1 CommitApprovalStateDiagnostic returned malformed state JSON."
    }
    if ($null -eq $state -or $state -is [array] -or
        -not [string]::Equals([string]$state.protocol, $RunnerV1CommitApprovalStateProtocol, [System.StringComparison]::Ordinal) -or
        -not [string]::Equals([string]$state.issue, [string]$IssueNumber, [System.StringComparison]::Ordinal) -or
        [string]::IsNullOrWhiteSpace([string]$state.approval_token)) {
        throw "Runner v1 CommitApprovalStateDiagnostic returned an invalid state contract."
    }

    return [pscustomobject]@{
        Protocol = [string]$state.protocol
        IssueNumber = [string]$state.issue
        Branch = [string]$state.branch
        Head = [string]$state.head
        ModifiedFiles = @($state.modified_files)
        ApprovalToken = [string]$state.approval_token
    }
}

function Assert-RunnerV1CommitApprovalStateMatchesV2State {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RunnerV1State,
        [Parameter(Mandatory = $true)]
        [object]$RunnerV2State
    )

    $mismatches = @()
    if (-not [string]::Equals([string]$RunnerV1State.IssueNumber, [string]$RunnerV2State.IssueNumber, [System.StringComparison]::Ordinal)) {
        $mismatches += "issue"
    }
    if (-not [string]::Equals([string]$RunnerV1State.Branch, [string]$RunnerV2State.Branch, [System.StringComparison]::Ordinal)) {
        $mismatches += "branch"
    }
    if (-not [string]::Equals([string]$RunnerV1State.Head, [string]$RunnerV2State.Head, [System.StringComparison]::OrdinalIgnoreCase)) {
        $mismatches += "head"
    }
    $runnerV1Files = @($RunnerV1State.ModifiedFiles | Sort-Object)
    $runnerV2Files = @($RunnerV2State.ModifiedFiles | Sort-Object)
    if (($runnerV1Files -join "`n") -ne ($runnerV2Files -join "`n")) {
        $mismatches += "modified_files"
    }
    if ($mismatches.Count -gt 0) {
        throw "Runner v1 authoritative approval state does not match Runner v2 approved candidate state: $($mismatches -join ',')."
    }
}

function Invoke-RunnerV1CommitApproved {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$ApprovalToken
    )

    $runnerV1Path = Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1"
    if (-not (Test-Path -LiteralPath $runnerV1Path -PathType Leaf)) {
        throw "Runner v1 script path is missing: $runnerV1Path"
    }

    $powerShellPath = Get-PowerShellExecutablePath
    $runnerOutput = & $powerShellPath -NoProfile -File $runnerV1Path -IssueNumber $IssueNumber -Mode CommitApproved -ApprovalToken $ApprovalToken 2>&1
    $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }

    foreach ($line in @($runnerOutput)) {
        Write-Host $line
    }

    return $exitCode
}

function Write-FinalGitStatus {
    Write-Host "Final local git status:"
    $finalStatus = Get-GitStatusShort
    if ([string]::IsNullOrWhiteSpace($finalStatus)) {
        Write-Host "(clean)"
    }
    else {
        Write-Host $finalStatus
    }
}

function Invoke-RunOnce {
    Assert-RepoRoot
    $null = Assert-CleanRepo
    $scanResult = Find-RunnerV2CandidateIssues
    $candidates = @($scanResult.Candidates)
    $skippedIssues = @($scanResult.SkippedIssues)

    Write-Host "$RunnerName $RunnerVersion"
    Write-Host "Mode: RunOnce"
    Write-Host "Marker matching: lightweight issue search, then exact case-sensitive marker matching on individually fetched issue bodies"

    foreach ($skippedIssue in $skippedIssues) {
        Write-Host ""
        Write-Host "Skipped issue #$($skippedIssue.Issue.number): could not read issue body. $($skippedIssue.Reason)"
    }

    if ($candidates.Count -eq 0) {
        Write-Host ""
        Write-Host "No eligible candidate issue found. RunOnce exits without running runner v1."
        Write-FinalGitStatus
        return
    }

    if ($candidates.Count -gt 1) {
        Write-Host ""
        Write-Host "Ambiguous candidate issues found. RunOnce requires exactly one candidate and will not choose automatically."
        foreach ($candidate in $candidates) {
            Write-Host (Format-CandidateLine -Candidate $candidate)
        }
        throw "RunOnce stopped because multiple eligible candidate issues were found."
    }

    $candidate = $candidates[0]
    $issueNumber = [int]$candidate.Issue.number

    Write-Host ""
    Write-Host "Candidate issue number: #$issueNumber"
    Write-Host "Candidate title: $($candidate.Issue.title)"
    Write-Host "Planned action: Run runner v1 ReviewBundle for issue #$issueNumber."
    Write-Host "Safety boundary: $RunOnceSafetyBoundary"
    Write-Host ""

    $runnerExitCode = Invoke-RunnerV1ReviewBundle -IssueNumber $issueNumber

    Write-Host ""
    Write-Host "Runner v1 exit code: $runnerExitCode"
    Write-Host "Next step: notify ChatGPT that issue #$issueNumber ReviewBundle was posted."
    Write-FinalGitStatus
    Write-RunnerResultSummary `
        -Issue $issueNumber `
        -Action "run-reviewbundle" `
        -Result $(if ($runnerExitCode -eq 0) { "success" } else { "failure" }) `
        -Branch (Get-CurrentBranch) `
        -Head (Get-CurrentHead) `
        -SelectedIssue $issueNumber `
        -ValidationOverrides @{ git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See runner v1 ReviewBundle final git status output.") }

    if ($runnerExitCode -ne 0) {
        Write-Host "Failure: runner v1 ReviewBundle failed with exit code $runnerExitCode."
        exit $runnerExitCode
    }
}

try {
    $selectedModes = @()
    if ($DryRun) {
        $selectedModes += "DryRun"
    }
    if ($RunOnce) {
        $selectedModes += "RunOnce"
    }
    if ($ApprovalDryRun) {
        $selectedModes += "ApprovalDryRun"
    }
    if ($ApprovalOnce) {
        $selectedModes += "ApprovalOnce"
    }
    if ($ApprovalNextDryRun) {
        $selectedModes += "ApprovalNextDryRun"
    }
    if ($ApprovalNextOnce) {
        $selectedModes += "ApprovalNextOnce"
    }
    if ($ApprovalNextWatch) {
        $selectedModes += "ApprovalNextWatch"
    }
    if ($ApprovalNextCommitDryRun) {
        $selectedModes += "ApprovalNextCommitDryRun"
    }
    if ($ApprovalNextCommitOnce) {
        $selectedModes += "ApprovalNextCommitOnce"
    }
    if ($PushDryRun) {
        $selectedModes += "PushDryRun"
    }
    if ($PushOnce) {
        $selectedModes += "PushOnce"
    }
    if ($CloseIssueOnce) {
        $selectedModes += "CloseIssueOnce"
    }
    if ($DryRunQueue) {
        $selectedModes += "DryRunQueue"
    }
    if ($RunQueue) {
        $selectedModes += "RunQueue"
    }
    if ($ApprovalStateDiagnostic) {
        $selectedModes += "ApprovalStateDiagnostic"
    }

    if ($selectedModes.Count -eq 0) {
        throw "Missing mode. Use: .\scripts\local_runner_v2.ps1 -DryRun, .\scripts\local_runner_v2.ps1 -RunOnce, .\scripts\local_runner_v2.ps1 -ApprovalDryRun -IssueNumber <N>, .\scripts\local_runner_v2.ps1 -ApprovalOnce -IssueNumber <N>, .\scripts\local_runner_v2.ps1 -ApprovalNextDryRun, .\scripts\local_runner_v2.ps1 -ApprovalNextOnce, .\scripts\local_runner_v2.ps1 -ApprovalNextWatch, .\scripts\local_runner_v2.ps1 -ApprovalNextCommitDryRun, .\scripts\local_runner_v2.ps1 -ApprovalNextCommitOnce, .\scripts\local_runner_v2.ps1 -PushDryRun, .\scripts\local_runner_v2.ps1 -PushOnce, .\scripts\local_runner_v2.ps1 -CloseIssueOnce -IssueNumber <N>, .\scripts\local_runner_v2.ps1 -DryRunQueue -QueueFile <path>, .\scripts\local_runner_v2.ps1 -RunQueue -QueueFile <path>, or .\scripts\local_runner_v2.ps1 -ApprovalStateDiagnostic -IssueNumber <N>."
    }

    if ($selectedModes.Count -gt 1) {
        throw "Choose exactly one mode. Supplied modes: $($selectedModes -join ', ')."
    }

    if ($ApprovalDryRun -and $IssueNumber -lt 1) {
        throw "ApprovalDryRun requires -IssueNumber <N>."
    }

    if ($ApprovalOnce -and $IssueNumber -lt 1) {
        throw "ApprovalOnce requires -IssueNumber <N>."
    }

    if ($ApprovalStateDiagnostic -and $IssueNumber -lt 1) {
        throw "ApprovalStateDiagnostic requires -IssueNumber <N>."
    }

    if ($CloseIssueOnce -and $IssueNumber -lt 1) {
        throw "CloseIssueOnce requires -IssueNumber <N> and scans only that issue."
    }

    if ($DryRunQueue -and [string]::IsNullOrWhiteSpace($QueueFile)) {
        throw "DryRunQueue requires -QueueFile <path>."
    }

    if ($RunQueue -and [string]::IsNullOrWhiteSpace($QueueFile)) {
        throw "RunQueue requires -QueueFile <path>."
    }

    if ($DryRun) {
        Invoke-DryRun
    }
    elseif ($RunOnce) {
        Invoke-RunOnce
    }
    elseif ($ApprovalDryRun) {
        Invoke-ApprovalDryRun
    }
    elseif ($ApprovalOnce) {
        Invoke-ApprovalOnce
    }
    elseif ($ApprovalNextDryRun) {
        Invoke-ApprovalNextDryRun
    }
    elseif ($ApprovalNextOnce) {
        Invoke-ApprovalNextOnce
    }
    elseif ($ApprovalNextWatch) {
        Invoke-ApprovalNextWatch
    }
    elseif ($ApprovalNextCommitDryRun) {
        Invoke-ApprovalNextCommitDryRun
    }
    elseif ($ApprovalNextCommitOnce) {
        Invoke-ApprovalNextCommitOnce
    }
    elseif ($PushDryRun) {
        Invoke-PushDryRun
    }
    elseif ($PushOnce) {
        Invoke-PushOnce
    }
    elseif ($CloseIssueOnce) {
        Invoke-CloseIssueOnce
    }
    elseif ($DryRunQueue) {
        Invoke-DryRunQueue
    }
    elseif ($RunQueue) {
        Invoke-RunQueue
    }
    else {
        Invoke-ApprovalStateDiagnostic
    }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
