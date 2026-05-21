import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v2.ps1"
MARKER = "QUEUE-RUNNER-RESULT protocol=lawb.queue_runner_result.v1"
REQUIRED_SAFETY_FLAGS = {
    "foreground_manual_start",
    "bounded_task_count",
    "bounded_runtime",
    "no_background_watcher",
    "no_task_execution",
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


def _base_queue(**overrides):
    queue = {
        "schema": "lawb.queue_definition.v1",
        "queue_id": "queue-test-1",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "parent_issue": 100,
        "branch": "master",
        "head": "1111111111111111111111111111111111111111",
        "max_codex_tasks_per_batch": 2,
        "max_runtime_minutes": 10,
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Read current status.",
                "risk_level": "low",
                "allowed_action": "git-status",
                "expected_inputs": ["repo"],
                "expected_outputs": ["status summary"],
                "stop_after_completion": False,
                "approved_changed_files": [],
            }
        ],
    }
    queue.update(overrides)
    return queue


def run_dry_run_queue_script(tmp_path: Path, queue_text: str) -> subprocess.CompletedProcess:
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(queue_text, encoding="utf-8")
    script = tmp_path / "dry_run_queue_test.ps1"
    script.write_text(
        _runner_core()
        + textwrap.dedent(
            f"""

            $Repo = "HarryWhite-TW/local-ai-workbench"
            $QueueFile = {json.dumps(str(queue_file))}
            $script:RunnerV1ReviewBundleCalls = 0

            function Assert-RepoRoot {{ return }}
            function Get-CurrentBranch {{ return "master" }}
            function Get-CurrentFullHead {{ return "1111111111111111111111111111111111111111" }}
            function Get-GitStatusShort {{ return "" }}
            function Invoke-RunnerV1ReviewBundle {{
                $script:RunnerV1ReviewBundleCalls += 1
                return 0
            }}

            Invoke-DryRunQueue
            Write-Host "RUNNER-V1-REVIEWBUNDLE-CALLS=$script:RunnerV1ReviewBundleCalls"
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


def test_valid_low_risk_queue_dry_run_emits_planned_task(tmp_path):
    result = run_dry_run_queue_script(tmp_path, json.dumps(_base_queue()))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["schema"] == "lawb.queue_runner_result.v1"
    assert packet["result"] == "success"
    assert packet["dry_run"] is True
    assert packet["planned_tasks"][0]["task_id"] == "task-1"
    assert packet["planned_tasks"][0]["planned_result"] == "not_executed_dry_run"
    assert packet["skipped_tasks"] == []
    assert packet["stop_reason"] is None


def test_high_risk_task_becomes_stop_gate(tmp_path):
    queue = _base_queue(
        tasks=[
            {
                "task_id": "push-step",
                "description": "Would push if this were not a dry-run.",
                "risk_level": "high",
                "allowed_action": "git-status",
                "expected_inputs": [],
                "expected_outputs": [],
                "stop_after_completion": False,
            }
        ]
    )

    result = run_dry_run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "stopped"
    assert packet["stopped_at_task"] == "push-step"
    assert packet["stop_reason"] == "high_risk_task_reached"
    assert packet["risk_gate"] == "high_risk_user_approval"


def test_malformed_queue_fails_closed(tmp_path):
    result = run_dry_run_queue_script(tmp_path, "{ not-json")
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stop_reason"] == "malformed_queue_definition"
    assert packet["validations"]["queue_json_parseable"]["status"] == "failed"


def test_task_count_exceeding_max_fails_closed(tmp_path):
    task = _base_queue()["tasks"][0]
    queue = _base_queue(max_codex_tasks_per_batch=1, tasks=[task, {**task, "task_id": "task-2"}])

    result = run_dry_run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stop_reason"] == "task_count_exceeds_max_codex_tasks_per_batch"
    assert packet["validations"]["task_count"]["status"] == "failed"


def test_unsupported_action_fails_closed(tmp_path):
    task = _base_queue()["tasks"][0]
    queue = _base_queue(tasks=[{**task, "allowed_action": "push-once"}])

    result = run_dry_run_queue_script(tmp_path, json.dumps(queue))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stopped_at_task"] == "task-1"
    assert packet["stop_reason"] == "unsupported_action"
    assert packet["skipped_tasks"] == [{"task_id": "task-1", "reason": "unsupported_action"}]


def test_dry_run_does_not_execute_runner_actions(tmp_path):
    result = run_dry_run_queue_script(tmp_path, json.dumps(_base_queue()))
    assert_success(result)

    assert "RUNNER-V1-REVIEWBUNDLE-CALLS=0" in result.stdout


def test_dry_run_emits_parseable_queue_runner_result_with_safety_flags(tmp_path):
    result = run_dry_run_queue_script(tmp_path, json.dumps(_base_queue()))
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert set(packet["safety"]) == REQUIRED_SAFETY_FLAGS
    assert all(value is True for value in packet["safety"].values())
    assert packet["validations"]["dry_run_no_execution"]["status"] == "passed"


def test_full_dry_run_queue_command_emits_parseable_result(tmp_path):
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    queue = _base_queue(branch=branch, head=head)
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(json.dumps(queue), encoding="utf-8")

    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-DryRunQueue",
            "-QueueFile",
            str(queue_file),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["schema"] == "lawb.queue_runner_result.v1"
    assert packet["queue_id"] == "queue-test-1"
