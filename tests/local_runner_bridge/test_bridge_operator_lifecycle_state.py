import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_lifecycle_state import (
    DISPATCHED_NOT_LOCALLY_SETTLED,
    PREPARED,
    PROCESSED,
    REJECTED_BEFORE_RUNNER,
    LifecycleEvidenceError,
    append_jsonl_durable,
    capture_current_process_identity,
    create_lock_payload,
    inspect_expected_process,
    inspect_lock_file,
    load_in_flight,
    load_review_candidate,
    new_in_flight_payload,
    new_review_candidate_payload,
    quarantine_lock,
    updated_in_flight_payload,
    write_durable_json,
    write_exclusive_json,
    write_or_replace_review_candidate,
)

NOW = datetime(2026, 8, 5, 4, 0, 0, tzinfo=timezone.utc)
SESSION = "a" * 32
HEAD = "1fc67d44f6708689b3dd654f3e9ebb3fb824f589"


def process_identity() -> dict:
    return {
        "platform": "windows",
        "pid": 1234,
        "start_token": "windows-filetime:123456789",
        "started_at_utc": "2026-08-05T04:00:00Z",
    }


def lock_payload() -> dict:
    return create_lock_payload(
        operator_session_id=SESSION,
        process_identity=process_identity(),
        created_at=NOW,
        repository="HarryWhite-TW/local-ai-workbench",
        inbox_issue=147,
        mode="b3c-run-reviewbundle",
    )


def in_flight_payload() -> dict:
    return new_in_flight_payload(
        request_id="ov1-request-001",
        target_repository="HarryWhite-TW/local-ai-workbench",
        target_issue=151,
        dispatch_request_id="ov1-dispatch-001",
        action="maybe-status-check",
        branch="ov1-test",
        expected_head=HEAD,
        operator_session_id=SESSION,
        process_identity=process_identity(),
        prepared_at=NOW,
    )


def review_candidate_payload(*, target_repo_root: str, **overrides) -> dict:
    value = new_review_candidate_payload(
        target_repository="HarryWhite-TW/local-ai-workbench",
        target_issue=151,
        dispatch_request_id="review-candidate-151",
        action="run-reviewbundle",
        branch="ov1-test",
        expected_head=HEAD,
        terminal_result_comment_id="5313180923",
        review_bundle_comment_id="5313180922",
        candidate_manifest_fingerprint="a" * 64,
        target_repo_root=target_repo_root,
        recorded_at=NOW,
    )
    value.update(overrides)
    return value


def dispatcher_rejection_terminal(**overrides) -> dict:
    terminal = {
        "evidence_id": "local-dispatcher:ov1-request-001",
        "author": "local-dispatcher-v1",
        "result": "blocked",
        "settlement": "settled_non_success",
        "reconciliation_decision": "DISPATCHER_REJECTED_BEFORE_RUNNER",
        "reconciliation_reason": "STRUCTURED_PRE_RUNNER_REJECTION",
        "observed_at_utc": "2026-08-05T04:00:00Z",
    }
    terminal.update(overrides)
    return terminal


def observation(process_status: str, descendant_status: str) -> dict:
    return {
        "process_status": process_status,
        "descendant_status": descendant_status,
        "observed_process_identity": None,
        "descendant_pids": [] if descendant_status == "none" else [99],
        "reason": "none",
    }


def test_current_process_identity_is_exactly_live():
    identity = capture_current_process_identity()
    observed = inspect_expected_process(identity)

    assert identity["pid"] > 0
    assert identity["start_token"]
    assert observed["process_status"] == "live"
    assert observed["observed_process_identity"] == identity


def test_exclusive_lock_create_is_no_overwrite_and_exact(tmp_path):
    path = tmp_path / "operator.lock"
    payload = lock_payload()

    write_exclusive_json(path, payload)

    assert json.loads(path.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError):
        write_exclusive_json(path, payload)


def test_lock_assessment_requires_dead_or_reused_pid_and_no_descendants(
    tmp_path,
):
    path = tmp_path / "operator.lock"
    write_exclusive_json(path, lock_payload())

    live = inspect_lock_file(
        path,
        process_probe=lambda _: observation("live", "none"),
    )
    reused = inspect_lock_file(
        path,
        process_probe=lambda _: observation("pid_reused", "none"),
    )
    descendant = inspect_lock_file(
        path,
        process_probe=lambda _: observation("dead", "present"),
    )

    assert live["quarantine_safe"] is False
    assert live["exceptional_recovery_reason"] == "live_operator_or_hung"
    assert reused["quarantine_safe"] is True
    assert reused["process_status"] == "pid_reused"
    assert descendant["quarantine_safe"] is False
    assert descendant["exceptional_recovery_reason"] == "live_descendant_present"


def test_legacy_lock_is_never_automatic_recovery_candidate(tmp_path):
    path = tmp_path / "operator.lock"
    path.write_text('{"pid":1234}\n', encoding="utf-8")

    inspected = inspect_lock_file(path)

    assert inspected["metadata_status"] == "legacy"
    assert inspected["quarantine_safe"] is False
    assert inspected["exceptional_recovery_reason"] == (
        "legacy_lock_manual_recovery_required"
    )
    assert path.exists()


def test_quarantine_is_atomic_rename_with_exact_preserved_evidence(tmp_path):
    path = tmp_path / "operator.lock"
    payload = lock_payload()
    write_exclusive_json(path, payload)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    quarantined = quarantine_lock(
        path,
        expected_sha256=digest,
        operator_session_id=SESSION,
    )

    assert not path.exists()
    assert quarantined.is_file()
    assert quarantined.read_bytes() == raw
    assert SESSION in quarantined.name


def test_durable_in_flight_precedes_dispatch_and_has_exact_readback(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        "local_runner_bridge.bridge_operator_lifecycle_state.os.fsync",
        lambda descriptor: calls.append(descriptor),
    )
    path = tmp_path / "in_flight.json"
    payload = in_flight_payload()

    write_durable_json(path, payload, operator_session_id=SESSION)

    assert calls
    assert load_in_flight(path) == payload
    assert payload["stage"] == PREPARED
    assert payload["dispatcher_invoked"] is False


def test_in_flight_stage_shapes_are_strict_and_terminal_non_success_is_preserved():
    prepared = in_flight_payload()
    dispatched = updated_in_flight_payload(
        prepared,
        stage=DISPATCHED_NOT_LOCALLY_SETTLED,
        dispatcher_invoked=True,
        terminal_evidence=None,
        updated_at=NOW,
    )
    terminal = {
        "evidence_id": "20",
        "author": "HarryWhite-TW",
        "result": "failure",
        "settlement": "settled_non_success",
        "reconciliation_decision": "SETTLED_NON_SUCCESS",
        "reconciliation_reason": "EXACTLY_ONE_TRUSTED_NON_SUCCESS_MATCH",
        "observed_at_utc": "2026-08-05T04:00:00Z",
    }
    processed = updated_in_flight_payload(
        dispatched,
        stage=PROCESSED,
        dispatcher_invoked=True,
        terminal_evidence=terminal,
        updated_at=NOW,
    )
    rejected = updated_in_flight_payload(
        prepared,
        stage=REJECTED_BEFORE_RUNNER,
        dispatcher_invoked=True,
        terminal_evidence=dispatcher_rejection_terminal(),
        updated_at=NOW,
    )

    assert dispatched["stage"] == DISPATCHED_NOT_LOCALLY_SETTLED
    assert rejected["stage"] == REJECTED_BEFORE_RUNNER
    assert processed["terminal_evidence"]["result"] == "failure"
    with pytest.raises(LifecycleEvidenceError, match="in_flight_invalid"):
        updated_in_flight_payload(
            prepared,
            stage=PREPARED,
            dispatcher_invoked=True,
            terminal_evidence=None,
            updated_at=NOW,
        )


@pytest.mark.parametrize(
    "terminal_overrides",
    [
        {"result": "success", "settlement": "settled_success"},
        {"reconciliation_decision": "SETTLED_NON_SUCCESS"},
        {"reconciliation_reason": "EXACTLY_ONE_TRUSTED_NON_SUCCESS_MATCH"},
        {"author": "HarryWhite-TW"},
        {"evidence_id": "local-dispatcher:another-request"},
    ],
    ids=[
        "success-settlement",
        "incompatible-decision",
        "incompatible-reason",
        "incompatible-author",
        "incompatible-request-identity",
    ],
)
def test_rejected_before_runner_requires_exact_structured_terminal_contract(
    terminal_overrides,
):
    with pytest.raises(LifecycleEvidenceError, match="in_flight_invalid"):
        updated_in_flight_payload(
            in_flight_payload(),
            stage=REJECTED_BEFORE_RUNNER,
            dispatcher_invoked=True,
            terminal_evidence=dispatcher_rejection_terminal(**terminal_overrides),
            updated_at=NOW,
        )


def test_durable_jsonl_append_fsyncs_and_preserves_records(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "local_runner_bridge.bridge_operator_lifecycle_state.os.fsync",
        lambda descriptor: calls.append(descriptor),
    )
    path = tmp_path / "processed_requests.jsonl"

    append_jsonl_durable(path, {"request_id": "first"})
    append_jsonl_durable(path, {"request_id": "second"})

    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(calls) == 2
    assert [record["request_id"] for record in records] == ["first", "second"]


def test_review_candidate_record_is_strict_and_replacement_is_request_bound(tmp_path):
    path = tmp_path / "review_candidate.json"
    candidate_root = str((tmp_path / "candidate-151").resolve())
    first = review_candidate_payload(target_repo_root=candidate_root)

    assert write_or_replace_review_candidate(
        path, first, operator_session_id=SESSION
    ) == "written"
    assert load_review_candidate(path) == first
    assert first["schema_version"] == 2
    assert first["target_repo_root"] == candidate_root
    assert write_or_replace_review_candidate(
        path, first, operator_session_id=SESSION
    ) == "already_present"

    conflicting = review_candidate_payload(
        target_repo_root=candidate_root,
        candidate_manifest_fingerprint="b" * 64,
    )
    with pytest.raises(LifecycleEvidenceError, match="review_candidate_conflict"):
        write_or_replace_review_candidate(
            path, conflicting, operator_session_id=SESSION
        )

    malformed = dict(first)
    malformed["eligible"] = True
    path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(LifecycleEvidenceError, match="review_candidate_invalid"):
        load_review_candidate(path)
