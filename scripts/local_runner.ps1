param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$IssueNumber
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v0"
$Repo = "HarryWhite-TW/local-ai-workbench"
$RepoPath = "C:\Users\harry\OneDrive\$([char]0x6587)$([char]0x4EF6)\New project"
$Gh = "C:\Program Files\GitHub CLI\gh.exe"
$RunnerScriptPath = "scripts/local_runner.ps1"
$MaxIssueBodyChars = 12000
$MaxStdoutChars = 6000
$MaxStderrPreviewChars = 1200
$MaxStderrPreviewLines = 8

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

function Get-GitStatusShort {
    $result = Invoke-Captured { git -C $RepoPath status --short }
    if ($result.ExitCode -ne 0) {
        throw "git status failed with exit code $($result.ExitCode): $($result.Stderr)"
    }
    return $result.Stdout.TrimEnd()
}

function Test-AllowedStatus {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Status
    )

    if ([string]::IsNullOrWhiteSpace($Status)) {
        return $true
    }

    $lines = $Status -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($line in $lines) {
        $path = $line.Substring([Math]::Min(3, $line.Length)).Trim()
        $normalized = $path -replace "\\", "/"
        if (($normalized -ne $RunnerScriptPath) -and ($normalized -ne "scripts/")) {
            return $false
        }
    }

    return $true
}

function Truncate-Text {
    param(
        [AllowNull()]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [int]$MaxChars
    )

    if ([string]::IsNullOrEmpty($Text) -or $Text.Length -le $MaxChars) {
        return $Text
    }

    return $Text.Substring(0, $MaxChars) + "`n`n[truncated by local-runner-v0]"
}

function Get-StderrSummary {
    param(
        [AllowNull()]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return [pscustomobject]@{
            Present = "no"
            Classification = "none"
            Preview = "(none)"
            Truncated = "no"
            LineCount = 0
            CharCount = 0
        }
    }

    $lines = $Text -split "\r?\n"
    $previewLines = @()
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            continue
        }
        if ($trimmed -match "^\s*<" -or $trimmed -match "^\s*(var |function|\}|\{)") {
            continue
        }
        if ($trimmed.Length -gt 240) {
            $trimmed = $trimmed.Substring(0, 240) + "..."
        }
        $previewLines += $trimmed
        if ($previewLines.Count -ge $MaxStderrPreviewLines) {
            break
        }
    }

    if ($previewLines.Count -eq 0) {
        $previewLines = @("[stderr contained only omitted markup or blank lines]")
    }

    $preview = $previewLines -join [Environment]::NewLine
    $truncated = if (($Text.Length -gt $MaxStderrPreviewChars) -or ($lines.Count -gt $previewLines.Count)) { "yes" } else { "no" }
    if ($preview.Length -gt $MaxStderrPreviewChars) {
        $preview = $preview.Substring(0, $MaxStderrPreviewChars) + "`n[stderr preview truncated by local-runner-v0]"
        $truncated = "yes"
    }

    return [pscustomobject]@{
        Present = "yes"
        Classification = if ($ExitCode -eq 0) { "non-blocking stderr/warning" } else { "stderr with non-zero exit" }
        Preview = $preview
        Truncated = $truncated
        LineCount = $lines.Count
        CharCount = $Text.Length
    }
}

if (-not (Test-Path -LiteralPath $Gh)) {
    throw "GitHub CLI was not found at expected path: $Gh"
}

$initialStatus = Get-GitStatusShort
if (-not (Test-AllowedStatus -Status $initialStatus)) {
    throw "Repo is not clean enough to run. git status --short:`n$initialStatus"
}

$issueJsonResult = Invoke-Captured {
    & $Gh issue view $IssueNumber --repo $Repo --json title,body,url,number
}
if ($issueJsonResult.ExitCode -ne 0) {
    throw "gh issue view failed with exit code $($issueJsonResult.ExitCode): $($issueJsonResult.Stderr)"
}

$issue = $issueJsonResult.Stdout | ConvertFrom-Json
$issueBody = Truncate-Text -Text ([string]$issue.body) -MaxChars $MaxIssueBodyChars

$prompt = @"
You are running inside local-runner-v0 for the repository at:
$RepoPath

This is a read-only automation pilot. Do not modify files. Do not stage, commit, push, merge, create branches, create PRs, close issues, or edit labels. Do not run write-capable tasks. Only inspect the repository as needed.

Summarize the GitHub issue below and identify likely safe next steps for a human reviewer. Keep the answer concise and practical.

Issue #$($issue.number): $($issue.title)
URL: $($issue.url)

Issue body:
$issueBody
"@

$codexResult = Invoke-Captured {
    Push-Location -LiteralPath $RepoPath
    try {
        $prompt | codex --ask-for-approval never exec --sandbox read-only -C "." -
    }
    finally {
        Pop-Location
    }
}

$finalStatus = Get-GitStatusShort
$repoStayedClean = Test-AllowedStatus -Status $finalStatus

$codexStdout = Truncate-Text -Text $codexResult.Stdout -MaxChars $MaxStdoutChars
$stderrSummary = Get-StderrSummary -Text $codexResult.Stderr -ExitCode $codexResult.ExitCode
$cleanText = if ($repoStayedClean) { "yes" } else { "no" }
$displayStatus = if ([string]::IsNullOrWhiteSpace($finalStatus)) { "(clean)" } else { $finalStatus }
$initialDisplayStatus = if ([string]::IsNullOrWhiteSpace($initialStatus)) { "(clean)" } else { $initialStatus }
$stdoutDisplay = if ([string]::IsNullOrWhiteSpace($codexStdout)) { "(no stdout)" } else { $codexStdout }

$comment = @"
## local-runner-v0 result

- Runner: $RunnerName
- Issue: #$IssueNumber
- Codex exit code: $($codexResult.ExitCode)
- Repo clean before: $initialDisplayStatus
- Repo clean after except approved runner script: $cleanText
- Stderr present: $($stderrSummary.Present)
- Stderr classification: $($stderrSummary.Classification)
- Stderr lines/chars: $($stderrSummary.LineCount) lines / $($stderrSummary.CharCount) chars
- Stderr preview truncated: $($stderrSummary.Truncated)

### Stderr preview

````text
$($stderrSummary.Preview)
````

### Codex stdout

````text
$stdoutDisplay
````

### Final git status

````text
$displayStatus
````
"@

$commentFile = New-TemporaryFile
try {
    Set-Content -LiteralPath $commentFile.FullName -Value $comment -Encoding UTF8
    $commentResult = Invoke-Captured {
        & $Gh issue comment $IssueNumber --repo $Repo --body-file $commentFile.FullName
    }
}
finally {
    Remove-Item -LiteralPath $commentFile.FullName -Force -ErrorAction SilentlyContinue
}
if ($commentResult.ExitCode -ne 0) {
    throw "gh issue comment failed with exit code $($commentResult.ExitCode): $($commentResult.Stderr)"
}

Write-Output $commentResult.Stdout

if (-not $repoStayedClean) {
    exit 2
}

exit $codexResult.ExitCode
