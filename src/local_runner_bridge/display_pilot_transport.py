"""Strict transport identity plus canonical Task Surface validation."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from local_runner_bridge.task_packet_validator import (
    TASK_PACKET_PROTOCOL_V1_1,
    validate_task_packet,
)
from local_runner_bridge.task_surface_resolver import extract_task_packet


PROTOCOL = "hgw.display_pilot.transport.v1"
SELECTOR_LABEL = PROTOCOL
SELECTOR_REPOSITORY = "HarryWhite-TW/human-governed-workflow"
SELECTOR_ISSUE = 1
TARGET_REPOSITORY = "HarryWhite-TW/human-approval-automation-gateway"
TRUSTED_ACTORS = ("HarryWhite-TW",)

_FENCE = re.compile(
    r"```json[ \t]+hgw\.display_pilot\.transport\.v1\r?\n"
    r"(.*?)\r?\n```",
    re.DOTALL,
)
_SELECTOR_KEYS = {
    "protocol",
    "repository",
    "issue",
    "target_repository",
    "target_issue",
    "action",
    "request_id",
    "target_body_sha256",
}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FULL_HEAD = re.compile(r"^[0-9a-fA-F]{40}$")
_PACKET_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def body_sha256(body: str) -> str:
    """Return the exact UTF-8 body digest used by the selector binding."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _load_json_object(text: str) -> dict[str, Any]:
    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    value = json.loads(text, object_pairs_hook=no_duplicate_keys)
    if type(value) is not dict:
        raise ValueError("machine_payload_not_object")
    return value


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "result": "blocked",
        "reason": reason,
        "selector": None,
    }


def _request_id_is_safe(value: Any) -> bool:
    if type(value) is not str or _REQUEST_ID.fullmatch(value) is None:
        return False
    if value.endswith((".", " ")):
        return False
    return value.split(".", 1)[0].upper() not in _WINDOWS_RESERVED_NAMES


def parse_selector(
    *,
    body: str,
    creator: str,
    expected_body_sha256: str,
) -> dict[str, Any]:
    """Parse one labelled identity fence; surrounding prose grants no authority."""
    if not isinstance(body, str) or body_sha256(body) != expected_body_sha256:
        return _blocked("selector_body_hash_mismatch")

    if SELECTOR_LABEL not in body:
        return {
            "protocol": PROTOCOL,
            "result": "idle",
            "reason": "selector_not_present",
            "selector": None,
        }
    matches = list(_FENCE.finditer(body))
    if len(matches) != 1:
        return _blocked("selector_machine_payload_ambiguous")
    match = matches[0]
    if SELECTOR_LABEL in body[: match.start()] + body[match.end() :]:
        return _blocked("selector_machine_payload_ambiguous")
    if creator not in TRUSTED_ACTORS:
        return _blocked("untrusted_selector_creator")
    try:
        selector = _load_json_object(match.group(1))
    except (ValueError, json.JSONDecodeError):
        return _blocked("selector_machine_payload_malformed")

    if set(selector) != _SELECTOR_KEYS:
        return _blocked("selector_unknown_or_missing_field")
    if (
        selector["protocol"] != PROTOCOL
        or selector["repository"] != SELECTOR_REPOSITORY
        or selector["issue"] != SELECTOR_ISSUE
        or selector["target_repository"] != TARGET_REPOSITORY
        or selector["action"] != "run-reviewbundle"
        or type(selector["target_issue"]) is not int
        or selector["target_issue"] <= 0
        or not _request_id_is_safe(selector["request_id"])
        or type(selector["target_body_sha256"]) is not str
        or _SHA256.fullmatch(selector["target_body_sha256"]) is None
    ):
        return _blocked("selector_identity_or_action_mismatch")

    return {
        "protocol": PROTOCOL,
        "result": "success",
        "reason": None,
        "selector": deepcopy(selector),
    }


def _task_packet_integrity_reason(packet_text: str) -> str | None:
    """Reject ambiguous line structures before canonical semantic validation."""
    contexts: dict[int, dict[str, Any]] = {
        0: {"kind": "mapping", "keys": set()}
    }
    for raw_line in packet_text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            return "malformed_task_packet_structure"

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2:
            return "malformed_task_packet_structure"
        stripped = raw_line.strip()
        for depth in tuple(contexts):
            if depth > indent:
                del contexts[depth]
        context = contexts.get(indent)
        if context is None:
            return "malformed_task_packet_structure"

        if stripped.startswith("-"):
            if not stripped.startswith("- ") or not stripped[2:].strip():
                return "malformed_task_packet_structure"
            if indent == 0 or context["kind"] not in {"unknown", "list"}:
                return "malformed_task_packet_structure"
            context["kind"] = "list"
            continue

        if context["kind"] == "list" or ":" not in stripped:
            return "malformed_task_packet_structure"
        key, value = stripped.split(":", 1)
        key = key.strip()
        if _PACKET_KEY.fullmatch(key) is None:
            return "malformed_task_packet_structure"
        if key in context["keys"]:
            return "duplicate_task_packet_field"
        context["kind"] = "mapping"
        context["keys"].add(key)
        if not value.strip():
            contexts[indent + 2] = {"kind": "unknown", "keys": set()}
    return None


def _target_blocked(reason: str, validation: dict | None = None) -> dict[str, Any]:
    return {
        "result": "blocked",
        "reason": reason,
        "validation_summary": deepcopy(validation),
        "runtime_contract": None,
    }


def validate_target(
    *,
    selector: dict[str, Any],
    issue: dict[str, Any],
) -> dict[str, Any]:
    """Validate the explicit target body as one canonical Task Packet v1.1."""
    if (
        issue.get("repository") != TARGET_REPOSITORY
        or issue.get("number") != selector.get("target_issue")
    ):
        return _target_blocked("target_identity_mismatch")
    if issue.get("creator") not in TRUSTED_ACTORS:
        return _target_blocked("untrusted_target_creator")
    if str(issue.get("state", "")).upper() != "OPEN":
        return _target_blocked("target_issue_not_open")

    body = issue.get("body")
    if (
        not isinstance(body, str)
        or body_sha256(body) != selector.get("target_body_sha256")
    ):
        return _target_blocked("target_body_hash_mismatch")

    extracted = extract_task_packet(body)
    if extracted.get("result") != "success":
        return _target_blocked(
            "canonical_task_surface_rejected",
            {key: value for key, value in extracted.items() if key != "packet_text"},
        )
    packet_text = extracted["packet_text"]
    integrity_reason = _task_packet_integrity_reason(packet_text)
    if integrity_reason is not None:
        return _target_blocked(integrity_reason)

    validated = validate_task_packet(
        packet_text,
        expected={"logical_issue": issue["number"]},
    )
    validation_summary = {
        key: deepcopy(value)
        for key, value in validated.items()
        if key != "packet_text"
    }
    if validated.get("result") != "success":
        return _target_blocked(
            "canonical_task_packet_rejected",
            validation_summary,
        )

    contract = validated.get("runtime_contract")
    if not isinstance(contract, dict):
        return _target_blocked(
            "task_packet_v1_1_runtime_contract_required",
            validation_summary,
        )
    commands = contract.get("verification_commands")
    allowed_files = contract.get("allowed_files")
    if (
        contract.get("protocol") != TASK_PACKET_PROTOCOL_V1_1
        or contract.get("logical_issue") != issue["number"]
        or contract.get("repository") != TARGET_REPOSITORY
        or contract.get("task_mode") != "PATCH_ONLY"
        or contract.get("verification_command_policy") != "explicit_only"
        or type(commands) is not list
        or not 1 <= len(commands) <= 2
        or type(allowed_files) is not list
        or not allowed_files
        or type(contract.get("max_allowed_files")) is not int
        or len(allowed_files) > contract["max_allowed_files"]
        or contract.get("scope_expansion_allowed") is not False
        or not isinstance(contract.get("branch"), str)
        or not contract["branch"]
        or not isinstance(contract.get("expected_head"), str)
        or _FULL_HEAD.fullmatch(contract["expected_head"]) is None
    ):
        return _target_blocked(
            "task_packet_identity_or_policy_mismatch",
            validation_summary,
        )

    return {
        "result": "success",
        "reason": None,
        "validation_summary": validation_summary,
        "runtime_contract": deepcopy(contract),
    }
