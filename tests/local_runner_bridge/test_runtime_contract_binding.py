import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.runtime_contract_binding import (
    enforce_changed_files,
    inspect_runtime_contract,
)
from local_runner_bridge.task_packet_validator import TASK_PACKET_PROTOCOL_V1_1


HEAD = "a" * 40


def packet(**overrides):
    values = {
        "protocol": TASK_PACKET_PROTOCOL_V1_1,
        "packet_id": "task-204-runtime-contract",
        "logical_issue": 204,
        "repository": "HarryWhite-TW/local-ai-workbench",
        "branch": "feature/runtime-contract",
        "expected_head": HEAD,
        "allowed_files": ["src/example.py", "tests/test_example.py"],
        "max_allowed_files": 2,
    }
    values.update(overrides)
    allowed = "\n".join(f"  - {value}" for value in values["allowed_files"])
    return f"""protocol: {values['protocol']}
packet_id: {values['packet_id']}
logical_issue: {values['logical_issue']}
phase: reviewbundle
action_type: read_only_audit
risk_level: low
repository: {values['repository']}
branch: {values['branch']}
expected_head: {values['expected_head']}
allowed_files:
{allowed}
forbidden_operations:
  - commit
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 204
  marker: REVIEWBUNDLE-AUDIT-VISIBLE
stop_condition: stop_after_result_packet
task_mode: PATCH_ONLY
objective: Bind task scope to runtime evidence.
max_allowed_files: {values['max_allowed_files']}
context_scope:
  - src/example.py
repair_attempt_limit: 1
verification_command_policy: explicit_only
verification_commands:
  - python -m pytest tests/test_example.py -q
scope_expansion_allowed: false
"""


def surface(packet_text=None):
    body = packet() if packet_text is None else packet_text
    return (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "BEGIN_TASK_PACKET\n"
        f"{body}"
        "END_TASK_PACKET\n"
    )


def inspect(surface_text=None, **overrides):
    state = {
        "logical_issue": 204,
        "repository": "HarryWhite-TW/local-ai-workbench",
        "branch": "feature/runtime-contract",
        "head": HEAD,
    }
    state.update(overrides)
    return inspect_runtime_contract(
        surface() if surface_text is None else surface_text, **state
    )


def test_no_contract_is_explicitly_not_present():
    result = inspect("ordinary issue body")

    assert result["status"] == "not_present"
    assert result["contract_present"] is False
    assert result["pre_execution"]["status"] == "not_present"


def test_matching_contract_passes_pre_execution_binding():
    result = inspect()

    assert result["status"] == "passed"
    assert result["contract_present"] is True
    assert result["pre_execution"] == {"status": "passed", "reasons": []}
    assert result["allowed_files"] == ["src/example.py", "tests/test_example.py"]


def test_valid_legacy_v1_is_not_runtime_contract_bound():
    legacy = packet(protocol="lawb.local_runner.task_packet.v1")
    legacy = "\n".join(
        line
        for line in legacy.splitlines()
        if not line.startswith(
            (
                "task_mode:",
                "objective:",
                "max_allowed_files:",
                "context_scope:",
                "repair_attempt_limit:",
                "verification_command_policy:",
                "verification_commands:",
                "scope_expansion_allowed:",
            )
        )
        and line not in {"  - src/example.py", "  - python -m pytest tests/test_example.py -q"}
    ) + "\n"

    result = inspect(surface(legacy))

    assert result["status"] == "not_present"
    assert result["contract_present"] is False


def test_malformed_present_packet_is_contract_violation():
    result = inspect("LOCAL-RUNNER-TASK-PACKET-V1\nBEGIN_TASK_PACKET\nbad\n")

    assert result["status"] == "contract_violation"
    assert "end_task_packet_missing" in result["reasons"]


def test_identity_mismatches_are_stable_contract_violations():
    cases = [
        ({"logical_issue": 999}, "logical_issue_mismatch"),
        ({"repository": "Other/repo"}, "repository_mismatch"),
        ({"branch": "other"}, "branch_mismatch"),
        ({"head": "b" * 40}, "expected_head_mismatch"),
    ]

    for state, reason in cases:
        result = inspect(**state)
        assert result["status"] == "contract_violation"
        assert reason in result["reasons"]


def test_short_current_head_fails_closed():
    result = inspect(head="1234567")

    assert result["status"] == "contract_violation"
    assert "current_head_not_full_sha" in result["reasons"]


def test_in_scope_changed_files_pass_post_execution():
    result = enforce_changed_files(inspect(), ["src/example.py"])

    assert result["status"] == "passed"
    assert result["post_execution"] == {"status": "passed", "reasons": []}
    assert result["actual_changed_files"] == ["src/example.py"]


def test_path_separator_normalization_avoids_false_mismatch():
    result = enforce_changed_files(inspect(), [r"src\example.py"])

    assert result["status"] == "passed"
    assert result["actual_changed_files"] == ["src/example.py"]


def test_out_of_scope_changed_file_is_contract_violation():
    result = enforce_changed_files(inspect(), ["README.md"])

    assert result["status"] == "contract_violation"
    assert "changed_file_outside_allowed_files" in result["reasons"]


def test_changed_file_count_over_maximum_is_contract_violation():
    binding = inspect(surface(packet(max_allowed_files=1, allowed_files=["a.py"])))
    binding["allowed_files"] = ["a.py", "b.py"]
    binding["runtime_contract"]["allowed_files"] = ["a.py", "b.py"]
    result = enforce_changed_files(binding, ["a.py", "b.py"])

    assert result["status"] == "contract_violation"
    assert "changed_file_count_exceeds_max_allowed_files" in result["reasons"]


def test_not_present_remains_explicit_after_legacy_execution():
    result = enforce_changed_files(inspect("ordinary issue body"), ["legacy.py"])

    assert result["status"] == "not_present"
    assert result["post_execution"]["status"] == "not_present"
    assert result["actual_changed_files"] == ["legacy.py"]
