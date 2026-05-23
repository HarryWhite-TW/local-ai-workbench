import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v2.ps1"
MARKER = "QUEUE-RUNNER-RESULT protocol=lawb.queue_runner_result.v1"
HANDOFF_ACTION = "run-reviewbundle-handoff"


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


def _task(task_id: str, action: str, risk_level: str = "low", **extra) -> dict:
    task = {
        "task_id": task_id,
        "description": f"Run {action}.",
        "risk_level": risk_level,
        "allowed_action": action,
        "expected_inputs": ["repo"],
        "expected_outputs": ["summary"],
        "stop_after_completion": False,
        "approved_changed_files": [],
    }
    task.update(extra)
    return task


def _base_queue(tasks):
    return {
        "schema": "lawb.queue_definition.v1",
        "queue_id": "medium-risk-queue-test-102",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "parent_issue": 102,
        "branch": "master",
        "head": "1111111111111111111111111111111111111111",
        "max_codex_tasks_per_batch": 5,
        "max_runtime_minutes": 10,
        "tasks": tasks,
    }


def run_queue_script(tmp_path: Path, queue: dict, *, status: str = "") -> subprocess.CompletedProcess:
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(json.dumps(queue), encoding="utf-8")
    script = tmp_path / "run_medium_queue_test.ps1"
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
            $script:Status = {json.dumps(status)}

            function Assert-RepoRoot {{ return }}
            function Get-CurrentBranch {{ return "master" }}
            function Get-CurrentFullHead {{ return "1111111111111111111111111111111111111111" }}
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


def test_real_runqueue_accepts_reviewbundle_handoff_and_stops(tmp_path):
    queue = _base_queue(
        [
            _task("status", "git-status"),
            _task(
                "review",
                HANDOFF_ACTION,
                "medium",
                review_id="review-102",
                diff_fingerprint="diff-102",
                files_fingerprint="files-102",
            ),
            _task("commit", "commit-approved", "high"),
        ]
    )

    result = run_queue_script(tmp_path, queue)
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "stopped"
    assert [task["task_id"] for task in packet["completed_tasks"]] == ["status"]
    assert packet["stopped_at_task"] == "review"
    assert packet["stop_reason"] == "reviewbundle_handoff_completed"
    assert packet["risk_gate"] == "medium_review_required"
    assert packet["reviewbundle_handoff_task"]["allowed_action"] == HANDOFF_ACTION
    assert packet["reviewbundle_metadata_status"] == "available"
    assert packet["review_id"] == "review-102"
    assert packet["diff_fingerprint"] == "diff-102"
    assert packet["files_fingerprint"] == "files-102"
    assert "commit" not in {task["task_id"] for task in packet["completed_tasks"]}
    assert "GIT-WRITE-CALLS=0" in result.stdout


def test_handoff_reports_dirty_precondition_without_bypassing_safety(tmp_path):
    queue = _base_queue([_task("status", "git-status"), _task("review", HANDOFF_ACTION, "medium")])
    queue["allowed_dirty_files"] = ["scripts/local_runner_v2.ps1"]

    result = run_queue_script(tmp_path, queue, status=" M scripts/local_runner_v2.ps1")
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "stopped"
    assert packet["completed_tasks"][0]["task_id"] == "status"
    assert packet["stopped_at_task"] == "review"
    assert packet["reviewbundle_metadata_status"] == "blocked"
    assert packet["reviewbundle_metadata_block_reason"] == "dirty_candidate_precondition"
    assert "RUNNER-V1-REVIEWBUNDLE-CALLS=0" in result.stdout
    assert "RUNNER-V1-COMMIT-CALLS=0" in result.stdout
    assert "GH-CLOSE-CALLS=0" in result.stdout
    assert "GIT-WRITE-CALLS=0" in result.stdout


def test_old_run_reviewbundle_action_is_not_official_handoff(tmp_path):
    queue = _base_queue([_task("review", "run-reviewbundle", "medium")])

    result = run_queue_script(tmp_path, queue)
    assert_success(result)

    packet = extract_packet(result.stdout)
    assert packet["result"] == "failed"
    assert packet["stopped_at_task"] == "review"
    assert packet["stop_reason"] == "unsupported_action"
    assert packet["validations"]["actions_supported"]["status"] == "failed"
    assert "run-reviewbundle" in packet["validations"]["actions_supported"]["summary"]
