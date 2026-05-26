import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "LOCAL_RELAY_READBACK_SMOKE.md"
SCRIPT = REPO_ROOT / "scripts" / "local_bridge_relay_smoke.ps1"
TASK_PACKET = REPO_ROOT / "docs" / "bridge_task_packet.readback_smoke.example.json"
RESULT_PACKET = REPO_ROOT / "docs" / "bridge_result_packet.readback_smoke.example.json"
GITHUB_TASK_PACKET = REPO_ROOT / "docs" / "bridge_task_packet.github_readback_smoke.example.json"
GITHUB_RESULT_PACKET = REPO_ROOT / "docs" / "bridge_result_packet.github_readback_smoke.example.json"
CODEX_COMMAND_TASK_PACKET = REPO_ROOT / "docs" / "bridge_task_packet.codex_command_smoke.example.json"
CODEX_COMMAND_RESULT_PACKET = REPO_ROOT / "docs" / "bridge_result_packet.codex_command_smoke.example.json"
MARKER = "BRIDGE-RESULT-PACKET protocol=lawb.bridge_result_packet.v1"
TASK_MARKER = "BRIDGE-TASK-PACKET protocol=lawb.bridge_task_packet.v1"


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local bridge relay smoke tests")
    return shell


def _extract_packet(stdout: str) -> dict:
    lines = stdout.splitlines()
    marker_index = lines.index(MARKER)
    json_text = "\n".join(lines[marker_index + 1 :])
    return json.loads(json_text)


def _github_task_packet(**overrides) -> dict:
    packet = {
        "schema": "lawb.bridge_task_packet.v1",
        "packet_id": "bridge-github-readback-smoke-109-task-001",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "issue": 109,
        "branch": "master",
        "base_head": "305f021daa98eb56a9fb117457a5b71bc15c2098",
        "requested_by": "chatgpt",
        "task_role": "core",
        "manual_copy_paste_is_target": False,
        "expires_utc": "20990101T000000Z",
        "action": "bounded-dry-echo",
        "command": {
            "kind": "local-dry-action",
            "description": "Echo a bounded GitHub readback smoke message without modifying files.",
            "timeout_seconds": 30,
            "message": "github packet readback smoke",
        },
        "writeback": {
            "surface": "github_issue_comment",
            "issue": 109,
            "requires_explicit_post_result_comment": True,
        },
        "expected_result_packet": "lawb.bridge_result_packet.v1",
        "safety": {
            "foreground_manual_start_only": True,
            "no_background_watcher": True,
            "no_always_on_polling": True,
            "no_stage": True,
            "no_commit": True,
            "no_push": True,
            "no_issue_close": True,
            "no_label": True,
            "no_pr": True,
            "no_merge": True,
            "no_approval_chaining": True,
            "no_real_codex_code_modification": True,
        },
    }
    packet.update(overrides)
    return packet


def _codex_command_task_packet(**overrides) -> dict:
    packet = {
        "schema": "lawb.bridge_task_packet.v1",
        "packet_id": "bridge-codex-command-smoke-110-task-001",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "issue": 110,
        "branch": "master",
        "base_head": "0925f2188b4781a0c9d76d727b0b456e6fea8cea",
        "requested_by": "chatgpt",
        "task_role": "core",
        "manual_copy_paste_is_target": False,
        "expires_utc": "20990101T000000Z",
        "action": "bounded-local-command",
        "command": {
            "kind": "local-git-status-summary",
            "description": "Read-only repository status summary.",
            "timeout_seconds": 30,
        },
        "writeback": {
            "surface": "github_issue_comment",
            "issue": 110,
            "requires_explicit_post_result_comment": True,
        },
        "expected_result_packet": "lawb.bridge_result_packet.v1",
        "safety": {
            "foreground_manual_start_only": True,
            "no_background_watcher": True,
            "no_always_on_polling": True,
            "no_stage": True,
            "no_commit": True,
            "no_push": True,
            "no_issue_close": True,
            "no_label": True,
            "no_pr": True,
            "no_merge": True,
            "no_approval_chaining": True,
            "no_real_codex_code_modification": True,
        },
    }
    packet.update(overrides)
    return packet


def _task_packet_text(packet: dict | str) -> str:
    if isinstance(packet, str):
        return TASK_MARKER + "\n" + packet
    return TASK_MARKER + "\n" + json.dumps(packet, indent=2)


def _write_fake_gh(
    tmp_path: Path,
    issue_body: str,
    comments: list[str] | None = None,
    issue_number: int = 109,
) -> Path:
    payload = {
        "number": issue_number,
        "state": "OPEN",
        "title": "Local relay GitHub packet read and result writeback runtime verification",
        "url": f"https://github.com/HarryWhite-TW/local-ai-workbench/issues/{issue_number}",
        "body": issue_body,
        "comments": [{"body": body} for body in (comments or [])],
    }
    payload_file = tmp_path / "issue_payload.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    record_file = tmp_path / "gh_comment_calls.txt"
    fake_gh = tmp_path / "gh.cmd"
    fake_gh.write_text(
        "\n".join(
            [
                "@echo off",
                f'if "%1"=="issue" if "%2"=="view" if "%3"=="{issue_number}" (',
                f'  type "{payload_file}"',
                "  exit /b 0",
                ")",
                f'if "%1"=="issue" if "%2"=="comment" if "%3"=="{issue_number}" (',
                f'  echo comment>>"{record_file}"',
                "  exit /b 0",
                ")",
                "echo unexpected gh arguments: %* 1>&2",
                "exit /b 2",
            ]
        ),
        encoding="utf-8",
    )
    return record_file


def _run_relay(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        env=env,
    )


def test_relay_smoke_document_defines_target_readback_without_drift():
    text = DOC.read_text(encoding="utf-8")

    assert "manual_copy_paste_is_target=false" in text
    assert "Manual relay remains fallback only" in text
    assert "ChatGPT writes a bridge task packet to GitHub" in text
    assert "local foreground relay reads the task packet" in text
    assert "BRIDGE-RESULT-PACKET" in text
    assert "ChatGPT reads the result packet from GitHub" in text
    assert "foreground_manual_start_only=true" in text
    assert "harmless_dry_action_only=true" in text
    assert "github_result_writeback_defined=true" in text
    assert "chatgpt_readback_path_defined=true" in text
    assert "No background watcher" not in text
    assert "does not implement background watching" in text


def test_readback_smoke_packets_are_parseable_and_safe():
    task = json.loads(TASK_PACKET.read_text(encoding="utf-8"))
    result = json.loads(RESULT_PACKET.read_text(encoding="utf-8"))
    github_task = json.loads(GITHUB_TASK_PACKET.read_text(encoding="utf-8"))
    github_result = json.loads(GITHUB_RESULT_PACKET.read_text(encoding="utf-8"))
    codex_command_task = json.loads(CODEX_COMMAND_TASK_PACKET.read_text(encoding="utf-8"))
    codex_command_result = json.loads(CODEX_COMMAND_RESULT_PACKET.read_text(encoding="utf-8"))

    assert task["schema"] == "lawb.bridge_task_packet.v1"
    assert task["issue"] == 107
    assert task["requested_by"] == "chatgpt"
    assert task["task_role"] == "core"
    assert task["manual_copy_paste_is_target"] is False
    assert task["action"] == "bounded-dry-echo"
    assert task["command"]["kind"] == "local-dry-action"
    assert task["command"]["timeout_seconds"] <= 30
    assert task["writeback"]["surface"] == "github_issue_comment"
    assert task["writeback"]["requires_explicit_post_result_comment"] is True

    assert result["schema"] == "lawb.bridge_result_packet.v1"
    assert result["task_packet_id"] == task["packet_id"]
    assert result["issue"] == task["issue"]
    assert result["result"] == "success"
    assert result["action"] == task["action"]
    assert result["writeback_surface"] == "github_issue_comment"
    assert "GitHub issue comment" in result["chatgpt_readback_path"]
    assert github_task["schema"] == "lawb.bridge_task_packet.v1"
    assert github_task["issue"] == 109
    assert github_task["expires_utc"] == "20990101T000000Z"
    assert github_task["writeback"]["requires_explicit_post_result_comment"] is True
    assert github_result["schema"] == "lawb.bridge_result_packet.v1"
    assert github_result["task_packet_id"] == github_task["packet_id"]
    assert codex_command_task["schema"] == "lawb.bridge_task_packet.v1"
    assert codex_command_task["issue"] == 110
    assert codex_command_task["action"] == "bounded-local-command"
    assert codex_command_task["command"]["kind"] == "local-git-status-summary"
    assert "command_text" not in codex_command_task["command"]
    assert "args" not in codex_command_task["command"]
    assert codex_command_result["schema"] == "lawb.bridge_result_packet.v1"
    assert codex_command_result["task_packet_id"] == codex_command_task["packet_id"]
    assert codex_command_result["action"] == "bounded-local-command"
    assert codex_command_result["command_result"]["kind"] == "local-git-status-summary"

    for packet in (task, result, codex_command_task, codex_command_result):
        safety = packet["safety"]
        assert safety["foreground_manual_start_only"] is True
        assert safety["no_background_watcher"] is True
        assert safety["no_always_on_polling"] is True
        assert safety["no_stage"] is True
        assert safety["no_commit"] is True
        assert safety["no_push"] is True
        assert safety["no_issue_close"] is True
        assert safety["no_approval_chaining"] is True
        assert safety["no_real_codex_code_modification"] is True


def test_local_bridge_relay_smoke_runs_harmless_dry_action_only():
    result = _run_relay(["-TaskPacketFile", str(TASK_PACKET)])

    assert result.returncode == 0, result.stdout + result.stderr
    packet = _extract_packet(result.stdout)

    assert packet["schema"] == "lawb.bridge_result_packet.v1"
    assert packet["task_packet_id"] == "bridge-readback-smoke-107-task-001"
    assert packet["issue"] == 107
    assert packet["result"] == "success"
    assert packet["action"] == "bounded-dry-echo"
    assert packet["dry_action_output"] == "local relay readback smoke"
    assert packet["writeback_surface"] == "github_issue_comment"
    assert packet["next_recommended_action"] == "chatgpt_review"
    assert all(packet["safety"].values())


def test_local_git_status_summary_runs_allowlisted_read_only_command():
    result = _run_relay(["-TaskPacketFile", str(CODEX_COMMAND_TASK_PACKET)])

    assert result.returncode == 0, result.stdout + result.stderr
    packet = _extract_packet(result.stdout)
    command_result = packet["command_result"]

    assert packet["schema"] == "lawb.bridge_result_packet.v1"
    assert packet["task_packet_id"] == "bridge-codex-command-smoke-110-task-001"
    assert packet["issue"] == 110
    assert packet["result"] == "success"
    assert packet["action"] == "bounded-local-command"
    assert "dry_action_output" not in packet
    assert command_result["kind"] == "local-git-status-summary"
    assert command_result["branch"] == "master"
    assert len(command_result["head"]) == 40
    assert len(command_result["origin_master"]) == 40
    assert isinstance(command_result["git_status_short"], str)
    assert len(command_result["git_status_short"]) <= 2012
    assert isinstance(command_result["is_clean"], bool)
    assert packet["safety"]["no_real_codex_code_modification"] is True


def test_github_issue_local_git_status_summary_no_post_default(tmp_path):
    record_file = _write_fake_gh(
        tmp_path,
        _task_packet_text(_codex_command_task_packet()),
        issue_number=110,
    )
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]

    result = _run_relay(["-IssueNumber", "110", "-ReadTaskPacketFromGitHub"], env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    packet = _extract_packet(result.stdout)
    assert packet["result"] == "success"
    assert packet["action"] == "bounded-local-command"
    assert packet["command_result"]["kind"] == "local-git-status-summary"
    assert not record_file.exists()


def test_unknown_command_kind_fails_closed(tmp_path):
    task_file = tmp_path / "unknown-command.json"
    task_file.write_text(
        json.dumps(
            _codex_command_task_packet(
                command={
                    "kind": "local-directory-listing",
                    "description": "Unsupported command.",
                    "timeout_seconds": 30,
                }
            )
        ),
        encoding="utf-8",
    )

    result = _run_relay(["-TaskPacketFile", str(task_file)])

    assert result.returncode != 0
    assert "local-git-status-summary" in (result.stdout + result.stderr)


def test_unsafe_command_fields_fail_closed(tmp_path):
    task_file = tmp_path / "unsafe-command.json"
    task_file.write_text(
        json.dumps(
            _codex_command_task_packet(
                command={
                    "kind": "local-git-status-summary",
                    "description": "Unsafe command shape.",
                    "timeout_seconds": 30,
                    "command_text": "git status --short",
                }
            )
        ),
        encoding="utf-8",
    )

    result = _run_relay(["-TaskPacketFile", str(task_file)])

    assert result.returncode != 0
    assert "Unsupported unsafe command field: command_text" in (result.stdout + result.stderr)


def test_timeout_above_30_fails_closed(tmp_path):
    task_file = tmp_path / "slow-command.json"
    task_file.write_text(
        json.dumps(
            _codex_command_task_packet(
                command={
                    "kind": "local-git-status-summary",
                    "description": "Timeout should be rejected.",
                    "timeout_seconds": 31,
                }
            )
        ),
        encoding="utf-8",
    )

    result = _run_relay(["-TaskPacketFile", str(task_file)])

    assert result.returncode != 0
    assert "timeout_seconds must be <= 30" in (result.stdout + result.stderr)


def test_github_issue_task_packet_read_no_post_default(tmp_path):
    record_file = _write_fake_gh(tmp_path, _task_packet_text(_github_task_packet()))
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]

    result = _run_relay(["-IssueNumber", "109", "-ReadTaskPacketFromGitHub"], env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    packet = _extract_packet(result.stdout)
    assert packet["schema"] == "lawb.bridge_result_packet.v1"
    assert packet["task_packet_id"] == "bridge-github-readback-smoke-109-task-001"
    assert packet["issue"] == 109
    assert packet["result"] == "success"
    assert packet["action"] == "bounded-dry-echo"
    assert packet["dry_action_output"] == "github packet readback smoke"
    assert packet["writeback_surface"] == "github_issue_comment"
    assert packet["safety"]["no_real_codex_code_modification"] is True
    assert not record_file.exists()


def test_github_issue_task_packet_explicit_post_calls_gh_issue_comment(tmp_path):
    record_file = _write_fake_gh(tmp_path, _task_packet_text(_github_task_packet()))
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]

    result = _run_relay(
        ["-IssueNumber", "109", "-ReadTaskPacketFromGitHub", "-PostResultComment"],
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _extract_packet(result.stdout)["result"] == "success"
    assert record_file.read_text(encoding="utf-8").count("comment") == 1


def test_github_issue_duplicate_task_packets_fail_closed_without_posting(tmp_path):
    record_file = _write_fake_gh(
        tmp_path,
        _task_packet_text(_github_task_packet()),
        comments=[_task_packet_text(_github_task_packet(packet_id="duplicate"))],
    )
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]

    result = _run_relay(
        ["-IssueNumber", "109", "-ReadTaskPacketFromGitHub", "-PostResultComment"],
        env=env,
    )

    assert result.returncode != 0
    assert "Multiple BRIDGE-TASK-PACKET entries" in (result.stdout + result.stderr)
    assert not record_file.exists()


def test_github_issue_missing_task_packet_fails_closed_without_posting(tmp_path):
    record_file = _write_fake_gh(tmp_path, "No task packet here.")
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]

    result = _run_relay(
        ["-IssueNumber", "109", "-ReadTaskPacketFromGitHub", "-PostResultComment"],
        env=env,
    )

    assert result.returncode != 0
    assert "No BRIDGE-TASK-PACKET found" in (result.stdout + result.stderr)
    assert not record_file.exists()


def test_github_issue_malformed_task_packet_fails_closed_without_posting(tmp_path):
    record_file = _write_fake_gh(tmp_path, _task_packet_text("{ not-json"))
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]

    result = _run_relay(
        ["-IssueNumber", "109", "-ReadTaskPacketFromGitHub", "-PostResultComment"],
        env=env,
    )

    assert result.returncode != 0
    assert "Malformed BRIDGE-TASK-PACKET JSON" in (result.stdout + result.stderr)
    assert not record_file.exists()
