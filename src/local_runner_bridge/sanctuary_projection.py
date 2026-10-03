"""Ephemeral presentation of the existing Workflow snapshot, never lifecycle authority.

No writes, network calls, approval decisions, or persisted animation state belong here.
The original snapshot is returned separately to the human and expert surfaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from local_runner_bridge.workflow_observability import _observation_time, _valid_record

SNAPSHOT_MAX_AGE_SECONDS = 10
ACTIVITY_MAX_AGE_SECONDS = 30
TEST_EXECUTABLES = frozenset({"pytest", "pytest.exe", "vitest", "jest", "ctest"})
ACTIVITY_KINDS = frozenset({
    "execution.started", "codex.error", "codex.turn.started", "codex.turn.completed", "codex.turn.failed",
    *(f"codex.{item}.{phase}" for item in ("command", "file", "tool")
      for phase in ("started", "updated", "completed")), "codex.command.failed",
})


def _time(value: Any) -> datetime | None:
    return _observation_time(value)


def _age(value: Any, now: datetime) -> float | None:
    parsed = _time(value)
    return (now - parsed).total_seconds() if parsed else None


def _test_command(payload: dict[str, Any]) -> bool:
    if "activity_kind" in payload:
        return (payload.get("activity_kind") == "test"
                and payload.get("test_framework") in ("pytest", "vitest", "jest", "ctest"))
    return str(payload.get("command_name", "")).lower() in TEST_EXECUTABLES


def project_sanctuary(
    snapshot: dict[str, Any], events: list[dict[str, Any]], *, now: datetime | None = None,
    observation_diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    """Derive a bounded pose and human context from canonical, sanitized evidence.

    A pose is disposable: polling/reconnect recalculates it from current evidence.
    Neither a movement finishing nor a process exit can advance Workflow lifecycle.
    """
    now = now or datetime.now(timezone.utc)
    task = snapshot.get("current_task") or {}
    lifecycle = task.get("lifecycle") or {}
    review = snapshot.get("review") or {}
    evidence = review.get("evidence") or {}
    verdict = review.get("final_verdict") or {}
    sources = snapshot.get("source_status") or {}
    observation = snapshot.get("observability") or {}
    system = snapshot.get("system") or {}
    request_id, run_id = task.get("request_id"), observation.get("run_id")
    stage = lifecycle.get("stage", "UNKNOWN")
    result: dict[str, Any] = {
        "protocol": "lawb.sanctuary_projection.v1",
        "source_lifecycle": stage,
        "identity": {"request_id": request_id, "run_id": run_id},
        "pose": "uncertain",
        "station": "core",
        "actor": None,
        "artifact": None,
        "activity": None,
        "activity_sequence": None,
        "activity_until_utc": None,
        "semantic_motion": False,
        "tone": "quiet",
        "title": "等待可信任的工作訊號",
        "description": "基地正在等候目前任務的證據。",
        "health": system.get("operator", "unknown"),
        "reasons": [],
        "human": {
            "attention": False,
            "kind": "UNKNOWN",
            "owner": "尚無法確認",
            "proposal_status": "unavailable",
            "what": "目前沒有已證明的人類決策請求。",
            "why": "世界只呈現 Workflow 已提供的證據。",
            "operation": "尚無可核對的下一步操作提案。",
            "scope": "操作範圍未提供；不由畫面推定。",
            "evidence": evidence.get("pointer") if evidence.get("status") == "available" else None,
            "write_enabled": False,
        },
    }

    def uncertain(reason: str, title: str = "目前活動無法確認") -> dict[str, Any]:
        result.update(pose="uncertain", semantic_motion=False, actor=None,
                      activity=None, activity_until_utc=None, title=title, tone="muted")
        result["reasons"].append(reason)
        result["description"] = "活動已停止呈現；保留可核對的來源，等待新證據。"
        result["human"].update(kind="UNKNOWN", owner="尚無法確認", attention=False)
        return result

    if snapshot.get("protocol") != "lawb.workflow_panel.v1" or snapshot.get("mode") != "read_only" or snapshot.get("bind") != "loopback":
        return uncertain("snapshot_contract_invalid")
    age = _age(snapshot.get("observed_at_utc"), now)
    if age is None or not -2 <= age <= SNAPSHOT_MAX_AGE_SECONDS:
        return uncertain("snapshot_stale_or_invalid", "這份畫面證據已過期")
    if lifecycle.get("certainty") not in {"verified", "observed"}:
        return uncertain("lifecycle_uncertain")
    if stage in {"NO_REQUEST_DETECTED", "CHECKING_FOR_WORK", "IDLE"}:
        result.update(pose="idle", title="基地待命中", description="目前沒有已接手的工作。")
        if system.get("operator") != "online":
            return uncertain("operator_unavailable", "基地目前離線")
        result["human"].update(kind="NONE", owner="無待辦交接", what="目前沒有已接手的工作。")
        return result
    if not isinstance(request_id, str) or not request_id:
        return uncertain("request_identity_missing")

    # Durable review facts do not disappear just because the Operator goes offline.
    # Their presentation is static; a historical accepted result never animates work.
    if stage == "FINAL_ACCEPTED":
        if not (lifecycle.get("certainty") == "verified"
                and lifecycle.get("basis") == "final_review_verdict:accepted"
                and verdict.get("status") == "available" and verdict.get("verdict") == "accepted"
                and sources.get("final_review_verdicts") == "available"):
            return uncertain("accepted_evidence_mismatch")
        result.update(pose="accepted", station="review", artifact="accepted", tone="mint",
                      title="這份結果已通過審查", description="已收到 Workflow 的最終接受證據。")
        result["human"].update(what="目前不需要你做決策。", why="最終審查已接受這份結果。",
                               kind="NONE", owner="無待辦交接",
                               evidence=verdict.get("evidence_pointer"))
        return result
    if stage in {"REPAIR_REQUIRED", "FINAL_REVIEW_BLOCKED"}:
        expected = "repair_required" if stage == "REPAIR_REQUIRED" else "blocked"
        if not (verdict.get("status") == "available" and verdict.get("verdict") == expected
                and sources.get("final_review_verdicts") == "available"
                and lifecycle.get("certainty") == "verified"):
            return uncertain("review_evidence_mismatch")
        result.update(pose="attention", station="review", artifact="needs_attention", tone="amber",
                      title="技術審查需要後續處理", description="審查尚未接受成果；技術處理與人類授權分開呈現。")
        # No trusted human-decision proposal exists in the incumbent snapshot.
        # Repair describes technical ownership, never grants execution permission.
        result["human"].update(attention=False, kind="TECHNICAL_ACTION", owner="技術處理／審查方",
                               what="下一步由技術處理／審查方接手。",
                               why="最終審查要求修復。" if expected == "repair_required" else "最終審查回報阻擋。",
                               operation="尚無可信的人類決策提案。",
                               scope="尚未提供；技術待辦不代表新的操作授權。",
                               evidence=verdict.get("evidence_pointer"))
        return result
    if stage == "WAITING_FOR_CHATGPT_REVIEW":
        if lifecycle.get("certainty") != "verified":
            return uncertain("review_lifecycle_unverified")
        candidate = sources.get("review_candidate") == "available"
        result.update(pose="review", station="review", artifact="candidate" if candidate else "result",
                      tone="violet", title="成果已送到審查區",
                      description="等待 ChatGPT 審查，尚未接受。" if candidate else "等待 ChatGPT 審查；目前無法核對 candidate 身分。")
        result["human"].update(what="目前在等 ChatGPT 審查，不是等待你批准。",
                               kind="CHATGPT_REVIEW", owner="ChatGPT／最終審查方",
                               why="執行結果不等於最終接受。")
        return result
    if stage in {"BLOCKED_OR_FAILED", "EXPIRED"}:
        result.update(pose="blocked", artifact="blocked", tone="coral", title="工作已停下來",
                      description="Workflow 回報阻擋、失敗或到期；請檢視來源原因。")
        result["human"].update(kind="TECHNICAL_ACTION", owner="技術處理／審查方",
                               what="技術待辦：核對阻擋或失敗原因。", why="畫面不會自行重試或繼續執行。")
        return result
    if stage == "COMPLETED_OR_LAST_COMPLETED":
        result.update(pose="settled", artifact="result", title="執行已結束",
                      description="這是執行結果；沒有將它升級成審查接受。")
        return result
    if system.get("operator") != "online":
        return uncertain("operator_" + str(system.get("operator", "unknown")), "連線需要確認，工作動態已停止")
    if sources.get("in_flight") == "invalid" or snapshot.get("diagnostics") or observation_diagnostics:
        return uncertain("source_evidence_degraded")
    if stage in {"REQUEST_DETECTED", "DISPATCHING"}:
        result.update(pose="arriving", artifact="brief", tone="cyan", title="有一份工作來到基地",
                      description="請求已被偵測，尚未宣稱 Codex 已開始執行。")
        result["human"].update(kind="SYSTEM", owner="Workflow Operator", what="等待既有 Operator 處理。")
        return result
    if stage != "RUNNING" or lifecycle.get("certainty") != "verified":
        return uncertain("unsupported_lifecycle")
    if not isinstance(run_id, str) or not run_id:
        return uncertain("run_identity_missing")
    if observation.get("run_started") is not True:
        return uncertain("run_start_not_observed")
    latest = observation.get("latest_sequence")
    if isinstance(latest, bool) or not isinstance(latest, int) or latest < 1:
        return uncertain("event_cursor_missing")

    by_sequence: dict[int, dict[str, Any]] = {}
    detected = _time(task.get("detected_at_utc"))
    for event in events:
        if not _valid_record(event):
            continue
        if event["request_id"] != request_id or event["run_id"] != run_id or event["sequence"] > latest:
            continue
        kind = event["kind"]
        if kind in ACTIVITY_KINDS or kind == "process.completed":
            expected_source = "runner" if kind in {"execution.started", "process.completed"} else "codex_exec_jsonl"
            if event["source"] != expected_source or (
                kind == "execution.started" and event["payload"].get("interface") != "codex_exec_jsonl"
            ):
                return uncertain("activity_source_invalid")
        elif kind.startswith(("codex.turn.", "codex.command.", "codex.file.", "codex.tool.")):
            return uncertain("activity_kind_unknown")
        previous = by_sequence.get(event["sequence"])
        if previous is not None and previous != event:
            return uncertain("ambiguous_event_sequence")
        timestamp = _time(event.get("observed_at_utc"))
        if timestamp is None or timestamp > now or (detected and timestamp < detected):
            return uncertain("event_time_identity_mismatch")
        by_sequence[event["sequence"]] = event
    matching = [by_sequence[n] for n in sorted(by_sequence)]
    if not matching:
        return uncertain("no_matching_run_activity")
    if any(_time(a["observed_at_utc"]) > _time(b["observed_at_utc"]) for a,b in zip(matching,matching[1:])):
        return uncertain("event_order_ambiguous")
    if observation.get("run_completed") is True or any(e["kind"] == "process.completed" for e in matching):
        result.update(pose="settled", artifact="result", title="執行動態已結束",
                      description="行程已結束，仍等待 Workflow 的 durable 結果；不代表接受。")
        result["human"].update(kind="SYSTEM", owner="Workflow Operator", what="等待既有 Operator 核對 durable 結果。")
        return result
    relevant = [e for e in matching if e["kind"] in ACTIVITY_KINDS]
    if not relevant:
        return uncertain("execution_not_observed")
    last = relevant[-1]
    age = _age(last["observed_at_utc"], now)
    if age is None or age > ACTIVITY_MAX_AGE_SECONDS:
        return uncertain("activity_evidence_stale", "最近沒有新的執行訊號")
    if last["kind"] in {"codex.error", "codex.turn.completed", "codex.turn.failed", "codex.command.failed"}:
        result.update(pose="settled", artifact="result", title="這段活動已停止",
                      description="僅呈現已觀察到的活動結束；Workflow 狀態仍以來源為準。")
        return result
    open_commands: dict[str, dict[str, Any]] = {}
    for event in relevant:
        kind, payload = event["kind"], event["payload"]
        item_id = payload.get("item_id")
        if kind.startswith("codex.command.") and (
            not isinstance(item_id, str) or not item_id
            or not isinstance(payload.get("command_name", ""), str)
        ):
            return uncertain("command_evidence_invalid")
        if kind.startswith("codex.turn."):
            open_commands.clear()
        if kind in {"codex.command.started", "codex.command.updated"} and isinstance(item_id,str):
            open_commands[item_id] = event
        if kind in {"codex.command.completed", "codex.command.failed"}:
            open_commands.pop(item_id, None)
    active_command = max(open_commands.values(), key=lambda e:e["sequence"], default=None)
    if not active_command and last["kind"] == "codex.command.completed" and _test_command(last["payload"]):
        result.update(pose="settled", station="test", title="測試指令已結束",
                      description="Test Bench 保留已完成的指令證據；exit code 不等於完整測試報告或最終接受。")
        return result
    activity, station = "execution", "workshop"
    if active_command and (now-_time(active_command["observed_at_utc"])).total_seconds() <= ACTIVITY_MAX_AGE_SECONDS:
        # New adapters classify bounded wrappers before discarding arguments.
        # Legacy direct-executable events remain readable without parsing shell.
        activity = "test" if _test_command(active_command["payload"]) else "command"
        station = "test" if activity == "test" else "workshop"
    elif last["kind"].startswith("codex.file."):
        activity = "file"
    elif last["kind"].startswith("codex.tool."):
        activity = "tool"
    descriptions = {"execution":"已觀察到目前任務的 Codex 執行。", "command":"Builder 正在執行已辨識的指令。", "file":"目前 run 回報檔案活動，檔案不等於已驗收成果。", "tool":"目前 run 回報工具活動；不據此虛構 Researcher 角色。", "test":"已辨識測試執行檔；尚未宣稱測試通過。"}
    result.update(pose="working", station=station, actor="builder", artifact="working", activity=activity,
                  activity_sequence=last["sequence"], semantic_motion=True, tone="cyan",
                  activity_until_utc=(_time(last["observed_at_utc"])+timedelta(seconds=ACTIVITY_MAX_AGE_SECONDS)).isoformat(),
                  title="Builder 正在測試" if activity=="test" else "Builder 正在工作", description=descriptions[activity])
    result["human"].update(kind="SYSTEM", owner="Codex／Builder", what="目前由 Codex／Builder 執行。",
                           why="已觀察到此 request/run 的近期活動。")
    return result
