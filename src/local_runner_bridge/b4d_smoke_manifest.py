"""Local-only B4-D smoke manifest validation and approval preview."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

MANIFEST_PROTOCOL = "lawb.b4d_smoke_manifest.v1"
VALIDATION_PROTOCOL = "lawb.b4d_smoke_manifest_validation.v1"
PREVIEW_PROTOCOL = "lawb.b4d_smoke_approval_preview.v1"

REPOSITORY = "HarryWhite-TW/local-ai-workbench"
INBOX_ISSUE = 147
BRANCH = "master"
ACTION = "run-reviewbundle"
REQUESTED_BY = "chatgpt"
B2_COMMAND = (
    r".\.venv-course\Scripts\python.exe "
    r"-m local_runner_bridge.bridge_operator_b2_cli --repo-root ."
)

TOP_LEVEL_FIELDS = (
    "protocol",
    "repo",
    "inbox_issue",
    "target_issue",
    "branch",
    "head",
    "action",
    "requested_by",
    "expires",
    "inbox_request_id",
    "dispatch_request_id",
    "allowed_paths",
    "markers",
    "approvals",
    "safety",
)
MARKER_FIELDS = ("dispatch", "inbox")
APPROVAL_FIELDS = ("approval_a", "approval_b")
SAFETY_FIELDS = (
    "foreground_only",
    "single_run",
    "no_retry",
    "no_b3_loop",
    "no_background",
    "no_broad_scan",
    "no_target_inference",
    "no_stage",
    "no_commit",
    "no_push",
    "no_issue_close",
    "no_label",
    "no_pr",
    "no_merge",
    "no_automatic_cleanup",
    "no_approval_chaining",
)
EXECUTION_CHAIN = (
    "bridge_operator_b2_once",
    "dispatcher_poll_once",
    "runner_v1_review_bundle_once",
    "codex_once",
)
FORBIDDEN_ACTIONS = (
    "retry",
    "loop",
    "background",
    "broad_issue_scan",
    "inferred_target",
    "stage",
    "commit",
    "push",
    "cleanup",
    "issue_close",
    "label",
    "pr",
    "merge",
    "approval_chaining",
    "another_request",
)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_EXPIRY_RE = re.compile(r"^\d{8}T\d{6}Z$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_WILDCARD_RE = re.compile(r"[*?\[\]]")
_RESERVED_DEVICE_RE = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.IGNORECASE)


def canonical_dispatch_marker(manifest: dict[str, Any]) -> str:
    return (
        "CHATGPT-DISPATCH protocol=lawb.dispatch.v1 "
        f"action={ACTION} issue={manifest['target_issue']} repo={REPOSITORY} "
        f"branch={BRANCH} head={manifest['head']} expires={manifest['expires']} "
        f"requested_by={REQUESTED_BY} request_id={manifest['dispatch_request_id']}"
    )


def canonical_inbox_marker(manifest: dict[str, Any]) -> str:
    return (
        "BRIDGE-INBOX-REQUEST protocol=lawb.bridge_inbox_request.v1 "
        f"request_id={manifest['inbox_request_id']} repo={REPOSITORY} "
        f"target_issue={manifest['target_issue']} "
        f"target_dispatch_request_id={manifest['dispatch_request_id']} "
        f"branch={BRANCH} head={manifest['head']} expires={manifest['expires']} "
        f"action={ACTION} requested_by={REQUESTED_BY}"
    )


def validate_manifest(
    manifest: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate one in-memory manifest without I/O or side effects."""
    errors: list[dict[str, str]] = []
    validation_time = _as_utc(now or datetime.now(timezone.utc))

    if not isinstance(manifest, dict):
        _error(errors, "manifest_not_object", "$", "Manifest must be one JSON object.")
        return _invalid(errors)

    _closed_keys(errors, manifest, TOP_LEVEL_FIELDS, "$")
    if errors:
        return _invalid(errors)

    _fixed_value(errors, manifest, "protocol", MANIFEST_PROTOCOL)
    _fixed_value(errors, manifest, "repo", REPOSITORY)
    _fixed_value(errors, manifest, "inbox_issue", INBOX_ISSUE)
    _fixed_value(errors, manifest, "branch", BRANCH)
    _fixed_value(errors, manifest, "action", ACTION)
    _fixed_value(errors, manifest, "requested_by", REQUESTED_BY)

    target_issue = manifest["target_issue"]
    if not _is_int(target_issue) or target_issue <= 0:
        _error(errors, "invalid_target_issue", "target_issue", "target_issue must be a positive integer.")
    elif target_issue == INBOX_ISSUE:
        _error(errors, "target_equals_inbox", "target_issue", "target_issue must differ from inbox_issue.")

    head = manifest["head"]
    if not isinstance(head, str) or _HEAD_RE.fullmatch(head) is None:
        _error(errors, "invalid_head", "head", "head must be 40 lowercase hexadecimal characters.")

    expires = _parse_expiry(manifest["expires"])
    if expires is None:
        _error(errors, "invalid_expiry", "expires", "expires must use valid UTC basic YYYYMMDDTHHMMSSZ format.")
    elif expires <= validation_time:
        _error(errors, "expired_manifest", "expires", "expires must be later than validation time.")

    for field in ("inbox_request_id", "dispatch_request_id"):
        value = manifest[field]
        if not isinstance(value, str) or not value.isascii() or _REQUEST_ID_RE.fullmatch(value) is None:
            _error(
                errors,
                "invalid_request_id",
                field,
                "Request ID must be an ASCII ID matching current repository constraints.",
            )
    if (
        isinstance(manifest["inbox_request_id"], str)
        and isinstance(manifest["dispatch_request_id"], str)
        and manifest["inbox_request_id"] == manifest["dispatch_request_id"]
    ):
        _error(errors, "request_ids_not_distinct", "dispatch_request_id", "Request IDs must be different.")

    normalized_paths = _validate_allowed_paths(errors, manifest["allowed_paths"])
    expected_dispatch = canonical_dispatch_marker(manifest)
    expected_inbox = canonical_inbox_marker(manifest)
    _validate_markers(errors, manifest["markers"], expected_dispatch, expected_inbox)
    _validate_approvals(
        errors,
        manifest["approvals"],
        target_issue=target_issue,
        allowed_paths=normalized_paths,
        dispatch_marker=expected_dispatch,
        inbox_marker=expected_inbox,
    )
    _validate_safety(errors, manifest["safety"])

    if errors:
        return _invalid(errors)

    canonical = {
        "protocol": MANIFEST_PROTOCOL,
        "repo": REPOSITORY,
        "inbox_issue": INBOX_ISSUE,
        "target_issue": target_issue,
        "branch": BRANCH,
        "head": head,
        "action": ACTION,
        "requested_by": REQUESTED_BY,
        "expires": manifest["expires"],
        "inbox_request_id": manifest["inbox_request_id"],
        "dispatch_request_id": manifest["dispatch_request_id"],
        "allowed_paths": normalized_paths,
        "markers": {"dispatch": expected_dispatch, "inbox": expected_inbox},
        "approvals": _canonical_approvals(
            target_issue=target_issue,
            allowed_paths=normalized_paths,
            dispatch_marker=expected_dispatch,
            inbox_marker=expected_inbox,
        ),
        "safety": {field: True for field in SAFETY_FIELDS},
    }
    return {
        "protocol": VALIDATION_PROTOCOL,
        "valid": True,
        "errors": [],
        "warnings": [],
        "canonical_manifest": canonical,
        "preview": _build_preview(canonical),
    }


def malformed_input_result(code: str, message: str) -> dict[str, Any]:
    return _invalid([{"code": code, "field": "$", "message": message}])


def _validate_allowed_paths(errors: list[dict[str, str]], value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        _error(errors, "invalid_allowed_paths", "allowed_paths", "allowed_paths must be a non-empty array.")
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for index, path in enumerate(value):
        field = f"allowed_paths[{index}]"
        if not isinstance(path, str) or not path:
            _error(errors, "invalid_allowed_path", field, "Allowed path must be a non-empty string.")
            continue
        if path != path.strip():
            _error(errors, "path_outer_whitespace", field, "Allowed path must not have leading or trailing whitespace.")
            continue
        if "\x00" in path:
            _error(errors, "path_nul_forbidden", field, "Allowed path must not contain NUL.")
            continue
        if any(ord(character) < 32 or ord(character) == 127 for character in path):
            _error(errors, "path_control_character", field, "Allowed path must not contain ASCII control characters.")
            continue
        if _DRIVE_RE.match(path) or path.startswith(("/", "\\")):
            _error(errors, "absolute_allowed_path", field, "Allowed path must be repository-relative.")
            continue
        if ":" in path:
            _error(errors, "path_colon_forbidden", field, "Allowed path must not contain colon characters.")
            continue
        if _WILDCARD_RE.search(path):
            _error(errors, "wildcard_allowed_path", field, "Allowed path must not contain wildcards.")
            continue
        candidate = path.replace("\\", "/")
        segments = candidate.split("/")
        if any(segment == "" for segment in segments):
            _error(errors, "empty_path_segment", field, "Allowed path must not contain empty segments.")
            continue
        if any(segment in {".", ".."} for segment in segments):
            _error(errors, "unsafe_path_segment", field, "Allowed path must not contain . or .. segments.")
            continue
        if any(segment.endswith((" ", ".")) for segment in segments):
            _error(
                errors,
                "path_segment_trailing_space_or_period",
                field,
                "Allowed path segments must not end in a space or period.",
            )
            continue
        if any(segment != segment.strip() for segment in segments):
            _error(
                errors,
                "path_segment_whitespace",
                field,
                "Allowed path segments must not have leading or trailing whitespace.",
            )
            continue
        if any(segment.casefold() == ".git" for segment in segments):
            _error(errors, "git_path_forbidden", field, "Allowed path must not include .git.")
            continue
        if any(_RESERVED_DEVICE_RE.match(segment) for segment in segments):
            _error(
                errors,
                "windows_reserved_device",
                field,
                "Allowed path must not contain a Windows reserved device basename.",
            )
            continue
        comparison_key = candidate.casefold()
        if comparison_key in seen:
            _error(errors, "duplicate_allowed_path", field, "Allowed paths must be unique after normalization.")
            continue
        seen.add(comparison_key)
        normalized.append(candidate)
    return normalized


def _validate_markers(
    errors: list[dict[str, str]],
    value: Any,
    dispatch_marker: str,
    inbox_marker: str,
) -> None:
    if not isinstance(value, dict):
        _error(errors, "invalid_markers", "markers", "markers must be an object.")
        return
    _closed_keys(errors, value, MARKER_FIELDS, "markers")
    if set(value) != set(MARKER_FIELDS):
        return
    if value["dispatch"] != dispatch_marker:
        _error(errors, "dispatch_marker_mismatch", "markers.dispatch", "Dispatch marker must exactly match canonical form.")
    if value["inbox"] != inbox_marker:
        _error(errors, "inbox_marker_mismatch", "markers.inbox", "Inbox marker must exactly match canonical form.")


def _validate_approvals(
    errors: list[dict[str, str]],
    value: Any,
    *,
    target_issue: Any,
    allowed_paths: list[str],
    dispatch_marker: str,
    inbox_marker: str,
) -> None:
    if not isinstance(value, dict):
        _error(errors, "invalid_approvals", "approvals", "approvals must be an object.")
        return
    _closed_keys(errors, value, APPROVAL_FIELDS, "approvals")
    if set(value) != set(APPROVAL_FIELDS):
        return
    expected = _canonical_approvals(
        target_issue=target_issue,
        allowed_paths=allowed_paths,
        dispatch_marker=dispatch_marker,
        inbox_marker=inbox_marker,
    )
    _exact_structure(errors, value["approval_a"], expected["approval_a"], "approvals.approval_a")
    _exact_structure(errors, value["approval_b"], expected["approval_b"], "approvals.approval_b")


def _validate_safety(errors: list[dict[str, str]], value: Any) -> None:
    if not isinstance(value, dict):
        _error(errors, "invalid_safety", "safety", "safety must be an object.")
        return
    _closed_keys(errors, value, SAFETY_FIELDS, "safety")
    for field in SAFETY_FIELDS:
        if field in value and value[field] is not True:
            _error(errors, "safety_not_true", f"safety.{field}", "Every safety field must be boolean true.")


def _canonical_approvals(
    *,
    target_issue: Any,
    allowed_paths: list[str],
    dispatch_marker: str,
    inbox_marker: str,
) -> dict[str, Any]:
    return {
        "approval_a": {
            "github_comment_writes": [
                {"kind": "chatgpt_dispatch", "issue": target_issue, "body": dispatch_marker},
                {"kind": "bridge_inbox_request", "issue": INBOX_ISSUE, "body": inbox_marker},
            ]
        },
        "approval_b": {
            "foreground_b2_execution": "once",
            "dispatcher_poll_once": "once",
            "runner_v1_review_bundle": "once",
            "codex_execution": "once",
            "local_unstaged_changes": {
                "unstaged_only": True,
                "limited_to_allowed_paths": True,
            },
            "allowed_paths": list(allowed_paths),
            "expected_result_writes": [
                {"kind": "runner_review_bundle", "issue": target_issue},
                {"kind": "dispatcher_lawbrunner_result", "issue": target_issue},
            ],
        },
    }


def _build_preview(canonical: dict[str, Any]) -> dict[str, Any]:
    compact = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(compact.encode("utf-8")).hexdigest()
    approvals = canonical["approvals"]
    return {
        "protocol": PREVIEW_PROTOCOL,
        "manifest_sha256": digest,
        "binding": {
            field: canonical[field]
            for field in (
                "repo",
                "inbox_issue",
                "target_issue",
                "branch",
                "head",
                "action",
                "requested_by",
                "expires",
                "inbox_request_id",
                "dispatch_request_id",
            )
        },
        "approval_a": {
            "github_comment_writes": approvals["approval_a"]["github_comment_writes"],
        },
        "approval_b": {
            "command": B2_COMMAND,
            "execution_chain": list(EXECUTION_CHAIN),
            "allowed_paths": canonical["allowed_paths"],
            "expected_result_writes": approvals["approval_b"]["expected_result_writes"],
        },
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "next_required_action": "human_review_approval_a",
    }


def _closed_keys(
    errors: list[dict[str, str]],
    value: dict[str, Any],
    expected: tuple[str, ...],
    field: str,
) -> None:
    missing = [key for key in expected if key not in value]
    unknown = sorted(set(value) - set(expected))
    for key in missing:
        _error(errors, "missing_field", f"{field}.{key}" if field != "$" else key, "Required field is missing.")
    for key in unknown:
        _error(errors, "unknown_field", f"{field}.{key}" if field != "$" else key, "Unknown field is not allowed.")


def _exact_structure(
    errors: list[dict[str, str]],
    actual: Any,
    expected: Any,
    field: str,
) -> None:
    if json.dumps(actual, sort_keys=True, separators=(",", ":")) == json.dumps(
        expected,
        sort_keys=True,
        separators=(",", ":"),
    ):
        return
    _error(errors, "approval_structure_mismatch", field, "Approval structure must exactly match bounded authority.")


def _fixed_value(
    errors: list[dict[str, str]],
    manifest: dict[str, Any],
    field: str,
    expected: Any,
) -> None:
    if manifest[field] != expected or type(manifest[field]) is not type(expected):
        _error(errors, "fixed_value_mismatch", field, f"{field} must equal {expected!r}.")


def _parse_expiry(value: Any) -> datetime | None:
    if not isinstance(value, str) or _EXPIRY_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _error(errors: list[dict[str, str]], code: str, field: str, message: str) -> None:
    errors.append({"code": code, "field": field, "message": message})


def _invalid(errors: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "protocol": VALIDATION_PROTOCOL,
        "valid": False,
        "errors": errors,
        "warnings": [],
        "canonical_manifest": None,
        "preview": None,
    }
