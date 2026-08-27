<#
.SYNOPSIS
Runs the canonical Bridge Operator B3-C preflight and, only when explicitly
requested, starts one bounded foreground B3-C process.

.DESCRIPTION
The default invocation is preflight-only. It does not read control relay #279 or invoke
Bridge Operator, Dispatcher, Runner, Codex, or a GitHub write path.

.EXAMPLE
.\scripts\start_bridge_operator_b3c.ps1

.EXAMPLE
.\scripts\start_bridge_operator_b3c.ps1 -StartForeground -MaxCycles 1 -PollIntervalSeconds 0
#>

[CmdletBinding()]
param(
    [switch]$StartForeground,
    [switch]$PublishStatus,
    [ValidateSet(
        "HarryWhite-TW/local-ai-workbench",
        "HarryWhite-TW/human-approval-automation-gateway"
    )]
    [string]$Repository = "HarryWhite-TW/local-ai-workbench",
    [string]$TargetRepoRoot = "",
    [ValidateRange(1, 960)]
    [int]$MaxCycles = 1,
    [ValidateRange(0, 3600)]
    [double]$PollIntervalSeconds = 0,
    [ValidateRange(1, 86400)]
    [int]$TimeoutSeconds = 600,
    [string]$StateDir = "",
    [long]$ContinuationIssueNumber = 0,
    [string]$ExpectedState = "",
    [string]$ExpectedCandidateManifestFingerprint = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Protocol = "lawb.bridge_operator_b3c_launcher.v1"
$ControlRepository = "HarryWhite-TW/local-ai-workbench"
$HagRepository = "HarryWhite-TW/human-approval-automation-gateway"
$SupportedRepositories = @($ControlRepository, $HagRepository)
$StatusProtocol = "lawb.bridge_status.v1"
$StatusMarker = "LAWBRIDGE-STATUS"
$StatusHostname = "github.com"
$StatusCreateEndpoint = "repos/HarryWhite-TW/local-ai-workbench/issues/279/comments"
$StatusUpdateEndpointPrefix = "repos/HarryWhite-TW/local-ai-workbench/issues/comments"
$SameNodeContinuationExpectedStatePrefix = "same_node_exact_candidate_continuation_v1:parent_comment_id="
$SameNodeContinuationProtocol = "lawb.same_node_exact_candidate_continuation.v1"
$RunnerResultMarker = "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1"
$CandidateEvidenceProfile = "local_git_candidate_observation.v1"
$ReviewCandidateFilename = "review_candidate.json"
$ReviewCandidateProtocol = "lawb.bridge_operator_review_candidate.v1"
$ReviewCandidateSchemaVersion = 2
$LegacyReviewCandidateSchemaVersion = 1
$TrustedContinuationAuthors = @("HarryWhite-TW")
$ProcessTreeTerminationTimeoutMilliseconds = 3000
$CleanupCommandKillWaitMilliseconds = 1000
$PostTerminationWaitTimeoutMilliseconds = 2000
$StreamDrainTimeoutMilliseconds = 3000
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

function Stop-NativeProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetProcessId
    )
    $cleanupTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $treeEvidenceId = New-NativeProcessTreeEvidence `
        -TargetProcessId $TargetProcessId
    $taskkillPath = Join-Path ([System.Environment]::SystemDirectory) "taskkill.exe"
    $taskkill = $null
    if (Test-Path -LiteralPath $taskkillPath -PathType Leaf) {
        try {
            $startInfo = New-Object System.Diagnostics.ProcessStartInfo
            $startInfo.FileName = $taskkillPath
            $startInfo.Arguments = (
                "/PID " + [string]$TargetProcessId + " /T /F"
            )
            $startInfo.UseShellExecute = $false
            $startInfo.CreateNoWindow = $true
            $startInfo.RedirectStandardOutput = $true
            $startInfo.RedirectStandardError = $true

            $taskkill = New-Object System.Diagnostics.Process
            $taskkill.StartInfo = $startInfo
            [void]$taskkill.Start()
            $taskkillWaitMilliseconds = [Math]::Max(
                0,
                $ProcessTreeTerminationTimeoutMilliseconds -
                    [int]$cleanupTimer.ElapsedMilliseconds
            )
            if ($taskkillWaitMilliseconds -le 0 -or
                -not $taskkill.WaitForExit($taskkillWaitMilliseconds)) {
                try {
                    $taskkill.Kill()
                }
                catch {
                }
                $cleanupCommandWaitMilliseconds = [Math]::Min(
                    $CleanupCommandKillWaitMilliseconds,
                    [Math]::Max(
                        0,
                        $ProcessTreeTerminationTimeoutMilliseconds -
                            [int]$cleanupTimer.ElapsedMilliseconds
                    )
                )
                if ($cleanupCommandWaitMilliseconds -gt 0) {
                    [void]$taskkill.WaitForExit($cleanupCommandWaitMilliseconds)
                }
            }
        }
        catch {
        }
        finally {
            if ($null -ne $taskkill) {
                $taskkill.Dispose()
            }
        }
    }
    $fallbackTimeoutMilliseconds = [Math]::Max(
        0,
        $ProcessTreeTerminationTimeoutMilliseconds -
            [int]$cleanupTimer.ElapsedMilliseconds
    )
    try {
        if ([string]::IsNullOrWhiteSpace([string]$treeEvidenceId)) {
            return $false
        }
        return Stop-NativeProcessTreeWithToolhelp `
            -EvidenceId $treeEvidenceId `
            -TimeoutMilliseconds $fallbackTimeoutMilliseconds
    }
    finally {
        if (-not [string]::IsNullOrWhiteSpace([string]$treeEvidenceId)) {
            [B3CLauncherProcessTree]::Release($treeEvidenceId)
        }
    }
}

function New-NativeProcessTreeEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetProcessId
    )
    try {
        if ($null -eq ("B3CLauncherProcessTree" -as [type])) {
            Add-Type -Language CSharp -ErrorAction Stop -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

public static class B3CLauncherProcessTree
{
    private const uint SnapshotProcesses = 0x00000002;
    private const uint ProcessTerminate = 0x00000001;
    private const uint Synchronize = 0x00100000;
    private const uint WaitObject0 = 0x00000000;
    private const int PerProcessWaitMilliseconds = 250;
    private static readonly IntPtr InvalidHandle = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct ProcessEntry
    {
        public uint Size;
        public uint UsageCount;
        public uint ProcessId;
        public IntPtr DefaultHeapId;
        public uint ModuleId;
        public uint ThreadCount;
        public uint ParentProcessId;
        public int BasePriority;
        public uint Flags;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string ExecutableName;
    }

    private sealed class ProcessNode
    {
        public int ProcessId;
        public int ParentProcessId;
        public int Depth;
    }

    private sealed class ProcessSnapshot
    {
        public readonly Dictionary<int, int> ParentByProcess =
            new Dictionary<int, int>();
        public readonly Dictionary<int, List<int>> ChildrenByParent =
            new Dictionary<int, List<int>>();
    }

    private sealed class ProcessEvidence
    {
        public int ParentProcessId;
        public int Depth;
        public IntPtr Handle;
    }

    private sealed class ProcessSession
    {
        public int RootProcessId;
        public bool BindingFailed;
        public readonly Dictionary<int, ProcessEvidence> EvidenceByProcess =
            new Dictionary<int, ProcessEvidence>();
    }

    private static readonly object SessionLock = new object();
    private static readonly Dictionary<string, ProcessSession> Sessions =
        new Dictionary<string, ProcessSession>();

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(
        uint flags,
        uint processId
    );

    [DllImport(
        "kernel32.dll",
        CharSet = CharSet.Unicode,
        SetLastError = true
    )]
    private static extern bool Process32FirstW(
        IntPtr snapshot,
        ref ProcessEntry entry
    );

    [DllImport(
        "kernel32.dll",
        CharSet = CharSet.Unicode,
        SetLastError = true
    )]
    private static extern bool Process32NextW(
        IntPtr snapshot,
        ref ProcessEntry entry
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(
        uint desiredAccess,
        bool inheritHandle,
        uint processId
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool TerminateProcess(
        IntPtr process,
        uint exitCode
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(
        IntPtr handle,
        uint milliseconds
    );

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    private static ProcessSnapshot CaptureSnapshot()
    {
        var result = new ProcessSnapshot();
        IntPtr snapshot = CreateToolhelp32Snapshot(SnapshotProcesses, 0);
        if (snapshot == InvalidHandle)
        {
            throw new InvalidOperationException("process_snapshot_failed");
        }
        try
        {
            var entry = new ProcessEntry();
            entry.Size = (uint)Marshal.SizeOf(entry);
            if (!Process32FirstW(snapshot, ref entry))
            {
                throw new InvalidOperationException(
                    "process_snapshot_read_failed"
                );
            }
            do
            {
                int parentId = unchecked((int)entry.ParentProcessId);
                int processId = unchecked((int)entry.ProcessId);
                result.ParentByProcess[processId] = parentId;
                List<int> children;
                if (!result.ChildrenByParent.TryGetValue(
                    parentId,
                    out children
                ))
                {
                    children = new List<int>();
                    result.ChildrenByParent[parentId] = children;
                }
                children.Add(processId);
                entry.Size = (uint)Marshal.SizeOf(entry);
            }
            while (Process32NextW(snapshot, ref entry));
        }
        finally
        {
            CloseHandle(snapshot);
        }
        return result;
    }

    private static List<ProcessNode> SelectTree(
        int rootProcessId,
        ProcessSnapshot snapshot,
        Dictionary<int, ProcessEvidence> evidenceByProcess
    )
    {
        var result = new List<ProcessNode>();
        var pending = new Stack<ProcessNode>();
        var seen = new HashSet<int>();
        var expanded = new HashSet<int>();
        int rootParent;
        if (snapshot.ParentByProcess.TryGetValue(rootProcessId, out rootParent))
        {
            pending.Push(new ProcessNode {
                ProcessId = rootProcessId,
                ParentProcessId = rootParent,
                Depth = 0
            });
        }
        else
        {
            expanded.Add(rootProcessId);
            List<int> rootChildren;
            if (snapshot.ChildrenByParent.TryGetValue(
                rootProcessId,
                out rootChildren
            ))
            {
                foreach (int childId in rootChildren)
                {
                    pending.Push(new ProcessNode {
                        ProcessId = childId,
                        ParentProcessId = rootProcessId,
                        Depth = 1
                    });
                }
            }
        }
        foreach (KeyValuePair<int, ProcessEvidence> item in evidenceByProcess)
        {
            if (item.Value.Handle == IntPtr.Zero ||
                !expanded.Add(item.Key))
            {
                continue;
            }
            List<int> knownChildren;
            if (snapshot.ChildrenByParent.TryGetValue(
                item.Key,
                out knownChildren
            ))
            {
                foreach (int childId in knownChildren)
                {
                    pending.Push(new ProcessNode {
                        ProcessId = childId,
                        ParentProcessId = item.Key,
                        Depth = item.Value.Depth + 1
                    });
                }
            }
        }
        while (pending.Count > 0)
        {
            ProcessNode node = pending.Pop();
            if (!seen.Add(node.ProcessId))
            {
                continue;
            }
            result.Add(node);
            expanded.Add(node.ProcessId);
            List<int> children;
            if (snapshot.ChildrenByParent.TryGetValue(
                node.ProcessId,
                out children
            ))
            {
                foreach (int childId in children)
                {
                    pending.Push(new ProcessNode {
                        ProcessId = childId,
                        ParentProcessId = node.ProcessId,
                        Depth = node.Depth + 1
                    });
                }
            }
        }
        result.Sort(delegate(ProcessNode left, ProcessNode right) {
            int depthOrder = right.Depth.CompareTo(left.Depth);
            return depthOrder != 0
                ? depthOrder
                : left.ProcessId.CompareTo(right.ProcessId);
        });
        return result;
    }

    private static int RemainingMilliseconds(
        Stopwatch timer,
        int timeoutMilliseconds
    )
    {
        long remaining = (long)timeoutMilliseconds -
            timer.ElapsedMilliseconds;
        return remaining <= 0
            ? 0
            : (int)Math.Min(Int32.MaxValue, remaining);
    }

    private static bool IsExited(IntPtr handle)
    {
        return WaitForSingleObject(handle, 0) == WaitObject0;
    }

    private static void BindTree(
        ProcessSession session,
        List<ProcessNode> tree
    )
    {
        foreach (ProcessNode node in tree)
        {
            ProcessEvidence evidence;
            if (!session.EvidenceByProcess.TryGetValue(
                node.ProcessId,
                out evidence
            ))
            {
                evidence = new ProcessEvidence {
                    ParentProcessId = node.ParentProcessId,
                    Depth = node.Depth,
                    Handle = IntPtr.Zero
                };
                session.EvidenceByProcess[node.ProcessId] = evidence;
            }
            if (evidence.Handle == IntPtr.Zero)
            {
                evidence.Handle = OpenProcess(
                    ProcessTerminate | Synchronize,
                    false,
                    unchecked((uint)node.ProcessId)
                );
                if (evidence.Handle == IntPtr.Zero)
                {
                    session.BindingFailed = true;
                }
            }
        }
    }

    public static string Bind(int rootProcessId)
    {
        var session = new ProcessSession {
            RootProcessId = rootProcessId,
            BindingFailed = false
        };
        ProcessSnapshot snapshot = CaptureSnapshot();
        List<ProcessNode> tree = SelectTree(
            rootProcessId,
            snapshot,
            session.EvidenceByProcess
        );
        BindTree(session, tree);
        ProcessEvidence rootEvidence;
        if (!session.EvidenceByProcess.TryGetValue(
                rootProcessId,
                out rootEvidence
            ) ||
            rootEvidence.Handle == IntPtr.Zero)
        {
            session.BindingFailed = true;
        }
        string evidenceId = Guid.NewGuid().ToString("N");
        lock (SessionLock)
        {
            Sessions[evidenceId] = session;
        }
        return evidenceId;
    }

    public static bool TryTerminate(
        string evidenceId,
        int timeoutMilliseconds
    )
    {
        ProcessSession session;
        lock (SessionLock)
        {
            if (!Sessions.TryGetValue(evidenceId, out session))
            {
                return false;
            }
        }
        var timer = Stopwatch.StartNew();
        try
        {
            while (RemainingMilliseconds(timer, timeoutMilliseconds) > 0)
            {
                ProcessSnapshot snapshot = CaptureSnapshot();
                List<ProcessNode> tree = SelectTree(
                    session.RootProcessId,
                    snapshot,
                    session.EvidenceByProcess
                );
                BindTree(session, tree);

                foreach (ProcessNode node in tree)
                {
                    ProcessEvidence evidence =
                        session.EvidenceByProcess[node.ProcessId];
                    if (evidence.Handle == IntPtr.Zero ||
                        IsExited(evidence.Handle))
                    {
                        continue;
                    }
                    bool terminationRequested = TerminateProcess(
                        evidence.Handle,
                        1
                    );
                    if (!terminationRequested && !IsExited(evidence.Handle))
                    {
                        continue;
                    }
                    int remaining = RemainingMilliseconds(
                        timer,
                        timeoutMilliseconds
                    );
                    if (remaining <= 0)
                    {
                        break;
                    }
                    uint waitMilliseconds = unchecked((uint)Math.Min(
                        remaining,
                        PerProcessWaitMilliseconds
                    ));
                    WaitForSingleObject(
                        evidence.Handle,
                        waitMilliseconds
                    );
                }

                bool allBoundProcessesExited = true;
                foreach (
                    ProcessEvidence evidence in
                        session.EvidenceByProcess.Values
                )
                {
                    if (evidence.Handle != IntPtr.Zero &&
                        !IsExited(evidence.Handle))
                    {
                        allBoundProcessesExited = false;
                        break;
                    }
                }
                ProcessSnapshot verificationSnapshot = CaptureSnapshot();
                List<ProcessNode> remainingTree = SelectTree(
                    session.RootProcessId,
                    verificationSnapshot,
                    session.EvidenceByProcess
                );
                bool unverifiedProcessRemains = false;
                foreach (ProcessNode node in remainingTree)
                {
                    ProcessEvidence evidence;
                    if (!session.EvidenceByProcess.TryGetValue(
                            node.ProcessId,
                            out evidence
                        ) ||
                        evidence.Handle == IntPtr.Zero ||
                        !IsExited(evidence.Handle))
                    {
                        unverifiedProcessRemains = true;
                        break;
                    }
                }
                if (!session.BindingFailed &&
                    allBoundProcessesExited &&
                    !unverifiedProcessRemains)
                {
                    return true;
                }
                int sleepMilliseconds = Math.Min(
                    RemainingMilliseconds(timer, timeoutMilliseconds),
                    10
                );
                if (sleepMilliseconds > 0)
                {
                    System.Threading.Thread.Sleep(sleepMilliseconds);
                }
            }
            return false;
        }
        catch
        {
            return false;
        }
    }

    public static void Release(string evidenceId)
    {
        ProcessSession session = null;
        lock (SessionLock)
        {
            if (Sessions.TryGetValue(evidenceId, out session))
            {
                Sessions.Remove(evidenceId);
            }
        }
        if (session == null)
        {
            return;
        }
        foreach (
            ProcessEvidence evidence in session.EvidenceByProcess.Values
        )
        {
            if (evidence.Handle != IntPtr.Zero)
            {
                CloseHandle(evidence.Handle);
            }
        }
    }
}
'@
        }
        return [B3CLauncherProcessTree]::Bind($TargetProcessId)
    }
    catch {
        return ""
    }
}

function Stop-NativeProcessTreeWithToolhelp {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EvidenceId,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutMilliseconds
    )
    if ($TimeoutMilliseconds -le 0 -or
        [string]::IsNullOrWhiteSpace($EvidenceId)) {
        return $false
    }
    try {
        return [B3CLauncherProcessTree]::TryTerminate(
            $EvidenceId,
            $TimeoutMilliseconds
        )
    }
    catch {
        return $false
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
        [string]$EncodingPolicy,
        [ValidateRange(0, 86400)]
        [int]$ProcessTimeoutSeconds = 0,
        [AllowNull()][string]$StandardInputText = $null
    )

    $exitCode = 9009
    $invocationError = ""
    $contractError = ""
    $cleanupError = ""
    $processStarted = $false
    $timedOut = $false
    $processTreeTerminationAttempted = $false
    $processTreeTerminationSucceeded = $false
    $postKillWaitTimedOut = $false
    $streamDrainTimedOut = $false
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
        $startInfo.RedirectStandardInput = $null -ne $StandardInputText

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $processStarted = $true
        if ($null -ne $StandardInputText) {
            $stdinBytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes(
                $StandardInputText
            )
            $process.StandardInput.BaseStream.Write(
                $stdinBytes,
                0,
                $stdinBytes.Length
            )
            $process.StandardInput.Close()
        }
        $stdoutBuffer = New-Object System.IO.MemoryStream
        $stderrBuffer = New-Object System.IO.MemoryStream
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutBuffer)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrBuffer)
        if ($ProcessTimeoutSeconds -gt 0) {
            $completed = $process.WaitForExit($ProcessTimeoutSeconds * 1000)
            if (-not $completed) {
                $timedOut = $true
                $processTreeTerminationAttempted = $true
                $terminationCommandSucceeded = Stop-NativeProcessTree `
                    -TargetProcessId $process.Id
                $postKillCompleted = $process.WaitForExit(
                    $PostTerminationWaitTimeoutMilliseconds
                )
                $postKillWaitTimedOut = -not $postKillCompleted
                $processTreeTerminationSucceeded = (
                    $terminationCommandSucceeded -and $postKillCompleted
                )
                if (-not $processTreeTerminationSucceeded) {
                    $cleanupError = "native_process_tree_cleanup_unverified"
                }
            }
            if ($process.HasExited) {
                $exitCode = $process.ExitCode
            }
            $streamDrainCompleted = [System.Threading.Tasks.Task]::WaitAll(
                [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask),
                $StreamDrainTimeoutMilliseconds
            )
            $streamDrainTimedOut = -not $streamDrainCompleted
        }
        else {
            $process.WaitForExit()
            $exitCode = $process.ExitCode
            [System.Threading.Tasks.Task]::WaitAll(
                [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
            )
        }
        if (-not $streamDrainTimedOut) {
            $stdoutBytes = $stdoutBuffer.ToArray()
            $stderrBytes = $stderrBuffer.ToArray()
        }
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
        invocation_error = $invocationError
        cleanup_error = $cleanupError
        process_started = $processStarted
        timed_out = $timedOut
        process_tree_termination_attempted = $processTreeTerminationAttempted
        process_tree_termination_succeeded = $processTreeTerminationSucceeded
        post_kill_wait_timed_out = $postKillWaitTimedOut
        stream_drain_timed_out = $streamDrainTimedOut
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
        [System.Collections.ArrayList]$Reasons,
        [switch]$DeferWorktreeDirty
    )

    if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_root_unavailable"
        return [pscustomobject]@{ branch = ""; head = ""; status = ""; staged_paths = @() }
    }

    $rootResult = Invoke-GitRead -GitPath $GitPath -RepositoryRoot $RepositoryRoot `
        -GitArguments @("rev-parse", "--show-toplevel")
    if (-not (Test-NativeCaptureDecoded -Result $rootResult `
        -Reason "${ReasonPrefix}_git_root_output_undecodable" -Reasons $Reasons)) {
        return [pscustomobject]@{ branch = ""; head = ""; status = ""; staged_paths = @() }
    }
    if ($rootResult.exit_code -ne 0) {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_not_git_repository"
        return [pscustomobject]@{ branch = ""; head = ""; status = ""; staged_paths = @() }
    }
    $observedRoot = $rootResult.stdout.Trim()
    try {
        $normalizedObserved = [System.IO.Path]::GetFullPath($observedRoot).TrimEnd("\")
        $normalizedExpected = [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\")
    }
    catch {
        Add-BlockedReason -Reasons $Reasons -Reason "${ReasonPrefix}_git_root_invalid"
        return [pscustomobject]@{ branch = ""; head = ""; status = ""; staged_paths = @() }
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
    elseif ($statusDecoded -and
        -not [string]::IsNullOrWhiteSpace($statusResult.stdout) -and
        -not $DeferWorktreeDirty) {
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

    $stagedPaths = @()
    if ($stagedDecoded -and $stagedResult.exit_code -eq 0 -and
        -not [string]::IsNullOrWhiteSpace($stagedResult.stdout)) {
        $stagedPaths = @($stagedResult.stdout -split "`r?`n" | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_)
        })
    }

    return [pscustomobject]@{
        branch = $branch
        head = $head
        status = if ($statusDecoded -and $statusResult.exit_code -eq 0) {
            [string]$statusResult.stdout
        }
        else { "" }
        staged_paths = $stagedPaths
    }
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

function ConvertFrom-FirstJsonObjectAfterMarker {
    param(
        [Parameter(Mandatory = $true)][string]$Body,
        [Parameter(Mandatory = $true)][string]$Marker
    )

    $markerIndex = $Body.IndexOf($Marker, [System.StringComparison]::Ordinal)
    if ($markerIndex -lt 0) { throw "runner_result_marker_missing" }
    $start = $Body.IndexOf("{", $markerIndex + $Marker.Length)
    if ($start -lt 0) { throw "runner_result_json_missing" }
    $depth = 0
    $inString = $false
    $escaped = $false
    for ($index = $start; $index -lt $Body.Length; $index++) {
        $character = $Body[$index]
        if ($inString) {
            if ($escaped) { $escaped = $false }
            elseif ($character -eq "\") { $escaped = $true }
            elseif ($character -eq '"') { $inString = $false }
            continue
        }
        if ($character -eq '"') { $inString = $true; continue }
        if ($character -eq "{") { $depth += 1; continue }
        if ($character -eq "}") {
            $depth -= 1
            if ($depth -eq 0) {
                return $Body.Substring($start, $index - $start + 1) |
                    ConvertFrom-Json -ErrorAction Stop
            }
        }
    }
    throw "runner_result_json_unterminated"
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return -join @($sha256.ComputeHash($Bytes) | ForEach-Object {
            $_.ToString("x2")
        })
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-SameNodeContinuationParentCommentId {
    param([Parameter(Mandatory = $true)][string]$ExpectedStateValue)
    if (-not $ExpectedStateValue.StartsWith(
        $SameNodeContinuationExpectedStatePrefix,
        [System.StringComparison]::Ordinal
    )) {
        throw "same_node_continuation_expected_state_invalid"
    }
    $parentId = $ExpectedStateValue.Substring(
        $SameNodeContinuationExpectedStatePrefix.Length
    )
    if ($parentId -notmatch '^[1-9][0-9]{0,18}$') {
        throw "same_node_continuation_parent_comment_id_invalid"
    }
    return $parentId
}

function Get-SameNodeContinuationComment {
    param(
        [Parameter(Mandatory = $true)][string]$GhPath,
        [Parameter(Mandatory = $true)][string]$ParentCommentId,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][int]$ProcessTimeoutSeconds
    )
    $endpoint = "repos/$ControlRepository/issues/comments/$ParentCommentId"
    $readResult = Invoke-CapturedNative `
        -CommandPath $GhPath `
        -Arguments @(
            "api",
            "--hostname", $StatusHostname,
            "--method", "GET",
            $endpoint
        ) `
        -WorkingDirectory $WorkingDirectory `
        -EncodingPolicy "utf-8" `
        -ProcessTimeoutSeconds $ProcessTimeoutSeconds
    if (-not $readResult.process_started -or
        $readResult.exit_code -ne 0 -or
        $readResult.timed_out -or
        $readResult.stream_drain_timed_out -or
        -not [string]::IsNullOrWhiteSpace([string]$readResult.contract_error) -or
        -not [string]::IsNullOrWhiteSpace([string]$readResult.invocation_error) -or
        -not [string]::IsNullOrWhiteSpace([string]$readResult.cleanup_error) -or
        -not [string]::IsNullOrWhiteSpace([string]$readResult.decode_error)) {
        throw "same_node_continuation_parent_read_failed"
    }
    try {
        return Get-JsonObject -JsonText $readResult.stdout
    }
    catch {
        throw "same_node_continuation_parent_response_invalid"
    }
}

function Get-ExactDirtyPathsFromStatus {
    param([Parameter(Mandatory = $true)][string]$Status)
    $paths = [System.Collections.Generic.List[string]]::new()
    foreach ($line in @($Status -split "`r?`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })) {
        if ($line -notmatch '^ M ([A-Za-z0-9._/-]+)$') {
            throw "same_node_continuation_worktree_status_unsupported"
        }
        $path = [string]$Matches[1]
        if ($path.StartsWith("/", [System.StringComparison]::Ordinal) -or
            $path.Contains("\") -or $path.Contains("//") -or
            @($path.Split("/") | Where-Object { $_ -in @("", ".", "..") }).Count -gt 0) {
            throw "same_node_continuation_candidate_path_invalid"
        }
        $paths.Add($path)
    }
    return @($paths.ToArray() | Sort-Object -Unique)
}

function Assert-ExactReviewCandidateIdentity {
    <#
    .SYNOPSIS
    Verifies only immutable candidate identity.  This function neither reads
    continuation budget nor creates any execution admission.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][object]$RepositoryEvidence,
        [Parameter(Mandatory = $true)][object]$Comment,
        [Parameter(Mandatory = $true)][string]$ParentCommentId,
        [Parameter(Mandatory = $true)][long]$IssueNumber,
        [Parameter(Mandatory = $true)][string]$ExpectedManifestFingerprint
    )

    if ($IssueNumber -le 0) { throw "same_node_continuation_issue_invalid" }
    if ($ParentCommentId -notmatch '^[1-9][0-9]{0,18}$') {
        throw "same_node_continuation_parent_comment_id_invalid"
    }
    if ($ExpectedManifestFingerprint -cnotmatch '^[0-9a-f]{64}$') {
        throw "same_node_continuation_manifest_fingerprint_invalid"
    }
    if ([string]::IsNullOrWhiteSpace([string]$RepositoryEvidence.status)) {
        throw "same_node_continuation_requires_dirty_candidate"
    }
    if (@($RepositoryEvidence.staged_paths).Count -ne 0) {
        throw "same_node_continuation_staged_changes_present"
    }
    $dirtyPaths = @(Get-ExactDirtyPathsFromStatus -Status ([string]$RepositoryEvidence.status))
    $commentId = Get-ObjectProperty -Object $Comment -Name "id"
    $commentUser = Get-ObjectProperty -Object $Comment -Name "user"
    $commentAuthor = [string](Get-ObjectProperty -Object $commentUser -Name "login")
    $expectedIssueUrl = "https://api.github.com/repos/$ControlRepository/issues/$IssueNumber"
    if ([string]$commentId -cne $ParentCommentId) {
        throw "same_node_continuation_parent_id_mismatch"
    }
    if ($commentAuthor -notin $TrustedContinuationAuthors) {
        throw "same_node_continuation_parent_untrusted"
    }
    if (-not [string]::Equals(
        [string](Get-ObjectProperty -Object $Comment -Name "issue_url"),
        $expectedIssueUrl,
        [System.StringComparison]::Ordinal
    )) {
        throw "same_node_continuation_parent_issue_url_mismatch"
    }
    $parent = ConvertFrom-FirstJsonObjectAfterMarker `
        -Body ([string](Get-ObjectProperty -Object $Comment -Name "body")) `
        -Marker $RunnerResultMarker
    if ([string](Get-ObjectProperty -Object $parent -Name "schema") -cne "lawb.runner_result.v1" -or
        [string](Get-ObjectProperty -Object $parent -Name "repo") -cne $ControlRepository -or
        [long](Get-ObjectProperty -Object $parent -Name "issue") -ne $IssueNumber -or
        [long](Get-ObjectProperty -Object $parent -Name "selected_issue") -ne $IssueNumber -or
        [string](Get-ObjectProperty -Object $parent -Name "action") -cne "run-reviewbundle" -or
        [string](Get-ObjectProperty -Object $parent -Name "result") -cne "success" -or
        [string](Get-ObjectProperty -Object $parent -Name "branch") -cne [string]$RepositoryEvidence.branch -or
        [string](Get-ObjectProperty -Object $parent -Name "head") -cne [string]$RepositoryEvidence.head) {
        throw "same_node_continuation_parent_identity_mismatch"
    }
    if ([string](Get-ObjectProperty -Object $parent -Name "candidate_acceptance") -cne "eligible" -or
        [string](Get-ObjectProperty -Object $parent -Name "approval_token_semantics") -cne "candidate_review_snapshot_not_human_approval") {
        throw "same_node_continuation_parent_acceptance_invalid"
    }
    $binding = Get-ObjectProperty -Object $parent -Name "runtime_contract_binding"
    $contract = Get-ObjectProperty -Object $binding -Name "runtime_contract"
    if ([string](Get-ObjectProperty -Object $binding -Name "status") -cne "passed" -or
        (Get-ObjectProperty -Object $binding -Name "contract_present") -ne $true -or
        [string](Get-ObjectProperty -Object $contract -Name "repository") -cne $ControlRepository -or
        [long](Get-ObjectProperty -Object $contract -Name "logical_issue") -ne $IssueNumber -or
        [string](Get-ObjectProperty -Object $contract -Name "branch") -cne [string]$RepositoryEvidence.branch -or
        [string](Get-ObjectProperty -Object $contract -Name "expected_head") -cne [string]$RepositoryEvidence.head) {
        throw "same_node_continuation_runtime_contract_mismatch"
    }
    $manifest = Get-ObjectProperty -Object $parent -Name "candidate_evidence_manifest"
    $entries = @(Get-ObjectProperty -Object $manifest -Name "entries")
    $allowedFiles = @(Get-ObjectProperty -Object $contract -Name "allowed_files")
    if ([string](Get-ObjectProperty -Object $manifest -Name "status") -cne "verified" -or
        [string](Get-ObjectProperty -Object $manifest -Name "evidence_profile") -cne $CandidateEvidenceProfile -or
        $entries.Count -eq 0 -or $entries.Count -ne $allowedFiles.Count) {
        throw "same_node_continuation_parent_manifest_invalid"
    }
    $manifestLines = [System.Collections.Generic.List[string]]::new()
    $manifestPaths = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in $entries) {
        $path = [string](Get-ObjectProperty -Object $entry -Name "path")
        $state = [string](Get-ObjectProperty -Object $entry -Name "state")
        $expectedSha = [string](Get-ObjectProperty -Object $entry -Name "sha256")
        $expectedLength = Get-ObjectProperty -Object $entry -Name "length"
        if ($path -notmatch '^[A-Za-z0-9._/-]+$' -or
            $path.StartsWith("/", [System.StringComparison]::Ordinal) -or
            $path.Contains("\") -or $path.Contains("//") -or
            @($path.Split("/") | Where-Object { $_ -in @("", ".", "..") }).Count -gt 0 -or
            $state -cne "regular_file" -or $expectedSha -cnotmatch '^[0-9a-f]{64}$' -or
            -not ($expectedLength -is [int] -or $expectedLength -is [long]) -or
            [long]$expectedLength -lt 0 -or $manifestPaths.Contains($path)) {
            throw "same_node_continuation_parent_manifest_invalid"
        }
        $manifestPaths.Add($path)
        $filePath = Join-Path $RepositoryRoot ($path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            throw "same_node_continuation_candidate_manifest_mismatch"
        }
        $bytes = [System.IO.File]::ReadAllBytes($filePath)
        $actualSha = Get-Sha256Hex -Bytes $bytes
        if ($actualSha -cne $expectedSha -or $bytes.Length -ne [long]$expectedLength) {
            throw "same_node_continuation_candidate_manifest_mismatch"
        }
        $manifestLines.Add("$path|regular_file|$actualSha|$($bytes.Length)")
    }
    $sortedManifestPaths = @($manifestPaths.ToArray() | Sort-Object -Unique)
    $sortedAllowedFiles = @($allowedFiles | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    if ((@($sortedManifestPaths) -join "`n") -cne (@($sortedAllowedFiles) -join "`n") -or
        (@($manifestPaths.ToArray()) -join "`n") -cne (@($sortedManifestPaths) -join "`n")) {
        throw "same_node_continuation_parent_manifest_scope_mismatch"
    }
    $changedFiles = @(Get-ObjectProperty -Object $parent -Name "changed_files" | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    if ((@($dirtyPaths) -join "`n") -cne (@($changedFiles) -join "`n")) {
        throw "same_node_continuation_dirty_path_mismatch"
    }
    $payload = [string]::Join("`n", $manifestLines.ToArray())
    $observedFingerprint = Get-Sha256Hex -Bytes ([System.Text.Encoding]::UTF8.GetBytes($payload))
    if ([string](Get-ObjectProperty -Object $manifest -Name "payload") -cne $payload -or
        [string](Get-ObjectProperty -Object $manifest -Name "fingerprint") -cne $observedFingerprint -or
        $ExpectedManifestFingerprint -cne $observedFingerprint) {
        throw "same_node_continuation_candidate_manifest_mismatch"
    }
    $assurance = Get-ObjectProperty -Object $parent -Name "execution_assurance"
    if ([string](Get-ObjectProperty -Object $assurance -Name "candidate_manifest_fingerprint") -cne $observedFingerprint) {
        throw "same_node_continuation_execution_assurance_mismatch"
    }
    return [pscustomobject]@{ parent = $parent; candidate_manifest_fingerprint = $observedFingerprint }
}

function Test-SameNodeExactCandidateContinuation {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][object]$RepositoryEvidence,
        [Parameter(Mandatory = $true)][string]$GhPath,
        [Parameter(Mandatory = $true)][long]$IssueNumber,
        [Parameter(Mandatory = $true)][string]$ExpectedStateValue,
        [Parameter(Mandatory = $true)][string]$ExpectedManifestFingerprint,
        [Parameter(Mandatory = $true)][int]$ProcessTimeoutSeconds
    )

    $reasons = [System.Collections.Generic.List[string]]::new()
    $parentCommentId = ""
    $observedFingerprint = ""
    $remainingBudget = $null
    try {
        $parentCommentId = Get-SameNodeContinuationParentCommentId `
            -ExpectedStateValue $ExpectedStateValue
        $comment = Get-SameNodeContinuationComment `
            -GhPath $GhPath `
            -ParentCommentId $parentCommentId `
            -WorkingDirectory $RepositoryRoot `
            -ProcessTimeoutSeconds $ProcessTimeoutSeconds
        $identity = Assert-ExactReviewCandidateIdentity `
            -RepositoryRoot $RepositoryRoot `
            -RepositoryEvidence $RepositoryEvidence `
            -Comment $comment `
            -ParentCommentId $parentCommentId `
            -IssueNumber $IssueNumber `
            -ExpectedManifestFingerprint $ExpectedManifestFingerprint
        $parent = $identity.parent
        $observedFingerprint = [string]$identity.candidate_manifest_fingerprint

        $continuation = Get-ObjectProperty -Object $parent -Name "same_node_continuation"
        $remainingValue = Get-ObjectProperty -Object $continuation -Name "remaining_budget"
        if ([string](Get-ObjectProperty -Object $continuation -Name "protocol") -cne $SameNodeContinuationProtocol -or
            -not ($remainingValue -is [int] -or $remainingValue -is [long]) -or
            [long]$remainingValue -ne 1 -or
            (Get-ObjectProperty -Object $continuation -Name "is_human_approval") -ne $false) {
            throw "same_node_continuation_parent_budget_or_authority_invalid"
        }
        $remainingBudget = [long]$remainingValue

    }
    catch {
        $reason = [string]$_.Exception.Message
        if ([string]::IsNullOrWhiteSpace($reason) -or $reason -notmatch '^[a-z0-9_]+$') {
            $reason = "same_node_continuation_admission_failed"
        }
        $reasons.Add($reason)
    }

    return [pscustomobject]@{
        protocol = $SameNodeContinuationProtocol
        requested = $true
        admitted = ($reasons.Count -eq 0)
        issue = $IssueNumber
        parent_comment_id = $parentCommentId
        candidate_manifest_fingerprint = $observedFingerprint
        remaining_budget_before = $remainingBudget
        is_human_approval = $false
        reasons = @($reasons.ToArray())
    }
}

function Get-ReviewCandidateRecord {
    param([Parameter(Mandatory = $true)][string]$StateDirectory)

    $path = Join-Path $StateDirectory $ReviewCandidateFilename
    if (-not (Test-Path -LiteralPath $path)) {
        return [pscustomobject]@{ status = "not_present"; record = $null; reason = "" }
    }
    try {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "review_candidate_record_invalid"
        }
        $bytes = [System.IO.File]::ReadAllBytes($path)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xef -and
            $bytes[1] -eq 0xbb -and $bytes[2] -eq 0xbf) {
            throw "review_candidate_record_invalid"
        }
        $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $record = Get-JsonObject -JsonText $utf8.GetString($bytes)
        $names = @($record.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
        $commonNames = @(
            "action", "branch", "candidate_manifest_fingerprint", "dispatch_request_id",
            "expected_head", "protocol", "recorded_at_utc", "review_bundle_comment_id",
            "schema_version", "target_issue", "target_repository", "terminal_result_comment_id"
        )
        $expectedNames = if ($record.schema_version -eq $ReviewCandidateSchemaVersion) {
            @($commonNames) + @("target_repo_root")
        }
        else { @($commonNames) }
        if ((@($names) -join "`n") -cne (@($expectedNames | Sort-Object) -join "`n") -or
            [string]$record.protocol -cne $ReviewCandidateProtocol -or
            $record.schema_version -notin @(
                $LegacyReviewCandidateSchemaVersion,
                $ReviewCandidateSchemaVersion
            ) -or
            [string]$record.target_repository -notmatch '^.+$' -or
            -not ($record.target_issue -is [int] -or $record.target_issue -is [long]) -or
            [long]$record.target_issue -le 0 -or
            [string]$record.dispatch_request_id -notmatch '^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$' -or
            [string]$record.action -cne "run-reviewbundle" -or
            [string]$record.branch -notmatch '^.+$' -or
            [string]$record.expected_head -cnotmatch '^[0-9a-f]{40}$' -or
            [string]$record.terminal_result_comment_id -cnotmatch '^[1-9][0-9]{0,18}$' -or
            [string]$record.review_bundle_comment_id -cnotmatch '^[1-9][0-9]{0,18}$' -or
            [string]$record.candidate_manifest_fingerprint -cnotmatch '^[0-9a-f]{64}$' -or
            [string]$record.recorded_at_utc -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$') {
            throw "review_candidate_record_invalid"
        }
        if ($record.schema_version -eq $ReviewCandidateSchemaVersion -and
            -not (Test-FullyQualifiedLocalWindowsPath `
                -Path ([string]$record.target_repo_root))) {
            throw "review_candidate_record_invalid"
        }
        $parsedRecordedAt = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParse(
            [string]$record.recorded_at_utc,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal,
            [ref]$parsedRecordedAt
        )) {
            throw "review_candidate_record_invalid"
        }
        return [pscustomobject]@{ status = "present"; record = $record; reason = "" }
    }
    catch {
        return [pscustomobject]@{
            status = "invalid"; record = $null; reason = "review_candidate_record_invalid"
        }
    }
}

function Test-ReviewCandidateClassification {
    param(
        [Parameter(Mandatory = $true)][object]$Record,
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][object]$RepositoryEvidence,
        [Parameter(Mandatory = $true)][string]$GhPath,
        [Parameter(Mandatory = $true)][int]$ProcessTimeoutSeconds
    )

    $parentCommentId = [string]$Record.review_bundle_comment_id
    try {
        if ([string]$Record.target_repository -cne $ControlRepository -or
            [long]$Record.target_issue -le 0 -or
            ($Record.schema_version -eq $ReviewCandidateSchemaVersion -and
                -not [string]::Equals(
                    [System.IO.Path]::GetFullPath([string]$Record.target_repo_root).TrimEnd("\"),
                    $RepositoryRoot,
                    [System.StringComparison]::OrdinalIgnoreCase
                )) -or
            [string]$Record.branch -cne [string]$RepositoryEvidence.branch -or
            [string]$Record.expected_head -cne [string]$RepositoryEvidence.head) {
            throw "review_candidate_record_target_mismatch"
        }
        $terminal = Get-SameNodeContinuationComment `
            -GhPath $GhPath `
            -ParentCommentId ([string]$Record.terminal_result_comment_id) `
            -WorkingDirectory $RepositoryRoot `
            -ProcessTimeoutSeconds $ProcessTimeoutSeconds
        $terminalId = [string](Get-ObjectProperty -Object $terminal -Name "id")
        $terminalAuthor = [string](Get-ObjectProperty -Object (Get-ObjectProperty -Object $terminal -Name "user") -Name "login")
        $expectedIssueUrl = "https://api.github.com/repos/$ControlRepository/issues/$($Record.target_issue)"
        if ($terminalId -cne [string]$Record.terminal_result_comment_id -or
            $terminalAuthor -notin $TrustedContinuationAuthors -or
            -not [string]::Equals([string](Get-ObjectProperty -Object $terminal -Name "issue_url"), $expectedIssueUrl, [System.StringComparison]::Ordinal)) {
            throw "review_candidate_terminal_identity_mismatch"
        }
        $terminalSummary = ConvertFrom-FirstJsonObjectAfterMarker `
            -Body ([string](Get-ObjectProperty -Object $terminal -Name "body")) `
            -Marker $RunnerResultMarker
        $currentTerminalEligibilityInvalid = `
            $Record.schema_version -eq $ReviewCandidateSchemaVersion -and (
                [string](Get-ObjectProperty -Object $terminalSummary -Name "candidate_acceptance") -cne "eligible" -or
                @(Get-ObjectProperty -Object $terminalSummary -Name "changed_files").Count -eq 0
            )
        if ([string](Get-ObjectProperty -Object $terminalSummary -Name "schema") -cne "lawb.runner_result.v1" -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "request_id") -cne [string]$Record.dispatch_request_id -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "action") -cne "run-reviewbundle" -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "result") -cne "success" -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "repo") -cne $ControlRepository -or
            [long](Get-ObjectProperty -Object $terminalSummary -Name "issue") -ne [long]$Record.target_issue -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "branch") -cne [string]$Record.branch -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "head") -cne [string]$Record.expected_head -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "review_bundle_comment_id") -cne $parentCommentId -or
            [string](Get-ObjectProperty -Object $terminalSummary -Name "candidate_manifest_fingerprint") -cne [string]$Record.candidate_manifest_fingerprint -or
            $currentTerminalEligibilityInvalid) {
            throw "review_candidate_terminal_binding_mismatch"
        }
        $parent = Get-SameNodeContinuationComment `
            -GhPath $GhPath -ParentCommentId $parentCommentId `
            -WorkingDirectory $RepositoryRoot -ProcessTimeoutSeconds $ProcessTimeoutSeconds
        [void](Assert-ExactReviewCandidateIdentity `
            -RepositoryRoot $RepositoryRoot -RepositoryEvidence $RepositoryEvidence `
            -Comment $parent -ParentCommentId $parentCommentId `
            -IssueNumber ([long]$Record.target_issue) `
            -ExpectedManifestFingerprint ([string]$Record.candidate_manifest_fingerprint))
        return [pscustomobject]@{ status = "verified"; reason = ""; parent_comment_id = $parentCommentId }
    }
    catch {
        $reason = [string]$_.Exception.Message
        if ([string]::IsNullOrWhiteSpace($reason) -or $reason -notmatch '^[a-z0-9_]+$') {
            $reason = "review_candidate_validation_failed"
        }
        $status = if ($reason -eq "same_node_continuation_parent_read_failed") {
            "unavailable"
        }
        else { "invalid" }
        return [pscustomobject]@{ status = $status; reason = $reason; parent_comment_id = "" }
    }
}

function Test-FullyQualifiedLocalWindowsPath {
    param([AllowNull()][object]$Path)

    if ($Path -isnot [string] -or [string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    return [System.Text.RegularExpressions.Regex]::IsMatch(
        $Path,
        "\A[A-Za-z]:[\\/]"
    )
}

function Get-LocalLawbRoutingConfiguration {
    param(
        [Parameter(Mandatory = $true)][string]$StateDirectory,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.ArrayList]$Reasons
    )

    $emptyResult = [pscustomobject]@{
        present = $false
        target_root = ""
        expected_branch = ""
        expected_head = ""
        selection_id = ""
    }
    if ([string]::IsNullOrWhiteSpace($StateDirectory)) {
        return $emptyResult
    }
    $routingPath = Join-Path $StateDirectory "repository_routing.json"
    if (-not (Test-Path -LiteralPath $routingPath)) {
        return $emptyResult
    }
    if (-not (Test-Path -LiteralPath $routingPath -PathType Leaf)) {
        Add-BlockedReason -Reasons $Reasons -Reason "lawb_routing_configuration_invalid"
        return [pscustomobject]@{
            present = $true
            target_root = ""
            expected_branch = ""
            expected_head = ""
            selection_id = ""
        }
    }

    try {
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $routingText = $strictUtf8.GetString(
            [System.IO.File]::ReadAllBytes($routingPath)
        )
        $routing = Get-JsonObject -JsonText $routingText
        $propertyNames = @($routing.PSObject.Properties | ForEach-Object { $_.Name })
        $protocol = Get-ObjectProperty -Object $routing -Name "protocol"
        $repositoryName = Get-ObjectProperty -Object $routing -Name "repository"
        if ($protocol -isnot [string]) {
            throw "routing_protocol_invalid"
        }
        if ($repositoryName -isnot [string] -or
            -not [string]::Equals(
                $repositoryName,
                $ControlRepository,
                [System.StringComparison]::Ordinal
            )) {
            Add-BlockedReason -Reasons $Reasons `
                -Reason "lawb_routing_repository_mismatch"
            return [pscustomobject]@{
                present = $true
                target_root = ""
                expected_branch = ""
                expected_head = ""
                selection_id = ""
            }
        }

        if ([string]::Equals(
            $protocol,
            "lawb.bridge_operator_local_routing.v1",
            [System.StringComparison]::Ordinal
        )) {
            $expectedNames = @("protocol", "repository", "target_repo_root")
            if ($propertyNames.Count -ne $expectedNames.Count -or
                @($propertyNames | Where-Object { $_ -cnotin $expectedNames }).Count -gt 0) {
                throw "unexpected_routing_properties"
            }
            $configuredRoot = Get-ObjectProperty -Object $routing -Name "target_repo_root"
            if (-not (Test-FullyQualifiedLocalWindowsPath -Path $configuredRoot)) {
                Add-BlockedReason -Reasons $Reasons -Reason "lawb_routing_target_root_invalid"
                return [pscustomobject]@{
                    present = $true
                    target_root = ""
                    expected_branch = ""
                    expected_head = ""
                    selection_id = ""
                }
            }
            $resolvedRoot = [System.IO.Path]::GetFullPath($configuredRoot).TrimEnd("\")
            return [pscustomobject]@{
                present = $true
                target_root = $resolvedRoot
                expected_branch = ""
                expected_head = ""
                selection_id = ""
            }
        }

        if (-not [string]::Equals(
            $protocol,
            "lawb.bridge_operator_local_routing.v2",
            [System.StringComparison]::Ordinal
        )) {
            throw "routing_protocol_invalid"
        }
        $expectedNames = @("protocol", "repository", "selected_target")
        if ($propertyNames.Count -ne $expectedNames.Count -or
            @($propertyNames | Where-Object { $_ -cnotin $expectedNames }).Count -gt 0) {
            throw "unexpected_routing_properties"
        }
        $selectedTarget = Get-ObjectProperty -Object $routing -Name "selected_target"
        if ($null -eq $selectedTarget) {
            Add-BlockedReason -Reasons $Reasons -Reason "lawb_routing_no_safe_target"
            return [pscustomobject]@{
                present = $true
                target_root = ""
                expected_branch = ""
                expected_head = ""
                selection_id = ""
            }
        }
        $selectedPropertyNames = @($selectedTarget.PSObject.Properties | ForEach-Object { $_.Name })
        $expectedSelectedNames = @("selection_id", "target_repo_root", "branch", "head")
        if ($selectedPropertyNames.Count -ne $expectedSelectedNames.Count -or
            @($selectedPropertyNames | Where-Object { $_ -cnotin $expectedSelectedNames }).Count -gt 0) {
            throw "unexpected_selected_target_properties"
        }
        $selectionId = Get-ObjectProperty -Object $selectedTarget -Name "selection_id"
        $configuredRoot = Get-ObjectProperty -Object $selectedTarget -Name "target_repo_root"
        $expectedBranch = Get-ObjectProperty -Object $selectedTarget -Name "branch"
        $expectedHead = Get-ObjectProperty -Object $selectedTarget -Name "head"
        if ($selectionId -isnot [string] -or
            $selectionId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' -or
            -not (Test-FullyQualifiedLocalWindowsPath -Path $configuredRoot) -or
            $expectedBranch -isnot [string] -or
            $expectedBranch -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$' -or
            $expectedHead -isnot [string] -or
            $expectedHead -notmatch '^[0-9a-fA-F]{40}$') {
            Add-BlockedReason -Reasons $Reasons -Reason "lawb_routing_target_selection_invalid"
            return [pscustomobject]@{
                present = $true
                target_root = ""
                expected_branch = ""
                expected_head = ""
                selection_id = ""
            }
        }
        $resolvedRoot = [System.IO.Path]::GetFullPath($configuredRoot).TrimEnd("\")
        return [pscustomobject]@{
            present = $true
            target_root = $resolvedRoot
            expected_branch = $expectedBranch
            expected_head = $expectedHead.ToLowerInvariant()
            selection_id = $selectionId
        }
    }
    catch [System.Text.DecoderFallbackException] {
        Add-BlockedReason -Reasons $Reasons -Reason "lawb_routing_configuration_invalid"
    }
    catch {
        Add-BlockedReason -Reasons $Reasons -Reason "lawb_routing_configuration_invalid"
    }
    return [pscustomobject]@{
        present = $true
        target_root = ""
        expected_branch = ""
        expected_head = ""
        selection_id = ""
    }
}

function Test-TrueProperty {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )
    return (Get-ObjectProperty -Object $Object -Name $Name) -eq $true
}

function ConvertTo-SafeStatusReasonCodes {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Reasons
    )
    $safeReasons = [System.Collections.ArrayList]::new()
    foreach ($reasonValue in @($Reasons)) {
        $reason = [string]$reasonValue
        if ($reason -notmatch '^[a-z0-9_]+$') {
            $reason = "unknown_blocked_reason"
        }
        if (-not $safeReasons.Contains($reason)) {
            [void]$safeReasons.Add($reason)
        }
    }
    return @($safeReasons)
}

function Get-OperatorStatusBlockedReasonValues {
    param([AllowNull()][object]$OperatorSummary)
    if ($null -eq $OperatorSummary) {
        return @()
    }
    $property = $OperatorSummary.PSObject.Properties["blocked_reasons"]
    if ($null -eq $property -or $null -eq $property.Value) {
        return @()
    }
    $value = $property.Value
    if ($value -isnot [System.Array]) {
        return @("unknown_blocked_reason")
    }
    return @($value)
}

function Get-ValidStatusRequestId {
    param([AllowNull()][object]$OperatorSummary)
    $value = [string](Get-ObjectProperty -Object $OperatorSummary -Name "request_id")
    if ($value -match '^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$') {
        return $value
    }
    return $null
}

function Get-ValidStatusTargetIssue {
    param([AllowNull()][object]$OperatorSummary)
    $value = Get-ObjectProperty -Object $OperatorSummary -Name "target_issue"
    if (($value -is [int] -or $value -is [long]) -and [long]$value -gt 0) {
        return [long]$value
    }
    return $null
}

function New-StatusPayload {
    param(
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)]
        [ValidateSet("preflight", "operator", "final")]
        [string]$Stage,
        [Parameter(Mandatory = $true)]
        [ValidateSet("ready", "running", "completed", "blocked")]
        [string]$Result,
        [Parameter(Mandatory = $true)][string]$Repository,
        [AllowEmptyString()][string]$Branch,
        [AllowEmptyString()][string]$Head,
        [Parameter(Mandatory = $true)][bool]$LaunchRequested,
        [Parameter(Mandatory = $true)][bool]$OperatorInvoked,
        [AllowNull()][object]$OperatorSummary,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$BlockedReasons,
        [Parameter(Mandatory = $true)]
        [ValidateSet(
            "start_foreground",
            "review_blocked_reasons",
            "review_operator_result"
        )]
        [string]$NextAction
    )
    $payload = [ordered]@{
        protocol = $StatusProtocol
        run_id = $RunId
        operator_session_id = $RunId
        started_at_utc = $statusPublicationStartedAtUtc
        valid_until_utc = $statusPublicationValidUntilUtc
        configured_max_cycles = $MaxCycles
        configured_poll_interval_seconds = $PollIntervalSeconds
        configured_timeout_seconds = $TimeoutSeconds
        observed_at_utc = [DateTime]::UtcNow.ToString(
            "yyyy-MM-ddTHH:mm:ssZ",
            [Globalization.CultureInfo]::InvariantCulture
        )
        stage = $Stage
        result = $Result
        repository = $Repository
        branch = if ($Branch -match '^[A-Za-z0-9][A-Za-z0-9._/\-]{0,255}$') {
            $Branch
        }
        else {
            ""
        }
        head = if ($Head -match '^[0-9a-f]{40}$') { $Head } else { "" }
        launch_requested = $LaunchRequested
        operator_invoked = $OperatorInvoked
    }
    $requestId = Get-ValidStatusRequestId -OperatorSummary $OperatorSummary
    if ($null -ne $requestId) {
        $payload.request_id = $requestId
    }
    $targetIssue = Get-ValidStatusTargetIssue -OperatorSummary $OperatorSummary
    if ($null -ne $targetIssue) {
        $payload.target_issue = $targetIssue
    }
    $payload.dispatcher_invoked = (
        (Get-ObjectProperty -Object $OperatorSummary -Name "dispatcher_invoked") -eq $true
    )
    $payload.dispatcher_result_writeback_reached = (
        (Get-ObjectProperty -Object $OperatorSummary `
            -Name "dispatcher_result_writeback_reached") -eq $true
    )
    $payload.dispatcher_result_writeback_verified = (
        (Get-ObjectProperty -Object $OperatorSummary `
            -Name "dispatcher_result_writeback_verified") -eq $true
    )
    $payload.target_result_verified = (
        (Get-ObjectProperty -Object $OperatorSummary -Name "target_result_verified") -eq $true
    )
    $payload.blocked_reasons = @(
        ConvertTo-SafeStatusReasonCodes -Reasons $BlockedReasons
    )
    $payload.next_action = $NextAction
    return $payload
}

function New-StatusComment {
    param([Parameter(Mandatory = $true)][object]$Payload)
    $json = $Payload | ConvertTo-Json -Depth 20 -Compress
    return (
        "$StatusMarker protocol=$StatusProtocol" +
        [Environment]::NewLine +
        [Environment]::NewLine +
        '```json' +
        [Environment]::NewLine +
        $json +
        [Environment]::NewLine +
        '```'
    )
}

function Invoke-StatusCommentWrite {
    param(
        [Parameter(Mandatory = $true)][string]$GhPath,
        [Parameter(Mandatory = $true)]
        [ValidateSet("POST", "PATCH")]
        [string]$Method,
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [Parameter(Mandatory = $true)][object]$Payload,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][int]$ProcessTimeoutSeconds
    )
    $body = New-StatusComment -Payload $Payload
    $apiInput = [ordered]@{ body = $body } | ConvertTo-Json -Compress
    return Invoke-CapturedNative `
        -CommandPath $GhPath `
        -Arguments @(
            "api",
            "--hostname", $StatusHostname,
            "--method", $Method,
            $Endpoint,
            "--input", "-"
        ) `
        -WorkingDirectory $WorkingDirectory `
        -EncodingPolicy "utf-8" `
        -ProcessTimeoutSeconds $ProcessTimeoutSeconds `
        -StandardInputText $apiInput
}

function Get-StatusWriteOutcome {
    param(
        [Parameter(Mandatory = $true)][object]$NativeResult,
        [AllowNull()][object]$ExpectedCommentId
    )
    if (-not $NativeResult.process_started -or
        -not [string]::IsNullOrWhiteSpace([string]$NativeResult.contract_error)) {
        return [pscustomobject]@{ classification = "failed"; comment_id = $null }
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$NativeResult.invocation_error) -or
        -not [string]::IsNullOrWhiteSpace([string]$NativeResult.cleanup_error) -or
        $NativeResult.timed_out -or
        $NativeResult.stream_drain_timed_out -or
        -not [string]::IsNullOrWhiteSpace([string]$NativeResult.decode_error)) {
        return [pscustomobject]@{ classification = "uncertain"; comment_id = $null }
    }
    if ($NativeResult.exit_code -ne 0) {
        return [pscustomobject]@{ classification = "uncertain"; comment_id = $null }
    }
    try {
        $response = Get-JsonObject -JsonText $NativeResult.stdout
        $responseId = Get-ObjectProperty -Object $response -Name "id"
        if (-not ($responseId -is [int] -or $responseId -is [long]) -or
            [long]$responseId -le 0) {
            throw "invalid_comment_id"
        }
        $commentId = [long]$responseId
        if ($null -ne $ExpectedCommentId -and
            $commentId -ne [long]$ExpectedCommentId) {
            throw "comment_id_mismatch"
        }
        return [pscustomobject]@{
            classification = "success"
            comment_id = $commentId
        }
    }
    catch {
        return [pscustomobject]@{ classification = "uncertain"; comment_id = $null }
    }
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
        [System.Collections.ArrayList]$Reasons,
        [Parameter(Mandatory = $true)][bool]$LifecycleRecoveryHandoff
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Add-BlockedReason -Reasons $Reasons -Reason "state_directory_unavailable"
        return
    }
    $lockPath = Join-Path $Path "operator.lock"
    $lockHandoffEligible = $false
    if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
        try {
            $lockPayload = Get-JsonObject -JsonText (
                [System.IO.File]::ReadAllText($lockPath)
            )
            $lockHandoffEligible = (
                [string](Get-ObjectProperty -Object $lockPayload -Name "protocol") -eq
                    "lawb.bridge_operator_b3_lock.v2" -and
                (Get-ObjectProperty -Object $lockPayload -Name "schema_version") -eq 2 -and
                -not [string]::IsNullOrWhiteSpace(
                    [string](Get-ObjectProperty -Object $lockPayload `
                        -Name "operator_session_id")
                ) -and
                $null -ne (Get-ObjectProperty -Object $lockPayload `
                    -Name "process_identity")
            )
        }
        catch {
            $lockHandoffEligible = $false
        }
        if (-not $LifecycleRecoveryHandoff -or -not $lockHandoffEligible) {
            Add-BlockedReason -Reasons $Reasons -Reason "operator_lock_present"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $Path "pause.flag") -PathType Leaf) {
        Add-BlockedReason -Reasons $Reasons -Reason "pause_flag_present"
    }
    if (Test-Path -LiteralPath (Join-Path $Path "stop.flag") -PathType Leaf) {
        Add-BlockedReason -Reasons $Reasons -Reason "stop_flag_present"
    }
    $inFlightPath = Join-Path $Path "in_flight.json"
    if (Test-Path -LiteralPath $inFlightPath -PathType Leaf) {
        if (-not (Test-JsonEvidenceFile -Path $inFlightPath)) {
            Add-BlockedReason -Reasons $Reasons -Reason "state_evidence_invalid_or_unreadable"
        }
        elseif (-not $LifecycleRecoveryHandoff -or -not $lockHandoffEligible) {
            Add-BlockedReason -Reasons $Reasons -Reason "unresolved_in_flight_present"
        }
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
    foreach ($candidate in @(Get-ChildItem -LiteralPath $Path `
        -Filter "operator.lock.quarantine.*.json" -File `
        -ErrorAction SilentlyContinue)) {
        if (-not (Test-JsonEvidenceFile -Path $candidate.FullName)) {
            Add-BlockedReason -Reasons $Reasons -Reason "state_evidence_invalid_or_unreadable"
        }
    }
}

$blockedReasons = [System.Collections.ArrayList]::new()
$branch = ""
$head = ""
$statusBranch = ""
$statusHead = ""
$controlRepositoryValidated = $false
$bootstrapStatus = "NOT_RUN"
$reviewedPythonPath = ""
$reviewedGhPath = ""
$reviewedCodexPath = ""
$operatorSummary = $null
$operatorExitCode = $null
$operatorStderrSummary = ""
$operatorInvoked = $false
$statusPublicationCapable = $false
$statusPublicationAttempted = $false
$statusCommentCreateAttempted = $false
$statusCommentCreateSucceeded = $false
$statusCommentUpdateAttempted = $false
$statusCommentUpdateSucceeded = $false
$statusCommentId = $null
$statusPublicationResult = if ($PublishStatus) { "pending" } else { "not_requested" }
$statusPublicationBlockedReason = ""
$statusPublicationRunId = [guid]::NewGuid().ToString("N")
$statusPublicationStartedAt = [DateTime]::UtcNow
$statusPublicationStartedAtUtc = $statusPublicationStartedAt.ToString(
    "yyyy-MM-ddTHH:mm:ssZ",
    [Globalization.CultureInfo]::InvariantCulture
)
$statusValiditySeconds = [Math]::Max(
    [double]$TimeoutSeconds,
    [double]$MaxCycles * [double]$PollIntervalSeconds
)
$statusPublicationValidUntilUtc = $statusPublicationStartedAt.AddSeconds(
    $statusValiditySeconds
).ToString(
    "yyyy-MM-ddTHH:mm:ssZ",
    [Globalization.CultureInfo]::InvariantCulture
)
$statusCommentNeedsUpdate = $false
$githubWritePerformedDirectly = $false
$continuationBindingFieldCount = 0
if ($ContinuationIssueNumber -gt 0) { $continuationBindingFieldCount += 1 }
if (-not [string]::IsNullOrWhiteSpace($ExpectedState)) {
    $continuationBindingFieldCount += 1
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedCandidateManifestFingerprint)) {
    $continuationBindingFieldCount += 1
}
$continuationBindingRequested = $continuationBindingFieldCount -gt 0
$continuationBindingComplete = $continuationBindingFieldCount -eq 3
$continuationAdmissionAttemptEnabled = $continuationBindingComplete -and [bool]$StartForeground
$sameNodeContinuationAdmission = [pscustomobject]@{
    protocol = $SameNodeContinuationProtocol
    requested = $continuationBindingRequested
    admitted = $false
    issue = $ContinuationIssueNumber
    parent_comment_id = ""
    candidate_manifest_fingerprint = ""
    remaining_budget_before = $null
    is_human_approval = $false
    reasons = @()
}
$reviewCandidateStatus = "not_present"
$reviewCandidateReason = ""
$reviewCandidateParentCommentId = ""
$reviewCandidateRecord = $null
$targetSelectionMode = if ($continuationAdmissionAttemptEnabled) {
    "continuation_pending"
}
else {
    "ordinary_routing"
}
if ($continuationBindingRequested -and -not $continuationBindingComplete) {
    Add-BlockedReason -Reasons $blockedReasons `
        -Reason "same_node_continuation_binding_incomplete"
}
elseif ($continuationBindingComplete -and -not $StartForeground) {
    Add-BlockedReason -Reasons $blockedReasons `
        -Reason "same_node_continuation_foreground_required"
}

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
    $controlReasonCountBefore = $blockedReasons.Count
    $repoEvidence = Test-ExactRepository `
        -GitPath $gitPath `
        -RepositoryRoot $ControlRepoRoot `
        -ExpectedRepository $ControlRepository `
        -ReasonPrefix "control_repository" `
        -Reasons $blockedReasons
    $branch = $repoEvidence.branch
    $head = $repoEvidence.head
    $controlRepositoryValidated = (
        $blockedReasons.Count -eq $controlReasonCountBefore -and
        $branch -match '^[A-Za-z0-9][A-Za-z0-9._/\-]{0,255}$' -and
        $head -match '^[0-9a-f]{40}$'
    )
}

if (-not [string]::IsNullOrWhiteSpace($ResolvedStateDir)) {
    Inspect-OperatorState -Path $ResolvedStateDir -Reasons $blockedReasons `
        -LifecycleRecoveryHandoff ([bool]$StartForeground)
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
            else {
                $statusPublicationCapable = $true
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
    $lawbRouting = [pscustomobject]@{
        present = $false
        target_root = ""
        expected_branch = ""
        expected_head = ""
        selection_id = ""
    }
    if ($targetSelectionMode -eq "continuation_pending") {
        $reviewCandidateRecord = Get-ReviewCandidateRecord `
            -StateDirectory $ResolvedStateDir
        if ($reviewCandidateRecord.status -eq "invalid") {
            $targetSelectionMode = "continuation_blocked"
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "review_candidate_continuation_record_invalid"
        }
        elseif ($reviewCandidateRecord.status -eq "present") {
            try {
                $expectedParentCommentId = `
                    Get-SameNodeContinuationParentCommentId `
                        -ExpectedStateValue $ExpectedState
                if ([string]$reviewCandidateRecord.record.target_repository -cne `
                        $ControlRepository -or
                    [long]$reviewCandidateRecord.record.target_issue -ne `
                        $ContinuationIssueNumber -or
                    [string]$reviewCandidateRecord.record.review_bundle_comment_id -cne `
                        $expectedParentCommentId -or
                    [string]$reviewCandidateRecord.record.candidate_manifest_fingerprint -cne `
                        $ExpectedCandidateManifestFingerprint) {
                    throw "review_candidate_continuation_binding_mismatch"
                }
                if ($reviewCandidateRecord.record.schema_version -eq `
                    $ReviewCandidateSchemaVersion) {
                    $ResolvedTargetRepoRoot = [System.IO.Path]::GetFullPath(
                        [string]$reviewCandidateRecord.record.target_repo_root
                    ).TrimEnd("\")
                    $targetSelectionMode = "continuation_record"
                }
                else {
                    $targetSelectionMode = "continuation_legacy_record_routing"
                }
            }
            catch {
                $ResolvedTargetRepoRoot = ""
                $targetSelectionMode = "continuation_blocked"
                Add-BlockedReason -Reasons $blockedReasons `
                    -Reason "review_candidate_continuation_binding_mismatch"
            }
        }
        else {
            # Preserve the pre-v2 exact-candidate path when no local candidate
            # record exists.  This is continuation resolution, not fallback
            # from a failed record binding.
            $targetSelectionMode = "continuation_legacy_routing"
        }
    }
    if ($targetSelectionMode -in @(
        "ordinary_routing",
        "continuation_legacy_record_routing",
        "continuation_legacy_routing"
    )) {
        $lawbRouting = Get-LocalLawbRoutingConfiguration `
            -StateDirectory $ResolvedStateDir `
            -Reasons $blockedReasons
        if ($targetSelectionMode -eq "continuation_legacy_record_routing") {
            if (-not [string]::IsNullOrWhiteSpace($TargetRepoRoot)) {
                $targetSelectionMode = "continuation_blocked"
                Add-BlockedReason -Reasons $blockedReasons `
                    -Reason "lawb_target_repo_root_ambiguous"
            }
            elseif (-not $lawbRouting.present) {
                $targetSelectionMode = "continuation_blocked"
                Add-BlockedReason -Reasons $blockedReasons `
                    -Reason "review_candidate_continuation_routing_required"
            }
            elseif ([string]::IsNullOrWhiteSpace($lawbRouting.target_root)) {
                $targetSelectionMode = "continuation_blocked"
            }
            else {
                $ResolvedTargetRepoRoot = $lawbRouting.target_root
            }
        }
        else {
            if (-not [string]::IsNullOrWhiteSpace($TargetRepoRoot) -and $lawbRouting.present) {
                Add-BlockedReason -Reasons $blockedReasons -Reason "lawb_target_repo_root_ambiguous"
            }
            elseif (-not [string]::IsNullOrWhiteSpace($TargetRepoRoot)) {
                if (-not (Test-FullyQualifiedLocalWindowsPath -Path $TargetRepoRoot)) {
                    Add-BlockedReason -Reasons $blockedReasons -Reason "target_repo_root_invalid"
                }
                else {
                    try {
                        $ResolvedTargetRepoRoot = [System.IO.Path]::GetFullPath(
                            $TargetRepoRoot
                        ).TrimEnd("\")
                    }
                    catch {
                        Add-BlockedReason -Reasons $blockedReasons -Reason "target_repo_root_invalid"
                    }
                }
            }
            elseif ($lawbRouting.present) {
                $ResolvedTargetRepoRoot = $lawbRouting.target_root
            }
            else {
                $ResolvedTargetRepoRoot = $ControlRepoRoot
            }
        }
    }
    elseif ($targetSelectionMode -eq "continuation_record" -and
        -not [string]::IsNullOrWhiteSpace($TargetRepoRoot)) {
        Add-BlockedReason -Reasons $blockedReasons -Reason "lawb_target_repo_root_ambiguous"
    }

    if (-not [string]::IsNullOrWhiteSpace($ResolvedTargetRepoRoot) -and
        [string]::Equals(
            $ResolvedTargetRepoRoot,
            $ControlRepoRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        if ($continuationBindingRequested) {
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "same_node_continuation_distinct_routed_target_required"
        }
        if ($controlRepositoryValidated) {
            $statusBranch = $branch
            $statusHead = $head
        }
    }
    elseif (-not [string]::IsNullOrWhiteSpace($ResolvedTargetRepoRoot) -and
        -not [string]::IsNullOrWhiteSpace($gitPath)) {
        $targetReasonCountBefore = $blockedReasons.Count
        $targetRepoEvidence = Test-ExactRepository `
            -GitPath $gitPath `
            -RepositoryRoot $ResolvedTargetRepoRoot `
            -ExpectedRepository $Repository `
            -ReasonPrefix "target_repository" `
            -Reasons $blockedReasons `
            -DeferWorktreeDirty:$continuationAdmissionAttemptEnabled
        if ($blockedReasons.Count -eq $targetReasonCountBefore -and
            $targetSelectionMode -ne "continuation_record" -and
            -not [string]::IsNullOrWhiteSpace($lawbRouting.expected_branch) -and
            -not [string]::Equals(
                $targetRepoEvidence.branch,
                $lawbRouting.expected_branch,
                [System.StringComparison]::Ordinal
            )) {
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "lawb_routing_target_branch_mismatch"
        }
        if ($blockedReasons.Count -eq $targetReasonCountBefore -and
            $targetSelectionMode -ne "continuation_record" -and
            -not [string]::IsNullOrWhiteSpace($lawbRouting.expected_head) -and
            -not [string]::Equals(
                $targetRepoEvidence.head,
                $lawbRouting.expected_head,
                [System.StringComparison]::Ordinal
            )) {
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "lawb_routing_target_head_mismatch"
        }
        if ($continuationAdmissionAttemptEnabled -and
            $blockedReasons.Count -eq $targetReasonCountBefore) {
            if ([string]::IsNullOrWhiteSpace($reviewedGhPath)) {
                Add-BlockedReason -Reasons $blockedReasons `
                    -Reason "same_node_continuation_reviewed_gh_unavailable"
            }
            else {
                if ($targetSelectionMode -in @(
                    "continuation_record",
                    "continuation_legacy_record_routing"
                )) {
                    $reviewCandidateClassification = `
                        Test-ReviewCandidateClassification `
                            -Record $reviewCandidateRecord.record `
                            -RepositoryRoot $ResolvedTargetRepoRoot `
                            -RepositoryEvidence $targetRepoEvidence `
                            -GhPath $reviewedGhPath `
                            -ProcessTimeoutSeconds ([Math]::Min($TimeoutSeconds, 30))
                    if ($reviewCandidateClassification.status -ne "verified") {
                        Add-BlockedReason -Reasons $blockedReasons `
                            -Reason ([string]$reviewCandidateClassification.reason)
                    }
                }
                if ($blockedReasons.Count -eq $targetReasonCountBefore) {
                    $sameNodeContinuationAdmission = `
                        Test-SameNodeExactCandidateContinuation `
                            -RepositoryRoot $ResolvedTargetRepoRoot `
                            -RepositoryEvidence $targetRepoEvidence `
                            -GhPath $reviewedGhPath `
                            -IssueNumber $ContinuationIssueNumber `
                            -ExpectedStateValue $ExpectedState `
                            -ExpectedManifestFingerprint `
                                $ExpectedCandidateManifestFingerprint `
                            -ProcessTimeoutSeconds ([Math]::Min($TimeoutSeconds, 30))
                }
                if (-not $sameNodeContinuationAdmission.admitted -and
                    $blockedReasons.Count -eq $targetReasonCountBefore) {
                    Add-BlockedReason -Reasons $blockedReasons `
                        -Reason "target_repository_worktree_dirty"
                    foreach ($admissionReason in @(
                        $sameNodeContinuationAdmission.reasons
                    )) {
                        Add-BlockedReason -Reasons $blockedReasons `
                            -Reason ([string]$admissionReason)
                    }
                }
            }
        }
        if ($blockedReasons.Count -eq $targetReasonCountBefore -or
            $sameNodeContinuationAdmission.admitted) {
            $statusBranch = $targetRepoEvidence.branch
            $statusHead = $targetRepoEvidence.head
        }
        # This is diagnostic only.  Test-ExactRepository has already retained
        # the ordinary dirty-worktree blocked reason unless the independently
        # requested same-node continuation path is active.
        if (-not [string]::IsNullOrWhiteSpace([string]$targetRepoEvidence.status)) {
            $reviewCandidateRecord = Get-ReviewCandidateRecord `
                -StateDirectory $ResolvedStateDir
            if ($reviewCandidateRecord.status -eq "present") {
                if ([string]::IsNullOrWhiteSpace($reviewedGhPath)) {
                    $reviewCandidateStatus = "unavailable"
                    $reviewCandidateReason = "review_candidate_reviewed_gh_unavailable"
                }
                else {
                    $reviewCandidateClassification = Test-ReviewCandidateClassification `
                        -Record $reviewCandidateRecord.record `
                        -RepositoryRoot $ResolvedTargetRepoRoot `
                        -RepositoryEvidence $targetRepoEvidence `
                        -GhPath $reviewedGhPath `
                        -ProcessTimeoutSeconds ([Math]::Min($TimeoutSeconds, 30))
                    $reviewCandidateStatus = [string]$reviewCandidateClassification.status
                    $reviewCandidateReason = [string]$reviewCandidateClassification.reason
                    if ($reviewCandidateStatus -eq "verified") {
                        $reviewCandidateParentCommentId = [string]$reviewCandidateClassification.parent_comment_id
                    }
                }
            }
            elseif ($reviewCandidateRecord.status -eq "invalid") {
                $reviewCandidateStatus = "invalid"
                $reviewCandidateReason = [string]$reviewCandidateRecord.reason
            }
        }
        if ($targetSelectionMode -eq "continuation_legacy_record_routing" -and
            -not $sameNodeContinuationAdmission.admitted) {
            $ResolvedTargetRepoRoot = ""
        }
    }
}
elseif ([string]::Equals($Repository, $HagRepository, [System.StringComparison]::Ordinal)) {
    if ($continuationBindingRequested) {
        Add-BlockedReason -Reasons $blockedReasons `
            -Reason "same_node_continuation_repository_unsupported"
    }
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
            $targetReasonCountBefore = $blockedReasons.Count
            $targetRepoEvidence = Test-ExactRepository `
                -GitPath $gitPath `
                -RepositoryRoot $ResolvedTargetRepoRoot `
                -ExpectedRepository $Repository `
                -ReasonPrefix "target_repository" `
                -Reasons $blockedReasons
            if ($blockedReasons.Count -eq $targetReasonCountBefore) {
                $statusBranch = $targetRepoEvidence.branch
                $statusHead = $targetRepoEvidence.head
            }
        }
    }
}

if ($PublishStatus) {
    if (-not $statusPublicationCapable) {
        Add-BlockedReason -Reasons $blockedReasons -Reason "status_publication_unavailable"
        $statusPublicationResult = "unavailable"
        $statusPublicationBlockedReason = "status_publication_unavailable"
    }
    else {
        $preflightBlocked = $blockedReasons.Count -gt 0
        if ($StartForeground -and -not $preflightBlocked) {
            $statusStage = "operator"
            $statusResult = "running"
            $statusNextAction = "review_operator_result"
            $statusCommentNeedsUpdate = $true
        }
        elseif ($preflightBlocked) {
            $statusStage = "preflight"
            $statusResult = "blocked"
            $statusNextAction = "review_blocked_reasons"
        }
        else {
            $statusStage = "preflight"
            $statusResult = "ready"
            $statusNextAction = "start_foreground"
        }
        $statusPayload = New-StatusPayload `
            -RunId $statusPublicationRunId `
            -Stage $statusStage `
            -Result $statusResult `
            -Repository $Repository `
            -Branch $statusBranch `
            -Head $statusHead `
            -LaunchRequested ([bool]$StartForeground) `
            -OperatorInvoked $false `
            -OperatorSummary $null `
            -BlockedReasons @($blockedReasons) `
            -NextAction $statusNextAction
        $statusPublicationAttempted = $true
        $statusCommentCreateAttempted = $true
        $createNativeResult = Invoke-StatusCommentWrite `
            -GhPath $reviewedGhPath `
            -Method "POST" `
            -Endpoint $StatusCreateEndpoint `
            -Payload $statusPayload `
            -WorkingDirectory $ControlRepoRoot `
            -ProcessTimeoutSeconds $TimeoutSeconds
        if (-not [string]::IsNullOrWhiteSpace(
            [string]$createNativeResult.cleanup_error
        )) {
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "status_publication_process_cleanup_unverified"
        }
        $createOutcome = Get-StatusWriteOutcome `
            -NativeResult $createNativeResult `
            -ExpectedCommentId $null
        if ($createOutcome.classification -eq "success") {
            $statusCommentCreateSucceeded = $true
            $statusCommentId = [long]$createOutcome.comment_id
            $statusPublicationResult = "created"
            $githubWritePerformedDirectly = $true
        }
        elseif ($createOutcome.classification -eq "failed") {
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "status_publication_create_failed"
            $statusPublicationResult = "create_failed"
            $statusPublicationBlockedReason = "status_publication_create_failed"
            $statusCommentNeedsUpdate = $false
        }
        else {
            Add-BlockedReason -Reasons $blockedReasons `
                -Reason "status_publication_create_outcome_uncertain"
            $statusPublicationResult = "create_outcome_uncertain"
            $statusPublicationBlockedReason = "status_publication_create_outcome_uncertain"
            $statusCommentNeedsUpdate = $false
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
        "--timeout-seconds", [string]$TimeoutSeconds,
        "--operator-session-id", $statusPublicationRunId
    )
    if (-not [string]::Equals(
        $ResolvedTargetRepoRoot,
        $ControlRepoRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        $operatorArguments += @("--target-repo-root", $ResolvedTargetRepoRoot)
    }
    if ($statusCommentNeedsUpdate -and $statusCommentCreateSucceeded -and
        $null -ne $statusCommentId) {
        $operatorArguments += @(
            "--status-comment-id", [string]$statusCommentId,
            "--status-gh-path", $reviewedGhPath
        )
    }

    $previousPath = $env:PATH
    $previousPythonPath = $env:PYTHONPATH
    $workflowNotificationSettingWasPresent = Test-Path `
        -LiteralPath "Env:\LAWB_WORKFLOW_RESULT_NOTIFICATIONS_ENABLED"
    $previousWorkflowNotificationSetting = `
        $env:LAWB_WORKFLOW_RESULT_NOTIFICATIONS_ENABLED
    $continuationBindingSettingWasPresent = Test-Path `
        -LiteralPath "Env:\LAWB_SAME_NODE_CONTINUATION_BINDING"
    $previousContinuationBindingSetting = `
        $env:LAWB_SAME_NODE_CONTINUATION_BINDING
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
        $env:LAWB_WORKFLOW_RESULT_NOTIFICATIONS_ENABLED = "1"
        if ($sameNodeContinuationAdmission.admitted) {
            $env:LAWB_SAME_NODE_CONTINUATION_BINDING = ([ordered]@{
                protocol = "lawb.same_node_exact_candidate_continuation_launcher_binding.v1"
                repository = $Repository
                issue = [long]$sameNodeContinuationAdmission.issue
                parent_comment_id = [string]$sameNodeContinuationAdmission.parent_comment_id
                branch = $statusBranch
                head = $statusHead
                candidate_manifest_fingerprint = [string]$sameNodeContinuationAdmission.candidate_manifest_fingerprint
                remaining_budget_before = [long]$sameNodeContinuationAdmission.remaining_budget_before
                is_human_approval = $false
            } | ConvertTo-Json -Compress)
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
        if ($workflowNotificationSettingWasPresent) {
            $env:LAWB_WORKFLOW_RESULT_NOTIFICATIONS_ENABLED = `
                $previousWorkflowNotificationSetting
        }
        else {
            Remove-Item `
                -LiteralPath "Env:\LAWB_WORKFLOW_RESULT_NOTIFICATIONS_ENABLED" `
                -ErrorAction SilentlyContinue
        }
        if ($continuationBindingSettingWasPresent) {
            $env:LAWB_SAME_NODE_CONTINUATION_BINDING = `
                $previousContinuationBindingSetting
        }
        else {
            Remove-Item `
                -LiteralPath "Env:\LAWB_SAME_NODE_CONTINUATION_BINDING" `
                -ErrorAction SilentlyContinue
        }
    }
}

$resultBeforeStatusUpdate = if ($blockedReasons.Count -gt 0) {
    "blocked"
}
elseif ($StartForeground) {
    "completed"
}
else {
    "ready"
}
if ($PublishStatus -and $statusCommentNeedsUpdate -and
    $statusCommentCreateSucceeded -and $null -ne $statusCommentId) {
    $updateNextAction = if ($resultBeforeStatusUpdate -eq "completed") {
        "review_operator_result"
    }
    else {
        "review_blocked_reasons"
    }
    $finalStatusBlockedReasons = @($blockedReasons) + @(
        Get-OperatorStatusBlockedReasonValues -OperatorSummary $operatorSummary
    )
    $updatePayload = New-StatusPayload `
        -RunId $statusPublicationRunId `
        -Stage "final" `
        -Result $resultBeforeStatusUpdate `
        -Repository $Repository `
        -Branch $statusBranch `
        -Head $statusHead `
        -LaunchRequested ([bool]$StartForeground) `
        -OperatorInvoked $operatorInvoked `
        -OperatorSummary $operatorSummary `
        -BlockedReasons $finalStatusBlockedReasons `
        -NextAction $updateNextAction
    $statusPublicationAttempted = $true
    $statusCommentUpdateAttempted = $true
    $updateNativeResult = Invoke-StatusCommentWrite `
        -GhPath $reviewedGhPath `
        -Method "PATCH" `
        -Endpoint ($StatusUpdateEndpointPrefix + "/" + [string]$statusCommentId) `
        -Payload $updatePayload `
        -WorkingDirectory $ControlRepoRoot `
        -ProcessTimeoutSeconds $TimeoutSeconds
    if (-not [string]::IsNullOrWhiteSpace(
        [string]$updateNativeResult.cleanup_error
    )) {
        Add-BlockedReason -Reasons $blockedReasons `
            -Reason "status_publication_process_cleanup_unverified"
    }
    $updateOutcome = Get-StatusWriteOutcome `
        -NativeResult $updateNativeResult `
        -ExpectedCommentId $statusCommentId
    if ($updateOutcome.classification -eq "success") {
        $statusCommentUpdateSucceeded = $true
        $statusPublicationResult = "updated"
        $githubWritePerformedDirectly = $true
    }
    elseif ($updateOutcome.classification -eq "failed") {
        Add-BlockedReason -Reasons $blockedReasons `
            -Reason "status_publication_update_failed"
        $statusPublicationResult = "update_failed"
        $statusPublicationBlockedReason = "status_publication_update_failed"
    }
    else {
        Add-BlockedReason -Reasons $blockedReasons `
            -Reason "status_publication_update_outcome_uncertain"
        $statusPublicationResult = "update_outcome_uncertain"
        $statusPublicationBlockedReason = "status_publication_update_outcome_uncertain"
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
    same_node_candidate_continuation = $sameNodeContinuationAdmission
    review_candidate_status = $reviewCandidateStatus
    review_candidate_reason = $reviewCandidateReason
    review_candidate_parent_comment_id = $reviewCandidateParentCommentId
    status_publication_requested = [bool]$PublishStatus
    status_publication_attempted = $statusPublicationAttempted
    status_comment_create_attempted = $statusCommentCreateAttempted
    status_comment_create_succeeded = $statusCommentCreateSucceeded
    status_comment_update_attempted = $statusCommentUpdateAttempted
    status_comment_update_succeeded = $statusCommentUpdateSucceeded
    status_comment_id = $statusCommentId
    status_publication_result = $statusPublicationResult
    status_publication_blocked_reason = $statusPublicationBlockedReason
    status_publication_run_id = $statusPublicationRunId
    path_binding_scope = "process_only"
    manual_poll_once_is_recovery = $true
    background_service_started = $false
    dispatcher_invoked_directly = $false
    runner_invoked_directly = $false
    codex_invoked_directly = $false
    github_write_performed_directly = $githubWritePerformedDirectly
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
