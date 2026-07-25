import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge.display_pilot_operator import (
    _read_machine_evidence,
    build_verification_argv,
    execute_verification_command,
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
    assert result["blocked_reasons"] == ["runner_execution_uncertain"]
    assert result["runner_invoked"] is False
    assert result["safety_flags"]["runner_invoked"] is False
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

    assert result["blocked_reasons"] == ["runner_execution_uncertain"]
    assert calls["render"] == []
    assert (state / "in_flight.json").exists()


def test_success_machine_evidence_with_reason_is_rejected(tmp_path):
    def contradictory_runner(request, evidence_path):
        payload = machine_evidence(tmp_path / "repo")
        payload["blocked_reasons"] = ["contradictory_reason"]
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    result, calls, state = invoke(tmp_path, runner=contradictory_runner)

    assert result["blocked_reasons"] == ["runner_execution_uncertain"]
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
        assert result["blocked_reasons"] == ["runner_execution_uncertain"]
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
    assert result["blocked_reasons"] == ["runner_execution_uncertain"]
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
