<#
.SYNOPSIS
Runs the canonical Bridge Operator B3-C preflight and, only when explicitly
requested, starts one bounded foreground B3-C process.

.DESCRIPTION
The default invocation is preflight-only. It does not read Inbox #147 or invoke
Bridge Operator, Dispatcher, Runner, Codex, or a GitHub write path.

.EXAMPLE
.\scripts\start_bridge_operator_b3c.ps1

.EXAMPLE
.\scripts\start_bridge_operator_b3c.ps1 -StartForeground -MaxCycles 1 -PollIntervalSeconds 0
#>

[CmdletBinding()]
param(
    [switch]$StartForeground,
    [ValidateSet(
        "HarryWhite-TW/local-ai-workbench",
        "HarryWhite-TW/human-approval-automation-gateway"
    )]
    [string]$Repository = "HarryWhite-TW/local-ai-workbench",
    [string]$TargetRepoRoot = "",
    [ValidateRange(1, 100)]
    [int]$MaxCycles = 1,
    [ValidateRange(0, 3600)]
    [double]$PollIntervalSeconds = 0,
    [ValidateRange(1, 86400)]
    [int]$TimeoutSeconds = 600,
    [string]$StateDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Protocol = "lawb.bridge_operator_b3c_launcher.v1"
$ControlRepository = "HarryWhite-TW/local-ai-workbench"
$HagRepository = "HarryWhite-TW/human-approval-automation-gateway"
$SupportedRepositories = @($ControlRepository, $HagRepository)
$BootstrapScript = Join-Path -Path $PSScriptRoot -ChildPath "bootstrap_course_environment.ps1"
$ControlRepoRoot = [System.IO.Path]::GetFullPath(
    (Join-Path -Path $PSScriptRoot -ChildPath "..")
).TrimEnd("\")

function Add-BlockedReason {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.ArrayList]$Reasons,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )
    if (-not $Reasons.Contains($Reason)) {
        [void]$Reasons.Add($Reason)
    }
}

function Get-SafeStderrSummary {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }
    $safe = $Text
    $safe = $safe -replace (
        '(?i)(["'']?(?:authorization|token|password|secret|credential)["'']?' +
        '\s*[:=]\s*["''])([^"''\r\n]*)(["''])'
    ), '$1[REDACTED]$3'
    $safe = $safe -replace (
        '(?im)\b(authorization|token|password|secret|credential)\b' +
        '\s*[:=]\s*(?:Bearer\s+)?[^\s,;}\]]+'
    ), '$1=[REDACTED]'
    $safe = $safe -replace (
        '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}'
    ), 'Bearer [REDACTED]'
    $safe = $safe -replace (
        '(?i)\b(?:gho|ghp|ghs|ghu|ghr)_[A-Za-z0-9_]{8,}\b'
    ), '[REDACTED]'
    $safe = $safe -replace (
        '(?i)\bgithub_pat_[A-Za-z0-9_]{8,}\b'
    ), '[REDACTED]'
    $safe = $safe -replace (
        '(?i)\bsk-proj-[A-Za-z0-9_-]{8,}\b'
    ), '[REDACTED]'
    $safe = $safe -replace (
        '(?i)\bsk-[A-Za-z0-9_-]{8,}\b'
    ), '[REDACTED]'
    $safe = $safe.Trim()
    if ($safe.Length -gt 600) {
        return $safe.Substring(0, 600) + "...[truncated]"
    }
    return $safe
}

function ConvertTo-WindowsCommandLineArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Argument)

    if ($Argument.Length -gt 0 -and $Argument -notmatch '[\s"]') {
        return $Argument
    }
    $escaped = [System.Text.RegularExpressions.Regex]::Replace(
        $Argument,
        '(\\*)"',
        '$1$1\"'
    )
    $escaped = [System.Text.RegularExpressions.Regex]::Replace(
        $escaped,
        '(\\+)$',
        '$1$1'
    )
    return '"' + $escaped + '"'
}

function ConvertFrom-NativeBytes {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [byte[]]$Bytes,
        [Parameter(Mandatory = $true)]
        [ValidateSet("utf-8", "cp950", "auto")]
        [string]$EncodingPolicy
    )

    if ($Bytes.Count -eq 0) {
        return [pscustomobject]@{
            succeeded = $true
            text = ""
            encoding = "empty"
            error = ""
        }
    }
    if (($Bytes.Count -ge 2 -and
            (($Bytes[0] -eq 0xff -and $Bytes[1] -eq 0xfe) -or
             ($Bytes[0] -eq 0xfe -and $Bytes[1] -eq 0xff))) -or
        ($Bytes.Count -ge 4 -and
            (($Bytes[0] -eq 0xff -and $Bytes[1] -eq 0xfe -and
              $Bytes[2] -eq 0x00 -and $Bytes[3] -eq 0x00) -or
             ($Bytes[0] -eq 0x00 -and $Bytes[1] -eq 0x00 -and
              $Bytes[2] -eq 0xfe -and $Bytes[3] -eq 0xff)))) {
        return [pscustomobject]@{
            succeeded = $false
            text = ""
            encoding = ""
            error = "unsupported_utf16_or_utf32_native_output"
        }
    }

    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $utf8Succeeded = $false
    $utf8Text = ""
    try {
        $utf8Text = $strictUtf8.GetString($Bytes)
        if ($utf8Text.Length -gt 0 -and $utf8Text[0] -eq [char]0xfeff) {
            $utf8Text = $utf8Text.Substring(1)
        }
        $utf8Succeeded = $true
    }
    catch [System.Text.DecoderFallbackException] {
    }

    if ($EncodingPolicy -eq "utf-8") {
        if (-not $utf8Succeeded) {
            return [pscustomobject]@{
                succeeded = $false
                text = ""
                encoding = ""
                error = "native_output_invalid_utf8"
            }
        }
        return [pscustomobject]@{
            succeeded = $true
            text = $utf8Text
            encoding = "utf-8"
            error = ""
        }
    }

    $strictCp950 = [System.Text.Encoding]::GetEncoding(
        950,
        [System.Text.EncoderFallback]::ExceptionFallback,
        [System.Text.DecoderFallback]::ExceptionFallback
    )
    $cp950Succeeded = $false
    $cp950Text = ""
    try {
        $cp950Text = $strictCp950.GetString($Bytes)
        $cp950Succeeded = $true
    }
    catch [System.Text.DecoderFallbackException] {
    }

    if ($EncodingPolicy -eq "cp950") {
        if (-not $cp950Succeeded) {
            return [pscustomobject]@{
                succeeded = $false
                text = ""
                encoding = ""
                error = "native_output_invalid_cp950"
            }
        }
        return [pscustomobject]@{
            succeeded = $true
            text = $cp950Text
            encoding = "cp950"
            error = ""
        }
    }

    if ($utf8Succeeded -and $cp950Succeeded) {
        if (-not [string]::Equals(
            $utf8Text,
            $cp950Text,
            [System.StringComparison]::Ordinal
        )) {
            return [pscustomobject]@{
                succeeded = $false
                text = ""
                encoding = ""
                error = "native_output_encoding_ambiguous"
            }
        }
        return [pscustomobject]@{
            succeeded = $true
            text = $utf8Text
            encoding = "utf-8-and-cp950"
            error = ""
        }
    }
    if ($utf8Succeeded) {
        return [pscustomobject]@{
            succeeded = $true
            text = $utf8Text
            encoding = "utf-8"
            error = ""
        }
    }
    if ($cp950Succeeded) {
        return [pscustomobject]@{
            succeeded = $true
            text = $cp950Text
            encoding = "cp950"
            error = ""
        }
    }
    return [pscustomobject]@{
        succeeded = $false
        text = ""
        encoding = ""
        error = "native_output_not_utf8_or_cp950"
    }
}

function Invoke-CapturedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandPath,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [ValidateSet("utf-8", "cp950", "auto")]
        [string]$EncodingPolicy
    )

    $exitCode = 9009
    $invocationError = ""
    $contractError = ""
    $processStarted = $false
    $stdoutBytes = [byte[]]@()
    $stderrBytes = [byte[]]@()
    $process = $null
    $stdoutBuffer = $null
    $stderrBuffer = $null
    try {
        $processPath = $CommandPath
        $processArguments = @($Arguments)
        $extension = [System.IO.Path]::GetExtension($CommandPath).ToLowerInvariant()
        if ($extension -in @(".cmd", ".bat")) {
            $unsafeMetacharacterPattern = '[&|<>^%]'
            if ($CommandPath -match $unsafeMetacharacterPattern -or
                @($Arguments | Where-Object {
                    [string]$_ -match $unsafeMetacharacterPattern
                }).Count -gt 0) {
                $contractError = "native_cmd_argument_unsupported_metacharacter"
            }
        }
        if ([string]::IsNullOrWhiteSpace($contractError) -and
            $extension -in @(".cmd", ".bat")) {
            $processPath = if (-not [string]::IsNullOrWhiteSpace($env:COMSPEC)) {
                $env:COMSPEC
            }
            else {
                (Get-Command cmd.exe -CommandType Application -ErrorAction Stop).Source
            }
            $processArguments = @("/d", "/s", "/c", "call", $CommandPath) + @($Arguments)
        }

        if (-not [string]::IsNullOrWhiteSpace($contractError)) {
            throw [System.InvalidOperationException]::new($contractError)
        }
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $processPath
        $startInfo.Arguments = (
            @($processArguments | ForEach-Object {
                ConvertTo-WindowsCommandLineArgument -Argument ([string]$_)
            }) -join " "
        )
        $startInfo.WorkingDirectory = $WorkingDirectory
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $processStarted = $true
        $stdoutBuffer = New-Object System.IO.MemoryStream
        $stderrBuffer = New-Object System.IO.MemoryStream
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutBuffer)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrBuffer)
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        [System.Threading.Tasks.Task]::WaitAll(
            [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
        )
        $stdoutBytes = $stdoutBuffer.ToArray()
        $stderrBytes = $stderrBuffer.ToArray()
    }
    catch {
        if ([string]::IsNullOrWhiteSpace($contractError)) {
            $invocationError = $_.Exception.Message
        }
    }
    finally {
        if ($null -ne $stdoutBuffer) {
            $stdoutBuffer.Dispose()
        }
        if ($null -ne $stderrBuffer) {
            $stderrBuffer.Dispose()
        }
        if ($null -ne $process) {
            $process.Dispose()
        }
    }

    $stdoutResult = ConvertFrom-NativeBytes `
        -Bytes $stdoutBytes `
        -EncodingPolicy $EncodingPolicy
    $stderrResult = ConvertFrom-NativeBytes `
        -Bytes $stderrBytes `
        -EncodingPolicy $EncodingPolicy
    $stdout = $stdoutResult.text
    $stderr = $stderrResult.text
    if (-not [string]::IsNullOrWhiteSpace($invocationError)) {
        $stderr = (($stderr + [Environment]::NewLine + $invocationError).Trim())
    }
    $decodeErrors = @()
    if (-not $stdoutResult.succeeded) {
        $decodeErrors += "stdout:" + $stdoutResult.error
    }
    if (-not $stderrResult.succeeded) {
        $decodeErrors += "stderr:" + $stderrResult.error
    }
    return [pscustomobject]@{
        exit_code = $exitCode
        stdout = $stdout
        stderr = $stderr
        stdout_encoding = $stdoutResult.encoding
        stderr_encoding = $stderrResult.encoding
        decode_error = ($decodeErrors -join ",")
        contract_error = $contractError
        process_started = $processStarted
    }
}

function Test-NativeCaptureDecoded {
    param(
        [Parameter(Mandatory = $true)][object]$Result,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.ArrayList]$Reasons
    )
    if (-not [string]::IsNullOrWhiteSpace([string]$Result.contract_error)) {
        Add-BlockedReason -Reasons $Reasons -Reason ([string]$Result.contract_error)
        return $false
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$Result.decode_error)) {
        Add-BlockedReason -Reasons $Reasons -Reason $Reason
        return $false
    }
    return $true
}

function Resolve-ApplicationPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        return $null
    }
    $source = if ($command.PSObject.Properties["Source"]) {
        [string]$command.Source
    }
    else {
        [string]$command.Definition
    }
    if ([string]::IsNullOrWhiteSpace($source) -or
        -not (Test-Path -LiteralPath $source -PathType Leaf)) {
        return $null
    }
    return [System.IO.Path]::GetFullPath($source)
}

function Invoke-GitRead {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitPath,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )
    return Invoke-CapturedNative `
        -CommandPath $GitPath `
        -Arguments (@("-C", $RepositoryRoot) + $GitArguments) `
        -WorkingDirectory $RepositoryRoot `
        -EncodingPolicy "utf-8"
}

function ConvertTo-NormalizedRepository {
    param([AllowNull()][string]$Origin)
    if ([string]::IsNullOrWhiteSpace($Origin)) {
        return ""
    }
    $value = $Origin.Trim()
    if ($value -match '^(?i)https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$') {
        return $Matches[1]
    }
    if ($value -match '^(?i)(?:ssh://)?git@github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$') {
        return $Matches[1]
    }
    return ""
}

function Test-ExactRepository {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitPath,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedRepository,
        [Parameter(Mandatory = $true)]
        [string]$ReasonPrefix,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.ArrayList]$Reasons
    )

    if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_root_unavailable"
        return [pscustomobject]@{ branch = ""; head = "" }
    }

    $rootResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("rev-parse", "--show-toplevel")
    if (-not (Test-NativeCaptureDecoded -Result $rootResult `
        -Reason "${ReasonPrefix}_git_root_output_undecodable" -Reasons $Reasons)) {
        return [pscustomobject]@{ branch = ""; head = "" }
    }
    if ($rootResult.exit_code -ne 0) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_not_git_repository"
        return [pscustomobject]@{ branch = ""; head = "" }
    }
    $observedRoot = $rootResult.stdout.Trim()
    try {
        $normalizedObserved = [System.IO.Path]::GetFullPath($observedRoot).TrimEnd("\")
        $normalizedExpected = [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\")
    }
    catch {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_git_root_invalid"
        return [pscustomobject]@{ branch = ""; head = "" }
    }
    if (-not [string]::Equals(
        $normalizedObserved,
        $normalizedExpected,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_git_root_mismatch"
    }

    $originResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("remote", "get-url", "origin")
    $originDecoded = Test-NativeCaptureDecoded -Result $originResult `
        -Reason "${ReasonPrefix}_origin_output_undecodable" -Reasons $Reasons
    if ($originDecoded -and ($originResult.exit_code -ne 0 -or
        -not [string]::Equals(
            (ConvertTo-NormalizedRepository -Origin $originResult.stdout),
            $ExpectedRepository,
            [System.StringComparison]::Ordinal
        ))) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_origin_mismatch"
    }

    $branch = ""
    $branchResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("branch", "--show-current")
    $branchDecoded = Test-NativeCaptureDecoded -Result $branchResult `
        -Reason "${ReasonPrefix}_branch_output_undecodable" -Reasons $Reasons
    if ($branchDecoded -and
        ($branchResult.exit_code -ne 0 -or [string]::IsNullOrWhiteSpace($branchResult.stdout))) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_branch_unreadable"
    }
    elseif ($branchDecoded) {
        $branch = $branchResult.stdout.Trim()
    }

    $head = ""
    $headResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("rev-parse", "HEAD")
    $headDecoded = Test-NativeCaptureDecoded -Result $headResult `
        -Reason "${ReasonPrefix}_head_output_undecodable" -Reasons $Reasons
    if ($headDecoded -and
        ($headResult.exit_code -ne 0 -or
         $headResult.stdout.Trim() -notmatch '^[0-9a-fA-F]{40}$')) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_head_unreadable"
    }
    elseif ($headDecoded) {
        $head = $headResult.stdout.Trim().ToLowerInvariant()
    }

    $statusResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("status", "--porcelain=v1", "--untracked-files=all")
    $statusDecoded = Test-NativeCaptureDecoded -Result $statusResult `
        -Reason "${ReasonPrefix}_status_output_undecodable" -Reasons $Reasons
    if ($statusDecoded -and $statusResult.exit_code -ne 0) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_status_unreadable"
    }
    elseif ($statusDecoded -and -not [string]::IsNullOrWhiteSpace($statusResult.stdout)) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_worktree_dirty"
    }

    $stagedResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("diff", "--cached", "--name-only")
    $stagedDecoded = Test-NativeCaptureDecoded -Result $stagedResult `
        -Reason "${ReasonPrefix}_staged_output_undecodable" -Reasons $Reasons
    if ($stagedDecoded -and $stagedResult.exit_code -ne 0) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_staged_status_unreadable"
    }
    elseif ($stagedDecoded -and -not [string]::IsNullOrWhiteSpace($stagedResult.stdout)) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_staged_changes_present"
    }

    return [pscustomobject]@{ branch = $branch; head = $head }
}

function Get-JsonObject {
    param([Parameter(Mandatory = $true)][string]$JsonText)
    if ([string]::IsNullOrWhiteSpace($JsonText)) {
        throw "missing_json"
    }
    $value = $JsonText | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $value -or $value -is [System.Array] -or
        $value -is [string] -or $value -is [ValueType]) {
        throw "non_object_json"
    }
    return $value
}

function Get-ObjectProperty {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Test-TrueProperty {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )
    return (Get-ObjectProperty -Object $Object -Name $Name) -eq $true
}

function Test-AbsoluteExistingFile {
    param([AllowNull()][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [System.IO.Path]::IsPathRooted($Path)) {
        return $false
    }
    return Test-Path -LiteralPath $Path -PathType Leaf
}

function Test-JsonEvidenceFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$JsonLines
    )
    try {
        $text = [System.IO.File]::ReadAllText($Path)
        if ($JsonLines) {
            foreach ($line in @($text -split "\r?\n")) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    [void](Get-JsonObject -JsonText $line)
                }
            }
        }
        elseif (-not [string]::IsNullOrWhiteSpace($text)) {
            [void](Get-JsonObject -JsonText $text)
        }
        else {
            throw "empty_json"
        }
        return $true
    }
    catch {
        return $false
    }
}

function Inspect-OperatorState {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.ArrayList]$Reasons
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Add-BlockedReason -Reasons $Reasons -Reason "state_directory_unavailable"
        return
    }
    if (Test-Path -LiteralPath (Join-Path $Path "operator.lock") -PathType Leaf) {
        Add-BlockedReason -Reasons $Reasons -Reason "operator_lock_present"
    }
    if (Test-Path -LiteralPath (Join-Path $Path "pause.flag") -PathType Leaf) {
        Add-BlockedReason -Reasons $Reasons -Reason "pause_flag_present"
    }
    if (Test-Path -LiteralPath (Join-Path $Path "stop.flag") -PathType Leaf) {
        Add-BlockedReason -Reasons $Reasons -Reason "stop_flag_present"
    }
    foreach ($name in @("state.json", "heartbeat.json", "last_failure.json")) {
        $candidate = Join-Path $Path $name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if (-not (Test-JsonEvidenceFile -Path $candidate)) {
                Add-BlockedReason -Reasons $Reasons -Reason "state_evidence_invalid_or_unreadable"
            }
        }
    }
    foreach ($name in @(
        "dry_run_observations.jsonl",
        "processed_requests.jsonl",
        "operator.log"
    )) {
        $candidate = Join-Path $Path $name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if (-not (Test-JsonEvidenceFile -Path $candidate -JsonLines)) {
                Add-BlockedReason -Reasons $Reasons -Reason "state_evidence_invalid_or_unreadable"
            }
        }
    }
}

$blockedReasons = [System.Collections.ArrayList]::new()
$branch = ""
$head = ""
$bootstrapStatus = "NOT_RUN"
$reviewedPythonPath = ""
$reviewedGhPath = ""
$reviewedCodexPath = ""
$operatorSummary = $null
$operatorExitCode = $null
$operatorStderrSummary = ""
$operatorInvoked = $false

if ([string]::IsNullOrWhiteSpace($StateDir)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $ResolvedStateDir = ""
        Add-BlockedReason -Reasons $blockedReasons -Reason "state_directory_unavailable"
    }
    else {
        $ResolvedStateDir = Join-Path $env:LOCALAPPDATA "LocalAIWorkbench\BridgeOperator"
    }
}
else {
    try {
        $ResolvedStateDir = [System.IO.Path]::GetFullPath($StateDir)
    }
    catch {
        $ResolvedStateDir = $StateDir
        Add-BlockedReason -Reasons $blockedReasons -Reason "state_directory_invalid"
    }
}

$gitPath = Resolve-ApplicationPath -Name "git.exe"
if ([string]::IsNullOrWhiteSpace($gitPath)) {
    Add-BlockedReason -Reasons $blockedReasons -Reason "git_unavailable"
}
else {
    $repoEvidence = Test-ExactRepository `
        -GitPath $gitPath `
        -RepositoryRoot $ControlRepoRoot `
        -ExpectedRepository $ControlRepository `
        -ReasonPrefix "control_repository" `
        -Reasons $blockedReasons
    $branch = $repoEvidence.branch
    $head = $repoEvidence.head
}

if (-not [string]::IsNullOrWhiteSpace($ResolvedStateDir)) {
    Inspect-OperatorState -Path $ResolvedStateDir -Reasons $blockedReasons
}

if (-not (Test-Path -LiteralPath $BootstrapScript -PathType Leaf)) {
    Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_script_unavailable"
}
elseif (-not (Test-Path -LiteralPath $ControlRepoRoot -PathType Container)) {
    Add-BlockedReason -Reasons $blockedReasons -Reason "control_repository_root_unavailable"
}
else {
    $powerShellPath = Join-Path $PSHOME "powershell.exe"
    if (-not (Test-Path -LiteralPath $powerShellPath -PathType Leaf)) {
        $powerShellPath = Resolve-ApplicationPath -Name "powershell.exe"
    }
    if ([string]::IsNullOrWhiteSpace($powerShellPath)) {
        Add-BlockedReason -Reasons $blockedReasons -Reason "powershell_unavailable"
    }
    else {
        $bootstrapResult = Invoke-CapturedNative `
            -CommandPath $powerShellPath `
            -Arguments @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $BootstrapScript,
                "-RepoRoot", $ControlRepoRoot,
                "-Json"
            ) `
            -WorkingDirectory $ControlRepoRoot `
            -EncodingPolicy "cp950"
        $bootstrapDecoded = Test-NativeCaptureDecoded -Result $bootstrapResult `
            -Reason "bootstrap_output_undecodable" -Reasons $blockedReasons
        if ($bootstrapResult.exit_code -ne 0) {
            Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_process_failed"
        }
        if ($bootstrapDecoded) {
          try {
            $bootstrap = Get-JsonObject -JsonText $bootstrapResult.stdout
            $bootstrapStatus = [string](Get-ObjectProperty -Object $bootstrap -Name "overall_status")
            $bootstrapBlockers = @(Get-ObjectProperty -Object $bootstrap -Name "blockers")
            $bootstrapAttention = @(Get-ObjectProperty -Object $bootstrap -Name "attention")
            $bootstrapManual = @(Get-ObjectProperty -Object $bootstrap -Name "manual_actions_required")
            if (-not [string]::Equals(
                $bootstrapStatus,
                "READY",
                [System.StringComparison]::Ordinal
            )) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_not_ready"
            }
            if ($bootstrapBlockers.Count -gt 0) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_blockers_present"
            }
            if ($bootstrapAttention.Count -gt 0) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_attention_present"
            }
            if ($bootstrapManual.Count -gt 0) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_manual_actions_present"
            }

            $venv = Get-ObjectProperty -Object $bootstrap -Name "venv"
            $dependencies = Get-ObjectProperty -Object $bootstrap -Name "dependencies"
            $detected = Get-ObjectProperty -Object $bootstrap -Name "detected"
            $gh = Get-ObjectProperty -Object $detected -Name "gh"
            $codex = Get-ObjectProperty -Object $detected -Name "codex"

            $reviewedPythonPath = [string](Get-ObjectProperty -Object $venv -Name "python")
            $reviewedGhPath = [string](Get-ObjectProperty -Object $gh -Name "path")
            $reviewedCodexPath = [string](Get-ObjectProperty -Object $codex -Name "path")

            if (-not (Test-TrueProperty -Object $venv -Name "pip_ready") -or
                -not (Test-TrueProperty -Object $dependencies -Name "ready") -or
                -not (Test-AbsoluteExistingFile -Path $reviewedPythonPath)) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "reviewed_python_not_ready"
            }
            if (-not (Test-TrueProperty -Object $gh -Name "ready") -or
                -not (Test-TrueProperty -Object $gh -Name "authenticated") -or
                -not (Test-AbsoluteExistingFile -Path $reviewedGhPath)) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "reviewed_gh_not_ready_or_authenticated"
            }
            if (-not (Test-TrueProperty -Object $codex -Name "command_usable") -or
                -not (Test-TrueProperty -Object $codex -Name "ready") -or
                -not (Test-AbsoluteExistingFile -Path $reviewedCodexPath)) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "reviewed_codex_not_ready"
            }
          }
          catch {
            $bootstrapStatus = "INVALID_JSON"
            Add-BlockedReason -Reasons $blockedReasons -Reason "bootstrap_json_invalid_or_missing"
          }
        }
    }
}

if (-not ($Repository -in $SupportedRepositories)) {
    Add-BlockedReason -Reasons $blockedReasons -Reason "unsupported_target_repository"
}

$ResolvedTargetRepoRoot = ""
if ([string]::Equals($Repository, $ControlRepository, [System.StringComparison]::Ordinal)) {
    $ResolvedTargetRepoRoot = $ControlRepoRoot
}
elseif ([string]::Equals($Repository, $HagRepository, [System.StringComparison]::Ordinal)) {
    if ([string]::IsNullOrWhiteSpace($TargetRepoRoot)) {
        Add-BlockedReason -Reasons $blockedReasons -Reason "target_repo_root_required"
    }
    else {
        try {
            $ResolvedTargetRepoRoot = [System.IO.Path]::GetFullPath($TargetRepoRoot).TrimEnd("\")
        }
        catch {
            Add-BlockedReason -Reasons $blockedReasons -Reason "target_repo_root_invalid"
        }
        if (-not [string]::IsNullOrWhiteSpace($ResolvedTargetRepoRoot) -and
            -not [string]::IsNullOrWhiteSpace($gitPath)) {
            [void](Test-ExactRepository `
                -GitPath $gitPath `
                -RepositoryRoot $ResolvedTargetRepoRoot `
                -ExpectedRepository $Repository `
                -ReasonPrefix "target_repository" `
                -Reasons $blockedReasons)
        }
    }
}

if ($StartForeground -and $blockedReasons.Count -eq 0) {
    $operatorArguments = @(
        "-m", "local_runner_bridge.bridge_operator_b3_cli",
        "--repo-root", $ControlRepoRoot,
        "--repo", $Repository,
        "--max-cycles", [string]$MaxCycles,
        "--poll-interval-seconds", [string]$PollIntervalSeconds,
        "--mode", "b3c-run-reviewbundle",
        "--state-dir", $ResolvedStateDir,
        "--timeout-seconds", [string]$TimeoutSeconds
    )
    if ([string]::Equals($Repository, $HagRepository, [System.StringComparison]::Ordinal)) {
        $operatorArguments += @("--target-repo-root", $ResolvedTargetRepoRoot)
    }

    $previousPath = $env:PATH
    $previousPythonPath = $env:PYTHONPATH
    try {
        $runtimeDirectories = @(
            (Split-Path -Parent $reviewedPythonPath),
            (Split-Path -Parent $reviewedGhPath),
            (Split-Path -Parent $reviewedCodexPath)
        ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -Unique
        $env:PATH = (@($runtimeDirectories) + @($previousPath) -join ";")
        $srcPath = Join-Path $ControlRepoRoot "src"
        $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
            $srcPath
        }
        else {
            $srcPath + ";" + $previousPythonPath
        }

        $operatorResult = Invoke-CapturedNative `
            -CommandPath $reviewedPythonPath `
            -Arguments $operatorArguments `
            -WorkingDirectory $ControlRepoRoot `
            -EncodingPolicy "utf-8"
        $operatorInvoked = $operatorResult.process_started
        $operatorExitCode = $operatorResult.exit_code
        $operatorStderrSummary = Get-SafeStderrSummary -Text $operatorResult.stderr
        $operatorDecoded = Test-NativeCaptureDecoded -Result $operatorResult `
            -Reason "operator_output_undecodable" -Reasons $blockedReasons
        if ($operatorDecoded) {
            try {
                $operatorSummary = Get-JsonObject -JsonText $operatorResult.stdout
            }
            catch {
                Add-BlockedReason -Reasons $blockedReasons -Reason "operator_json_invalid_or_missing"
            }
        }
        if ($operatorResult.exit_code -ne 0) {
            Add-BlockedReason -Reasons $blockedReasons -Reason "operator_process_failed"
        }
        if ($null -ne $operatorSummary -and
            -not [string]::Equals(
                [string](Get-ObjectProperty -Object $operatorSummary -Name "result"),
                "success",
                [System.StringComparison]::Ordinal
            )) {
            Add-BlockedReason -Reasons $blockedReasons -Reason "operator_reported_blocked"
        }
    }
    finally {
        $env:PATH = $previousPath
        $env:PYTHONPATH = $previousPythonPath
    }
}

$result = if ($blockedReasons.Count -gt 0) {
    "blocked"
}
elseif ($StartForeground) {
    "completed"
}
else {
    "ready"
}
$phase = if ($operatorInvoked) { "operator" } else { "preflight" }
$nextAction = if ($result -eq "ready") {
    "Review this preflight evidence, then explicitly use -StartForeground for one bounded foreground run."
}
elseif ($result -eq "completed") {
    "Review the retained Bridge Operator child summary."
}
else {
    "Review blocked_reasons and repair manually outside this launcher before retrying."
}

$summary = [ordered]@{
    protocol = $Protocol
    result = $result
    phase = $phase
    launch_requested = [bool]$StartForeground
    operator_invoked = $operatorInvoked
    repository = $Repository
    repo_root = $ControlRepoRoot
    target_repo_root = $ResolvedTargetRepoRoot
    branch = $branch
    head = $head
    state_dir = $ResolvedStateDir
    bootstrap_status = $bootstrapStatus
    blocked_reasons = @($blockedReasons)
    next_recommended_action = $nextAction
    reviewed_python_path = $reviewedPythonPath
    reviewed_gh_path = $reviewedGhPath
    reviewed_codex_path = $reviewedCodexPath
    operator_exit_code = $operatorExitCode
    operator_stderr_summary = $operatorStderrSummary
    operator_summary = $operatorSummary
    path_binding_scope = "process_only"
    manual_poll_once_is_recovery = $true
    background_service_started = $false
    dispatcher_invoked_directly = $false
    runner_invoked_directly = $false
    codex_invoked_directly = $false
    github_write_performed_directly = $false
    path_persisted = $false
    authentication_repair_performed = $false
    install_performed = $false
    commit_performed = $false
    push_performed = $false
    pr_created = $false
    merge_performed = $false
}

$summaryJson = $summary | ConvertTo-Json -Depth 100 -Compress
$summaryBytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes(
    $summaryJson + [Environment]::NewLine
)
[void][Console]::OpenStandardOutput().Write($summaryBytes, 0, $summaryBytes.Length)
if ($result -eq "blocked") {
    exit 2
}
exit 0
