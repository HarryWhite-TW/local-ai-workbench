import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v2.ps1"


def _runner_core() -> str:
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index("\ntry {")
    return source[start:end]


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local_runner_v2 tests")
    return shell


def run_close_issue_once_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "close_issue_once_test.ps1"
    script.write_text(
        _runner_core()
        + textwrap.dedent(
            """

            $script:IssueState = "OPEN"
            $script:FinalIssueState = "CLOSED"
            $script:CloseCalls = 0
            $script:CloseExitCode = 0
            $script:CloseStdout = "closed"
            $script:CloseStderr = ""
            $script:LocalHead = "1111111111111111111111111111111111111111"
            $script:RemoteHead = "1111111111111111111111111111111111111111"
            $script:Pushed = "1111111111111111111111111111111111111111"
            $script:RemoteNames = @("origin")
            $script:RemoteUrl = "https://github.com/HarryWhite-TW/local-ai-workbench.git"
            $script:Upstream = "origin/master"
            $script:Branch = "master"
            $script:Markers = @()
            $Repo = "HarryWhite-TW/local-ai-workbench"

            function New-TestMarker {
                param(
                    [Parameter(Mandatory = $true)][string]$Line,
                    [string]$Body,
                    [object]$Comment
                )
                if ([string]::IsNullOrEmpty($Body)) {
                    $Body = $Line
                }
                if ($null -eq $Comment) {
                    $Comment = [pscustomobject]@{
                        id = "comment-1"
                        author = [pscustomobject]@{ login = "tester" }
                        createdAt = "2026-05-16T00:00:00Z"
                        body = $Body
                    }
                }
                return [pscustomobject]@{
                    Line = $Line
                    Comment = $Comment
                    CommentIndex = 1
                    LineNumber = 1
                }
            }

            function New-CloseMarkerLine {
                param(
                    [string]$Issue = "74",
                    [string]$Target = "74",
                    [string]$Expires = "20990101T000000Z",
                    [string]$TargetState = "OPEN",
                    [string]$LocalHead = $script:LocalHead,
                    [string]$RemoteHead = $script:RemoteHead,
                    [string]$Pushed = $script:Pushed
                )
                return "RUNNER-V2-APPROVE protocol=v2.approval.1 action=close-issue-approved-once issue=$Issue repo=HarryWhite-TW/local-ai-workbench target=$Target targetstate=$TargetState branch=$script:Branch localhead=$LocalHead remote=origin upstream=$script:Upstream remotehead=$RemoteHead pushed=$Pushed expires=$Expires"
            }

            function Assert-RepoRoot {}
            function Assert-GhAvailable {}
            function Assert-CleanRepo { return [pscustomobject]@{ Summary = "clean" } }
            function Get-CurrentBranch { return $script:Branch }
            function Get-CurrentFullHead { return $script:LocalHead }
            function Get-RemoteNames { return @($script:RemoteNames) }
            function Get-RemoteBranchHead { param([string]$Remote, [string]$BranchName) return $script:RemoteHead }
            function Write-FinalGitStatus {}
            function Invoke-GhIssueCloseOnce {
                param([int]$IssueNumber)
                $script:CloseCalls += 1
                return [pscustomobject]@{
                    ExitCode = $script:CloseExitCode
                    Stdout = $script:CloseStdout
                    Stderr = $script:CloseStderr
                }
            }
            function Get-GitOutput {
                param([string[]]$GitArgs, [string]$Action)
                $joined = $GitArgs -join " "
                if ($joined -eq "diff --cached --name-only") { return "" }
                if ($joined -eq "remote get-url origin") { return $script:RemoteUrl }
                if ($joined -eq "rev-parse --abbrev-ref --symbolic-full-name @{u}") { return $script:Upstream }
                throw "Unexpected git command in test: $joined"
            }
            function Get-IssueApprovalMarkerReadResult {
                param([int]$IssueNumber)
                $state = if ($script:CloseCalls -gt 0) { $script:FinalIssueState } else { $script:IssueState }
                return [pscustomobject]@{
                    IssueNumber = $IssueNumber
                    Title = "Issue $IssueNumber"
                    IssueState = $state
                    Markers = @($script:Markers)
                }
            }

            function Assert-Contains {
                param([string]$Text, [string]$Expected)
                if (-not $Text.Contains($Expected)) {
                    throw "Expected text to contain '$Expected', found '$Text'"
                }
            }
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


def test_historical_malformed_non_close_marker_is_skipped_with_valid_close(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Markers = @(
            (New-TestMarker "RUNNER-V2-APPROVE action=push-approved-once push=legacy"),
            (New-TestMarker (New-CloseMarkerLine))
        )
        $selection = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
        if ($selection.Selected.Marker.Line -ne (New-CloseMarkerLine)) { throw "Wrong marker selected" }
        if (@($selection.SkippedNonCloseMarkers).Count -ne 1) { throw "Expected one skipped non-close marker" }
        if ($script:CloseCalls -ne 0) { throw "Selection must not close issues" }
        """,
    )
    assert_success(result)


def test_historical_close_marker_example_inside_code_block_is_skipped_with_valid_close(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $example = "RUNNER-V2-APPROVE protocol=v2.approval.1 action=close-issue-approved-once issue=77 repo=HarryWhite-TW/local-ai-workbench target=77 targetstate=OPEN branch=master localhead=<HEAD> remote=origin upstream=origin/master remotehead=<HEAD> pushed=<HEAD> expires=<UTC_BASIC>"
        $body = '```text' + "`n" + $example + "`n" + '```'
        $script:Markers = @(
            (New-TestMarker $example -Body $body),
            (New-TestMarker (New-CloseMarkerLine))
        )
        $selection = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
        if ($selection.Selected.Marker.Line -ne (New-CloseMarkerLine)) { throw "Wrong marker selected" }
        if (@($selection.SkippedIneligibleMarkers).Count -ne 1) { throw "Expected one skipped ineligible marker" }
        if (@($selection.SkippedNonCloseMarkers).Count -ne 0) { throw "Expected no skipped non-close markers" }
        if ($script:CloseCalls -ne 0) { throw "Selection must not close issues" }
        """,
    )
    assert_success(result)


def test_historical_close_marker_example_inside_longer_comment_is_skipped_with_valid_close(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $example = "RUNNER-V2-APPROVE protocol=v2.approval.1 action=close-issue-approved-once issue=77 repo=HarryWhite-TW/local-ai-workbench target=77 targetstate=OPEN branch=master localhead=<HEAD> remote=origin upstream=origin/master remotehead=<HEAD> pushed=<HEAD> expires=<UTC_BASIC>"
        $script:Markers = @(
            (New-TestMarker $example -Body "Design note:`n$example`nEnd note."),
            (New-TestMarker (New-CloseMarkerLine))
        )
        $selection = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
        if ($selection.Selected.Marker.Line -ne (New-CloseMarkerLine)) { throw "Wrong marker selected" }
        if (@($selection.SkippedIneligibleMarkers).Count -ne 1) { throw "Expected one skipped ineligible marker" }
        if ($script:CloseCalls -ne 0) { throw "Selection must not close issues" }
        """,
    )
    assert_success(result)


def test_historical_close_marker_example_from_issue_body_is_skipped_with_valid_close(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $example = "RUNNER-V2-APPROVE protocol=v2.approval.1 action=close-issue-approved-once issue=77 repo=HarryWhite-TW/local-ai-workbench target=77 targetstate=OPEN branch=master localhead=<HEAD> remote=origin upstream=origin/master remotehead=<HEAD> pushed=<HEAD> expires=<UTC_BASIC>"
        $script:Markers = @(
            (New-TestMarker $example -Comment $null -Body $null),
            (New-TestMarker (New-CloseMarkerLine))
        )
        $script:Markers[0].Comment = $null
        $selection = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
        if ($selection.Selected.Marker.Line -ne (New-CloseMarkerLine)) { throw "Wrong marker selected" }
        if (@($selection.SkippedIneligibleMarkers).Count -ne 1) { throw "Expected one skipped ineligible marker" }
        if ($script:CloseCalls -ne 0) { throw "Selection must not close issues" }
        """,
    )
    assert_success(result)


def test_malformed_close_marker_still_fails_closed(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Markers = @(
            (New-TestMarker "$(New-CloseMarkerLine) unexpected=field")
        )
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected malformed close marker to fail"
        } catch {
            Assert-Contains $_.Exception.Message "Unknown approval marker field 'unexpected'"
        }
        if ($script:CloseCalls -ne 0) { throw "Failed validation must not close issues" }
        """,
    )
    assert_success(result)


def test_valid_close_happy_path_closes_exactly_one_mocked_issue(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $IssueNumber = 74
        $script:Markers = @((New-TestMarker (New-CloseMarkerLine)))
        Invoke-CloseIssueOnce
        if ($script:CloseCalls -ne 1) { throw "Expected exactly one mocked close call" }
        """,
    )
    assert_success(result)


def test_duplicate_current_close_markers_fail_closed(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Markers = @(
            (New-TestMarker (New-CloseMarkerLine)),
            (New-TestMarker (New-CloseMarkerLine))
        )
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected duplicate close markers to fail"
        } catch {
            Assert-Contains $_.Exception.Message "Ambiguous close approvals"
        }
        if ($script:CloseCalls -ne 0) { throw "Failed validation must not close issues" }
        """,
    )
    assert_success(result)


def test_expired_close_marker_fails_closed(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Markers = @((New-TestMarker (New-CloseMarkerLine -Expires "20200101T000000Z")))
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected expired close marker to fail"
        } catch {
            Assert-Contains $_.Exception.Message "Latest close marker expired"
        }
        if ($script:CloseCalls -ne 0) { throw "Failed validation must not close issues" }
        """,
    )
    assert_success(result)


def test_wrong_actions_cannot_authorize_close(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Markers = @(
            (New-TestMarker "RUNNER-V2-APPROVE protocol=v2.approval.1 action=push-approved-once issue=74 repo=HarryWhite-TW/local-ai-workbench branch=master push=legacy expires=20990101T000000Z")
        )
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected wrong action to fail"
        } catch {
            Assert-Contains $_.Exception.Message "No matching approval was found"
        }
        if ($script:CloseCalls -ne 0) { throw "Wrong action must not close issues" }
        """,
    )
    assert_success(result)


def test_target_mismatch_fails_closed(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Markers = @((New-TestMarker (New-CloseMarkerLine -Target "75")))
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected target mismatch to fail"
        } catch {
            Assert-Contains $_.Exception.Message "field 'target' mismatch"
        }
        if ($script:CloseCalls -ne 0) { throw "Failed validation must not close issues" }
        """,
    )
    assert_success(result)


def test_already_closed_issue_fails_closed(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:IssueState = "CLOSED"
        $script:Markers = @((New-TestMarker (New-CloseMarkerLine)))
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected already closed issue to fail"
        } catch {
            Assert-Contains $_.Exception.Message "must be currently OPEN"
        }
        if ($script:CloseCalls -ne 0) { throw "Failed validation must not close issues" }
        """,
    )
    assert_success(result)


def test_local_remote_pushed_mismatch_fails_closed(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $script:Pushed = "2222222222222222222222222222222222222222"
        $script:Markers = @((New-TestMarker (New-CloseMarkerLine -Pushed $script:Pushed)))
        try {
            $null = Get-ValidatedCloseIssueOnceSelection -IssueNumber 74 -NowUtc ([datetime]"2026-05-16T00:00:00Z")
            throw "Expected pushed mismatch to fail"
        } catch {
            Assert-Contains $_.Exception.Message "field 'pushed' mismatch"
        }
        if ($script:CloseCalls -ne 0) { throw "Failed validation must not close issues" }
        """,
    )
    assert_success(result)


def test_close_api_failure_reports_failure_without_claiming_success(tmp_path):
    result = run_close_issue_once_script(
        tmp_path,
        """
        $IssueNumber = 74
        $script:CloseExitCode = 1
        $script:CloseStdout = ""
        $script:CloseStderr = "api failed"
        $script:Markers = @((New-TestMarker (New-CloseMarkerLine)))
        try {
            Invoke-CloseIssueOnce
            throw "Expected close API failure"
        } catch {
            Assert-Contains $_.Exception.Message "gh issue close failed with exit code 1"
        }
        if ($script:CloseCalls -ne 1) { throw "Expected exactly one mocked close attempt" }
        """,
    )
    assert_success(result)
