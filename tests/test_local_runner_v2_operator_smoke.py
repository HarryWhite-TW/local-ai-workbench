import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v2.ps1"
EXAMPLE_README = REPO_ROOT / "docs" / "QUEUE_RUNNER_OPERATOR_EXAMPLE.md"
EXAMPLE_QUEUE = REPO_ROOT / "docs" / "queue_runner_reviewbundle_handoff_queue.example.json"
MARKER = "QUEUE-RUNNER-RESULT protocol=lawb.queue_runner_result.v1"
REQUIRED_PACKET_FIELDS = {
    "completed_tasks",
    "skipped_tasks",
    "stopped_at_task",
    "stop_reason",
    "risk_gate",
    "validations",
    "safety",
    "next_recommended_action",
}


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local_runner_v2 tests")
    return shell


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _status_paths() -> list[str]:
    status = _git("status", "--porcelain")
    paths = []
    for line in status.splitlines():
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.replace("\\", "/"))
    return sorted(set(paths))


def _materialize_example_queue(tmp_path: Path) -> Path:
    queue = json.loads(EXAMPLE_QUEUE.read_text(encoding="utf-8"))
    queue["branch"] = _git("branch", "--show-current")
    queue["head"] = _git("rev-parse", "HEAD")
    dirty_files = _status_paths()
    if dirty_files:
        queue["allow_dirty"] = True
        queue["allowed_dirty_files"] = dirty_files

    queue_file = tmp_path / "reviewbundle_handoff_queue.local.json"
    queue_file.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return queue_file


def _run_queue_command(mode: str, queue_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            mode,
            "-QueueFile",
            str(queue_file),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=45,
    )


def _extract_packet(stdout: str) -> dict:
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


def _assert_success(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_operator_example_files_exist_and_queue_is_parseable():
    assert EXAMPLE_README.exists()
    assert EXAMPLE_QUEUE.exists()

    readme = EXAMPLE_README.read_text(encoding="utf-8")
    assert "DryRunQueue -> low-risk RunQueue -> run-reviewbundle-handoff stop" in readme
    assert "no background watcher" in readme
    assert "not an approval token" in readme

    queue = json.loads(EXAMPLE_QUEUE.read_text(encoding="utf-8"))
    assert queue["schema"] == "lawb.queue_definition.v1"
    assert queue["parent_issue"] == 104
    assert [task["allowed_action"] for task in queue["tasks"]] == [
        "git-status",
        "branch-head-check",
        "run-reviewbundle-handoff",
        "git-status",
    ]
    assert queue["tasks"][2]["risk_level"] == "medium"
    assert queue["tasks"][3]["risk_level"] == "high"


def test_operator_smoke_dryrun_and_runqueue_emit_single_review_packets(tmp_path):
    queue_file = _materialize_example_queue(tmp_path)

    dry_run = _run_queue_command("-DryRunQueue", queue_file)
    _assert_success(dry_run)
    dry_packet = _extract_packet(dry_run.stdout)

    assert REQUIRED_PACKET_FIELDS <= set(dry_packet)
    assert dry_packet["schema"] == "lawb.queue_runner_result.v1"
    assert dry_packet["dry_run"] is True
    assert dry_packet["queue_id"] == "operator-reviewbundle-handoff-smoke"
    assert dry_packet["validations"]["actions_supported"]["status"] == "passed"
    assert all(dry_packet["safety"].values())
    assert dry_packet["safety"]["no_task_execution"] is True
    assert len(dry_run.stdout) < 20000

    run = _run_queue_command("-RunQueue", queue_file)
    _assert_success(run)
    run_packet = _extract_packet(run.stdout)

    assert REQUIRED_PACKET_FIELDS <= set(run_packet)
    assert run_packet["schema"] == "lawb.queue_runner_result.v1"
    assert run_packet["dry_run"] is False
    assert run_packet["result"] == "stopped"
    assert [task["task_id"] for task in run_packet["completed_tasks"]] == ["status", "head-check"]
    assert run_packet["stopped_at_task"] == "reviewbundle-handoff"
    assert run_packet["stop_reason"] == "reviewbundle_handoff_completed"
    assert run_packet["risk_gate"] == "medium_review_required"
    assert run_packet["reviewbundle_handoff_task"]["allowed_action"] == "run-reviewbundle-handoff"
    assert "must-not-run-high-risk" not in {task["task_id"] for task in run_packet["completed_tasks"]}
    assert all(run_packet["safety"].values())
    assert run_packet["next_recommended_action"] == "chatgpt_review"
    assert len(run.stdout) < 20000
