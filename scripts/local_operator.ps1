<#
.SYNOPSIS
Creates a deterministic local operator report package.

.DESCRIPTION
local_operator.ps1 is a narrow local operator entrypoint. Report mode captures
repository state and writes a local review package under data/local-operator-runs.
It does not run user-supplied commands, delegate to other runners, modify source
documents, stage, commit, push, close issues, edit labels, create PRs, merge, or
start background work.

.EXAMPLE
.\scripts\local_operator.ps1 -Mode Report
#>

param(
    [string]$Mode = "Report"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-operator"
$RunnerVersion = "report-slice-1"
$SupportedMode = "Report"
$ArtifactRootRelative = "data/local-operator-runs"
$RequiredArtifactFiles = @(
    "summary.md",
    "metadata.json",
    "commands.jsonl",
    "transcript.txt",
    "git-before.txt",
    "git-after.txt",
    "diff-stat-before.txt",
    "diff-stat-after.txt",
    "no-files-modified.txt"
)

$script:CommandLog = @()
$script:TranscriptLines = New-Object System.Collections.Generic.List[string]
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Add-TranscriptLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = (Get-Date).ToUniversalTime().ToString("o")
    $script:TranscriptLines.Add("[$timestamp] $Message")
}

function Write-TextFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [AllowNull()]
        [string]$Content
    )

    if ($null -eq $Content) {
        $Content = ""
    }

    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
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

function Join-Lines {
    param(
        [AllowNull()]
        [string[]]$Lines
    )

    if ($null -eq $Lines -or $Lines.Count -eq 0) {
        return ""
    }

    return ($Lines -join [Environment]::NewLine).TrimEnd()
}

function ConvertTo-NormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [object]$Path
    )

    if ($null -eq $Path) {
        throw "Path cannot be null."
    }

    $pathValue = $Path
    if ($Path -is [array]) {
        if ($Path.Count -ne 1) {
            throw "Expected a single path, but received $($Path.Count) paths."
        }
        $pathValue = $Path[0]
    }

    if ($null -eq $pathValue) {
        throw "Path cannot be null."
    }

    if ($pathValue -is [System.Management.Automation.PathInfo]) {
        $pathText = [string]$pathValue.ProviderPath
    }
    else {
        $pathText = [string]$pathValue
    }

    $pathText = $pathText.Trim()
    if ([string]::IsNullOrWhiteSpace($pathText)) {
        throw "Path cannot be empty."
    }

    $resolvedPaths = @(Convert-Path -LiteralPath $pathText -ErrorAction Stop)
    if ($resolvedPaths.Count -ne 1) {
        throw "Expected a single resolved path, but received $($resolvedPaths.Count) paths."
    }

    $resolvedPathText = [string]$resolvedPaths[0]
    if ([string]::IsNullOrWhiteSpace($resolvedPathText)) {
        throw "Resolved path cannot be empty."
    }

    return $resolvedPathText.TrimEnd([char[]]@("\", "/"))
}

function Test-GitArgsAllowed {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs
    )

    $allowed = @(
        "rev-parse --is-inside-work-tree",
        "rev-parse --show-toplevel",
        "branch --show-current",
        "rev-parse HEAD",
        "status --porcelain=v1",
        "diff --name-only",
        "diff --stat"
    )
    $rendered = $GitArgs -join " "
    return $allowed -contains $rendered
}

function Invoke-AllowlistedGit {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    if (-not (Test-GitArgsAllowed -GitArgs $GitArgs)) {
        throw "Internal command is not allowlisted: git $($GitArgs -join ' ')"
    }

    $startedAt = (Get-Date).ToUniversalTime()
    Add-TranscriptLine "RUN $Action : git $($GitArgs -join ' ')"

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $output = & git -C $RepoRoot @GitArgs 2> $stderrPath
        $stderr = [System.IO.File]::ReadAllText($stderrPath).TrimEnd()
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
    }
    catch {
        $output = @($_.Exception.Message)
        $stderr = ""
        $exitCode = 1
    }
    finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $endedAt = (Get-Date).ToUniversalTime()
    $stdout = (@($output) | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    $stdout = $stdout.TrimEnd()

    $entry = [pscustomobject]@{
        timestampUtc = $startedAt.ToString("o")
        completedUtc = $endedAt.ToString("o")
        action = $Action
        command = "git -C <repo-root> $($GitArgs -join ' ')"
        exitCode = $exitCode
    }
    $script:CommandLog += $entry

    Add-TranscriptLine "EXIT $Action : $exitCode"
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        Add-TranscriptLine "OUTPUT $Action"
        foreach ($line in ($stdout -split "`r?`n")) {
            Add-TranscriptLine "  $line"
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        Add-TranscriptLine "STDERR $Action"
        foreach ($line in ($stderr -split "`r?`n")) {
            Add-TranscriptLine "  $line"
        }
    }

    if ($exitCode -ne 0) {
        $failureText = (Join-Lines -Lines @($stdout, $stderr))
        throw "$Action failed with exit code ${exitCode}: $failureText"
    }

    return $stdout
}

function Get-StatusLines {
    param(
        [AllowNull()]
        [string]$StatusText
    )

    if ([string]::IsNullOrWhiteSpace($StatusText)) {
        return @()
    }

    return @($StatusText -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Get-StatusPathPart {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StatusLine
    )

    if ($StatusLine.Length -le 3) {
        return ""
    }

    return $StatusLine.Substring(3)
}

function Test-IsArtifactStatusLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StatusLine,
        [Parameter(Mandatory = $true)]
        [string]$ArtifactPrefix
    )

    $pathPart = Get-StatusPathPart -StatusLine $StatusLine
    if ($pathPart -like "* -> *") {
        $parts = $pathPart -split " -> ", 2
        return ($parts[0].StartsWith($ArtifactPrefix) -and $parts[1].StartsWith($ArtifactPrefix))
    }

    return $pathPart.StartsWith($ArtifactPrefix)
}

function Get-SourceStatusLines {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$StatusText,
        [Parameter(Mandatory = $true)]
        [string]$ArtifactPrefix,
        [Parameter(Mandatory = $true)]
        [bool]$IncludeUntracked
    )

    $lines = Get-StatusLines -StatusText $StatusText
    return @($lines | Where-Object {
        $isArtifact = Test-IsArtifactStatusLine -StatusLine $_ -ArtifactPrefix $ArtifactPrefix
        $isUntracked = $_.StartsWith("?? ")
        (-not $isArtifact) -and ($IncludeUntracked -or (-not $isUntracked))
    })
}

function Get-UntrackedSourceStatusLines {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$StatusText,
        [Parameter(Mandatory = $true)]
        [string]$ArtifactPrefix
    )

    $lines = Get-StatusLines -StatusText $StatusText
    return @($lines | Where-Object {
        (-not (Test-IsArtifactStatusLine -StatusLine $_ -ArtifactPrefix $ArtifactPrefix)) -and $_.StartsWith("?? ")
    })
}

function New-GitSnapshotText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [AllowNull()]
        [string]$Status,
        [AllowNull()]
        [string]$DiffNameOnly
    )

    return @(
        "# $Title",
        "",
        "## git status --porcelain=v1",
        "",
        "``````text",
        (Format-Block -Text $Status),
        "``````",
        "",
        "## git diff --name-only",
        "",
        "``````text",
        (Format-Block -Text $DiffNameOnly),
        "``````",
        ""
    ) -join [Environment]::NewLine
}

function Write-ArtifactPackage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunDir,
        [Parameter(Mandatory = $true)]
        [object]$Metadata,
        [Parameter(Mandatory = $true)]
        [string]$Summary,
        [Parameter(Mandatory = $true)]
        [string]$NoFilesModifiedText,
        [Parameter(Mandatory = $true)]
        [string]$GitBeforeText,
        [Parameter(Mandatory = $true)]
        [string]$GitAfterText,
        [AllowNull()]
        [string]$DiffStatBefore,
        [AllowNull()]
        [string]$DiffStatAfter
    )

    Write-TextFile -Path (Join-Path $RunDir "summary.md") -Content $Summary
    Write-TextFile -Path (Join-Path $RunDir "metadata.json") -Content (($Metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine)

    $commandLines = @()
    foreach ($entry in $script:CommandLog) {
        $commandLines += ($entry | ConvertTo-Json -Compress -Depth 4)
    }
    Write-TextFile -Path (Join-Path $RunDir "commands.jsonl") -Content ((Join-Lines -Lines $commandLines) + [Environment]::NewLine)

    Write-TextFile -Path (Join-Path $RunDir "transcript.txt") -Content ((Join-Lines -Lines $script:TranscriptLines.ToArray()) + [Environment]::NewLine)
    Write-TextFile -Path (Join-Path $RunDir "git-before.txt") -Content $GitBeforeText
    Write-TextFile -Path (Join-Path $RunDir "git-after.txt") -Content $GitAfterText
    Write-TextFile -Path (Join-Path $RunDir "diff-stat-before.txt") -Content ((Format-Block -Text $DiffStatBefore) + [Environment]::NewLine)
    Write-TextFile -Path (Join-Path $RunDir "diff-stat-after.txt") -Content ((Format-Block -Text $DiffStatAfter) + [Environment]::NewLine)
    Write-TextFile -Path (Join-Path $RunDir "no-files-modified.txt") -Content $NoFilesModifiedText
}

if ($Mode -ne $SupportedMode) {
    throw "Unsupported mode '$Mode'. Supported modes: $SupportedMode."
}

$startedAtUtc = (Get-Date).ToUniversalTime()
$RepoRoot = ConvertTo-NormalizedPath -Path (Join-Path -Path $PSScriptRoot -ChildPath "..")
Add-TranscriptLine "$RunnerName $RunnerVersion starting in $Mode mode."
Add-TranscriptLine "Resolved repository root: $RepoRoot"

if (-not (Test-Path -LiteralPath (Join-Path -Path $RepoRoot -ChildPath ".git"))) {
    throw "Resolved path is not a Git repository root: $RepoRoot"
}

$insideWorkTree = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("rev-parse", "--is-inside-work-tree") -Action "verify work tree"
if ($insideWorkTree.Trim() -ne "true") {
    throw "Resolved path is not inside a Git work tree: $RepoRoot"
}

$gitTopLevel = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("rev-parse", "--show-toplevel") -Action "verify repository top level"
$normalizedGitTopLevel = (ConvertTo-NormalizedPath -Path $gitTopLevel)
if ($normalizedGitTopLevel -ne $RepoRoot) {
    throw "Repository root mismatch. Script root resolved to '$RepoRoot' but git top level is '$normalizedGitTopLevel'."
}

$branch = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("branch", "--show-current") -Action "capture branch"
if ([string]::IsNullOrWhiteSpace($branch)) {
    $branch = "(detached HEAD)"
}
$head = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("rev-parse", "HEAD") -Action "capture HEAD"

$statusBefore = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("status", "--porcelain=v1") -Action "capture git status before"
$diffNameBefore = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("diff", "--name-only") -Action "capture git diff name-only before"
$diffStatBefore = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("diff", "--stat") -Action "capture git diff stat before"

$runId = $startedAtUtc.ToString("yyyyMMdd-HHmmssZ") + "-Report"
$artifactRoot = Join-Path -Path $RepoRoot -ChildPath $ArtifactRootRelative
$runDir = Join-Path -Path $artifactRoot -ChildPath $runId
$artifactPrefix = ($ArtifactRootRelative.Replace("\", "/").TrimEnd("/") + "/" + $runId + "/")
$artifactStatusPrefix = ($ArtifactRootRelative.Replace("\", "/").TrimEnd("/") + "/")

New-Item -ItemType Directory -Path $runDir -Force | Out-Null
foreach ($fileName in $RequiredArtifactFiles) {
    Write-TextFile -Path (Join-Path $runDir $fileName) -Content "pending report content`n"
}
Add-TranscriptLine "Created report artifact directory: $runDir"

$statusAfter = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("status", "--porcelain=v1") -Action "capture git status after"
$diffNameAfter = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("diff", "--name-only") -Action "capture git diff name-only after"
$diffStatAfter = Invoke-AllowlistedGit -RepoRoot $RepoRoot -GitArgs @("diff", "--stat") -Action "capture git diff stat after"
$completedAtUtc = (Get-Date).ToUniversalTime()

$trackedSourceBefore = @(Get-SourceStatusLines -StatusText $statusBefore -ArtifactPrefix $artifactStatusPrefix -IncludeUntracked $false)
$trackedSourceAfter = @(Get-SourceStatusLines -StatusText $statusAfter -ArtifactPrefix $artifactStatusPrefix -IncludeUntracked $false)
$untrackedSourceAfter = @(Get-UntrackedSourceStatusLines -StatusText $statusAfter -ArtifactPrefix $artifactStatusPrefix)
$artifactStatusAfter = @((Get-StatusLines -StatusText $statusAfter) | Where-Object {
    Test-IsArtifactStatusLine -StatusLine $_ -ArtifactPrefix $artifactStatusPrefix
})

$trackedStatusBeforeText = Join-Lines -Lines $trackedSourceBefore
$trackedStatusAfterText = Join-Lines -Lines $trackedSourceAfter
$trackedSourceFilesModifiedByReport = (($trackedStatusBeforeText -ne $trackedStatusAfterText) -or ($diffNameBefore.TrimEnd() -ne $diffNameAfter.TrimEnd()))

$trackedModifiedText = if ($trackedSourceFilesModifiedByReport) { "Yes" } else { "No" }
$untrackedOutsideText = if ($untrackedSourceAfter.Count -eq 0) { "(none)" } else { Join-Lines -Lines $untrackedSourceAfter }
$artifactStatusText = if ($artifactStatusAfter.Count -eq 0) { "(none detected by git status)" } else { Join-Lines -Lines $artifactStatusAfter }

if ($trackedSourceFilesModifiedByReport) {
    $noFilesModifiedText = @(
        "Tracked source file state changed during Report mode.",
        "",
        "Tracked source status before:",
        (Format-Block -Text $trackedStatusBeforeText),
        "",
        "Tracked source status after:",
        (Format-Block -Text $trackedStatusAfterText),
        "",
        "This mode does not auto-clean, reset, stash, or revert."
    ) -join [Environment]::NewLine
}
else {
    $noFilesModifiedText = @(
        "No tracked source files were modified by Report mode.",
        "",
        "Expected local operator artifacts are under:",
        $artifactPrefix,
        "",
        "Tracked source status before:",
        (Format-Block -Text $trackedStatusBeforeText),
        "",
        "Tracked source status after:",
        (Format-Block -Text $trackedStatusAfterText),
        "",
        "Untracked source entries outside the artifact directory after report:",
        $untrackedOutsideText
    ) -join [Environment]::NewLine
}
$noFilesModifiedText = $noFilesModifiedText + [Environment]::NewLine

$gitBeforeText = New-GitSnapshotText -Title "Git Before Report Artifact Creation" -Status $statusBefore -DiffNameOnly $diffNameBefore
$gitAfterText = New-GitSnapshotText -Title "Git After Report Artifact Creation" -Status $statusAfter -DiffNameOnly $diffNameAfter

$summary = @(
    "# Local Operator Report",
    "",
    "- Runner: $RunnerName $RunnerVersion",
    "- Mode: $Mode",
    "- Repository root: $RepoRoot",
    "- Branch: $branch",
    "- HEAD: $head",
    "- Started UTC: $($startedAtUtc.ToString("o"))",
    "- Completed UTC: $($completedAtUtc.ToString("o"))",
    "- Artifact directory: $runDir",
    "- Tracked source files modified by Report mode: $trackedModifiedText",
    "",
    "## Expected artifact status",
    "",
    "``````text",
    $artifactStatusText,
    "``````",
    "",
    "## Untracked entries outside artifact directory after report",
    "",
    "``````text",
    $untrackedOutsideText,
    "``````",
    ""
) -join [Environment]::NewLine

$metadata = [pscustomobject]@{
    runner = $RunnerName
    version = $RunnerVersion
    mode = $Mode
    repoRoot = $RepoRoot
    branch = $branch
    head = $head
    startedUtc = $startedAtUtc.ToString("o")
    completedUtc = $completedAtUtc.ToString("o")
    artifactDirectory = $runDir
    artifactDirectoryRelative = $artifactPrefix.TrimEnd("/")
    trackedSourceFilesModifiedByReport = $trackedSourceFilesModifiedByReport
    expectedArtifactStatusAfter = $artifactStatusAfter
    trackedSourceStatusBefore = $trackedSourceBefore
    trackedSourceStatusAfter = $trackedSourceAfter
    untrackedSourceStatusAfter = $untrackedSourceAfter
    gitBefore = [pscustomobject]@{
        statusPorcelainV1 = $statusBefore
        diffNameOnly = $diffNameBefore
        diffStat = $diffStatBefore
    }
    gitAfter = [pscustomobject]@{
        statusPorcelainV1 = $statusAfter
        diffNameOnly = $diffNameAfter
        diffStat = $diffStatAfter
    }
    safetyBoundaries = @(
        "No user-supplied command execution.",
        "Switch-based Report mode only.",
        "Exact internal git command allowlist only.",
        "No runner v1 or runner v2 delegation.",
        "No stage, commit, push, issue close, label edit, PR creation, merge, force push, daemon, scheduler, dependency installation, API key use, PATH mutation, clean, reset, stash, or revert."
    )
}

Write-ArtifactPackage `
    -RunDir $runDir `
    -Metadata $metadata `
    -Summary $summary `
    -NoFilesModifiedText $noFilesModifiedText `
    -GitBeforeText $gitBeforeText `
    -GitAfterText $gitAfterText `
    -DiffStatBefore $diffStatBefore `
    -DiffStatAfter $diffStatAfter

Write-Host "Local operator Report complete."
Write-Host "Run artifact directory: $runDir"
Write-Host "Tracked source files modified by Report mode: $trackedModifiedText"
Write-Host "Expected artifact status after report:"
Write-Host (Format-Block -Text $artifactStatusText)
if ($untrackedSourceAfter.Count -gt 0) {
    Write-Host "Untracked entries outside artifact directory after report:"
    Write-Host $untrackedOutsideText
}
