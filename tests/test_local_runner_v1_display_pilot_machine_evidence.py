import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_runner_bridge.display_pilot_operator import run_foreground
from local_runner_bridge.display_pilot_transport import (
    PROTOCOL,
    SELECTOR_REPOSITORY,
    TARGET_REPOSITORY,
    body_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "local_runner_v1.ps1"
HEAD = "a" * 40


def powershell():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required")
    return shell


def runner_core():
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index("\nAssert-TargetRepositoryBinding")
    return source[start:end]


def run_script(tmp_path, *, prefix="", body="", binary=False):
    script = tmp_path / "machine_evidence_harness.ps1"
    script.write_text(
        prefix + "\n" + runner_core() + "\n" + textwrap.dedent(body),
        encoding="utf-8-sig",
    )
    return subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=ROOT,
        capture_output=True,
        text=not binary,
        check=False,
    )


def completion_body(
    codex_exit="0",
    *,
    poison_evidence=False,
    write_failure_marker=None,
):
    codex_status = "passed" if codex_exit == "0" else "failed"
    poison = (
        'function New-DisplayPilotMachineEvidence { throw "machine evidence path entered" }'
        if poison_evidence
        else ""
    )
    fail_write = ""
    if write_failure_marker is not None:
        marker = str(write_failure_marker).replace("\\", "/").replace("'", "''")
        fail_write = f"""
        function Write-DisplayPilotMachineEvidence {{
            param([object]$Evidence)
            Set-Content -LiteralPath '{marker}' -Value ([string]$script:PostCalls)
            throw "simulated post-comment evidence rewrite failure"
        }}
        """
    return f"""
    $script:PostCalls = 0
    function Post-IssueComment {{
        param([string]$Comment)
        $script:PostCalls += 1
        return [pscustomobject]@{{ ExitCode = 0; Stdout = "posted"; Stderr = "" }}
    }}
    {poison}
    {fail_write}
    $stderrSummary = Get-StderrSummary -Text "" -ExitCode "{codex_exit}"
    $comment = New-ReviewBundleComment `
        -IssueNumberText "9" `
        -Branch "feature/display-pilot" `
        -HeadBefore ("a" * 40) `
        -HeadAfter ("a" * 40) `
        -CodexExitCode "{codex_exit}" `
        -RepoCleanBefore "yes" `
        -ReviewId "" `
        -DiffFingerprint "" `
        -FilesFingerprint "" `
        -ApprovalToken "" `
        -ModifiedFiles "src/example.py" `
        -DiffStat "" `
        -CachedDiffStat "" `
        -CommandsSummary "parent evidence" `
        -CodexFinalReport "untrusted prose" `
        -StderrSummary $stderrSummary `
        -FinalStatus " M src/example.py" `
        -FinalIndexClean $true `
        -FinalHeadMatchesInitial $true
    $binding = [pscustomobject]@{{
        status = "passed"
        contract_present = $true
        pre_execution = [pscustomobject]@{{ status = "passed"; reasons = @() }}
        post_execution = [pscustomobject]@{{ status = "passed"; reasons = @() }}
        allowed_files = @("src/example.py")
        actual_changed_files = @("src/example.py")
        reasons = @()
        runtime_contract = [pscustomobject]@{{
            protocol = "lawb.local_runner.task_packet.v1.1"
            packet_id = "dp4-br-9"
            logical_issue = 9
            repository = "HarryWhite-TW/human-approval-automation-gateway"
            branch = "feature/display-pilot"
            expected_head = ("a" * 40)
            task_mode = "PATCH_ONLY"
            objective = "Implement one bounded change."
            allowed_files = @("src/example.py")
            max_allowed_files = 1
            verification_command_policy = "explicit_only"
            verification_commands = @("python -m pytest -q tests/test_example.py")
            scope_expansion_allowed = $false
        }}
    }}
    $assurance = [pscustomobject]@{{
        governance_scope = "passed"
        observable_evidence = "verified"
        evidence_profile = "local_git_candidate_observation.v1"
        candidate_manifest_fingerprint = "fingerprint"
        isolation_guarantee = "unverified"
        isolation_provider = "codex_cli_workspace_write"
        isolation_evidence_source = $null
    }}
    $result = Complete-ReviewBundleOutcome `
        -Comment $comment `
        -EvidenceFactory {{
            New-DisplayPilotMachineEvidence `
                -IssueNumberText "9" `
                -Branch "feature/display-pilot" `
                -HeadBefore ("a" * 40) `
                -HeadAfter ("a" * 40) `
                -CodexExitCode "{codex_exit}" `
                -CodexStatus "{codex_status}" `
                -CodexTimedOut $false `
                -RuntimeContractBinding $binding `
                -ChangedFiles @("src/example.py") `
                -FinalStatus " M src/example.py" `
                -StagedAreaClean $true `
                -ExecutionAssurance $assurance
        }}
    [ordered]@{{
        exit_code = $result.ExitCode
        stdout = $result.Stdout
        post_calls = $script:PostCalls
    }} | ConvertTo-Json -Compress
    """


def prefix(
    path="",
    suppress=False,
    mode="ReviewBundle",
    request_id="req-9",
):
    bound_request_id = request_id if path else ""
    return "\n".join(
        [
            '$Repo = "HarryWhite-TW/human-approval-automation-gateway"',
            f"$RepoPath = {str(ROOT).replace(chr(92), '/')!r}",
            "$IssueNumber = 9",
            f"$Mode = {mode!r}",
            f"$MachineEvidencePath = {str(path).replace(chr(92), '/')!r}",
            f"$DisplayPilotRequestId = {bound_request_id!r}",
            f"$SuppressReviewBundleComment = ${str(suppress).lower()}",
        ]
    )


def test_strict_mode_extracted_core_loads_without_param_block(tmp_path):
    result = run_script(tmp_path, body='Write-Output "loaded"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "loaded"


def test_suppression_without_machine_path_is_blocked(tmp_path):
    result = run_script(tmp_path, prefix=prefix(suppress=True))
    assert result.returncode != 0
    assert "SuppressReviewBundleComment requires MachineEvidencePath" in result.stderr


def test_non_reviewbundle_machine_path_is_blocked(tmp_path):
    result = run_script(
        tmp_path,
        prefix=prefix(path=tmp_path / "evidence.json", mode="CommitApproved"),
    )
    assert result.returncode != 0
    assert "MachineEvidencePath is ReviewBundle-only" in result.stderr


def test_machine_path_requires_request_id_and_matching_request_directory(tmp_path):
    missing = run_script(
        tmp_path,
        prefix=prefix(
            path=tmp_path / "req-9" / "evidence.json",
            request_id="",
        ),
        binary=True,
    )
    assert missing.returncode != 0
    assert b"requires a Windows-safe DisplayPilotRequestId" in missing.stderr

    mismatch = run_script(
        tmp_path,
        prefix=prefix(
            path=tmp_path / "different" / "evidence.json",
            request_id="req-9",
        ),
        binary=True,
    )
    assert mismatch.returncode != 0
    assert b"request directory must match DisplayPilotRequestId" in mismatch.stderr


@pytest.mark.parametrize("request_id", ["CON", "bad/name", "trailing."])
def test_machine_path_rejects_windows_unsafe_request_id(tmp_path, request_id):
    result = run_script(
        tmp_path,
        prefix=prefix(
            path=tmp_path / request_id / "evidence.json",
            request_id=request_id,
        ),
        binary=True,
    )
    assert result.returncode != 0
    assert b"requires a Windows-safe DisplayPilotRequestId" in result.stderr


def test_default_path_posts_existing_comment_and_writes_no_machine_file(tmp_path):
    evidence = tmp_path / "must-not-exist.json"
    result = run_script(
        tmp_path,
        prefix=prefix(),
        body=completion_body(poison_evidence=True),
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.strip())
    assert output == {"exit_code": 0, "stdout": "posted", "post_calls": 1}
    assert not evidence.exists()


def test_machine_evidence_is_written_and_suppression_never_posts(tmp_path):
    request = tmp_path / "req-9"
    request.mkdir()
    evidence = request / "runner-machine-evidence.json"
    result = run_script(
        tmp_path,
        prefix=prefix(path=evidence, suppress=True),
        body=completion_body(),
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.strip())
    assert output["post_calls"] == 0
    assert "suppressed" in output["stdout"]

    payload = json.loads(evidence.read_text(encoding="utf-8-sig"))
    assert payload["protocol"] == "lawb.display_pilot.runner_machine_evidence.v1"
    assert payload["schema_version"] == 1
    assert payload["request_id"] == "req-9"
    assert payload["repository"] == "HarryWhite-TW/human-approval-automation-gateway"
    assert payload["issue"] == 9
    assert payload["branch"] == "feature/display-pilot"
    assert payload["head_before"] == "a" * 40
    assert payload["head_after"] == "a" * 40
    assert payload["changed_files"] == ["src/example.py"]
    assert payload["staged_area_clean"] is True
    assert payload["review_bundle_comment_suppressed"] is True
    assert payload["github_comment_posted"] is False
    assert payload["safety_flags"]["result_packet_written"] is True
    assert type(payload["safety_flags"]["result_packet_written"]) is bool
    assert all(
        payload["safety_flags"][name] is False
        for name in (
            "github_write_performed",
            "commit_performed",
            "push_performed",
            "pr_created",
            "merge_performed",
            "issue_closed",
            "label_changed",
        )
    )


def test_machine_evidence_without_suppression_records_comment_post(tmp_path):
    request = tmp_path / "req-9"
    request.mkdir()
    evidence = request / "runner-machine-evidence.json"
    result = run_script(
        tmp_path,
        prefix=prefix(path=evidence),
        body=completion_body(),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip())["post_calls"] == 1
    payload = json.loads(evidence.read_text(encoding="utf-8-sig"))
    assert payload["review_bundle_comment_suppressed"] is False
    assert payload["github_comment_posted"] is True
    assert payload["safety_flags"]["github_write_performed"] is True


def test_post_comment_evidence_write_failure_is_visible_without_false_record(tmp_path):
    request = tmp_path / "req-9"
    request.mkdir()
    evidence = request / "runner-machine-evidence.json"
    marker = tmp_path / "post-calls.txt"
    result = run_script(
        tmp_path,
        prefix=prefix(path=evidence),
        body=completion_body(write_failure_marker=marker),
    )
    assert result.returncode != 0
    assert "simulated post-comment evidence rewrite failure" in result.stderr
    assert marker.read_text(encoding="utf-8-sig").strip() == "1"
    assert not evidence.exists()


def test_reviewable_nonzero_codex_result_writes_blocked_evidence(tmp_path):
    request = tmp_path / "req-9"
    request.mkdir()
    evidence = request / "runner-machine-evidence.json"
    result = run_script(
        tmp_path,
        prefix=prefix(path=evidence, suppress=True),
        body=completion_body(codex_exit="7"),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(evidence.read_text(encoding="utf-8-sig"))
    assert payload["result_status"] == "blocked"
    assert payload["codex_exit_code"] == "7"
    assert "codex_failed" in payload["blocked_reasons"]


def test_real_runner_json_crosses_operator_boundary_without_field_rewrite(tmp_path):
    target_body = f"""LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1.1
packet_id: dp4-br-9
logical_issue: 9
phase: display_pilot_foreground
action_type: implementation
risk_level: medium
repository: {TARGET_REPOSITORY}
branch: feature/display-pilot
expected_head: {HEAD}
allowed_files:
  - src/example.py
forbidden_operations:
  - commit
approval:
  required: false
payload:
  kind: implementation
result_target:
  github_issue: 9
  marker: DISPLAY-PILOT-RESULT
stop_condition: stop_after_result
task_mode: PATCH_ONLY
objective: Implement one bounded change.
max_allowed_files: 1
context_scope:
  - src/example.py
repair_attempt_limit: 1
verification_command_policy: explicit_only
verification_commands:
  - python -m pytest -q tests/test_example.py
scope_expansion_allowed: false
END_TASK_PACKET
"""
    selector_payload = {
        "protocol": PROTOCOL,
        "repository": SELECTOR_REPOSITORY,
        "issue": 1,
        "target_repository": TARGET_REPOSITORY,
        "target_issue": 9,
        "action": "run-reviewbundle",
        "request_id": "req-9",
        "target_body_sha256": body_sha256(target_body),
    }
    selector_body = (
        "```json hgw.display_pilot.transport.v1\n"
        + json.dumps(selector_payload)
        + "\n```"
    )
    selector = {
        "body": selector_body,
        "creator": "HarryWhite-TW",
        "body_sha256": body_sha256(selector_body),
    }
    target = {
        "repository": TARGET_REPOSITORY,
        "number": 9,
        "creator": "HarryWhite-TW",
        "state": "OPEN",
        "body": target_body,
    }
    observed = {"runner_bytes": None, "verification": 0, "render": []}

    def actual_runner(request, evidence_path):
        result = run_script(
            tmp_path,
            prefix=prefix(path=evidence_path, suppress=True),
            body=completion_body(),
        )
        assert result.returncode == 0, result.stderr
        observed["runner_bytes"] = evidence_path.read_bytes()
        return 0

    def verifier(command, **kwargs):
        observed["verification"] += 1
        return {"command": command, "result": "success", "reason": "exit_code_0"}

    def renderer(evidence, result_id, created_at):
        observed["render"].append(evidence)
        return {
            "result": "success",
            "result_surface": {"request_id": result_id, "status": evidence["result"]},
            "reviewer_report": "review:success",
            "plain_language_zh_TW": "plain:success",
        }

    state = tmp_path / "operator-state"
    result = run_foreground(
        state_root=state,
        target_repo_root=ROOT,
        selector_reader=lambda: selector,
        target_reader=lambda _: target,
        runner=actual_runner,
        hgw_renderer=renderer,
        python_path=sys.executable,
        verifier=verifier,
        git_observer=lambda _: {
            "head": HEAD,
            "staged_paths": [],
            "staged_clean": True,
            "status_short": " M src/example.py",
            "effective_changed_paths": ["src/example.py"],
            "fingerprint": "stable",
        },
        sleep=lambda _: None,
    )

    request = state / "requests" / "req-9"
    runner_path = request / "runner_machine_evidence.json"
    assert runner_path.read_bytes() == observed["runner_bytes"]
    runner_payload = json.loads(observed["runner_bytes"].decode("utf-8-sig"))
    canonical = json.loads((request / "canonical_evidence.json").read_text())
    request_summary = json.loads((request / "operator_summary.json").read_text())
    safety = runner_payload["safety_flags"]

    assert runner_payload["request_id"] == "req-9"
    assert safety["result_packet_written"] is True
    assert safety == {
        "github_write_performed": False,
        "result_packet_written": True,
        "codex_side_action_executed": True,
        "runner_invoked": True,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "broad_scan_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "pr_created": False,
        "merge_performed": False,
        "issue_closed": False,
        "label_changed": False,
    }
    assert result["result"] == "success"
    assert result["blocked_reasons"] == []
    assert result["verification_invoked"] is True
    assert observed["verification"] == 1
    assert len(observed["render"]) == 1
    assert canonical["safety_flags"] == safety
    assert canonical["runner_machine_evidence"]["safety_flags"] == safety
    assert observed["render"][0]["safety_flags"] == safety
    assert observed["render"][0]["runner_machine_evidence"]["safety_flags"] == safety
    assert result["safety_flags"] == safety
    assert request_summary["safety_flags"] == safety


def test_reviewed_gh_path_resolves_to_the_exact_supplied_executable(tmp_path):
    reviewed = tmp_path / "reviewed-gh.exe"
    reviewed.write_text("", encoding="utf-8")
    rendered = str(reviewed).replace("\\", "/").replace("'", "''")
    result = run_script(
        tmp_path,
        prefix=prefix(),
        body=f"""
        $resolved = Resolve-ReviewedGitHubCliPath -Path '{rendered}'
        Write-Output $resolved
        """,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == reviewed.resolve()
