<#
.SYNOPSIS
Runs one safe local CHATGPT-DISPATCH poll for an explicit GitHub issue.

.DESCRIPTION
local_dispatcher_v1.ps1 implements manual PollOnce only for
CHATGPT-DISPATCH protocol=lawb.dispatch.v1. It reads only the explicitly
selected issue, validates exactly one current standalone dispatch marker, and
executes only supported bounded dispatcher actions in this slice.

The dispatcher never treats CHATGPT-DISPATCH as approval for commit, push,
issue close, labels, PRs, merges, force push, or approval chaining.

.EXAMPLE
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber 83

.EXAMPLE
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber 83 -PostResultComment
#>

param(
    [switch]$PollOnce,
    [switch]$DryRunBoundedPoll,
    [switch]$BoundedPoll,
    [switch]$ToolResolutionPreflight,
    [string]$RequiredAction = "",
    [switch]$PostResultComment,
    [int]$IssueNumber = 0,
    [int[]]$IssueNumbers = @(),
    [string]$ReviewedCodexPath = "",
    [ValidateNotNullOrEmpty()]
    [string]$Repo = "HarryWhite-TW/local-ai-workbench"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DispatcherName = "local-dispatcher-v1"
$DispatcherVersion = "pollonce-manual"
$ExpectedDispatchRepo = "HarryWhite-TW/local-ai-workbench"
$DispatchMarkerPrefix = "CHATGPT-DISPATCH"
$DispatchProtocol = "lawb.dispatch.v1"
$RunnerResultProtocol = "lawb.runner_result.v1"
$RunnerResultMarker = "LAWBRUNNER-RESULT protocol=$RunnerResultProtocol"
$DryRunProtocol = "lawb.dispatch_dry_run.v1"
$DryRunMarker = "LAWBRUNNER-DRYRUN protocol=$DryRunProtocol"
$ToolResolutionPreflightProtocol = "lawb.rv2_03_tool_resolution_preflight.v1"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$GhCliFallbackPath = "C:\Program Files\GitHub CLI\gh.exe"
$GhCliPortableFallbackPath = Join-Path $env:USERPROFILE "tools\gh-portable\bin\gh.exe"
$MaxDryRunIssuesPerRun = 3
$MaxBoundedPollIssuesPerRun = 3
$AllowedDispatchActions = @("maybe-status-check", "run-reviewbundle")
$TrustedDispatchAuthors = @("HarryWhite-TW")
$ReservedDispatchActions = @("read-final-audit")
$ForbiddenDispatchActions = @(
    "commit",
    "push",
    "close",
    "commit-approved-once",
    "push-approved-once",
    "close-issue-approved-once",
    "commit-approved-docs-only",
    "push-dryrun-approved",
    "push-approved-once",
    "close-issue-approved-once"
)
$DispatchRequiredFields = @(
    "protocol",
    "action",
    "issue",
    "repo",
    "branch",
    "head",
    "expires",
    "requested_by",
    "request_id"
)
$DispatchKnownFields = @($DispatchRequiredFields + "mode", "expected_state", "reason" | Sort-Object -Unique)
$PollOnceSafetyBoundary = "PollOnce reads only the explicit issue and supports only maybe-status-check or run-reviewbundle. run-reviewbundle delegates once to runner v1 ReviewBundle after a clean-status preflight. It does not run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, consume approvals, or chain approvals."
$DryRunSafetyBoundary = "DryRunBoundedPoll reads only the explicit issue scope, validates marker selection, prints local decisions, and does not execute dispatch actions, post claim comments, post result comments, stage, commit, push, close issues, edit labels, create PRs, merge, force push, consume approvals, or chain approvals."
$BoundedPollSafetyBoundary = "BoundedPoll reads only the explicit issue scope, supports only maybe-status-check execution, executes at most one action per accepted dispatch, and does not run Codex, run runner v1, stage, commit, push, close issues, edit labels, create PRs, merge, force push, consume approvals, or chain approvals."

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

function Test-AsciiText {
    param(
        [AllowNull()]
        [string]$Text
    )

    if ($null -eq $Text) {
        return $true
    }

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

    foreach ($item in $Values) {
        if ([string]::Equals($item, $Value, [System.StringComparison]::Ordinal)) {
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

function Get-CommentBodyText {
    param(
        [Parameter(Mandatory = $false)]
        [object]$Comment
    )

    return Get-ObjectPropertyText -Object $Comment -PropertyName "body"
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
        throw "Run local-dispatcher-v1 from the repo root. Current path: $currentPath. Repo root: $expectedRoot."
    }
}

function Resolve-GhPath {
    return [string](Resolve-GhToolInfo).SelectedPath
}

function Resolve-GhToolInfo {
    $candidates = @()
    $candidateOrder = 0
    foreach ($command in @(Get-Command "gh" -All -ErrorAction SilentlyContinue)) {
        $commandType = Get-ObjectPropertyText -Object $command -PropertyName "CommandType"
        if (-not [string]::Equals($commandType, "Application", [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        foreach ($propertyName in @("Source", "Path", "Definition")) {
            $path = Get-ObjectPropertyText -Object $command -PropertyName $propertyName
            if ([string]::IsNullOrWhiteSpace($path)) {
                continue
            }
            $candidates += [pscustomobject]@{
                Path = $path
                Source = "path"
                Order = $candidateOrder
            }
            $candidateOrder += 1
            break
        }
    }

    $candidates += [pscustomobject]@{ Path = $GhCliFallbackPath; Source = "program_files_fallback"; Order = $candidateOrder }
    $candidateOrder += 1
    $candidates += [pscustomobject]@{ Path = $GhCliPortableFallbackPath; Source = "portable_fallback"; Order = $candidateOrder }

    $normalized = @()
    foreach ($candidate in @($candidates)) {
        $path = [string]$candidate.Path
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }
        $suffix = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        $rank = [array]::IndexOf(@(".exe", ".cmd", ".bat", ".com"), $suffix)
        if ($rank -lt 0) {
            continue
        }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            continue
        }
        $normalized += [pscustomobject]@{
            SelectedPath = [System.IO.Path]::GetFullPath($path)
            Suffix = $suffix
            SelectionSource = [string]$candidate.Source
            Rank = $rank
            Order = [int]$candidate.Order
        }
    }

    if (@($normalized).Count -gt 0) {
        return @($normalized | Sort-Object Rank, Order | Select-Object -First 1)[0]
    }

    $fallbackPaths = @($GhCliFallbackPath, $GhCliPortableFallbackPath)
    $fallbackSummary = ($fallbackPaths | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "', '"
    throw "GitHub CLI 'gh' is required to read the selected issue. Tried PATH command 'gh' and fallback paths '$fallbackSummary'."
}

function Get-CurrentBranch {
    $branch = Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current"
    if ([string]::IsNullOrWhiteSpace($branch)) {
        return "(detached HEAD)"
    }

    return $branch
}

function Get-CurrentFullHead {
    return Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
}

function Get-GitStatusShort {
    return Get-GitOutput -GitArgs @("status", "--short", "--untracked-files=all") -Action "git status --short --untracked-files=all"
}

function Test-GitStatusHasStagedChanges {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    if ([string]::IsNullOrWhiteSpace($Status)) {
        return $false
    }
    foreach ($line in @($Status -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        if ($line.Length -lt 2) {
            throw "Unexpected git status line: $line"
        }
        $indexStatus = $line.Substring(0, 1)
        if ($indexStatus -notin @(" ", "?", "!")) {
            return $true
        }
    }
    return $false
}

function Resolve-CurrentPowerShellHostPath {
    try {
        $processPath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    }
    catch {
        throw "Current PowerShell host path could not be resolved: $($_.Exception.Message)"
    }

    if ([string]::IsNullOrWhiteSpace($processPath)) {
        throw "Current PowerShell host path could not be resolved."
    }

    $fullPath = [System.IO.Path]::GetFullPath($processPath)
    if ($fullPath -notmatch '^[A-Za-z]:[\\/]' -and $fullPath -notmatch '^\\\\[^\\]+\\[^\\]+\\') {
        throw "Current PowerShell host path is not absolute: $fullPath"
    }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Current PowerShell host path does not exist: $fullPath"
    }
    if (-not [string]::Equals([System.IO.Path]::GetExtension($fullPath), ".exe", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Current PowerShell host path is not an .exe: $fullPath"
    }

    $fileName = [System.IO.Path]::GetFileName($fullPath)
    if (-not [string]::Equals($fileName, "powershell.exe", [System.StringComparison]::OrdinalIgnoreCase) -and
        -not [string]::Equals($fileName, "pwsh.exe", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Current PowerShell host executable is not powershell.exe or pwsh.exe: $fullPath"
    }

    return $fullPath
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
        [Parameter(Mandatory = $true)]
        [Alias("NoStage")]
        [bool]$FinalIndexClean,
        [Parameter(Mandatory = $true)]
        [Alias("NoCommit")]
        [bool]$FinalHeadMatchesInitial,
        [hashtable]$ValidationOverrides = @{},
        [hashtable]$ParentActionOverrides = @{},
        [string]$RequestId = $null,
        [string]$PollMode = $null,
        [string]$NextRecommendedAction = "chatgpt_review"
    )

    $validations = [ordered]@{
        dispatch_marker = (New-RunnerValidationResult -Status "reported" -Summary "See dispatcher output for marker validation details.")
        git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See dispatcher output for local git status.")
        pytest = (New-RunnerValidationResult -Status "not_run" -Summary "Dispatcher action '$Action' did not independently run pytest.")
        git_diff_check = (New-RunnerValidationResult -Status "not_run" -Summary "Dispatcher action '$Action' did not independently run git diff --check.")
    }
    foreach ($key in $ValidationOverrides.Keys) {
        $validations[$key] = $ValidationOverrides[$key]
    }

    $parentActions = [ordered]@{
        stage_invoked = $false
        commit_invoked = $false
        push_invoked = $false
        issue_close_invoked = $false
        label_edit_invoked = $false
        pr_create_invoked = $false
        merge_invoked = $false
        approval_token_consumed = $false
    }
    foreach ($key in $ParentActionOverrides.Keys) {
        $parentActions[$key] = [bool]$ParentActionOverrides[$key]
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
        request_id = $RequestId
        poll_mode = $PollMode
        review_id = $null
        diff_fingerprint = $null
        files_fingerprint = $null
        changed_files = @()
        result_scope = "dispatcher_action_and_final_git_observations"
        validations = $validations
        observations = [ordered]@{
            final_index_clean = $FinalIndexClean
            final_head_matches_initial = $FinalHeadMatchesInitial
        }
        trusted_parent_actions = $parentActions
        child_action_non_claim = "transient_or_external_child_actions_not_guaranteed_absent"
        next_recommended_action = $NextRecommendedAction
    }

    return ($summary | ConvertTo-Json -Depth 8)
}

function New-DryRunIssueDecision {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Issue,
        [Parameter(Mandatory = $true)]
        [ValidateSet("accepted", "rejected")]
        [string]$Decision,
        [Parameter(Mandatory = $true)]
        [string]$Reason,
        [string]$Action = $null,
        [string]$RequestId = $null,
        [string]$Branch = $null,
        [string]$Head = $null
    )

    return [ordered]@{
        issue = $Issue
        decision = $Decision
        reason = $Reason
        action = $Action
        request_id = $RequestId
        branch = $Branch
        head = $Head
        would_execute_dispatch_action = $false
        would_post_claim_comment = $false
        would_post_result_comment = $false
    }
}

function New-DryRunSummaryJson {
    param(
        [Parameter(Mandatory = $true)]
        [int[]]$Issues,
        [Parameter(Mandatory = $true)]
        [object[]]$Decisions,
        [Parameter(Mandatory = $true)]
        [ValidateSet("success", "failure")]
        [string]$Result,
        [Parameter(Mandatory = $true)]
        [Alias("NoStage")]
        [bool]$FinalIndexClean,
        [Parameter(Mandatory = $true)]
        [Alias("NoCommit")]
        [bool]$FinalHeadMatchesInitial
    )

    $summary = [ordered]@{
        schema = $DryRunProtocol
        repo = $Repo
        poll_mode = "dry_run_bounded"
        result = $Result
        max_issues_per_run = $MaxDryRunIssuesPerRun
        issues = @($Issues)
        decisions = @($Decisions)
        dry_run_facts = [ordered]@{
            dry_run_only = $true
            dispatch_action_invoked = $false
            claim_comment_invoked = $false
            result_comment_invoked = $false
        }
        observations = [ordered]@{
            final_index_clean = $FinalIndexClean
            final_head_matches_initial = $FinalHeadMatchesInitial
        }
        trusted_parent_actions = [ordered]@{
            stage_invoked = $false
            commit_invoked = $false
            push_invoked = $false
            issue_close_invoked = $false
            label_edit_invoked = $false
            pr_create_invoked = $false
            merge_invoked = $false
            approval_token_consumed = $false
        }
        next_recommended_action = "human_review"
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
        [Parameter(Mandatory = $true)]
        [Alias("NoStage")]
        [bool]$FinalIndexClean,
        [Parameter(Mandatory = $true)]
        [Alias("NoCommit")]
        [bool]$FinalHeadMatchesInitial,
        [hashtable]$ValidationOverrides = @{},
        [hashtable]$ParentActionOverrides = @{},
        [string]$RequestId = $null,
        [string]$PollMode = $null,
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
        -FinalIndexClean $FinalIndexClean `
        -FinalHeadMatchesInitial $FinalHeadMatchesInitial `
        -ValidationOverrides $ValidationOverrides `
        -ParentActionOverrides $ParentActionOverrides `
        -RequestId $RequestId `
        -PollMode $PollMode `
        -NextRecommendedAction $NextRecommendedAction)
}

function ConvertFrom-DispatchMarkerLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MarkerLine
    )

    if (-not (Test-AsciiText -Text $MarkerLine)) {
        throw "Dispatch marker contains non-ASCII text. Marker lines must be ASCII-safe."
    }

    $parts = $MarkerLine.Split(" ")
    if ($parts.Count -lt 2 -or -not [string]::Equals($parts[0], $DispatchMarkerPrefix, [System.StringComparison]::Ordinal)) {
        throw "Malformed dispatch marker. Marker must start with exact token '$DispatchMarkerPrefix' followed by key=value fields."
    }

    if (@($parts | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
        throw "Malformed dispatch marker. Use single spaces between marker fields and do not include empty fields."
    }

    $seenFields = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $fields = @{}

    foreach ($part in @($parts | Select-Object -Skip 1)) {
        if ($part -notmatch "^([a-z_]+)=([^=\s]+)$") {
            throw "Malformed dispatch marker field '$part'. Expected key=value with a lowercase known key and a non-empty value."
        }

        $fieldName = $Matches[1]
        $fieldValue = $Matches[2]

        if (-not (Test-ExactListValue -Values $DispatchKnownFields -Value $fieldName)) {
            throw "Unknown dispatch marker field '$fieldName'."
        }

        if (-not $seenFields.Add($fieldName)) {
            throw "Duplicate dispatch marker field '$fieldName'."
        }

        if ([string]::IsNullOrWhiteSpace($fieldValue)) {
            throw "Dispatch marker field '$fieldName' has an empty value."
        }

        $fields[$fieldName] = $fieldValue
    }

    foreach ($requiredField in $DispatchRequiredFields) {
        if (-not $seenFields.Contains($requiredField)) {
            throw "Missing required dispatch marker field '$requiredField'."
        }
    }

    return $fields
}

function ConvertTo-DispatchExpiryUtc {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Expires
    )

    if ($Expires -notmatch "^\d{8}T\d{6}Z$") {
        throw "Dispatch marker expires value '$Expires' is malformed. Expected YYYYMMDDTHHMMSSZ."
    }

    try {
        $styles = [System.Globalization.DateTimeStyles]::AssumeUniversal -bor [System.Globalization.DateTimeStyles]::AdjustToUniversal
        return [System.DateTime]::ParseExact($Expires, "yyyyMMdd'T'HHmmss'Z'", [System.Globalization.CultureInfo]::InvariantCulture, $styles)
    }
    catch {
        throw "Dispatch marker expires value '$Expires' is not a valid UTC timestamp: $($_.Exception.Message)"
    }
}

function Assert-DispatchFieldEquals {
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
        throw "Dispatch marker field '$Name' mismatch. Expected '$Expected', found '$actual'."
    }
}

function ConvertTo-ParsedDispatchMarker {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Marker,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    $fields = ConvertFrom-DispatchMarkerLine -MarkerLine ([string]$Marker.Line)
    $expiresUtc = ConvertTo-DispatchExpiryUtc -Expires ([string]$fields["expires"])

    return [pscustomobject]@{
        Marker = $Marker
        Fields = $fields
        ExpiresUtc = $expiresUtc
        IsCurrent = ($expiresUtc -gt $NowUtc)
    }
}

function Assert-DispatchMarkerMatchesLocalState {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedIssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$CurrentBranch,
        [Parameter(Mandatory = $true)]
        [string]$CurrentHead,
        [Parameter(Mandatory = $true)]
        [datetime]$ExpiresUtc,
        [Parameter(Mandatory = $true)]
        [datetime]$NowUtc
    )

    Assert-DispatchFieldEquals -Fields $Fields -Name "protocol" -Expected $DispatchProtocol
    Assert-DispatchFieldEquals -Fields $Fields -Name "issue" -Expected ([string]$ExpectedIssueNumber)
    Assert-DispatchFieldEquals -Fields $Fields -Name "repo" -Expected $ExpectedDispatchRepo
    Assert-DispatchFieldEquals -Fields $Fields -Name "branch" -Expected $CurrentBranch
    Assert-DispatchFieldEquals -Fields $Fields -Name "head" -Expected $CurrentHead

    if ($ExpiresUtc -le $NowUtc) {
        throw "Dispatch marker expired at $($ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")); current UTC time is $($NowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
    }

    $action = [string]$Fields["action"]
    if (Test-ExactListValue -Values $ForbiddenDispatchActions -Value $action) {
        throw "Forbidden dispatch action '$action'. CHATGPT-DISPATCH v1 cannot authorize commit, push, close, or approval-gated actions."
    }

    if (Test-ExactListValue -Values $ReservedDispatchActions -Value $action) {
        throw "Reserved dispatch action '$action' is not implemented in this PollOnce slice."
    }

    if (-not (Test-ExactListValue -Values $AllowedDispatchActions -Value $action)) {
        throw "Unsupported dispatch action '$action'. Supported dispatch v1 actions in this slice: $($AllowedDispatchActions -join ', ')."
    }
}

function Get-IssueDispatchMarkerReadResult {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber
    )

    $ghPath = Resolve-GhPath

    $ghArgs = @(
        "issue",
        "view",
        "$IssueNumber",
        "--repo",
        $Repo,
        "--json",
        "number,title,state,comments"
    )
    $result = Invoke-ReadOnlyCommand -FilePath $ghPath -Arguments $ghArgs -Action "gh issue view"
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
    $runnerResults = @()
    $commentIndex = 0
    foreach ($comment in $comments) {
        $commentIndex += 1
        $body = Get-CommentBodyText -Comment $comment
        $trimmedBody = $body.Trim()
        $lines = @($body -split "\r?\n")
        $lineNumber = 0
        foreach ($line in $lines) {
            $lineNumber += 1
            if ($line.StartsWith($DispatchMarkerPrefix, [System.StringComparison]::Ordinal)) {
                if (-not [string]::Equals($trimmedBody, $line, [System.StringComparison]::Ordinal)) {
                    throw "Malformed dispatch marker comment. CHATGPT-DISPATCH must be one standalone issue comment line."
                }

                $markers += [pscustomobject]@{
                    Line = $line
                    Comment = $comment
                    CommentIndex = $commentIndex
                    LineNumber = $lineNumber
                }
            }

            if ($line.StartsWith($RunnerResultMarker, [System.StringComparison]::Ordinal)) {
                $runnerResults += [pscustomobject]@{
                    Line = $line
                    Body = $body
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
        RunnerResults = @($runnerResults)
    }
}

function Test-MatchingRunnerResultExists {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ReadResult,
        [Parameter(Mandatory = $true)]
        [hashtable]$Fields
    )

    foreach ($runnerResult in @($ReadResult.RunnerResults)) {
        $body = [string]$runnerResult.Body
        $markerIndex = $body.IndexOf($RunnerResultMarker, [System.StringComparison]::Ordinal)
        if ($markerIndex -lt 0) {
            continue
        }

        $jsonText = $body.Substring($markerIndex + $RunnerResultMarker.Length).Trim()
        if ([string]::IsNullOrWhiteSpace($jsonText)) {
            continue
        }

        try {
            $summary = $jsonText | ConvertFrom-Json
        }
        catch {
            continue
        }

        $summaryIssue = Get-ObjectPropertyText -Object $summary -PropertyName "issue"
        $summaryAction = Get-ObjectPropertyText -Object $summary -PropertyName "action"
        $summaryRepo = Get-ObjectPropertyText -Object $summary -PropertyName "repo"
        $summaryBranch = Get-ObjectPropertyText -Object $summary -PropertyName "branch"
        $summaryHead = Get-ObjectPropertyText -Object $summary -PropertyName "head"
        $summaryRequestId = Get-ObjectPropertyText -Object $summary -PropertyName "request_id"

        if (
            [string]::Equals($summaryIssue, [string]$Fields["issue"], [System.StringComparison]::Ordinal) -and
            [string]::Equals($summaryAction, [string]$Fields["action"], [System.StringComparison]::Ordinal) -and
            [string]::Equals($summaryRepo, [string]$Fields["repo"], [System.StringComparison]::Ordinal) -and
            [string]::Equals($summaryBranch, [string]$Fields["branch"], [System.StringComparison]::Ordinal) -and
            [string]::Equals($summaryHead, [string]$Fields["head"], [System.StringComparison]::Ordinal) -and
            [string]::Equals($summaryRequestId, [string]$Fields["request_id"], [System.StringComparison]::Ordinal)
        ) {
            return $true
        }
    }

    return $false
}

function Get-ValidatedDispatchSelection {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [datetime]$NowUtc = [System.DateTime]::UtcNow
    )

    $branch = Get-CurrentBranch
    $head = Get-CurrentFullHead
    $readResult = Get-IssueDispatchMarkerReadResult -IssueNumber $IssueNumber
    $markers = @($readResult.Markers)

    if (-not [string]::Equals([string]$readResult.IssueState, "OPEN", [System.StringComparison]::Ordinal)) {
        throw "Target issue #$IssueNumber is not OPEN."
    }

    if ($markers.Count -eq 0) {
        throw "No current dispatch marker found for issue #$IssueNumber. No CHATGPT-DISPATCH marker comments were found."
    }

    $parsedMarkers = @()
    foreach ($marker in $markers) {
        $parsedMarkers += ConvertTo-ParsedDispatchMarker -Marker $marker -NowUtc $NowUtc
    }

    $currentMarkers = @($parsedMarkers | Where-Object { $_.IsCurrent })
    if ($currentMarkers.Count -eq 0) {
        $latestMarker = $parsedMarkers[$parsedMarkers.Count - 1]
        throw "No current dispatch marker found for issue #$IssueNumber. Latest marker expired at $($latestMarker.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
    }

    if ($currentMarkers.Count -gt 1) {
        throw "Ambiguous dispatch markers found for issue #$IssueNumber. Found $($currentMarkers.Count) current CHATGPT-DISPATCH marker comments; exactly one is required."
    }

    $selected = $currentMarkers[0]
    $authorLogin = Get-CommentAuthorLogin -Comment $selected.Marker.Comment
    if (-not (Test-ExactListValue -Values $TrustedDispatchAuthors -Value $authorLogin)) {
        throw "Dispatch marker author '$authorLogin' is not trusted."
    }

    Assert-DispatchFieldEquals -Fields $selected.Fields -Name "requested_by" -Expected "chatgpt"

    Assert-DispatchMarkerMatchesLocalState `
        -Fields $selected.Fields `
        -ExpectedIssueNumber $IssueNumber `
        -CurrentBranch $branch `
        -CurrentHead $head `
        -ExpiresUtc $selected.ExpiresUtc `
        -NowUtc $NowUtc

    return [pscustomobject]@{
        ReadResult = $readResult
        Markers = @($markers)
        Branch = $branch
        Head = $head
        NowUtc = $NowUtc
        Selected = $selected
    }
}

function Invoke-MaybeStatusCheck {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection
    )

    $status = Get-GitStatusShort
    return [pscustomobject]@{
        Action = "maybe-status-check"
        Result = "success"
        Status = $status
        StatusSummary = if ([string]::IsNullOrWhiteSpace($status)) { "clean" } else { "dirty" }
    }
}

function Invoke-ReviewBundle {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection,
        [Parameter(Mandatory = $true)]
        [int]$Issue
    )

    $status = Get-GitStatusShort
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "run-reviewbundle requires a clean repo before dispatch. Current git status: $status"
    }

    $runnerScript = Get-RunnerScriptPath
    $codexPathBinding = Resolve-ReviewBundleCodexPathBinding
    $powerShellHost = Resolve-CurrentPowerShellHostPath

    $runnerResult = Invoke-WriteCommand `
        -FilePath $powerShellHost `
        -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runnerScript, "-IssueNumber", "$Issue", "-Mode", "ReviewBundle", "-ReviewedCodexPath", $codexPathBinding) `
        -Action "local_runner_v1.ps1 ReviewBundle"

    $result = if ($runnerResult.ExitCode -eq 0) { "success" } else { "failure" }

    return [pscustomobject]@{
        Action = "run-reviewbundle"
        Result = $result
        Status = $status
        StatusSummary = "clean"
        RunnerExitCode = $runnerResult.ExitCode
        Stdout = $runnerResult.Stdout
        Stderr = $runnerResult.Stderr
    }
}

function New-ToolResolutionSafety {
    return [ordered]@{
        pollonce_invoked = $false
        dispatcher_action_executed = $false
        github_issue_read_performed = $false
        github_write_performed = $false
        runner_work_invoked = $false
        codex_task_executed = $false
    }
}

function New-ToolResolutionProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    try {
        $result = Invoke-ReadOnlyCommand -FilePath $FilePath -Arguments $Arguments -Action $Action
        return [ordered]@{
            executed = $true
            exit_code = $result.ExitCode
            ok = ($result.ExitCode -eq 0)
            safe_message = if ($result.ExitCode -eq 0) { "ok" } else { "version_probe_failed" }
        }
    }
    catch {
        return [ordered]@{
            executed = $true
            exit_code = 1
            ok = $false
            safe_message = "version_probe_failed"
        }
    }
}

function New-ToolEntry {
    param(
        [AllowNull()]
        [object]$ToolInfo,
        [AllowNull()]
        [object]$VersionProbe
    )

    return [ordered]@{
        selected_path = if ($null -eq $ToolInfo) { $null } else { [string]$ToolInfo.SelectedPath }
        suffix = if ($null -eq $ToolInfo) { $null } else { [string]$ToolInfo.Suffix }
        selection_source = if ($null -eq $ToolInfo) { $null } else { [string]$ToolInfo.SelectionSource }
        version_probe = $VersionProbe
    }
}

function New-ToolResolutionSummary {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("success", "blocked")]
        [string]$Result,
        [Parameter(Mandatory = $true)]
        [string]$RequiredActionValue,
        [string[]]$BlockedReasons = @(),
        [hashtable]$Tools = @{},
        [AllowNull()]
        [object]$NestedRunner = $null
    )

    return [ordered]@{
        protocol = $ToolResolutionPreflightProtocol
        component = "dispatcher"
        result = $Result
        required_action = $RequiredActionValue
        blocked_reasons = @($BlockedReasons)
        tools = $Tools
        nested_runner = $NestedRunner
        safety = New-ToolResolutionSafety
    }
}

function Test-ToolResolutionToolEntry {
    param(
        [AllowNull()]
        [object]$Tool,
        [Parameter(Mandatory = $true)]
        [string]$ReasonPrefix
    )

    if ($null -eq $Tool) {
        throw "${ReasonPrefix}_missing"
    }
    $selectedPath = Get-ObjectPropertyText -Object $Tool -PropertyName "selected_path"
    $suffix = Get-ObjectPropertyText -Object $Tool -PropertyName "suffix"
    $selectionSource = Get-ObjectPropertyText -Object $Tool -PropertyName "selection_source"
    if ([string]::IsNullOrWhiteSpace($selectedPath)) {
        throw "${ReasonPrefix}_missing_selected_path"
    }
    if ([string]::IsNullOrWhiteSpace($suffix)) {
        throw "${ReasonPrefix}_missing_suffix"
    }
    $normalizedSuffix = $suffix.ToLowerInvariant()
    if ($normalizedSuffix -notin @(".exe", ".cmd", ".bat", ".com")) {
        throw "${ReasonPrefix}_unsafe_suffix"
    }
    if (-not $selectedPath.ToLowerInvariant().EndsWith($normalizedSuffix)) {
        throw "${ReasonPrefix}_suffix_path_mismatch"
    }
    if ([string]::IsNullOrWhiteSpace($selectionSource)) {
        throw "${ReasonPrefix}_missing_selection_source"
    }
    $versionProbeProperty = $Tool.PSObject.Properties["version_probe"]
    if ($null -eq $versionProbeProperty -or $null -eq $versionProbeProperty.Value) {
        throw "${ReasonPrefix}_missing_version_probe"
    }
    $versionProbe = $versionProbeProperty.Value
    $executedProperty = $versionProbe.PSObject.Properties["executed"]
    if ($null -eq $executedProperty -or $executedProperty.Value -ne $true) {
        throw "${ReasonPrefix}_version_probe_not_executed"
    }
    $exitCodeProperty = $versionProbe.PSObject.Properties["exit_code"]
    if ($null -eq $exitCodeProperty -or $exitCodeProperty.Value -ne 0) {
        throw "${ReasonPrefix}_version_probe_nonzero_exit"
    }
    $okProperty = $versionProbe.PSObject.Properties["ok"]
    if ($null -eq $okProperty -or $okProperty.Value -ne $true) {
        throw "${ReasonPrefix}_version_probe_not_ok"
    }
    $safeMessageProperty = $versionProbe.PSObject.Properties["safe_message"]
    if ($null -eq $safeMessageProperty -or -not [string]::Equals([string]$safeMessageProperty.Value, "ok", [System.StringComparison]::Ordinal)) {
        throw "${ReasonPrefix}_version_probe_unsafe_message"
    }
}

function Test-ToolResolutionSafety {
    param(
        [AllowNull()]
        [object]$Safety,
        [Parameter(Mandatory = $true)]
        [string]$ReasonPrefix
    )

    if ($null -eq $Safety) {
        throw "${ReasonPrefix}_missing_safety"
    }
    foreach ($field in @("pollonce_invoked", "dispatcher_action_executed", "github_issue_read_performed", "github_write_performed", "runner_work_invoked", "codex_task_executed")) {
        $fieldProperty = $Safety.PSObject.Properties[$field]
        if ($null -eq $fieldProperty -or $fieldProperty.Value -ne $false) {
            throw "${ReasonPrefix}_safety_contradiction_$field"
        }
    }
}

function Get-ReviewedCodexPathValue {
    $valueVariable = Get-Variable -Name ReviewedCodexPath -ErrorAction SilentlyContinue
    if ($null -eq $valueVariable) {
        return ""
    }
    return [string]$valueVariable.Value
}

function Get-RunnerScriptPath {
    $runnerScript = Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1"
    if (-not (Test-Path -LiteralPath $runnerScript -PathType Leaf)) {
        throw "Runner v1 script not found at $runnerScript."
    }
    return $runnerScript
}

function ConvertFrom-ToolResolutionJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JsonText,
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    try {
        $payload = $JsonText | ConvertFrom-Json
    }
    catch {
        throw "runner_preflight_malformed_json"
    }
    if ($null -eq $payload -or $payload -is [array]) {
        throw "runner_preflight_non_object_json"
    }
    if (-not [string]::Equals((Get-ObjectPropertyText -Object $payload -PropertyName "protocol"), $ToolResolutionPreflightProtocol, [System.StringComparison]::Ordinal)) {
        throw "runner_preflight_wrong_protocol"
    }
    if (-not [string]::Equals((Get-ObjectPropertyText -Object $payload -PropertyName "component"), "runner", [System.StringComparison]::Ordinal)) {
        throw "runner_preflight_wrong_component"
    }
    if (-not [string]::Equals((Get-ObjectPropertyText -Object $payload -PropertyName "required_action"), "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        throw "runner_preflight_wrong_required_action"
    }
    $result = Get-ObjectPropertyText -Object $payload -PropertyName "result"
    if (-not [string]::Equals($result, "success", [System.StringComparison]::Ordinal) -and
        -not [string]::Equals($result, "blocked", [System.StringComparison]::Ordinal)) {
        throw "runner_preflight_invalid_result"
    }
    if ([string]::Equals($result, "success", [System.StringComparison]::Ordinal) -and $ExitCode -ne 0) {
        throw "runner_preflight_success_exit_mismatch"
    }
    if ([string]::Equals($result, "blocked", [System.StringComparison]::Ordinal) -and $ExitCode -ne 2) {
        throw "runner_preflight_blocked_exit_mismatch"
    }
    $blockedReasonsProperty = $payload.PSObject.Properties["blocked_reasons"]
    if ($null -eq $blockedReasonsProperty -or $null -eq $blockedReasonsProperty.Value -or $blockedReasonsProperty.Value -is [string]) {
        throw "runner_preflight_invalid_blocked_reasons"
    }
    $blockedReasons = @($blockedReasonsProperty.Value)
    foreach ($blockedReason in $blockedReasons) {
        if ($blockedReason -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$blockedReason)) {
            throw "runner_preflight_invalid_blocked_reasons"
        }
    }
    if ([string]::Equals($result, "success", [System.StringComparison]::Ordinal) -and $blockedReasons.Count -ne 0) {
        throw "runner_preflight_success_with_blocked_reasons"
    }
    if ([string]::Equals($result, "blocked", [System.StringComparison]::Ordinal) -and $blockedReasons.Count -eq 0) {
        throw "runner_preflight_blocked_without_reasons"
    }
    $nestedRunnerProperty = $payload.PSObject.Properties["nested_runner"]
    if ($null -eq $nestedRunnerProperty -or $null -ne $nestedRunnerProperty.Value) {
        throw "runner_preflight_unexpected_nested_runner"
    }
    $safetyProperty = $payload.PSObject.Properties["safety"]
    Test-ToolResolutionSafety -Safety $(if ($null -eq $safetyProperty) { $null } else { $safetyProperty.Value }) -ReasonPrefix "runner_preflight"

    if ([string]::Equals($result, "success", [System.StringComparison]::Ordinal)) {
        $toolsProperty = $payload.PSObject.Properties["tools"]
        if ($null -eq $toolsProperty -or $null -eq $toolsProperty.Value) {
            throw "runner_preflight_missing_tools"
        }
        $tools = $toolsProperty.Value
        $runnerGhProperty = $tools.PSObject.Properties["runner_gh"]
        $codexProperty = $tools.PSObject.Properties["codex"]
        Test-ToolResolutionToolEntry -Tool $(if ($null -eq $runnerGhProperty) { $null } else { $runnerGhProperty.Value }) -ReasonPrefix "runner_preflight_runner_gh"
        Test-ToolResolutionToolEntry -Tool $(if ($null -eq $codexProperty) { $null } else { $codexProperty.Value }) -ReasonPrefix "runner_preflight_codex"
    }
    return $payload
}

function Invoke-RunnerToolResolutionPreflight {
    $runnerScript = Get-RunnerScriptPath
    $runnerResult = Invoke-ReadOnlyCommand `
        -FilePath "powershell.exe" `
        -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runnerScript, "-ToolResolutionPreflight", "-RequiredAction", "run-reviewbundle") `
        -Action "runner ToolResolutionPreflight"
    if ($runnerResult.ExitCode -notin @(0, 2)) {
        throw "runner_preflight_process_failed"
    }
    return ConvertFrom-ToolResolutionJson -JsonText $runnerResult.Stdout -ExitCode $runnerResult.ExitCode
}

function Get-RunnerCodexSelectedPath {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RunnerPreflight
    )

    $toolsProperty = $RunnerPreflight.PSObject.Properties["tools"]
    if ($null -eq $toolsProperty -or $null -eq $toolsProperty.Value) {
        throw "runner_preflight_missing_tools"
    }
    $codexProperty = $toolsProperty.Value.PSObject.Properties["codex"]
    if ($null -eq $codexProperty -or $null -eq $codexProperty.Value) {
        throw "runner_preflight_codex_missing"
    }
    $selectedPath = Get-ObjectPropertyText -Object $codexProperty.Value -PropertyName "selected_path"
    if ([string]::IsNullOrWhiteSpace($selectedPath)) {
        throw "runner_preflight_codex_missing_selected_path"
    }
    return [System.IO.Path]::GetFullPath($selectedPath)
}

function Test-ReviewedCodexPathShape {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ($Path -notmatch '^[A-Za-z]:[\\/]' -and $Path -notmatch '^\\\\[^\\]+\\[^\\]+\\') {
        throw "reviewed_codex_path_not_absolute"
    }
    $suffix = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($suffix -notin @(".exe", ".cmd", ".bat", ".com")) {
        throw "reviewed_codex_path_unsafe_suffix"
    }
}

function Resolve-ReviewBundleCodexPathBinding {
    $runnerPreflight = Invoke-RunnerToolResolutionPreflight
    if (-not [string]::Equals((Get-ObjectPropertyText -Object $runnerPreflight -PropertyName "result"), "success", [System.StringComparison]::Ordinal)) {
        throw "runner_preflight_blocked"
    }
    $selectedCodexPath = Get-RunnerCodexSelectedPath -RunnerPreflight $runnerPreflight
    $reviewedPath = Get-ReviewedCodexPathValue
    if ([string]::IsNullOrWhiteSpace($reviewedPath)) {
        return $selectedCodexPath
    }
    Test-ReviewedCodexPathShape -Path $reviewedPath
    $reviewedFullPath = [System.IO.Path]::GetFullPath($reviewedPath)
    if (-not [string]::Equals($reviewedFullPath, $selectedCodexPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "reviewed_codex_path_mismatch"
    }
    return $reviewedFullPath
}

function Invoke-ToolResolutionPreflight {
    if (-not [string]::Equals($Repo, $ExpectedDispatchRepo, [System.StringComparison]::Ordinal)) {
        throw "ToolResolutionPreflight supports only repo=$ExpectedDispatchRepo for this dispatcher slice."
    }
    if (-not [string]::Equals($RequiredAction, "maybe-status-check", [System.StringComparison]::Ordinal) -and
        -not [string]::Equals($RequiredAction, "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        throw "ToolResolutionPreflight requires -RequiredAction maybe-status-check or run-reviewbundle."
    }
    if ($PostResultComment -or $IssueNumber -ne 0 -or @($IssueNumbers).Count -ne 0) {
        throw "ToolResolutionPreflight does not accept IssueNumber, IssueNumbers, or PostResultComment."
    }

    Assert-RepoRoot
    $blocked = @()
    $tools = @{}
    $nestedRunner = $null

    try {
        $ghInfo = Resolve-GhToolInfo
        $ghProbe = New-ToolResolutionProbe -FilePath $ghInfo.SelectedPath -Arguments @("--version") -Action "gh --version"
        $tools["dispatcher_gh"] = New-ToolEntry -ToolInfo $ghInfo -VersionProbe $ghProbe
        if (-not $ghProbe.ok) {
            $blocked += "dispatcher_gh_version_probe_failed"
        }
    }
    catch {
        $blocked += "dispatcher_gh_unavailable"
        $tools["dispatcher_gh"] = New-ToolEntry -ToolInfo $null -VersionProbe $null
    }

    if ([string]::Equals($RequiredAction, "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        try {
            $nestedRunner = Invoke-RunnerToolResolutionPreflight
            if ([string]$nestedRunner.result -eq "blocked") {
                $blocked += "runner_preflight_blocked"
                foreach ($nestedReason in @($nestedRunner.blocked_reasons)) {
                    if ($nestedReason -is [string] -and -not [string]::IsNullOrWhiteSpace($nestedReason)) {
                        $blocked += [string]$nestedReason
                    }
                }
            }
        }
        catch {
            $knownReason = [string]$_.Exception.Message
            if ($knownReason -match '^Runner v1 script not found') {
                $knownReason = "runner_script_missing"
            }
            elseif ($knownReason -notmatch '^runner_preflight_[A-Za-z0-9_]+$') {
                $knownReason = "runner_preflight_contract_failure"
            }
            $blocked += $knownReason
        }
    }

    $result = if ($blocked.Count -eq 0) { "success" } else { "blocked" }
    $summary = New-ToolResolutionSummary `
        -Result $result `
        -RequiredActionValue $RequiredAction `
        -BlockedReasons $blocked `
        -Tools $tools `
        -NestedRunner $nestedRunner
    Write-Output ($summary | ConvertTo-Json -Depth 12 -Compress)
    if ($result -eq "success") {
        exit 0
    }
    exit 2
}

function Publish-RunnerResultComment {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$Body
    )

    $bodyFile = New-TemporaryFile
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
        [System.IO.File]::WriteAllText($bodyFile.FullName, $Body, $utf8NoBom)
        $ghPath = Resolve-GhPath
        $result = Invoke-WriteCommand -FilePath $ghPath -Arguments @("issue", "comment", "$IssueNumber", "--repo", $Repo, "--body-file", $bodyFile.FullName) -Action "gh issue comment"
        Require-Success -Result $result -Action "gh issue comment"
        return $result
    }
    finally {
        Remove-Item -LiteralPath $bodyFile.FullName -Force -ErrorAction SilentlyContinue
    }
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

function Invoke-AcceptedDispatchAction {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Selection,
        [Parameter(Mandatory = $true)]
        [int]$Issue,
        [Parameter(Mandatory = $true)]
        [string]$ModeName,
        [Parameter(Mandatory = $true)]
        [string]$SafetyBoundary
    )

    $selected = $selection.Selected
    $fields = $selected.Fields
    $action = [string]$fields["action"]
    $requestId = [string]$fields["request_id"]

    Write-Host "$DispatcherName $DispatcherVersion"
    Write-Host "Mode: $ModeName"
    Write-Host "Issue number: #$Issue"
    Write-Host "Issue state: $($selection.ReadResult.IssueState)"
    Write-Host "Dispatch comment id: $(Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id")"
    Write-Host "Dispatch comment author: $(Get-CommentAuthorLogin -Comment $selected.Marker.Comment)"
    Write-Host "Parsed action: $action"
    Write-Host "Request id: $requestId"
    Write-Host "Branch: $($selection.Branch)"
    Write-Host "HEAD: $($selection.Head)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Safety boundary: $SafetyBoundary"
    Write-Host ""

    $headBeforeAction = Get-CurrentFullHead

    if ([string]::Equals($action, "maybe-status-check", [System.StringComparison]::Ordinal)) {
        $actionResult = Invoke-MaybeStatusCheck -Selection $selection
    }
    elseif ([string]::Equals($action, "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        $actionResult = Invoke-ReviewBundle -Selection $selection -Issue $Issue
        if (-not [string]::IsNullOrWhiteSpace($actionResult.Stdout)) {
            Write-Host "Runner v1 stdout:"
            Write-Host $actionResult.Stdout
        }
        if (-not [string]::IsNullOrWhiteSpace($actionResult.Stderr)) {
            Write-Host "Runner v1 stderr:"
            Write-Host $actionResult.Stderr
        }
    }
    else {
        throw "Internal dispatcher error: selected unsupported action '$action'."
    }

    Write-Host "Action result: $($actionResult.Result)"
    Write-Host "Git status summary: $($actionResult.StatusSummary)"
    if (-not [string]::IsNullOrWhiteSpace($actionResult.Status)) {
        Write-Host $actionResult.Status
    }

    $headAfterAction = Get-CurrentFullHead
    $finalObservedStatus = Get-GitStatusShort
    $finalHeadMatchesInitial = [string]::Equals($headBeforeAction, $headAfterAction, [System.StringComparison]::OrdinalIgnoreCase)
    $finalIndexClean = -not (Test-GitStatusHasStagedChanges -Status $finalObservedStatus)
    $summaryResult = if ([string]::Equals($actionResult.Result, "success", [System.StringComparison]::Ordinal) -and $finalHeadMatchesInitial -and $finalIndexClean) { "success" } else { "failure" }

    Write-FinalGitStatus

    $gitStatusValidationSummary = if ([string]::Equals($action, "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        "run-reviewbundle pre-dispatch git status was clean."
    }
    else {
        "maybe-status-check observed git status: $($actionResult.StatusSummary)."
    }

    $validationOverrides = @{
        dispatch_marker = (New-RunnerValidationResult -Status "passed" -Summary "Exactly one current CHATGPT-DISPATCH marker matched issue, repo, branch, HEAD, expiry, and allowed action.")
        git_status_clean = (New-RunnerValidationResult -Status $(if ($actionResult.StatusSummary -eq "clean") { "passed" } else { "warning" }) -Summary $gitStatusValidationSummary)
        final_head_matches_initial = (New-RunnerValidationResult -Status $(if ($finalHeadMatchesInitial) { "passed" } else { "failed" }) -Summary $(if ($finalHeadMatchesInitial) { "Final full HEAD matches the initial dispatcher observation." } else { "Final full HEAD differs from the initial dispatcher observation." }))
        final_index_clean = (New-RunnerValidationResult -Status $(if ($finalIndexClean) { "passed" } else { "failed" }) -Summary $(if ($finalIndexClean) { "The final staged area was observed clean." } else { "The final staged area contains changes." }))
    }

    if ([string]::Equals($action, "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        $runnerExitCode = if ($null -eq $actionResult.RunnerExitCode) { "unknown" } else { [string]$actionResult.RunnerExitCode }
        $runnerValidationStatus = if ([string]::Equals($actionResult.Result, "success", [System.StringComparison]::Ordinal)) { "passed" } else { "failed" }
        $validationOverrides["runner_v1"] = New-RunnerValidationResult -Status $runnerValidationStatus -Summary "runner v1 invocation attempted; exit code: $runnerExitCode."
    }

    $summaryJson = New-RunnerResultSummaryJson `
        -Issue $Issue `
        -Action $action `
        -Result $summaryResult `
        -Branch $selection.Branch `
        -Head $headAfterAction `
        -SelectedIssue $Issue `
        -FinalIndexClean $finalIndexClean `
        -FinalHeadMatchesInitial $finalHeadMatchesInitial `
        -ValidationOverrides $validationOverrides `
        -RequestId $requestId `
        -PollMode $ModeName

    Write-Host $RunnerResultMarker
    Write-Host $summaryJson

    if ($PostResultComment) {
        Publish-RunnerResultComment -IssueNumber $Issue -Body "$RunnerResultMarker`n$summaryJson" | Out-Null
        Write-Host "Posted one LAWBRUNNER-RESULT comment to issue #$Issue."
    }
}

function Invoke-PollOnce {
    if ($IssueNumber -lt 1) {
        throw "PollOnce requires -IssueNumber <N> and scans only that issue."
    }

    if (-not [string]::Equals($Repo, $ExpectedDispatchRepo, [System.StringComparison]::Ordinal)) {
        throw "PollOnce supports only repo=$ExpectedDispatchRepo for this dispatcher slice."
    }

    Assert-RepoRoot
    $selection = Get-ValidatedDispatchSelection -IssueNumber $IssueNumber
    Invoke-AcceptedDispatchAction -Selection $selection -Issue $IssueNumber -ModeName "PollOnce" -SafetyBoundary $PollOnceSafetyBoundary
}

function Get-ExplicitIssueScope {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ModeName,
        [Parameter(Mandatory = $true)]
        [int]$MaxIssuesPerRun
    )

    $scope = @()
    if ($IssueNumber -gt 0) {
        $scope += $IssueNumber
    }

    foreach ($issue in @($IssueNumbers)) {
        if ($issue -gt 0) {
            $scope += $issue
        }
        else {
            throw "$ModeName issue numbers must be positive integers."
        }
    }

    if ($scope.Count -eq 0) {
        throw "$ModeName requires explicit issue scope via -IssueNumber <N> or -IssueNumbers <N>[,<M>,<K>]."
    }

    $unique = @($scope | Select-Object -Unique)
    if ($unique.Count -ne $scope.Count) {
        throw "$ModeName issue scope contains duplicate issue numbers."
    }

    if ($unique.Count -gt $MaxIssuesPerRun) {
        throw "$ModeName supports at most $MaxIssuesPerRun explicit issues per run."
    }

    return [int[]]$unique
}

function Get-DryRunIssueScope {
    return Get-ExplicitIssueScope -ModeName "DryRunBoundedPoll" -MaxIssuesPerRun $MaxDryRunIssuesPerRun
}

function Invoke-DryRunBoundedPoll {
    if (-not [string]::Equals($Repo, $ExpectedDispatchRepo, [System.StringComparison]::Ordinal)) {
        throw "DryRunBoundedPoll supports only repo=$ExpectedDispatchRepo for this dispatcher slice."
    }

    Assert-RepoRoot
    $headBeforeDryRun = Get-CurrentFullHead
    $scope = @(Get-DryRunIssueScope)
    $decisions = @()

    Write-Host "$DispatcherName $DispatcherVersion"
    Write-Host "Mode: DryRunBoundedPoll"
    Write-Host "Issue scope: $($scope -join ', ')"
    Write-Host "Max issues per run: $MaxDryRunIssuesPerRun"
    Write-Host "Safety boundary: $DryRunSafetyBoundary"
    Write-Host ""

    foreach ($issue in $scope) {
        try {
            $selection = Get-ValidatedDispatchSelection -IssueNumber $issue
            $fields = $selection.Selected.Fields

            if (Test-MatchingRunnerResultExists -ReadResult $selection.ReadResult -Fields $fields) {
                throw "Matching LAWBRUNNER-RESULT already exists for issue #$issue request_id=$($fields["request_id"])."
            }

            $action = [string]$fields["action"]
            $requestId = [string]$fields["request_id"]
            $reason = "Exactly one current dispatch marker would be accepted. Dry-run did not execute action '$action' and did not post claim or result comments."
            Write-Host "Issue #${issue}: accepted dry-run decision for action '$action' request_id=$requestId."
            $decisions += New-DryRunIssueDecision `
                -Issue $issue `
                -Decision "accepted" `
                -Reason $reason `
                -Action $action `
                -RequestId $requestId `
                -Branch $selection.Branch `
                -Head $selection.Head
        }
        catch {
            $reason = $_.Exception.Message
            Write-Host "Issue #${issue}: rejected dry-run decision. $reason"
            $decisions += New-DryRunIssueDecision `
                -Issue $issue `
                -Decision "rejected" `
                -Reason $reason
        }
    }

    $rejectedCount = @($decisions | Where-Object { $_["decision"] -eq "rejected" }).Count
    $result = if ($rejectedCount -eq 0) { "success" } else { "failure" }
    $headAfterDryRun = Get-CurrentFullHead
    $statusAfterDryRun = Get-GitStatusShort
    $finalHeadMatchesInitial = [string]::Equals($headBeforeDryRun, $headAfterDryRun, [System.StringComparison]::OrdinalIgnoreCase)
    $finalIndexClean = -not (Test-GitStatusHasStagedChanges -Status $statusAfterDryRun)
    if (-not $finalHeadMatchesInitial -or -not $finalIndexClean) {
        $result = "failure"
    }

    Write-Host $DryRunMarker
    Write-Host (New-DryRunSummaryJson -Issues $scope -Decisions $decisions -Result $result -FinalIndexClean $finalIndexClean -FinalHeadMatchesInitial $finalHeadMatchesInitial)

    if ($rejectedCount -gt 0 -or -not $finalHeadMatchesInitial -or -not $finalIndexClean) {
        throw "DryRunBoundedPoll failed closed for $rejectedCount issue(s); final_head_matches_initial=$finalHeadMatchesInitial final_index_clean=$finalIndexClean."
    }
}

function Get-BoundedPollIssueScope {
    return Get-ExplicitIssueScope -ModeName "BoundedPoll" -MaxIssuesPerRun $MaxBoundedPollIssuesPerRun
}

function Invoke-BoundedPoll {
    if (-not [string]::Equals($Repo, $ExpectedDispatchRepo, [System.StringComparison]::Ordinal)) {
        throw "BoundedPoll supports only repo=$ExpectedDispatchRepo for this dispatcher slice."
    }

    Assert-RepoRoot
    $scope = @(Get-BoundedPollIssueScope)
    $acceptedSelections = @()
    $rejections = @()

    Write-Host "$DispatcherName $DispatcherVersion"
    Write-Host "Mode: BoundedPoll"
    Write-Host "Issue scope: $($scope -join ', ')"
    Write-Host "Max issues per run: $MaxBoundedPollIssuesPerRun"
    Write-Host "Safety boundary: $BoundedPollSafetyBoundary"
    Write-Host ""

    foreach ($issue in $scope) {
        try {
            $selection = Get-ValidatedDispatchSelection -IssueNumber $issue
            $fields = $selection.Selected.Fields

            if ([string]::Equals([string]$fields["action"], "run-reviewbundle", [System.StringComparison]::Ordinal)) {
                throw "BoundedPoll does not execute run-reviewbundle. Use PollOnce with one explicit -IssueNumber."
            }

            if (Test-MatchingRunnerResultExists -ReadResult $selection.ReadResult -Fields $fields) {
                throw "Matching LAWBRUNNER-RESULT already exists for issue #$issue request_id=$($fields["request_id"])."
            }

            $acceptedSelections += [pscustomobject]@{
                Issue = $issue
                Selection = $selection
            }
            Write-Host "Issue #${issue}: accepted bounded-poll selection for action '$($fields["action"])' request_id=$($fields["request_id"])."
        }
        catch {
            $reason = $_.Exception.Message
            Write-Host "Issue #${issue}: rejected bounded-poll selection. $reason"
            $rejections += [pscustomobject]@{
                Issue = $issue
                Reason = $reason
            }
        }
    }

    if (@($rejections).Count -gt 0) {
        throw "BoundedPoll failed closed before action execution for $(@($rejections).Count) issue(s)."
    }

    foreach ($accepted in $acceptedSelections) {
        Invoke-AcceptedDispatchAction `
            -Selection $accepted.Selection `
            -Issue ([int]$accepted.Issue) `
            -ModeName "BoundedPoll" `
            -SafetyBoundary $BoundedPollSafetyBoundary
    }
}

try {
    $selectedModes = @()
    if ($PollOnce) {
        $selectedModes += "PollOnce"
    }
    if ($DryRunBoundedPoll) {
        $selectedModes += "DryRunBoundedPoll"
    }
    if ($BoundedPoll) {
        $selectedModes += "BoundedPoll"
    }
    if ($ToolResolutionPreflight) {
        $selectedModes += "ToolResolutionPreflight"
    }

    if ($selectedModes.Count -eq 0) {
        throw "Missing mode. Use: .\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> [-PostResultComment], .\scripts\local_dispatcher_v1.ps1 -DryRunBoundedPoll -IssueNumber <N>, .\scripts\local_dispatcher_v1.ps1 -BoundedPoll -IssueNumber <N> [-PostResultComment], or .\scripts\local_dispatcher_v1.ps1 -ToolResolutionPreflight -RequiredAction <action>."
    }

    if ($selectedModes.Count -gt 1) {
        throw "Choose exactly one mode. Supplied modes: $($selectedModes -join ', ')."
    }

    if ($PostResultComment -and -not ($PollOnce -or $BoundedPoll)) {
        throw "-PostResultComment is valid only with -PollOnce or -BoundedPoll."
    }

    if ($PollOnce -and @($IssueNumbers).Count -gt 0) {
        throw "-IssueNumbers is valid only with -DryRunBoundedPoll or -BoundedPoll."
    }

    if ($ToolResolutionPreflight) {
        Invoke-ToolResolutionPreflight
    }
    elseif ($DryRunBoundedPoll) {
        Invoke-DryRunBoundedPoll
    }
    elseif ($BoundedPoll) {
        Invoke-BoundedPoll
    }
    else {
        Invoke-PollOnce
    }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
