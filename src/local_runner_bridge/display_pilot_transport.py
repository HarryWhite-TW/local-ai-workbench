"""Strict, fakeable transport validation for the Display Pilot candidate."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

PROTOCOL = "hgw.display_pilot.transport.v1"
SELECTOR_REPOSITORY = "HarryWhite-TW/human-governed-workflow"
SELECTOR_ISSUE = 1
TARGET_REPOSITORY = "HarryWhite-TW/human-approval-automation-gateway"
TRUSTED_ACTORS = ("HarryWhite-TW",)
_FENCE = re.compile(r"```json[ \t]+hgw\.display_pilot\.transport\.v1\r?\n(.*?)\r?\n```", re.S)
_SELECTOR_KEYS = {"protocol", "repository", "issue", "target_repository", "target_issue", "action", "request_id", "target_body_sha256"}

def body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

def _load(text: str) -> dict[str, Any]:
    def no_dupes(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    value = json.loads(text, object_pairs_hook=no_dupes)
    if type(value) is not dict: raise ValueError("machine_payload_not_object")
    return value

def parse_selector(*, body: str, creator: str, expected_body_sha256: str) -> dict[str, Any]:
    """Parse exactly one expressly labelled JSON fence; no prose is authority."""
    result = {"protocol": PROTOCOL, "result": "blocked", "reason": None, "selector": None}
    if creator not in TRUSTED_ACTORS: result["reason"] = "untrusted_selector_creator"; return result
    if body_sha256(body) != expected_body_sha256: result["reason"] = "selector_body_hash_mismatch"; return result
    blocks = _FENCE.findall(body)
    if len(blocks) != 1: result["reason"] = "selector_machine_payload_ambiguous_or_missing"; return result
    try: selector = _load(blocks[0])
    except (ValueError, json.JSONDecodeError): result["reason"] = "selector_machine_payload_malformed"; return result
    if set(selector) != _SELECTOR_KEYS: result["reason"] = "selector_unknown_or_missing_field"; return result
    if (selector.get("protocol") != PROTOCOL or selector.get("repository") != SELECTOR_REPOSITORY
        or selector.get("issue") != SELECTOR_ISSUE or selector.get("target_repository") != TARGET_REPOSITORY
        or selector.get("action") != "run-reviewbundle" or not isinstance(selector.get("target_issue"), int)
        or not isinstance(selector.get("request_id"), str) or not selector["request_id"]):
        result["reason"] = "selector_identity_or_action_mismatch"; return result
    result.update(result="success", reason=None, selector=selector)
    return result

def validate_target(*, selector: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    """Validate the dedicated target issue and its JSON Task Packet v1.1."""
    result = {"result": "blocked", "reason": None, "packet": None}
    if issue.get("repository") != TARGET_REPOSITORY or issue.get("number") != selector.get("target_issue"):
        result["reason"] = "target_identity_mismatch"; return result
    if issue.get("creator") not in TRUSTED_ACTORS: result["reason"] = "untrusted_target_creator"; return result
    if str(issue.get("state", "")).lower() != "open": result["reason"] = "target_issue_not_open"; return result
    body = issue.get("body")
    if not isinstance(body, str) or body_sha256(body) != selector.get("target_body_sha256"):
        result["reason"] = "target_body_hash_mismatch"; return result
    try: packet = _load(body)
    except (ValueError, json.JSONDecodeError): result["reason"] = "task_packet_malformed"; return result
    required = {"protocol", "packet_id", "logical_issue", "repository", "task_mode", "verification_command_policy", "verification_commands"}
    if set(packet) - required or not required <= set(packet): result["reason"] = "task_packet_unknown_or_missing_field"; return result
    if (packet["protocol"] != "lawb.local_runner.task_packet.v1.1" or packet["logical_issue"] != issue["number"]
        or packet["repository"] != TARGET_REPOSITORY or packet["task_mode"] != "PATCH_ONLY"
        or packet["verification_command_policy"] != "explicit_only" or not isinstance(packet["verification_commands"], list)
        or len(packet["verification_commands"]) > 2):
        result["reason"] = "task_packet_identity_or_policy_mismatch"; return result
    result.update(result="success", packet=packet)
    return result
