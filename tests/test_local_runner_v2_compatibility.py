import json
import re
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


def test_runner_v2_real_approval_state_diagnostic_is_strict_mode_safe_and_read_only():
    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        stderr = result.stderr.decode("utf-8", errors="replace")
        assert result.returncode == 0, f"git {' '.join(args)} failed:\n{stderr}"
        return result.stdout

    before = {
        "head": git("rev-parse", "HEAD"),
        "status": git("status", "--porcelain=v1", "--untracked-files=all"),
        "staged": git("diff", "--cached", "--binary"),
        "worktree": git("diff", "--binary"),
    }
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER_V2),
            "-ApprovalStateDiagnostic",
            "-IssueNumber",
            "211",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=60,
    )
    after = {
        "head": git("rev-parse", "HEAD"),
        "status": git("status", "--porcelain=v1", "--untracked-files=all"),
        "staged": git("diff", "--cached", "--binary"),
        "worktree": git("diff", "--binary"),
    }

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    output = stdout + stderr
    assert result.returncode == 0, f"stdout:\n{stdout}\nstderr:\n{stderr}"
    assert "Mode: ApprovalStateDiagnostic" in output
    assert "Read-only: yes" in output
    assert "Issue number: #211" in output
    assert "Final files fingerprint:" in output
    assert "Final diff fingerprint:" in output
    assert "No-write guarantee:" in output
    assert "Approval token preview:" not in output
    assert "ApprovalToken" not in output
    assert after == before


def test_workflow_closeout_surfaces_record_final_done_truth():
    paths = (
        REPO_ROOT / "PLANS.md",
        REPO_ROOT / "docs" / "BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md",
        REPO_ROOT / "docs" / "WORKFLOW_V1_FINAL_CLOSEOUT.md",
        REPO_ROOT / "docs" / "ENGINEERING_RECORDS_INDEX.md",
    )
    reviewed_head = "4d3b649da9c953480c5053ae8e0b1707315de3e6"
    canonical_merge = "38d3e96263b671a72141d0ab92b61b91a85e6c36"
    tracker_checkpoint = "4998971940"
    stale_placeholders = (
        "future documentation publication commit / PR head",
        "future documentation publication commit and PR head",
        "future documentation commit and PR",
        "documentation publication commit and PR head had not yet been created",
    )

    stale_current_status_patterns = (
        r"PR #211 is (?:now )?the active correction/publication PR",
        r"active correction/publication PR:\s*#211",
        r"REVIEW\s*[—-]\s*ACTIVE PR #211",
        r"(?:ChatGPT\s+)?final reviewer acceptance is withheld",
        r"final acceptance is withheld",
        r"Workflow v1 is not yet finally accepted as\s+(?:DONE|`DONE`)",
        r"Final Closeout remains\s+`?REVIEW\b",
        r"(?:rereview|merge|post-merge canonical verification|"
        r"tracker #168 (?:synchronization|sync)|final residual review)"
        r"[^\n]{0,120}\b(?:remain|remains|is|are)\s+(?:pending|open|required)\b",
    )
    stale_acceptance_examples = (
        "ChatGPT final reviewer acceptance is withheld",
        "final reviewer acceptance is withheld",
        "final acceptance is withheld",
        "Workflow v1 is not yet finally accepted as DONE",
        "Workflow v1 is not yet finally accepted as `DONE`",
        "Final Closeout remains REVIEW",
    )
    historical_acceptance_examples = (
        "ChatGPT final reviewer acceptance was withheld at the incident checkpoint",
        "ChatGPT final reviewer acceptance had been withheld pending correction",
        "ChatGPT final reviewer acceptance was historically withheld",
    )

    for example in stale_acceptance_examples:
        assert any(
            re.search(pattern, example, flags=re.IGNORECASE)
            for pattern in stale_current_status_patterns
        ), example
    for example in historical_acceptance_examples:
        assert all(
            re.search(pattern, example, flags=re.IGNORECASE) is None
            for pattern in stale_current_status_patterns
        ), example

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "PR #211" in text, path
        assert reviewed_head in text, path
        assert canonical_merge in text, path
        assert tracker_checkpoint in text, path
        assert re.search(
            r"Workflow v1 Final Closeout[^\n]{0,240}`DONE`",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"(?:no major issues|reported no major issues)",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"post-merge canonical verification (?:is )?complete(?:d)?",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"final residual review (?:is )?complete(?:d)?",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"(?:no later (?:Roadmap )?node is activated|"
            r"does not activate another node|No-Auto-Activation)",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            rf"comment\s+`?{tracker_checkpoint}`?.{{0,240}}"
            r"(?:REVIEW|before final residual review)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ), path
        for pattern in stale_current_status_patterns:
            assert re.search(pattern, text, flags=re.IGNORECASE) is None, (
                path,
                pattern,
            )
        for placeholder in stale_placeholders:
            assert placeholder not in text, (path, placeholder)

    closeout = (REPO_ROOT / "docs" / "WORKFLOW_V1_FINAL_CLOSEOUT.md").read_text(
        encoding="utf-8"
    )
    for evidence in (
        "targeted pycache regressions `10 passed`",
        "Runner v1 `89 passed`",
        "Runner v2 compatibility `4 passed`",
        "related Runner/Bridge suite `810 passed`",
        "full repository suite `1112 passed`",
        "`0 failed`",
        "`git diff --check` exit `0`",
    ):
        assert evidence in closeout
    assert "PR #203" in closeout
    assert "PR #204" in closeout
    assert "historical integrity-incident evidence" in closeout
    assert re.search(
        r"provider-backed filesystem isolation remains `unverified`",
        closeout,
        flags=re.IGNORECASE,
    )
    assert re.search(
        r"unresolved historical GitHub review-thread UI state.+"
        r"not an outstanding technical blocker",
        closeout,
        flags=re.IGNORECASE,
    )
