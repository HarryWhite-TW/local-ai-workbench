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

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRun

.EXAMPLE
.\scripts\local_runner_v2.ps1 -RunOnce

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalDryRun -IssueNumber 39

.EXAMPLE
.\scripts\local_runner_v2.ps1 -ApprovalOnce -IssueNumber 41

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRun -Repo "HarryWhite-TW/local-ai-workbench" -MaxIssues 20
#>

param(
    [switch]$DryRun,
    [switch]$RunOnce,
    [switch]$ApprovalDryRun,
    [switch]$ApprovalOnce,
    [int]$IssueNumber = 0,
    [ValidateNotNullOrEmpty()]
    [string]$Repo = "HarryWhite-TW/local-ai-workbench",
    [ValidateRange(1, 100)]
    [int]$MaxIssues = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v2"
$RunnerVersion = "v2A-runonce-reviewbundle"
$ExpectedApprovalRepo = "HarryWhite-TW/local-ai-workbench"
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
$ApprovalRequiredFields = @(
    "protocol",
    "action",
    "issue",
    "repo",
    "branch",
    "head",
    "review",
    "diff",
    "files",
    "filelist",
    "expires"
)
$ApprovalKnownFields = $ApprovalRequiredFields
$ApprovalDryRunNoWriteGuarantee = "ApprovalDryRun detection only: does not call Codex, run runner v1, modify files, post GitHub comments, stage files, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run a polling loop, daemon, or scheduler."
$ApprovalOnceSafetyBoundary = "ApprovalOnce delegates only to runner v1 ReviewBundle for the approved issue. It does not call Codex directly, run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run a polling loop."

function Invoke-ReadOnlyCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
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
    }

    $text = (@($output) | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    return [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = $text.TrimEnd()
        Stderr = ""
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

    foreach ($requiredField in $ApprovalRequiredFields) {
        if (-not $seenFields.Contains($requiredField)) {
            throw "Missing required approval marker field '$requiredField'."
        }
    }

    return $fields
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
    Assert-ApprovalFieldEquals -Fields $Fields -Name "filelist" -Expected "none"

    if ($ExpiresUtc -le $NowUtc) {
        throw "Approval marker expired at $($ExpiresUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")); current UTC time is $($NowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))."
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
        "number,state,comments"
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

    if ($selectedModes.Count -eq 0) {
        throw "Missing mode. Use: .\scripts\local_runner_v2.ps1 -DryRun, .\scripts\local_runner_v2.ps1 -RunOnce, .\scripts\local_runner_v2.ps1 -ApprovalDryRun -IssueNumber <N>, or .\scripts\local_runner_v2.ps1 -ApprovalOnce -IssueNumber <N>."
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

    if ($DryRun) {
        Invoke-DryRun
    }
    elseif ($RunOnce) {
        Invoke-RunOnce
    }
    elseif ($ApprovalDryRun) {
        Invoke-ApprovalDryRun
    }
    else {
        Invoke-ApprovalOnce
    }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
