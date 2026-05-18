<#
.SYNOPSIS
Runs one safe local CHATGPT-DISPATCH poll for an explicit GitHub issue.

.DESCRIPTION
local_dispatcher_v1.ps1 implements manual PollOnce only for
CHATGPT-DISPATCH protocol=lawb.dispatch.v1. It reads only the explicitly
selected issue, validates exactly one current standalone dispatch marker, and
executes only the low-risk maybe-status-check action in this slice.

The dispatcher never treats CHATGPT-DISPATCH as approval for commit, push,
issue close, labels, PRs, merges, force push, or approval chaining.

.EXAMPLE
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber 83

.EXAMPLE
.\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber 83 -PostResultComment
#>

param(
    [switch]$PollOnce,
    [switch]$PostResultComment,
    [int]$IssueNumber = 0,
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
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$AllowedDispatchActions = @("maybe-status-check")
$ReservedDispatchActions = @("run-reviewbundle", "read-final-audit")
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
$PollOnceSafetyBoundary = "PollOnce reads only the explicit issue and supports only maybe-status-check. It does not run Codex, run runner v1, stage, commit, push, close issues, edit labels, create PRs, merge, force push, consume approvals, or chain approvals."

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

function Assert-GhAvailable {
    $command = Get-Command "gh" -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "GitHub CLI 'gh' is required to read the selected issue."
    }
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
    return Get-GitOutput -GitArgs @("status", "--short") -Action "git status --short"
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
        [hashtable]$ValidationOverrides = @{},
        [hashtable]$SafetyOverrides = @{},
        [string]$NextRecommendedAction = "chatgpt_review"
    )

    $validations = [ordered]@{
        dispatch_marker = (New-RunnerValidationResult -Status "reported" -Summary "See dispatcher output for marker validation details.")
        git_status_clean = (New-RunnerValidationResult -Status "reported" -Summary "See dispatcher output for local git status.")
        pytest = (New-RunnerValidationResult -Status "not_run" -Summary "Dispatcher maybe-status-check did not run pytest.")
        git_diff_check = (New-RunnerValidationResult -Status "not_run" -Summary "Dispatcher maybe-status-check did not run git diff --check.")
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
        review_id = $null
        diff_fingerprint = $null
        files_fingerprint = $null
        changed_files = @()
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
        -ValidationOverrides $ValidationOverrides `
        -SafetyOverrides $SafetyOverrides `
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
        }
    }

    return [pscustomobject]@{
        IssueNumber = $IssueNumber
        Title = $issueTitle
        IssueState = $issueState
        Markers = @($markers)
    }
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

function Publish-RunnerResultComment {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumber,
        [Parameter(Mandatory = $true)]
        [string]$Body
    )

    $result = Invoke-WriteCommand -FilePath "gh" -Arguments @("issue", "comment", "$IssueNumber", "--repo", $Repo, "--body", $Body) -Action "gh issue comment"
    Require-Success -Result $result -Action "gh issue comment"
    return $result
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

function Invoke-PollOnce {
    if ($IssueNumber -lt 1) {
        throw "PollOnce requires -IssueNumber <N> and scans only that issue."
    }

    if (-not [string]::Equals($Repo, $ExpectedDispatchRepo, [System.StringComparison]::Ordinal)) {
        throw "PollOnce supports only repo=$ExpectedDispatchRepo for this dispatcher slice."
    }

    Assert-RepoRoot
    $selection = Get-ValidatedDispatchSelection -IssueNumber $IssueNumber
    $selected = $selection.Selected
    $fields = $selected.Fields
    $action = [string]$fields["action"]

    Write-Host "$DispatcherName $DispatcherVersion"
    Write-Host "Mode: PollOnce"
    Write-Host "Issue number: #$IssueNumber"
    Write-Host "Issue state: $($selection.ReadResult.IssueState)"
    Write-Host "Dispatch comment id: $(Get-ObjectPropertyText -Object $selected.Marker.Comment -PropertyName "id")"
    Write-Host "Dispatch comment author: $(Get-CommentAuthorLogin -Comment $selected.Marker.Comment)"
    Write-Host "Parsed action: $action"
    Write-Host "Branch: $($selection.Branch)"
    Write-Host "HEAD: $($selection.Head)"
    Write-Host "Expiry status: current until $($selected.ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    Write-Host "Safety boundary: $PollOnceSafetyBoundary"
    Write-Host ""

    if (-not [string]::Equals($action, "maybe-status-check", [System.StringComparison]::Ordinal)) {
        throw "Internal dispatcher error: selected unsupported action '$action'."
    }

    $actionResult = Invoke-MaybeStatusCheck -Selection $selection
    Write-Host "Action result: $($actionResult.Result)"
    Write-Host "Git status summary: $($actionResult.StatusSummary)"
    if (-not [string]::IsNullOrWhiteSpace($actionResult.Status)) {
        Write-Host $actionResult.Status
    }

    Write-FinalGitStatus

    $validationOverrides = @{
        dispatch_marker = (New-RunnerValidationResult -Status "passed" -Summary "Exactly one current CHATGPT-DISPATCH marker matched issue, repo, branch, HEAD, expiry, and allowed action.")
        git_status_clean = (New-RunnerValidationResult -Status $(if ($actionResult.StatusSummary -eq "clean") { "passed" } else { "warning" }) -Summary "maybe-status-check observed git status: $($actionResult.StatusSummary).")
    }
    $summaryJson = New-RunnerResultSummaryJson `
        -Issue $IssueNumber `
        -Action $action `
        -Result "success" `
        -Branch $selection.Branch `
        -Head $selection.Head `
        -SelectedIssue $IssueNumber `
        -ValidationOverrides $validationOverrides

    Write-Host $RunnerResultMarker
    Write-Host $summaryJson

    if ($PostResultComment) {
        Publish-RunnerResultComment -IssueNumber $IssueNumber -Body "$RunnerResultMarker`n$summaryJson" | Out-Null
        Write-Host "Posted one LAWBRUNNER-RESULT comment to issue #$IssueNumber."
    }
}

try {
    $selectedModes = @()
    if ($PollOnce) {
        $selectedModes += "PollOnce"
    }

    if ($selectedModes.Count -eq 0) {
        throw "Missing mode. Use: .\scripts\local_dispatcher_v1.ps1 -PollOnce -IssueNumber <N> [-PostResultComment]."
    }

    if ($selectedModes.Count -gt 1) {
        throw "Choose exactly one mode. Supplied modes: $($selectedModes -join ', ')."
    }

    if ($PostResultComment -and -not $PollOnce) {
        throw "-PostResultComment is valid only with -PollOnce."
    }

    Invoke-PollOnce
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
