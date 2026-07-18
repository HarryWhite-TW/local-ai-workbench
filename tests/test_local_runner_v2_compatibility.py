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


def test_workflow_closeout_surfaces_record_conditional_final_done_truth():
    paths = (
        REPO_ROOT / "PLANS.md",
        REPO_ROOT / "docs" / "BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md",
        REPO_ROOT / "docs" / "WORKFLOW_V1_FINAL_CLOSEOUT.md",
        REPO_ROOT / "docs" / "ENGINEERING_RECORDS_INDEX.md",
    )
    reviewed_head = "dd6046409505e009e95e3a68433bca147542a088"
    canonical_merge = "ee4f9c06dc48719b8165b75607e51d38e7344c6b"
    tracker_checkpoint = "5005537101"
    final_transition_pr = "PR #213"
    final_truth_sync = "final post-tracker repository truth-sync"
    conditional_status = (
        "DONE — FINAL RESIDUAL REVIEW ACCEPTED; CANONICAL EFFECTIVENESS "
        "CONDITIONED ON FINAL TRANSITION MERGE AND TRACKER FINAL DONE PUBLICATION"
    )
    done_nodes = (
        "RV2-P1-SYNC",
        "RV2-04N",
        "Cross-Repository Bounded Proof",
    )
    unconditional_done_claims = (
        r"Workflow v1 Final Closeout\s+(?:is|:)\s*`DONE`",
        r"Workflow v1 Final Closeout\s*\|\s*`DONE`",
        r"Workflow v1 is (?:now )?finally (?:recorded as\s+)?`DONE`",
        r"all four mandatory(?: Workflow v1)? nodes are `DONE`",
        r"Workflow v1(?:\s+is|\s*:)\s*"
        r"(?:\*\*|__)?`?DONE`?(?:\*\*|__)?"
        r"(?=\s*(?:[.,;:]|$))",
    )
    premature_closure_claims = (
        r"no further repository wording change is required",
        r"Tracker #168 final `DONE` publication\s+(?:plus|and)\s+"
        r"final canonical verification\s+(?:is|are)\s+sufficient",
        rf"repository/tracker agreement is final[^\n]{{0,160}}"
        rf"(?:only |solely )?(?:references|records)[^\n]{{0,80}}{tracker_checkpoint}",
    )
    direct_done_examples = (
        "Workflow v1 is `DONE`",
        "Workflow v1: `DONE`",
        "Workflow v1 : `DONE`",
        "Workflow v1 is **DONE**",
        "Workflow v1: **DONE**",
        "Workflow v1 is DONE.",
    )
    for example in direct_done_examples:
        assert any(
            re.search(pattern, example, flags=re.IGNORECASE)
            for pattern in unconditional_done_claims
        ), example
    non_done_examples = (
        "Workflow v1 remains `REVIEW`",
        "Workflow v1 is not `DONE`",
        "Workflow v1 Final Closeout remains pending",
        f"Workflow v1 is `{conditional_status}`",
    )
    for example in non_done_examples:
        assert all(
            re.search(pattern, example, flags=re.IGNORECASE) is None
            for pattern in unconditional_done_claims
        ), example
    premature_closure_examples = (
        "No further repository wording change is required.",
        "Tracker #168 final `DONE` publication plus final canonical verification "
        "is sufficient.",
        "Repository/tracker agreement is final while the repository only "
        f"references intermediate comment {tracker_checkpoint}.",
    )
    for pattern, example in zip(
        premature_closure_claims, premature_closure_examples, strict=True
    ):
        assert re.search(pattern, example, flags=re.IGNORECASE), example

    surface_texts = {path: path.read_text(encoding="utf-8") for path in paths}
    for path, text in surface_texts.items():
        assert "PR #211" in text, path
        assert "PR #212" in text, path
        assert reviewed_head in text, path
        assert canonical_merge in text, path
        assert tracker_checkpoint in text, path
        assert final_transition_pr in text, path
        for node in done_nodes:
            assert re.search(
                rf"{re.escape(node)}[^\n]{{0,200}}`DONE`",
                text,
                flags=re.IGNORECASE,
            ), (path, node)
        assert re.search(
            r"post-merge canonical verification"
            r"[^\n]{0,100}(?:complete(?:d)?|passed)",
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
            r"final residual review / final `DONE` re-adjudication"
            r"[^\n]{0,120}(?:passed|accepted)",
            text,
            flags=re.IGNORECASE,
        ), path
        final_sync_requirements = (
            r"PR #213 merge",
            r"Tracker #168 final `DONE` publication",
            re.escape(final_truth_sync),
            r"actual PR #213 canonical merge SHA",
            r"actual Tracker #168 final `DONE` comment ID",
            r"exact-head review[^\n]{0,160}canonical merge[^\n]{0,160}"
            r"post-merge verification",
            r"final canonical verification",
        )
        for requirement in final_sync_requirements:
            assert re.search(requirement, text, flags=re.IGNORECASE), (
                path,
                requirement,
            )
        assert re.search(
            r"final canonical verification[^\n]{0,240}"
            r"(?:repository/tracker agreement|repository and tracker agree)",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            rf"^(?=[^\n]*{tracker_checkpoint})(?=[^\n]*`REVIEW`)[^\n]+$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        ), path
        assert not re.search(
            r"(?:4998971940[^\n]{0,120}latest|latest[^\n]{0,120}4998971940)",
            text,
            flags=re.IGNORECASE,
        ), path
        for pattern in premature_closure_claims:
            assert re.search(pattern, text, flags=re.IGNORECASE) is None, (
                path,
                pattern,
            )

    def extract_line(text: str, pattern: str) -> str:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        assert match is not None, pattern
        return match.group(0)

    plans_path = REPO_ROOT / "PLANS.md"
    roadmap_path = REPO_ROOT / "docs" / "BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md"
    closeout_path = REPO_ROOT / "docs" / "WORKFLOW_V1_FINAL_CLOSEOUT.md"
    index_path = REPO_ROOT / "docs" / "ENGINEERING_RECORDS_INDEX.md"
    plans = surface_texts[plans_path]
    roadmap = surface_texts[roadmap_path]
    closeout = surface_texts[closeout_path]
    index = surface_texts[index_path]

    plans_node_four = extract_line(
        plans, r"^4\. Workflow v1 Final Closeout:[^\n]+$"
    )
    assert conditional_status in plans_node_four
    assert reviewed_head in plans_node_four
    assert canonical_merge in plans_node_four
    assert tracker_checkpoint in plans_node_four
    plans_summary = extract_line(plans, r"^The first three mandatory nodes remain[^\n]+$")
    assert conditional_status in plans_summary
    assert final_truth_sync in plans_summary
    assert "actual PR #213 canonical merge SHA" in plans_summary
    assert "actual Tracker #168 final `DONE` comment ID" in plans_summary

    roadmap_completion = re.search(
        r"### Workflow v1 completion boundary(?P<section>.*?)"
        r"#### Workflow v1 Final Closeout Acceptance Contract",
        roadmap,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert roadmap_completion is not None
    roadmap_node_four = extract_line(
        roadmap_completion.group("section"),
        r"^4\. Workflow v1 Final Closeout:[^\n]+$",
    )
    assert conditional_status in roadmap_node_four
    assert reviewed_head in roadmap_node_four
    assert canonical_merge in roadmap_node_four
    assert tracker_checkpoint in roadmap_node_four
    roadmap_summary = extract_line(
        roadmap, r"^The first three mandatory Workflow v1 nodes remain[^\n]+$"
    )
    assert conditional_status in roadmap_summary
    roadmap_contract = extract_line(
        roadmap, r"^The final residual review / final `DONE` re-adjudication[^\n]+$"
    )
    assert "has passed" in roadmap_contract
    assert final_truth_sync in roadmap_contract
    assert "actual PR #213 canonical merge SHA" in roadmap_contract
    assert "actual Tracker #168 final `DONE` comment ID" in roadmap_contract

    index_status = extract_line(
        index, r"^`PLANS\.md` remains the current project-status authority\.[^\n]+$"
    )
    assert conditional_status in index_status
    assert "navigation only and does not itself accept, activate, or grant authority" in index_status
    assert final_truth_sync in index_status
    assert "actual PR #213 canonical merge SHA" in index_status
    assert "actual Tracker #168 final `DONE` comment ID" in index_status

    matrix_row_match = re.search(
        r"^\| Workflow v1 Final Closeout \|[^\n]+$",
        closeout,
        flags=re.MULTILINE,
    )
    assert matrix_row_match is not None
    matrix_row = matrix_row_match.group(0)
    assert conditional_status in matrix_row
    assert "final residual review / final `DONE` re-adjudication are complete" in matrix_row
    assert "PR #213 repair and exact-head rereview" in matrix_row
    assert "PR #213 merge" in matrix_row
    assert "post-merge canonical verification" in matrix_row
    assert "Tracker #168" in matrix_row
    assert "paired final `DONE`" in matrix_row
    assert final_truth_sync in matrix_row
    assert "actual PR #213 canonical merge SHA" in matrix_row
    assert "actual Tracker #168 final `DONE` comment ID" in matrix_row
    assert "exact-head review, canonical merge, and post-merge verification" in matrix_row
    assert "final canonical verification" in matrix_row
    assert "no later node activation" in matrix_row
    closeout_ledger = extract_line(closeout, r"^- current status:[^\n]+$")
    assert conditional_status in closeout_ledger
    ledger_match = re.search(
        r"### Workflow v1 Final Closeout(?P<section>.*?)### Phase C target-flow evidence",
        closeout,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert ledger_match is not None
    ledger = ledger_match.group("section")
    assert reviewed_head in ledger
    assert canonical_merge in ledger
    assert tracker_checkpoint in ledger
    assert "ACCEPTED — FINAL RESIDUAL REVIEW PASSED" in ledger

    current_checkpoint = extract_line(closeout, r"^Current status:[^\n]+$")
    current_anchors = (
        plans_node_four,
        plans_summary,
        roadmap_node_four,
        roadmap_summary,
        index_status,
        matrix_row,
        closeout_ledger,
        current_checkpoint,
    )
    for anchor in current_anchors:
        assert conditional_status in anchor
        assert "remains pending" not in anchor.lower()
        assert "4998971940" not in anchor
        for pattern in unconditional_done_claims:
            assert re.search(pattern, anchor, flags=re.IGNORECASE) is None, (
                anchor,
                pattern,
            )

    for cache_surface in (plans, closeout):
        assert "six reviewed `.pytest_cache` metadata path patterns" in cache_surface
        assert "excluded as benign cache noise" in cache_surface
        assert "beneath any `.pytest_cache` directory" in cache_surface
        assert re.search(
            r"arbitrary `\.pyc` creation or removal remains observable",
            cache_surface,
            flags=re.IGNORECASE,
        )
        assert "`.pyc` path outside runtime `allowed_files` fails closed" in cache_surface
        assert (
            "`.pyc` path explicitly included in `allowed_files` is not rejected solely "
            "because its extension is `.pyc`"
        ) in cache_surface
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
