<#
.SYNOPSIS
Detects runner v2A ReviewBundle-ready issues and can run one ReviewBundle.

.DESCRIPTION
local_runner_v2.ps1 is a local, on-demand v2A runner. In -DryRun mode it checks
local repository state, reads open GitHub issues, prints matching candidate
issues, and stops. In -RunOnce mode it requires exactly one matching candidate
and delegates only to runner v1 ReviewBundle for that issue.

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRun

.EXAMPLE
.\scripts\local_runner_v2.ps1 -RunOnce

.EXAMPLE
.\scripts\local_runner_v2.ps1 -DryRun -Repo "HarryWhite-TW/local-ai-workbench" -MaxIssues 20
#>

param(
    [switch]$DryRun,
    [switch]$RunOnce,
    [ValidateNotNullOrEmpty()]
    [string]$Repo = "HarryWhite-TW/local-ai-workbench",
    [ValidateRange(1, 100)]
    [int]$MaxIssues = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v2"
$RunnerVersion = "v2A-runonce-reviewbundle"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$RequiredMarkers = @(
    "Runner marker: runner-v2-reviewbundle-ready",
    "write-capable",
    "review-bundle capable"
)
$NoWriteGuarantee = "DryRun detection only: does not call Codex, run runner v1, modify files, post comments, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, or invoke external agents."
$RunOnceSafetyBoundary = "RunOnce delegates only to runner v1 ReviewBundle for exactly one eligible candidate. It does not call Codex directly, run CommitApproved, stage, commit, push, close issues, edit labels, create PRs, merge, force push, install dependencies, change PATH or Windows settings, invoke external agents, or run a polling loop."

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
    & $powerShellPath -NoProfile -File $runnerV1Path -IssueNumber $IssueNumber
    if ($null -eq $LASTEXITCODE) {
        return 0
    }

    return [int]$LASTEXITCODE
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
    if ($DryRun -and $RunOnce) {
        throw "Choose exactly one mode. Use either .\scripts\local_runner_v2.ps1 -DryRun or .\scripts\local_runner_v2.ps1 -RunOnce."
    }

    if (-not $DryRun -and -not $RunOnce) {
        throw "Missing mode. Use: .\scripts\local_runner_v2.ps1 -DryRun or .\scripts\local_runner_v2.ps1 -RunOnce."
    }

    if ($DryRun) {
        Invoke-DryRun
    }
    else {
        Invoke-RunOnce
    }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
