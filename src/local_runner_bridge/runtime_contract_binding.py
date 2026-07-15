"""Pure Task Packet v1.1 runtime-contract binding and enforcement."""

from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

try:
    from local_runner_bridge.task_packet_validator import validate_task_packet
    from local_runner_bridge.task_surface_resolver import (
        BEGIN_MARKER,
        END_MARKER,
        PROTOCOL_MARKER,
        extract_task_packet,
    )
except ModuleNotFoundError:  # Direct-file execution used by Runner v1.
    from task_packet_validator import validate_task_packet
    from task_surface_resolver import (
        BEGIN_MARKER,
        END_MARKER,
        PROTOCOL_MARKER,
        extract_task_packet,
    )


STATUS_PASSED = "passed"
STATUS_VIOLATION = "contract_violation"
STATUS_NOT_PRESENT = "not_present"
STATUS_NOT_RUN = "not_run"
FULL_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def _stage(status: str, reasons: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "reasons": list(reasons or [])}


def _binding(
    *,
    status: str,
    contract_present: bool,
    pre_status: str,
    post_status: str = STATUS_NOT_RUN,
    allowed_files: list[str] | None = None,
    actual_changed_files: list[str] | None = None,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    reason_values = list(dict.fromkeys(reasons or []))
    return {
        "status": status,
        "contract_present": contract_present,
        "pre_execution": _stage(pre_status, reason_values if pre_status == STATUS_VIOLATION else []),
        "post_execution": _stage(post_status),
        "allowed_files": list(allowed_files or []),
        "actual_changed_files": list(actual_changed_files or []),
        "reasons": reason_values,
    }


def normalize_repo_path(value: str) -> str:
    """Normalize a safe repository-relative path to slash form."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid_repository_relative_path")
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        re.match(r"^[A-Za-z]:", normalized)
        or ":" in normalized
        or any(character in normalized for character in "*?[]")
        or normalized.endswith("/")
    ):
        raise ValueError("invalid_repository_relative_path")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized in {"", "."}:
        raise ValueError("invalid_repository_relative_path")
    if path.parts and path.parts[0].casefold() == ".git":
        raise ValueError("invalid_repository_relative_path")
    return path.as_posix()


def _normalize_paths(values: Any, reason: str) -> tuple[list[str], list[str]]:
    if not isinstance(values, list):
        return [], [reason]
    normalized: list[str] = []
    errors: list[str] = []
    for value in values:
        try:
            normalized.append(normalize_repo_path(value))
        except ValueError:
            errors.append(reason)
    return sorted(set(normalized)), list(dict.fromkeys(errors))


def inspect_runtime_contract(
    surface_text: str,
    *,
    logical_issue: int | str,
    repository: str,
    branch: str,
    head: str,
) -> dict[str, Any]:
    """Extract a packet and enforce its pre-execution identity when v1.1 is present."""
    if not isinstance(surface_text, str):
        return _binding(
            status=STATUS_VIOLATION,
            contract_present=False,
            pre_status=STATUS_VIOLATION,
            reasons=["task_surface_not_string"],
        )

    markers_present = any(
        marker in surface_text for marker in (PROTOCOL_MARKER, BEGIN_MARKER, END_MARKER)
    )
    if not markers_present:
        return _binding(
            status=STATUS_NOT_PRESENT,
            contract_present=False,
            pre_status=STATUS_NOT_PRESENT,
        )

    extracted = extract_task_packet(surface_text)
    if extracted["result"] != "success":
        return _binding(
            status=STATUS_VIOLATION,
            contract_present=False,
            pre_status=STATUS_VIOLATION,
            reasons=list(extracted.get("errors", ["task_packet_extraction_failed"])),
        )

    validated = validate_task_packet(extracted["packet_text"])
    if validated["result"] != "success":
        return _binding(
            status=STATUS_VIOLATION,
            contract_present=False,
            pre_status=STATUS_VIOLATION,
            reasons=list(validated.get("errors", ["task_packet_validation_failed"])),
        )

    contract = validated.get("runtime_contract")
    if contract is None:
        return _binding(
            status=STATUS_NOT_PRESENT,
            contract_present=False,
            pre_status=STATUS_NOT_PRESENT,
        )

    allowed_files, path_errors = _normalize_paths(
        contract.get("allowed_files"), "invalid_allowed_file"
    )
    reasons = list(path_errors)
    if str(contract.get("logical_issue")) != str(logical_issue):
        reasons.append("logical_issue_mismatch")
    if contract.get("repository") != repository:
        reasons.append("repository_mismatch")
    if contract.get("branch") != branch:
        reasons.append("branch_mismatch")
    expected_head = contract.get("expected_head")
    if not isinstance(head, str) or not FULL_SHA_PATTERN.fullmatch(head):
        reasons.append("current_head_not_full_sha")
    if not isinstance(expected_head, str) or not FULL_SHA_PATTERN.fullmatch(expected_head):
        reasons.append("expected_head_not_full_sha")
    elif expected_head.lower() != head.lower():
        reasons.append("expected_head_mismatch")

    result = _binding(
        status=STATUS_VIOLATION if reasons else STATUS_PASSED,
        contract_present=True,
        pre_status=STATUS_VIOLATION if reasons else STATUS_PASSED,
        allowed_files=allowed_files,
        reasons=reasons,
    )
    result["runtime_contract"] = deepcopy(contract)
    result["runtime_contract"]["allowed_files"] = allowed_files
    return result


def enforce_changed_files(
    binding: dict[str, Any], actual_changed_files: list[str]
) -> dict[str, Any]:
    """Apply allowed-files and maximum-count rules after execution."""
    result = deepcopy(binding)
    actual_files, path_errors = _normalize_paths(
        actual_changed_files, "invalid_actual_changed_file"
    )
    result["actual_changed_files"] = actual_files

    if result.get("status") == STATUS_NOT_PRESENT:
        result["post_execution"] = _stage(STATUS_NOT_PRESENT)
        return result
    if result.get("pre_execution", {}).get("status") != STATUS_PASSED:
        return result

    reasons = list(path_errors)
    allowed = set(result.get("allowed_files", []))
    if any(path not in allowed for path in actual_files):
        reasons.append("changed_file_outside_allowed_files")

    contract = result.get("runtime_contract", {})
    maximum = contract.get("max_allowed_files")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
        reasons.append("invalid_max_allowed_files")
    elif len(actual_files) > maximum:
        reasons.append("changed_file_count_exceeds_max_allowed_files")

    reasons = list(dict.fromkeys(reasons))
    result["post_execution"] = _stage(
        STATUS_VIOLATION if reasons else STATUS_PASSED, reasons
    )
    result["reasons"] = list(dict.fromkeys(result.get("reasons", []) + reasons))
    result["status"] = STATUS_VIOLATION if result["reasons"] else STATUS_PASSED
    return result


def _main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"inspect", "post"}:
        raise ValueError("expected inspect or post action")
    payload = json.load(sys.stdin)
    if args[0] == "inspect":
        result = inspect_runtime_contract(
            payload.get("surface_text"),
            logical_issue=payload.get("logical_issue"),
            repository=payload.get("repository"),
            branch=payload.get("branch"),
            head=payload.get("head"),
        )
    else:
        result = enforce_changed_files(
            payload.get("runtime_contract_binding", {}),
            payload.get("actual_changed_files", []),
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
