import json
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
            $script:Branch = "master"
            $script:Head = "{HEAD}"
            $script:GitStatus = ""
            $script:Markers = @()
            $script:IssueMarkers = @{{}}
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
            Set-Content -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath "local_runner_v1.ps1") -Value "# runner stub" -Encoding UTF8

            function New-TestComment {{
                param(
                    [Parameter(Mandatory = $true)][string]$Body,
                    [string]$Id = "comment-1"
                )
                return [pscustomobject]@{{
                    id = $Id
                    author = [pscustomobject]@{{ login = "tester" }}
                    createdAt = "2026-05-18T00:00:00Z"
                    body = $Body
                }}
            }}

            function New-TestMarker {{
                param(
                    [Parameter(Mandatory = $true)][string]$Line,
                    [string]$Body = $null,
                    [string]$Id = "comment-1"
                )
                if ([string]::IsNullOrEmpty($Body)) {{
                    $Body = $Line
                }}
                return [pscustomobject]@{{
                    Line = $Line
                    Comment = (New-TestComment -Body $Body -Id $Id)
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
            function Assert-GhAvailable {{}}
            function Get-CurrentBranch {{ return $script:Branch }}
            function Get-CurrentFullHead {{ return $script:Head }}
            function Get-GitStatusShort {{ return $script:GitStatus }}
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
                $requestedIssue = [int]$Arguments[2]
                $sourceMarkers = $script:Markers
                if ($script:IssueMarkers.ContainsKey($requestedIssue)) {{
                    $sourceMarkers = @($script:IssueMarkers[$requestedIssue])
                }}
                $comments = @($sourceMarkers | ForEach-Object {{ $_.Comment }})
                $payload = [pscustomobject]@{{
                    number = $requestedIssue
                    title = "Issue $requestedIssue"
                    state = "OPEN"
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
    return subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
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
            $script:ForbiddenCalls = @()
            function git {{ $script:ForbiddenCalls += "git" }}
            function gh {{ $script:ForbiddenCalls += "gh" }}
            """
        )
        + "\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    return subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def assert_success(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def extract_summary(stdout: str) -> dict:
    return extract_summary_after(stdout, MARKER)


def extract_summary_after(stdout: str, marker: str) -> dict:
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
    assert "RUNNER_ARGS=-IssueNumber|83|-Mode|ReviewBundle" in result.stdout
    assert "local_runner_v1.ps1" in result.stdout
    assert "runner v1 review bundle ok" in result.stdout

    summary = extract_summary(result.stdout)
    assert summary["action"] == "run-reviewbundle"
    assert summary["issue"] == 83
    assert summary["selected_issue"] == 83
    assert summary["request_id"] == "req-rb-83"
    assert summary["result"] == "success"
    assert summary["validations"]["git_status_clean"]["status"] == "passed"
    assert summary["safety"]["no_commit"] is True


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
            -SelectedIssue 83
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
    assert summary["safety"]["no_commit"] is True


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
    assert summary["safety"]["no_result_comment"] is True


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
    assert summary["safety"]["no_push"] is True

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


def test_script_entry_rejects_post_result_comment_without_pollonce(tmp_path):
    result = subprocess.run(
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
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Missing mode" in (result.stdout + result.stderr)
