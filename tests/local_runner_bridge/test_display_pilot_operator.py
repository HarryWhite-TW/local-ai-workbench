import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge import display_pilot_operator as operator
from local_runner_bridge.display_pilot_operator import (
    RUNNER_PROCESS_EVIDENCE_PROTOCOL,
    RUNNER_STREAM_PREVIEW_BYTES,
    RUNNER_STREAM_TRUNCATION_MARKER,
    RunnerInvocationResult,
    _normalize_runner_result,
    _process_evidence_value,
    _read_machine_evidence,
    _runner_stream_evidence,
    _stream_evidence_is_valid,
    _validate_runner_process_evidence,
    _write_runner_process_evidence,
    build_verification_argv,
    execute_verification_command,
    recover_incident,
    run_foreground,
)
from local_runner_bridge.display_pilot_transport import (
    PROTOCOL,
    SELECTOR_REPOSITORY,
    TARGET_REPOSITORY,
    body_sha256,
)


HEAD = "a" * 40
NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def runner_result(
    *,
    exit_code=0,
    timed_out=False,
    process_started=True,
    launch_exception=None,
    stdout=b"",
    stderr=b"",
):
    return RunnerInvocationResult(
        process_started=process_started,
        exit_code=exit_code,
        timed_out=timed_out,
        launch_exception=launch_exception,
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
        duration_ms=0.0,
        stdout=stdout,
        stderr=stderr,
    )


def process_evidence_path(state, request_id="req-9"):
    return (
        state
        / "requests"
        / request_id
        / "runner_process_evidence.json"
    )


def process_evidence_fixture(
    tmp_path,
    *,
    result=None,
    machine_evidence_bytes=None,
    prepared_at=None,
):
    request_root = tmp_path / "state" / "requests" / "req-9"
    request_root.mkdir(parents=True, exist_ok=True)
    machine_path = request_root / "runner_machine_evidence.json"
    value = _process_evidence_value(
        request_id="req-9",
        target_issue=9,
        target_repo_root=tmp_path / "repo",
        runner_path=tmp_path / "runner.ps1",
        powershell_path=tmp_path / "pwsh.exe",
        machine_evidence_path=machine_path,
        machine_evidence_bytes=machine_evidence_bytes,
        result=result or runner_result(),
        prepared_at=prepared_at or NOW.isoformat(),
    )
    validation = {
        "request_id": "req-9",
        "target_issue": 9,
        "target_repo_root": tmp_path / "repo",
        "runner_path": tmp_path / "runner.ps1",
        "powershell_path": tmp_path / "pwsh.exe",
        "machine_evidence_path": machine_path,
        "stdout": (result or runner_result()).stdout,
        "stderr": (result or runner_result()).stderr,
        "machine_evidence_bytes": machine_evidence_bytes,
    }
    return value, validation, request_root / "runner_process_evidence.json"


def task_surface(commands=None, *, allowed_files=None, max_allowed_files=None):
    commands = commands or ["python -m pytest -q tests/test_example.py"]
    allowed_files = (
        ["src/example.py"] if allowed_files is None else list(allowed_files)
    )
    maximum = len(allowed_files) if max_allowed_files is None else max_allowed_files
    rendered_commands = "\n".join(f"  - {command}" for command in commands)
    rendered_allowed_files = "\n".join(
        f"  - {path}" for path in allowed_files
    )
    return f"""LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1.1
packet_id: dp4-br-9
logical_issue: 9
phase: display_pilot_foreground
action_type: implementation
risk_level: medium
repository: {TARGET_REPOSITORY}
branch: feature/display-pilot
expected_head: {HEAD}
allowed_files:
{rendered_allowed_files}
forbidden_operations:
  - commit
approval:
  required: false
payload:
  kind: implementation
result_target:
  github_issue: 9
  marker: DISPLAY-PILOT-RESULT
stop_condition: stop_after_result
task_mode: PATCH_ONLY
objective: Implement one bounded change.
max_allowed_files: {maximum}
context_scope:
  - src/example.py
repair_attempt_limit: 1
verification_command_policy: explicit_only
verification_commands:
{rendered_commands}
scope_expansion_allowed: false
END_TASK_PACKET
"""


def request_fixture(
    commands=None,
    *,
    request_id="req-9",
    allowed_files=None,
    max_allowed_files=None,
):
    target_body = task_surface(
        commands,
        allowed_files=allowed_files,
        max_allowed_files=max_allowed_files,
    )
    selector = {
        "protocol": PROTOCOL,
        "repository": SELECTOR_REPOSITORY,
        "issue": 1,
        "target_repository": TARGET_REPOSITORY,
        "target_issue": 9,
        "action": "run-reviewbundle",
        "request_id": request_id,
        "target_body_sha256": body_sha256(target_body),
    }
    selector_body = (
        "```json hgw.display_pilot.transport.v1\n"
        + json.dumps(selector)
        + "\n```"
    )
    return (
        {
            "body": selector_body,
            "creator": "HarryWhite-TW",
            "body_sha256": body_sha256(selector_body),
        },
        {
            "repository": TARGET_REPOSITORY,
            "number": 9,
            "creator": "HarryWhite-TW",
            "state": "OPEN",
            "body": target_body,
        },
    )


def runtime_contract(commands=None, allowed_files=None, max_allowed_files=None):
    allowed_files = (
        ["src/example.py"] if allowed_files is None else list(allowed_files)
    )
    return {
        "protocol": "lawb.local_runner.task_packet.v1.1",
        "packet_id": "dp4-br-9",
        "logical_issue": 9,
        "repository": TARGET_REPOSITORY,
        "branch": "feature/display-pilot",
        "expected_head": HEAD,
        "task_mode": "PATCH_ONLY",
        "objective": "Implement one bounded change.",
        "allowed_files": allowed_files,
        "max_allowed_files": (
            len(allowed_files)
            if max_allowed_files is None
            else max_allowed_files
        ),
        "verification_command_policy": "explicit_only",
        "verification_commands": commands
        or ["python -m pytest -q tests/test_example.py"],
        "scope_expansion_allowed": False,
    }


def machine_evidence(
    repo_path,
    *,
    request_id="req-9",
    result="success",
    reasons=None,
    side_effect=None,
    allowed_files=None,
    changed_files=None,
    max_allowed_files=None,
    safety_overrides=None,
    review_bundle_comment_suppressed=True,
    github_comment_posted=False,
):
    allowed_files = (
        ["src/example.py"] if allowed_files is None else list(allowed_files)
    )
    safety = {
        "github_write_performed": False,
        "result_packet_written": True,
        "codex_side_action_executed": True,
        "runner_invoked": True,
        "dispatcher_invoked": False,
        "watcher_invoked": False,
        "broad_scan_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "pr_created": False,
        "merge_performed": False,
        "issue_closed": False,
        "label_changed": False,
    }
    if side_effect:
        safety[side_effect] = True
    safety.update(safety_overrides or {})
    changed_files = (
        ["src/example.py"] if changed_files is None else list(changed_files)
    )
    binding = {
        "status": "passed",
        "contract_present": True,
        "pre_execution": {"status": "passed", "reasons": []},
        "post_execution": {"status": "passed", "reasons": []},
        "allowed_files": allowed_files,
        "actual_changed_files": list(changed_files),
        "reasons": [],
        "runtime_contract": runtime_contract(
            allowed_files=allowed_files,
            max_allowed_files=max_allowed_files,
        ),
    }
    assurance = {
        "governance_scope": "passed",
        "observable_evidence": "verified",
        "evidence_profile": "local_git_candidate_observation.v1",
        "candidate_manifest_fingerprint": "fingerprint",
        "isolation_guarantee": "unverified",
        "isolation_provider": "codex_cli_workspace_write",
        "isolation_evidence_source": None,
    }
    blocked_reasons = list(reasons or [])
    if result == "blocked":
        binding["status"] = "contract_violation"
        binding["post_execution"] = {
            "status": "contract_violation",
            "reasons": blocked_reasons,
        }
        binding["reasons"] = blocked_reasons
        assurance["governance_scope"] = "violation"
        assurance["observable_evidence"] = "violation"
    return {
        "protocol": "lawb.display_pilot.runner_machine_evidence.v1",
        "schema_version": 1,
        "request_id": request_id,
        "repository": TARGET_REPOSITORY,
        "issue": 9,
        "repo_path": str(repo_path),
        "branch": "feature/display-pilot",
        "head_before": HEAD,
        "head_after": HEAD,
        "codex_exit_code": "0" if result == "success" else "7",
        "codex_status": "passed" if result == "success" else "failed",
        "codex_timed_out": False,
        "runtime_contract_binding": binding,
        "result_status": result,
        "blocked_reasons": blocked_reasons,
        "changed_files": list(changed_files),
        "final_git_status": " M src/example.py",
        "staged_area_clean": True,
        "execution_assurance": assurance,
        "safety_flags": safety,
        "review_bundle_comment_suppressed": review_bundle_comment_suppressed,
        "github_comment_posted": github_comment_posted,
    }


def read_machine_evidence(
    tmp_path,
    *,
    selected_allowed_files,
    binding_allowed_files,
    embedded_allowed_files,
):
    repo = tmp_path / "evidence-repo"
    repo.mkdir(exist_ok=True)
    payload = machine_evidence(
        repo,
        allowed_files=binding_allowed_files,
    )
    payload["runtime_contract_binding"]["runtime_contract"] = runtime_contract(
        allowed_files=embedded_allowed_files
    )
    path = tmp_path / "machine-evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return _read_machine_evidence(
        path,
        request_id="req-9",
        target_issue=9,
        target_repo_root=repo,
        runtime_contract=runtime_contract(
            allowed_files=selected_allowed_files
        ),
    )


def invoke(tmp_path, **overrides):
    request_options = overrides.pop("request_options", {})
    provided_runner = overrides.pop("runner", None)
    selector, target = request_fixture(
        overrides.pop("commands", None),
        **request_options,
    )
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_example.py").write_text("", encoding="utf-8")
    calls = {"runner": 0, "verification": 0, "render": []}

    def runner(request, evidence_path):
        calls["runner"] += 1
        evidence_path.write_text(
            json.dumps(
                machine_evidence(
                    repo,
                    request_id=request["selector"]["request_id"],
                )
            ),
            encoding="utf-8",
        )
        return 0

    def verifier(command, **kwargs):
        calls["verification"] += 1
        return {"command": command, "result": "success", "reason": "exit_code_0"}

    def renderer(evidence, result_id, created_at):
        calls["render"].append(evidence)
        return {
            "result": "success",
            "result_surface": {
                "request_id": evidence["request_id"],
                "canonical_result": evidence["result"],
            },
            "reviewer_report": f"review:{evidence['result']}",
            "plain_language_zh_TW": f"plain:{evidence['result']}",
        }

    arguments = {
        "state_root": tmp_path / "state",
        "target_repo_root": repo,
        "selector_reader": lambda: selector,
        "target_reader": lambda number: target,
        "runner": runner,
        "hgw_renderer": renderer,
        "python_path": sys.executable,
        "verifier": verifier,
        "git_observer": lambda _: {
            "head": HEAD,
            "staged_paths": [],
            "staged_clean": True,
            "status_short": " M src/example.py",
            "effective_changed_paths": ["src/example.py"],
            "fingerprint": "stable",
        },
        "now": lambda: NOW,
        "sleep": lambda _: None,
    }
    if provided_runner is not None:
        def counted_runner(request, evidence_path):
            calls["runner"] += 1
            return provided_runner(request, evidence_path)

        arguments["runner"] = counted_runner
    arguments.update(overrides)
    return run_foreground(**arguments), calls, arguments["state_root"]


def evidence_runner(tmp_path, *, evidence_kwargs=None, mutate=None, exit_code=0):
    def runner(request, evidence_path):
        payload = machine_evidence(
            tmp_path / "repo",
            request_id=request["selector"]["request_id"],
            **(evidence_kwargs or {}),
        )
        if mutate is not None:
            mutate(payload)
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        return exit_code

    return runner


def recovery_fixture(
    tmp_path,
    *,
    request_id="req-9",
    target_issue=9,
    raw=None,
):
    return recovery_state_at(
        tmp_path / "state",
        request_id=request_id,
        target_issue=target_issue,
        raw=raw,
    )


def recovery_state_at(
    state,
    *,
    request_id="req-9",
    target_issue=9,
    raw=None,
):
    request = state / "requests" / request_id
    request.mkdir(parents=True)
    raw = raw or (
        json.dumps(
            {
                "at": NOW.isoformat(),
                "request_id": request_id,
                "state": "delegating_runner",
                "target_issue": target_issue,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )
    (state / "in_flight.json").write_bytes(raw)
    return state, raw, hashlib.sha256(raw).hexdigest()


def recover_fixture(state, digest, **overrides):
    protected = tuple(state.parent / name for name in ("lawb", "hgw", "hag"))
    for root in protected:
        root.mkdir(exist_ok=True)
    arguments = {
        "state_root": state,
        "request_id": "req-9",
        "target_issue": 9,
        "in_flight_sha256": digest,
        "forbidden_state_roots": protected,
        "now": lambda: NOW,
    }
    arguments.update(overrides)
    return recover_incident(**arguments)


def write_valid_process_evidence(
    state,
    *,
    request_id="req-9",
    target_issue=9,
    machine_evidence_bytes=None,
):
    request_root = state / "requests" / request_id
    machine_path = request_root / "runner_machine_evidence.json"
    if machine_evidence_bytes is not None:
        machine_path.write_bytes(machine_evidence_bytes)
    value = _process_evidence_value(
        request_id=request_id,
        target_issue=target_issue,
        target_repo_root=state.parent / "repo",
        runner_path=state.parent / "runner.ps1",
        powershell_path=state.parent / "pwsh.exe",
        machine_evidence_path=machine_path,
        machine_evidence_bytes=machine_evidence_bytes,
        result=runner_result(exit_code=0, stdout=b"observed"),
        prepared_at=NOW.isoformat(),
    )
    path = request_root / "runner_process_evidence.json"
    path.write_bytes(
        (
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
    )
    return path


def test_no_eligible_request_polls_bounded_cycles_and_sleeps(tmp_path):
    sleeps = []
    result, _, state = invoke(
        tmp_path,
        selector_reader=lambda: None,
        max_cycles=3,
        poll_interval_seconds=2.5,
        sleep=sleeps.append,
    )

    assert result["result"] == "success"
    assert result["polling_outcome"] == "no_eligible_request"
    assert result["cycles"] == 3
    assert sleeps == [2.5, 2.5]
    assert json.loads((state / "heartbeat.json").read_text())["cycle"] == 3


def test_production_style_issue_without_selector_polls_sleeps_and_never_writes(
    tmp_path,
):
    sleeps = []
    body = "The fixed Issue is idle and has no current DP4-B selector."
    selector_issue = {
        "repository": SELECTOR_REPOSITORY,
        "number": 1,
        "creator": "HarryWhite-TW",
        "state": "OPEN",
        "body": body,
        "body_sha256": body_sha256(body),
    }
    result, calls, _ = invoke(
        tmp_path,
        selector_reader=lambda: selector_issue,
        max_cycles=3,
        poll_interval_seconds=1.25,
        sleep=sleeps.append,
    )

    assert result["result"] == "success"
    assert result["polling_outcome"] == "no_eligible_request"
    assert result["cycles"] == 3
    assert sleeps == [1.25, 1.25]
    assert calls["runner"] == 0
    assert calls["verification"] == 0
    assert result["github_write_performed"] is False


def test_one_valid_request_invokes_runner_once_and_writes_one_candidate(tmp_path):
    result, calls, state = invoke(tmp_path)

    assert result["result"] == "success"
    assert calls["runner"] == 1
    assert calls["verification"] == 1
    assert result["result_comment_candidate_count"] == 1
    request = state / "requests" / "req-9"
    assert (request / "runner_machine_evidence.json").exists()
    assert (request / "canonical_evidence.json").exists()
    assert (request / "result_surface.json").exists()
    assert (request / "result_comment_candidate.md").read_text() == "review:success"
    assert not (state / "in_flight.json").exists()
    canonical = json.loads((request / "canonical_evidence.json").read_text())
    assert result["safety_flags"] == canonical["safety_flags"]
    assert result["safety_flags"]["result_packet_written"] is True


def test_active_lock_and_unresolved_in_flight_block(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "operator.lock").write_text("active", encoding="utf-8")
    result, calls, _ = invoke(tmp_path)
    assert result["blocked_reasons"] == ["active_lock_present"]
    assert calls["runner"] == 0

    (state / "operator.lock").unlink()
    (state / "in_flight.json").write_text("{}", encoding="utf-8")
    result, calls, _ = invoke(tmp_path)
    assert result["blocked_reasons"] == ["unresolved_in_flight_state"]
    assert calls["runner"] == 0
    assert not (state / "operator.lock").exists()


@pytest.mark.parametrize(("flag", "reason"), [("pause.flag", "pause_flag_present"), ("stop.flag", "stop_flag_present")])
def test_pause_and_stop_are_checked_each_cycle(tmp_path, flag, reason):
    state = tmp_path / "state"
    observations = [None, request_fixture()[0]]

    def reader():
        return observations.pop(0)

    def sleep(_):
        state.mkdir(exist_ok=True)
        (state / flag).write_text("", encoding="utf-8")

    result, calls, _ = invoke(
        tmp_path,
        selector_reader=reader,
        sleep=sleep,
        max_cycles=2,
    )
    assert result["cycles"] == 2
    assert result["blocked_reasons"] == [reason]
    assert calls["runner"] == 0


def test_processed_request_is_idle_and_cannot_run_again(tmp_path):
    first, first_calls, state = invoke(tmp_path)
    second, second_calls, _ = invoke(tmp_path, max_cycles=2)

    assert first["result"] == "success"
    assert first_calls["runner"] == 1
    assert second["result"] == "success"
    assert second["polling_outcome"] == "no_eligible_request"
    assert second["cycles"] == 2
    assert second_calls["runner"] == 0
    records = (state / "processed_requests.jsonl").read_text().splitlines()
    assert len(records) == 1


def test_stale_selector_polls_then_executes_one_new_request_once(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "processed_requests.jsonl").write_text(
        json.dumps({"request_id": "req-9"}) + "\n",
        encoding="utf-8",
    )
    stale, _ = request_fixture(request_id="req-9")
    current, _ = request_fixture(request_id="req-10")
    observations = [stale, current]
    sleeps = []

    result, calls, _ = invoke(
        tmp_path,
        selector_reader=lambda: observations.pop(0),
        max_cycles=3,
        poll_interval_seconds=2,
        sleep=sleeps.append,
    )

    assert result["result"] == "success"
    assert result["request_id"] == "req-10"
    assert result["cycles"] == 2
    assert calls["runner"] == 1
    assert calls["verification"] == 1
    assert sleeps == [2]
    records = [
        json.loads(line)
        for line in (state / "processed_requests.jsonl").read_text().splitlines()
    ]
    assert [record["request_id"] for record in records] == ["req-9", "req-10"]


@pytest.mark.parametrize("selector_kind", ["multiple", "malformed"])
def test_ambiguous_or_malformed_selector_blocks_without_runner_or_write(
    tmp_path,
    selector_kind,
):
    valid, _ = request_fixture()
    body = (
        valid["body"] + "\n" + valid["body"]
        if selector_kind == "multiple"
        else "```json hgw.display_pilot.transport.v1\n{bad-json}\n```"
    )
    selector_issue = {
        "body": body,
        "creator": "HarryWhite-TW",
        "body_sha256": body_sha256(body),
    }

    result, calls, _ = invoke(tmp_path, selector_reader=lambda: selector_issue)

    assert result["result"] == "blocked"
    assert calls["runner"] == 0
    assert calls["verification"] == 0
    assert result["github_write_performed"] is False


def test_runner_exception_preserves_uncertain_in_flight_state(tmp_path):
    def failing_runner(request, evidence_path):
        raise RuntimeError("simulated runner start uncertainty")

    result, _, state = invoke(tmp_path, runner=failing_runner)
    assert result["blocked_reasons"] == ["runner_process_launch_failed"]
    assert result["runner_invoked"] is True
    assert result["safety_flags"]["runner_invoked"] is True
    evidence = json.loads(
        process_evidence_path(state).read_text(encoding="utf-8")
    )
    assert evidence["process_started"] is False
    assert evidence["launch_exception"]["type"] == "builtins.RuntimeError"
    assert (state / "in_flight.json").exists()
    assert not (state / "operator.lock").exists()


def test_known_runner_failure_becomes_blocked_and_is_processed(tmp_path):
    def blocked_runner(request, evidence_path):
        evidence_path.write_text(
            json.dumps(
                machine_evidence(
                    tmp_path / "repo",
                    result="blocked",
                    reasons=["codex_failed"],
                )
            ),
            encoding="utf-8",
        )
        return 2

    result, calls, state = invoke(tmp_path, runner=blocked_runner)
    assert result["result"] == "blocked"
    assert set(result["blocked_reasons"]) == {"codex_failed", "runner_blocked"}
    assert calls["verification"] == 0
    assert (state / "processed_requests.jsonl").exists()
    assert not (state / "in_flight.json").exists()


def test_blocked_machine_evidence_with_valid_reason_is_accepted(tmp_path):
    def blocked_runner(request, evidence_path):
        evidence_path.write_text(
            json.dumps(
                machine_evidence(
                    tmp_path / "repo",
                    result="blocked",
                    reasons=["explicit_runner_failure"],
                )
            ),
            encoding="utf-8",
        )
        return 2

    result, calls, state = invoke(tmp_path, runner=blocked_runner)

    assert "explicit_runner_failure" in result["blocked_reasons"]
    assert calls["render"]
    assert not (state / "in_flight.json").exists()


@pytest.mark.parametrize(
    "invalid_reasons",
    [[], None, ["   "], [7]],
)
def test_blocked_machine_evidence_without_valid_reason_is_rejected(
    tmp_path,
    invalid_reasons,
):
    def malformed_runner(request, evidence_path):
        payload = machine_evidence(
            tmp_path / "repo",
            result="blocked",
            reasons=["original_reason"],
        )
        payload["blocked_reasons"] = invalid_reasons
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        return 2

    result, calls, state = invoke(tmp_path, runner=malformed_runner)

    assert result["blocked_reasons"] == ["runner_machine_evidence_invalid"]
    assert calls["render"] == []
    assert (state / "in_flight.json").exists()


def test_success_machine_evidence_with_reason_is_rejected(tmp_path):
    def contradictory_runner(request, evidence_path):
        payload = machine_evidence(tmp_path / "repo")
        payload["blocked_reasons"] = ["contradictory_reason"]
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    result, calls, state = invoke(tmp_path, runner=contradictory_runner)

    assert result["blocked_reasons"] == ["runner_machine_evidence_invalid"]
    assert calls["render"] == []
    assert (state / "in_flight.json").exists()


def test_success_machine_evidence_with_empty_reasons_is_accepted(tmp_path):
    result, calls, state = invoke(tmp_path)

    assert result["result"] == "success"
    assert calls["render"]
    assert not (state / "in_flight.json").exists()


def test_allowed_files_canonical_exact_set_accepts_order_and_slash_equivalence(
    tmp_path,
):
    evidence = read_machine_evidence(
        tmp_path,
        selected_allowed_files=[
            "src/example.py",
            "tests/test_example.py",
        ],
        binding_allowed_files=[
            r"tests\test_example.py",
            "./src/example.py",
        ],
        embedded_allowed_files=[
            "./tests/test_example.py",
            r"src\example.py",
        ],
    )

    assert evidence["result_status"] == "success"


@pytest.mark.parametrize(
    (
        "selected_allowed_files",
        "binding_allowed_files",
        "embedded_allowed_files",
    ),
    [
        (
            ["src/example.py", "./src/example.py"],
            ["src/example.py"],
            ["src/example.py"],
        ),
        (
            ["src/example.py"],
            ["src/example.py", "./src/example.py"],
            ["src/example.py"],
        ),
        (
            ["src/example.py"],
            [],
            ["src/example.py"],
        ),
        (
            ["src/example.py"],
            ["src/example.py"],
            ["src/example.py", "tests/additional.py"],
        ),
        (
            ["src/example.py", ".git/config"],
            ["src/example.py", ".git/config"],
            ["src/example.py", ".git/config"],
        ),
    ],
)
def test_allowed_files_duplicate_missing_additional_or_unsafe_fails_closed(
    tmp_path,
    selected_allowed_files,
    binding_allowed_files,
    embedded_allowed_files,
):
    with pytest.raises(ValueError, match="runner_machine_evidence_invalid"):
        read_machine_evidence(
            tmp_path,
            selected_allowed_files=selected_allowed_files,
            binding_allowed_files=binding_allowed_files,
            embedded_allowed_files=embedded_allowed_files,
        )


def test_parent_verification_failure_becomes_blocked(tmp_path):
    def failed(command, **kwargs):
        return {"command": command, "result": "failed", "reason": "exit_code_1"}

    result, calls, _ = invoke(tmp_path, verifier=failed)
    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == ["parent_verification_failed"]
    assert calls["runner"] == 1


def test_forbidden_runner_side_effect_evidence_blocks(tmp_path):
    def unsafe_runner(request, evidence_path):
        evidence_path.write_text(
            json.dumps(
                machine_evidence(
                    tmp_path / "repo",
                    side_effect="push_performed",
                )
            ),
            encoding="utf-8",
        )
        return 0

    result, calls, state = invoke(tmp_path, runner=unsafe_runner)
    assert result["result"] == "blocked"
    assert "runner_reported_forbidden_side_effect" in result["blocked_reasons"]
    assert calls["verification"] == 0
    assert result["push_performed"] is True
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    assert canonical["result"] == "blocked"
    assert canonical["safety_flags"]["push_performed"] is True
    assert result["safety_flags"] == canonical["safety_flags"]


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest tests/test_x.py | more",
        "python -m pytest C:/outside/test_x.py",
        "python -m pytest ../outside.py",
        "python -m unittest tests/test_x.py",
        "python -m pytest --pyargs package",
        "python -m pytest -p arbitrary_plugin tests/test_x.py",
        "python -m pytest --plugins arbitrary_plugin tests/test_x.py",
        "python -m pytest --basetemp ../outside tests/test_x.py",
        "python -m pytest -c ../pytest.ini tests/test_x.py",
        "python -m pytest --rootdir ../outside tests/test_x.py",
        "python -m pytest src/package",
        "python -m pytest --collect-only tests/test_x.py",
    ],
)
def test_verification_policy_rejects_unsafe_or_non_pytest_commands(tmp_path, command):
    with pytest.raises(ValueError):
        build_verification_argv(
            command,
            python_path=sys.executable,
            repo_root=tmp_path,
        )


def test_verification_execution_uses_reviewed_python_shell_false_and_target_cwd(tmp_path):
    test_file = tmp_path / "tests" / "test_x.py"
    test_file.parent.mkdir()
    test_file.write_text("", encoding="utf-8")
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        return type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    result = execute_verification_command(
        "python -m pytest -q tests/test_x.py",
        python_path=sys.executable,
        repo_root=tmp_path,
        run=fake_run,
    )
    assert result["result"] == "success"
    assert observed["argv"][0] == str(Path(sys.executable).resolve())
    assert observed["shell"] is False
    assert observed["cwd"] == str(tmp_path.resolve())


def test_collect_only_is_rejected_before_runner_or_parent_verification(tmp_path):
    result, calls, _ = invoke(
        tmp_path,
        commands=["python -m pytest --collect-only tests/test_example.py"],
    )

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == ["verification_command_option_rejected"]
    assert calls["runner"] == 0
    assert calls["verification"] == 0


@pytest.mark.parametrize(
    "mutation",
    ["missing_safety_flag", "wrong_type", "contradictory_comment_flags"],
)
def test_incomplete_or_contradictory_machine_evidence_blocks_before_render(
    tmp_path,
    mutation,
):
    def malformed_runner(request, evidence_path):
        payload = machine_evidence(tmp_path / "repo")
        if mutation == "missing_safety_flag":
            payload["safety_flags"].pop("commit_performed")
        elif mutation == "wrong_type":
            payload["staged_area_clean"] = "true"
        else:
            payload["github_comment_posted"] = True
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    result, calls, state = invoke(tmp_path, runner=malformed_runner)

    assert result["result"] == "blocked"
    if mutation == "contradictory_comment_flags":
        assert result["blocked_reasons"] == [
            "github_write_fact_mismatch"
        ]
        assert calls["render"]
        assert calls["verification"] == 0
        assert not (state / "in_flight.json").exists()
    else:
        assert result["blocked_reasons"] == ["runner_machine_evidence_invalid"]
        assert calls["render"] == []
        assert (state / "in_flight.json").exists()


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("request_id", None),
        ("request_id", "req-other"),
        ("stale_allowlist", ["src/stale.py"]),
        ("changed_files_mismatch", ["src/stale.py"]),
        ("contradictory_status", "failed"),
        ("inconsistent_post_status", "contract_violation"),
        ("stale_runtime_contract", "stale-packet"),
    ],
)
def test_semantically_inconsistent_machine_evidence_blocks_before_render(
    tmp_path,
    mutation,
    value,
):
    def malformed_runner(request, evidence_path):
        payload = machine_evidence(tmp_path / "repo")
        if mutation == "request_id":
            payload["request_id"] = value
        elif mutation == "stale_allowlist":
            payload["runtime_contract_binding"]["allowed_files"] = value
        elif mutation == "changed_files_mismatch":
            payload["runtime_contract_binding"]["actual_changed_files"] = value
        elif mutation == "contradictory_status":
            payload["codex_status"] = value
        elif mutation == "inconsistent_post_status":
            payload["runtime_contract_binding"]["post_execution"]["status"] = value
        else:
            payload["runtime_contract_binding"]["runtime_contract"][
                "packet_id"
            ] = value
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    result, calls, state = invoke(tmp_path, runner=malformed_runner)

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == ["runner_machine_evidence_invalid"]
    assert calls["render"] == []
    assert calls["verification"] == 0
    assert (state / "in_flight.json").exists()


def test_runner_timeout_blocks_once_and_preserves_uncertain_state(tmp_path):
    calls = []

    def timed_out_runner(request, evidence_path):
        calls.append((request, evidence_path))
        raise subprocess.TimeoutExpired(["pwsh", "runner.ps1"], 1500)

    result, _, state = invoke(tmp_path, runner=timed_out_runner)

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == ["runner_timeout"]
    assert result["runner_invoked"] is True
    assert result["safety_flags"]["runner_invoked"] is True
    assert len(calls) == 1
    assert (state / "in_flight.json").exists()


@pytest.mark.parametrize(
    ("exit_code", "expected_reason"),
    [
        (0, "runner_machine_evidence_missing"),
        (17, "runner_nonzero_exit_without_machine_evidence"),
    ],
)
def test_runner_exit_without_machine_evidence_is_specific_and_durable(
    tmp_path,
    exit_code,
    expected_reason,
):
    result, calls, state = invoke(
        tmp_path,
        runner=lambda request, evidence_path: runner_result(
            exit_code=exit_code,
            stdout=b"runner-out",
            stderr=b"runner-err",
        ),
    )

    evidence = json.loads(
        process_evidence_path(state).read_text(encoding="utf-8")
    )
    assert result["blocked_reasons"] == [expected_reason]
    assert result["runner_exit_code"] == exit_code
    assert evidence["exit_code"] == exit_code
    assert evidence["machine_evidence_observed"] is False
    assert calls["verification"] == 0
    assert calls["render"] == []
    assert (state / "in_flight.json").exists()
    assert not (state / "processed_requests.jsonl").exists()
    assert not (
        state / "requests" / "req-9" / "canonical_evidence.json"
    ).exists()


def test_runner_timeout_preserves_partial_raw_stream_evidence(tmp_path):
    stdout = b"partial-out-\xff"
    stderr = b"partial-err-\xfe"

    def timed_out(request, evidence_path):
        raise subprocess.TimeoutExpired(
            ["pwsh", "runner.ps1"],
            1500,
            output=stdout,
            stderr=stderr,
        )

    result, _, state = invoke(tmp_path, runner=timed_out)

    evidence = json.loads(
        process_evidence_path(state).read_text(encoding="utf-8")
    )
    assert result["blocked_reasons"] == ["runner_timeout"]
    assert evidence["timed_out"] is True
    assert evidence["exit_code"] is None
    assert evidence["stdout"]["byte_count"] == len(stdout)
    assert evidence["stdout"]["sha256"] == hashlib.sha256(stdout).hexdigest()
    assert evidence["stdout"]["decode_replacement_used"] is True
    assert evidence["stderr"]["byte_count"] == len(stderr)
    assert evidence["stderr"]["sha256"] == hashlib.sha256(stderr).hexdigest()
    assert evidence["stderr"]["decode_replacement_used"] is True


def test_process_evidence_preview_is_deterministic_bounded_and_byte_safe(
    tmp_path,
):
    raw = b"h" * 2048 + b"\xff" + b"m" * 4096 + b"t" * 2048
    machine_path = tmp_path / "runner_machine_evidence.json"
    value = _process_evidence_value(
        request_id="req-9",
        target_issue=9,
        target_repo_root=tmp_path / "repo",
        runner_path=tmp_path / "runner.ps1",
        powershell_path=tmp_path / "pwsh.exe",
        machine_evidence_path=machine_path,
        machine_evidence_bytes=None,
        result=runner_result(stdout=raw, stderr=b"valid"),
        prepared_at=NOW.isoformat(),
    )

    stream = value["stdout"]
    assert stream["byte_count"] == len(raw)
    assert stream["sha256"] == hashlib.sha256(raw).hexdigest()
    assert stream["preview_truncated"] is True
    assert stream["preview"].count(
        "\n...[runner stream truncated]...\n"
    ) == 1
    assert stream["decode_replacement_used"] is True
    assert len(stream["preview"].encode("utf-8")) < 4300
    assert value["stderr"]["decode_replacement_used"] is False


@pytest.mark.parametrize("character", ["¢", "€", "😀"])
@pytest.mark.parametrize("boundary", ["head", "tail"])
def test_valid_utf8_crossing_preview_boundary_is_not_corrupted(
    character,
    boundary,
):
    encoded = character.encode("utf-8")
    raw = (
        b"h" * 2047 + encoded + b"m" * 5000
        if boundary == "head"
        else b"m" * 5000 + encoded + b"t" * 2047
    )

    stream = _runner_stream_evidence(raw)

    assert stream["preview_truncated"] is True
    assert stream["decode_replacement_used"] is False
    assert "\ufffd" not in stream["preview"]
    head, tail = stream["preview"].split(
        RUNNER_STREAM_TRUNCATION_MARKER
    )
    assert (
        len(head.encode("utf-8")) + len(tail.encode("utf-8"))
        <= RUNNER_STREAM_PREVIEW_BYTES
    )


@pytest.mark.parametrize("position", ["head", "tail", "middle"])
def test_invalid_utf8_is_reported_even_when_omitted_from_preview(position):
    if position == "head":
        raw = b"h" * 100 + b"\xff" + b"m" * 6000
    elif position == "tail":
        raw = b"m" * 6000 + b"\xff" + b"t" * 100
    else:
        raw = b"h" * 2048 + b"m" * 1000 + b"\xff" + b"n" * 1000 + b"t" * 2048

    stream = _runner_stream_evidence(raw)

    assert stream["preview_truncated"] is True
    assert stream["decode_replacement_used"] is True
    if position == "middle":
        assert "\ufffd" not in stream["preview"]
    else:
        assert "\ufffd" in stream["preview"]


def test_genuine_replacement_character_is_not_decoder_replacement():
    raw = b"h" * 1900 + "\ufffd".encode("utf-8") + b"m" * 5000

    first = _runner_stream_evidence(raw)
    second = _runner_stream_evidence(raw)

    assert first == second
    assert first["decode_replacement_used"] is False
    assert "\ufffd" in first["preview"]


def test_generated_stream_evidence_corpus_is_semantically_valid():
    multibyte = "¢€😀".encode("utf-8")
    marker = RUNNER_STREAM_TRUNCATION_MARKER.encode("utf-8")
    corpus = [
        b"",
        b"ASCII",
        marker,
        b"prefix" + marker + b"middle" + marker + b"suffix",
        multibyte,
        "\ufffd".encode("utf-8"),
        b"\xff",
        b"\xe2\x82",
        b"short-\xff-tail",
        b"a" * 2047 + "¢".encode("utf-8") + b"m" * 5000,
        b"a" * 2047 + "€".encode("utf-8") + b"m" * 5000,
        b"a" * 2047 + "😀".encode("utf-8") + b"m" * 5000,
        b"m" * 5000 + "¢".encode("utf-8") + b"t" * 2047,
        b"m" * 5000 + "€".encode("utf-8") + b"t" * 2047,
        b"m" * 5000 + "😀".encode("utf-8") + b"t" * 2047,
        b"h" * 2048 + b"\xff" + b"m" * 1000 + b"t" * 2048,
        b"h" * 2048 + b"m" * 1000 + b"\xff" + b"t" * 2048,
        b"h" * 2048 + b"m" * 1000 + b"\xe2\x82" + b"t" * 2048,
        (multibyte * 1400),
        marker + b"h" * 3000 + b"t" * 2048,
        b"h" * 2048 + b"m" * 3000 + marker,
        marker + b"h" * 3000 + b"t" * 2048 + marker,
        b"h" * (2048 - len(marker)) + marker + b"m" * 5000,
        marker + marker + b"h" * 3000 + marker + b"t" * 2048 + marker,
        marker + b"\xff" + b"h" * 3000 + b"t" * 2048 + marker,
    ]

    for raw in corpus:
        assert _stream_evidence_is_valid(_runner_stream_evidence(raw)), raw[:20]


@pytest.mark.parametrize(
    "stream",
    [
        {
            "byte_count": 1,
            "sha256": "0" * 64,
            "preview": "\ufffd" * 1000,
            "preview_truncated": False,
            "decode_replacement_used": True,
        },
        {
            "byte_count": 5000,
            "sha256": "0" * 64,
            "preview": RUNNER_STREAM_TRUNCATION_MARKER,
            "preview_truncated": True,
            "decode_replacement_used": False,
        },
    ],
)
def test_impossible_recovery_stream_evidence_is_rejected(stream):
    assert _stream_evidence_is_valid(stream) is False


def test_process_evidence_schema_version_rejects_json_boolean(tmp_path):
    value, validation, _ = process_evidence_fixture(tmp_path)
    value["schema_version"] = True

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_invalid",
    ):
        _validate_runner_process_evidence(value, **validation)


def test_natural_truncation_marker_remains_valid_stream_evidence(tmp_path):
    raw = (
        RUNNER_STREAM_TRUNCATION_MARKER.encode("utf-8")
        + b"x" * (RUNNER_STREAM_PREVIEW_BYTES + 1)
    )
    value, validation, _ = process_evidence_fixture(
        tmp_path,
        result=runner_result(stdout=raw),
    )

    assert _validate_runner_process_evidence(value, **validation) is value


@pytest.mark.parametrize(
    (
        "process_started",
        "exit_code",
        "timed_out",
        "launch_exception",
        "stdout",
    ),
    [
        (True, None, False, None, b""),
        (True, None, False, {"type": "builtins.OSError", "message": "x"}, b""),
        (True, None, True, {"type": "builtins.OSError", "message": "x"}, b""),
        (True, 1, False, {"type": "builtins.OSError", "message": "x"}, b""),
        (True, 1, True, None, b""),
        (True, 1, True, {"type": "builtins.OSError", "message": "x"}, b""),
        (False, None, False, None, b""),
        (False, None, True, None, b""),
        (False, None, True, {"type": "builtins.OSError", "message": "x"}, b""),
        (False, 1, False, None, b""),
        (False, 1, False, {"type": "builtins.OSError", "message": "x"}, b""),
        (False, 1, True, None, b""),
        (False, 1, True, {"type": "builtins.OSError", "message": "x"}, b""),
        (False, None, False, {"type": "builtins.OSError", "message": "x"}, b"x"),
    ],
)
def test_runner_result_rejects_every_invalid_process_state_combination(
    process_started,
    exit_code,
    timed_out,
    launch_exception,
    stdout,
):
    value = runner_result(
        process_started=process_started,
        exit_code=exit_code,
        timed_out=timed_out,
        launch_exception=launch_exception,
        stdout=stdout,
    )

    with pytest.raises(
        ValueError,
        match="runner_invocation_result_invalid",
    ):
        _normalize_runner_result(
            value,
            started_at=NOW,
            finished_at=NOW,
        )


@pytest.mark.parametrize(
    "value",
    [
        runner_result(),
        runner_result(
            exit_code=None,
            timed_out=True,
        ),
        runner_result(
            process_started=False,
            exit_code=None,
            launch_exception={
                "type": "builtins.FileNotFoundError",
                "message": "missing",
            },
        ),
    ],
)
def test_runner_result_accepts_exact_three_state_table(value):
    assert (
        _normalize_runner_result(
            value,
            started_at=NOW,
            finished_at=NOW,
        )
        is value
    )


@pytest.mark.parametrize(
    (
        "process_started",
        "exit_code",
        "timed_out",
        "launch_exception",
    ),
    [
        (True, None, False, None),
        (True, None, False, {"type": "builtins.OSError", "message": "x"}),
        (True, None, True, {"type": "builtins.OSError", "message": "x"}),
        (True, 1, False, {"type": "builtins.OSError", "message": "x"}),
        (True, 1, True, None),
        (True, 1, True, {"type": "builtins.OSError", "message": "x"}),
        (False, None, False, None),
        (False, None, True, None),
        (False, None, True, {"type": "builtins.OSError", "message": "x"}),
        (False, 1, False, None),
        (False, 1, False, {"type": "builtins.OSError", "message": "x"}),
        (False, 1, True, None),
        (False, 1, True, {"type": "builtins.OSError", "message": "x"}),
    ],
)
def test_process_evidence_validator_rejects_every_invalid_process_state(
    tmp_path,
    process_started,
    exit_code,
    timed_out,
    launch_exception,
):
    value, validation, _ = process_evidence_fixture(tmp_path)
    value.update(
        {
            "process_started": process_started,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "launch_exception": launch_exception,
        }
    )

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_invalid",
    ):
        _validate_runner_process_evidence(value, **validation)


@pytest.mark.parametrize(
    "mutation",
    [
        "zero_nonempty_preview",
        "zero_wrong_sha",
        "zero_truncated",
        "truncated_flag_mismatch",
        "machine_false_with_metadata",
        "machine_true_missing_size",
        "machine_true_missing_sha",
        "machine_uppercase_sha",
        "timestamps_reversed",
        "prepared_before_finished",
        "duration_mismatch",
    ],
)
def test_process_evidence_validator_rejects_semantic_contradictions(
    tmp_path,
    mutation,
):
    raw = (
        b"x" * (RUNNER_STREAM_PREVIEW_BYTES + 1)
        if mutation == "truncated_flag_mismatch"
        else b""
    )
    result = runner_result(stdout=raw)
    machine_bytes = (
        b"machine"
        if mutation.startswith("machine_true")
        or mutation == "machine_uppercase_sha"
        else None
    )
    value, validation, _ = process_evidence_fixture(
        tmp_path,
        result=result,
        machine_evidence_bytes=machine_bytes,
    )
    if mutation == "zero_nonempty_preview":
        value["stdout"]["preview"] = "x"
    elif mutation == "zero_wrong_sha":
        value["stdout"]["sha256"] = "0" * 64
    elif mutation == "zero_truncated":
        value["stdout"]["preview_truncated"] = True
    elif mutation == "truncated_flag_mismatch":
        value["stdout"]["preview_truncated"] = False
    elif mutation == "machine_false_with_metadata":
        value["machine_evidence_size"] = 1
        value["machine_evidence_sha256"] = "0" * 64
    elif mutation == "machine_true_missing_size":
        value["machine_evidence_size"] = None
    elif mutation == "machine_true_missing_sha":
        value["machine_evidence_sha256"] = None
    elif mutation == "machine_uppercase_sha":
        value["machine_evidence_sha256"] = (
            value["machine_evidence_sha256"].upper()
        )
    elif mutation == "timestamps_reversed":
        value["started_at"] = "2026-07-24T00:00:01+00:00"
    elif mutation == "prepared_before_finished":
        value["prepared_at"] = "2026-07-23T23:59:59+00:00"
    else:
        value["duration_ms"] = 10_000

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_invalid",
    ):
        _validate_runner_process_evidence(value, **validation)


def test_live_validator_rejects_machine_file_size_or_hash_mismatch(tmp_path):
    value, validation, _ = process_evidence_fixture(
        tmp_path,
        machine_evidence_bytes=b"expected",
    )
    validation["machine_evidence_bytes"] = b"actual"

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_invalid",
    ):
        _validate_runner_process_evidence(value, **validation)


def test_preexisting_process_evidence_conflict_skips_runner_and_keeps_in_flight(
    tmp_path,
):
    state = tmp_path / "state"
    path = process_evidence_path(state)
    path.parent.mkdir(parents=True)
    original = b'{"preexisting":true}\n'
    path.write_bytes(original)

    result, calls, _ = invoke(tmp_path)

    assert result["blocked_reasons"] == [
        "runner_process_evidence_write_failed"
    ]
    assert calls["runner"] == 0
    assert path.read_bytes() == original
    assert (state / "in_flight.json").exists()


def test_process_evidence_readback_validation_failure_is_controlled(
    tmp_path,
    monkeypatch,
):
    def reject(*args, **kwargs):
        raise ValueError("runner_process_evidence_invalid")

    monkeypatch.setattr(
        operator,
        "_validate_runner_process_evidence",
        reject,
    )
    result, calls, state = invoke(tmp_path)

    assert result["blocked_reasons"] == [
        "runner_process_evidence_write_failed"
    ]
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    assert calls["render"] == []
    assert (state / "in_flight.json").exists()
    assert not (state / "processed_requests.jsonl").exists()
    assert not (
        state / "requests" / "req-9" / "canonical_evidence.json"
    ).exists()


def test_process_evidence_atomic_write_failure_cleans_owned_temporary(
    tmp_path,
    monkeypatch,
):
    def fail_process_publish(source, destination, **kwargs):
        if Path(destination).name == "runner_process_evidence.json":
            raise OSError("simulated process evidence link failure")
        pytest.fail("unexpected no-replace publication target")

    monkeypatch.setattr(operator.os, "link", fail_process_publish)
    result, calls, state = invoke(tmp_path)
    request_root = state / "requests" / "req-9"

    assert result["blocked_reasons"] == [
        "runner_process_evidence_write_failed"
    ]
    assert calls["runner"] == 1
    assert not process_evidence_path(state).exists()
    assert not any(
        path.name.startswith(".runner_process_evidence.json.")
        for path in request_root.iterdir()
    )
    assert (state / "in_flight.json").exists()
    assert not (state / "processed_requests.jsonl").exists()


@pytest.mark.parametrize("entry_kind", ["file", "directory"])
def test_process_evidence_publication_never_overwrites_existing_entry(
    tmp_path,
    entry_kind,
):
    value, validation, path = process_evidence_fixture(tmp_path)
    if entry_kind == "file":
        original = b"preexisting-canonical"
        path.write_bytes(original)
    else:
        path.mkdir()

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_conflict",
    ):
        _write_runner_process_evidence(
            path,
            value,
            validation=validation,
        )

    if entry_kind == "file":
        assert path.read_bytes() == original
    else:
        assert path.is_dir()


@pytest.mark.parametrize("dangling", [False, True])
def test_process_evidence_publication_rejects_symlink_entry(
    tmp_path,
    dangling,
):
    value, validation, path = process_evidence_fixture(tmp_path)
    target = path.parent / "symlink-target"
    if not dangling:
        target.write_bytes(b"target-unchanged")
    try:
        path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_conflict",
    ):
        _write_runner_process_evidence(
            path,
            value,
            validation=validation,
        )

    assert path.is_symlink()
    if not dangling:
        assert target.read_bytes() == b"target-unchanged"


def test_process_evidence_publish_race_preserves_conflicting_destination(
    tmp_path,
    monkeypatch,
):
    value, validation, path = process_evidence_fixture(tmp_path)
    original_link = operator.os.link
    raced = b"racing-destination"

    def create_destination_then_publish(source, destination, **kwargs):
        Path(destination).write_bytes(raced)
        return original_link(source, destination, **kwargs)

    monkeypatch.setattr(
        operator.os,
        "link",
        create_destination_then_publish,
    )

    with pytest.raises(FileExistsError):
        _write_runner_process_evidence(
            path,
            value,
            validation=validation,
        )

    assert path.read_bytes() == raced
    assert not (
        path.parent / f".{path.name}.{os.getpid()}.tmp"
    ).exists()


def test_process_evidence_publish_conflict_cleans_only_owned_temporary(
    tmp_path,
    monkeypatch,
):
    value, validation, path = process_evidence_fixture(tmp_path)
    unrelated = path.parent / ".runner_process_evidence.json.unrelated.tmp"
    unrelated.write_bytes(b"unrelated")

    def conflict(*args, **kwargs):
        raise FileExistsError("simulated no-replace conflict")

    monkeypatch.setattr(operator.os, "link", conflict)
    with pytest.raises(FileExistsError):
        _write_runner_process_evidence(
            path,
            value,
            validation=validation,
        )

    assert unrelated.read_bytes() == b"unrelated"
    assert not (
        path.parent / f".{path.name}.{os.getpid()}.tmp"
    ).exists()
    assert not path.exists()


def test_process_evidence_no_replace_publication_reads_back_exact_value(
    tmp_path,
):
    value, validation, path = process_evidence_fixture(
        tmp_path,
        result=runner_result(stdout=b"raw", stderr=b"bytes"),
    )
    expected = (
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")

    _write_runner_process_evidence(
        path,
        value,
        validation=validation,
    )

    assert path.read_bytes() == expected
    assert json.loads(path.read_text(encoding="utf-8")) == value
    assert not (
        path.parent / f".{path.name}.{os.getpid()}.tmp"
    ).exists()


def test_process_evidence_readback_byte_mismatch_fails_closed(
    tmp_path,
    monkeypatch,
):
    value, validation, path = process_evidence_fixture(tmp_path)
    original_read_bytes = Path.read_bytes

    def mismatched_readback(observed_path):
        raw = original_read_bytes(observed_path)
        return raw + b" " if observed_path == path else raw

    monkeypatch.setattr(Path, "read_bytes", mismatched_readback)

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_invalid",
    ):
        _write_runner_process_evidence(
            path,
            value,
            validation=validation,
        )

    assert path.exists()


def test_process_evidence_readback_value_mismatch_fails_closed(
    tmp_path,
    monkeypatch,
):
    value, validation, path = process_evidence_fixture(tmp_path)

    def mismatched_value(raw, *, reason):
        observed = json.loads(raw.decode("utf-8"))
        observed["request_id"] = "req-other"
        return observed

    monkeypatch.setattr(operator, "_load_json_bytes", mismatched_value)

    with pytest.raises(
        ValueError,
        match="runner_process_evidence_invalid",
    ):
        _write_runner_process_evidence(
            path,
            value,
            validation=validation,
        )

    assert path.exists()


def test_success_keeps_process_and_machine_evidence_with_separate_authority(
    tmp_path,
):
    result, calls, state = invoke(tmp_path)
    request_root = state / "requests" / "req-9"
    process = json.loads(
        (request_root / "runner_process_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    machine = json.loads(
        (request_root / "runner_machine_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    canonical = json.loads(
        (request_root / "canonical_evidence.json").read_text()
    )

    assert result["result"] == "success"
    assert result["runner_process_evidence_written"] is True
    assert process["protocol"] == RUNNER_PROCESS_EVIDENCE_PROTOCOL
    assert process["machine_evidence_observed"] is True
    assert process["machine_evidence_size"] == len(
        (request_root / "runner_machine_evidence.json").read_bytes()
    )
    assert process["machine_evidence_sha256"] == hashlib.sha256(
        (request_root / "runner_machine_evidence.json").read_bytes()
    ).hexdigest()
    assert not any("codex" in key for key in process)
    assert canonical["runner_machine_evidence"]["codex_status"] == (
        machine["codex_status"]
    )
    assert calls["verification"] == 1


def test_live_machine_evidence_mutation_after_snapshot_fails_closed(
    tmp_path,
    monkeypatch,
):
    original_write = operator._write_runner_process_evidence
    observed = {"write_denied": False}

    def capture_runner(request, evidence_path):
        payload = machine_evidence(tmp_path / "repo")
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        evidence_path.write_bytes(raw)
        observed["initial"] = raw
        return 0

    def mutate_after_process_evidence(path, value, *, validation):
        original_write(path, value, validation=validation)
        replacement = machine_evidence(tmp_path / "repo")
        replacement["request_id"] = "req-replaced"
        try:
            path.with_name("runner_machine_evidence.json").write_text(
                json.dumps(replacement, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            observed["write_denied"] = True
            raise

    monkeypatch.setattr(
        operator,
        "_write_runner_process_evidence",
        mutate_after_process_evidence,
    )
    result, calls, state = invoke(tmp_path, runner=capture_runner)
    process = json.loads(
        process_evidence_path(state).read_text(encoding="utf-8")
    )

    assert result["blocked_reasons"] == [
        (
            "runner_process_evidence_write_failed"
            if observed["write_denied"]
            else "runner_machine_evidence_invalid"
        )
    ]
    assert calls["verification"] == 0
    assert calls["render"] == []
    assert process["machine_evidence_size"] == len(observed["initial"])
    assert process["machine_evidence_sha256"] == hashlib.sha256(
        observed["initial"]
    ).hexdigest()
    assert (state / "in_flight.json").exists()


def test_live_machine_evidence_guard_closes_after_durable_finalization(
    tmp_path,
    monkeypatch,
):
    original_open = operator._open_canonical_evidence_guard
    observations = []
    state = tmp_path / "state"

    def observed_open(path, *, reason):
        guard = original_open(path, reason=reason)
        original_close = guard.close

        def observed_close():
            observations.append(
                {
                    "in_flight_exists": (state / "in_flight.json").exists(),
                    "processed_exists": (
                        state / "processed_requests.jsonl"
                    ).exists(),
                }
            )
            original_close()

        guard.close = observed_close
        return guard

    monkeypatch.setattr(
        operator,
        "_open_canonical_evidence_guard",
        observed_open,
    )
    result, _, _ = invoke(tmp_path)

    assert result["result"] == "success"
    assert observations == [
        {
            "in_flight_exists": False,
            "processed_exists": True,
        }
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows share-mode contract")
@pytest.mark.parametrize(
    "boundary",
    [
        "renderer",
        "artifact_publication",
        "processed_append",
        "in_flight_release",
    ],
)
def test_live_machine_evidence_guard_blocks_finalization_races(
    tmp_path,
    monkeypatch,
    boundary,
):
    machine_path = {}
    attempts = []

    def capture_runner(request, evidence_path):
        evidence_path.write_text(
            json.dumps(machine_evidence(tmp_path / "repo")),
            encoding="utf-8",
        )
        machine_path["value"] = evidence_path
        return 0

    def mutate_machine_evidence():
        attempts.append(boundary)
        replacement = machine_evidence(tmp_path / "repo")
        replacement["request_id"] = "req-replaced"
        machine_path["value"].write_text(
            json.dumps(replacement),
            encoding="utf-8",
        )

    overrides = {"runner": capture_runner}
    if boundary == "renderer":
        def mutating_renderer(evidence, result_id, created_at):
            mutate_machine_evidence()
            raise AssertionError("Windows guard allowed evidence mutation")

        overrides["hgw_renderer"] = mutating_renderer
    elif boundary == "artifact_publication":
        original_atomic_json = operator._atomic_json
        mutated = False

        def mutate_during_artifact(path, value):
            nonlocal mutated
            original_atomic_json(path, value)
            if path.name == "canonical_evidence.json" and not mutated:
                mutated = True
                mutate_machine_evidence()

        monkeypatch.setattr(
            operator,
            "_atomic_json",
            mutate_during_artifact,
        )
    elif boundary == "processed_append":
        original_append = operator._append_processed

        def mutate_before_append(path, record, *, evidence_guard=None):
            mutate_machine_evidence()
            return original_append(
                path,
                record,
                evidence_guard=evidence_guard,
            )

        monkeypatch.setattr(
            operator,
            "_append_processed",
            mutate_before_append,
        )
    else:
        original_release = operator._release_in_flight

        def mutate_before_release(path, *, evidence_guard):
            mutate_machine_evidence()
            return original_release(
                path,
                evidence_guard=evidence_guard,
            )

        monkeypatch.setattr(
            operator,
            "_release_in_flight",
            mutate_before_release,
        )

    result, _, state = invoke(tmp_path, **overrides)

    assert attempts == [boundary]
    assert result["blocked_reasons"] == ["runner_execution_uncertain"]
    assert not (state / "processed_requests.jsonl").exists()
    assert (state / "in_flight.json").exists()


def test_parent_verification_repository_mutation_is_canonical_and_blocks(tmp_path):
    observations = [
        {
            "head": HEAD,
            "staged_paths": [],
            "staged_clean": True,
            "status_short": " M src/example.py",
            "effective_changed_paths": ["src/example.py"],
            "fingerprint": "before",
        },
        {
            "head": HEAD,
            "staged_paths": [],
            "staged_clean": True,
            "status_short": " M src/example.py\n?? outside.txt",
            "effective_changed_paths": ["outside.txt", "src/example.py"],
            "fingerprint": "after",
        },
    ]

    result, calls, state = invoke(
        tmp_path,
        git_observer=lambda _: observations.pop(0),
    )

    assert result["result"] == "blocked"
    assert set(result["blocked_reasons"]) == {
        "parent_verification_changed_file_outside_allowed_files",
        "parent_verification_repository_mutation",
    }
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    assert canonical["verification_git_observation"]["before"]["fingerprint"] == "before"
    assert canonical["verification_git_observation"]["after"]["fingerprint"] == "after"
    assert calls["verification"] == 1


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("head", "b" * 40, "runner_parent_handoff_head_mismatch"),
        ("staged_clean", False, "runner_parent_handoff_staged_mismatch"),
        (
            "effective_changed_paths",
            ["src/other.py"],
            "runner_parent_handoff_changed_files_mismatch",
        ),
    ],
)
def test_runner_parent_handoff_mismatch_skips_verifier_and_is_canonical(
    tmp_path,
    field,
    replacement,
    reason,
):
    observation = {
        "head": HEAD,
        "staged_paths": [],
        "staged_clean": True,
        "status_short": " M src/example.py",
        "effective_changed_paths": ["src/example.py"],
        "fingerprint": "handoff",
    }
    observation[field] = replacement
    if field == "staged_clean":
        observation["staged_paths"] = ["src/example.py"]

    result, calls, state = invoke(
        tmp_path,
        git_observer=lambda _: observation,
    )

    assert result["result"] == "blocked"
    assert reason in result["blocked_reasons"]
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    handoff = canonical["verification_git_observation"][
        "runner_parent_handoff"
    ]
    assert reason in handoff["reasons"]
    assert handoff["machine_evidence"]["head_after"] == HEAD
    assert handoff["parent_observation"][field] == replacement


def test_exact_runner_parent_handoff_proceeds_to_verifier_once(tmp_path):
    result, calls, state = invoke(tmp_path)

    assert result["result"] == "success"
    assert calls["runner"] == 1
    assert calls["verification"] == 1
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    handoff = canonical["verification_git_observation"][
        "runner_parent_handoff"
    ]
    assert handoff["reasons"] == []
    assert handoff["parent_observation"]["effective_changed_paths"] == [
        "src/example.py"
    ]


def test_canonical_path_equivalence_survives_runner_handoff_and_post_check(
    tmp_path,
):
    def mutate(payload):
        binding = payload["runtime_contract_binding"]
        binding["allowed_files"] = [r"src\example.py"]
        binding["actual_changed_files"] = ["./src/example.py"]
        binding["runtime_contract"]["allowed_files"] = ["./src/example.py"]
        payload["changed_files"] = [r"src\example.py"]

    observations = iter(
        [
            {
                "head": HEAD,
                "staged_paths": [],
                "staged_clean": True,
                "status_short": " M src/example.py",
                "effective_changed_paths": ["./src/example.py"],
                "fingerprint": "stable",
            },
            {
                "head": HEAD,
                "staged_paths": [],
                "staged_clean": True,
                "status_short": " M src/example.py",
                "effective_changed_paths": [r"src\example.py"],
                "fingerprint": "stable",
            },
        ]
    )
    result, calls, state = invoke(
        tmp_path,
        request_options={"allowed_files": ["./src/example.py"]},
        runner=evidence_runner(tmp_path, mutate=mutate),
        git_observer=lambda _: next(observations),
    )

    assert result["result"] == "success"
    assert calls["runner"] == 1
    assert calls["verification"] == 1
    assert "parent_verification_changed_file_outside_allowed_files" not in (
        result["blocked_reasons"]
    )
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    assert canonical["changed_files"] == ["src/example.py"]
    assert canonical["runtime_contract"]["allowed_files"] == ["src/example.py"]


def test_duplicate_selected_canonical_allowed_path_blocks_before_runner(
    tmp_path,
):
    result, calls, _ = invoke(
        tmp_path,
        request_options={
            "allowed_files": ["src/example.py", "./src/example.py"],
            "max_allowed_files": 2,
        },
    )

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == [
        "runtime_contract_allowed_files_invalid"
    ]
    assert calls["runner"] == 0
    assert calls["verification"] == 0


@pytest.mark.parametrize(
    "changed_files",
    [
        ["src/example.py", "./src/example.py"],
        ["/outside.py"],
        ["../outside.py"],
        [".git/config"],
        ["src/outside.py"],
    ],
)
def test_invalid_duplicate_or_out_of_scope_machine_changed_path_blocks_before_verifier(
    tmp_path,
    changed_files,
):
    result, calls, state = invoke(
        tmp_path,
        runner=evidence_runner(
            tmp_path,
            evidence_kwargs={"changed_files": changed_files},
        ),
    )

    assert result["result"] == "blocked"
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    assert calls["render"] == []
    assert (state / "in_flight.json").exists()


def test_changed_file_count_above_contract_max_blocks_before_runner_or_verifier(
    tmp_path,
):
    result, calls, _ = invoke(
        tmp_path,
        request_options={
            "allowed_files": ["src/example.py", "tests/test_example.py"],
            "max_allowed_files": 1,
        },
    )

    assert result["result"] == "blocked"
    assert calls["runner"] == 0
    assert calls["verification"] == 0


@pytest.mark.parametrize(
    ("binding_allowed", "embedded_allowed"),
    [
        ([], ["src/example.py"]),
        (["src/example.py", "tests/additional.py"], ["src/example.py"]),
        (["src/example.py"], []),
        (["src/example.py"], ["src/example.py", "tests/additional.py"]),
    ],
)
def test_missing_or_additional_allowed_path_blocks_before_verifier(
    tmp_path,
    binding_allowed,
    embedded_allowed,
):
    def mutate(payload):
        binding = payload["runtime_contract_binding"]
        binding["allowed_files"] = binding_allowed
        binding["runtime_contract"]["allowed_files"] = embedded_allowed

    result, calls, _ = invoke(
        tmp_path,
        runner=evidence_runner(tmp_path, mutate=mutate),
    )

    assert result["result"] == "blocked"
    assert calls["runner"] == 1
    assert calls["verification"] == 0


@pytest.mark.parametrize(
    "observed_paths",
    [
        ["src/example.py", "./src/example.py"],
        ["/outside.py"],
        ["../outside.py"],
        [".git/config"],
    ],
)
def test_invalid_or_duplicate_handoff_git_paths_block_before_verifier(
    tmp_path,
    observed_paths,
):
    observation = {
        "head": HEAD,
        "staged_paths": [],
        "staged_clean": True,
        "status_short": " M src/example.py",
        "effective_changed_paths": observed_paths,
        "fingerprint": "handoff",
    }
    result, calls, state = invoke(
        tmp_path,
        git_observer=lambda _: observation,
    )

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == [
        "runner_parent_handoff_paths_invalid"
    ]
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    assert canonical["verification_git_observation"][
        "runner_parent_handoff"
    ]["parent_observation"] is None


@pytest.mark.parametrize(
    ("safety_overrides", "expected_reason_fragment"),
    [
        ({"dispatcher_invoked": True}, "dispatcher_invoked"),
        ({"watcher_invoked": True}, "watcher_invoked"),
        ({"broad_scan_performed": True}, "broad_scan_performed"),
        ({"result_packet_written": False}, "result_packet_written"),
    ],
)
def test_success_safety_contradiction_blocks_before_parent_verifier(
    tmp_path,
    safety_overrides,
    expected_reason_fragment,
):
    result, calls, state = invoke(
        tmp_path,
        runner=evidence_runner(
            tmp_path,
            evidence_kwargs={"safety_overrides": safety_overrides},
        ),
    )

    assert result["result"] == "blocked"
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    assert calls["render"][0]["result"] == "blocked"
    assert any(
        expected_reason_fragment in reason
        for reason in result["blocked_reasons"]
    )
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    assert result["safety_flags"] == canonical["safety_flags"]
    assert calls["render"][0]["safety_flags"] == canonical["safety_flags"]


@pytest.mark.parametrize(
    ("safety_overrides", "evidence_kwargs", "flag", "reason"),
    [
        (
            {"runner_invoked": False},
            {},
            "runner_invoked",
            "runner_invocation_fact_mismatch",
        ),
        (
            {"codex_side_action_executed": False},
            {},
            "codex_side_action_executed",
            "codex_execution_fact_mismatch",
        ),
        (
            {"github_write_performed": False},
            {"github_comment_posted": True},
            "github_write_performed",
            "github_write_fact_mismatch",
        ),
    ],
)
def test_false_cannot_erase_stronger_true_fact_across_operator_surfaces(
    tmp_path,
    safety_overrides,
    evidence_kwargs,
    flag,
    reason,
):
    result, calls, state = invoke(
        tmp_path,
        runner=evidence_runner(
            tmp_path,
            evidence_kwargs={
                "safety_overrides": safety_overrides,
                **evidence_kwargs,
            },
        ),
    )

    request = state / "requests" / "req-9"
    canonical = json.loads((request / "canonical_evidence.json").read_text())
    request_summary = json.loads((request / "operator_summary.json").read_text())
    rendered = calls["render"][0]

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == [reason]
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    assert result["verification_invoked"] is False
    assert result["safety_flags"][flag] is True
    assert canonical["safety_flags"][flag] is True
    assert canonical["runner_machine_evidence"]["safety_flags"][flag] is True
    assert rendered["safety_flags"][flag] is True
    assert rendered["runner_machine_evidence"]["safety_flags"][flag] is True
    assert request_summary["safety_flags"][flag] is True
    if flag in result:
        assert result[flag] is True
        assert request_summary[flag] is True


@pytest.mark.parametrize("flag", ["commit_performed", "push_performed", "pr_created"])
def test_forbidden_true_fact_is_retained_in_summary_and_canonical_evidence(
    tmp_path,
    flag,
):
    result, calls, state = invoke(
        tmp_path,
        runner=evidence_runner(
            tmp_path,
            evidence_kwargs={"safety_overrides": {flag: True}},
        ),
    )

    assert result["result"] == "blocked"
    assert result["safety_flags"][flag] is True
    assert result[flag] is True
    assert calls["runner"] == 1
    assert calls["verification"] == 0
    assert calls["render"][0]["result"] == "blocked"
    canonical = json.loads(
        (state / "requests" / "req-9" / "canonical_evidence.json").read_text()
    )
    assert canonical["safety_flags"][flag] is True
    assert result["safety_flags"] == canonical["safety_flags"]


def test_parent_verification_staged_or_head_mutation_blocks(tmp_path):
    observations = iter(
        [
            {
                "head": HEAD,
                "staged_paths": [],
                "staged_clean": True,
                "status_short": " M src/example.py",
                "effective_changed_paths": ["src/example.py"],
                "fingerprint": "before",
            },
            {
                "head": "b" * 40,
                "staged_paths": ["src/example.py"],
                "staged_clean": False,
                "status_short": "M  src/example.py",
                "effective_changed_paths": ["src/example.py"],
                "fingerprint": "after",
            },
        ]
    )
    result, _, _ = invoke(tmp_path, git_observer=lambda _: next(observations))
    assert "parent_verification_head_changed" in result["blocked_reasons"]
    assert (
        "parent_verification_staged_changes_detected"
        in result["blocked_reasons"]
    )


def test_state_root_equal_or_child_of_target_repo_is_blocked(tmp_path):
    equal, equal_calls, _ = invoke(
        tmp_path,
        state_root=tmp_path / "repo",
    )
    child, child_calls, _ = invoke(
        tmp_path,
        state_root=tmp_path / "repo" / "state",
    )

    assert equal["blocked_reasons"] == ["state_root_inside_git_worktree"]
    assert child["blocked_reasons"] == ["state_root_inside_git_worktree"]
    assert equal_calls["runner"] == child_calls["runner"] == 0


def test_external_sibling_state_root_is_allowed(tmp_path):
    result, calls, _ = invoke(
        tmp_path,
        state_root=tmp_path / "external-state",
    )
    assert result["result"] == "success"
    assert calls["runner"] == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows path comparison")
def test_state_root_comparison_is_case_insensitive_on_windows(tmp_path):
    repo = tmp_path / "repo"
    differently_cased = Path(str(repo).swapcase()) / "state"
    result, calls, _ = invoke(tmp_path, state_root=differently_cased)
    assert result["blocked_reasons"] == ["state_root_inside_git_worktree"]
    assert calls["runner"] == 0


def test_exact_uncertain_incident_recovery_preserves_evidence_and_orders_records(
    tmp_path,
):
    raw = (
        b'{\n  "request_id": "req-9",\n  "target_issue": 9,\n'
        b'  "state": "delegating_runner",\n'
        b'  "at": "2026-07-24T00:00:00+00:00"\n}\n'
    )
    state, _, digest = recovery_fixture(tmp_path, raw=raw)
    request = state / "requests" / "req-9"
    tombstone_path = state / "replay_tombstones" / "req-9.json"
    release_observation = {}

    def remove_after_durable_records(path):
        release_observation["original"] = (
            request / "original_in_flight.json"
        ).is_file()
        release_observation["incident"] = (
            request / "recovery_incident.json"
        ).is_file()
        release_observation["tombstone"] = tombstone_path.is_file()
        path.unlink()

    result = recover_fixture(
        state,
        digest,
        remove_in_flight=remove_after_durable_records,
    )

    original = request / "original_in_flight.json"
    incident = json.loads((request / "recovery_incident.json").read_text())
    tombstone = json.loads(tombstone_path.read_text())
    assert result["result"] == "success"
    assert result["recovery_status"] == "recovered"
    assert result["original_evidence_preserved"] is True
    assert result["incident_record"] == "written"
    assert result["replay_tombstone"] == "written"
    assert result["active_in_flight_released"] is True
    assert result["runner_invoked"] is False
    assert result["codex_invoked"] is False
    assert result["github_write_performed"] is False
    assert result["repository_mutation_performed"] is False
    assert original.read_bytes() == raw
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    assert incident["outcome"] == tombstone["outcome"] == "uncertain"
    assert incident["replay_policy"] == tombstone["replay_policy"] == "prohibited"
    assert incident["observed_request_directory_inventory_before_recovery"] == []
    assert release_observation == {
        "original": True,
        "incident": True,
        "tombstone": True,
    }
    assert sorted(path.name for path in state.iterdir()) == [
        "replay_tombstones",
        "requests",
    ]
    assert not (state / "in_flight.json").exists()
    assert not (state / "processed_requests.jsonl").exists()


def test_recovery_preserves_valid_process_evidence_bytes_and_inventory(
    tmp_path,
):
    state, _, digest = recovery_fixture(tmp_path)
    process_path = write_valid_process_evidence(state)
    original_process_bytes = process_path.read_bytes()

    result = recover_fixture(state, digest)
    incident = json.loads(
        (
            state
            / "requests"
            / "req-9"
            / "recovery_incident.json"
        ).read_text()
    )

    assert result["result"] == "success"
    assert process_path.read_bytes() == original_process_bytes
    assert incident["outcome"] == "uncertain"
    assert incident[
        "observed_request_directory_inventory_before_recovery"
    ] == ["runner_process_evidence.json"]
    assert not (state / "in_flight.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "malformed",
        "request_id",
        "protocol",
        "target_issue",
        "target_repository",
        "machine_path",
        "process_state",
        "stream_metadata",
        "machine_metadata",
    ],
)
def test_recovery_blocks_malformed_or_mismatched_process_evidence(
    tmp_path,
    mutation,
):
    state, raw, digest = recovery_fixture(tmp_path)
    process_path = write_valid_process_evidence(state)
    if mutation == "malformed":
        process_path.write_bytes(b"{not-json}\n")
    else:
        value = json.loads(process_path.read_text(encoding="utf-8"))
        if mutation == "request_id":
            value["request_id"] = "req-other"
        elif mutation == "protocol":
            value["protocol"] = (
                "lawb.display_pilot.runner_process_evidence.v0"
            )
        elif mutation == "target_issue":
            value["target_issue"] = 10
        elif mutation == "target_repository":
            value["target_repository"] = "HarryWhite-TW/wrong-repository"
        elif mutation == "machine_path":
            value["machine_evidence_path"] = str(
                state
                / "requests"
                / "req-other"
                / "runner_machine_evidence.json"
            )
        elif mutation == "process_state":
            value["exit_code"] = None
        elif mutation == "stream_metadata":
            value["stdout"]["preview"] = "contradictory"
        else:
            value["machine_evidence_size"] = 1
            value["machine_evidence_sha256"] = "0" * 64
        process_path.write_text(json.dumps(value), encoding="utf-8")
    observed = process_path.read_bytes()

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == [
        "runner_process_evidence_invalid"
    ]
    assert process_path.read_bytes() == observed
    assert (state / "in_flight.json").read_bytes() == raw
    assert not (
        state / "requests" / "req-9" / "recovery_incident.json"
    ).exists()


def test_recovery_validates_and_preserves_observed_machine_evidence(
    tmp_path,
):
    state, _, digest = recovery_fixture(tmp_path)
    machine_bytes = b'{"parent_observed":"machine"}\n'
    process_path = write_valid_process_evidence(
        state,
        machine_evidence_bytes=machine_bytes,
    )
    process_bytes = process_path.read_bytes()
    machine_path = (
        state
        / "requests"
        / "req-9"
        / "runner_machine_evidence.json"
    )

    result = recover_fixture(state, digest)
    incident = json.loads(
        (
            state
            / "requests"
            / "req-9"
            / "recovery_incident.json"
        ).read_text()
    )

    assert result["result"] == "success"
    assert process_path.read_bytes() == process_bytes
    assert machine_path.read_bytes() == machine_bytes
    assert incident[
        "observed_request_directory_inventory_before_recovery"
    ] == [
        "runner_machine_evidence.json",
        "runner_process_evidence.json",
    ]
    assert incident["outcome"] == "uncertain"


def test_recovery_machine_observation_mismatch_keeps_in_flight(
    tmp_path,
):
    state, raw, digest = recovery_fixture(tmp_path)
    process_path = write_valid_process_evidence(
        state,
        machine_evidence_bytes=b"expected-machine",
    )
    machine_path = (
        state
        / "requests"
        / "req-9"
        / "runner_machine_evidence.json"
    )
    machine_path.write_bytes(b"actual-machine")
    process_bytes = process_path.read_bytes()

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == [
        "runner_process_evidence_invalid"
    ]
    assert (state / "in_flight.json").read_bytes() == raw
    assert process_path.read_bytes() == process_bytes
    assert machine_path.read_bytes() == b"actual-machine"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("request_id", "in_flight_request_id_mismatch"),
        ("target_issue", "in_flight_target_issue_mismatch"),
        ("sha256", "in_flight_sha256_mismatch"),
        ("malformed", "in_flight_invalid"),
        ("state", "in_flight_state_unsupported"),
        ("timestamp", "in_flight_invalid"),
    ],
)
def test_recovery_exact_binding_mismatches_fail_closed(tmp_path, mutation, reason):
    state, raw, digest = recovery_fixture(tmp_path)
    arguments = {}
    if mutation == "request_id":
        (state / "requests" / "req-other").mkdir()
        arguments["request_id"] = "req-other"
    elif mutation == "target_issue":
        arguments["target_issue"] = 10
    elif mutation == "sha256":
        digest = "0" * 64
    elif mutation == "malformed":
        raw = b"{bad-json}\n"
        (state / "in_flight.json").write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
    else:
        payload = json.loads(raw)
        payload["state" if mutation == "state" else "at"] = (
            "completed" if mutation == "state" else ""
        )
        raw = json.dumps(payload).encode("utf-8")
        (state / "in_flight.json").write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()

    result = recover_fixture(state, digest, **arguments)

    assert result["blocked_reasons"] == [reason]
    assert (state / "in_flight.json").exists()
    assert not (state / "requests" / arguments.get("request_id", "req-9") / "original_in_flight.json").exists()


def test_recovery_lock_processed_conflict_and_nonempty_request_fail_closed(tmp_path):
    for case in ("lock", "processed", "nonempty"):
        case_root = tmp_path / case
        state, _, digest = recovery_fixture(case_root)
        if case == "lock":
            (state / "operator.lock").write_text("active", encoding="utf-8")
            expected = "active_lock_present"
        elif case == "processed":
            (state / "processed_requests.jsonl").write_text(
                json.dumps({"request_id": "req-9"}) + "\n",
                encoding="utf-8",
            )
            expected = "processed_request_conflict"
        else:
            (state / "requests" / "req-9" / "runner_machine_evidence.json").write_text(
                "{}",
                encoding="utf-8",
            )
            expected = "request_directory_not_empty"

        result = recover_fixture(state, digest)

        assert result["blocked_reasons"] == [expected]
        assert (state / "in_flight.json").exists()


def test_existing_lock_blocks_without_promoting_pending_or_mutating_state(
    tmp_path,
):
    state, raw, digest = recovery_fixture(tmp_path)
    request = state / "requests" / "req-9"
    pending = request / "original_in_flight.json.pending"
    pending.write_bytes(raw)
    lock = state / "operator.lock"
    lock.write_bytes(b"stale-lock-evidence")

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == ["active_lock_present"]
    assert lock.read_bytes() == b"stale-lock-evidence"
    assert pending.read_bytes() == raw
    assert (state / "in_flight.json").read_bytes() == raw
    assert not (request / "original_in_flight.json").exists()
    assert not (request / "recovery_incident.json").exists()
    assert not (state / "replay_tombstones").exists()
    assert result["runner_invoked"] is False
    assert result["codex_invoked"] is False
    assert result["github_write_performed"] is False
    assert result["repository_mutation_performed"] is False


def test_recovery_rejects_state_root_inside_protected_worktree(tmp_path):
    protected = tmp_path / "protected"
    state, _, digest = recovery_fixture(protected)

    result = recover_fixture(
        state,
        digest,
        forbidden_state_roots=(protected,),
    )

    assert result["blocked_reasons"] == ["state_root_inside_git_worktree"]
    assert (state / "in_flight.json").exists()


def test_conflicting_original_snapshot_is_not_overwritten(tmp_path):
    state, _, digest = recovery_fixture(tmp_path)
    original = state / "requests" / "req-9" / "original_in_flight.json"
    original.write_bytes(b"conflicting")

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == ["original_snapshot_conflict"]
    assert original.read_bytes() == b"conflicting"
    assert (state / "in_flight.json").exists()


def test_conflicting_incident_record_is_not_overwritten(tmp_path):
    state, raw, digest = recovery_fixture(tmp_path)
    request = state / "requests" / "req-9"
    (request / "original_in_flight.json").write_bytes(raw)
    incident = request / "recovery_incident.json"
    incident.write_text("{}", encoding="utf-8")

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == ["recovery_incident_conflict"]
    assert incident.read_text() == "{}"
    assert (state / "in_flight.json").exists()


def test_conflicting_tombstone_is_not_overwritten(tmp_path):
    state, _, digest = recovery_fixture(tmp_path)
    first = recover_fixture(
        state,
        digest,
        phase_hook=lambda phase: (
            (_ for _ in ()).throw(RuntimeError("stop"))
            if phase == "after_incident_record"
            else None
        ),
    )
    tombstone = state / "replay_tombstones" / "req-9.json"
    tombstone.parent.mkdir()
    tombstone.write_text("{}", encoding="utf-8")

    result = recover_fixture(state, digest)

    assert first["result"] == "blocked"
    assert result["blocked_reasons"] == ["replay_tombstone_conflict"]
    assert tombstone.read_text() == "{}"
    assert (state / "in_flight.json").exists()


@pytest.mark.parametrize(
    ("phase", "expected_artifacts"),
    [
        ("before_original_snapshot", set()),
        ("after_original_snapshot", {"original_in_flight.json"}),
        (
            "after_incident_record",
            {"original_in_flight.json", "recovery_incident.json"},
        ),
        (
            "after_replay_tombstone",
            {
                "original_in_flight.json",
                "recovery_incident.json",
                "tombstone",
            },
        ),
    ],
)
def test_recovery_interruption_keeps_in_flight_and_is_safely_rerunnable(
    tmp_path,
    phase,
    expected_artifacts,
):
    state, _, digest = recovery_fixture(tmp_path)

    def interrupt(observed):
        if observed == phase:
            raise RuntimeError("simulated interruption")

    interrupted = recover_fixture(state, digest, phase_hook=interrupt)
    request = state / "requests" / "req-9"
    observed = {
        path.name for path in request.iterdir()
    }
    if (state / "replay_tombstones" / "req-9.json").exists():
        observed.add("tombstone")

    assert interrupted["result"] == "blocked"
    assert (state / "in_flight.json").exists()
    assert observed == expected_artifacts

    completed = recover_fixture(state, digest)
    assert completed["result"] == "success"
    assert completed["recovery_status"] == "recovered"
    assert not (state / "in_flight.json").exists()


def test_unlink_failure_remains_replay_safe_and_rerun_reports_already_recovered(
    tmp_path,
):
    state, _, digest = recovery_fixture(tmp_path)

    def remove_then_fail(path):
        path.unlink()
        raise OSError("simulated post-unlink failure")

    interrupted = recover_fixture(
        state,
        digest,
        remove_in_flight=remove_then_fail,
    )

    assert interrupted["result"] == "blocked"
    assert not (state / "in_flight.json").exists()
    assert (state / "replay_tombstones" / "req-9.json").is_file()

    completed = recover_fixture(state, digest)
    assert completed["result"] == "success"
    assert completed["recovery_status"] == "already_recovered"
    assert completed["incident_record"] == "already_present"
    assert completed["replay_tombstone"] == "already_present"


def test_completed_recovery_rerun_does_not_rewrite_historical_records(tmp_path):
    state, _, digest = recovery_fixture(tmp_path)
    first = recover_fixture(state, digest)
    request = state / "requests" / "req-9"
    incident_before = (request / "recovery_incident.json").read_bytes()
    tombstone_before = (
        state / "replay_tombstones" / "req-9.json"
    ).read_bytes()

    second = recover_incident(
        state_root=state,
        request_id="req-9",
        target_issue=9,
        in_flight_sha256=digest,
        now=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert first["recovery_status"] == "recovered"
    assert second["recovery_status"] == "already_recovered"
    assert (request / "recovery_incident.json").read_bytes() == incident_before
    assert (state / "replay_tombstones" / "req-9.json").read_bytes() == tombstone_before


def test_tombstoned_request_is_stale_and_never_invokes_runner(tmp_path):
    state, _, digest = recovery_fixture(tmp_path)
    assert recover_fixture(state, digest)["result"] == "success"

    result, calls, _ = invoke(tmp_path, max_cycles=2)

    assert result["result"] == "success"
    assert result["polling_outcome"] == "no_eligible_request"
    assert calls["runner"] == 0
    assert calls["verification"] == 0


def test_different_request_blocks_until_recovery_then_becomes_eligible(tmp_path):
    state, _, digest = recovery_fixture(tmp_path)
    blocked, blocked_calls, _ = invoke(
        tmp_path,
        request_options={"request_id": "req-10"},
    )

    assert blocked["blocked_reasons"] == ["unresolved_in_flight_state"]
    assert blocked_calls["runner"] == 0

    assert recover_fixture(state, digest)["result"] == "success"
    eligible, eligible_calls, _ = invoke(
        tmp_path,
        request_options={"request_id": "req-10"},
    )
    assert eligible["result"] == "success"
    assert eligible_calls["runner"] == 1


@pytest.mark.parametrize("mutation", ["malformed", "identity_mismatch"])
def test_matching_malformed_or_mismatched_tombstone_fails_start_closed(
    tmp_path,
    mutation,
):
    state = tmp_path / "state"
    tombstone = state / "replay_tombstones" / "req-9.json"
    tombstone.parent.mkdir(parents=True)
    if mutation == "malformed":
        tombstone.write_text("{bad-json}", encoding="utf-8")
    else:
        tombstone.write_text(
            json.dumps(
                {
                    "protocol": "lawb.display_pilot.replay_tombstone.v1",
                    "schema_version": 1,
                    "request_id": "req-other",
                    "target_issue": 9,
                    "outcome": "uncertain",
                    "replay_policy": "prohibited",
                    "original_in_flight_sha256": "a" * 64,
                    "incident_record": "requests/req-9/recovery_incident.json",
                    "recorded_at": NOW.isoformat(),
                }
            ),
            encoding="utf-8",
        )

    result, calls, _ = invoke(tmp_path)

    assert result["result"] == "blocked"
    assert result["blocked_reasons"] == ["replay_tombstone_invalid"]
    assert calls["runner"] == 0
    assert calls["verification"] == 0


def test_in_flight_absent_with_incomplete_recovery_artifacts_fails_closed(tmp_path):
    state, raw, digest = recovery_fixture(tmp_path)
    (state / "in_flight.json").unlink()
    (state / "requests" / "req-9" / "original_in_flight.json").write_bytes(raw)

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == [
        "in_flight_missing_or_recovery_incomplete"
    ]


@pytest.mark.parametrize("protected_name", ["lawb", "hgw", "hag"])
@pytest.mark.parametrize("relation", ["equal", "beneath"])
def test_recovery_blocks_equal_or_beneath_each_protected_root_without_writing(
    tmp_path,
    protected_name,
    relation,
):
    protected = tmp_path / protected_name
    state = protected if relation == "equal" else protected / "nested-state"
    state, raw, digest = recovery_state_at(state)

    result = recover_fixture(
        state,
        digest,
        forbidden_state_roots=(protected,),
    )

    assert result["blocked_reasons"] == ["state_root_inside_git_worktree"]
    assert (state / "in_flight.json").read_bytes() == raw
    assert not (state / "operator.lock").exists()
    assert not (state / "replay_tombstones").exists()
    assert list((state / "requests" / "req-9").iterdir()) == []


def _symlink_or_skip(link, target, *, is_directory):
    try:
        link.symlink_to(target, target_is_directory=is_directory)
        return
    except (NotImplementedError, OSError) as symlink_error:
        if os.name == "nt" and is_directory:
            completed = subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                return
        pytest.skip(f"symlink or junction creation unavailable: {symlink_error}")


@pytest.mark.skipif(os.name != "nt", reason="Windows handle contract")
def test_windows_evidence_open_uses_nofollow_and_read_only_share(monkeypatch):
    observed = {}

    def create_file(
        path,
        desired_access,
        share_mode,
        creation_disposition,
        flags_and_attributes,
    ):
        observed.update(
            {
                "path": path,
                "desired_access": desired_access,
                "share_mode": share_mode,
                "creation_disposition": creation_disposition,
                "flags_and_attributes": flags_and_attributes,
            }
        )
        return 917

    monkeypatch.setattr(operator, "_win32_create_file", create_file)

    assert operator._win32_create_evidence_handle(Path("evidence.json")) == 917
    assert observed["desired_access"] == operator._WINDOWS_GENERIC_READ
    assert observed["share_mode"] == operator._WINDOWS_FILE_SHARE_READ
    assert (
        observed["creation_disposition"]
        == operator._WINDOWS_OPEN_EXISTING
    )
    assert (
        observed["flags_and_attributes"]
        & operator._WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows handle contract")
@pytest.mark.parametrize(
    ("attributes", "file_type"),
    [
        (operator._WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT, 1),
        (operator._WINDOWS_FILE_ATTRIBUTE_DIRECTORY, 1),
        (0, 2),
    ],
)
def test_windows_evidence_handle_rejects_reparse_directory_and_device(
    tmp_path,
    monkeypatch,
    attributes,
    file_type,
):
    path = tmp_path / "evidence.json"
    raw = b"evidence"
    path.write_bytes(raw)
    metadata = path.stat()
    information = operator._WindowsHandleInfo(
        attributes=attributes,
        file_type=file_type,
        volume_serial=1,
        file_index=metadata.st_ino,
        size=len(raw),
        last_write=1,
    )
    closed = []
    monkeypatch.setattr(
        operator,
        "_win32_create_evidence_handle",
        lambda _: 918,
    )
    monkeypatch.setattr(
        operator,
        "_win32_evidence_handle_info",
        lambda _: information,
    )
    monkeypatch.setattr(
        operator,
        "_win32_read_evidence_handle",
        lambda *_: raw,
    )
    monkeypatch.setattr(
        operator,
        "_win32_close_evidence_handle",
        closed.append,
    )

    with pytest.raises(ValueError, match="evidence_invalid"):
        operator._open_canonical_evidence_guard(
            path,
            reason="evidence_invalid",
        )

    assert closed == [918]


@pytest.mark.skipif(os.name != "nt", reason="Windows handle contract")
def test_windows_evidence_handle_identity_drift_is_rejected(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "evidence.json"
    raw = b"evidence"
    path.write_bytes(raw)
    metadata = path.stat()
    initial = operator._WindowsHandleInfo(
        attributes=0,
        file_type=operator._WINDOWS_FILE_TYPE_DISK,
        volume_serial=1,
        file_index=metadata.st_ino,
        size=len(raw),
        last_write=1,
    )
    changed = operator._WindowsHandleInfo(
        **{**initial.__dict__, "last_write": 2}
    )
    observations = iter((initial, changed))
    closed = []
    monkeypatch.setattr(
        operator,
        "_win32_create_evidence_handle",
        lambda _: 919,
    )
    monkeypatch.setattr(
        operator,
        "_win32_evidence_handle_info",
        lambda _: next(observations),
    )
    monkeypatch.setattr(
        operator,
        "_win32_read_evidence_handle",
        lambda *_: raw,
    )
    monkeypatch.setattr(
        operator,
        "_win32_close_evidence_handle",
        closed.append,
    )

    with pytest.raises(ValueError, match="evidence_invalid"):
        operator._open_canonical_evidence_guard(
            path,
            reason="evidence_invalid",
        )

    assert closed == [919]


@pytest.mark.skipif(os.name != "nt", reason="Windows handle contract")
def test_windows_evidence_guard_denies_write_delete_and_reads_same_handle(
    tmp_path,
):
    path = tmp_path / "evidence.json"
    raw = b"canonical evidence"
    path.write_bytes(raw)

    guard = operator._open_canonical_evidence_guard(
        path,
        reason="evidence_invalid",
    )
    try:
        assert guard.raw == raw
        with pytest.raises(OSError):
            path.write_bytes(b"replacement")
        with pytest.raises(OSError):
            path.unlink()
        guard.require_unchanged()
    finally:
        guard.close()

    path.write_bytes(b"released")


@pytest.mark.skipif(os.name != "nt", reason="Windows handle contract")
def test_windows_evidence_path_to_reparse_swap_is_rejected(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "evidence.json"
    target = tmp_path / "target.json"
    path.write_bytes(b"original")
    target.write_bytes(b"replacement")
    original_create = operator._win32_create_file
    swapped = False

    def swap_then_create(*arguments):
        nonlocal swapped
        if not swapped:
            swapped = True
            path.unlink()
            _symlink_or_skip(path, target, is_directory=False)
        return original_create(*arguments)

    monkeypatch.setattr(operator, "_win32_create_file", swap_then_create)

    with pytest.raises(ValueError, match="evidence_invalid"):
        operator._open_canonical_evidence_guard(
            path,
            reason="evidence_invalid",
        )

    assert swapped is True


@pytest.mark.parametrize("artifact", ["process", "machine"])
def test_recovery_rejects_symlinked_evidence_entry(tmp_path, artifact):
    state, raw, digest = recovery_fixture(tmp_path)
    machine_bytes = b'{"parent_observed":"machine"}\n'
    process_path = write_valid_process_evidence(
        state,
        machine_evidence_bytes=(
            machine_bytes if artifact == "machine" else None
        ),
    )
    machine_path = process_path.with_name("runner_machine_evidence.json")
    canonical = process_path if artifact == "process" else machine_path
    target = state / f"other-{artifact}-evidence.json"
    target.write_bytes(canonical.read_bytes())
    canonical.unlink()
    _symlink_or_skip(canonical, target, is_directory=False)

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == [
        "runner_process_evidence_invalid"
    ]
    assert (state / "in_flight.json").read_bytes() == raw
    assert target.is_file()


def test_recovery_rejects_dangling_process_evidence_symlink(tmp_path):
    state, raw, digest = recovery_fixture(tmp_path)
    process_path = (
        state / "requests" / "req-9" / "runner_process_evidence.json"
    )
    _symlink_or_skip(
        process_path,
        state / "missing-process-evidence.json",
        is_directory=False,
    )

    result = recover_fixture(state, digest)

    assert result["result"] == "blocked"
    assert (state / "in_flight.json").read_bytes() == raw
    assert not (state / "missing-process-evidence.json").exists()


def test_recovery_rejects_directory_evidence_entry(tmp_path):
    state, raw, digest = recovery_fixture(tmp_path)
    process_path = (
        state / "requests" / "req-9" / "runner_process_evidence.json"
    )
    process_path.mkdir()

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == [
        "runner_process_evidence_invalid"
    ]
    assert (state / "in_flight.json").read_bytes() == raw


def test_recovery_rejects_directory_reparse_evidence_entry(tmp_path):
    state, raw, digest = recovery_fixture(tmp_path)
    process_path = (
        state / "requests" / "req-9" / "runner_process_evidence.json"
    )
    target = state / "reparse-target"
    target.mkdir()
    _symlink_or_skip(process_path, target, is_directory=True)

    result = recover_fixture(state, digest)

    assert result["result"] == "blocked"
    assert (state / "in_flight.json").read_bytes() == raw
    assert target.is_dir()


def test_recovery_detects_process_evidence_path_swap_before_open(
    tmp_path,
    monkeypatch,
):
    state, raw, digest = recovery_fixture(tmp_path)
    process_path = write_valid_process_evidence(state)
    replacement = state / "replacement-process-evidence.json"
    replacement.write_bytes(process_path.read_bytes())
    swapped = False

    if os.name == "nt":
        original_open = operator._win32_create_file
    else:
        original_open = operator.os.open

    def swap_then_open(path, *args, **kwargs):
        nonlocal swapped
        if Path(path) == process_path and not swapped:
            swapped = True
            os.replace(replacement, process_path)
        return original_open(path, *args, **kwargs)

    if os.name == "nt":
        monkeypatch.setattr(operator, "_win32_create_file", swap_then_open)
    else:
        monkeypatch.setattr(operator.os, "open", swap_then_open)
    result = recover_fixture(state, digest)

    assert swapped is True
    assert result["blocked_reasons"] == [
        "runner_process_evidence_invalid"
    ]
    assert (state / "in_flight.json").read_bytes() == raw


@pytest.mark.parametrize(
    "escape",
    ["request_directory", "tombstone_directory", "in_flight"],
)
def test_recovery_resolved_path_escape_blocks_without_mutating_target(
    tmp_path,
    escape,
):
    state, raw, digest = recovery_fixture(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("unchanged", encoding="utf-8")

    if escape == "request_directory":
        request = state / "requests" / "req-9"
        request.rmdir()
        escaped_request = external / "request"
        escaped_request.mkdir()
        _symlink_or_skip(request, escaped_request, is_directory=True)
    elif escape == "tombstone_directory":
        escaped_tombstones = external / "tombstones"
        escaped_tombstones.mkdir()
        _symlink_or_skip(
            state / "replay_tombstones",
            escaped_tombstones,
            is_directory=True,
        )
    else:
        in_flight = state / "in_flight.json"
        escaped_in_flight = external / "in_flight.json"
        escaped_in_flight.write_bytes(raw)
        in_flight.unlink()
        _symlink_or_skip(in_flight, escaped_in_flight, is_directory=False)

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == ["recovery_path_escape"]
    assert marker.read_text(encoding="utf-8") == "unchanged"
    assert not (external / "original_in_flight.json").exists()
    assert not (external / "recovery_incident.json").exists()
    assert not (external / "req-9.json").exists()


@pytest.mark.parametrize(
    ("phase", "pending_relative"),
    [
        (
            "after_original_pending",
            "requests/req-9/original_in_flight.json.pending",
        ),
        (
            "after_incident_pending",
            "requests/req-9/recovery_incident.json.pending",
        ),
        (
            "after_tombstone_pending",
            "replay_tombstones/req-9.json.pending",
        ),
    ],
)
def test_recovery_owned_pending_write_resumes_after_controlled_interruption(
    tmp_path,
    phase,
    pending_relative,
):
    state, raw, digest = recovery_fixture(tmp_path)

    def interrupt(observed):
        if observed == phase:
            raise RuntimeError("simulated controlled interruption")

    interrupted = recover_fixture(
        state,
        digest,
        phase_hook=interrupt,
    )

    assert interrupted["result"] == "blocked"
    assert interrupted["blocked_reasons"] == [
        "recovery_interrupted:RuntimeError"
    ]
    assert interrupted["runner_invoked"] is False
    assert interrupted["codex_invoked"] is False
    assert interrupted["github_write_performed"] is False
    assert (state / "in_flight.json").read_bytes() == raw
    assert (state / pending_relative).is_file()

    completed = recover_fixture(state, digest)
    request = state / "requests" / "req-9"
    incident = json.loads(
        (request / "recovery_incident.json").read_text(encoding="utf-8")
    )
    tombstone = json.loads(
        (state / "replay_tombstones" / "req-9.json").read_text(
            encoding="utf-8"
        )
    )
    assert completed["result"] == "success"
    assert completed["recovery_status"] == "recovered"
    assert not (state / "in_flight.json").exists()
    assert not (state / pending_relative).exists()
    assert (request / "original_in_flight.json").read_bytes() == raw
    assert incident["recorded_at"] == tombstone["recorded_at"] == NOW.isoformat()
    assert tombstone["replay_policy"] == "prohibited"


@pytest.mark.parametrize("failure", ["creation_error", "not_directory"])
def test_tombstone_store_creation_failure_preserves_in_flight(
    tmp_path,
    failure,
):
    state, raw, digest = recovery_fixture(tmp_path)
    tombstone_store = state / "replay_tombstones"

    def fail_creation(path):
        if failure == "creation_error":
            raise OSError("simulated directory creation failure")
        path.write_text("not-a-directory", encoding="utf-8")

    result = recover_fixture(
        state,
        digest,
        create_tombstone_store=fail_creation,
    )

    assert result["blocked_reasons"] == ["replay_tombstone_store_invalid"]
    assert (state / "in_flight.json").read_bytes() == raw
    assert not (tombstone_store / "req-9.json").exists()
    assert not (tombstone_store / "req-9.json.pending").exists()
    assert result["runner_invoked"] is False
    assert result["codex_invoked"] is False
    assert result["github_write_performed"] is False


@pytest.mark.parametrize("escape", ["outside_state", "protected_root"])
def test_post_creation_tombstone_store_escape_blocks_before_pending_write(
    tmp_path,
    escape,
):
    state, raw, digest = recovery_fixture(tmp_path)
    external = tmp_path / "external-tombstones"
    external.mkdir()
    protected = state.parent / "lawb"
    target = external if escape == "outside_state" else protected

    def substitute_store(path):
        _symlink_or_skip(path, target, is_directory=True)

    result = recover_fixture(
        state,
        digest,
        create_tombstone_store=substitute_store,
    )

    assert result["blocked_reasons"] == ["recovery_path_escape"]
    assert (state / "in_flight.json").read_bytes() == raw
    assert not (target / "req-9.json").exists()
    assert not (target / "req-9.json.pending").exists()
    assert result["runner_invoked"] is False
    assert result["codex_invoked"] is False
    assert result["github_write_performed"] is False


def test_unknown_temporary_looking_recovery_file_still_blocks(tmp_path):
    state, raw, digest = recovery_fixture(tmp_path)
    unknown = state / "requests" / "req-9" / ".original_in_flight.json.123.tmp"
    unknown.write_bytes(raw)

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == ["request_directory_not_empty"]
    assert unknown.read_bytes() == raw
    assert (state / "in_flight.json").exists()


@pytest.mark.parametrize(
    ("pending_relative", "reason"),
    [
        (
            "requests/req-9/original_in_flight.json.pending",
            "original_snapshot_conflict",
        ),
        (
            "requests/req-9/recovery_incident.json.pending",
            "recovery_incident_conflict",
        ),
        (
            "replay_tombstones/req-9.json.pending",
            "replay_tombstone_conflict",
        ),
    ],
)
def test_conflicting_recovery_owned_pending_file_is_not_overwritten(
    tmp_path,
    pending_relative,
    reason,
):
    state, _, digest = recovery_fixture(tmp_path)
    pending = state / pending_relative
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"conflicting")

    result = recover_fixture(state, digest)

    assert result["blocked_reasons"] == [reason]
    assert pending.read_bytes() == b"conflicting"
    assert (state / "in_flight.json").exists()
