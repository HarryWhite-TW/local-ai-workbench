param(
    [string]$TaskPacketFile,
    [int]$IssueNumber = 0,
    [switch]$ReadTaskPacketFromGitHub,
    [switch]$PostResultComment
)

$ErrorActionPreference = "Stop"
$ExpectedRepo = "HarryWhite-TW/local-ai-workbench"
$ExpectedSchema = "lawb.bridge_task_packet.v1"
$ResultSchema = "lawb.bridge_result_packet.v1"
$TaskMarker = "BRIDGE-TASK-PACKET protocol=$ExpectedSchema"
$ResultMarker = "BRIDGE-RESULT-PACKET protocol=$ResultSchema"

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Get-PropertyText {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) {
        return ""
    }
    return [string]$property.Value
}

function Assert-SafetyFlag {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Safety,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $property = $Safety.PSObject.Properties[$Name]
    Assert-True -Condition ($null -ne $property) -Message "Missing safety flag: $Name"
    Assert-True -Condition ([bool]$property.Value) -Message "Safety flag must be true: $Name"
}

function Assert-NoUnsafeCommandFields {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Command
    )

    $forbiddenFields = @(
        "shell",
        "args",
        "script",
        "command_text",
        "powershell",
        "bash",
        "cmd",
        "exec",
        "path"
    )

    foreach ($field in $forbiddenFields) {
        if ($null -ne $Command.PSObject.Properties[$field]) {
            throw "Unsupported unsafe command field: $field"
        }
    }
}

function Invoke-GitReadOnly {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $output = & git @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE`: $($output -join "`n")"
    }
    return (($output | ForEach-Object { [string]$_ }) -join "`n").TrimEnd()
}

function Get-BoundedText {
    param(
        [AllowNull()]
        [string]$Text,
        [int]$MaxChars = 2000
    )

    if ($null -eq $Text) {
        return ""
    }
    if ($Text.Length -le $MaxChars) {
        return $Text
    }
    return $Text.Substring(0, $MaxChars) + "`n[truncated]"
}

function Invoke-LocalGitStatusSummary {
    $statusShort = Invoke-GitReadOnly -GitArgs @("status", "--short") -Action "git status --short"
    $branch = Invoke-GitReadOnly -GitArgs @("branch", "--show-current") -Action "git branch --show-current"
    $head = Invoke-GitReadOnly -GitArgs @("rev-parse", "HEAD") -Action "git rev-parse HEAD"
    $originMaster = Invoke-GitReadOnly -GitArgs @("rev-parse", "origin/master") -Action "git rev-parse origin/master"

    return [ordered]@{
        kind = "local-git-status-summary"
        branch = $branch
        head = $head
        origin_master = $originMaster
        git_status_short = Get-BoundedText -Text $statusShort
        is_clean = [string]::IsNullOrWhiteSpace($statusShort)
    }
}

function ConvertFrom-TaskPacketJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JsonText,
        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    try {
        return $JsonText | ConvertFrom-Json
    }
    catch {
        throw "Malformed BRIDGE-TASK-PACKET JSON in ${SourceName}: $($_.Exception.Message)"
    }
}

function Get-TaskPacketFromText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,
        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    $lines = $Text -split "`r?`n"
    $packets = @()

    for ($index = 0; $index -lt $lines.Count; $index += 1) {
        if ($lines[$index].Trim() -ne $TaskMarker) {
            continue
        }

        $jsonLines = New-Object System.Collections.Generic.List[string]
        for ($jsonIndex = $index + 1; $jsonIndex -lt $lines.Count; $jsonIndex += 1) {
            $jsonLines.Add($lines[$jsonIndex])
            $jsonText = ($jsonLines -join "`n").Trim()
            if ([string]::IsNullOrWhiteSpace($jsonText)) {
                continue
            }

            try {
                $packet = $jsonText | ConvertFrom-Json
                $packets += [pscustomobject]@{
                    SourceName = $SourceName
                    Packet = $packet
                }
                break
            }
            catch {
                if ($jsonIndex -eq ($lines.Count - 1)) {
                    throw "Malformed BRIDGE-TASK-PACKET JSON in ${SourceName}: $($_.Exception.Message)"
                }
            }
        }

        if ($index -eq ($lines.Count - 1)) {
            throw "Malformed BRIDGE-TASK-PACKET in ${SourceName}: marker is not followed by JSON."
        }
    }

    return @($packets)
}

function Get-TaskPacketFromGitHubIssue {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Issue
    )

    $issueJson = & gh issue view $Issue --repo $ExpectedRepo --json number,state,title,url,body,comments
    if ($LASTEXITCODE -ne 0) {
        throw "gh issue view failed for issue #${Issue}."
    }

    try {
        $issueData = $issueJson | ConvertFrom-Json
    }
    catch {
        throw "gh issue view returned invalid JSON for issue #${Issue}: $($_.Exception.Message)"
    }

    $packets = @()
    if ($null -ne $issueData.body -and -not [string]::IsNullOrWhiteSpace([string]$issueData.body)) {
        $packets += Get-TaskPacketFromText -Text ([string]$issueData.body) -SourceName "issue #${Issue} body"
    }

    $commentIndex = 0
    foreach ($comment in @($issueData.comments)) {
        $commentIndex += 1
        if ($null -eq $comment.body -or [string]::IsNullOrWhiteSpace([string]$comment.body)) {
            continue
        }
        $packets += Get-TaskPacketFromText -Text ([string]$comment.body) -SourceName "issue #${Issue} comment ${commentIndex}"
    }

    if (@($packets).Count -eq 0) {
        throw "No BRIDGE-TASK-PACKET found on issue #${Issue}."
    }
    if (@($packets).Count -gt 1) {
        throw "Multiple BRIDGE-TASK-PACKET entries found on issue #${Issue}; exactly one is required."
    }

    return $packets[0].Packet
}

function Assert-TaskPacketCurrent {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Task
    )

    $expiresText = Get-PropertyText -Object $Task -Name "expires_utc"
    if ([string]::IsNullOrWhiteSpace($expiresText)) {
        throw "GitHub BRIDGE-TASK-PACKET must include expires_utc."
    }

    try {
        $expires = [DateTime]::ParseExact(
            $expiresText,
            "yyyyMMddTHHmmssZ",
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal
        ).ToUniversalTime()
    }
    catch {
        throw "expires_utc value '$expiresText' is malformed; expected yyyyMMddTHHmmssZ."
    }

    Assert-True -Condition ($expires -gt [DateTime]::UtcNow) -Message "BRIDGE-TASK-PACKET is stale; expires_utc=$expiresText."
}

if ($ReadTaskPacketFromGitHub) {
    Assert-True -Condition ([string]::IsNullOrWhiteSpace($TaskPacketFile)) -Message "Use either -TaskPacketFile or -ReadTaskPacketFromGitHub, not both."
    Assert-True -Condition ($IssueNumber -gt 0) -Message "-ReadTaskPacketFromGitHub requires -IssueNumber <N>."
    $task = Get-TaskPacketFromGitHubIssue -Issue $IssueNumber
    Assert-TaskPacketCurrent -Task $task
}
else {
    Assert-True -Condition (-not [string]::IsNullOrWhiteSpace($TaskPacketFile)) -Message "-TaskPacketFile is required unless -ReadTaskPacketFromGitHub is used."
    $resolvedTaskPacket = Resolve-Path -LiteralPath $TaskPacketFile
    $taskJson = Get-Content -LiteralPath $resolvedTaskPacket.Path -Raw
    $task = ConvertFrom-TaskPacketJson -JsonText $taskJson -SourceName $resolvedTaskPacket.Path
}

Assert-True -Condition ((Get-PropertyText -Object $task -Name "schema") -eq $ExpectedSchema) -Message "Unsupported task packet schema."
Assert-True -Condition ((Get-PropertyText -Object $task -Name "repo") -eq $ExpectedRepo) -Message "Task packet repo mismatch."
if ($ReadTaskPacketFromGitHub) {
    Assert-True -Condition ([int]$task.issue -eq $IssueNumber) -Message "Task packet issue mismatch."
}
Assert-True -Condition ((Get-PropertyText -Object $task -Name "requested_by") -eq "chatgpt") -Message "Task packet must be requested_by=chatgpt."
Assert-True -Condition ((Get-PropertyText -Object $task -Name "task_role") -eq "core") -Message "Task packet must be task_role=core."
Assert-True -Condition ([bool]$task.manual_copy_paste_is_target -eq $false) -Message "Manual copy/paste must not be target workflow."
Assert-NoUnsafeCommandFields -Command $task.command
Assert-True -Condition ([int]$task.command.timeout_seconds -le 30) -Message "timeout_seconds must be <= 30."

foreach ($flag in @(
    "foreground_manual_start_only",
    "no_background_watcher",
    "no_always_on_polling",
    "no_stage",
    "no_commit",
    "no_push",
    "no_issue_close",
    "no_label",
    "no_pr",
    "no_merge",
    "no_approval_chaining",
    "no_real_codex_code_modification"
)) {
    Assert-SafetyFlag -Safety $task.safety -Name $flag
}

$action = Get-PropertyText -Object $task -Name "action"
$commandKind = Get-PropertyText -Object $task.command -Name "kind"
$summary = ""
$dryActionOutput = $null
$commandResult = $null

if ($action -eq "bounded-dry-echo") {
    Assert-True -Condition ($commandKind -eq "local-dry-action") -Message "bounded-dry-echo requires command.kind=local-dry-action."
    $message = Get-PropertyText -Object $task.command -Name "message"
    if ([string]::IsNullOrWhiteSpace($message)) {
        $message = "local relay readback smoke"
    }
    $summary = "Local relay read the task packet, executed a harmless bounded dry action, and produced this result packet."
    $dryActionOutput = $message
}
elseif ($action -eq "bounded-local-command") {
    Assert-True -Condition ($commandKind -eq "local-git-status-summary") -Message "bounded-local-command supports only command.kind=local-git-status-summary."
    $summary = "Local relay read the task packet, executed one allowlisted read-only git status summary command, and produced this result packet."
    $commandResult = Invoke-LocalGitStatusSummary
}
else {
    throw "Unsupported action: $action"
}

$result = [ordered]@{
    schema = $ResultSchema
    packet_id = "$($task.packet_id)-result"
    task_packet_id = [string]$task.packet_id
    repo = [string]$task.repo
    issue = [int]$task.issue
    result = "success"
    action = [string]$task.action
    summary = $summary
    writeback_surface = "github_issue_comment"
    chatgpt_readback_path = "ChatGPT reads BRIDGE-RESULT-PACKET from the GitHub issue comment."
    remaining_user_actions = @(
        "User manually starts the foreground relay until a direct ChatGPT-triggered relay exists.",
        "User makes key approval decisions through ChatGPT."
    )
    safety = [ordered]@{
        foreground_manual_start_only = $true
        no_background_watcher = $true
        no_always_on_polling = $true
        no_stage = $true
        no_commit = $true
        no_push = $true
        no_issue_close = $true
        no_label = $true
        no_pr = $true
        no_merge = $true
        no_approval_chaining = $true
        no_real_codex_code_modification = $true
    }
    next_recommended_action = "chatgpt_review"
}

if ($null -ne $dryActionOutput) {
    $result["dry_action_output"] = $dryActionOutput
}
if ($null -ne $commandResult) {
    $result["command_result"] = $commandResult
}

$resultJson = $result | ConvertTo-Json -Depth 8
$packetText = "$ResultMarker`n$resultJson"

Write-Output $packetText

if ($PostResultComment) {
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($tmp, $packetText, $utf8NoBom)
        gh issue comment ([int]$task.issue) --repo $ExpectedRepo --body-file $tmp | Out-Host
    }
    finally {
        if (Test-Path -LiteralPath $tmp) {
            Remove-Item -LiteralPath $tmp -Force
        }
    }
}
