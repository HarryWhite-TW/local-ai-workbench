import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "LOCAL_RELAY_READBACK_SMOKE.md"
SCRIPT = REPO_ROOT / "scripts" / "local_bridge_relay_smoke.ps1"
TASK_PACKET = REPO_ROOT / "docs" / "bridge_task_packet.readback_smoke.example.json"
RESULT_PACKET = REPO_ROOT / "docs" / "bridge_result_packet.readback_smoke.example.json"
MARKER = "BRIDGE-RESULT-PACKET protocol=lawb.bridge_result_packet.v1"


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

    for packet in (task, result):
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
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-TaskPacketFile",
            str(TASK_PACKET),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )

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
