import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_V1 = REPO_ROOT / "scripts" / "local_runner_v1.ps1"
RUNNER_V2 = REPO_ROOT / "scripts" / "local_runner_v2.ps1"


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for Runner compatibility tests")
    return shell


def _runner_v2_core() -> str:
    source = RUNNER_V2.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index("\ntry {")
    return source[start:end]


def _approval_token_parser() -> str:
    source = RUNNER_V1.read_text(encoding="utf-8")
    start = source.index("function ConvertFrom-ApprovalToken")
    end = source.index("\nfunction Assert-ApprovalMatchesState", start)
    return source[start:end]


def test_runner_v2_handoff_uses_runner_v1_authoritative_full_token(tmp_path):
    token = (
        "LRV1-APPROVE issue=206 mode=Level3A branch=test head="
        + "1" * 40
        + " review=review206 diff="
        + "2" * 64
        + " files="
        + "3" * 64
        + " scope="
        + "4" * 64
        + " manifest="
        + "5" * 64
        + " evidence=local_git_candidate_observation.v1 isolation=unverified"
    )
    fake_runner_v1 = tmp_path / "local_runner_v1.ps1"
    fake_runner_v1.write_text(
        textwrap.dedent(
            f"""
            param(
                [int]$IssueNumber,
                [string]$Mode,
                [string]$ApprovalToken = ""
            )
            Set-StrictMode -Version Latest
            $ErrorActionPreference = "Stop"
            {_approval_token_parser()}
            if ($Mode -eq "CommitApprovalStateDiagnostic") {{
                Write-Output "LRV1-COMMIT-APPROVAL-STATE protocol=lawb.runner_v1.commit_approval_state.v1"
                [ordered]@{{
                    protocol = "lawb.runner_v1.commit_approval_state.v1"
                    issue = [string]$IssueNumber
                    branch = "test"
                    head = ("1" * 40)
                    modified_files = @("docs/example.md")
                    approval_token = {token!r}
                }} | ConvertTo-Json -Compress
                exit 0
            }}
            if ($Mode -eq "CommitApproved") {{
                $parsed = ConvertFrom-ApprovalToken -Token $ApprovalToken
                if ($parsed.Issue -ne [string]$IssueNumber) {{ throw "issue mismatch" }}
                Write-Output "COMMIT-APPROVED-TOKEN-ACCEPTED"
                exit 0
            }}
            exit 9
            """
        ).strip(),
        encoding="utf-8-sig",
    )
    harness = tmp_path / "runner_v2_compatibility.ps1"
    harness.write_text(
        _runner_v2_core()
        + textwrap.dedent(
            """

            $state = Get-RunnerV1CommitApprovalState -IssueNumber 206
            $exitCode = Invoke-RunnerV1CommitApproved -IssueNumber 206 -ApprovalToken $state.ApprovalToken
            [ordered]@{
                protocol = $state.Protocol
                issue = $state.IssueNumber
                branch = $state.Branch
                head = $state.Head
                modified_files = @($state.ModifiedFiles)
                approval_token = $state.ApprovalToken
                commit_exit_code = $exitCode
            } | ConvertTo-Json -Compress
            """
        ),
        encoding="utf-8-sig",
    )

    result = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["protocol"] == "lawb.runner_v1.commit_approval_state.v1"
    assert payload["issue"] == "206"
    assert payload["modified_files"] == ["docs/example.md"]
    assert payload["commit_exit_code"] == 0
    parts = payload["approval_token"].split()
    assert len(parts) == 12
    assert {part.split("=", 1)[0] for part in parts[1:]} == {
        "issue",
        "mode",
        "branch",
        "head",
        "review",
        "diff",
        "files",
        "scope",
        "manifest",
        "evidence",
        "isolation",
    }


def test_runner_v2_no_longer_constructs_a_divergent_lrv1_token():
    source = RUNNER_V2.read_text(encoding="utf-8")
    assert 'ApprovalToken = "LRV1-APPROVE' not in source
    assert "Get-RunnerV1CommitApprovalState" in source
    commit_start = source.index("function Invoke-ApprovalNextCommitOnce")
    commit_end = source.index("\nfunction Write-PushDryRunScanMessages", commit_start)
    body = source[commit_start:commit_end]
    diagnostic = body.index("Get-RunnerV1CommitApprovalState")
    current_state = body.index("Get-CommitApprovalState", diagnostic)
    marker_recheck = body.index("Assert-CommitApprovalMarkerMatchesState", current_state)
    handoff = body.index("Invoke-RunnerV1CommitApproved", marker_recheck)
    assert diagnostic < current_state < marker_recheck < handoff
