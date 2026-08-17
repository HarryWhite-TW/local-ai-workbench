from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.workflow_result_notifications import (  # noqa: E402
    AMBIGUOUS,
    ATTENTION_REQUIRED,
    COMPLETED_NON_SUCCESS,
    COMPLETED_SUCCESS,
    NOTIFICATION_STATE_FILE,
    SUBMITTED,
    NotificationSubmission,
    notification_identity,
    process_new_workflow_result_notifications,
)
from local_runner_bridge import workflow_result_notifications as notification_module  # noqa: E402


NOW = datetime(2026, 8, 15, 8, 0, 0, tzinfo=timezone.utc)
SESSION_ID = "a" * 32


def test_windows_helper_get_all_diagnostic_is_non_live_and_bounded():
    helper_source = (
        ROOT
        / "src"
        / "local_runner_bridge"
        / "windows_app_notification_helper"
        / "Program.cs"
    ).read_text(encoding="utf-8")
    diagnostic = helper_source.split(
        "private static async Task<int> GetAllNotifications()", 1
    )[1].split("private static int Submit(", 1)[0]

    assert 'args[0] == "--get-all"' in helper_source
    assert "await manager.GetAllAsync()" in diagnostic
    assert 'new ReceiptState("get_all")' in diagnostic
    assert 'state.GetAllStatus = "succeeded"' in diagnostic
    assert "state.NotificationCount = notifications.Count" in diagnostic
    assert "matches_prior_smoke" in diagnostic
    assert "manager.Show(" not in diagnostic
    assert "RemoveByIdAsync" not in diagnostic
    assert "RemoveByTagAsync" not in diagnostic
    assert "RemoveByTagAndGroupAsync" not in diagnostic
    assert "RemoveAllAsync" not in diagnostic
    assert "UnregisterAll" not in diagnostic


def test_windows_helper_get_all_receipt_exposes_required_diagnostic_fields():
    helper_source = (
        ROOT
        / "src"
        / "local_runner_bridge"
        / "windows_app_notification_helper"
        / "Program.cs"
    ).read_text(encoding="utf-8")

    assert "get_all_status = state.GetAllStatus" in helper_source
    assert "notification_count = state.NotificationCount" in helper_source
    assert "notifications = state.Notifications" in helper_source
    assert "bootstrap_status = state.BootstrapStatus" in helper_source
    assert "register_status = state.RegisterStatus" in helper_source
    assert "notification_setting = state.NotificationSetting" in helper_source
    assert "cleanup_status = state.CleanupStatus" in helper_source
    assert "error_type = state.ErrorType" in helper_source
    assert "error_hresult = state.ErrorHResult" in helper_source
    assert "payload = notification.Payload" in helper_source
    assert "payload_sha256" in helper_source
    assert "payload = payload" not in helper_source


def helper_receipt(**overrides) -> dict:
    payload = {
        "protocol": "lawb.windows_app_notification_helper.v1",
        "record_type": "receipt",
        "event_name": None,
        "operation": "submit",
        "status": "ambiguous",
        "detail": "windows_app_notification_helper_failed",
        "stage": "startup",
        "bootstrap_status": "not_attempted",
        "register_status": "not_attempted",
        "notification_setting": None,
        "show_attempted": False,
        "show_returned": False,
        "cleanup_status": "not_attempted",
        "api_submission_confirmed": False,
        "user_visible_delivery_confirmed": False,
        "error_type": None,
        "error_hresult": None,
        "cleanup_error_type": None,
        "cleanup_error_hresult": None,
    }
    payload.update(overrides)
    return payload


def show_attempted_event(receipt: dict) -> dict:
    event = dict(receipt)
    event.update(
        record_type="event",
        event_name="show_attempted",
        status="ambiguous",
        detail="windows_app_notification_show_started",
        stage="show",
        show_attempted=True,
        show_returned=False,
        cleanup_status="not_attempted",
        api_submission_confirmed=False,
    )
    return event


def test_windows_adapter_submits_via_app_notification_helper(monkeypatch, tmp_path):
    captured = {}
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")

    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        receipt = helper_receipt(status="submitted")
        receipt.update(
            detail="windows_app_notification_show_returned",
            stage="complete",
            bootstrap_status="succeeded",
            register_status="succeeded",
            notification_setting="Enabled",
            show_attempted=True,
            show_returned=True,
            cleanup_status="succeeded",
            api_submission_confirmed=True,
        )
        output = "\n".join(
            (json.dumps(show_attempted_event(receipt)), json.dumps(receipt))
        )
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(notification_module.subprocess, "run", fake_run)

    result = notification_module.submit_windows_desktop_notification(
        "Notification test",
        "Execution result is awaiting ChatGPT review.",
    )

    arguments = captured["arguments"]
    assert arguments[0] == str(helper)
    assert base64.b64decode(arguments[2]).decode("utf-8") == "Notification test"
    assert base64.b64decode(arguments[4]).decode("utf-8") == (
        "Execution result is awaiting ChatGPT review."
    )
    assert captured["kwargs"]["cwd"] == str(helper.parent)
    assert captured["kwargs"]["timeout"] == 20
    assert result.status == SUBMITTED
    assert result.detail == "windows_app_notification_show_returned"
    assert result.api_submission_confirmed is True
    assert result.show_attempted is True
    assert result.show_returned is True
    assert result.cleanup_status == "succeeded"


def test_windows_adapter_missing_helper_is_ambiguous(monkeypatch, tmp_path):
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: tmp_path / "missing.exe",
    )

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result == NotificationSubmission(
        AMBIGUOUS,
        "windows_app_notification_helper_not_found",
        False,
        False,
    )


def test_windows_adapter_timeout_is_ambiguous(monkeypatch, tmp_path):
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )

    def fake_run(arguments, **_kwargs):
        raise subprocess.TimeoutExpired(arguments, 20)

    monkeypatch.setattr(notification_module.subprocess, "run", fake_run)

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result == NotificationSubmission(
        AMBIGUOUS,
        "windows_app_notification_helper_timeout",
        False,
        False,
        operation="submit",
        stage="startup",
    )


def test_windows_adapter_preserves_register_exception(monkeypatch, tmp_path):
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )

    def fake_run(arguments, **_kwargs):
        receipt = helper_receipt(
            detail="windows_app_notification_register_failed",
            stage="register",
            bootstrap_status="succeeded",
            register_status="failed",
            error_type="System.Runtime.InteropServices.COMException",
            error_hresult="0x80004005",
        )
        return subprocess.CompletedProcess(arguments, 4, json.dumps(receipt), "")

    monkeypatch.setattr(notification_module.subprocess, "run", fake_run)

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result.status == AMBIGUOUS
    assert result.stage == "register"
    assert result.register_status == "failed"
    assert result.api_submission_confirmed is False
    assert result.error_type == "System.Runtime.InteropServices.COMException"
    assert result.error_hresult == "0x80004005"


def test_windows_adapter_disabled_setting_never_reports_show_attempted(
    monkeypatch, tmp_path
):
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )
    receipt = helper_receipt(
        detail="windows_app_notifications_disabledforuser",
        stage="setting",
        bootstrap_status="succeeded",
        register_status="succeeded",
        notification_setting="DisabledForUser",
        cleanup_status="succeeded",
    )
    monkeypatch.setattr(
        notification_module.subprocess,
        "run",
        lambda arguments, **_kwargs: subprocess.CompletedProcess(
            arguments, 5, json.dumps(receipt), ""
        ),
    )

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result.stage == "setting"
    assert result.notification_setting == "DisabledForUser"
    assert result.show_attempted is False
    assert result.show_returned is False
    assert result.api_submission_confirmed is False


def test_windows_adapter_preserves_show_exception(monkeypatch, tmp_path):
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )
    receipt = helper_receipt(
        detail="windows_app_notification_show_failed",
        stage="show",
        bootstrap_status="succeeded",
        register_status="succeeded",
        notification_setting="Enabled",
        show_attempted=True,
        cleanup_status="succeeded",
        error_type="System.Runtime.InteropServices.COMException",
        error_hresult="0x80070005",
    )
    output = "\n".join(
        (json.dumps(show_attempted_event(receipt)), json.dumps(receipt))
    )
    monkeypatch.setattr(
        notification_module.subprocess,
        "run",
        lambda arguments, **_kwargs: subprocess.CompletedProcess(
            arguments, 7, output, ""
        ),
    )

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result.stage == "show"
    assert result.show_attempted is True
    assert result.show_returned is False
    assert result.api_submission_confirmed is False
    assert result.error_hresult == "0x80070005"


def test_windows_adapter_preserves_show_success_when_cleanup_fails(
    monkeypatch, tmp_path
):
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )
    receipt = helper_receipt(
        detail="windows_app_notification_show_returned_cleanup_failed",
        stage="cleanup",
        bootstrap_status="succeeded",
        register_status="succeeded",
        notification_setting="Enabled",
        show_attempted=True,
        show_returned=True,
        cleanup_status="failed",
        api_submission_confirmed=True,
        cleanup_error_type="System.Runtime.InteropServices.COMException",
        cleanup_error_hresult="0x80004005",
    )
    output = "\n".join(
        (json.dumps(show_attempted_event(receipt)), json.dumps(receipt))
    )
    monkeypatch.setattr(
        notification_module.subprocess,
        "run",
        lambda arguments, **_kwargs: subprocess.CompletedProcess(
            arguments, 7, output, ""
        ),
    )

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result.status == AMBIGUOUS
    assert result.stage == "cleanup"
    assert result.show_returned is True
    assert result.api_submission_confirmed is True
    assert result.cleanup_status == "failed"
    assert result.cleanup_error_hresult == "0x80004005"


def test_windows_adapter_rejects_invalid_success_receipt(monkeypatch, tmp_path):
    helper = tmp_path / "LocalAIWorkbench.NotificationHelper.exe"
    helper.write_bytes(b"test helper placeholder")
    monkeypatch.setattr(notification_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        notification_module,
        "_windows_app_notification_helper_path",
        lambda: helper,
    )
    monkeypatch.setattr(
        notification_module.subprocess,
        "run",
        lambda arguments, **_kwargs: subprocess.CompletedProcess(
            arguments,
            0,
            '{"status":"submitted"}',
            "",
        ),
    )

    result = notification_module.submit_windows_desktop_notification("title", "body")

    assert result == NotificationSubmission(
        AMBIGUOUS,
        "windows_app_notification_helper_receipt_invalid",
        False,
        False,
        operation="submit",
        stage="startup",
    )


def processed_record(**overrides) -> dict:
    payload = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "processed_at_utc": "2026-08-15T08:00:00Z",
        "cycle": 1,
        "request_id": "notification-request-001",
        "target_repository": "HarryWhite-TW/local-ai-workbench",
        "target_issue": 274,
        "target_dispatch_request_id": "notification-dispatch-001",
        "requested_action": "run-reviewbundle",
        "expected_branch": "codex/eco-cp1-final-publication",
        "expected_head": "adab21c189708a427510fb307b1f195c9bc1d2bd",
        "target_result_comment_id": "9001",
        "target_result_author": "HarryWhite-TW",
        "terminal_result": "success",
        "terminal_settlement": "settled_success",
        "terminal_observed_at_utc": "2026-08-15T08:00:00Z",
        "dispatcher_invoked": True,
        "result_verified": True,
        "lifecycle_state": "CONSUMED",
    }
    payload.update(overrides)
    return payload


def append_record(state_dir: Path, record: dict) -> None:
    with (state_dir / "processed_requests.jsonl").open(
        "a", encoding="utf-8", newline="\n"
    ) as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def activate(state_dir: Path, submitter) -> dict:
    return process_new_workflow_result_notifications(
        state_dir=state_dir,
        operator_session_id=SESSION_ID,
        submitter=submitter,
        now_utc=NOW,
    )


def test_first_activation_watermarks_history_then_new_success_submits_once(tmp_path):
    historical = processed_record(request_id="historical-request")
    append_record(tmp_path, historical)
    calls = []

    first = activate(
        tmp_path,
        lambda title, message: calls.append((title, message))
        or NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )
    state_after_activation = json.loads(
        (tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8")
    )
    append_record(tmp_path, processed_record())
    second = activate(
        tmp_path,
        lambda title, message: calls.append((title, message))
        or NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )
    third = activate(
        tmp_path,
        lambda title, message: calls.append((title, message))
        or NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )

    assert first["status"] == "activated"
    assert first["activation_created"] is True
    assert state_after_activation["activation_offset"] > 0
    assert len(calls) == 1
    assert second["status"] == SUBMITTED
    assert second["submitted_count"] == 1
    assert third["status"] == "idle"
    assert "Execution result is awaiting ChatGPT review." in calls[0][1]
    final_state = json.loads(
        (tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8")
    )
    entry = next(iter(final_state["notifications"].values()))
    assert entry["classification"] == COMPLETED_SUCCESS
    assert entry["api_submission_confirmed"] is True
    assert entry["user_visible_delivery_confirmed"] is False


@pytest.mark.parametrize(
    ("overrides", "expected_classification", "expected_text"),
    [
        ({}, COMPLETED_SUCCESS, "completed successfully"),
        (
            {
                "terminal_result": "failure",
                "terminal_settlement": "settled_non_success",
            },
            COMPLETED_NON_SUCCESS,
            "non-success result",
        ),
        (
            {
                "terminal_result": "blocked",
                "terminal_settlement": "settled_non_success",
            },
            COMPLETED_NON_SUCCESS,
            "non-success result",
        ),
        (
            {
                "completion_source": "dispatcher_outcome",
                "dispatcher_execution_reach": "rejected_before_runner",
                "result_verified": False,
                "terminal_result": "blocked",
                "terminal_settlement": "settled_non_success",
                "target_result_comment_id": None,
                "target_result_author": None,
            },
            ATTENTION_REQUIRED,
            "no Runner or Codex success is claimed",
        ),
    ],
)
def test_classification_comes_only_from_consumed_settlement(
    tmp_path,
    overrides,
    expected_classification,
    expected_text,
):
    calls = []
    activate(tmp_path, lambda *_: pytest.fail("activation must not submit"))
    record = processed_record(**overrides)
    append_record(tmp_path, record)

    result = activate(
        tmp_path,
        lambda title, message: calls.append((title, message))
        or NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )

    assert result["submitted_count"] == 1
    assert expected_text in calls[0][1]
    state = json.loads((tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8"))
    notification_id = notification_identity(record)
    assert state["notifications"][notification_id]["classification"] == (
        expected_classification
    )


def test_ambiguous_submission_is_durable_and_never_blindly_retried(tmp_path):
    calls = []
    activate(tmp_path, lambda *_: pytest.fail("activation must not submit"))
    append_record(tmp_path, processed_record())

    first = activate(
        tmp_path,
        lambda title, message: calls.append((title, message))
        or NotificationSubmission(AMBIGUOUS, "fake_timeout", False),
    )
    second = activate(
        tmp_path,
        lambda *_: pytest.fail("ambiguous notification must not be retried"),
    )

    assert first["status"] == AMBIGUOUS
    assert first["ambiguous_count"] == 1
    assert second["status"] == "idle"
    assert len(calls) == 1
    state = json.loads((tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8"))
    entry = next(iter(state["notifications"].values()))
    assert entry["status"] == AMBIGUOUS
    assert entry["api_submission_confirmed"] is False
    assert entry["user_visible_delivery_confirmed"] is False


def test_submitting_notification_recovers_ambiguous_without_resend(
    tmp_path, monkeypatch
):
    activate(tmp_path, lambda *_: pytest.fail("activation must not submit"))
    append_record(tmp_path, processed_record())
    submit_calls = []
    original_persist = notification_module._persist_state
    interrupted = False

    def persist_then_interrupt(path, state, operator_session_id):
        nonlocal interrupted
        original_persist(path, state, operator_session_id)
        if not interrupted:
            interrupted = True
            raise RuntimeError("simulated interruption after submitting state persist")

    monkeypatch.setattr(notification_module, "_persist_state", persist_then_interrupt)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        activate(
            tmp_path,
            lambda title, message: submit_calls.append((title, message))
            or NotificationSubmission(SUBMITTED, "unexpected_submit", True),
        )

    assert submit_calls == []
    state = json.loads((tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8"))
    entry = next(iter(state["notifications"].values()))
    assert entry["status"] == "submitting"
    assert entry["api_submission_confirmed"] is False
    assert entry["user_visible_delivery_confirmed"] is False

    monkeypatch.setattr(notification_module, "_persist_state", original_persist)
    recovery_calls = []
    recovered = activate(
        tmp_path,
        lambda title, message: recovery_calls.append((title, message))
        or pytest.fail("recovered submitting notification must not resend"),
    )

    assert recovered["status"] == AMBIGUOUS
    assert recovered["ambiguous_count"] == 1
    assert recovery_calls == []
    recovered_state = json.loads(
        (tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8")
    )
    recovered_entry = next(iter(recovered_state["notifications"].values()))
    assert recovered_entry["status"] == AMBIGUOUS
    assert recovered_entry["detail"] == "prior_submission_outcome_unknown"
    assert recovered_entry["api_submission_confirmed"] is False
    assert recovered_entry["user_visible_delivery_confirmed"] is False

    rescan = activate(
        tmp_path,
        lambda *_: pytest.fail("submitting recovery must not resend on rescan"),
    )
    assert rescan["status"] == "idle"
    assert rescan["submitted_count"] == 0
    assert rescan["ambiguous_count"] == 0


def test_submitter_exception_becomes_ambiguous_without_affecting_later_scan(tmp_path):
    activate(tmp_path, lambda *_: pytest.fail("activation must not submit"))
    append_record(tmp_path, processed_record())

    def raising_submitter(*_):
        raise RuntimeError("desktop unavailable")

    first = activate(tmp_path, raising_submitter)
    second = activate(
        tmp_path,
        lambda *_: pytest.fail("submitting or ambiguous state must not resend"),
    )

    assert first["status"] == AMBIGUOUS
    assert second["status"] == "idle"
    entry = next(
        iter(
            json.loads(
                (tmp_path / NOTIFICATION_STATE_FILE).read_text(encoding="utf-8")
            )["notifications"].values()
        )
    )
    assert entry["detail"] == "notification_submitter_raised"


def test_changed_processed_history_fails_ambiguous_without_submission(tmp_path):
    activate(tmp_path, lambda *_: pytest.fail("activation must not submit"))
    append_record(tmp_path, processed_record())
    activate(
        tmp_path,
        lambda *_: NotificationSubmission(SUBMITTED, "fake_api_returned", True),
    )
    processed_path = tmp_path / "processed_requests.jsonl"
    original = processed_path.read_bytes()
    processed_path.write_bytes(b"X" + original[1:])

    result = activate(
        tmp_path,
        lambda *_: pytest.fail("changed source history must not submit"),
    )

    assert result["status"] == "source_history_ambiguous"
    assert result["ambiguous_count"] == 1
