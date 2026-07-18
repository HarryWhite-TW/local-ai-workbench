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


def test_workflow_closeout_surfaces_publish_final_done_truth():
    paths = (
        REPO_ROOT / "PLANS.md",
        REPO_ROOT / "docs" / "BRIDGE_ROADMAP_V2_EXECUTION_SPEC.md",
        REPO_ROOT / "docs" / "WORKFLOW_V1_FINAL_CLOSEOUT.md",
        REPO_ROOT / "docs" / "ENGINEERING_RECORDS_INDEX.md",
    )
    reviewed_head = "60be637db0c237db3d53408a272fd3aaba98ec8b"
    canonical_merge = "317cd7e9fedb153daa034c1e698819042e2e4564"
    tracker_checkpoint = "5005537101"
    residual_review_anchor = "5010099708"
    final_done_comment = "5010353117"
    current_status = "DONE — FINAL DURABLE TRUTH SYNCHRONIZED"
    done_nodes = (
        "RV2-P1-SYNC",
        "RV2-04N",
        "Cross-Repository Bounded Proof",
    )
    stale_current_claims = (
        r"Workflow v1(?: Final Closeout)?\s+(?:is|remains|:)\s*`?REVIEW\b",
        r"canonical closure gates remain pending",
        r"Workflow v1(?: Final Closeout)?[^\n]{0,100}"
        r"(?:conditional(?:ly)?|provisional(?:ly)?)\s+`?DONE\b",
        r"PR #213 (?:merge|canonical merge)[^\n]{0,80}(?:pending|remains required)",
        r"Tracker #168 final `DONE` publication[^\n]{0,80}"
        r"(?:pending|remains required)",
        r"another post-tracker repository truth-sync remains required",
        r"candidate branch content alone is canonical current truth",
        r"successful post-merge verification[^\n]{0,120}"
        r"requires another repository (?:wording )?(?:change|update|edit)",
    )
    stale_current_examples = (
        "Workflow v1 remains REVIEW",
        "Canonical closure gates remain pending",
        "Workflow v1 is conditionally DONE",
        "PR #213 merge remains required",
        "Tracker #168 final `DONE` publication is pending",
        "Another post-tracker repository truth-sync remains required",
        "Candidate branch content alone is canonical current truth",
        "Successful post-merge verification requires another repository edit",
    )
    for pattern, example in zip(
        stale_current_claims, stale_current_examples, strict=True
    ):
        assert re.search(pattern, example, flags=re.IGNORECASE), example

    surface_texts = {path: path.read_text(encoding="utf-8") for path in paths}
    for path, text in surface_texts.items():
        assert "PR #211" in text, path
        assert "PR #212" in text, path
        assert "PR #213" in text, path
        assert reviewed_head in text, path
        assert canonical_merge in text, path
        assert tracker_checkpoint in text, path
        assert residual_review_anchor in text, path
        assert final_done_comment in text, path
        assert current_status in text, path
        for node in done_nodes:
            assert re.search(
                rf"{re.escape(node)}[^\n]{{0,200}}`DONE`",
                text,
                flags=re.IGNORECASE,
            ), (path, node)
        assert re.search(
            r"(?:no later (?:Roadmap )?node is activated|"
            r"does not activate another node|No-Auto-Activation)",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            rf"^(?=[^\n]*{residual_review_anchor})"
            r"(?=[^\n]*(?:reviewer-controlled|residual-review))"
            r"(?=[^\n]*FINAL RESIDUAL REVIEW PASSED)[^\n]+$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        ), path
        assert re.search(
            rf"^(?=[^\n]*{final_done_comment})"
            r"(?=[^\n]*final `DONE`)[^\n]+$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        ), path
        assert re.search(
            rf"^(?=[^\n]*{tracker_checkpoint})(?=[^\n]*intermediate)"
            r"(?=[^\n]*(?:historical|history))(?=[^\n]*`REVIEW`)[^\n]+$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        ), path
        assert re.search(
            r"repository and (?:Tracker #168|tracker) truth are synchronized",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"feature branches and PR candidates are proposals, not current truth",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"merging the exact reviewed truth-sync content into `master` publishes"
            r"[^\n]{0,80}final `DONE`",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"post-merge canonical verification validates",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"successful verification requires no second repository wording update",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            r"truth-sync PR number and its future merge SHA are intentionally not pre-recorded",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(
            rf"PR #213[^\n]{{0,240}}{reviewed_head}[^\n]{{0,240}}"
            rf"{canonical_merge}[^\n]{{0,160}}post-merge",
            text,
            flags=re.IGNORECASE,
        ), path
        assert not re.search(
            r"(?:4998971940[^\n]{0,120}latest|latest[^\n]{0,120}4998971940)",
            text,
            flags=re.IGNORECASE,
        ), path
        assert re.search(r"truth-sync PR\s+#\d+", text, flags=re.IGNORECASE) is None, path
        assert re.search(
            r"truth-sync (?:PR )?(?:canonical )?merge(?: SHA)?\s*[:` ]+"
            r"[0-9a-f]{40}",
            text,
            flags=re.IGNORECASE,
        ) is None, path

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
    assert current_status in plans_node_four
    assert reviewed_head in plans_node_four
    assert canonical_merge in plans_node_four
    assert tracker_checkpoint in plans_node_four
    assert residual_review_anchor in plans_node_four
    assert final_done_comment in plans_node_four
    plans_proof_summary = extract_line(
        plans, r"^This proves bounded reuse[^\n]+Workflow v1 is[^\n]+$"
    )
    assert current_status in plans_proof_summary
    assert residual_review_anchor in plans_proof_summary
    assert final_done_comment in plans_proof_summary
    plans_summary = extract_line(plans, r"^The first three mandatory nodes remain[^\n]+$")
    assert current_status in plans_summary
    assert tracker_checkpoint in plans_summary
    assert residual_review_anchor in plans_summary
    assert final_done_comment in plans_summary
    assert reviewed_head in plans_summary
    assert canonical_merge in plans_summary
    assert "Repository and Tracker #168 truth are synchronized" in plans_summary

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
    assert current_status in roadmap_node_four
    assert reviewed_head in roadmap_node_four
    assert canonical_merge in roadmap_node_four
    assert tracker_checkpoint in roadmap_node_four
    assert residual_review_anchor in roadmap_node_four
    assert final_done_comment in roadmap_node_four
    roadmap_summary = extract_line(
        roadmap, r"^The first three mandatory Workflow v1 nodes remain[^\n]+$"
    )
    assert current_status in roadmap_summary
    roadmap_contract = extract_line(
        roadmap, r"^The final residual review / final `DONE` re-adjudication[^\n]+$"
    )
    assert "passed" in roadmap_contract
    assert residual_review_anchor in roadmap_contract
    assert reviewed_head in roadmap_contract
    assert canonical_merge in roadmap_contract
    assert final_done_comment in roadmap_contract
    assert current_status in roadmap_contract

    index_status = extract_line(
        index, r"^`PLANS\.md` remains the current project-status authority\.[^\n]+$"
    )
    assert current_status in index_status
    assert "navigation only and does not itself accept, activate, or grant authority" in index_status
    assert reviewed_head in index_status
    assert canonical_merge in index_status
    assert final_done_comment in index_status
    assert tracker_checkpoint in index_status
    assert residual_review_anchor in index_status

    closeout_identity = extract_line(closeout, r"^- status: `[^\n]+`$")
    assert closeout_identity == f"- status: `{current_status}`"
    closeout_verdict = extract_line(
        closeout, r"^Workflow v1 Final Closeout is[^\n]+$"
    )
    assert closeout_verdict.count(current_status) == 2

    matrix_row_match = re.search(
        r"^\| Workflow v1 Final Closeout \|[^\n]+$",
        closeout,
        flags=re.MULTILINE,
    )
    assert matrix_row_match is not None
    matrix_row = matrix_row_match.group(0)
    assert current_status in matrix_row
    assert tracker_checkpoint in matrix_row
    assert residual_review_anchor in matrix_row
    assert "FINAL RESIDUAL REVIEW PASSED" in matrix_row
    assert reviewed_head in matrix_row
    assert canonical_merge in matrix_row
    assert final_done_comment in matrix_row
    assert "post-merge verification" in matrix_row
    assert "Tracker #168" in matrix_row
    assert "published final `DONE`" in matrix_row
    assert "Repository and tracker truth are synchronized" in matrix_row
    assert "no later node is activated" in matrix_row
    closeout_ledger = extract_line(closeout, r"^- current status:[^\n]+$")
    assert current_status in closeout_ledger
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
    assert residual_review_anchor in ledger
    assert final_done_comment in ledger
    assert "ACCEPTED — FINAL RESIDUAL REVIEW PASSED" in ledger
    assert "repository and Tracker #168 truth are synchronized" in ledger
    assert "no later node is activated" in ledger

    current_checkpoint = extract_line(closeout, r"^Current status:[^\n]+$")
    closeout_summary = extract_line(
        closeout, r"^The first three mandatory nodes remain[^\n]+$"
    )
    current_anchors = (
        plans_node_four,
        plans_proof_summary,
        plans_summary,
        roadmap_node_four,
        roadmap_summary,
        index_status,
        closeout_identity,
        closeout_verdict,
        matrix_row,
        closeout_ledger,
        current_checkpoint,
        closeout_summary,
    )
    for anchor in current_anchors:
        assert current_status in anchor
        assert "4998971940" not in anchor
        for pattern in stale_current_claims:
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
