import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = REPO_ROOT / "scripts" / "local_dispatcher_v1.ps1"
MARKER = "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1"
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
            $PostResultComment = $false
            $script:Branch = "master"
            $script:Head = "{HEAD}"
            $script:GitStatus = ""
            $script:Markers = @()
            $script:PostCalls = 0
            $script:PostedIssue = 0
            $script:PostedBody = ""
            $script:ForbiddenCalls = @()

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
                $comments = @($script:Markers | ForEach-Object {{ $_.Comment }})
                $payload = [pscustomobject]@{{
                    number = $IssueNumber
                    title = "Issue $IssueNumber"
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
    lines = stdout.splitlines()
    marker_index = lines.index(MARKER)
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
            '$script:Markers = @((New-TestMarker (New-DispatchLine -Action "run-reviewbundle")))',
            "Reserved dispatch action",
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
