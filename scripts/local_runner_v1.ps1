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
    [ValidateRange(0, [int]::MaxValue)]
    [int]$IssueNumber = 0,
    [ValidateSet("ReviewBundle", "CommitApproved", "ApprovalStateDiagnostic", "CommitApprovalStateDiagnostic")]
    [string]$Mode = "ReviewBundle",
    [switch]$ToolResolutionPreflight,
    [string]$RequiredAction = "",
    [string]$ReviewedCodexPath = "",
    [string]$ApprovalToken = "",
    [string]$Repo = "HarryWhite-TW/local-ai-workbench",
    [string]$RepoPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RunnerName = "local-runner-v1"
$RunnerVersion = "v1-review-bundle-level3a"
$ControlRepoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "..")).Path
$repoVariable = Get-Variable -Name Repo -ErrorAction SilentlyContinue
if ($null -eq $repoVariable -or [string]::IsNullOrWhiteSpace([string]$repoVariable.Value)) {
    $Repo = "HarryWhite-TW/local-ai-workbench"
}
$repoPathVariable = Get-Variable -Name RepoPath -ErrorAction SilentlyContinue
if ($null -eq $repoPathVariable -or [string]::IsNullOrWhiteSpace([string]$repoPathVariable.Value)) {
    $RepoPath = $ControlRepoRoot
}
$SupportedTargetRepositories = @(
    "HarryWhite-TW/local-ai-workbench",
    "HarryWhite-TW/human-approval-automation-gateway"
)
$Gh = "C:\Program Files\GitHub CLI\gh.exe"
$MaxIssueBodyChars = 16000
$MaxCodexStdoutChars = 9000
$MaxStderrPreviewChars = 1200
$MaxStderrPreviewLines = 8
$MaxGitOutputChars = 5000
$ReviewBundleCodexTimeoutSeconds = 1200
$RunnerResultProtocol = "lawb.runner_result.v1"
$RunnerResultMarker = "LAWBRUNNER-RESULT protocol=$RunnerResultProtocol"
$ToolResolutionPreflightProtocol = "lawb.rv2_03_tool_resolution_preflight.v1"
$CandidateEvidenceProfile = "local_git_candidate_observation.v1"
$LocalIsolationProvider = "codex_cli_workspace_write"
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

function ConvertTo-NormalizedGitHubRepository {
    param([Parameter(Mandatory = $true)][string]$Url)
    $value = $Url.Trim().Replace("\", "/")
    foreach ($pattern in @(
        '^https?://github\.com/(?<repo>[^/]+/[^/]+?)(?:\.git)?/?$',
        '^git@github\.com:(?<repo>[^/]+/[^/]+?)(?:\.git)?$',
        '^ssh://git@github\.com/(?<repo>[^/]+/[^/]+?)(?:\.git)?/?$'
    )) {
        if ($value -match $pattern) {
            $repository = [string]$Matches["repo"]
            if ($repository.EndsWith(".git", [System.StringComparison]::OrdinalIgnoreCase)) {
                return $repository.Substring(0, $repository.Length - 4)
            }
            return $repository
        }
    }
    throw "wrong_target_origin"
}

function Assert-TargetRepositoryBinding {
    if ($Repo -notin $SupportedTargetRepositories) {
        throw "unsupported_target_repository: $Repo"
    }
    if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
        throw "target_repo_root_missing"
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $RepoPath).ProviderPath.TrimEnd("\", "/")
    $script:RepoPath = $resolvedRoot
    $topLevel = Invoke-Git -GitArgs @("rev-parse", "--show-toplevel")
    Require-Success -Result $topLevel -Action "git rev-parse --show-toplevel"
    $actualRoot = (Resolve-Path -LiteralPath $topLevel.Stdout.Trim()).ProviderPath.TrimEnd("\", "/")
    if (-not [string]::Equals($actualRoot, $resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "target_not_git_repository_root"
    }
    $origin = Invoke-Git -GitArgs @("remote", "get-url", "origin")
    Require-Success -Result $origin -Action "git remote get-url origin"
    $originRepository = ConvertTo-NormalizedGitHubRepository -Url $origin.Stdout
    if (-not [string]::Equals($originRepository, $Repo, [System.StringComparison]::Ordinal)) {
        throw "wrong_target_origin"
    }
    if ($Mode -ne "ReviewBundle" -and
        (-not [string]::Equals($Repo, "HarryWhite-TW/local-ai-workbench", [System.StringComparison]::Ordinal) -or
         -not [string]::Equals($RepoPath, $ControlRepoRoot, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "cross_repository_mode_not_supported"
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

function Get-Sha256File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "SHA-256 input file was not found: $Path"
    }
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    try {
        $hashBytes = $sha256.ComputeHash($stream)
        return (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $stream.Dispose()
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

function Invoke-BoundedGitObservation {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs
    )

    return Invoke-Captured {
        git -C $RepoPath `
            "--work-tree=$RepoPath" `
            -c "color.status=false" `
            -c "core.fsmonitor=false" `
            -c "core.ignoreStat=false" `
            -c "core.untrackedCache=false" `
            -c "status.relativePaths=false" `
            @GitArgs
    }
}

function Get-GitStatusShort {
    $result = Invoke-BoundedGitObservation -GitArgs @(
        "status",
        "--short",
        "--untracked-files=all",
        "--ignore-submodules=none"
    )
    Require-Success -Result $result -Action "bounded git status --short --untracked-files=all --ignore-submodules=none"
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

function Get-GitUntrackedFilesWithoutExcludes {
    $result = Invoke-BoundedGitObservation -GitArgs @(
        "ls-files",
        "--others",
        "--full-name",
        "--"
    )
    Require-Success -Result $result -Action "bounded git ls-files --others without excludes"
    return @(Convert-FileTextToArray -Text $result.Stdout)
}

function Test-IsBenignPythonCacheNoisePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = $Path.Replace("\", "/")
    return $normalized -match '(^|/)\.pytest_cache/(README\.md|CACHEDIR\.TAG|\.gitignore|v/cache/(nodeids|lastfailed|stepwise))$'
}

function Get-GitIndexVisibilityFiles {
    $result = Invoke-BoundedGitObservation -GitArgs @(
        "ls-files",
        "-v",
        "-f",
        "--full-name",
        "--"
    )
    Require-Success -Result $result -Action "bounded git ls-files index visibility inspection"

    $paths = @()
    foreach ($line in @($result.Stdout -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        if ($line.Length -lt 3 -or $line.Substring(1, 1) -ne " ") {
            throw "Unexpected git ls-files visibility line: $line"
        }
        $tag = $line.Substring(0, 1)
        if ([char]::IsLower($tag[0]) -or $tag -ceq "S") {
            $paths += $line.Substring(2).Trim()
        }
    }
    return @($paths | Sort-Object -Unique)
}

function Get-GitVisibilityMetadataFingerprint {
    $configuration = Invoke-BoundedGitObservation -GitArgs @(
        "config",
        "--list",
        "--show-origin",
        "--includes"
    )
    Require-Success -Result $configuration -Action "bounded git visibility configuration inspection"

    $entries = [System.Collections.Generic.List[string]]::new()
    $entries.Add("configuration=$(Get-Sha256Text -Text $configuration.Stdout)")
    foreach ($relativePath in @("info/exclude", "info/attributes", "info/sparse-checkout")) {
        $pathResult = Invoke-BoundedGitObservation -GitArgs @(
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            $relativePath
        )
        Require-Success -Result $pathResult -Action "git path resolution for $relativePath"
        $metadataPath = $pathResult.Stdout.Trim()
        $entries.Add("${relativePath}:path=$metadataPath")
        if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
            $entries.Add("${relativePath}:file=$(Get-Sha256File -Path $metadataPath)")
        }
        elseif (Test-Path -LiteralPath $metadataPath) {
            $entries.Add("${relativePath}:type=non_file")
        }
        else {
            $entries.Add("${relativePath}:type=absent")
        }
    }
    return Get-Sha256Text -Text ([string]::Join("`n", $entries))
}

function Get-ReviewBundleEffectiveChangedFiles {
    param(
        [AllowEmptyString()]
        [string]$Status,
        [AllowEmptyCollection()]
        [string[]]$UntrackedFilesBefore = @(),
        [AllowEmptyCollection()]
        [string[]]$UntrackedFilesAfter = @(),
        [AllowEmptyCollection()]
        [string[]]$IndexVisibilityFilesBefore = @(),
        [AllowEmptyCollection()]
        [string[]]$IndexVisibilityFilesAfter = @(),
        [AllowEmptyCollection()]
        [string[]]$AllowedFilesChanged = @()
    )

    $changed = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($path in @(Convert-FileTextToArray -Text (Get-ModifiedFilesFromStatus -Status $Status))) {
        $null = $changed.Add($path)
    }

    $before = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $after = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($path in @($UntrackedFilesBefore)) {
        $null = $before.Add($path)
    }
    foreach ($path in @($UntrackedFilesAfter)) {
        $null = $after.Add($path)
    }
    foreach ($path in @($before)) {
        if (-not $after.Contains($path) -and -not (Test-IsBenignPythonCacheNoisePath -Path $path)) {
            $null = $changed.Add($path)
        }
    }
    foreach ($path in @($after)) {
        if (-not $before.Contains($path) -and -not (Test-IsBenignPythonCacheNoisePath -Path $path)) {
            $null = $changed.Add($path)
        }
    }
    foreach ($path in @($IndexVisibilityFilesBefore) + @($IndexVisibilityFilesAfter)) {
        $null = $changed.Add($path)
    }
    foreach ($path in @($AllowedFilesChanged)) {
        $null = $changed.Add($path)
    }

    [string[]]$sortedPaths = @($changed)
    [System.Array]::Sort($sortedPaths, [System.StringComparer]::Ordinal)
    return $sortedPaths
}

function Get-BoundedCandidateManifest {
    param(
        [AllowEmptyCollection()]
        [string[]]$AllowedFiles = @()
    )

    $normalization = ConvertTo-NormalizedRuntimeContractPathSet `
        -Paths @($AllowedFiles) `
        -InvalidReason "invalid_allowed_file"
    $reasons = @($normalization.Reasons)
    $entries = [System.Collections.Generic.List[object]]::new()
    $repositoryRoot = [System.IO.Path]::GetFullPath($RepoPath).TrimEnd("\", "/")
    $repositoryPrefix = $repositoryRoot + [System.IO.Path]::DirectorySeparatorChar

    foreach ($relativePath in @($normalization.Paths)) {
        try {
            $fullPath = [System.IO.Path]::GetFullPath((Join-Path -Path $repositoryRoot -ChildPath ($relativePath -replace "/", "\")))
            if (-not $fullPath.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "path_resolves_outside_worktree"
            }

            if (-not (Test-Path -LiteralPath $fullPath)) {
                $entries.Add([pscustomobject]@{
                    path = $relativePath
                    state = "absent"
                    sha256 = $null
                    length = $null
                })
                continue
            }

            $item = Get-Item -LiteralPath $fullPath -Force
            if ($item.PSIsContainer) {
                throw "allowed_path_is_directory"
            }
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "allowed_path_is_reparse_point"
            }

            $entries.Add([pscustomobject]@{
                path = $relativePath
                state = "regular_file"
                sha256 = Get-Sha256File -Path $fullPath
                length = [int64]$item.Length
            })
        }
        catch {
            $reasons += "bounded_manifest_unavailable:$relativePath"
        }
    }

    $sortedEntries = @($entries | Sort-Object -Property path)
    $payload = @($sortedEntries | ForEach-Object {
        "$($_.path)|$($_.state)|$($_.sha256)|$($_.length)"
    }) -join "`n"
    $uniqueReasons = @($reasons | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $status = if ($uniqueReasons.Count -eq 0) { "verified" } else { "unverified" }

    return [pscustomobject]@{
        status = $status
        evidence_profile = $CandidateEvidenceProfile
        entries = @($sortedEntries)
        payload = $payload
        fingerprint = if ($status -eq "verified") { Get-Sha256Text -Text $payload } else { $null }
        reasons = $uniqueReasons
    }
}

function Get-ChangedAllowedFilesFromManifests {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Before,
        [Parameter(Mandatory = $true)]
        [object]$After
    )

    if ($Before.status -ne "verified" -or $After.status -ne "verified") {
        return @()
    }

    $beforeByPath = @{}
    $afterByPath = @{}
    foreach ($entry in @($Before.entries)) {
        $beforeByPath[[string]$entry.path] = "$($entry.state)|$($entry.sha256)|$($entry.length)"
    }
    foreach ($entry in @($After.entries)) {
        $afterByPath[[string]$entry.path] = "$($entry.state)|$($entry.sha256)|$($entry.length)"
    }

    $changed = [System.Collections.Generic.List[string]]::new()
    $allPaths = @($beforeByPath.Keys) + @($afterByPath.Keys)
    foreach ($path in @($allPaths | Sort-Object -Unique)) {
        if (-not $beforeByPath.ContainsKey($path) -or
            -not $afterByPath.ContainsKey($path) -or
            $beforeByPath[$path] -ne $afterByPath[$path]) {
            $changed.Add($path)
        }
    }
    return @($changed)
}

function New-RuntimeContractNotPresent {
    return [pscustomobject]@{
        status = "not_present"
        contract_present = $false
        pre_execution = [pscustomobject]@{ status = "not_present"; reasons = @() }
        post_execution = [pscustomobject]@{ status = "not_run"; reasons = @() }
        allowed_files = @()
        actual_changed_files = @()
        reasons = @()
    }
}

function Get-RuntimeContractEvaluatorIdentity {
    param(
        [string]$RepositoryPath = $ControlRepoRoot
    )

    $relativePaths = @(
        "src/local_runner_bridge/__init__.py",
        "src/local_runner_bridge/runtime_contract_binding.py",
        "src/local_runner_bridge/task_packet_validator.py",
        "src/local_runner_bridge/task_surface_resolver.py"
    )
    $files = [ordered]@{}
    foreach ($relativePath in $relativePaths) {
        $fullPath = Join-Path -Path $RepositoryPath -ChildPath ($relativePath -replace "/", "\")
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            throw "Runtime contract evaluator dependency was not found: $fullPath"
        }
        $files[$relativePath] = Get-Sha256File -Path $fullPath
    }
    $fingerprintPayload = @($files.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
    return [pscustomobject]@{
        EvaluatorPath = Join-Path -Path $RepositoryPath -ChildPath "src\local_runner_bridge\runtime_contract_binding.py"
        Files = $files
        Fingerprint = Get-Sha256Text -Text $fingerprintPayload
    }
}

function New-TrustedRuntimeContractEvaluatorSnapshot {
    $relativePaths = @(
        "src/local_runner_bridge/__init__.py",
        "src/local_runner_bridge/runtime_contract_binding.py",
        "src/local_runner_bridge/task_packet_validator.py",
        "src/local_runner_bridge/task_surface_resolver.py"
    )
    $snapshotRoot = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("lawb-runtime-contract-" + [guid]::NewGuid().ToString("N"))
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    try {
        New-Item -ItemType Directory -Path $snapshotRoot -Force | Out-Null
        $packageRoot = Join-Path -Path $snapshotRoot -ChildPath "local_runner_bridge"
        New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
        $files = [ordered]@{}
        foreach ($relativePath in $relativePaths) {
            $committed = Invoke-Git -GitArgs @("show", "HEAD:$relativePath")
            Require-Success -Result $committed -Action "trusted runtime contract evaluator baseline read for $relativePath"
            $destination = Join-Path -Path $snapshotRoot -ChildPath ($relativePath -replace "^src/", "")
            [System.IO.File]::WriteAllText($destination, ([string]$committed.Stdout) + "`n", $utf8NoBom)
            $files[$relativePath] = Get-Sha256File -Path $destination
        }
        $entryPath = Join-Path -Path $snapshotRoot -ChildPath "trusted_runtime_contract_entry.py"
        $entrySource = @'
import runpy
import sys
from pathlib import Path

trusted_root = str(Path(__file__).resolve().parent)
sys.path.insert(0, trusted_root)
runpy.run_module("local_runner_bridge.runtime_contract_binding", run_name="__main__")
'@
        [System.IO.File]::WriteAllText($entryPath, $entrySource, $utf8NoBom)
        $fingerprintPayload = @($files.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
        return [pscustomobject]@{
            Root = $snapshotRoot
            EvaluatorPath = $entryPath
            Files = $files
            Fingerprint = Get-Sha256Text -Text $fingerprintPayload
            Source = "committed_head"
        }
    }
    catch {
        Remove-Item -LiteralPath $snapshotRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

function Get-ReviewBundleGitObservation {
    $head = Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
    $status = Get-GitStatusShort
    return [pscustomobject]@{
        Head = $head
        Status = $status
        NoStage = -not (Test-GitStatusHasStagedChanges -Status $status)
        UntrackedFiles = @(Get-GitUntrackedFilesWithoutExcludes)
        IndexVisibilityFiles = @(Get-GitIndexVisibilityFiles)
        GitVisibilityMetadataFingerprint = Get-GitVisibilityMetadataFingerprint
    }
}

function Get-ReviewBundleInvariantViolationReasons {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HeadBefore,
        [Parameter(Mandatory = $true)]
        [string]$HeadAfter,
        [Parameter(Mandatory = $true)]
        [bool]$NoStage,
        [AllowEmptyCollection()]
        [string[]]$IndexVisibilityFilesBefore = @(),
        [AllowEmptyCollection()]
        [string[]]$IndexVisibilityFilesAfter = @(),
        [AllowEmptyString()]
        [string]$GitVisibilityMetadataFingerprintBefore = "",
        [AllowEmptyString()]
        [string]$GitVisibilityMetadataFingerprintAfter = ""
    )

    $reasons = @()
    if ($HeadBefore -notmatch '^[0-9a-fA-F]{40}$' -or $HeadAfter -notmatch '^[0-9a-fA-F]{40}$') {
        $reasons += "head_measurement_invalid"
    }
    elseif (-not [string]::Equals($HeadBefore, $HeadAfter, [System.StringComparison]::OrdinalIgnoreCase)) {
        $reasons += "unexpected_head_movement"
    }
    if (-not $NoStage) {
        $reasons += "staged_changes_detected"
    }
    if (@($IndexVisibilityFilesBefore).Count -gt 0 -or @($IndexVisibilityFilesAfter).Count -gt 0) {
        $reasons += "git_index_visibility_flags_detected"
    }
    if (-not [string]::IsNullOrWhiteSpace($GitVisibilityMetadataFingerprintBefore) -and
        -not [string]::IsNullOrWhiteSpace($GitVisibilityMetadataFingerprintAfter) -and
        -not [string]::Equals(
            $GitVisibilityMetadataFingerprintBefore,
            $GitVisibilityMetadataFingerprintAfter,
            [System.StringComparison]::Ordinal
        )) {
        $reasons += "git_visibility_metadata_changed"
    }
    return @($reasons)
}

function New-RuntimeContractViolationBinding {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RuntimeContractBinding,
        [Parameter(Mandatory = $true)]
        [string[]]$Reasons,
        [AllowEmptyCollection()]
        [string[]]$ActualChangedFiles = @()
    )

    $newReasons = @($Reasons | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $allReasons = @(@($RuntimeContractBinding.reasons) + $newReasons | Select-Object -Unique)
    $result = [ordered]@{
        status = "contract_violation"
        contract_present = [bool]$RuntimeContractBinding.contract_present
        pre_execution = $RuntimeContractBinding.pre_execution
        post_execution = [pscustomobject]@{ status = "contract_violation"; reasons = $newReasons }
        allowed_files = @($RuntimeContractBinding.allowed_files)
        actual_changed_files = @($ActualChangedFiles | Sort-Object -Unique)
        reasons = $allReasons
    }
    $runtimeContractProperty = $RuntimeContractBinding.PSObject.Properties["runtime_contract"]
    if ($null -ne $runtimeContractProperty) {
        $result["runtime_contract"] = $runtimeContractProperty.Value
    }
    return [pscustomobject]$result
}

function ConvertTo-NormalizedRuntimeContractPath {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Path
    )

    $normalized = $Path.Trim().Replace("\", "/")
    while ($normalized.StartsWith("./", [System.StringComparison]::Ordinal)) {
        $normalized = $normalized.Substring(2)
    }
    if ([string]::IsNullOrWhiteSpace($normalized) -or
        $normalized -eq "." -or
        $normalized -match '^[A-Za-z]:' -or
        $normalized.Contains(":") -or
        $normalized.IndexOfAny([char[]]@([char]'*', [char]'?', [char]'[', [char]']')) -ge 0 -or
        $normalized.EndsWith("/", [System.StringComparison]::Ordinal) -or
        $normalized.StartsWith("/", [System.StringComparison]::Ordinal)) {
        throw "invalid_repository_relative_path"
    }

    $parts = [System.Collections.Generic.List[string]]::new()
    foreach ($part in $normalized.Split("/")) {
        if ($part -eq "..") {
            throw "invalid_repository_relative_path"
        }
        if ($part -eq "" -or $part -eq ".") {
            continue
        }
        $parts.Add($part)
    }
    if ($parts.Count -eq 0) {
        throw "invalid_repository_relative_path"
    }
    if ([string]::Equals($parts[0], ".git", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "invalid_repository_relative_path"
    }
    return [string]::Join("/", $parts)
}

function ConvertTo-NormalizedRuntimeContractPathSet {
    param(
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$Paths,
        [Parameter(Mandatory = $true)]
        [string]$InvalidReason
    )

    $normalized = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $reasons = @()
    foreach ($path in @($Paths)) {
        try {
            if ($path -isnot [string]) {
                throw "invalid_repository_relative_path"
            }
            $null = $normalized.Add((ConvertTo-NormalizedRuntimeContractPath -Path ([string]$path)))
        }
        catch {
            $reasons += $InvalidReason
        }
    }

    [string[]]$sortedPaths = @($normalized)
    [System.Array]::Sort($sortedPaths, [System.StringComparer]::Ordinal)
    return [pscustomobject]@{
        Paths = @($sortedPaths)
        Reasons = @($reasons | Select-Object -Unique)
    }
}

function Test-PositiveRuntimeContractInteger {
    param(
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value -or $Value -is [bool]) {
        return $false
    }
    $integerTypes = @(
        "System.Byte",
        "System.SByte",
        "System.Int16",
        "System.UInt16",
        "System.Int32",
        "System.UInt32",
        "System.Int64",
        "System.UInt64"
    )
    return (($integerTypes -contains $Value.GetType().FullName) -and ([decimal]$Value -gt 0))
}

function Invoke-ParentControlledRuntimeContractEnforcement {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RuntimeContractBinding,
        [AllowEmptyCollection()]
        [string[]]$ActualChangedFiles = @(),
        [AllowEmptyCollection()]
        [string[]]$InvariantViolationReasons = @()
    )

    $actualNormalization = ConvertTo-NormalizedRuntimeContractPathSet `
        -Paths @($ActualChangedFiles) `
        -InvalidReason "invalid_actual_changed_file"
    $actualFiles = @($actualNormalization.Paths)
    $reasons = @(@($InvariantViolationReasons) + @($actualNormalization.Reasons))
    $bindingStatus = [string]$RuntimeContractBinding.status

    if ([string]::Equals($bindingStatus, "not_present", [System.StringComparison]::Ordinal)) {
        $reasons = @($reasons | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
        if ($reasons.Count -gt 0) {
            return New-RuntimeContractViolationBinding `
                -RuntimeContractBinding $RuntimeContractBinding `
                -Reasons $reasons `
                -ActualChangedFiles $actualFiles
        }
        return [pscustomobject]@{
            status = "not_present"
            contract_present = $false
            pre_execution = $RuntimeContractBinding.pre_execution
            post_execution = [pscustomobject]@{ status = "not_present"; reasons = @() }
            allowed_files = @()
            actual_changed_files = $actualFiles
            reasons = @()
        }
    }

    if (-not [string]::Equals($bindingStatus, "passed", [System.StringComparison]::Ordinal) -or
        -not [string]::Equals([string]$RuntimeContractBinding.pre_execution.status, "passed", [System.StringComparison]::Ordinal) -or
        -not [bool]$RuntimeContractBinding.contract_present) {
        $reasons += "runtime_contract_pre_execution_not_passed"
    }

    $allowedNormalization = ConvertTo-NormalizedRuntimeContractPathSet `
        -Paths @($RuntimeContractBinding.allowed_files) `
        -InvalidReason "invalid_allowed_file"
    $allowedFiles = @($allowedNormalization.Paths)
    $reasons += @($allowedNormalization.Reasons)
    $allowedSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($allowedFile in $allowedFiles) {
        $null = $allowedSet.Add($allowedFile)
    }
    if (@($actualFiles | Where-Object { -not $allowedSet.Contains($_) }).Count -gt 0) {
        $reasons += "changed_file_outside_allowed_files"
    }

    $runtimeContractProperty = $RuntimeContractBinding.PSObject.Properties["runtime_contract"]
    $maximum = $null
    if ($null -eq $runtimeContractProperty) {
        $reasons += "runtime_contract_binding_invalid"
    }
    else {
        $maximumProperty = $runtimeContractProperty.Value.PSObject.Properties["max_allowed_files"]
        if ($null -ne $maximumProperty) {
            $maximum = $maximumProperty.Value
        }
    }
    if (-not (Test-PositiveRuntimeContractInteger -Value $maximum)) {
        $reasons += "invalid_max_allowed_files"
    }
    elseif ($actualFiles.Count -gt [uint64]$maximum) {
        $reasons += "changed_file_count_exceeds_max_allowed_files"
    }

    $reasons = @($reasons | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    if ($reasons.Count -gt 0) {
        return New-RuntimeContractViolationBinding `
            -RuntimeContractBinding $RuntimeContractBinding `
            -Reasons $reasons `
            -ActualChangedFiles $actualFiles
    }

    return [pscustomobject]@{
        status = "passed"
        contract_present = $true
        pre_execution = $RuntimeContractBinding.pre_execution
        post_execution = [pscustomobject]@{ status = "passed"; reasons = @() }
        allowed_files = $allowedFiles
        actual_changed_files = $actualFiles
        reasons = @()
        runtime_contract = $runtimeContractProperty.Value
    }
}

function New-ExecutionAssurance {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RuntimeContractBinding,
        [Parameter(Mandatory = $true)]
        [ValidateSet("verified", "violation", "unverified")]
        [string]$ObservableEvidence,
        [AllowNull()]
        [object]$CandidateManifest = $null
    )

    $governanceScope = switch ([string]$RuntimeContractBinding.status) {
        "passed" { "passed" }
        "contract_violation" { "violation" }
        default { "not_present" }
    }
    $manifestEvidenceVerified = $null -ne $CandidateManifest -and
        [string]::Equals([string]$CandidateManifest.status, "verified", [System.StringComparison]::Ordinal) -and
        [string]::Equals([string]$CandidateManifest.evidence_profile, $CandidateEvidenceProfile, [System.StringComparison]::Ordinal) -and
        -not [string]::IsNullOrWhiteSpace([string]$CandidateManifest.fingerprint)
    $effectiveObservableEvidence = if ($ObservableEvidence -eq "verified" -and -not $manifestEvidenceVerified) {
        "unverified"
    }
    else {
        $ObservableEvidence
    }
    if ($effectiveObservableEvidence -eq "verified" -and [string]::IsNullOrWhiteSpace($CandidateEvidenceProfile)) {
        throw "Verified observable evidence requires a named evidence profile."
    }

    return [pscustomobject][ordered]@{
        governance_scope = $governanceScope
        observable_evidence = $effectiveObservableEvidence
        evidence_profile = if ($effectiveObservableEvidence -eq "verified") { $CandidateEvidenceProfile } else { $null }
        candidate_manifest_fingerprint = if ($effectiveObservableEvidence -eq "verified") { [string]$CandidateManifest.fingerprint } else { $null }
        isolation_guarantee = "unverified"
        isolation_provider = $LocalIsolationProvider
        isolation_evidence_source = $null
    }
}

function Get-AllowedFileScopeViolationReasons {
    param(
        [AllowEmptyCollection()]
        [string[]]$AllowedFiles = @()
    )

    $normalization = ConvertTo-NormalizedRuntimeContractPathSet `
        -Paths @($AllowedFiles) `
        -InvalidReason "invalid_allowed_file"
    $reasons = @($normalization.Reasons)
    $repositoryRoot = [System.IO.Path]::GetFullPath($RepoPath).TrimEnd("\", "/")
    $repositoryPrefix = $repositoryRoot + [System.IO.Path]::DirectorySeparatorChar

    foreach ($relativePath in @($normalization.Paths)) {
        try {
            $fullPath = [System.IO.Path]::GetFullPath((Join-Path -Path $repositoryRoot -ChildPath ($relativePath -replace "/", "\")))
            if (-not $fullPath.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                $reasons += "allowed_file_outside_worktree"
                continue
            }
            if (Test-Path -LiteralPath $fullPath) {
                $item = Get-Item -LiteralPath $fullPath -Force
                if ($item.PSIsContainer) {
                    $reasons += "allowed_file_is_directory"
                }
                elseif (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    $reasons += "allowed_file_not_regular_worktree_path"
                }
            }
        }
        catch {
            $reasons += "allowed_file_scope_unavailable"
        }
    }
    return @($reasons | Select-Object -Unique)
}

function Test-ApprovalContextAllowed {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RuntimeContractBinding,
        [Parameter(Mandatory = $true)]
        [Alias("NoStage")]
        [bool]$FinalIndexClean,
        [Parameter(Mandatory = $true)]
        [Alias("NoCommit")]
        [bool]$FinalHeadMatchesInitial,
        [AllowNull()]
        [object]$ExecutionAssurance,
        [bool]$CandidatePathsReviewable = $true
    )

    if ($null -eq $ExecutionAssurance) {
        $defaultEvidence = if ($RuntimeContractBinding.status -eq "contract_violation") { "violation" } else { "unverified" }
        $ExecutionAssurance = New-ExecutionAssurance `
            -RuntimeContractBinding $RuntimeContractBinding `
            -ObservableEvidence $defaultEvidence
    }

    return $FinalIndexClean -and
        $FinalHeadMatchesInitial -and
        $CandidatePathsReviewable -and
        [bool]$RuntimeContractBinding.contract_present -and
        [string]::Equals([string]$RuntimeContractBinding.status, "passed", [System.StringComparison]::Ordinal) -and
        [string]::Equals([string]$ExecutionAssurance.governance_scope, "passed", [System.StringComparison]::Ordinal) -and
        [string]::Equals([string]$ExecutionAssurance.observable_evidence, "verified", [System.StringComparison]::Ordinal) -and
        -not [string]::IsNullOrWhiteSpace([string]$ExecutionAssurance.evidence_profile) -and
        -not [string]::IsNullOrWhiteSpace([string]$ExecutionAssurance.candidate_manifest_fingerprint)
}

function Resolve-PythonRuntimeCommand {
    $commands = @(Get-Command python -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($command in $commands) {
        $path = Get-CommandCandidatePath -Command $command
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }
        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        if ($extension -in @(".exe", ".com") -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            return [System.IO.Path]::GetFullPath($path)
        }
    }
    throw "Python runtime was not found as a direct executable on PATH."
}

function Invoke-RuntimeContractEvaluator {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("inspect")]
        [string]$Action,
        [Parameter(Mandatory = $true)]
        [object]$Payload,
        [string]$PythonPath = "",
        [switch]$TrustedCommittedBaseline
    )

    $python = if ([string]::IsNullOrWhiteSpace($PythonPath)) { Resolve-PythonRuntimeCommand } else { [System.IO.Path]::GetFullPath($PythonPath) }
    $pythonExtension = [System.IO.Path]::GetExtension($python).ToLowerInvariant()
    if ($pythonExtension -notin @(".exe", ".com") -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Runtime contract Python path is not an available direct executable: $python"
    }
    $trustedSnapshot = $null
    try {
        if ($TrustedCommittedBaseline) {
            $trustedSnapshot = New-TrustedRuntimeContractEvaluatorSnapshot
            $bindingScript = [string]$trustedSnapshot.EvaluatorPath
            $workingDirectory = [string]$trustedSnapshot.Root
        }
        else {
            $bindingScript = Join-Path -Path $ControlRepoRoot -ChildPath "src\local_runner_bridge\runtime_contract_binding.py"
            $workingDirectory = $ControlRepoRoot
        }
        if (-not (Test-Path -LiteralPath $bindingScript -PathType Leaf)) {
            throw "Runtime contract binding module was not found: $bindingScript"
        }
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $payloadJson = $Payload | ConvertTo-Json -Depth 20 -Compress
        $pythonArguments = if ($TrustedCommittedBaseline) {
            @("-I", "-S", $bindingScript, $Action)
        }
        else {
            @($bindingScript, $Action)
        }
        $evaluation = Invoke-CapturedNativeProcess `
            -FilePath $python `
            -Arguments $pythonArguments `
            -WorkingDirectory $workingDirectory `
            -StandardInput $payloadJson `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 30 `
            -Action "runtime contract $Action evaluation"
        if ($evaluation.ExitCode -ne 0) {
            throw "Runtime contract $Action evaluation failed closed: $($evaluation.Stderr)"
        }
        try {
            $binding = $evaluation.Stdout | ConvertFrom-Json
        }
        catch {
            throw "Runtime contract $Action evaluation returned malformed JSON."
        }
        if ($null -eq $binding -or $binding -is [array] -or $binding.status -notin @("passed", "contract_violation", "not_present")) {
            throw "Runtime contract $Action evaluation returned an invalid binding status."
        }
        return $binding
    }
    finally {
        if ($null -ne $trustedSnapshot) {
            Remove-Item -LiteralPath ([string]$trustedSnapshot.Root) -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Assert-RuntimeContractAllowsCodex {
    param(
        [Parameter(Mandatory = $true)]
        [object]$RuntimeContractBinding
    )

    if ([string]::Equals([string]$RuntimeContractBinding.status, "contract_violation", [System.StringComparison]::Ordinal)) {
        $reasons = @($RuntimeContractBinding.reasons) -join ","
        throw "Runtime contract violation blocks Codex execution: $reasons"
    }
}

function Get-OverallRunnerResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CodexExitCode,
        [Parameter(Mandatory = $true)]
        [object]$RuntimeContractBinding,
        [AllowNull()]
        [object]$ExecutionAssurance = $null
    )

    if ([string]::Equals([string]$RuntimeContractBinding.status, "contract_violation", [System.StringComparison]::Ordinal)) {
        return "failure"
    }
    if ($null -ne $ExecutionAssurance -and
        -not [string]::Equals([string]$ExecutionAssurance.observable_evidence, "verified", [System.StringComparison]::Ordinal)) {
        return "failure"
    }
    if ($CodexExitCode -eq "0") {
        return "success"
    }
    return "failure"
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

function Resolve-ComSpecPath {
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:COMSPEC)) {
        $candidates += $env:COMSPEC
    }
    $cmdCommand = Get-Command cmd.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $cmdCommand) {
        $cmdPath = Get-CommandCandidatePath -Command $cmdCommand
        if (-not [string]::IsNullOrWhiteSpace($cmdPath)) {
            $candidates += $cmdPath
        }
    }

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    throw "cmd.exe was not found through COMSPEC or the Application command resolver."
}

function Resolve-CodexCommand {
    param(
        [object[]]$Commands = $null,
        [string]$ReviewedCodexPath = ""
    )

    if (-not [string]::IsNullOrWhiteSpace($ReviewedCodexPath)) {
        $source = Resolve-ReviewedCodexPath -ReviewedCodexPath $ReviewedCodexPath
        return New-CodexLaunchSpec -Source $source -SelectionSource "reviewed_exact_path" -ReviewedCodexPath $source
    }

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

    $selected = @($candidates | Where-Object {
        $_.CommandType -eq "Application" -and $_.Extension -eq ".cmd"
    } | Select-Object -First 1)
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object {
            $_.CommandType -eq "Application" -and $_.Extension -eq ".bat"
        } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object {
            $_.CommandType -eq "Application" -and $_.Extension -eq ".exe"
        } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        $selected = @($candidates | Where-Object {
            $_.CommandType -eq "Application" -and $_.Extension -eq ".com"
        } | Select-Object -First 1)
    }
    if ($selected.Count -eq 0) {
        throw "codex command was found, but only PowerShell script wrappers or other unsafe launchers were available. Refusing to directly launch codex.ps1 or another shell wrapper; ensure codex.exe, codex.cmd, or codex.bat is available on PATH."
    }

    return New-CodexLaunchSpec -Source ([string]$selected[0].Source) -SelectionSource "path" -Command $selected[0].Command
}

function Test-AbsoluteCodexLauncherPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return ($Path -match '^[A-Za-z]:[\\/]' -or $Path -match '^\\\\[^\\]+\\[^\\]+\\')
}

function Resolve-ReviewedCodexPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReviewedCodexPath
    )

    if ([string]::IsNullOrWhiteSpace($ReviewedCodexPath)) {
        throw "ReviewedCodexPath is required before launching codex."
    }
    if (-not (Test-AbsoluteCodexLauncherPath -Path $ReviewedCodexPath)) {
        throw "ReviewedCodexPath must be an absolute Windows path."
    }
    $fullPath = [System.IO.Path]::GetFullPath($ReviewedCodexPath)
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "ReviewedCodexPath does not exist: $fullPath"
    }
    $extension = [System.IO.Path]::GetExtension($fullPath).ToLowerInvariant()
    if ($extension -notin @(".exe", ".cmd", ".bat", ".com")) {
        throw "ReviewedCodexPath has an unsafe launcher suffix '$extension'."
    }
    return $fullPath
}

function New-CodexLaunchSpec {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$SelectionSource,
        [AllowNull()]
        [object]$Command = $null,
        [string]$ReviewedCodexPath = ""
    )

    $extension = [System.IO.Path]::GetExtension($Source).ToLowerInvariant()
    if ($extension -notin @(".exe", ".cmd", ".bat", ".com")) {
        throw "codex command was found, but only PowerShell script wrappers or other unsafe launchers were available. Refusing to directly launch codex.ps1 or another shell wrapper; ensure codex.exe, codex.cmd, or codex.bat is available on PATH."
    }
    if ($extension -in @(".cmd", ".bat")) {
        $filePath = Resolve-ComSpecPath
        $argumentPrefix = @("/d", "/s", "/c", "call", $source)
        $reason = "resolved safe batch launcher through cmd.exe"
        $launcherType = "cmd"
    }
    else {
        $filePath = $source
        $argumentPrefix = @()
        $reason = "resolved direct executable launcher"
        $launcherType = "direct"
    }
    $pathBindingMatch = [string]::IsNullOrWhiteSpace($ReviewedCodexPath) -or
        [string]::Equals(
            [System.IO.Path]::GetFullPath($Source),
            [System.IO.Path]::GetFullPath($ReviewedCodexPath),
            [System.StringComparison]::OrdinalIgnoreCase
        )

    return [pscustomobject]@{
        Source = $source
        FilePath = $filePath
        ArgumentPrefix = @($argumentPrefix)
        Command = $Command
        Reason = $reason
        SelectionSource = $SelectionSource
        ReviewedCodexPath = if ([string]::IsNullOrWhiteSpace($ReviewedCodexPath)) { "" } else { [System.IO.Path]::GetFullPath($ReviewedCodexPath) }
        LauncherType = $launcherType
        PathBindingMatch = $pathBindingMatch
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
    $candidateOrder = 0

    if (-not [string]::IsNullOrWhiteSpace($DefaultPath) -and (Test-Path -LiteralPath $DefaultPath)) {
        $candidatePaths += [pscustomobject]@{ Path = $DefaultPath; Order = $candidateOrder }
        $candidateOrder += 1
    }

    if ($null -eq $Commands) {
        $Commands = @(Get-Command gh -All -ErrorAction SilentlyContinue)
    }

    foreach ($command in @($Commands)) {
        $commandTypeProperty = $command.PSObject.Properties["CommandType"]
        $commandType = if ($null -eq $commandTypeProperty) { "" } else { [string]$commandTypeProperty.Value }
        if (-not [string]::Equals($commandType, "Application", [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }

        $path = Get-GitHubCliCandidatePath -Command $command
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $candidatePaths += [pscustomobject]@{ Path = $path; Order = $candidateOrder }
        $candidateOrder += 1
    }

    if ([string]::IsNullOrWhiteSpace($PortablePath)) {
        $PortablePath = Join-Path $env:USERPROFILE "tools\gh-portable\bin\gh.exe"
    }

    $candidatePaths += [pscustomobject]@{ Path = $PortablePath; Order = $candidateOrder }
    $candidateOrder += 1

    if ($null -ne $ExtraCandidatePaths) {
        foreach ($extraPath in $ExtraCandidatePaths) {
            $candidatePaths += [pscustomobject]@{ Path = $extraPath; Order = $candidateOrder }
            $candidateOrder += 1
        }
    }

    $normalized = @()
    foreach ($candidate in $candidatePaths) {
        $path = [string]$candidate.Path
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        $rank = [array]::IndexOf(@(".exe", ".cmd", ".bat", ".com"), $extension)
        if ($rank -lt 0) {
            continue
        }

        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            continue
        }

        $normalized += [pscustomobject]@{
            Source = [System.IO.Path]::GetFullPath($path)
            Extension = $extension
            Rank = $rank
            Order = [int]$candidate.Order
        }
    }

    if (@($normalized).Count -eq 0) {
        throw "GitHub CLI was not found. Checked fixed Program Files path, PATH candidates, and portable user tools path."
    }

    $selected = @($normalized | Sort-Object Rank, Order | Select-Object -First 1)

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
        [System.Text.Encoding]$StandardInputEncoding,
        [Parameter(Mandatory = $true)]
        [System.Text.Encoding]$StandardOutputEncoding,
        [Parameter(Mandatory = $true)]
        [System.Text.Encoding]$StandardErrorEncoding,
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
    $stdout = ""
    $stderr = ""

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
        $startInfo.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1"
        $startInfo.StandardOutputEncoding = $StandardOutputEncoding
        $startInfo.StandardErrorEncoding = $StandardErrorEncoding

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo

        $hasStandardInput = -not [string]::IsNullOrEmpty($StandardInput)
        $null = $process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if ($hasStandardInput) {
            $inputBytes = $StandardInputEncoding.GetBytes($StandardInput)
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
        $stdout = if ($null -eq $stdoutTask) { "" } else { $stdoutTask.GetAwaiter().GetResult() }
        $stderr = if ($null -eq $stderrTask) { "" } else { $stderrTask.GetAwaiter().GetResult() }
    }
    catch {
        $stderr = "$Action failed: $($_.Exception.Message)"
        $failureExitCode = if ($timedOut) { 124 } else { 1 }
        return [pscustomobject]@{
            ExitCode = $failureExitCode
            Stdout = $stdout.TrimEnd()
            Stderr = $stderr.TrimEnd()
            TimedOut = $timedOut
            TimeoutSeconds = $TimeoutSeconds
            FilePath = $FilePath
            Arguments = @($Arguments)
            CommandLine = $commandLine
            LastStdoutLine = Get-LastNonEmptyLine -Text $stdout
            LastStderrLine = Get-LastNonEmptyLine -Text $stderr
            ProcessId = if ($null -eq $process) { $null } else { $process.Id }
            StopAttempted = $stopAttempted
            StoppedProcessIds = @($stoppedProcessIds)
        }
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = if ($null -eq $stdout) { "" } else { $stdout.TrimEnd() }
        Stderr = if ($null -eq $stderr) { "" } else { $stderr.TrimEnd() }
        TimedOut = $timedOut
        TimeoutSeconds = $TimeoutSeconds
        FilePath = $FilePath
        Arguments = @($Arguments)
        CommandLine = $commandLine
        LastStdoutLine = Get-LastNonEmptyLine -Text $stdout
        LastStderrLine = Get-LastNonEmptyLine -Text $stderr
        ProcessId = if ($null -eq $process) { $null } else { $process.Id }
        StopAttempted = $stopAttempted
        StoppedProcessIds = @($stoppedProcessIds)
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

function New-ToolResolutionNativeProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $probe = Invoke-CapturedNativeProcess `
        -FilePath $FilePath `
        -Arguments $Arguments `
        -WorkingDirectory $RepoPath `
        -StandardInput "" `
        -StandardInputEncoding $utf8 `
        -StandardOutputEncoding $utf8 `
        -StandardErrorEncoding $utf8 `
        -TimeoutSeconds 15 `
        -Action $Action

    return [ordered]@{
        executed = $true
        exit_code = $probe.ExitCode
        ok = ($probe.ExitCode -eq 0)
        safe_message = if ($probe.ExitCode -eq 0) { "ok" } elseif ($probe.TimedOut) { "version_probe_timeout" } else { "version_probe_failed" }
    }
}

function Test-StringArrayEqual {
    param(
        [AllowEmptyCollection()]
        [string[]]$Left,
        [AllowEmptyCollection()]
        [string[]]$Right
    )

    $leftValues = @($Left)
    $rightValues = @($Right)
    if ($leftValues.Count -ne $rightValues.Count) {
        return $false
    }
    for ($index = 0; $index -lt $leftValues.Count; $index += 1) {
        if (-not [string]::Equals([string]$leftValues[$index], [string]$rightValues[$index], [System.StringComparison]::Ordinal)) {
            return $false
        }
    }
    return $true
}

function Invoke-ReviewedCodexVersionProbe {
    param(
        [Parameter(Mandatory = $true)]
        [object]$CodexCommand,
        [ValidateRange(1, [int]::MaxValue)]
        [int]$TimeoutSeconds = 30
    )

    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $probeArguments = @($CodexCommand.ArgumentPrefix) + @("--version")
    $probe = $null
    $failureReason = "none"
    try {
        $probe = Invoke-CapturedNativeProcess `
            -FilePath ([string]$CodexCommand.FilePath) `
            -Arguments $probeArguments `
            -WorkingDirectory $RepoPath `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds $TimeoutSeconds `
            -Action "codex --version reviewed exact launcher"
    }
    catch {
        $failureReason = "process_start_exception"
    }

    $probeFilePath = ""
    $probeArgumentsValue = @()
    $exitCode = $null
    $timedOut = $false
    if ($null -ne $probe) {
        $filePathProperty = $probe.PSObject.Properties["FilePath"]
        $argumentsProperty = $probe.PSObject.Properties["Arguments"]
        $exitCodeProperty = $probe.PSObject.Properties["ExitCode"]
        $timedOutProperty = $probe.PSObject.Properties["TimedOut"]
        $probeFilePath = if ($null -eq $filePathProperty) { "" } else { [string]$filePathProperty.Value }
        $probeArgumentsValue = if ($null -eq $argumentsProperty) { @() } else { @($argumentsProperty.Value) }
        $exitCode = if ($null -eq $exitCodeProperty) { $null } else { [int]$exitCodeProperty.Value }
        $timedOut = if ($null -eq $timedOutProperty) { $false } else { [bool]$timedOutProperty.Value }
    }

    $filePathMatches = $false
    if (-not [string]::IsNullOrWhiteSpace($probeFilePath)) {
        $filePathMatches = [string]::Equals(
            [System.IO.Path]::GetFullPath($probeFilePath),
            [System.IO.Path]::GetFullPath([string]$CodexCommand.FilePath),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
    $reviewedCodexPathValue = [string]$CodexCommand.ReviewedCodexPath
    $launcherSourceMatchesReviewedPath = -not [string]::IsNullOrWhiteSpace($reviewedCodexPathValue) -and [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$CodexCommand.Source),
        [System.IO.Path]::GetFullPath($reviewedCodexPathValue),
        [System.StringComparison]::OrdinalIgnoreCase
    )
    $argumentsMatch = Test-StringArrayEqual -Left ([string[]]$probeArgumentsValue) -Right ([string[]]$probeArguments)
    $pathBindingMatch = [bool]$CodexCommand.PathBindingMatch
    $passed = $false
    if ([string]::Equals($failureReason, "none", [System.StringComparison]::Ordinal)) {
        if ($null -eq $probe) {
            $failureReason = "probe_result_missing"
        }
        elseif ($timedOut) {
            $failureReason = "probe_timeout"
        }
        elseif ($null -eq $exitCode -or $exitCode -ne 0) {
            $failureReason = "probe_nonzero_exit"
        }
        elseif (-not $filePathMatches) {
            $failureReason = "probe_file_path_mismatch"
        }
        elseif (-not $launcherSourceMatchesReviewedPath) {
            $failureReason = "probe_launcher_source_mismatch"
        }
        elseif (-not $argumentsMatch) {
            $failureReason = "probe_argument_prefix_mismatch"
        }
        elseif (-not $pathBindingMatch) {
            $failureReason = "probe_path_binding_mismatch"
        }
        else {
            $passed = $true
        }
    }

    return [pscustomobject]@{
        Attempted = $true
        Passed = $passed
        FailureReason = $failureReason
        ExitCode = $exitCode
        TimedOut = $timedOut
        ProcessFilePath = $probeFilePath
        LauncherSource = [string]$CodexCommand.Source
        ReviewedCodexPath = $reviewedCodexPathValue
        LauncherType = [string]$CodexCommand.LauncherType
        ArgumentPrefix = @($CodexCommand.ArgumentPrefix)
        Arguments = @($probeArguments)
        PathBindingMatch = $pathBindingMatch
        ProcessResult = $probe
    }
}

function Resolve-GitHubCliProbeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GhPath
    )

    $suffix = [System.IO.Path]::GetExtension($GhPath).ToLowerInvariant()
    if ($suffix -in @(".cmd", ".bat")) {
        return [pscustomobject]@{
            FilePath = Resolve-ComSpecPath
            Arguments = @("/d", "/s", "/c", "call", $GhPath, "--version")
        }
    }

    return [pscustomobject]@{
        FilePath = $GhPath
        Arguments = @("--version")
    }
}

function New-ToolEntry {
    param(
        [AllowNull()]
        [string]$SelectedPath,
        [AllowNull()]
        [string]$SelectionSource,
        [AllowNull()]
        [object]$VersionProbe
    )

    return [ordered]@{
        selected_path = if ([string]::IsNullOrWhiteSpace($SelectedPath)) { $null } else { [System.IO.Path]::GetFullPath($SelectedPath) }
        suffix = if ([string]::IsNullOrWhiteSpace($SelectedPath)) { $null } else { [System.IO.Path]::GetExtension($SelectedPath).ToLowerInvariant() }
        selection_source = $SelectionSource
        version_probe = $VersionProbe
    }
}

function Invoke-ToolResolutionPreflight {
    $modeVariable = Get-Variable -Name Mode -ErrorAction SilentlyContinue
    $modeValue = if ($null -eq $modeVariable) { "ReviewBundle" } else { [string]$modeVariable.Value }
    $approvalTokenVariable = Get-Variable -Name ApprovalToken -ErrorAction SilentlyContinue
    $approvalTokenValue = if ($null -eq $approvalTokenVariable) { "" } else { [string]$approvalTokenVariable.Value }
    $issueNumberVariable = Get-Variable -Name IssueNumber -ErrorAction SilentlyContinue
    $issueNumberValue = if ($null -eq $issueNumberVariable) { 0 } else { [int]$issueNumberVariable.Value }

    if ($issueNumberValue -ne 0 -or
        -not [string]::Equals($modeValue, "ReviewBundle", [System.StringComparison]::Ordinal) -or
        -not [string]::IsNullOrEmpty($approvalTokenValue)) {
        throw "ToolResolutionPreflight does not accept IssueNumber, non-ReviewBundle Mode, or ApprovalToken."
    }
    if (-not [string]::Equals($RequiredAction, "run-reviewbundle", [System.StringComparison]::Ordinal)) {
        throw "ToolResolutionPreflight requires -RequiredAction run-reviewbundle."
    }

    $blocked = @()
    $tools = @{}

    try {
        $ghPath = Resolve-GitHubCliCommand
        $ghProbeCommand = Resolve-GitHubCliProbeCommand -GhPath $ghPath
        $ghProbe = New-ToolResolutionNativeProbe -FilePath $ghProbeCommand.FilePath -Arguments @($ghProbeCommand.Arguments) -Action "gh --version"
        $tools["runner_gh"] = New-ToolEntry -SelectedPath $ghPath -SelectionSource "other existing source" -VersionProbe $ghProbe
        if (-not $ghProbe.ok) {
            $blocked += "runner_gh_version_probe_failed"
        }
    }
    catch {
        $blocked += "runner_gh_unavailable"
        $tools["runner_gh"] = New-ToolEntry -SelectedPath $null -SelectionSource $null -VersionProbe $null
    }

    try {
        $pythonPath = Resolve-PythonRuntimeCommand
        $pythonProbe = New-ToolResolutionNativeProbe -FilePath $pythonPath -Arguments @("--version") -Action "python --version"
        $tools["python"] = New-ToolEntry -SelectedPath $pythonPath -SelectionSource "direct executable on PATH" -VersionProbe $pythonProbe
        if (-not $pythonProbe.ok) {
            $blocked += "runner_python_version_probe_failed"
        }
    }
    catch {
        $blocked += "runner_python_unavailable"
        $tools["python"] = New-ToolEntry -SelectedPath $null -SelectionSource $null -VersionProbe $null
    }

    try {
        $evaluatorIdentity = Get-RuntimeContractEvaluatorIdentity
        $tools["runtime_contract_evaluator"] = [ordered]@{
            selected_path = [System.IO.Path]::GetFullPath([string]$evaluatorIdentity.EvaluatorPath)
            suffix = ".py"
            selection_source = "repository trusted path"
            available = $true
            identity_fingerprint = [string]$evaluatorIdentity.Fingerprint
            files = $evaluatorIdentity.Files
        }
    }
    catch {
        $blocked += "runtime_contract_evaluator_unavailable"
        $tools["runtime_contract_evaluator"] = [ordered]@{
            selected_path = $null
            suffix = ".py"
            selection_source = "repository trusted path"
            available = $false
            identity_fingerprint = $null
            files = [ordered]@{}
        }
    }

    try {
        $codexCommand = Resolve-CodexCommand
        $codexProbe = New-ToolResolutionNativeProbe `
            -FilePath $codexCommand.FilePath `
            -Arguments (@($codexCommand.ArgumentPrefix) + @("--version")) `
            -Action "codex --version"
        $selectionSourceProperty = $codexCommand.PSObject.Properties["SelectionSource"]
        $selectionSourceValue = if ($null -eq $selectionSourceProperty) { "" } else { [string]$selectionSourceProperty.Value }
        $selectionSource = if ([string]::IsNullOrWhiteSpace($selectionSourceValue)) { "path" } else { $selectionSourceValue }
        $tools["codex"] = New-ToolEntry -SelectedPath $codexCommand.Source -SelectionSource $selectionSource -VersionProbe $codexProbe
        if (-not $codexProbe.ok) {
            $blocked += "codex_version_probe_failed"
        }
    }
    catch {
        $blocked += "codex_unavailable"
        $tools["codex"] = New-ToolEntry -SelectedPath $null -SelectionSource $null -VersionProbe $null
    }

    $result = if ($blocked.Count -eq 0) { "success" } else { "blocked" }
    $summary = [ordered]@{
        protocol = $ToolResolutionPreflightProtocol
        component = "runner"
        result = $result
        required_action = $RequiredAction
        blocked_reasons = @($blocked)
        tools = $tools
        nested_runner = $null
        safety = New-ToolResolutionSafety
    }
    Write-Output ($summary | ConvertTo-Json -Depth 12 -Compress)
    if ($result -eq "success") {
        exit 0
    }
    exit 2
}

function New-ChildProcessReviewBundleSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Result,
        [AllowNull()]
        [string]$FinalStatus,
        [AllowNull()]
        [object]$CodexCommand = $null,
        [string]$ReviewedCodexPath = "",
        [AllowNull()]
        [object]$CodexVersionProbe = $null
    )

    $partialCandidateExists = (-not [string]::IsNullOrWhiteSpace($FinalStatus)).ToString().ToLowerInvariant()
    $timedOut = ([bool]$Result.TimedOut).ToString().ToLowerInvariant()
    $stopAttempted = ([bool]$Result.StopAttempted).ToString().ToLowerInvariant()
    $stoppedIds = @($Result.StoppedProcessIds) -join ","
    if ([string]::IsNullOrWhiteSpace($stoppedIds)) {
        $stoppedIds = "none"
    }
    $actualSource = if ($null -eq $CodexCommand) { "" } else { [string]$CodexCommand.Source }
    $resultFilePathProperty = $Result.PSObject.Properties["FilePath"]
    $resultFilePath = if ($null -eq $resultFilePathProperty) { "" } else { [string]$resultFilePathProperty.Value }
    $actualFilePath = if ($null -eq $CodexCommand) { $resultFilePath } else { [string]$CodexCommand.FilePath }
    $launcherType = if ($null -eq $CodexCommand) { "" } else { [string]$CodexCommand.LauncherType }
    $bindingMatch = if ($null -eq $CodexCommand) { $false } else { [bool]$CodexCommand.PathBindingMatch }
    $bindingMatchText = $bindingMatch.ToString().ToLowerInvariant()
    $probeAttempted = if ($null -eq $CodexVersionProbe) { $false } else { [bool]$CodexVersionProbe.Attempted }
    $probePassed = if ($null -eq $CodexVersionProbe) { $false } else { [bool]$CodexVersionProbe.Passed }
    $probeTimedOut = if ($null -eq $CodexVersionProbe) { $false } else { [bool]$CodexVersionProbe.TimedOut }
    $probeExitCode = if ($null -eq $CodexVersionProbe -or $null -eq $CodexVersionProbe.ExitCode) { "missing" } else { [string]$CodexVersionProbe.ExitCode }
    $probeProcessFilePath = if ($null -eq $CodexVersionProbe) { "" } else { [string]$CodexVersionProbe.ProcessFilePath }
    $probeLauncherSource = if ($null -eq $CodexVersionProbe) { "" } else { [string]$CodexVersionProbe.LauncherSource }
    $probePathBindingMatch = if ($null -eq $CodexVersionProbe) { $false } else { [bool]$CodexVersionProbe.PathBindingMatch }

    return @"
child_process_command=$($Result.CommandLine)
reviewed_codex_path=$(Format-Block -Text $ReviewedCodexPath -EmptyText "(none)")
actual_child_process_source=$(Format-Block -Text $actualSource -EmptyText "(unknown)")
actual_process_file_path=$(Format-Block -Text $actualFilePath -EmptyText "(unknown)")
launcher_type=$(Format-Block -Text $launcherType -EmptyText "(unknown)")
path_binding_match=$bindingMatchText
codex_version_probe_attempted=$($probeAttempted.ToString().ToLowerInvariant())
codex_version_probe_exit_code=$probeExitCode
codex_version_probe_timed_out=$($probeTimedOut.ToString().ToLowerInvariant())
codex_version_probe_passed=$($probePassed.ToString().ToLowerInvariant())
codex_version_probe_process_file_path=$(Format-Block -Text $probeProcessFilePath -EmptyText "(unknown)")
codex_version_probe_launcher_source=$(Format-Block -Text $probeLauncherSource -EmptyText "(unknown)")
codex_version_probe_path_binding_match=$($probePathBindingMatch.ToString().ToLowerInvariant())
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
parent_commit_push_close_continuation_after_timeout=false
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
        [string]$CodexExitCode,
        [Parameter(Mandatory = $true)]
        [Alias("NoStage")]
        [bool]$FinalIndexClean,
        [Parameter(Mandatory = $true)]
        [Alias("NoCommit")]
        [bool]$FinalHeadMatchesInitial,
        [Parameter(Mandatory = $true)]
        [bool]$ApprovalTokenGenerated,
        [AllowNull()]
        [object]$RuntimeContractBinding = $null,
        [AllowNull()]
        [object]$ExecutionAssurance = $null,
        [AllowNull()]
        [object]$CandidateEvidenceManifest = $null
    )

    if ($null -eq $RuntimeContractBinding) {
        $RuntimeContractBinding = New-RuntimeContractNotPresent
    }
    if ($null -eq $ExecutionAssurance) {
        $ExecutionAssurance = New-ExecutionAssurance `
            -RuntimeContractBinding $RuntimeContractBinding `
            -ObservableEvidence "unverified"
    }
    $candidateManifestVerified = $null -ne $CandidateEvidenceManifest -and
        [string]::Equals([string]$CandidateEvidenceManifest.status, "verified", [System.StringComparison]::Ordinal) -and
        -not [string]::IsNullOrWhiteSpace([string]$CandidateEvidenceManifest.fingerprint) -and
        [string]::Equals(
            [string]$CandidateEvidenceManifest.fingerprint,
            [string]$ExecutionAssurance.candidate_manifest_fingerprint,
            [System.StringComparison]::Ordinal
        )
    $candidateSnapshotEligible = $ApprovalTokenGenerated -and
        $candidateManifestVerified -and
        (Test-ApprovalContextAllowed `
            -RuntimeContractBinding $RuntimeContractBinding `
            -FinalIndexClean $FinalIndexClean `
            -FinalHeadMatchesInitial $FinalHeadMatchesInitial `
            -ExecutionAssurance $ExecutionAssurance)

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
        runtime_contract_binding = $RuntimeContractBinding
        execution_assurance = $ExecutionAssurance
        candidate_evidence_manifest = $CandidateEvidenceManifest
        candidate_acceptance = if ($candidateSnapshotEligible) { "eligible" } else { "ineligible" }
        approval_token_generated = $candidateSnapshotEligible
        approval_token_semantics = "candidate_review_snapshot_not_human_approval"
        validations = [ordered]@{
            git_status_clean = (New-RunnerValidationResult -Status $(if ($finalClean) { "passed" } else { "warning" }) -Summary $(if ($finalClean) { "Final git status is clean." } else { "Final git status reports local changes for review." }))
            codex = (New-RunnerValidationResult -Status $codexStatus -Summary "Codex exit code: $CodexExitCode")
            pytest = (New-RunnerValidationResult -Status "reported" -Summary "See Codex final report for test commands and results.")
            git_diff_check = (New-RunnerValidationResult -Status "reported" -Summary "See Codex final report for git diff --check result if run.")
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

        $repositoryRoot = [System.IO.Path]::GetFullPath($RepoPath).TrimEnd("\", "/")
        $repositoryPrefix = $repositoryRoot + [System.IO.Path]::DirectorySeparatorChar
        $fullPath = Join-Path -Path $repositoryRoot -ChildPath $path
        $resolvedParent = Resolve-Path -LiteralPath (Split-Path -Parent $fullPath) -ErrorAction SilentlyContinue
        if ($null -ne $resolvedParent) {
            $resolvedParentPath = [System.IO.Path]::GetFullPath($resolvedParent.Path).TrimEnd("\", "/")
            if ($resolvedParentPath -ne $repositoryRoot -and
                -not $resolvedParentPath.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing path outside repo root: $path"
            }
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

function Assert-RepositoryLocalGitIdentity {
    $nameResult = Invoke-Git -GitArgs @("config", "--local", "--get", "user.name")
    if ($nameResult.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($nameResult.Stdout)) {
        throw "Repository-local git user.name is missing. Configure it explicitly before CommitApproved."
    }

    $emailResult = Invoke-Git -GitArgs @("config", "--local", "--get", "user.email")
    if ($emailResult.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($emailResult.Stdout)) {
        throw "Repository-local git user.email is missing. Configure it explicitly before CommitApproved."
    }

    return [pscustomobject]@{
        UserName = $nameResult.Stdout.Trim()
        UserEmail = $emailResult.Stdout.Trim()
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
        [switch]$RequireChanges,
        [AllowEmptyCollection()]
        [string[]]$AllowedFiles = @(),
        [AllowNull()]
        [object]$CandidateManifest = $null
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
    $allowedNormalization = ConvertTo-NormalizedRuntimeContractPathSet `
        -Paths @($AllowedFiles) `
        -InvalidReason "invalid_allowed_file"
    if (@($allowedNormalization.Reasons).Count -gt 0) {
        throw "Approval state contains an invalid allowed path."
    }
    $normalizedAllowedFiles = @($allowedNormalization.Paths)
    if ($null -eq $CandidateManifest) {
        $CandidateManifest = Get-BoundedCandidateManifest -AllowedFiles $normalizedAllowedFiles
    }
    if ([string]$CandidateManifest.status -ne "verified" -or
        [string]::IsNullOrWhiteSpace([string]$CandidateManifest.fingerprint)) {
        throw "Bounded candidate evidence manifest is unverified."
    }

    $statusPayload = $statusLines -join [Environment]::NewLine
    $allowedScopePayload = @($normalizedAllowedFiles) -join "`n"
    $allowedScopeFingerprint = Get-Sha256Text -Text $allowedScopePayload
    $manifestFingerprint = [string]$CandidateManifest.fingerprint
    $filesPayload = "issue=$IssueNumberForState`nbranch=$branchForState`nhead=$headForState`nevidence=$CandidateEvidenceProfile`nisolation=unverified`nscope=`n$allowedScopePayload`nmanifest=$manifestFingerprint`nstatus=`n$statusPayload"
    $diffPayload = "issue=$IssueNumberForState`nbranch=$branchForState`nhead=$headForState`nevidence=$CandidateEvidenceProfile`nisolation=unverified`nscope=$allowedScopeFingerprint`nmanifest=$manifestFingerprint`nstatus=`n$statusPayload`ntracked-diff=`n$trackedDiff`nuntracked=`n$untrackedPayload"
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
        AllowedFiles = $normalizedAllowedFiles
        AllowedScopeFingerprint = $allowedScopeFingerprint
        CandidateManifest = $CandidateManifest
        CandidateManifestFingerprint = $manifestFingerprint
        EvidenceProfile = $CandidateEvidenceProfile
        IsolationGuarantee = "unverified"
        FilesPayload = $filesPayload
        FilesPayloadHash = Get-Sha256Text -Text $filesPayload
        DiffPayload = $diffPayload
        DiffPayloadHash = Get-Sha256Text -Text $diffPayload
        DiffFingerprint = $diffFingerprint
        FilesFingerprint = $filesFingerprint
        ReviewId = $reviewId
        ApprovalToken = "LRV1-APPROVE issue=$IssueNumberForState mode=Level3A branch=$branchForState head=$headForState review=$reviewId diff=$diffFingerprint files=$filesFingerprint scope=$allowedScopeFingerprint manifest=$manifestFingerprint evidence=$CandidateEvidenceProfile isolation=unverified"
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
    if ($parts.Count -ne 12 -or $parts[0] -ne "LRV1-APPROVE") {
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

    foreach ($requiredKey in @("issue", "mode", "branch", "head", "review", "diff", "files", "scope", "manifest", "evidence", "isolation")) {
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
        Scope = $values["scope"]
        Manifest = $values["manifest"]
        Evidence = $values["evidence"]
        Isolation = $values["isolation"]
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
    if ($Token.Scope -ne $State.AllowedScopeFingerprint) { $mismatches += "allowed scope fingerprint mismatch" }
    if ($Token.Manifest -ne $State.CandidateManifestFingerprint) { $mismatches += "candidate manifest fingerprint mismatch" }
    if ($Token.Evidence -ne $State.EvidenceProfile) { $mismatches += "evidence profile mismatch" }
    if ($Token.Isolation -ne $State.IsolationGuarantee) { $mismatches += "isolation guarantee mismatch" }

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
        [string]$FinalStatus,
        [Parameter(Mandatory = $true)]
        [Alias("NoStage")]
        [bool]$FinalIndexClean,
        [Parameter(Mandatory = $true)]
        [Alias("NoCommit")]
        [bool]$FinalHeadMatchesInitial,
        [AllowNull()]
        [object]$RuntimeContractBinding = $null,
        [AllowNull()]
        [object]$ExecutionAssurance = $null,
        [AllowNull()]
        [object]$CandidateEvidenceManifest = $null,
        [bool]$CandidatePathsReviewable = $true
    )

    if ($null -eq $RuntimeContractBinding) {
        $RuntimeContractBinding = New-RuntimeContractNotPresent
    }
    if ($null -eq $ExecutionAssurance) {
        $ExecutionAssurance = New-ExecutionAssurance `
            -RuntimeContractBinding $RuntimeContractBinding `
            -ObservableEvidence "unverified"
    }
    if (-not (Test-ApprovalContextAllowed `
        -RuntimeContractBinding $RuntimeContractBinding `
        -FinalIndexClean $FinalIndexClean `
        -FinalHeadMatchesInitial $FinalHeadMatchesInitial `
        -ExecutionAssurance $ExecutionAssurance `
        -CandidatePathsReviewable $CandidatePathsReviewable)) {
        $ApprovalToken = ""
    }

    $TextFence = '```text'
    $Fence = '```'
    $displayDiffStat = Format-Block -Text (Truncate-Text -Text $DiffStat -MaxChars $MaxGitOutputChars -Label "git diff --stat") -EmptyText "(no unstaged tracked diff)"
    $displayCachedDiffStat = Format-Block -Text (Truncate-Text -Text $CachedDiffStat -MaxChars $MaxGitOutputChars -Label "git diff --cached --stat") -EmptyText "(no staged diff)"
    $displayFinalStatus = Format-Block -Text (Truncate-Text -Text $FinalStatus -MaxChars $MaxGitOutputChars -Label "final git status") -EmptyText "(clean)"
    $displayModifiedFiles = Format-Block -Text (Truncate-Text -Text $ModifiedFiles -MaxChars $MaxGitOutputChars -Label "modified files") -EmptyText "(none)"
    $displayFinalReport = Format-Block -Text $CodexFinalReport -EmptyText "(no Codex stdout captured)"
    $displayChildProcessSummary = Format-Block -Text $ChildProcessSummary -EmptyText "child_process_timed_out=false`nparent_commit_push_close_continuation_after_timeout=false"
    $runnerResult = Get-OverallRunnerResult `
        -CodexExitCode $CodexExitCode `
        -RuntimeContractBinding $RuntimeContractBinding `
        -ExecutionAssurance $ExecutionAssurance
    $runtimeContractJson = $RuntimeContractBinding | ConvertTo-Json -Depth 12
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
        -CodexExitCode $CodexExitCode `
        -FinalIndexClean $FinalIndexClean `
        -FinalHeadMatchesInitial $FinalHeadMatchesInitial `
        -ApprovalTokenGenerated (-not [string]::IsNullOrWhiteSpace($ApprovalToken)) `
        -RuntimeContractBinding $RuntimeContractBinding `
        -ExecutionAssurance $ExecutionAssurance `
        -CandidateEvidenceManifest $CandidateEvidenceManifest

    $finalIndexCleanText = if ($FinalIndexClean) { "yes" } else { "no" }
    $finalHeadMatchesText = if ($FinalHeadMatchesInitial) { "yes" } else { "no" }
    $executionAssuranceJson = $ExecutionAssurance | ConvertTo-Json -Depth 12
    $candidateManifestJson = if ($null -eq $CandidateEvidenceManifest) { "null" } else { $CandidateEvidenceManifest | ConvertTo-Json -Depth 12 }

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

### Bounded evidence and trusted-parent facts

- Repo clean before start: $RepoCleanBefore
- Final staged area observed clean: $finalIndexCleanText
- Final HEAD matches initial HEAD: $finalHeadMatchesText
- Runner parent invoked stage/commit/push/Issue-close/label-edit/PR-create/merge: no
- Runner parent consumed an approval token: no
- Child-wide absence of transient actions or external side effects: not guaranteed

### Modified files

$TextFence
$displayModifiedFiles
$Fence

### Runtime contract binding

$TextFence
$runtimeContractJson
$Fence

### Execution assurance

$TextFence
$executionAssuranceJson
$Fence

### Bounded candidate evidence manifest

$TextFence
$candidateManifestJson
$Fence

### Approval context

The token below, when present, binds a candidate-review snapshot only. It is not human approval, final acceptance, new authority, or proof of universal write prevention. CommitApproved re-reads the current v1.1 contract and recomputes branch, full HEAD, allowed scope, candidate manifest, and fingerprints before staging.

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

This run is review-bundle-only. Human / ChatGPT review remains a separate authority event before any commit. A candidate token records eligibility for review only and does not itself approve CommitApproved. Do not push until a separate push step is approved.
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

### Candidate token and trusted-parent actions

- Candidate snapshot token matched the rebound current state: yes
- Token meaning: candidate snapshot only; not human approval or new authority
- Exactly one local commit created: yes
- Runner parent invoked push/Issue-close/label-edit/PR-create/merge: no
- Hook, child, transient, or external side effects absent: not guaranteed
- Token input source: $ApprovalSource

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

### Trusted-parent action facts

- Local commit completed: $LocalCommitCreated
- Runner parent invoked push/Issue-close/label-edit/PR-create/merge/force-push: no
- Runner parent invoked auto-reset: no
- Hook, child, transient, or external side effects absent: not guaranteed

### Final git status

$TextFence
$displayStatus
$Fence

### Cleanup note

$cleanupNote
"@
}

function Get-CommitApprovedBoundState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$IssueBody
    )

    $branchForContract = Format-Block `
        -Text (Get-GitOutput -GitArgs @("branch", "--show-current") -Action "git branch --show-current") `
        -EmptyText "(detached HEAD)"
    $headForContract = Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
    $runtimeContractBinding = Invoke-RuntimeContractEvaluator `
        -Action "inspect" `
        -PythonPath (Resolve-PythonRuntimeCommand) `
        -TrustedCommittedBaseline `
        -Payload ([ordered]@{
            surface_text = $IssueBody
            logical_issue = $IssueNumber
            repository = $Repo
            branch = $branchForContract
            head = $headForContract
        })
    $scopeViolationReasons = @(Get-AllowedFileScopeViolationReasons -AllowedFiles @($runtimeContractBinding.allowed_files))
    if (-not [bool]$runtimeContractBinding.contract_present -or
        -not [string]::Equals([string]$runtimeContractBinding.status, "passed", [System.StringComparison]::Ordinal) -or
        $scopeViolationReasons.Count -gt 0) {
        $reason = @(@($runtimeContractBinding.reasons) + $scopeViolationReasons) -join ","
        throw "CommitApproved requires a currently valid Task Packet v1.1 governance contract: $reason"
    }

    $observation = Get-ReviewBundleGitObservation
    $manifest = Get-BoundedCandidateManifest -AllowedFiles @($runtimeContractBinding.allowed_files)
    $observableEvidence = if ($manifest.status -eq "verified") { "verified" } else { "unverified" }
    $actualFiles = @(Get-StatusPaths -Status $observation.Status)
    $invariantReasons = @(Get-ReviewBundleInvariantViolationReasons `
        -HeadBefore $headForContract `
        -HeadAfter ([string]$observation.Head) `
        -NoStage ([bool]$observation.NoStage) `
        -IndexVisibilityFilesBefore @($observation.IndexVisibilityFiles) `
        -IndexVisibilityFilesAfter @($observation.IndexVisibilityFiles) `
        -GitVisibilityMetadataFingerprintBefore ([string]$observation.GitVisibilityMetadataFingerprint) `
        -GitVisibilityMetadataFingerprintAfter ([string]$observation.GitVisibilityMetadataFingerprint))
    $runtimeContractBinding = Invoke-ParentControlledRuntimeContractEnforcement `
        -RuntimeContractBinding $runtimeContractBinding `
        -ActualChangedFiles $actualFiles `
        -InvariantViolationReasons $invariantReasons
    if ($runtimeContractBinding.status -eq "contract_violation") {
        $observableEvidence = "violation"
    }
    $assurance = New-ExecutionAssurance `
        -RuntimeContractBinding $runtimeContractBinding `
        -ObservableEvidence $observableEvidence `
        -CandidateManifest $manifest
    $headMatches = [string]::Equals($headForContract, [string]$observation.Head, [System.StringComparison]::OrdinalIgnoreCase)
    if (-not (Test-ApprovalContextAllowed `
        -RuntimeContractBinding $runtimeContractBinding `
        -FinalIndexClean ([bool]$observation.NoStage) `
        -FinalHeadMatchesInitial $headMatches `
        -ExecutionAssurance $assurance `
        -CandidatePathsReviewable $true)) {
        throw "CommitApproved current governance or bounded evidence is not eligible for continuation."
    }

    $approvalState = Get-ApprovalState `
        -IssueNumberForState $IssueNumber `
        -RequireChanges `
        -AllowedFiles @($runtimeContractBinding.allowed_files) `
        -CandidateManifest $manifest
    Assert-NoPreexistingStagedFiles -Status $approvalState.Status

    return [pscustomobject]@{
        RuntimeContractBinding = $runtimeContractBinding
        ExecutionAssurance = $assurance
        CandidateManifest = $manifest
        ApprovalState = $approvalState
    }
}

function Get-CommitApprovedIssueSnapshot {
    $issueJsonResult = Invoke-Captured {
        & $Gh issue view $IssueNumber --repo $Repo --json title,body,url,number
    }
    Require-Success -Result $issueJsonResult -Action "gh issue view"
    try {
        $issue = $issueJsonResult.Stdout | ConvertFrom-Json
    }
    catch {
        throw "gh issue view returned malformed JSON for CommitApproved."
    }
    if ($null -eq $issue -or $issue -is [array] -or [int]$issue.number -ne $IssueNumber) {
        throw "gh issue view returned an invalid Issue snapshot for CommitApproved."
    }
    return $issue
}

function Write-CommitApprovalStateDiagnostic {
    $issue = Get-CommitApprovedIssueSnapshot
    $issueTitle = [string]$issue.title
    $issueBody = [string]$issue.body
    if (-not (Test-IssueAllowsWriteCapableRun -Title $issueTitle -Body $issueBody)) {
        throw "Issue #$IssueNumber does not explicitly identify itself as write-capable or review-bundle capable."
    }

    $boundState = Get-CommitApprovedBoundState -IssueBody $issueBody
    $state = $boundState.ApprovalState
    $summary = [ordered]@{
        protocol = "lawb.runner_v1.commit_approval_state.v1"
        issue = [string]$state.IssueNumber
        branch = [string]$state.Branch
        head = [string]$state.Head
        review_id = [string]$state.ReviewId
        diff_fingerprint = [string]$state.DiffFingerprint
        files_fingerprint = [string]$state.FilesFingerprint
        scope_fingerprint = [string]$state.AllowedScopeFingerprint
        manifest_fingerprint = [string]$state.CandidateManifestFingerprint
        evidence_profile = [string]$state.EvidenceProfile
        isolation_guarantee = [string]$state.IsolationGuarantee
        modified_files = @($state.ModifiedFiles)
        approval_token = [string]$state.ApprovalToken
        trusted_evaluator_source = "committed_head"
    }
    Write-Output "LRV1-COMMIT-APPROVAL-STATE protocol=lawb.runner_v1.commit_approval_state.v1"
    Write-Output ($summary | ConvertTo-Json -Depth 8 -Compress)
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

    $null = Assert-RepositoryLocalGitIdentity

    $issue = Get-CommitApprovedIssueSnapshot
    $issueTitle = [string]$issue.title
    $issueBody = [string]$issue.body

    if (-not (Test-IssueAllowsWriteCapableRun -Title $issueTitle -Body $issueBody)) {
        throw "Issue #$IssueNumber does not explicitly identify itself as write-capable or review-bundle capable."
    }

    $boundState = Get-CommitApprovedBoundState -IssueBody $issueBody
    $state = $boundState.ApprovalState

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

    $currentIssue = Get-CommitApprovedIssueSnapshot
    $currentIssueTitle = [string]$currentIssue.title
    $currentIssueBody = [string]$currentIssue.body
    if (-not (Test-IssueAllowsWriteCapableRun -Title $currentIssueTitle -Body $currentIssueBody)) {
        throw "Issue #$IssueNumber no longer identifies itself as write-capable or review-bundle capable."
    }
    $boundStateBeforeStage = Get-CommitApprovedBoundState -IssueBody $currentIssueBody
    $stateBeforeStage = $boundStateBeforeStage.ApprovalState
    Assert-ApprovalMatchesState -Token $token -State $stateBeforeStage
    $issueTitle = $currentIssueTitle

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

Assert-TargetRepositoryBinding

if ($ToolResolutionPreflight) {
    Invoke-ToolResolutionPreflight
}

if ($IssueNumber -lt 1) {
    $issueNumberRequiredMessage = "IssueNumber is required for ReviewBundle, CommitApproved, " +
        "ApprovalStateDiagnostic, and CommitApprovalStateDiagnostic modes."
    throw $issueNumberRequiredMessage
}

if ($Mode -eq "ApprovalStateDiagnostic") {
    Write-ApprovalStateDiagnostic
    exit 0
}

$Gh = Resolve-GitHubCliCommand

if ($Mode -eq "CommitApprovalStateDiagnostic") {
    Write-CommitApprovalStateDiagnostic
    exit 0
}

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
$headBefore = Get-GitOutput -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
$initialStatus = Get-GitStatusShort
$initialNoStage = -not (Test-GitStatusHasStagedChanges -Status $initialStatus)

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
        -FinalStatus $initialStatus `
        -FinalIndexClean $initialNoStage `
        -FinalHeadMatchesInitial $true

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
        -FinalStatus "(clean)" `
        -FinalIndexClean $true `
        -FinalHeadMatchesInitial $true

    $postResult = Post-IssueComment -Comment $comment
    if ($postResult.ExitCode -ne 0) {
        throw "gh issue comment failed with exit code $($postResult.ExitCode): $($postResult.Stderr)"
    }
    Write-Output $postResult.Stdout
    exit 3
}

$headBeforeFull = $headBefore
$runtimeContractPython = Resolve-PythonRuntimeCommand
$runtimeContractBinding = Invoke-RuntimeContractEvaluator `
    -Action "inspect" `
    -PythonPath $runtimeContractPython `
    -Payload ([ordered]@{
        surface_text = $issueBody
        logical_issue = $IssueNumber
        repository = $Repo
        branch = $branch
        head = $headBeforeFull
    })
$preExecutionScopeReasons = @(Get-AllowedFileScopeViolationReasons -AllowedFiles @($runtimeContractBinding.allowed_files))
if ($preExecutionScopeReasons.Count -gt 0) {
    $runtimeContractBinding = New-RuntimeContractViolationBinding `
        -RuntimeContractBinding $runtimeContractBinding `
        -Reasons $preExecutionScopeReasons
    $runtimeContractBinding.pre_execution = [pscustomobject]@{
        status = "contract_violation"
        reasons = $preExecutionScopeReasons
    }
    $runtimeContractBinding.post_execution = [pscustomobject]@{
        status = "not_run"
        reasons = @()
    }
}
if ([string]::Equals([string]$runtimeContractBinding.status, "contract_violation", [System.StringComparison]::Ordinal)) {
    $stderrSummary = Get-StderrSummary -Text "" -ExitCode "not-run"
    $violationReasons = @($runtimeContractBinding.reasons) -join ","
    $comment = New-ReviewBundleComment `
        -IssueNumberText ([string]$IssueNumber) `
        -Branch $branch `
        -HeadBefore $headBefore `
        -HeadAfter $headBefore `
        -CodexExitCode "not run; runtime contract violation" `
        -RepoCleanBefore "yes" `
        -ReviewId "" `
        -DiffFingerprint "" `
        -FilesFingerprint "" `
        -ApprovalToken "" `
        -ModifiedFiles "(none)" `
        -DiffStat "" `
        -CachedDiffStat "" `
        -CommandsSummary "Codex was not run because Task Packet v1.1 runtime contract binding failed: $violationReasons" `
        -CodexFinalReport "Codex was not run. Runtime contract identity evidence failed closed before invocation." `
        -StderrSummary $stderrSummary `
        -FinalStatus "(clean)" `
        -FinalIndexClean $true `
        -FinalHeadMatchesInitial $true `
        -RuntimeContractBinding $runtimeContractBinding
    $postResult = Post-IssueComment -Comment $comment
    if ($postResult.ExitCode -ne 0) {
        throw "Runtime contract violation blocked Codex, and posting the failure bundle failed: $($postResult.Stderr)"
    }
    Write-Output $postResult.Stdout
    exit 2
}
Assert-RuntimeContractAllowsCodex -RuntimeContractBinding $runtimeContractBinding

if ([string]::IsNullOrWhiteSpace($ReviewedCodexPath)) {
    throw "ReviewedCodexPath is required for ReviewBundle execution; refusing to re-resolve codex from PATH."
}
$codexCommand = Resolve-CodexCommand -ReviewedCodexPath $ReviewedCodexPath
if (-not [bool]$codexCommand.PathBindingMatch) {
    throw "ReviewedCodexPath binding mismatch; refusing to launch codex."
}
$codexVersionProbe = Invoke-ReviewedCodexVersionProbe -CodexCommand $codexCommand -TimeoutSeconds 30
if (-not [bool]$codexVersionProbe.Passed) {
    throw "Reviewed Codex version probe failed closed before task invocation: $($codexVersionProbe.FailureReason)"
}
$codexUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
$codexArguments = @(
    "--ask-for-approval",
    "never",
    "exec",
    "--sandbox",
    "workspace-write",
    "-C",
    $RepoPath,
    "-"
)

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

$preExecutionObservation = Get-ReviewBundleGitObservation
$preExecutionManifest = Get-BoundedCandidateManifest -AllowedFiles @($runtimeContractBinding.allowed_files)
$codexResult = Invoke-CapturedNativeProcess `
    -FilePath $codexCommand.FilePath `
    -Arguments (@($codexCommand.ArgumentPrefix) + $codexArguments) `
    -WorkingDirectory $RepoPath `
    -StandardInput $prompt `
    -StandardInputEncoding $codexUtf8 `
    -StandardOutputEncoding $codexUtf8 `
    -StandardErrorEncoding $codexUtf8 `
    -TimeoutSeconds $ReviewBundleCodexTimeoutSeconds `
    -Action "codex ReviewBundle candidate generation"

$postExecutionObservation = Get-ReviewBundleGitObservation
$postExecutionManifest = Get-BoundedCandidateManifest -AllowedFiles @($runtimeContractBinding.allowed_files)
$headAfter = [string]$postExecutionObservation.Head
$finalStatus = [string]$postExecutionObservation.Status
$finalIndexClean = [bool]$postExecutionObservation.NoStage
$finalHeadMatchesInitial = [string]::Equals($headBeforeFull, $headAfter, [System.StringComparison]::OrdinalIgnoreCase)
$diffStatAfter = Get-GitOutput -GitArgs @("diff", "--stat") -Action "git diff --stat"
$cachedDiffStatAfter = Get-GitOutput -GitArgs @("diff", "--cached", "--stat") -Action "git diff --cached --stat"
$allowedFilesChanged = @(Get-ChangedAllowedFilesFromManifests `
    -Before $preExecutionManifest `
    -After $postExecutionManifest)
$actualChangedFiles = @(Get-ReviewBundleEffectiveChangedFiles `
    -Status $finalStatus `
    -UntrackedFilesBefore @($preExecutionObservation.UntrackedFiles) `
    -UntrackedFilesAfter @($postExecutionObservation.UntrackedFiles) `
    -IndexVisibilityFilesBefore @($preExecutionObservation.IndexVisibilityFiles) `
    -IndexVisibilityFilesAfter @($postExecutionObservation.IndexVisibilityFiles) `
    -AllowedFilesChanged $allowedFilesChanged)
$reviewableStatusFiles = @()
$candidatePathsReviewable = $true
try {
    $reviewableStatusFiles = @(Get-StatusPaths -Status $finalStatus)
}
catch {
    $candidatePathsReviewable = $false
}
if ($candidatePathsReviewable -and
    (@($actualChangedFiles | Sort-Object) -join "`n") -ne (@($reviewableStatusFiles | Sort-Object) -join "`n")) {
    $candidatePathsReviewable = $false
}
$modifiedFiles = if ($actualChangedFiles.Count -eq 0) {
    "(none)"
}
else {
    $actualChangedFiles -join [Environment]::NewLine
}
$invariantViolationReasons = @(Get-ReviewBundleInvariantViolationReasons `
    -HeadBefore $headBeforeFull `
    -HeadAfter $headAfter `
    -NoStage $finalIndexClean `
    -IndexVisibilityFilesBefore @($preExecutionObservation.IndexVisibilityFiles) `
    -IndexVisibilityFilesAfter @($postExecutionObservation.IndexVisibilityFiles) `
    -GitVisibilityMetadataFingerprintBefore ([string]$preExecutionObservation.GitVisibilityMetadataFingerprint) `
    -GitVisibilityMetadataFingerprintAfter ([string]$postExecutionObservation.GitVisibilityMetadataFingerprint))
$runtimeContractBinding = Invoke-ParentControlledRuntimeContractEnforcement `
    -RuntimeContractBinding $runtimeContractBinding `
    -ActualChangedFiles $actualChangedFiles `
    -InvariantViolationReasons $invariantViolationReasons
$observableEvidence = if ($preExecutionManifest.status -eq "verified" -and $postExecutionManifest.status -eq "verified") {
    "verified"
}
else {
    "unverified"
}
if ($runtimeContractBinding.status -eq "contract_violation") {
    $observableEvidence = "violation"
}
$executionAssurance = New-ExecutionAssurance `
    -RuntimeContractBinding $runtimeContractBinding `
    -ObservableEvidence $observableEvidence `
    -CandidateManifest $postExecutionManifest
$codexFinalReport = Truncate-Text -Text $codexResult.Stdout -MaxChars $MaxCodexStdoutChars -Label "Codex final report"
$stderrSummaryAfter = Get-StderrSummary -Text $codexResult.Stderr -ExitCode ([string]$codexResult.ExitCode)
$commandsSummary = "Review the Codex final report below for commands and verification results reported by Codex. The runner also captured bounded final git status, git diff --stat, and git diff --cached --stat evidence. The trusted Runner parent did not invoke stage, commit, push, issue close, label edit, or PR commands; child-wide absence of transient or external actions is not guaranteed."
$childProcessSummary = New-ChildProcessReviewBundleSummary -Result $codexResult -FinalStatus $finalStatus -CodexCommand $codexCommand -ReviewedCodexPath $ReviewedCodexPath -CodexVersionProbe $codexVersionProbe
if ($codexResult.TimedOut) {
    $commandsSummary = "$commandsSummary Codex child process timed out after $($codexResult.TimeoutSeconds) second(s); runner stopped the child process tree when possible and did not continue into any higher-risk action."
}
$reviewId = ""
$diffFingerprint = ""
$filesFingerprint = ""
$approvalToken = ""
if (-not [string]::IsNullOrWhiteSpace($finalStatus) -and
    (Test-ApprovalContextAllowed `
        -RuntimeContractBinding $runtimeContractBinding `
        -FinalIndexClean $finalIndexClean `
        -FinalHeadMatchesInitial $finalHeadMatchesInitial `
        -ExecutionAssurance $executionAssurance `
        -CandidatePathsReviewable $candidatePathsReviewable)) {
    try {
        $approvalState = Get-ApprovalState `
            -IssueNumberForState $IssueNumber `
            -RequireChanges `
            -AllowedFiles @($runtimeContractBinding.allowed_files) `
            -CandidateManifest $postExecutionManifest
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
    -FinalStatus $finalStatus `
    -FinalIndexClean $finalIndexClean `
    -FinalHeadMatchesInitial $finalHeadMatchesInitial `
    -RuntimeContractBinding $runtimeContractBinding `
    -ExecutionAssurance $executionAssurance `
    -CandidateEvidenceManifest $postExecutionManifest `
    -CandidatePathsReviewable $candidatePathsReviewable

$commentResult = Post-IssueComment -Comment $comment
if ($commentResult.ExitCode -ne 0) {
    throw "gh issue comment failed with exit code $($commentResult.ExitCode): $($commentResult.Stderr)"
}

Write-Output $commentResult.Stdout
$overallExitCode = if (
    [string]::Equals([string]$runtimeContractBinding.status, "contract_violation", [System.StringComparison]::Ordinal) -or
    -not [string]::Equals([string]$executionAssurance.observable_evidence, "verified", [System.StringComparison]::Ordinal)
) { 2 } else { $codexResult.ExitCode }
exit $overallExitCode
