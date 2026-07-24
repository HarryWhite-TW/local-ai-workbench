import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge.display_pilot_transport import (
    PROTOCOL,
    SELECTOR_ISSUE,
    SELECTOR_REPOSITORY,
    TARGET_REPOSITORY,
    body_sha256,
    parse_selector,
    validate_target,
)


HEAD = "a" * 40


def packet(**replacements):
    values = {
        "logical_issue": "9",
        "repository": TARGET_REPOSITORY,
        "branch": "feature/display-pilot",
        "expected_head": HEAD,
        "allowed_files": "  - src/example.py",
        "extra": "",
    }
    values.update(replacements)
    return f"""LOCAL-RUNNER-TASK-PACKET-V1
BEGIN_TASK_PACKET
protocol: lawb.local_runner.task_packet.v1.1
packet_id: dp4-br-9
logical_issue: {values["logical_issue"]}
phase: display_pilot_foreground
action_type: implementation
risk_level: medium
repository: {values["repository"]}
branch: {values["branch"]}
expected_head: {values["expected_head"]}
allowed_files:
{values["allowed_files"]}
forbidden_operations:
  - commit
  - push
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
max_allowed_files: 1
context_scope:
  - src/example.py
repair_attempt_limit: 1
verification_command_policy: explicit_only
verification_commands:
  - python -m pytest -q tests/test_example.py -p no:cacheprovider
scope_expansion_allowed: false
{values["extra"]}END_TASK_PACKET
"""


def selector_body(target_body, **overrides):
    value = {
        "protocol": PROTOCOL,
        "repository": SELECTOR_REPOSITORY,
        "issue": SELECTOR_ISSUE,
        "target_repository": TARGET_REPOSITORY,
        "target_issue": 9,
        "action": "run-reviewbundle",
        "request_id": "req-9",
        "target_body_sha256": body_sha256(target_body),
    }
    value.update(overrides)
    return (
        "Transport prose grants no authority.\n"
        "```json hgw.display_pilot.transport.v1\n"
        + json.dumps(value)
        + "\n```\n"
    )


def parsed_selector(target_body=None, **overrides):
    target_body = target_body or packet()
    body = selector_body(target_body, **overrides)
    result = parse_selector(
        body=body,
        creator="HarryWhite-TW",
        expected_body_sha256=body_sha256(body),
    )
    assert result["result"] == "success"
    return result["selector"]


def issue(body=None, **overrides):
    body = body or packet()
    value = {
        "repository": TARGET_REPOSITORY,
        "number": 9,
        "creator": "HarryWhite-TW",
        "state": "OPEN",
        "body": body,
    }
    value.update(overrides)
    return value


def test_valid_selector_and_canonical_task_surface_succeeds():
    body = packet()
    result = validate_target(selector=parsed_selector(body), issue=issue(body))

    assert result["result"] == "success"
    assert result["runtime_contract"] == {
        "protocol": "lawb.local_runner.task_packet.v1.1",
        "packet_id": "dp4-br-9",
        "logical_issue": 9,
        "repository": TARGET_REPOSITORY,
        "branch": "feature/display-pilot",
        "expected_head": HEAD,
        "task_mode": "PATCH_ONLY",
        "objective": "Implement one bounded change.",
        "allowed_files": ["src/example.py"],
        "max_allowed_files": 1,
        "verification_command_policy": "explicit_only",
        "verification_commands": [
            "python -m pytest -q tests/test_example.py -p no:cacheprovider"
        ],
        "scope_expansion_allowed": False,
    }


def test_mini_json_target_packet_is_rejected():
    body = json.dumps(
        {
            "protocol": "lawb.local_runner.task_packet.v1.1",
            "logical_issue": 9,
        }
    )
    result = validate_target(selector=parsed_selector(body), issue=issue(body))
    assert result["reason"] == "canonical_task_surface_rejected"


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (
            packet().replace(
                "branch: feature/display-pilot\n",
                "branch: feature/display-pilot\nbranch: duplicate\n",
            ),
            "duplicate_task_packet_field",
        ),
        (
            packet().replace(
                "approval:\n  required: false\n",
                "approval:\n  required: false\n  required: true\n",
            ),
            "duplicate_task_packet_field",
        ),
        (
            packet().replace(
                "objective: Implement one bounded change.\n",
                "objective: Implement one bounded change.\nignored malformed line\n",
            ),
            "malformed_task_packet_structure",
        ),
        (
            packet().replace("  - src/example.py\n", "   - src/example.py\n"),
            "malformed_task_packet_structure",
        ),
        (
            packet(extra="unknown_authority: true\n"),
            "canonical_task_packet_rejected",
        ),
        (
            packet().replace("END_TASK_PACKET\n", ""),
            "canonical_task_surface_rejected",
        ),
    ],
)
def test_malformed_duplicate_and_unknown_packet_data_fail_closed(body, reason):
    result = validate_target(selector=parsed_selector(body), issue=issue(body))
    assert result["result"] == "blocked"
    assert result["reason"] == reason


@pytest.mark.parametrize(
    "needle",
    [
        "branch: feature/display-pilot\n",
        f"expected_head: {HEAD}\n",
        "allowed_files:\n  - src/example.py\n",
    ],
)
def test_missing_branch_head_or_allowed_files_fails_closed(needle):
    body = packet().replace(needle, "")
    result = validate_target(selector=parsed_selector(body), issue=issue(body))
    assert result["result"] == "blocked"


def test_selector_hash_and_creator_mismatch_fail_closed():
    body = selector_body(packet())
    assert (
        parse_selector(
            body=body,
            creator="HarryWhite-TW",
            expected_body_sha256="0" * 64,
        )["reason"]
        == "selector_body_hash_mismatch"
    )
    assert (
        parse_selector(
            body=body,
            creator="outsider",
            expected_body_sha256=body_sha256(body),
        )["reason"]
        == "untrusted_selector_creator"
    )


def test_no_selector_label_is_idle():
    no_selector = "This fixed Issue does not currently contain a DP4-B selector."
    idle = parse_selector(
        body=no_selector,
        creator="HarryWhite-TW",
        expected_body_sha256=body_sha256(no_selector),
    )
    assert idle == {
        "protocol": PROTOCOL,
        "result": "idle",
        "reason": "selector_not_present",
        "selector": None,
    }


@pytest.mark.parametrize(
    "body",
    [
        "```json hgw.display_pilot.transport.v1\n",
        "```json hgw.display_pilot.transport.v1\n{}\n``x",
        "```json hgw.display_pilot.transport.v1\n{\"protocol\":",
        "hgw.display_pilot.transport.v1",
        selector_body(packet()) + "```json hgw.display_pilot.transport.v1\n",
    ],
)
def test_incomplete_or_stray_labelled_selector_blocks_without_side_effects(
    body,
    tmp_path,
):
    before = list(tmp_path.iterdir())
    result = parse_selector(
        body=body,
        creator="HarryWhite-TW",
        expected_body_sha256=body_sha256(body),
    )

    assert result["result"] == "blocked"
    assert result["reason"] == "selector_machine_payload_ambiguous"
    assert list(tmp_path.iterdir()) == before


def test_multiple_complete_or_one_malformed_selector_blocks():
    valid = selector_body(packet())
    multiple = valid + valid
    assert (
        parse_selector(
            body=multiple,
            creator="HarryWhite-TW",
            expected_body_sha256=body_sha256(multiple),
        )["reason"]
        == "selector_machine_payload_ambiguous"
    )

    malformed = "```json hgw.display_pilot.transport.v1\n{not-json}\n```"
    assert (
        parse_selector(
            body=malformed,
            creator="HarryWhite-TW",
            expected_body_sha256=body_sha256(malformed),
        )["reason"]
        == "selector_machine_payload_malformed"
    )


def test_target_hash_creator_and_closed_state_fail_closed():
    body = packet()
    selector = parsed_selector(body)
    assert (
        validate_target(selector=selector, issue=issue(body + "x"))[
            "reason"
        ]
        == "target_body_hash_mismatch"
    )
    assert (
        validate_target(selector=selector, issue=issue(body, creator="outsider"))[
            "reason"
        ]
        == "untrusted_target_creator"
    )
    assert (
        validate_target(selector=selector, issue=issue(body, state="CLOSED"))[
            "reason"
        ]
        == "target_issue_not_open"
    )


@pytest.mark.parametrize(
    "body",
    [
        packet(logical_issue="10"),
        packet(repository="Other/repository"),
    ],
)
def test_wrong_logical_issue_or_repository_fails_closed(body):
    result = validate_target(selector=parsed_selector(body), issue=issue(body))
    assert result["result"] == "blocked"


@pytest.mark.parametrize(
    "request_id",
    [
        "bad/name",
        r"bad\name",
        "bad:name",
        "bad*name",
        'bad"name',
        "bad<name",
        "bad>name",
        "bad|name",
        "trailing.",
        "trailing ",
        "CON",
        "nul.txt",
        "COM1.log",
    ],
)
def test_windows_unsafe_request_ids_are_rejected(request_id):
    target = packet()
    body = selector_body(target, request_id=request_id)
    result = parse_selector(
        body=body,
        creator="HarryWhite-TW",
        expected_body_sha256=body_sha256(body),
    )
    assert result["result"] == "blocked"
    assert result["reason"] == "selector_identity_or_action_mismatch"
