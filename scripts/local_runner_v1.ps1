<#
.SYNOPSIS
Runs a write-capable GitHub Issue through Codex and posts a review bundle.

.DESCRIPTION
local_runner_v1.ps1 is review-bundle-only. It may leave Codex changes unstaged
for human review, but the runner itself never stages, commits, pushes, closes
issues, edits labels, creates PRs, or consumes approval tokens.

The repo must be clean before the runner starts. If it is dirty, the runner
stops before calling Codex and posts a failure review bundle when possible.

.EXAMPLE
.\scripts\local_runner_v1.ps1 -IssueNumber 23
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$IssueNumber
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v1"
$RunnerVersion = "v1-review-bundle-only"
$Repo = "HarryWhite-TW/local-ai-workbench"
$RepoPath = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$Gh = "C:\Program Files\GitHub CLI\gh.exe"
$MaxIssueBodyChars = 16000
$MaxCodexStdoutChars = 9000
$MaxStderrPreviewChars = 1200
$MaxStderrPreviewLines = 8
$MaxGitOutputChars = 5000

function Invoke-Captured {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    $stdoutFile = New-TemporaryFile
    $stderrFile = New-TemporaryFile
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command 1> $stdoutFile.FullName 2> $stderrFile.FullName
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        $stdout = Get-Content -LiteralPath $stdoutFile.FullName -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrFile.FullName -Raw -ErrorAction SilentlyContinue
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

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs
    )

    return Invoke-Captured { git -C $RepoPath @GitArgs }
}

function Require-Success {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Result,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    if ($Result.ExitCode -ne 0) {
        throw "$Action failed with exit code $($Result.ExitCode): $($Result.Stderr)"
    }
}

function Truncate-Text {
    param(
        [AllowNull()]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [int]$MaxChars,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if ([string]::IsNullOrEmpty($Text) -or $Text.Length -le $MaxChars) {
        return $Text
    }

    return $Text.Substring(0, $MaxChars) + "`n`n[truncated by ${RunnerName}: $Label]"
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

function Get-GitStatusShort {
    $result = Invoke-Git -GitArgs @("status", "--short")
    Require-Success -Result $result -Action "git status --short"
    return $result.Stdout.TrimEnd()
}

function Get-GitOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $result = Invoke-Git -GitArgs $GitArgs
    Require-Success -Result $result -Action $Action
    return $result.Stdout.TrimEnd()
}

function Get-ModifiedFilesFromStatus {
    param(
        [AllowEmptyString()]
        [string]$Status
    )

    if ([string]::IsNullOrWhiteSpace($Status)) {
        return "(none)"
    }

    $lines = $Status -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $paths = foreach ($line in $lines) {
        if ($line.Length -le 3) {
            $line.Trim()
        }
        else {
            $line.Substring(3).Trim()
        }
    }

    return (($paths | Sort-Object -Unique) -join [Environment]::NewLine)
}

function Test-IssueAllowsWriteCapableRun {
    param(
        [AllowNull()]
        [string]$Title,
        [AllowNull()]
        [string]$Body
    )

    $combined = "$Title`n$Body"
    return ($combined -match "(?i)\bwrite-capable\b|(?i)\bwrite capable\b|(?i)\breview-bundle\b|(?i)\breview bundle\b")
}

function Get-StderrSummary {
    param(
        [AllowNull()]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [string]$ExitCode
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return [pscustomobject]@{
            Present = "no"
            Classification = "none"
            Preview = "(none)"
            Truncated = "no"
            LineCount = 0
            CharCount = 0
            KnownNoise = "none detected"
        }
    }

    $lines = $Text -split "\r?\n"
    $previewLines = @()
    $hasCloudflareHtml = $false
    $hasPluginSyncWarning = $false
    $hasPowerShellWrapper = $false
    $hasResearchPreview = $false

    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            continue
        }

        if ($trimmed -match "Cloudflare|cf_chl|challenge-platform|Enable JavaScript and cookies|<html>|</html>|<script|</script>") {
            $hasCloudflareHtml = $true
            continue
        }
        if ($trimmed -match "plugin sync|plugins/list|plugins/featured|403 Forbidden|startup remote plugin sync failed|failed to warm featured plugin") {
            $hasPluginSyncWarning = $true
            continue
        }
        if ($trimmed -match "NativeCommandError|At .*codex\.ps1|CategoryInfo|FullyQualifiedErrorId|node\.exe :|RemoteException") {
            $hasPowerShellWrapper = $true
            continue
        }
        if ($trimmed -match "research preview") {
            $hasResearchPreview = $true
            continue
        }
        if ($trimmed -match "^\s*<" -or $trimmed -match "^\s*(var |function|\}|\{)") {
            continue
        }
        if ($trimmed.Length -gt 260) {
            $trimmed = $trimmed.Substring(0, 260) + "..."
        }

        $previewLines += $trimmed
        if ($previewLines.Count -ge $MaxStderrPreviewLines) {
            break
        }
    }

    if ($previewLines.Count -eq 0) {
        $previewLines = @("[stderr contained only known runner/Codex warning noise or omitted markup]")
    }

    $preview = $previewLines -join [Environment]::NewLine
    $truncated = if (($Text.Length -gt $MaxStderrPreviewChars) -or ($lines.Count -gt $previewLines.Count)) { "yes" } else { "no" }
    if ($preview.Length -gt $MaxStderrPreviewChars) {
        $preview = $preview.Substring(0, $MaxStderrPreviewChars) + "`n[stderr preview truncated by $RunnerName]"
        $truncated = "yes"
    }

    $knownNoise = @()
    if ($hasResearchPreview) { $knownNoise += "Codex research preview notice" }
    if ($hasPluginSyncWarning) { $knownNoise += "plugin sync / 403 warning" }
    if ($hasPowerShellWrapper) { $knownNoise += "PowerShell codex.ps1 wrapper noise" }
    if ($hasCloudflareHtml) { $knownNoise += "Cloudflare/HTML challenge response omitted" }
    $knownNoiseSummary = if ($knownNoise.Count -eq 0) { "none detected" } else { $knownNoise -join "; " }

    return [pscustomobject]@{
        Present = "yes"
        Classification = if ($ExitCode -eq "0") { "non-blocking stderr/warning" } else { "stderr with non-zero exit" }
        Preview = $preview
        Truncated = $truncated
        LineCount = $lines.Count
        CharCount = $Text.Length
        KnownNoise = $knownNoiseSummary
    }
}

function New-ReviewBundleComment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$IssueNumberText,
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$HeadBefore,
        [Parameter(Mandatory = $true)]
        [string]$HeadAfter,
        [Parameter(Mandatory = $true)]
        [string]$CodexExitCode,
        [Parameter(Mandatory = $true)]
        [string]$RepoCleanBefore,
        [Parameter(Mandatory = $true)]
        [string]$ModifiedFiles,
        [Parameter(Mandatory = $true)]
        [string]$DiffStat,
        [Parameter(Mandatory = $true)]
        [string]$CachedDiffStat,
        [Parameter(Mandatory = $true)]
        [string]$CommandsSummary,
        [Parameter(Mandatory = $true)]
        [string]$CodexFinalReport,
        [Parameter(Mandatory = $true)]
        [object]$StderrSummary,
        [Parameter(Mandatory = $true)]
        [string]$FinalStatus
    )

    $TextFence = '```text'
    $Fence = '```'
    $displayDiffStat = Format-Block -Text (Truncate-Text -Text $DiffStat -MaxChars $MaxGitOutputChars -Label "git diff --stat") -EmptyText "(no unstaged tracked diff)"
    $displayCachedDiffStat = Format-Block -Text (Truncate-Text -Text $CachedDiffStat -MaxChars $MaxGitOutputChars -Label "git diff --cached --stat") -EmptyText "(no staged diff)"
    $displayFinalStatus = Format-Block -Text (Truncate-Text -Text $FinalStatus -MaxChars $MaxGitOutputChars -Label "final git status") -EmptyText "(clean)"
    $displayModifiedFiles = Format-Block -Text (Truncate-Text -Text $ModifiedFiles -MaxChars $MaxGitOutputChars -Label "modified files") -EmptyText "(none)"
    $displayFinalReport = Format-Block -Text $CodexFinalReport -EmptyText "(no Codex stdout captured)"

    return @"
## local-runner-v1 review bundle

### Run metadata

- Runner version: $RunnerVersion
- Issue number: #$IssueNumberText
- Branch: $Branch
- HEAD before: $HeadBefore
- HEAD after: $HeadAfter
- Codex exit code: $CodexExitCode

### Safety status

- Repo clean before start: $RepoCleanBefore
- No stage performed: yes
- No commit performed: yes
- No push performed: yes
- No issue close performed: yes
- No label edit performed: yes
- No PR created: yes
- Approval tokens consumed: no; this version does not implement approval token consumption

### Modified files

$TextFence
$displayModifiedFiles
$Fence

### git diff --stat

$TextFence
$displayDiffStat
$Fence

### git diff --cached --stat

$TextFence
$displayCachedDiffStat
$Fence

### Commands / verification summary

$TextFence
$CommandsSummary
$Fence

### Codex final report

$TextFence
$displayFinalReport
$Fence

### Stderr summary if present

- Present: $($StderrSummary.Present)
- Classification: $($StderrSummary.Classification)
- Truncated: $($StderrSummary.Truncated)
- Lines/chars: $($StderrSummary.LineCount) lines / $($StderrSummary.CharCount) chars
- Known omitted noise: $($StderrSummary.KnownNoise)

$TextFence
$($StderrSummary.Preview)
$Fence

### Final git status

$TextFence
$displayFinalStatus
$Fence

### Next approval note

This is review-bundle-only. Human / ChatGPT review is required. Do not commit until a separate approval step is implemented or manual commit instructions are given.
"@
}

function Post-IssueComment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Comment
    )

    $commentFile = New-TemporaryFile
    try {
        Set-Content -LiteralPath $commentFile.FullName -Value $Comment -Encoding UTF8
        $commentResult = Invoke-Captured {
            & $Gh issue comment $IssueNumber --repo $Repo --body-file $commentFile.FullName
        }
    }
    finally {
        Remove-Item -LiteralPath $commentFile.FullName -Force -ErrorAction SilentlyContinue
    }

    return $commentResult
}

if (-not (Test-Path -LiteralPath $Gh)) {
    throw "GitHub CLI was not found at expected path: $Gh"
}
if (-not (Test-Path -LiteralPath $RepoPath)) {
    throw "Repository path was not found: $RepoPath"
}

$branch = Format-Block -Text (Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current") -EmptyText "(detached HEAD)"
$headBefore = Get-GitOutput -GitArgs @("rev-parse", "--short", "HEAD") -Action "git rev-parse --short HEAD"
$initialStatus = Get-GitStatusShort

if (-not [string]::IsNullOrWhiteSpace($initialStatus)) {
    $diffStat = Get-GitOutput -GitArgs @("diff", "--stat") -Action "git diff --stat"
    $cachedDiffStat = Get-GitOutput -GitArgs @("diff", "--cached", "--stat") -Action "git diff --cached --stat"
    $stderrSummary = Get-StderrSummary -Text "" -ExitCode "not-run"
    $comment = New-ReviewBundleComment `
        -IssueNumberText ([string]$IssueNumber) `
        -Branch $branch `
        -HeadBefore $headBefore `
        -HeadAfter $headBefore `
        -CodexExitCode "not run; repo dirty before start" `
        -RepoCleanBefore "no" `
        -ModifiedFiles (Get-ModifiedFilesFromStatus -Status $initialStatus) `
        -DiffStat $diffStat `
        -CachedDiffStat $cachedDiffStat `
        -CommandsSummary "Codex was not run because the repo was dirty before start." `
        -CodexFinalReport "Codex was not run. Clean or commit/stash existing changes before using local-runner-v1." `
        -StderrSummary $stderrSummary `
        -FinalStatus $initialStatus

    $postResult = Post-IssueComment -Comment $comment
    if ($postResult.ExitCode -ne 0) {
        Write-Error "Repo is dirty before start, and posting the failure bundle failed: $($postResult.Stderr)"
    }
    Write-Output "Repo is dirty before start. Codex was not run."
    exit 2
}

$issueJsonResult = Invoke-Captured {
    & $Gh issue view $IssueNumber --repo $Repo --json title,body,url,number
}
Require-Success -Result $issueJsonResult -Action "gh issue view"

$issue = $issueJsonResult.Stdout | ConvertFrom-Json
$issueTitle = [string]$issue.title
$issueBody = [string]$issue.body

if (-not (Test-IssueAllowsWriteCapableRun -Title $issueTitle -Body $issueBody)) {
    $stderrSummary = Get-StderrSummary -Text "" -ExitCode "not-run"
    $comment = New-ReviewBundleComment `
        -IssueNumberText ([string]$IssueNumber) `
        -Branch $branch `
        -HeadBefore $headBefore `
        -HeadAfter $headBefore `
        -CodexExitCode "not run; issue missing write-capable marker" `
        -RepoCleanBefore "yes" `
        -ModifiedFiles "(none)" `
        -DiffStat "" `
        -CachedDiffStat "" `
        -CommandsSummary "Codex was not run because the issue did not explicitly identify itself as write-capable or review-bundle capable." `
        -CodexFinalReport "Codex was not run. Add an explicit write-capable or review-bundle marker to the issue before using local-runner-v1." `
        -StderrSummary $stderrSummary `
        -FinalStatus "(clean)"

    $postResult = Post-IssueComment -Comment $comment
    if ($postResult.ExitCode -ne 0) {
        throw "gh issue comment failed with exit code $($postResult.ExitCode): $($postResult.Stderr)"
    }
    Write-Output $postResult.Stdout
    exit 3
}

if ($null -eq (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "codex command was not found on PATH for this PowerShell session."
}

$issueBodyForPrompt = Truncate-Text -Text $issueBody -MaxChars $MaxIssueBodyChars -Label "issue body"

$prompt = @"
You are running inside local-runner-v1 review-bundle-only mode for the repository at:
$RepoPath

This is a write-capable local Codex run for a GitHub Issue, but it is review-bundle-only.

You may implement the requested repo changes locally when the issue asks for code or documentation changes. Keep changes small and reviewable. Do not use scripts/local_runner.ps1. Do not stage, commit, push, merge, create branches, create PRs, close issues, edit labels, or consume approval tokens. Leave any changes unstaged for human review.

At the end, provide the exact final report structure requested by the issue. Include commands run and test results clearly so the review bundle can quote your final report.

Issue #$($issue.number): $issueTitle
URL: $($issue.url)

Issue body:
$issueBodyForPrompt
"@

$codexResult = Invoke-Captured {
    Push-Location -LiteralPath $RepoPath
    try {
        $prompt | codex --ask-for-approval never exec --sandbox workspace-write -C "." -
    }
    finally {
        Pop-Location
    }
}

$headAfter = Get-GitOutput -GitArgs @("rev-parse", "--short", "HEAD") -Action "git rev-parse --short HEAD"
$finalStatus = Get-GitStatusShort
$diffStatAfter = Get-GitOutput -GitArgs @("diff", "--stat") -Action "git diff --stat"
$cachedDiffStatAfter = Get-GitOutput -GitArgs @("diff", "--cached", "--stat") -Action "git diff --cached --stat"
$modifiedFiles = Get-ModifiedFilesFromStatus -Status $finalStatus
$codexFinalReport = Truncate-Text -Text $codexResult.Stdout -MaxChars $MaxCodexStdoutChars -Label "Codex final report"
$stderrSummaryAfter = Get-StderrSummary -Text $codexResult.Stderr -ExitCode ([string]$codexResult.ExitCode)
$commandsSummary = "Review the Codex final report below for commands and verification results reported by Codex. The runner also captured final git status, git diff --stat, and git diff --cached --stat. The runner did not run stage, commit, push, issue close, label edit, or PR commands."

$comment = New-ReviewBundleComment `
    -IssueNumberText ([string]$IssueNumber) `
    -Branch $branch `
    -HeadBefore $headBefore `
    -HeadAfter $headAfter `
    -CodexExitCode ([string]$codexResult.ExitCode) `
    -RepoCleanBefore "yes" `
    -ModifiedFiles $modifiedFiles `
    -DiffStat $diffStatAfter `
    -CachedDiffStat $cachedDiffStatAfter `
    -CommandsSummary $commandsSummary `
    -CodexFinalReport $codexFinalReport `
    -StderrSummary $stderrSummaryAfter `
    -FinalStatus $finalStatus

$commentResult = Post-IssueComment -Comment $comment
if ($commentResult.ExitCode -ne 0) {
    throw "gh issue comment failed with exit code $($commentResult.ExitCode): $($commentResult.Stderr)"
}

Write-Output $commentResult.Stdout
exit $codexResult.ExitCode
