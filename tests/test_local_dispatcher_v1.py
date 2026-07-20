import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = REPO_ROOT / "scripts" / "local_dispatcher_v1.ps1"
MARKER = "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1"
DRY_RUN_MARKER = "LAWBRUNNER-DRYRUN protocol=lawb.dispatch_dry_run.v1"
HEAD = "1111111111111111111111111111111111111111"
VALID_LINE = (
    "CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check "
    f"issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head={HEAD} "
    "expires=20990101T000000Z requested_by=chatgpt request_id=req-83"
)


def _dispatcher_core() -> str:
    source = DISPATCHER.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index("\ntry {")
    return source[start:end]


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local_dispatcher_v1 tests")
    return shell


def _powershell_single_quoted_literal() -> str:
    return "'" + _powershell().replace("'", "''") + "'"


def _decode_process_stream(stream: bytes | None) -> str | None:
    if stream is None:
        return None
    return stream.decode("utf-8", errors="replace")


def _normalize_line_endings(stream: str | None) -> str:
    return (stream or "").replace("\r\n", "\n").replace("\r", "\n")


def _process_output_contains(
    result: subprocess.CompletedProcess,
    token: str,
    *,
    allow_single_hard_wrap: bool = False,
) -> bool:
    for stream in (result.stdout, result.stderr):
        normalized = _normalize_line_endings(stream)
        if token in normalized:
            return True
        if not allow_single_hard_wrap:
            continue
        for index in range(1, len(token)):
            if token[index - 1].isspace() or token[index].isspace():
                continue
            pattern = (
                re.escape(token[:index])
                + r"\n[ \t]*"
                + re.escape(token[index:])
            )
            if re.search(pattern, normalized):
                return True
    return False


def _run_powershell(command: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
    )
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=_decode_process_stream(result.stdout),
        stderr=_decode_process_stream(result.stderr),
    )


def run_dispatcher_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "dispatcher_v1_test.ps1"
    script.write_text(
        _dispatcher_core()
        + textwrap.dedent(
            f"""

            $Repo = "HarryWhite-TW/local-ai-workbench"
            $IssueNumber = 83
            $IssueNumbers = @()
            $PostResultComment = $false
            $ReviewedCodexPath = ""
            $script:Branch = "master"
            $script:Head = "{HEAD}"
            $script:GitStatus = ""
            $script:Markers = @()
            $script:IssueMarkers = @{{}}
            $script:IssueStates = @{{}}
            $script:PostCalls = 0
            $script:PostedIssue = 0
            $script:PostedBody = ""
            $script:ForbiddenCalls = @()
            $script:RunnerCalls = 0
            $script:RunnerFilePath = ""
            $script:RunnerArguments = @()
            $script:RunnerStdout = "runner v1 review bundle ok"
            $script:RunnerStderr = ""
            $script:RunnerExitCode = 0
            $script:RunnerPreflightCalls = 0
            $script:RunnerPreflightStdout = '{json.dumps(_dispatcher_nested_runner())}'
            $script:RunnerPreflightExitCode = 0
            $script:PowerShellHostPath = {_powershell_single_quoted_literal()}
            Set-Content -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1") -Value "# runner stub" -Encoding UTF8

            function New-TestComment {{
                param(
                    [Parameter(Mandatory = $true)][string]$Body,
                    [string]$Id = "comment-1",
                    [string]$AuthorLogin = "HarryWhite-TW"
                )
                return [pscustomobject]@{{
                    id = $Id
                    author = [pscustomobject]@{{ login = $AuthorLogin }}
                    createdAt = "2026-05-18T00:00:00Z"
                    body = $Body
                }}
            }}

            function New-TestMarker {{
                param(
                    [Parameter(Mandatory = $true)][string]$Line,
                    [string]$Body = $null,
                    [string]$Id = "comment-1",
                    [string]$AuthorLogin = "HarryWhite-TW"
                )
                if ([string]::IsNullOrEmpty($Body)) {{
                    $Body = $Line
                }}
                return [pscustomobject]@{{
                    Line = $Line
                    Comment = (New-TestComment -Body $Body -Id $Id -AuthorLogin $AuthorLogin)
                    CommentIndex = 1
                    LineNumber = 1
                }}
            }}

            function New-DispatchLine {{
                param(
                    [string]$Action = "maybe-status-check",
                    [string]$Issue = "83",
                    [string]$RepoValue = "HarryWhite-TW/local-ai-workbench",
                    [string]$Branch = $script:Branch,
                    [string]$Head = $script:Head,
                    [string]$Expires = "20990101T000000Z",
                    [string]$RequestedBy = "chatgpt",
                    [string]$RequestId = "req-83",
                    [string]$Extra = ""
                )
                $line = "CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=$Action issue=$Issue repo=$RepoValue branch=$Branch head=$Head expires=$Expires requested_by=$RequestedBy request_id=$RequestId"
                if (-not [string]::IsNullOrWhiteSpace($Extra)) {{
                    $line = "$line $Extra"
                }}
                return $line
            }}

            function Assert-RepoRoot {{}}
            function Resolve-GhPath {{ return "gh" }}
            function Get-CurrentBranch {{ return $script:Branch }}
            function Get-CurrentFullHead {{ return $script:Head }}
            function Get-GitStatusShort {{ return $script:GitStatus }}
            function Resolve-CurrentPowerShellHostPath {{ return $script:PowerShellHostPath }}
            function Write-FinalGitStatus {{
                Write-Host "Final local git status:"
                if ([string]::IsNullOrWhiteSpace($script:GitStatus)) {{
                    Write-Host "(clean)"
                }} else {{
                    Write-Host $script:GitStatus
                }}
            }}
            function Invoke-ReadOnlyCommand {{
                param([string]$FilePath, [string[]]$Arguments, [string]$Action)
                if ($Action -eq "runner ToolResolutionPreflight") {{
                    $script:RunnerPreflightCalls += 1
                    return [pscustomobject]@{{
                        ExitCode = $script:RunnerPreflightExitCode
                        Stdout = $script:RunnerPreflightStdout
                        Stderr = ""
                    }}
                }}
                $requestedIssue = [int]$Arguments[2]
                $sourceMarkers = $script:Markers
                if ($script:IssueMarkers.ContainsKey($requestedIssue)) {{
                    $sourceMarkers = @($script:IssueMarkers[$requestedIssue])
                }}
                $issueState = "OPEN"
                if ($script:IssueStates.ContainsKey($requestedIssue)) {{
                    $issueState = [string]$script:IssueStates[$requestedIssue]
                }}
                $comments = @($sourceMarkers | ForEach-Object {{ $_.Comment }})
                $payload = [pscustomobject]@{{
                    number = $requestedIssue
                    title = "Issue $requestedIssue"
                    state = $issueState
                    comments = @($comments)
                }} | ConvertTo-Json -Depth 8
                return [pscustomobject]@{{
                    ExitCode = 0
                    Stdout = $payload
                    Stderr = ""
                }}
            }}
            function Publish-RunnerResultComment {{
                param([int]$IssueNumber, [string]$Body)
                $script:PostCalls += 1
                $script:PostedIssue = $IssueNumber
                $script:PostedBody = $Body
                return [pscustomobject]@{{ ExitCode = 0; Stdout = "posted"; Stderr = "" }}
            }}
            function Invoke-WriteCommand {{
                param([string]$FilePath, [string[]]$Arguments, [string]$Action)
                $script:RunnerCalls += 1
                $script:RunnerFilePath = $FilePath
                $script:RunnerArguments = @($Arguments)
                return [pscustomobject]@{{
                    ExitCode = $script:RunnerExitCode
                    Stdout = $script:RunnerStdout
                    Stderr = $script:RunnerStderr
                }}
            }}
            function git {{ $script:ForbiddenCalls += "git" }}
            function gh {{ $script:ForbiddenCalls += "gh" }}
            """
        )
        + "\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    return _run_powershell(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    )


def run_dispatcher_core_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "dispatcher_v1_core_test.ps1"
    script.write_text(
        _dispatcher_core()
        + textwrap.dedent(
            f"""

            $Repo = "HarryWhite-TW/local-ai-workbench"
            $IssueNumber = 83
            $IssueNumbers = @()
            $PostResultComment = $false
            $ReviewedCodexPath = ""
            $script:ForbiddenCalls = @()
            function git {{ $script:ForbiddenCalls += "git" }}
            function gh {{ $script:ForbiddenCalls += "gh" }}
            """
        )
        + "\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    return _run_powershell(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    )


def test_reviewbundle_cross_repo_runner_arguments_bind_hag_target(tmp_path):
    result = run_dispatcher_script(
        tmp_path,
        """
        $Repo = "HarryWhite-TW/human-approval-automation-gateway"
        $TargetRepoRoot = $RepoRoot
        $script:GitStatus = ""
        $selection = [pscustomobject]@{}
        $result = Invoke-ReviewBundle -Selection $selection -Issue 218
        if ($result.Result -ne "success") { throw "runner invocation failed" }
        $repoIndex = [array]::IndexOf($script:RunnerArguments, "-Repo")
        $pathIndex = [array]::IndexOf($script:RunnerArguments, "-RepoPath")
        if ($repoIndex -lt 0 -or $script:RunnerArguments[$repoIndex + 1] -ne $Repo) {
            throw "HAG repository was not propagated to Runner"
        }
        if ($pathIndex -lt 0 -or $script:RunnerArguments[$pathIndex + 1] -ne $TargetRepoRoot) {
            throw "HAG target root was not propagated to Runner"
        }
        "ok"
        """,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout


def assert_success(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def extract_summary(stdout: str) -> dict:
    return extract_summary_after(stdout, MARKER)


def extract_summary_after(stdout: str, marker: str) -> dict:
    assert "\ufffd" not in stdout, "Structured dispatcher output contained replacement characters."
    lines = stdout.splitlines()
    marker_index = lines.index(marker)
    json_lines = []
    depth = 0
    started = False
    for line in lines[marker_index + 1 :]:
        json_lines.append(line)
        depth += line.count("{") - line.count("}")
        started = started or "{" in line
        if started and depth == 0:
            break
    return json.loads("\n".join(json_lines))


def test_extract_summary_rejects_replacement_characters():
    output = MARKER + '\n{"result":"success\ufffd"}'

    with pytest.raises(AssertionError, match="replacement characters"):
        extract_summary(output)


def test_process_output_match_does_not_cross_stream_boundary():
    result = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="Choos",
        stderr="e exactly one mode.",
    )

    assert not _process_output_contains(
        result,
        "Choose exactly one mode.",
        allow_single_hard_wrap=True,
    )


def test_process_output_match_accepts_one_crlf_hard_wrap():
    result = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout=None,
        stderr="Choos\r\n    e exactly one mode.",
    )

    assert _process_output_contains(
        result,
        "Choose exactly one mode.",
        allow_single_hard_wrap=True,
    )


def test_process_output_match_handles_none_streams():
    result = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout=None,
        stderr=None,
    )

    assert not _process_output_contains(result, "Choose exactly one mode.")


def extract_posted_body(stdout: str) -> str:
    prefix = "POSTED_BODY_BASE64="
    encoded = next(line[len(prefix) :] for line in stdout.splitlines() if line.startswith(prefix))
    return bytes.fromhex(encoded).decode("utf-8")


def extract_value(stdout: str, prefix: str) -> str:
    return next(line[len(prefix) :] for line in stdout.splitlines() if line.startswith(prefix))


def run_case(tmp_path: Path, setup: str, post: bool = False) -> subprocess.CompletedProcess:
    post_value = "$true" if post else "$false"
    return run_dispatcher_script(
        tmp_path,
        f"""
        {setup}
        $PostResultComment = {post_value}
        try {{
            Invoke-PollOnce
            Write-Host "CASE_RESULT=success"
        }} catch {{
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }}
        Write-Host "POST_CALLS=$script:PostCalls"
        Write-Host "POSTED_ISSUE=$script:PostedIssue"
        Write-Host "RUNNER_CALLS=$script:RunnerCalls"
        Write-Host "RUNNER_FILE=$script:RunnerFilePath"
        Write-Host "RUNNER_ARGS=$($script:RunnerArguments -join '|')"
        if (-not [string]::IsNullOrEmpty($script:PostedBody)) {{
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($script:PostedBody)
            Write-Host "POSTED_BODY_BASE64=$([System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant())"
        }}
        Write-Host "FORBIDDEN_CALLS=$(@($script:ForbiddenCalls).Count)"
        """,
    )


def run_dry_case(tmp_path: Path, setup: str) -> subprocess.CompletedProcess:
    return run_dispatcher_script(
        tmp_path,
        f"""
        {setup}
        try {{
            Invoke-DryRunBoundedPoll
            Write-Host "CASE_RESULT=success"
        }} catch {{
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }}
        Write-Host "POST_CALLS=$script:PostCalls"
        Write-Host "FORBIDDEN_CALLS=$(@($script:ForbiddenCalls).Count)"
        """,
    )


def run_bounded_case(tmp_path: Path, setup: str, post: bool = False) -> subprocess.CompletedProcess:
    post_value = "$true" if post else "$false"
    return run_dispatcher_script(
        tmp_path,
        f"""
        {setup}
        $PostResultComment = {post_value}
        try {{
            Invoke-BoundedPoll
            Write-Host "CASE_RESULT=success"
        }} catch {{
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }}
        Write-Host "POST_CALLS=$script:PostCalls"
        Write-Host "POSTED_ISSUE=$script:PostedIssue"
        if (-not [string]::IsNullOrEmpty($script:PostedBody)) {{
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($script:PostedBody)
            Write-Host "POSTED_BODY_BASE64=$([System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant())"
        }}
        Write-Host "FORBIDDEN_CALLS=$(@($script:ForbiddenCalls).Count)"
        """,
    )


def test_missing_issue_number_fails_closed_without_posting(tmp_path):
    result = run_case(
        tmp_path,
        f"""
        $IssueNumber = 0
        $script:Markers = @((New-TestMarker "{VALID_LINE}"))
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "PollOnce requires -IssueNumber <N>" in result.stdout
    assert "POST_CALLS=0" in result.stdout


def test_valid_maybe_status_check_succeeds_without_posting_by_default(tmp_path):
    result = run_case(
        tmp_path,
        '$script:Markers = @((New-TestMarker (New-DispatchLine)))',
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "POST_CALLS=0" in result.stdout
    assert MARKER in result.stdout
    summary = extract_summary(result.stdout)
    assert summary["action"] == "maybe-status-check"
    assert summary["issue"] == 83
    assert summary["selected_issue"] == 83
    assert summary["result"] == "success"
    assert "RUNNER_CALLS=0" in result.stdout


def test_valid_run_reviewbundle_delegates_to_runner_v1_reviewbundle(tmp_path):
    result = run_case(
        tmp_path,
        '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle" -RequestId "req-rb-83")))',
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "RUNNER_CALLS=1" in result.stdout
    runner_file = extract_value(result.stdout, "RUNNER_FILE=")
    assert runner_file.lower() == _powershell().lower()
    assert "local_runner_v1.ps1" in result.stdout
    runner_args = extract_value(result.stdout, "RUNNER_ARGS=").split("|")
    assert runner_args[:4] == ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    assert runner_args[4].endswith("local_runner_v1.ps1")
    assert runner_args[5:] == [
        "-IssueNumber",
        "83",
        "-Mode",
        "ReviewBundle",
        "-ReviewedCodexPath",
        r"C:\Tools\codex.cmd",
    ]
    assert "runner v1 review bundle ok" in result.stdout

    summary = extract_summary(result.stdout)
    assert summary["action"] == "run-reviewbundle"
    assert summary["issue"] == 83
    assert summary["selected_issue"] == 83
    assert summary["request_id"] == "req-rb-83"
    assert summary["result"] == "success"
    assert summary["validations"]["git_status_clean"]["status"] == "passed"
    assert summary["validations"]["final_head_matches_initial"]["status"] == "passed"
    assert summary["validations"]["final_index_clean"]["status"] == "passed"
    assert summary["observations"]["final_index_clean"] is True
    assert summary["observations"]["final_head_matches_initial"] is True
    assert summary["trusted_parent_actions"]["push_invoked"] is False
    assert summary["child_action_non_claim"] == "transient_or_external_child_actions_not_guaranteed_absent"


def test_dispatcher_reports_changed_head_as_bounded_observation_failure(tmp_path):
    result = run_case(
        tmp_path,
        f"""
        function Invoke-WriteCommand {{
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            $script:RunnerCalls += 1
            $script:RunnerFilePath = $FilePath
            $script:RunnerArguments = @($Arguments)
            $script:Head = {('2' * 40)!r}
            return [pscustomobject]@{{ ExitCode = 0; Stdout = "runner ok"; Stderr = "" }}
        }}
        $script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle" -RequestId "req-head-change")))
        """,
    )

    assert_success(result)
    summary = extract_summary(result.stdout)
    assert summary["result"] == "failure"
    assert summary["head"] == "2" * 40
    assert summary["observations"]["final_head_matches_initial"] is False
    assert summary["validations"]["final_head_matches_initial"]["status"] == "failed"


def test_dispatcher_reports_final_staged_index_as_bounded_observation_failure(tmp_path):
    result = run_case(
        tmp_path,
        """
        function Invoke-WriteCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            $script:RunnerCalls += 1
            $script:RunnerFilePath = $FilePath
            $script:RunnerArguments = @($Arguments)
            $script:GitStatus = "M  staged.txt"
            return [pscustomobject]@{ ExitCode = 0; Stdout = "runner ok"; Stderr = "" }
        }
        $script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle" -RequestId "req-stage-change")))
        """,
    )

    assert_success(result)
    summary = extract_summary(result.stdout)
    assert summary["result"] == "failure"
    assert summary["observations"]["final_index_clean"] is False
    assert summary["observations"]["final_head_matches_initial"] is True
    assert summary["validations"]["final_index_clean"]["status"] == "failed"


def test_run_reviewbundle_real_stub_runner_binds_named_parameters(tmp_path):
    runner = tmp_path / "local_runner_v1.ps1"
    reviewed = tmp_path / "Reviewed Codex Path" / "codex launcher.exe"
    reviewed.parent.mkdir()
    reviewed.write_text("fake codex", encoding="utf-8")
    runner.write_text(
        textwrap.dedent(
            """
            param(
                [ValidateRange(0, [int]::MaxValue)]
                [int]$IssueNumber = 0,
                [ValidateSet("ReviewBundle")]
                [string]$Mode = "ReviewBundle",
                [string]$ReviewedCodexPath = ""
            )

            $payload = [ordered]@{
                issue_number = $IssueNumber
                issue_type = $IssueNumber.GetType().FullName
                mode = $Mode
                reviewed_codex_path = $ReviewedCodexPath
            }
            Write-Output ("STUB_BINDING_JSON=" + ($payload | ConvertTo-Json -Compress))
            exit 0
            """
        ).strip(),
        encoding="utf-8",
    )
    result = run_dispatcher_core_script(
        tmp_path,
        f"""
        function Get-GitStatusShort {{ return "" }}
        function Get-RunnerScriptPath {{ return {runner.as_posix()!r} }}
        function Resolve-ReviewBundleCodexPathBinding {{ return {reviewed.as_posix()!r} }}

        $result = Invoke-ReviewBundle -Selection ([pscustomobject]@{{}}) -Issue 83
        Write-Host "PARENT_SENTINEL=continued"
        Write-Host "RESULT=$($result.Result)"
        Write-Host "RUNNER_EXIT=$($result.RunnerExitCode)"
        $stdoutBytes = [System.Text.Encoding]::UTF8.GetBytes($result.Stdout)
        Write-Host "CAPTURED_STDOUT_HEX=$([System.BitConverter]::ToString($stdoutBytes).Replace('-', '').ToLowerInvariant())"
        Write-Host "CAPTURED_STDERR=$($result.Stderr)"
        """,
    )

    assert_success(result)
    assert "PARENT_SENTINEL=continued" in result.stdout
    assert "RESULT=success" in result.stdout
    assert "RUNNER_EXIT=0" in result.stdout
    captured_stdout = bytes.fromhex(
        extract_value(result.stdout, "CAPTURED_STDOUT_HEX=")
    ).decode("utf-8")
    payload_line = next(
        line
        for line in captured_stdout.splitlines()
        if line.startswith("STUB_BINDING_JSON=")
    )
    payload = json.loads(payload_line.split("=", 1)[1])
    assert payload["issue_number"] == 83
    assert payload["issue_type"] == "System.Int32"
    assert payload["mode"] == "ReviewBundle"
    assert payload["reviewed_codex_path"] == reviewed.as_posix()
    assert "Cannot process argument transformation" not in result.stdout
    assert "Cannot convert value \"-IssueNumber\"" not in result.stdout


def test_run_reviewbundle_fails_closed_when_reviewed_codex_path_mismatches_preflight(tmp_path):
    result = run_case(
        tmp_path,
        r'''
        $ReviewedCodexPath = "C:\WindowsApps\codex.exe"
        $script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle" -RequestId "req-rb-mismatch-83")))
        ''',
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "reviewed_codex_path_mismatch" in result.stdout
    assert "RUNNER_CALLS=0" in result.stdout


def test_run_reviewbundle_runner_failure_posts_dispatcher_failure_result(tmp_path):
    result = run_case(
        tmp_path,
        '$script:RunnerExitCode = 1; $script:RunnerStdout = "runner bundle posted"; $script:RunnerStderr = "runner failed"; $script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle" -RequestId "req-rb-fail-83")))',
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "Action result: failure" in result.stdout
    assert "RUNNER_CALLS=1" in result.stdout
    assert "POST_CALLS=1" in result.stdout

    summary = extract_summary(result.stdout)
    assert summary["action"] == "run-reviewbundle"
    assert summary["result"] == "failure"
    assert summary["request_id"] == "req-rb-fail-83"
    assert summary["validations"]["git_status_clean"]["status"] == "passed"
    assert summary["validations"]["runner_v1"]["status"] == "failed"
    assert "exit code: 1" in summary["validations"]["runner_v1"]["summary"]
    assert summary["observations"]["final_head_matches_initial"] is True
    assert summary["trusted_parent_actions"]["push_invoked"] is False
    assert summary["trusted_parent_actions"]["issue_close_invoked"] is False

    posted_body = extract_posted_body(result.stdout)
    posted_summary = extract_summary_after(posted_body, MARKER)
    assert posted_summary["result"] == "failure"
    assert posted_summary["request_id"] == "req-rb-fail-83"


def test_run_reviewbundle_fails_closed_when_repo_is_dirty_before_runner(tmp_path):
    result = run_case(
        tmp_path,
        '$script:GitStatus = " M docs/RUNNER_V2.md"; $script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle")))',
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "run-reviewbundle requires a clean repo before dispatch" in result.stdout
    assert "POST_CALLS=0" in result.stdout
    assert "RUNNER_CALLS=0" in result.stdout


def test_valid_maybe_status_check_with_post_result_comment_posts_exactly_one_parseable_result(tmp_path):
    result = run_case(
        tmp_path,
        '$script:Markers = @((New-TestMarker (New-DispatchLine)))',
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "POST_CALLS=1" in result.stdout
    assert "POSTED_ISSUE=83" in result.stdout
    assert MARKER in result.stdout

    stdout_summary = extract_summary(result.stdout)
    posted_body = extract_posted_body(result.stdout)
    assert posted_body.startswith(MARKER + "\n")
    posted_summary = json.loads(posted_body.split("\n", 1)[1])
    assert posted_summary["issue"] == 83
    assert posted_summary["selected_issue"] == 83
    assert posted_summary == stdout_summary


def test_publish_runner_result_comment_uses_body_file_for_multiline_body(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        """
        function Resolve-GhPath { return "gh" }
        function Invoke-WriteCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            $script:CapturedFilePath = $FilePath
            $script:CapturedArguments = @($Arguments)
            $bodyFileIndex = [Array]::IndexOf($script:CapturedArguments, "--body-file")
            if ($bodyFileIndex -ge 0) {
                $script:CapturedBodyFile = $script:CapturedArguments[$bodyFileIndex + 1]
                $script:BodyFileExistedDuringPost = Test-Path -LiteralPath $script:CapturedBodyFile
                $script:BodyFileBytes = [System.IO.File]::ReadAllBytes($script:CapturedBodyFile)
                $script:BodyFileText = [System.Text.Encoding]::UTF8.GetString($script:BodyFileBytes)
            }
            return [pscustomobject]@{ ExitCode = 0; Stdout = "posted"; Stderr = "" }
        }

        $summaryJson = New-RunnerResultSummaryJson `
            -Issue 83 `
            -Action "maybe-status-check" `
            -Result "success" `
            -Branch "master" `
            -Head "1111111111111111111111111111111111111111" `
            -SelectedIssue 83 `
            -NoStage $true `
            -NoCommit $true
        $body = "$RunnerResultMarker`n$summaryJson"
        $null = Publish-RunnerResultComment -IssueNumber 83 -Body $body

        Write-Host "CAPTURED_FILE_PATH=$script:CapturedFilePath"
        Write-Host "CAPTURED_ARGUMENTS=$($script:CapturedArguments -join '|')"
        Write-Host "BODY_FILE_EXISTED_DURING_POST=$script:BodyFileExistedDuringPost"
        Write-Host "BODY_FILE_EXISTS_AFTER_POST=$(Test-Path -LiteralPath $script:CapturedBodyFile)"
        Write-Host "BODY_FILE_BYTE_PREFIX=$([System.BitConverter]::ToString($script:BodyFileBytes[0..2]).Replace('-', '').ToLowerInvariant())"
        $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($script:BodyFileText)
        Write-Host "BODY_FILE_TEXT_BASE64=$([System.BitConverter]::ToString($bodyBytes).Replace('-', '').ToLowerInvariant())"
        Write-Host "FORBIDDEN_CALLS=$(@($script:ForbiddenCalls).Count)"
        """,
    )
    assert_success(result)
    assert "CAPTURED_FILE_PATH=gh" in result.stdout
    captured_arguments = extract_value(result.stdout, "CAPTURED_ARGUMENTS=").split("|")
    assert captured_arguments[:5] == ["issue", "comment", "83", "--repo", "HarryWhite-TW/local-ai-workbench"]
    assert "--body-file" in captured_arguments
    assert "--body" not in captured_arguments
    assert "--check" not in captured_arguments
    assert "edit" not in captured_arguments
    assert "delete" not in captured_arguments
    assert "label" not in captured_arguments
    assert "close" not in captured_arguments
    assert "push" not in captured_arguments
    assert "commit" not in captured_arguments
    assert "BODY_FILE_EXISTED_DURING_POST=True" in result.stdout
    assert "BODY_FILE_EXISTS_AFTER_POST=False" in result.stdout
    assert "BODY_FILE_BYTE_PREFIX=4c4157" in result.stdout
    assert "FORBIDDEN_CALLS=0" in result.stdout

    posted_body = bytes.fromhex(extract_value(result.stdout, "BODY_FILE_TEXT_BASE64=")).decode("utf-8")
    assert posted_body.startswith(MARKER + "\n")
    posted_summary = json.loads(posted_body.split("\n", 1)[1])
    assert posted_summary["validations"]["git_diff_check"]["summary"] == (
        "Dispatcher action 'maybe-status-check' did not independently run git diff --check."
    )


def test_resolve_gh_path_prefers_path_command_before_fallback(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fallback-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        $PathGh = Join-Path -Path $PSScriptRoot -ChildPath "path-gh.exe"
        New-Item -ItemType File -Path $PathGh -Force | Out-Null
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return [pscustomobject]@{ CommandType = "Application"; Source = $PathGh }
        }

        Write-Host "GH_PATH=$(Resolve-GhPath)"
        """,
    )
    assert_success(result)
    assert f"GH_PATH={tmp_path / 'path-gh.exe'}" in result.stdout


def test_resolve_gh_path_uses_fallback_when_path_command_missing(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fallback-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }

        Write-Host "GH_PATH=$(Resolve-GhPath)"
        """,
    )
    assert_success(result)
    assert f"GH_PATH={tmp_path / 'fallback-gh.exe'}" in result.stdout



def test_resolve_gh_path_uses_portable_fallback_when_path_and_program_files_missing(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-program-files-gh.exe"
        $GhCliPortableFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "portable-gh.exe"
        New-Item -ItemType File -Path $GhCliPortableFallbackPath -Force | Out-Null
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }

        Write-Host "GH_PATH=$(Resolve-GhPath)"
        """,
    )
    assert_success(result)
    assert f"GH_PATH={tmp_path / 'portable-gh.exe'}" in result.stdout


def test_resolve_gh_path_prefers_exe_and_rejects_unsafe_path_candidates(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-gh.exe"
        $GhCliPortableFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-portable-gh.exe"
        $ps1 = Join-Path -Path $PSScriptRoot -ChildPath "gh.ps1"
        $unknown = Join-Path -Path $PSScriptRoot -ChildPath "gh.sh"
        $cmd = Join-Path -Path $PSScriptRoot -ChildPath "gh.cmd"
        $exe = Join-Path -Path $PSScriptRoot -ChildPath "gh.exe"
        foreach ($path in @($ps1, $unknown, $cmd, $exe)) {
            New-Item -ItemType File -Path $path -Force | Out-Null
        }
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return @(
                [pscustomobject]@{ CommandType = "ExternalScript"; Source = $ps1 },
                [pscustomobject]@{ CommandType = "Application"; Source = $unknown },
                [pscustomobject]@{ CommandType = "Application"; Source = $cmd },
                [pscustomobject]@{ CommandType = "Application"; Source = $exe }
            )
        }

        Write-Host "GH_PATH=$(Resolve-GhPath)"
        """,
    )
    assert_success(result)
    assert f"GH_PATH={tmp_path / 'gh.exe'}" in result.stdout


def test_resolve_gh_path_rejects_alias_function_and_unknown_extension(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-gh.exe"
        $GhCliPortableFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-portable-gh.exe"
        $unknown = Join-Path -Path $PSScriptRoot -ChildPath "gh.sh"
        New-Item -ItemType File -Path $unknown -Force | Out-Null
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return @(
                [pscustomobject]@{ CommandType = "Alias"; Source = "gh-alias" },
                [pscustomobject]@{ CommandType = "Function"; Source = "gh-function" },
                [pscustomobject]@{ CommandType = "Application"; Source = $unknown }
            )
        }

        try {
            $null = Resolve-GhPath
            Write-Host "CASE_RESULT=success"
        } catch {
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "GitHub CLI 'gh' is required" in result.stdout


def test_resolve_gh_path_fails_closed_when_missing_from_path_and_fallback(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-gh.exe"
        $GhCliPortableFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "missing-portable-gh.exe"
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }

        try {
            $null = Resolve-GhPath
            Write-Host "CASE_RESULT=success"
        } catch {
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "Tried PATH command 'gh'" in result.stdout
    assert "missing-gh.exe" in result.stdout


def test_issue_read_uses_resolved_fallback_gh_path(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fallback-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }
        function Invoke-ReadOnlyCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            $script:CapturedFilePath = $FilePath
            $payload = [pscustomobject]@{
                number = 83
                title = "Issue 83"
                state = "OPEN"
                comments = @()
            } | ConvertTo-Json -Depth 8
            return [pscustomobject]@{ ExitCode = 0; Stdout = $payload; Stderr = "" }
        }

        $null = Get-IssueDispatchMarkerReadResult -IssueNumber 83
        Write-Host "CAPTURED_FILE_PATH=$script:CapturedFilePath"
        """,
    )
    assert_success(result)
    assert f"CAPTURED_FILE_PATH={tmp_path / 'fallback-gh.exe'}" in result.stdout


def test_publish_runner_result_comment_uses_resolved_fallback_gh_path(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fallback-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }
        function Invoke-WriteCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            $script:CapturedFilePath = $FilePath
            return [pscustomobject]@{ ExitCode = 0; Stdout = "posted"; Stderr = "" }
        }

        $null = Publish-RunnerResultComment -IssueNumber 83 -Body "result"
        Write-Host "CAPTURED_FILE_PATH=$script:CapturedFilePath"
        """,
    )
    assert_success(result)
    assert f"CAPTURED_FILE_PATH={tmp_path / 'fallback-gh.exe'}" in result.stdout


def test_tool_resolution_preflight_maybe_status_check_resolves_gh_only(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $Repo = "HarryWhite-TW/local-ai-workbench"
        $RequiredAction = "maybe-status-check"
        $IssueNumber = 0
        $IssueNumbers = @()
        $PostResultComment = $false
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fake-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        $script:VersionProbeCalls = 0
        $script:IssueReadCalls = 0
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }
        function Assert-RepoRoot {}
        function Invoke-ReadOnlyCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            if ($Action -eq "gh --version") {
                $script:VersionProbeCalls += 1
                return [pscustomobject]@{ ExitCode = 0; Stdout = "gh version 2.fake"; Stderr = "" }
            }
            $script:IssueReadCalls += 1
            throw "unexpected read action $Action"
        }
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["protocol"] == "lawb.rv2_03_tool_resolution_preflight.v1"
    assert summary["component"] == "dispatcher"
    assert summary["result"] == "success"
    assert summary["required_action"] == "maybe-status-check"
    assert summary["nested_runner"] is None
    assert summary["tools"]["dispatcher_gh"]["suffix"] == ".exe"
    assert summary["tools"]["dispatcher_gh"]["version_probe"]["ok"] is True
    assert summary["safety"]["pollonce_invoked"] is False
    assert summary["safety"]["github_issue_read_performed"] is False


def _dispatcher_tool_entry(path=r"C:\Tools\gh.exe", suffix=".exe", **overrides):
    entry = {
        "selected_path": path,
        "suffix": suffix,
        "selection_source": "path",
        "version_probe": {
            "executed": True,
            "exit_code": 0,
            "ok": True,
            "safe_message": "ok",
        },
    }
    entry.update(overrides)
    return entry


def _dispatcher_nested_runner(**overrides):
    nested = {
        "protocol": "lawb.rv2_03_tool_resolution_preflight.v1",
        "component": "runner",
        "result": "success",
        "required_action": "run-reviewbundle",
        "blocked_reasons": [],
        "tools": {
            "runner_gh": _dispatcher_tool_entry(r"C:\Tools\gh.exe"),
            "codex": _dispatcher_tool_entry(r"C:\Tools\codex.cmd", ".cmd"),
        },
        "nested_runner": None,
        "safety": {
            "pollonce_invoked": False,
            "dispatcher_action_executed": False,
            "github_issue_read_performed": False,
            "github_write_performed": False,
            "runner_work_invoked": False,
            "codex_task_executed": False,
        },
    }
    nested.update(overrides)
    return nested


def test_tool_resolution_preflight_run_reviewbundle_invokes_runner_preflight_once(tmp_path):
    nested = _dispatcher_nested_runner()
    result = run_dispatcher_core_script(
        tmp_path,
        rf"""
        $Repo = "HarryWhite-TW/local-ai-workbench"
        $RequiredAction = "run-reviewbundle"
        $IssueNumber = 0
        $IssueNumbers = @()
        $PostResultComment = $false
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fake-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        Set-Content -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1") -Value "# runner" -Encoding UTF8
        $script:RunnerPreflightCalls = 0
        function Get-Command {{
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }}
        function Assert-RepoRoot {{}}
        function Invoke-ReadOnlyCommand {{
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            if ($Action -eq "gh --version") {{
                return [pscustomobject]@{{ ExitCode = 0; Stdout = "gh version 2.fake"; Stderr = "" }}
            }}
            if ($Action -eq "runner ToolResolutionPreflight") {{
                $script:RunnerPreflightCalls += 1
                if (($Arguments -join "|") -notmatch "ToolResolutionPreflight") {{
                    throw "Runner preflight flag missing"
                }}
                return [pscustomobject]@{{ ExitCode = 0; Stdout = '{json.dumps(nested)}'; Stderr = "" }}
            }}
            throw "unexpected action $Action"
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "success"
    assert summary["required_action"] == "run-reviewbundle"
    assert summary["nested_runner"]["component"] == "runner"
    assert summary["safety"]["runner_work_invoked"] is False


def test_tool_resolution_preflight_blocks_on_malformed_runner_json(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        r"""
        $Repo = "HarryWhite-TW/local-ai-workbench"
        $RequiredAction = "run-reviewbundle"
        $IssueNumber = 0
        $IssueNumbers = @()
        $PostResultComment = $false
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fake-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        Set-Content -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1") -Value "# runner" -Encoding UTF8
        function Get-Command {
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }
        function Assert-RepoRoot {}
        function Invoke-ReadOnlyCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            if ($Action -eq "gh --version") {
                return [pscustomobject]@{ ExitCode = 0; Stdout = "gh version 2.fake"; Stderr = "" }
            }
            return [pscustomobject]@{ ExitCode = 0; Stdout = "not json"; Stderr = "" }
        }
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "blocked"
    assert "runner_preflight_malformed_json" in summary["blocked_reasons"]


def test_tool_resolution_preflight_preserves_blocked_runner_payload_with_missing_tool(tmp_path):
    nested = _dispatcher_nested_runner(
        result="blocked",
        blocked_reasons=["runner_gh_unavailable"],
        tools={
            "runner_gh": {
                "selected_path": None,
                "suffix": None,
                "selection_source": None,
                "version_probe": None,
            },
            "codex": _dispatcher_tool_entry(r"C:\Tools\codex.cmd", ".cmd"),
        },
    )
    result = run_dispatcher_core_script(
        tmp_path,
        rf"""
        $Repo = "HarryWhite-TW/local-ai-workbench"
        $RequiredAction = "run-reviewbundle"
        $IssueNumber = 0
        $IssueNumbers = @()
        $PostResultComment = $false
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fake-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        Set-Content -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1") -Value "# runner" -Encoding UTF8
        $script:UnexpectedReads = @()
        function Get-Command {{
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }}
        function Assert-RepoRoot {{}}
        function Invoke-ReadOnlyCommand {{
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            if ($Action -eq "gh --version") {{
                return [pscustomobject]@{{ ExitCode = 0; Stdout = "gh version 2.fake"; Stderr = "" }}
            }}
            if ($Action -eq "runner ToolResolutionPreflight") {{
                return [pscustomobject]@{{ ExitCode = 2; Stdout = '{json.dumps(nested)}'; Stderr = "" }}
            }}
            $script:UnexpectedReads += $Action
            throw "unexpected action $Action"
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "blocked"
    assert summary["nested_runner"] == nested
    assert "runner_preflight_blocked" in summary["blocked_reasons"]
    assert "runner_gh_unavailable" in summary["blocked_reasons"]
    assert summary["safety"]["pollonce_invoked"] is False
    assert summary["safety"]["github_issue_read_performed"] is False
    assert summary["safety"]["github_write_performed"] is False
    assert summary["nested_runner"]["safety"]["runner_work_invoked"] is False


@pytest.mark.parametrize(
    ("nested_overrides", "exit_code", "expected_reason"),
    [
        ({"result": "blocked", "blocked_reasons": ["missing"]}, 0, "runner_preflight_blocked_exit_mismatch"),
        ({"result": "success"}, 2, "runner_preflight_success_exit_mismatch"),
        ({"result": "unknown"}, 0, "runner_preflight_invalid_result"),
        ({"blocked_reasons": None}, 0, "runner_preflight_invalid_blocked_reasons"),
        ({"blocked_reasons": "missing"}, 0, "runner_preflight_invalid_blocked_reasons"),
        ({"result": "blocked", "blocked_reasons": [7]}, 2, "runner_preflight_invalid_blocked_reasons"),
        ({"blocked_reasons": ["   "]}, 0, "runner_preflight_invalid_blocked_reasons"),
        ({"nested_runner": {"result": "success"}}, 0, "runner_preflight_unexpected_nested_runner"),
        ({"safety": None}, 0, "runner_preflight_missing_safety"),
        ({"safety": {"pollonce_invoked": False, "dispatcher_action_executed": False, "github_issue_read_performed": False, "github_write_performed": False, "runner_work_invoked": False}}, 0, "runner_preflight_safety_contradiction_codex_task_executed"),
        ({"tools": None}, 0, "runner_preflight_missing_tools"),
        ({"tools": {}}, 0, "runner_preflight_runner_gh_missing"),
        ({"tools": {"codex": _dispatcher_tool_entry(r"C:\Tools\codex.exe")}}, 0, "runner_preflight_runner_gh_missing"),
        ({"tools": {"runner_gh": _dispatcher_tool_entry(), "codex": _dispatcher_tool_entry(version_probe=None)}}, 0, "runner_preflight_codex_missing_version_probe"),
        ({"tools": {"runner_gh": _dispatcher_tool_entry(), "codex": _dispatcher_tool_entry(version_probe={"exit_code": 0, "ok": True, "safe_message": "ok"})}}, 0, "runner_preflight_codex_version_probe_not_executed"),
        (
            {"tools": {"runner_gh": _dispatcher_tool_entry(version_probe={"executed": True, "exit_code": 0, "ok": False, "safe_message": "ok"}), "codex": _dispatcher_tool_entry(r"C:\Tools\codex.exe")}},
            0,
            "runner_preflight_runner_gh_version_probe_not_ok",
        ),
        (
            {"tools": {"runner_gh": _dispatcher_tool_entry(version_probe={"executed": True, "exit_code": 1, "ok": True, "safe_message": "ok"}), "codex": _dispatcher_tool_entry(r"C:\Tools\codex.exe")}},
            0,
            "runner_preflight_runner_gh_version_probe_nonzero_exit",
        ),
        ({"tools": {"runner_gh": _dispatcher_tool_entry(r"C:\Tools\gh.ps1", ".ps1"), "codex": _dispatcher_tool_entry(r"C:\Tools\codex.exe")}}, 0, "runner_preflight_runner_gh_unsafe_suffix"),
        ({"tools": {"runner_gh": _dispatcher_tool_entry(r"C:\Tools\gh.exe", ".cmd"), "codex": _dispatcher_tool_entry(r"C:\Tools\codex.exe")}}, 0, "runner_preflight_runner_gh_suffix_path_mismatch"),
        ({"result": "success", "blocked_reasons": ["unexpected"]}, 0, "runner_preflight_success_with_blocked_reasons"),
        ({"result": "blocked", "blocked_reasons": []}, 2, "runner_preflight_blocked_without_reasons"),
    ],
)
def test_tool_resolution_preflight_blocks_on_contradictory_runner_contract(
    tmp_path, nested_overrides, exit_code, expected_reason
):
    nested = _dispatcher_nested_runner(**nested_overrides)
    result = run_dispatcher_core_script(
        tmp_path,
        rf"""
        $Repo = "HarryWhite-TW/local-ai-workbench"
        $RequiredAction = "run-reviewbundle"
        $IssueNumber = 0
        $IssueNumbers = @()
        $PostResultComment = $false
        $GhCliFallbackPath = Join-Path -Path $PSScriptRoot -ChildPath "fake-gh.exe"
        New-Item -ItemType File -Path $GhCliFallbackPath -Force | Out-Null
        Set-Content -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1") -Value "# runner" -Encoding UTF8
        function Get-Command {{
            param([string]$Name, [switch]$All, [object]$ErrorAction)
            return $null
        }}
        function Assert-RepoRoot {{}}
        function Invoke-ReadOnlyCommand {{
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            if ($Action -eq "gh --version") {{
                return [pscustomobject]@{{ ExitCode = 0; Stdout = "gh version 2.fake"; Stderr = "" }}
            }}
            return [pscustomobject]@{{ ExitCode = {exit_code}; Stdout = '{json.dumps(nested)}'; Stderr = "" }}
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "blocked"
    assert expected_reason in summary["blocked_reasons"]


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        ("$script:Markers = @()", "No current dispatch marker found"),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine)), (New-TestMarker (New-DispatchLine -RequestId "req-84") -Id "comment-2"))',
            "Ambiguous dispatch markers",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Expires "20200101T000000Z")))',
            "Latest marker expired",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -RepoValue "Other/repo")))',
            "field 'repo' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Branch "feature")))',
            "field 'branch' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Head "2222222222222222222222222222222222222222")))',
            "field 'head' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Issue "84")))',
            "field 'issue' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "unknown-action")))',
            "Unsupported dispatch action",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "read-final-audit")))',
            "Reserved dispatch action",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "commit")))',
            "Forbidden dispatch action",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "push")))',
            "Forbidden dispatch action",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "close")))',
            "Forbidden dispatch action",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "push-approved-once")))',
            "Forbidden dispatch action",
        ),
        (
            '$script:IssueStates[83] = "CLOSED"; $script:Markers = @((New-TestMarker (New-DispatchLine)))',
            "Target issue #83 is not OPEN.",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine) -AuthorLogin "outsider"))',
            "Dispatch marker author 'outsider' is not trusted.",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -RequestedBy "human")))',
            "Dispatch marker field 'requested_by' mismatch.",
        ),
    ],
)
def test_fail_closed_cases_do_not_post_comments(tmp_path, setup, expected):
    result = run_case(tmp_path, setup, post=True)
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert expected in result.stdout
    assert "POST_CALLS=0" in result.stdout
    assert "FORBIDDEN_CALLS=0" in result.stdout


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=20990101T000000Z requested_by=chatgpt", "Missing required dispatch marker field 'request_id'"),
        ("CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=20990101T000000Z requested_by=chatgpt request_id=req-83 issue=83", "Duplicate dispatch marker field 'issue'"),
        ("CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=20990101T000000Z requested_by=chatgpt request_id=req-83 unexpected=1", "Unknown dispatch marker field 'unexpected'"),
        ("CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=not-a-date requested_by=chatgpt request_id=req-83", "expires value 'not-a-date' is malformed"),
        ("CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=20260230T000000Z requested_by=chatgpt request_id=req-83", "is not a valid UTC timestamp"),
        ("CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check bad-field issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=20990101T000000Z requested_by=chatgpt request_id=req-83", "Malformed dispatch marker field"),
    ],
)
def test_malformed_markers_fail_closed_without_posting(tmp_path, line, expected):
    result = run_case(
        tmp_path,
        f'$script:Markers = @((New-TestMarker "{line}"))',
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert expected in result.stdout
    assert "POST_CALLS=0" in result.stdout


def test_read_result_rejects_embedded_marker_from_github_shape(tmp_path):
    result = run_dispatcher_script(
        tmp_path,
        """
        function Invoke-ReadOnlyCommand {
            param([string]$FilePath, [string[]]$Arguments, [string]$Action)
            $line = New-DispatchLine
            $body = "Before`n$line`nAfter"
            $payload = [pscustomobject]@{
                number = 83
                title = "Issue 83"
                state = "OPEN"
                comments = @((New-TestComment -Body $body))
            } | ConvertTo-Json -Depth 8
            return [pscustomobject]@{ ExitCode = 0; Stdout = $payload; Stderr = "" }
        }
        try {
            $null = Get-IssueDispatchMarkerReadResult -IssueNumber 83
            Write-Host "CASE_RESULT=success"
        } catch {
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }
        Write-Host "POST_CALLS=$script:PostCalls"
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "standalone issue comment line" in result.stdout
    assert "POST_CALLS=0" in result.stdout


def test_dirty_status_still_succeeds_as_read_only_warning(tmp_path):
    result = run_case(
        tmp_path,
        '$script:GitStatus = " M docs/RUNNER_V2.md"; $script:Markers = @((New-TestMarker (New-DispatchLine)))',
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    summary = extract_summary(result.stdout)
    assert summary["validations"]["git_status_clean"]["status"] == "warning"
    assert summary["observations"]["final_head_matches_initial"] is True


def test_post_result_comment_failure_is_reported_after_stdout_summary(tmp_path):
    result = run_dispatcher_script(
        tmp_path,
        """
        $script:Markers = @((New-TestMarker (New-DispatchLine)))
        $PostResultComment = $true
        function Publish-RunnerResultComment {
            param([int]$IssueNumber, [string]$Body)
            $script:PostCalls += 1
            throw "mock post failed"
        }
        try {
            Invoke-PollOnce
            Write-Host "CASE_RESULT=success"
        } catch {
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }
        Write-Host "POST_CALLS=$script:PostCalls"
        """,
    )
    assert_success(result)
    assert MARKER in result.stdout
    assert "CASE_RESULT=failure" in result.stdout
    assert "mock post failed" in result.stdout
    assert "POST_CALLS=1" in result.stdout


def test_dry_run_single_issue_reports_would_happen_without_action_or_post(tmp_path):
    result = run_dry_case(
        tmp_path,
        """
        $IssueNumber = 83
        $script:Markers = @((New-TestMarker (New-DispatchLine)))
        function Invoke-MaybeStatusCheck {
            throw "dry-run must not execute maybe-status-check"
        }
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "POST_CALLS=0" in result.stdout
    assert "FORBIDDEN_CALLS=0" in result.stdout
    assert DRY_RUN_MARKER in result.stdout

    summary = extract_summary_after(result.stdout, DRY_RUN_MARKER)
    assert summary["schema"] == "lawb.dispatch_dry_run.v1"
    assert summary["poll_mode"] == "dry_run_bounded"
    assert summary["result"] == "success"
    assert summary["issues"] == [83]
    assert summary["decisions"][0]["decision"] == "accepted"
    assert summary["decisions"][0]["action"] == "maybe-status-check"
    assert summary["decisions"][0]["request_id"] == "req-83"
    assert summary["decisions"][0]["would_execute_dispatch_action"] is False
    assert summary["dry_run_facts"]["result_comment_invoked"] is False


def test_dry_run_accepts_run_reviewbundle_without_delegating_to_runner(tmp_path):
    result = run_dry_case(
        tmp_path,
        """
        $IssueNumber = 83
        $script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle" -RequestId "req-rb-83")))
        function Invoke-ReviewBundle {
            throw "dry-run must not execute runner v1 ReviewBundle"
        }
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "POST_CALLS=0" in result.stdout
    summary = extract_summary_after(result.stdout, DRY_RUN_MARKER)
    assert summary["result"] == "success"
    assert summary["decisions"][0]["action"] == "run-reviewbundle"
    assert summary["decisions"][0]["request_id"] == "req-rb-83"
    assert summary["decisions"][0]["would_execute_dispatch_action"] is False


def test_dry_run_bounded_issue_list_accepts_up_to_three_explicit_issues(tmp_path):
    result = run_dry_case(
        tmp_path,
        """
        $IssueNumber = 0
        $IssueNumbers = @(83, 84, 85)
        $script:IssueMarkers[83] = @((New-TestMarker (New-DispatchLine -Issue "83" -RequestId "req-83")))
        $script:IssueMarkers[84] = @((New-TestMarker (New-DispatchLine -Issue "84" -RequestId "req-84")))
        $script:IssueMarkers[85] = @((New-TestMarker (New-DispatchLine -Issue "85" -RequestId "req-85")))
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    summary = extract_summary_after(result.stdout, DRY_RUN_MARKER)
    assert summary["issues"] == [83, 84, 85]
    assert [decision["decision"] for decision in summary["decisions"]] == ["accepted", "accepted", "accepted"]
    assert [decision["request_id"] for decision in summary["decisions"]] == ["req-83", "req-84", "req-85"]


def test_dry_run_rejects_too_many_issues_before_reading_github(tmp_path):
    result = run_dry_case(
        tmp_path,
        """
        $IssueNumber = 0
        $IssueNumbers = @(83, 84, 85, 86)
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "at most 3 explicit issues" in result.stdout
    assert DRY_RUN_MARKER not in result.stdout
    assert "POST_CALLS=0" in result.stdout
    assert "FORBIDDEN_CALLS=0" in result.stdout


def test_dry_run_reports_rejected_issue_and_fails_closed_without_posting(tmp_path):
    result = run_dry_case(
        tmp_path,
        """
        $IssueNumber = 83
        $script:Markers = @((New-TestMarker (New-DispatchLine -Action "push")))
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "DryRunBoundedPoll failed closed" in result.stdout
    assert "POST_CALLS=0" in result.stdout

    summary = extract_summary_after(result.stdout, DRY_RUN_MARKER)
    assert summary["result"] == "failure"
    assert summary["decisions"][0]["decision"] == "rejected"
    assert "Forbidden dispatch action 'push'" in summary["decisions"][0]["reason"]


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine)), (New-TestMarker (New-DispatchLine -RequestId "req-84") -Id "comment-2"))',
            "Ambiguous dispatch markers",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Expires "20200101T000000Z")))',
            "Latest marker expired",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -RepoValue "Other/repo")))',
            "field 'repo' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Branch "feature")))',
            "field 'branch' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Head "2222222222222222222222222222222222222222")))',
            "field 'head' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Issue "84")))',
            "field 'issue' mismatch",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "unknown-action")))',
            "Unsupported dispatch action",
        ),
        (
            '$script:Markers = @((New-TestMarker "CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=maybe-status-check issue=83 repo=HarryWhite-TW/local-ai-workbench branch=master head=1111111111111111111111111111111111111111 expires=20990101T000000Z requested_by=chatgpt"))',
            "Missing required dispatch marker field 'request_id'",
        ),
        (
            '$script:IssueStates[83] = "CLOSED"; $script:Markers = @((New-TestMarker (New-DispatchLine)))',
            "Target issue #83 is not OPEN.",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine) -AuthorLogin "outsider"))',
            "Dispatch marker author 'outsider' is not trusted.",
        ),
        (
            '$script:Markers = @((New-TestMarker (New-DispatchLine -RequestedBy "outsider")))',
            "Dispatch marker field 'requested_by' mismatch.",
        ),
    ],
)
def test_dry_run_marker_validation_failures_are_reported_without_posting(tmp_path, setup, expected):
    result = run_dry_case(tmp_path, f"$IssueNumber = 83; {setup}")
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "POST_CALLS=0" in result.stdout
    summary = extract_summary_after(result.stdout, DRY_RUN_MARKER)
    assert summary["result"] == "failure"
    assert summary["decisions"][0]["decision"] == "rejected"
    assert expected in summary["decisions"][0]["reason"]


def test_dry_run_existing_matching_result_fails_closed_as_already_handled(tmp_path):
    result = run_dry_case(
        tmp_path,
        """
        $IssueNumber = 83
        $line = New-DispatchLine
        $resultJson = @{
            schema = "lawb.runner_result.v1"
            repo = "HarryWhite-TW/local-ai-workbench"
            issue = 83
            action = "maybe-status-check"
            branch = $script:Branch
            head = $script:Head
            request_id = "req-83"
        } | ConvertTo-Json
        $resultBody = "$RunnerResultMarker`n$resultJson"
        $script:Markers = @(
            (New-TestMarker $line),
            (New-TestMarker -Line $RunnerResultMarker -Body $resultBody -Id "result-1")
        )
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    summary = extract_summary_after(result.stdout, DRY_RUN_MARKER)
    assert summary["decisions"][0]["decision"] == "rejected"
    assert "Matching LAWBRUNNER-RESULT already exists" in summary["decisions"][0]["reason"]


def test_bounded_poll_single_issue_executes_maybe_status_check_and_posts_when_requested(tmp_path):
    result = run_bounded_case(
        tmp_path,
        """
        $IssueNumber = 83
        $script:Markers = @((New-TestMarker (New-DispatchLine)))
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "POST_CALLS=1" in result.stdout
    assert "POSTED_ISSUE=83" in result.stdout
    assert MARKER in result.stdout

    summary = extract_summary(result.stdout)
    assert summary["issue"] == 83
    assert summary["selected_issue"] == 83
    assert summary["action"] == "maybe-status-check"
    assert summary["request_id"] == "req-83"
    assert summary["poll_mode"] == "BoundedPoll"
    assert summary["trusted_parent_actions"]["push_invoked"] is False

    posted_body = extract_posted_body(result.stdout)
    assert posted_body.startswith(MARKER + "\n")
    assert json.loads(posted_body.split("\n", 1)[1]) == summary


def test_bounded_poll_issue_list_accepts_up_to_three_and_posts_one_result_per_issue(tmp_path):
    result = run_bounded_case(
        tmp_path,
        """
        $IssueNumber = 0
        $IssueNumbers = @(83, 84, 85)
        $script:IssueMarkers[83] = @((New-TestMarker (New-DispatchLine -Issue "83" -RequestId "req-83")))
        $script:IssueMarkers[84] = @((New-TestMarker (New-DispatchLine -Issue "84" -RequestId "req-84")))
        $script:IssueMarkers[85] = @((New-TestMarker (New-DispatchLine -Issue "85" -RequestId "req-85")))
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=success" in result.stdout
    assert "POST_CALLS=3" in result.stdout
    assert result.stdout.count(MARKER) == 3
    assert "Issue #83: accepted bounded-poll selection" in result.stdout
    assert "Issue #84: accepted bounded-poll selection" in result.stdout
    assert "Issue #85: accepted bounded-poll selection" in result.stdout


def test_bounded_poll_rejects_too_many_issues_before_reading_github(tmp_path):
    result = run_bounded_case(
        tmp_path,
        """
        $IssueNumber = 0
        $IssueNumbers = @(83, 84, 85, 86)
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "at most 3 explicit issues" in result.stdout
    assert MARKER not in result.stdout
    assert "POST_CALLS=0" in result.stdout
    assert "FORBIDDEN_CALLS=0" in result.stdout


def test_bounded_poll_existing_matching_result_fails_closed_before_action_or_post(tmp_path):
    result = run_bounded_case(
        tmp_path,
        """
        $IssueNumber = 83
        $line = New-DispatchLine
        $resultJson = @{
            schema = "lawb.runner_result.v1"
            repo = "HarryWhite-TW/local-ai-workbench"
            issue = 83
            action = "maybe-status-check"
            branch = $script:Branch
            head = $script:Head
            request_id = "req-83"
        } | ConvertTo-Json
        $resultBody = "$RunnerResultMarker`n$resultJson"
        $script:Markers = @(
            (New-TestMarker $line),
            (New-TestMarker -Line $RunnerResultMarker -Body $resultBody -Id "result-1")
        )
        function Invoke-MaybeStatusCheck {
            throw "bounded poll must not execute already-handled dispatch"
        }
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "Matching LAWBRUNNER-RESULT already exists" in result.stdout
    assert "BoundedPoll failed closed before action execution" in result.stdout
    assert MARKER not in result.stdout
    assert "POST_CALLS=0" in result.stdout


def test_bounded_poll_marker_validation_failure_prevents_all_action_execution(tmp_path):
    result = run_bounded_case(
        tmp_path,
        """
        $IssueNumber = 0
        $IssueNumbers = @(83, 84)
        $script:IssueMarkers[83] = @((New-TestMarker (New-DispatchLine -Issue "83" -RequestId "req-83")))
        $script:IssueMarkers[84] = @((New-TestMarker (New-DispatchLine -Issue "84" -RequestId "req-84" -Action "push")))
        function Invoke-MaybeStatusCheck {
            throw "bounded poll must not execute when any scoped issue is rejected"
        }
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "Forbidden dispatch action 'push'" in result.stdout
    assert "BoundedPoll failed closed before action execution" in result.stdout
    assert MARKER not in result.stdout
    assert "POST_CALLS=0" in result.stdout


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (
            '$script:IssueStates[84] = "CLOSED"; $script:IssueMarkers[84] = @((New-TestMarker (New-DispatchLine -Issue "84" -RequestId "req-84")))',
            "Target issue #84 is not OPEN.",
        ),
        (
            '$script:IssueMarkers[84] = @((New-TestMarker (New-DispatchLine -Issue "84" -RequestId "req-84") -AuthorLogin "outsider"))',
            "Dispatch marker author 'outsider' is not trusted.",
        ),
        (
            '$script:IssueMarkers[84] = @((New-TestMarker (New-DispatchLine -Issue "84" -RequestId "req-84" -RequestedBy "human")))',
            "Dispatch marker field 'requested_by' mismatch.",
        ),
    ],
)
def test_bounded_poll_trust_boundary_rejection_prevents_all_action_execution(tmp_path, setup, expected):
    result = run_bounded_case(
        tmp_path,
        f"""
        $IssueNumber = 0
        $IssueNumbers = @(83, 84)
        $script:IssueMarkers[83] = @((New-TestMarker (New-DispatchLine -Issue "83" -RequestId "req-83")))
        {setup}
        function Invoke-MaybeStatusCheck {{
            throw "bounded poll must not execute when any scoped issue is rejected"
        }}
        """,
        post=True,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert expected in result.stdout
    assert "BoundedPoll failed closed before action execution" in result.stdout
    assert MARKER not in result.stdout
    assert "POST_CALLS=0" in result.stdout


def test_script_entry_rejects_post_result_comment_without_pollonce(tmp_path):
    result = _run_powershell(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DISPATCHER),
            "-PostResultComment",
            "-IssueNumber",
            "83",
        ]
    )
    assert result.returncode != 0
    assert _process_output_contains(
        result,
        "Missing mode.",
        allow_single_hard_wrap=True,
    )


def test_script_entry_rejects_tool_resolution_preflight_with_other_mode():
    result = _run_powershell(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DISPATCHER),
            "-ToolResolutionPreflight",
            "-PollOnce",
            "-RequiredAction",
            "maybe-status-check",
        ]
    )
    assert result.returncode != 0
    assert _process_output_contains(
        result,
        "Choose exactly one mode",
        allow_single_hard_wrap=True,
    )


def test_tool_resolution_preflight_rejects_issue_arguments_before_reads(tmp_path):
    result = run_dispatcher_core_script(
        tmp_path,
        """
        $Repo = "HarryWhite-TW/local-ai-workbench"
        $RequiredAction = "maybe-status-check"
        $IssueNumber = 83
        $IssueNumbers = @()
        $PostResultComment = $false
        function Get-IssueDispatchMarkerReadResult { throw "issue read must not happen" }
        try {
            Invoke-ToolResolutionPreflight
        } catch {
            Write-Host "CASE_RESULT=failure"
            Write-Host "CASE_ERROR=$($_.Exception.Message)"
        }
        """,
    )
    assert_success(result)
    assert "CASE_RESULT=failure" in result.stdout
    assert "does not accept IssueNumber" in result.stdout
