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
    [int]$IssueNumber,
    [ValidateSet("ReviewBundle", "CommitApproved", "ApprovalStateDiagnostic")]
    [string]$Mode = "ReviewBundle",
    [string]$ApprovalToken = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v1"
$RunnerVersion = "v1-review-bundle-level3a"
$Repo = "HarryWhite-TW/local-ai-workbench"
$RepoPath = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$Gh = "C:\Program Files\GitHub CLI\gh.exe"
$MaxIssueBodyChars = 16000
$MaxCodexStdoutChars = 9000
$MaxStderrPreviewChars = 1200
$MaxStderrPreviewLines = 8
$MaxGitOutputChars = 5000
$ReviewBundleCodexTimeoutSeconds = 1200
$RunnerResultProtocol = "lawb.runner_result.v1"
$RunnerResultMarker = "LAWBRUNNER-RESULT protocol=$RunnerResultProtocol"
$script:CommitApprovedLocalCommitCreated = "unknown"
$script:CommitApprovedCommitSha = ""

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

function Format-CommandLineForDisplay {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $parts = @($FilePath) + @($Arguments)
    $displayParts = foreach ($part in $parts) {
        if ($part -match "\s") {
            '"' + ($part -replace '"', '\"') + '"'
        }
        else {
            $part
        }
    }
    return $displayParts -join " "
}

function Get-CommandCandidatePath {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Command
    )

    foreach ($propertyName in @("Source", "Path", "Definition")) {
        $property = $Command.PSObject.Properties[$propertyName]
        if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
            return [string]$property.Value
        }
    }

    return ""
}

function Resolve-CodexCommand {
    param(
        [object[]]$Commands = $null
    )

    if ($null -eq $Commands) {
        $Commands = @(Get-Command codex -All -ErrorAction SilentlyContinue)
    }

    if (@($Commands).Count -eq 0) {
        throw "codex command was not found on PATH for this PowerShell session."
    }

    $candidates = @()
    foreach ($command in @($Commands)) {
        $path = Get-CommandCandidatePath -Command $command
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $commandType = ""
        $commandTypeProperty = $command.PSObject.Properties["CommandType"]
        if ($null -ne $commandTypeProperty) {
            $commandType = [string]$commandTypeProperty.Value
        }

        $candidates += [pscustomobject]@{
            Command = $command
            Source = $path
            Extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
            CommandType = $commandType
        }
    }

    if ($candidates.Count -eq 0) {
        throw "codex command was found, but no launchable path could be resolved."
    }

    $selected = @($candidates | Where-Object { $_.Extension -eq ".exe" } | Select-Object -First 1)
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object { $_.Extension -eq ".cmd" } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object { $_.Extension -eq ".bat" } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object {
            $_.CommandType -eq "Application" -and $_.Extension -ne ".ps1"
        } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object { $_.Extension -ne ".ps1" } | Select-Object -First 1)
    }

    if ($selected.Count -eq 0) {
        throw "codex command was found, but only PowerShell script wrappers were available. Refusing to directly launch codex.ps1; ensure codex.cmd or codex.exe is available on PATH."
    }

    return [pscustomobject]@{
        Source = [string]$selected[0].Source
        Command = $selected[0].Command
        Reason = "resolved by local-runner-v1 launcher preference"
    }
}

function Get-GitHubCliCandidatePath {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Command
    )

    foreach ($propertyName in @("Source", "Path", "Definition")) {
        $property = $Command.PSObject.Properties[$propertyName]
        if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
            return [string]$property.Value
        }
    }

    return ""
}

function Resolve-GitHubCliCommand {
    param(
        [object[]]$Commands = $null,
        [string[]]$ExtraCandidatePaths = $null,
        [string]$DefaultPath = "C:\Program Files\GitHub CLI\gh.exe",
        [string]$PortablePath = ""
    )

    $candidatePaths = @()

    if (-not [string]::IsNullOrWhiteSpace($DefaultPath) -and (Test-Path -LiteralPath $DefaultPath)) {
        $candidatePaths += $DefaultPath
    }

    if ($null -eq $Commands) {
        $Commands = @(Get-Command gh -All -ErrorAction SilentlyContinue)
    }

    foreach ($command in @($Commands)) {
        $path = Get-GitHubCliCandidatePath -Command $command
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $candidatePaths += $path
    }

    if ([string]::IsNullOrWhiteSpace($PortablePath)) {
        $PortablePath = Join-Path $env:USERPROFILE "tools\gh-portable\bin\gh.exe"
    }

    $candidatePaths += $PortablePath

    if ($null -ne $ExtraCandidatePaths) {
        $candidatePaths += $ExtraCandidatePaths
    }

    $normalized = @()
    foreach ($path in $candidatePaths) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        if ($extension -eq ".ps1") {
            continue
        }

        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }

        $normalized += [pscustomobject]@{
            Source = $path
            Extension = $extension
        }
    }

    if (@($normalized).Count -eq 0) {
        throw "GitHub CLI was not found. Checked fixed Program Files path, PATH candidates, and portable user tools path."
    }

    $selected = @($normalized | Where-Object { $_.Extension -eq ".exe" } | Select-Object -First 1)
    if ($selected.Count -eq 0) {
        $selected = @($normalized | Where-Object { $_.Extension -eq ".cmd" } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        $selected = @($normalized | Select-Object -First 1)
    }

    return [string]$selected[0].Source
}

function ConvertTo-NativeArgumentString {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $escaped = foreach ($argument in $Arguments) {
        if ($argument -match '[\s"]') {
            '"' + ($argument -replace '"', '\"') + '"'
        }
        else {
            $argument
        }
    }
    return $escaped -join " "
}

function Get-LastNonEmptyLine {
    param(
        [AllowNull()]
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    $lines = $Text -split "\r?\n"
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        $line = $lines[$i].Trim()
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            if ($line.Length -gt 260) {
                return $line.Substring(0, 260) + "..."
            }
            return $line
        }
    }

    return ""
}

function Get-ProcessTreeIds {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $ids = @($ProcessId)
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        $ids += Get-ProcessTreeIds -ProcessId ([int]$child.ProcessId)
    }
    return @($ids | Select-Object -Unique)
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $stopped = @()
    $ids = @(Get-ProcessTreeIds -ProcessId $ProcessId | Sort-Object -Descending)
    foreach ($id in $ids) {
        $process = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }
        try {
            Stop-Process -Id $id -Force -ErrorAction Stop
            $stopped += $id
        }
        catch {
            Write-Warning "Could not stop timed-out child process ${id}: $($_.Exception.Message)"
        }
    }
    return $stopped
}

function Invoke-CapturedNativeProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [AllowNull()]
        [string]$StandardInput = "",
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, [int]::MaxValue)]
        [int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $process = $null
    $timedOut = $false
    $stopAttempted = $false
    $stoppedProcessIds = @()
    $commandLine = Format-CommandLineForDisplay -FilePath $FilePath -Arguments $Arguments
    $exitCode = 1
    $stdoutTask = $null
    $stderrTask = $null

    try {
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $FilePath
        $startInfo.Arguments = ConvertTo-NativeArgumentString -Arguments $Arguments
        $startInfo.WorkingDirectory = $WorkingDirectory
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardInput = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.CreateNoWindow = $true

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo

        $null = $process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not [string]::IsNullOrEmpty($StandardInput)) {
            $inputBytes = [System.Text.Encoding]::UTF8.GetBytes($StandardInput)
            $process.StandardInput.BaseStream.Write($inputBytes, 0, $inputBytes.Length)
            $process.StandardInput.BaseStream.Flush()
        }
        $process.StandardInput.Close()

        $completed = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $completed) {
            $timedOut = $true
            $stopAttempted = $true
            $stoppedProcessIds = @(Stop-ProcessTree -ProcessId ([int]$process.Id))
            $null = $process.WaitForExit(5000)
            $exitCode = 124
        }
        else {
            $process.WaitForExit()
            $exitCode = [int]$process.ExitCode
        }
    }
    catch {
        $stdout = if ($null -eq $stdoutTask) { "" } else { $stdoutTask.Result }
        $capturedStderr = if ($null -eq $stderrTask) { "" } else { $stderrTask.Result }
        $stderr = "$Action failed: $($_.Exception.Message)`n$capturedStderr"
        return [pscustomobject]@{
            ExitCode = 1
            Stdout = $stdout.TrimEnd()
            Stderr = $stderr.TrimEnd()
            TimedOut = $false
            TimeoutSeconds = $TimeoutSeconds
            CommandLine = $commandLine
            LastStdoutLine = Get-LastNonEmptyLine -Text $stdout
            LastStderrLine = Get-LastNonEmptyLine -Text $stderr
            ProcessId = if ($null -eq $process) { $null } else { $process.Id }
            StopAttempted = $stopAttempted
            StoppedProcessIds = @($stoppedProcessIds)
        }
    }

    $stdout = if ($null -eq $stdoutTask) { "" } else { $stdoutTask.Result }
    $stderr = if ($null -eq $stderrTask) { "" } else { $stderrTask.Result }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = if ($null -eq $stdout) { "" } else { $stdout.TrimEnd() }
        Stderr = if ($null -eq $stderr) { "" } else { $stderr.TrimEnd() }
        TimedOut = $timedOut
        TimeoutSeconds = $TimeoutSeconds
        CommandLine = $commandLine
        LastStdoutLine = Get-LastNonEmptyLine -Text $stdout
        LastStderrLine = Get-LastNonEmptyLine -Text $stderr
        ProcessId = if ($null -eq $process) { $null } else { $process.Id }
        StopAttempted = $stopAttempted
        StoppedProcessIds = @($stoppedProcessIds)
    }
}

function New-ChildProcessReviewBundleSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Result,
        [AllowNull()]
        [string]$FinalStatus
    )

    $partialCandidateExists = (-not [string]::IsNullOrWhiteSpace($FinalStatus)).ToString().ToLowerInvariant()
    $timedOut = ([bool]$Result.TimedOut).ToString().ToLowerInvariant()
    $stopAttempted = ([bool]$Result.StopAttempted).ToString().ToLowerInvariant()
    $stoppedIds = @($Result.StoppedProcessIds) -join ","
    if ([string]::IsNullOrWhiteSpace($stoppedIds)) {
        $stoppedIds = "none"
    }

    return @"
child_process_command=$($Result.CommandLine)
child_process_timeout_seconds=$($Result.TimeoutSeconds)
child_process_timed_out=$timedOut
child_process_exit_code=$($Result.ExitCode)
last_stdout_line=$(Format-Block -Text $Result.LastStdoutLine -EmptyText "(none)")
last_stderr_line=$(Format-Block -Text $Result.LastStderrLine -EmptyText "(none)")
partial_candidate_exists=$partialCandidateExists
stop_attempted=$stopAttempted
stopped_process_ids=$stoppedIds
fail_closed_on_timeout=$timedOut
no_tests_after_timeout=$timedOut
no_smoke_after_timeout=$timedOut
no_commit_push_close_after_timeout=true
"@
}

function New-RunnerResultSummaryJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$IssueNumberText,
        [Parameter(Mandatory = $true)]
        [string]$Action,
        [Parameter(Mandatory = $true)]
        [string]$Result,
        [Parameter(Mandatory = $true)]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [string]$Head,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ReviewId,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$DiffFingerprint,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FilesFingerprint,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ChangedFilesText,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FinalStatus,
        [Parameter(Mandatory = $true)]
        [string]$CodexExitCode
    )

    $issueValue = [int]$IssueNumberText
    $changedFiles = @(Convert-FileTextToArray -Text $ChangedFilesText)
    $finalClean = [string]::IsNullOrWhiteSpace($FinalStatus) -or $FinalStatus.Trim() -eq "(clean)"
    $codexStatus = if ($CodexExitCode -eq "0") { "passed" } elseif ($CodexExitCode -like "not run*") { "not_run" } else { "failed" }

    $summary = [ordered]@{
        schema = $RunnerResultProtocol
        repo = $Repo
        issue = $issueValue
        action = $Action
        result = $Result
        branch = $Branch
        head = $Head
        selected_issue = $issueValue
        review_id = if ([string]::IsNullOrWhiteSpace($ReviewId)) { $null } else { $ReviewId }
        diff_fingerprint = if ([string]::IsNullOrWhiteSpace($DiffFingerprint)) { $null } else { $DiffFingerprint }
        files_fingerprint = if ([string]::IsNullOrWhiteSpace($FilesFingerprint)) { $null } else { $FilesFingerprint }
        changed_files = $changedFiles
        validations = [ordered]@{
            git_status_clean = (New-RunnerValidationResult -Status $(if ($finalClean) { "passed" } else { "warning" }) -Summary $(if ($finalClean) { "Final git status is clean." } else { "Final git status reports local changes for review." }))
            codex = (New-RunnerValidationResult -Status $codexStatus -Summary "Codex exit code: $CodexExitCode")
            pytest = (New-RunnerValidationResult -Status "reported" -Summary "See Codex final report for test commands and results.")
            git_diff_check = (New-RunnerValidationResult -Status "reported" -Summary "See Codex final report for git diff --check result if run.")
        }
        safety = [ordered]@{
            no_stage = $true
            no_commit = $true
            no_push = $true
            no_issue_close = $true
            no_label = $true
            no_pr = $true
            no_merge = $true
            no_approval_chaining = $true
        }
        next_recommended_action = "chatgpt_review"
    }

    return ($summary | ConvertTo-Json -Depth 8)
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
        throw "Renamed or copied paths are not supported by runner v1 commit mode: $path"
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

        $fullPath = Join-Path -Path $RepoPath -ChildPath $path
        $resolvedParent = Resolve-Path -LiteralPath (Split-Path -Parent $fullPath) -ErrorAction SilentlyContinue
        if ($null -ne $resolvedParent -and -not $resolvedParent.Path.StartsWith($RepoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
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
        throw "Refusing commit-approved mode because staged files already exist:`n$($stagedLines -join [Environment]::NewLine)"
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
            $fullPath = Join-Path -Path $RepoPath -ChildPath $path
            if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
                throw "Untracked directories are not supported by runner v1 commit mode: $path"
            }
            $hash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
            "$path $hash"
        }
    }

    return (@($payloadLines) | Sort-Object) -join [Environment]::NewLine
}

function Get-ApprovalState {
    param(
        [Parameter(Mandatory = $true)]
        [int]$IssueNumberForState,
        [switch]$RequireChanges
    )

    $branchForState = Format-Block -Text (Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current") -EmptyText "(detached HEAD)"
    $headForState = Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
    $statusForState = Get-GitStatusShort
    Assert-ReviewableStatus -Status $statusForState

    $statusLines = @(Get-StatusLines -Status $statusForState | Sort-Object)
    if ($RequireChanges -and $statusLines.Count -eq 0) {
        throw "No modified files are available for commit-approved mode."
    }

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
        ApprovalToken = "LRV1-APPROVE issue=$IssueNumberForState mode=Level3A branch=$branchForState head=$headForState review=$reviewId diff=$diffFingerprint files=$filesFingerprint"
    }
}

function Write-ApprovalStateDiagnostic {
    if ($IssueNumber -lt 1) {
        throw "ApprovalStateDiagnostic requires -IssueNumber <N>."
    }

    if (-not (Test-Path -LiteralPath $RepoPath)) {
        throw "Repository path was not found: $RepoPath"
    }

    $state = Get-ApprovalState -IssueNumberForState $IssueNumber

    Write-Output "$RunnerName $RunnerVersion"
    Write-Output "Mode: ApprovalStateDiagnostic"
    Write-Output "Read-only: yes"
    Write-Output "Issue number: #$($state.IssueNumber)"
    Write-Output "Branch: $($state.Branch)"
    Write-Output "Full HEAD: $($state.Head)"
    Write-Output "Git status raw hash: $($state.StatusRawHash)"
    Write-Output "Git status normalized visible representation:"
    Write-Output (Get-TextPreview -Text $state.Status)
    Write-Output "Status records used for fingerprinting:"
    Write-Output (Get-TextPreview -Text $state.StatusRecords)
    Write-Output "Modified files payload:"
    Write-Output (Get-TextPreview -Text $state.ModifiedFilesText)
    Write-Output "Tracked diff fingerprint: $($state.TrackedDiffHash)"
    Write-Output "Tracked diff length: $($state.TrackedDiffLength)"
    Write-Output "Tracked diff line count: $($state.TrackedDiffLineCount)"
    Write-Output "Untracked payload fingerprint: $($state.UntrackedPayloadHash)"
    Write-Output "Untracked payload visible representation:"
    Write-Output (Get-TextPreview -Text $state.UntrackedPayload)
    Write-Output "Files payload hash: $($state.FilesPayloadHash)"
    Write-Output "Files payload preview:"
    Write-Output (Get-TextPreview -Text $state.FilesPayload)
    Write-Output "Diff payload hash: $($state.DiffPayloadHash)"
    Write-Output "Diff payload length: $($state.DiffPayload.Length)"
    Write-Output "Diff payload line count: $(Get-TextLineCount -Text $state.DiffPayload)"
    Write-Output "Final files fingerprint: $($state.FilesFingerprint)"
    Write-Output "Final diff fingerprint: $($state.DiffFingerprint)"
    Write-Output "Final review id: $($state.ReviewId)"
    Write-Output "Approval token preview: $($state.ApprovalToken)"
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

function ConvertFrom-ApprovalToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Token
    )

    if ($Token -match "[^\x00-\x7F]") {
        throw "Approval token must be ASCII-only."
    }

    $parts = $Token.Trim() -split "\s+"
    if ($parts.Count -ne 8 -or $parts[0] -ne "LRV1-APPROVE") {
        throw "Approval token format is invalid."
    }

    $values = @{}
    foreach ($part in $parts[1..($parts.Count - 1)]) {
        if ($part -notmatch "^([a-z]+)=([A-Za-z0-9._/\-]+)$") {
            throw "Approval token field is invalid: $part"
        }
        $key = $Matches[1]
        if ($values.ContainsKey($key)) {
            throw "Approval token contains duplicate field: $key"
        }
        $values[$key] = $Matches[2]
    }

    foreach ($requiredKey in @("issue", "mode", "branch", "head", "review", "diff", "files")) {
        if (-not $values.ContainsKey($requiredKey)) {
            throw "Approval token is missing field: $requiredKey"
        }
    }

    return [pscustomobject]@{
        Issue = $values["issue"]
        Mode = $values["mode"]
        Branch = $values["branch"]
        Head = $values["head"]
        Review = $values["review"]
        Diff = $values["diff"]
        Files = $values["files"]
    }
}

function Assert-ApprovalMatchesState {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Token,
        [Parameter(Mandatory = $true)]
        [object]$State
    )

    $mismatches = @()
    if ($Token.Issue -ne $State.IssueNumber) { $mismatches += "issue expected $($State.IssueNumber), got $($Token.Issue)" }
    if ($Token.Mode -ne "Level3A") { $mismatches += "mode expected Level3A, got $($Token.Mode)" }
    if ($Token.Branch -ne $State.Branch) { $mismatches += "branch expected $($State.Branch), got $($Token.Branch)" }
    if ($Token.Head -ne $State.Head) { $mismatches += "head expected $($State.Head), got $($Token.Head)" }
    if ($Token.Review -ne $State.ReviewId) { $mismatches += "review expected $($State.ReviewId), got $($Token.Review)" }
    if ($Token.Diff -ne $State.DiffFingerprint) { $mismatches += "diff fingerprint mismatch" }
    if ($Token.Files -ne $State.FilesFingerprint) { $mismatches += "files fingerprint mismatch" }

    if ($mismatches.Count -gt 0) {
        throw "Approval token does not match current repo state:`n$($mismatches -join [Environment]::NewLine)"
    }
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
        [AllowEmptyString()]
        [string]$ReviewId,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$DiffFingerprint,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FilesFingerprint,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ApprovalToken,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ModifiedFiles,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$DiffStat,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$CachedDiffStat,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$CommandsSummary,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$CodexFinalReport,
        [Parameter(Mandatory = $true)]
        [object]$StderrSummary,
        [AllowEmptyString()]
        [string]$ChildProcessSummary = "",
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FinalStatus
    )

    $TextFence = '```text'
    $Fence = '```'
    $displayDiffStat = Format-Block -Text (Truncate-Text -Text $DiffStat -MaxChars $MaxGitOutputChars -Label "git diff --stat") -EmptyText "(no unstaged tracked diff)"
    $displayCachedDiffStat = Format-Block -Text (Truncate-Text -Text $CachedDiffStat -MaxChars $MaxGitOutputChars -Label "git diff --cached --stat") -EmptyText "(no staged diff)"
    $displayFinalStatus = Format-Block -Text (Truncate-Text -Text $FinalStatus -MaxChars $MaxGitOutputChars -Label "final git status") -EmptyText "(clean)"
    $displayModifiedFiles = Format-Block -Text (Truncate-Text -Text $ModifiedFiles -MaxChars $MaxGitOutputChars -Label "modified files") -EmptyText "(none)"
    $displayFinalReport = Format-Block -Text $CodexFinalReport -EmptyText "(no Codex stdout captured)"
    $displayChildProcessSummary = Format-Block -Text $ChildProcessSummary -EmptyText "child_process_timed_out=false`nno_commit_push_close_after_timeout=true"
    $runnerResult = if ($CodexExitCode -eq "0") { "success" } else { "failure" }
    $runnerResultJson = New-RunnerResultSummaryJson `
        -IssueNumberText $IssueNumberText `
        -Action "run-reviewbundle" `
        -Result $runnerResult `
        -Branch $Branch `
        -Head $HeadAfter `
        -ReviewId $ReviewId `
        -DiffFingerprint $DiffFingerprint `
        -FilesFingerprint $FilesFingerprint `
        -ChangedFilesText $ModifiedFiles `
        -FinalStatus $FinalStatus `
        -CodexExitCode $CodexExitCode

    return @"
## local-runner-v1 review bundle

### Machine-readable runner result

$RunnerResultMarker
$runnerResultJson

### Run metadata

- Runner version: $RunnerVersion
- Issue number: #$IssueNumberText
- Branch: $Branch
- HEAD before: $HeadBefore
- HEAD after: $HeadAfter
- Codex exit code: $CodexExitCode
- Review id: $(Format-Block -Text $ReviewId -EmptyText "(not available)")
- Diff fingerprint: $(Format-Block -Text $DiffFingerprint -EmptyText "(not available)")
- Files fingerprint: $(Format-Block -Text $FilesFingerprint -EmptyText "(not available)")

### Safety status

- Repo clean before start: $RepoCleanBefore
- No stage performed: yes
- No commit performed: yes
- No push performed: yes
- No issue close performed: yes
- No label edit performed: yes
- No PR created: yes
- Approval tokens consumed in this run: no

### Modified files

$TextFence
$displayModifiedFiles
$Fence

### Approval context

Allowed files are the modified files listed above. Commit-approved mode recomputes branch, HEAD, modified files, diff fingerprint, and files fingerprint before staging.

$TextFence
$(Format-Block -Text $ApprovalToken -EmptyText "(not available)")
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

### Child process guard

$TextFence
$displayChildProcessSummary
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

This run is review-bundle-only. Human / ChatGPT review is required before any commit. To create a local commit after review, run this script separately with `-Mode CommitApproved` and enter the exact ASCII approval token for the current state. Do not push until a separate push step is approved.
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

function Get-SafeCommitTitle {
    param(
        [AllowNull()]
        [string]$Title
    )

    $safe = if ([string]::IsNullOrWhiteSpace($Title)) { "approved runner v1 changes" } else { $Title.Trim() }
    $safe = $safe -replace "[\r\n]+", " "
    if ($safe.Length -gt 160) {
        $safe = $safe.Substring(0, 160).TrimEnd()
    }
    return $safe
}

function New-CommitApprovedComment {
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
        [string]$CommitSha,
        [Parameter(Mandatory = $true)]
        [string]$ReviewId,
        [Parameter(Mandatory = $true)]
        [string]$DiffFingerprint,
        [Parameter(Mandatory = $true)]
        [string]$FilesFingerprint,
        [Parameter(Mandatory = $true)]
        [string]$ApprovalSource,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$CommittedFiles,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FinalStatus
    )

    $TextFence = '```text'
    $Fence = '```'
    $displayFiles = Format-Block -Text $CommittedFiles -EmptyText "(none)"
    $displayStatus = Format-Block -Text $FinalStatus -EmptyText "(clean)"

    return @"
## local-runner-v1 commit approved result

### Run metadata

- Runner version: $RunnerVersion
- Issue number: #$IssueNumberText
- Mode: CommitApproved
- Branch: $Branch
- HEAD before: $HeadBefore
- HEAD after: $HeadAfter
- Commit SHA: $CommitSha
- Review id: $ReviewId
- Diff fingerprint: $DiffFingerprint
- Files fingerprint: $FilesFingerprint

### Safety status

- Local approval token accepted: yes
- Exactly one local commit created: yes
- No push performed: yes
- No issue close performed: yes
- No label edit performed: yes
- No PR created: yes
- Approval source: $ApprovalSource

### Committed files

$TextFence
$displayFiles
$Fence

### Final git status

$TextFence
$displayStatus
$Fence

### Next step

This Level 3A mode created a local commit only. Review the commit before any separate push, issue close, label, or PR action.
"@
}

function New-CommitApprovedFailureComment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$IssueNumberText,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FailureReason,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Branch,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Head,
        [Parameter(Mandatory = $true)]
        [ValidateSet("yes", "no", "unknown")]
        [string]$LocalCommitCreated,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$CommitSha,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$FinalStatus,
        [Parameter(Mandatory = $true)]
        [bool]$MayHaveStagedFiles
    )

    $TextFence = '```text'
    $Fence = '```'
    $displayReason = Format-Block -Text $FailureReason -EmptyText "(no failure reason captured)"
    $displayBranch = Format-Block -Text $Branch -EmptyText "(unavailable)"
    $displayHead = Format-Block -Text $Head -EmptyText "(unavailable)"
    $displayCommitSha = Format-Block -Text $CommitSha -EmptyText "(none)"
    $displayStatus = Format-Block -Text $FinalStatus -EmptyText "(clean)"
    $cleanupNote = if ($MayHaveStagedFiles) {
        "Files may be staged. Human cleanup is required. The runner did not auto-reset."
    }
    else {
        "No staged files were detected in the final status. The runner did not auto-reset."
    }

    return @"
## local-runner-v1 commit approved failure

### Run metadata

- Runner version: $RunnerVersion
- Issue number: #$IssueNumberText
- Mode: CommitApproved
- Branch: $displayBranch
- HEAD: $displayHead
- Local commit created: $LocalCommitCreated
- Commit SHA: $displayCommitSha

### Failure reason

$TextFence
$displayReason
$Fence

### Safety status

- Local commit completed: $LocalCommitCreated
- No push performed: yes
- No issue close performed: yes
- No label edit performed: yes
- No PR created: yes
- No merge or force push performed: yes
- Auto-reset performed: no

### Final git status

$TextFence
$displayStatus
$Fence

### Cleanup note

$cleanupNote
"@
}

function Invoke-CommitApprovedMode {
    $script:CommitApprovedLocalCommitCreated = "no"
    $script:CommitApprovedCommitSha = ""

    if (-not (Test-Path -LiteralPath $Gh)) {
        throw "GitHub CLI was not found at expected path: $Gh"
    }
    if (-not (Test-Path -LiteralPath $RepoPath)) {
        throw "Repository path was not found: $RepoPath"
    }

    $issueJsonResult = Invoke-Captured {
        & $Gh issue view $IssueNumber --repo $Repo --json title,body,url,number
    }
    Require-Success -Result $issueJsonResult -Action "gh issue view"
    $issue = $issueJsonResult.Stdout | ConvertFrom-Json
    $issueTitle = [string]$issue.title
    $issueBody = [string]$issue.body

    if (-not (Test-IssueAllowsWriteCapableRun -Title $issueTitle -Body $issueBody)) {
        throw "Issue #$IssueNumber does not explicitly identify itself as write-capable or review-bundle capable."
    }

    $state = Get-ApprovalState -IssueNumberForState $IssueNumber -RequireChanges
    Assert-NoPreexistingStagedFiles -Status $state.Status

    Write-Output "local-runner-v1 CommitApproved expected approval context:"
    Write-Output "Issue: #$IssueNumber"
    Write-Output "Branch: $($state.Branch)"
    Write-Output "HEAD: $($state.Head)"
    Write-Output "Review id: $($state.ReviewId)"
    Write-Output "Diff fingerprint: $($state.DiffFingerprint)"
    Write-Output "Files fingerprint: $($state.FilesFingerprint)"
    Write-Output "Modified files:"
    Write-Output $state.ModifiedFilesText

    $tokenText = $ApprovalToken
    $approvalSource = "non-interactive parameter"
    if ([string]::IsNullOrWhiteSpace($tokenText)) {
        $tokenText = Read-Host "Enter exact ASCII approval token"
        $approvalSource = "local prompt"
    }
    $token = ConvertFrom-ApprovalToken -Token $tokenText

    $stateBeforeStage = Get-ApprovalState -IssueNumberForState $IssueNumber -RequireChanges
    Assert-NoPreexistingStagedFiles -Status $stateBeforeStage.Status
    Assert-ApprovalMatchesState -Token $token -State $stateBeforeStage

    $filesToStage = @($stateBeforeStage.ModifiedFiles)
    if ($filesToStage.Count -eq 0) {
        throw "No approved files to stage."
    }

    $gitAddPathspecs = @($filesToStage | ForEach-Object { ":(literal)$_" })
    $stageResult = Invoke-Captured {
        git -C $RepoPath add -- @gitAddPathspecs
    }
    Require-Success -Result $stageResult -Action "git add approved files"

    $stagedFiles = Get-GitOutput -GitArgs @("diff", "--cached", "--name-only") -Action "git diff --cached --name-only"
    $stagedFileList = @($stagedFiles -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object)
    $approvedFileList = @($filesToStage | Sort-Object)
    if (($stagedFileList -join "`n") -ne ($approvedFileList -join "`n")) {
        throw "Staged files do not match approved files after staging. Human cleanup required."
    }

    $commitMessage = "Issue #${IssueNumber}: $(Get-SafeCommitTitle -Title $issueTitle)"
    $headBeforeCommit = Get-GitOutput -GitArgs @("rev-parse", "--short", "HEAD") -Action "git rev-parse --short HEAD before commit"
    $commitResult = Invoke-Git -GitArgs @("commit", "-m", $commitMessage)
    Require-Success -Result $commitResult -Action "git commit"
    $headAfterCommit = Get-GitOutput -GitArgs @("rev-parse", "--short", "HEAD") -Action "git rev-parse --short HEAD after commit"
    $script:CommitApprovedLocalCommitCreated = "yes"
    $script:CommitApprovedCommitSha = $headAfterCommit
    $commitCount = Get-GitOutput -GitArgs @("rev-list", "--count", "$headBeforeCommit..HEAD") -Action "git rev-list --count"
    if ($commitCount -ne "1") {
        throw "Expected exactly one commit, but git rev-list reported $commitCount."
    }

    $finalStatusAfterCommit = Get-GitStatusShort
    $comment = New-CommitApprovedComment `
        -IssueNumberText ([string]$IssueNumber) `
        -Branch $stateBeforeStage.Branch `
        -HeadBefore $headBeforeCommit `
        -HeadAfter $headAfterCommit `
        -CommitSha $headAfterCommit `
        -ReviewId $stateBeforeStage.ReviewId `
        -DiffFingerprint $stateBeforeStage.DiffFingerprint `
        -FilesFingerprint $stateBeforeStage.FilesFingerprint `
        -ApprovalSource $approvalSource `
        -CommittedFiles ($approvedFileList -join [Environment]::NewLine) `
        -FinalStatus $finalStatusAfterCommit

    $commentResult = Post-IssueComment -Comment $comment
    if ($commentResult.ExitCode -ne 0) {
        throw "gh issue comment failed with exit code $($commentResult.ExitCode): $($commentResult.Stderr)"
    }

    Write-Output $commentResult.Stdout
}

if (-not (Test-Path -LiteralPath $RepoPath)) {
    throw "Repository path was not found: $RepoPath"
}

if ($Mode -eq "ApprovalStateDiagnostic") {
    Write-ApprovalStateDiagnostic
    exit 0
}

$Gh = Resolve-GitHubCliCommand

if ($Mode -eq "CommitApproved") {
    try {
        Invoke-CommitApprovedMode
        exit 0
    }
    catch {
        $failureReason = $_.Exception.Message
        $failureBranch = ""
        $failureHead = ""
        $failureStatus = ""
        $mayHaveStagedFiles = $true

        try {
            $failureBranch = Format-Block -Text (Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current") -EmptyText "(detached HEAD)"
        }
        catch {
            $failureBranch = "(unavailable: $($_.Exception.Message))"
        }

        try {
            $failureHead = Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
        }
        catch {
            $failureHead = "(unavailable: $($_.Exception.Message))"
        }

        try {
            $failureStatus = Get-GitStatusShort
            $mayHaveStagedFiles = $false
            foreach ($line in (Get-StatusLines -Status $failureStatus)) {
                if (($line.Substring(0, 1) -ne " ") -and ($line.Substring(0, 1) -ne "?")) {
                    $mayHaveStagedFiles = $true
                    break
                }
            }
        }
        catch {
            $failureStatus = "(unavailable: $($_.Exception.Message))"
            $mayHaveStagedFiles = $true
        }

        try {
            $failureComment = New-CommitApprovedFailureComment `
                -IssueNumberText ([string]$IssueNumber) `
                -FailureReason $failureReason `
                -Branch $failureBranch `
                -Head $failureHead `
                -LocalCommitCreated $script:CommitApprovedLocalCommitCreated `
                -CommitSha $script:CommitApprovedCommitSha `
                -FinalStatus $failureStatus `
                -MayHaveStagedFiles $mayHaveStagedFiles
            $failurePostResult = Post-IssueComment -Comment $failureComment
            if ($failurePostResult.ExitCode -ne 0) {
                Write-Warning "CommitApproved failed, and posting the failure comment also failed: $($failurePostResult.Stderr)"
            }
        }
        catch {
            Write-Warning "CommitApproved failed, and posting the failure comment also failed: $($_.Exception.Message)"
        }

        Write-Warning "CommitApproved failed: $failureReason"
        exit 4
    }
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
        -ReviewId "" `
        -DiffFingerprint "" `
        -FilesFingerprint "" `
        -ApprovalToken "" `
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
        -ReviewId "" `
        -DiffFingerprint "" `
        -FilesFingerprint "" `
        -ApprovalToken "" `
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

$codexCommand = Resolve-CodexCommand

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

$codexResult = Invoke-CapturedNativeProcess `
    -FilePath $codexCommand.Source `
    -Arguments @("--ask-for-approval", "never", "exec", "--sandbox", "workspace-write", "-C", ".", "-") `
    -WorkingDirectory $RepoPath `
    -StandardInput $prompt `
    -TimeoutSeconds $ReviewBundleCodexTimeoutSeconds `
    -Action "codex ReviewBundle candidate generation"

$headAfter = Get-GitOutput -GitArgs @("rev-parse", "--short", "HEAD") -Action "git rev-parse --short HEAD"
$finalStatus = Get-GitStatusShort
$diffStatAfter = Get-GitOutput -GitArgs @("diff", "--stat") -Action "git diff --stat"
$cachedDiffStatAfter = Get-GitOutput -GitArgs @("diff", "--cached", "--stat") -Action "git diff --cached --stat"
$modifiedFiles = Get-ModifiedFilesFromStatus -Status $finalStatus
$codexFinalReport = Truncate-Text -Text $codexResult.Stdout -MaxChars $MaxCodexStdoutChars -Label "Codex final report"
$stderrSummaryAfter = Get-StderrSummary -Text $codexResult.Stderr -ExitCode ([string]$codexResult.ExitCode)
$commandsSummary = "Review the Codex final report below for commands and verification results reported by Codex. The runner also captured final git status, git diff --stat, and git diff --cached --stat. The runner did not run stage, commit, push, issue close, label edit, or PR commands."
$childProcessSummary = New-ChildProcessReviewBundleSummary -Result $codexResult -FinalStatus $finalStatus
if ($codexResult.TimedOut) {
    $commandsSummary = "$commandsSummary Codex child process timed out after $($codexResult.TimeoutSeconds) second(s); runner stopped the child process tree when possible and did not continue into any higher-risk action."
}
$reviewId = ""
$diffFingerprint = ""
$filesFingerprint = ""
$approvalToken = ""
if (-not [string]::IsNullOrWhiteSpace($finalStatus)) {
    try {
        $approvalState = Get-ApprovalState -IssueNumberForState $IssueNumber -RequireChanges
        Assert-NoPreexistingStagedFiles -Status $approvalState.Status
        $reviewId = $approvalState.ReviewId
        $diffFingerprint = $approvalState.DiffFingerprint
        $filesFingerprint = $approvalState.FilesFingerprint
        $approvalToken = $approvalState.ApprovalToken
    }
    catch {
        $commandsSummary = "$commandsSummary Approval context unavailable: $($_.Exception.Message)"
    }
}

$comment = New-ReviewBundleComment `
    -IssueNumberText ([string]$IssueNumber) `
    -Branch $branch `
    -HeadBefore $headBefore `
    -HeadAfter $headAfter `
    -CodexExitCode ([string]$codexResult.ExitCode) `
    -RepoCleanBefore "yes" `
    -ReviewId $reviewId `
    -DiffFingerprint $diffFingerprint `
    -FilesFingerprint $filesFingerprint `
    -ApprovalToken $approvalToken `
    -ModifiedFiles $modifiedFiles `
    -DiffStat $diffStatAfter `
    -CachedDiffStat $cachedDiffStatAfter `
    -CommandsSummary $commandsSummary `
    -CodexFinalReport $codexFinalReport `
    -StderrSummary $stderrSummaryAfter `
    -ChildProcessSummary $childProcessSummary `
    -FinalStatus $finalStatus

$commentResult = Post-IssueComment -Comment $comment
if ($commentResult.ExitCode -ne 0) {
    throw "gh issue comment failed with exit code $($commentResult.ExitCode): $($commentResult.Stderr)"
}

Write-Output $commentResult.Stdout
exit $codexResult.ExitCode
