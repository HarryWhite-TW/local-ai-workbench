import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v2.ps1"
MARKER = "QUEUE-RUNNER-RESULT protocol=lawb.queue_runner_result.v1"
REQUIRED_RUN_SAFETY_FLAGS = {
    "foreground_manual_start",
    "bounded_task_count",
    "bounded_runtime",
    "no_background_watcher",
    "no_stage",
    "no_commit",
    "no_push",
    "no_issue_close",
    "no_label",
    "no_pr",
    "no_merge",
    "no_approval_chaining",
    "no_approval_token_consumption",
}


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


def _task(task_id: str, action: str, risk_level: str = "low") -> dict:
    return {
        "task_id": task_id,
        "description": f"Run {action}.",
        "risk_level": risk_level,
        "allowed_action": action,
        "expected_inputs": ["repo"],
        "expected_outputs": ["summary"],
        "stop_after_completion": False,
        "approved_changed_files": [],
    }


def _base_queue(**overrides):
    queue = {
        "schema": "lawb.queue_definition.v1",
        "queue_id": "queue-test-101",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "parent_issue": 101,
        "branch": "master",
        "head": "1111111111111111111111111111111111111111",
        "max_codex_tasks_per_batch": 10,
        "max_runtime_minutes": 10,
        "tasks": [_task("status", "git-status")],
    }
    queue.update(overrides)
    return queue


def run_queue_script(
    tmp_path: Path,
    queue_text: str,
    *,
    branch: str = "master",
    head: str = "1111111111111111111111111111111111111111",
    status: str = "",
) -> subprocess.CompletedProcess:
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(queue_text, encoding="utf-8")
    script = tmp_path / "run_queue_test.ps1"
    script.write_text(
        _runner_core()
        + textwrap.dedent(
            f"""

            $Repo = "HarryWhite-TW/local-ai-workbench"
            $QueueFile = {json.dumps(str(queue_file))}
            $script:RunnerV1ReviewBundleCalls = 0
            $script:RunnerV1CommitCalls = 0
            $script:GhCloseCalls = 0
            $script:GitWriteCalls = 0
            $script:Branch = {json.dumps(branch)}
            $script:Head = {json.dumps(head)}
            $script:Status = {json.dumps(status)}

            function Assert-RepoRoot {{ return }}
            function Get-CurrentBranch {{ return $script:Branch }}
            function Get-CurrentFullHead {{ return $script:Head }}
            function Get-GitStatusShort {{ return $script:Status }}
            function Get-IssueApprovalMarkerReadResult {{
                param([int]$IssueNumber)
                return [pscustomobject]@{{ IssueNumber = $IssueNumber; IssueState = "OPEN"; Markers = @() }}
            }}
            function Invoke-RunnerV1ReviewBundle {{
                $script:RunnerV1ReviewBundleCalls += 1
                return 0
            }}
            function Invoke-RunnerV1CommitApproved {{
                $script:RunnerV1CommitCalls += 1
                return 0
            }}
            function Invoke-GhIssueCloseOnce {{
                $script:GhCloseCalls += 1
                return [pscustomobject]@{{ ExitCode = 0; Stdout = "closed"; Stderr = "" }}
            }}
            function Get-GitOutput {{
                param([string[]]$GitArgs, [string]$Action)
                $joined = $GitArgs -join " "
                if ($joined -match "^(add|commit|push|merge)") {{
                    $script:GitWriteCalls += 1
                    throw "Unexpected write-like git call: $joined"
                }}
                return ""
            }}

            Invoke-RunQueue
            Write-Host "RUNNER-V1-REVIEWBUNDLE-CALLS=$script:RunnerV1ReviewBundleCalls"
            Write-Host "RUNNER-V1-COMMIT-CALLS=$script:RunnerV1CommitCalls"
            Write-Host "GH-CLOSE-CALLS=$script:GhCloseCalls"
            Write-Host "GIT-WRITE-CALLS=$script:GitWriteCalls"
            """
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def extract_packet(stdout: str) -> dict:
    lines = stdout.splitlines()
    marker_index = lines.index(MARKER)
    assert lines[marker_index + 1].startswith("{")

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


def assert_success(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_valid_low_risk_queue_executes_read_only_tasks(tmp_path):
    queue = _base_queue(
        tasks=[
            _task("status", "git-status"),
            _task("head", "branch-head-check"),
            _task("issue", "issue-state-check"),
            _task("marker", "marker-readback"),
            _task("audit", "read-only-audit"),
            _task("verify", "runner-result-verification"),
            _task("final", "final-read-only-audit"),
        ]
    )

    result = run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "success"
    assert packet["dry_run"] is False
    assert [task["task_id"] for task in packet["completed_tasks"]] == [
        "status",
        "head",
        "issue",
        "marker",
        "audit",
        "verify",
        "final",
    ]
    assert packet["skipped_tasks"] == []
    assert packet["stopped_at_task"] is None
    assert packet["stop_reason"] is None
    assert packet["risk_gate"] == "none"


def test_medium_risk_task_becomes_stop_gate(tmp_path):
    queue = _base_queue(tasks=[_task("status", "git-status"), _task("review", "run-reviewbundle", "medium")])

    result = run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "stopped"
    assert [task["task_id"] for task in packet["completed_tasks"]] == ["status"]
    assert packet["stopped_at_task"] == "review"
    assert packet["stop_reason"] == "medium_risk_task_reached"
    assert packet["risk_gate"] == "medium_review"
    assert packet["skipped_tasks"] == [{"task_id": "review", "reason": "medium_risk_stop_gate"}]


def test_high_risk_task_becomes_stop_gate(tmp_path):
    queue = _base_queue(tasks=[_task("status", "git-status"), _task("push", "push-once", "high")])

    result = run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "stopped"
    assert [task["task_id"] for task in packet["completed_tasks"]] == ["status"]
    assert packet["stopped_at_task"] == "push"
    assert packet["stop_reason"] == "high_risk_task_reached"
    assert packet["risk_gate"] == "high_risk_user_approval"
    assert packet["skipped_tasks"] == [{"task_id": "push", "reason": "high_risk_stop_gate"}]


def test_unsupported_low_risk_action_fails_closed(tmp_path):
    queue = _base_queue(tasks=[_task("bad", "dry-run-bounded-poll")])

    result = run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["completed_tasks"] == []
    assert packet["stopped_at_task"] == "bad"
    assert packet["stop_reason"] == "unsupported_action"
    assert packet["skipped_tasks"] == [{"task_id": "bad", "reason": "unsupported_action"}]


def test_malformed_queue_fails_closed(tmp_path):
    result = run_queue_script(tmp_path, "{ not-json")
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stop_reason"] == "malformed_queue_definition"
    assert packet["completed_tasks"] == []
    assert packet["validations"]["queue_json_parseable"]["status"] == "failed"


def test_repo_branch_head_mismatch_fails_closed(tmp_path):
    queue = _base_queue(repo="Other/repo", branch="other", head="2222222222222222222222222222222222222222")

    result = run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stop_reason"] == "repo_branch_head_mismatch"
    assert packet["completed_tasks"] == []
    assert packet["validations"]["repo_match"]["status"] == "failed"
    assert packet["validations"]["branch_match"]["status"] == "failed"
    assert packet["validations"]["head_match"]["status"] == "failed"


def test_unexpected_dirty_state_fails_closed_unless_allowed(tmp_path):
    result = run_queue_script(tmp_path, json.dumps(_base_queue()), status=" M docs/example.md")
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stop_reason"] == "unexpected_git_dirty_state"
    assert packet["completed_tasks"] == []
    assert packet["validations"]["git_status_scope"]["status"] == "failed"

    allowed_queue = _base_queue(allowed_dirty_files=["docs/example.md"])
    allowed_result = run_queue_script(tmp_path, json.dumps(allowed_queue), status=" M docs/example.md")
    assert_success(allowed_result)
    allowed_packet = extract_packet(allowed_result.stdout)
    assert allowed_packet["result"] == "success"
    assert allowed_packet["validations"]["git_status_scope"]["status"] == "passed"


def test_run_queue_emits_parseable_result_and_safety_flags(tmp_path):
    result = run_queue_script(tmp_path, json.dumps(_base_queue()))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["schema"] == "lawb.queue_runner_result.v1"
    assert set(packet["safety"]) == REQUIRED_RUN_SAFETY_FLAGS
    assert all(value is True for value in packet["safety"].values())
    assert packet["next_recommended_action"] == "chatgpt_review"


def test_no_stage_commit_push_close_or_runner_v1_calls_occur(tmp_path):
    result = run_queue_script(tmp_path, json.dumps(_base_queue()))
    assert_success(result)

    assert "RUNNER-V1-REVIEWBUNDLE-CALLS=0" in result.stdout
    assert "RUNNER-V1-COMMIT-CALLS=0" in result.stdout
    assert "GH-CLOSE-CALLS=0" in result.stdout
    assert "GIT-WRITE-CALLS=0" in result.stdout
