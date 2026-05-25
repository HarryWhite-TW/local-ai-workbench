import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_DOC = REPO_ROOT / "docs" / "BRIDGE_FEASIBILITY_PROBE.md"
TASK_PACKET = REPO_ROOT / "docs" / "bridge_task_packet.example.json"
RESULT_PACKET = REPO_ROOT / "docs" / "bridge_result_packet.example.json"


def test_bridge_probe_document_defines_core_readback_loop():
    text = PROBE_DOC.read_text(encoding="utf-8")

    assert "bridge_feasibility_result=partial" in text
    assert "manual_copy_paste_is_target=false" in text
    assert "BRIDGE-TASK-PACKET protocol=lawb.bridge_task_packet.v1" in text
    assert "BRIDGE-RESULT-PACKET protocol=lawb.bridge_result_packet.v1" in text
    assert "ChatGPT writes `BRIDGE-TASK-PACKET` to a GitHub issue body or comment" in text
    assert "The relay reads the GitHub issue text" in text
    assert "The relay writes `BRIDGE-RESULT-PACKET` back to the same GitHub issue" in text
    assert "ChatGPT reads the GitHub result packet directly" in text
    assert "background watcher" in text
    assert "always-on polling" in text
    assert "no_background_watcher" in text
    assert "no_always_on_polling" in text
    assert "no_commit" in text
    assert "The result packet is not an approval token" in text


def test_bridge_probe_packets_are_parseable_and_bounded():
    task = json.loads(TASK_PACKET.read_text(encoding="utf-8"))
    result = json.loads(RESULT_PACKET.read_text(encoding="utf-8"))

    assert task["schema"] == "lawb.bridge_task_packet.v1"
    assert task["packet_id"] == "bridge-probe-106-task-001"
    assert task["repo"] == "HarryWhite-TW/local-ai-workbench"
    assert task["issue"] == 106
    assert task["requested_by"] == "chatgpt"
    assert task["task_role"] == "core"
    assert task["manual_copy_paste_is_target"] is False
    assert task["action"] == "bounded-dry-echo"
    assert task["command"]["kind"] == "local-dry-action"
    assert task["command"]["timeout_seconds"] == 30
    assert task["expected_result_packet"] == "lawb.bridge_result_packet.v1"

    assert result["schema"] == "lawb.bridge_result_packet.v1"
    assert result["task_packet_id"] == task["packet_id"]
    assert result["repo"] == task["repo"]
    assert result["issue"] == task["issue"]
    assert result["result"] == "partial"
    assert result["action"] == task["action"]
    assert result["next_recommended_action"] == "chatgpt_review"
    assert result["remaining_user_actions"]

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
