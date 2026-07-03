"""Standalone read-only durable-evidence reconciliation resolver."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

RESULT_MARKER = "LAWBRUNNER-RESULT"
RESULT_PROTOCOL = "lawb.runner_result.v1"
SUPPORTED_SURFACE = "issue_comment"
SUCCESS_RESULT = "success"


class ReconciliationDecision(str, Enum):
    COMPLETED = "COMPLETED"
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class ReconciliationReason(str, Enum):
    EXACTLY_ONE_TRUSTED_MATCH = "EXACTLY_ONE_TRUSTED_MATCH"
    ZERO_MATCHING_COMPLETIONS = "ZERO_MATCHING_COMPLETIONS"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PAGINATION_INCOMPLETE = "PAGINATION_INCOMPLETE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    MALFORMED_EVIDENCE = "MALFORMED_EVIDENCE"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    UNTRUSTED_AUTHOR = "UNTRUSTED_AUTHOR"
    REPOSITORY_MISMATCH = "REPOSITORY_MISMATCH"
    ISSUE_MISMATCH = "ISSUE_MISMATCH"
    SURFACE_MISMATCH = "SURFACE_MISMATCH"
    ACTION_MISMATCH = "ACTION_MISMATCH"
    BRANCH_MISMATCH = "BRANCH_MISMATCH"
    HEAD_MISMATCH = "HEAD_MISMATCH"
    MULTIPLE_MATCHING_COMPLETIONS = "MULTIPLE_MATCHING_COMPLETIONS"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NON_SUCCESS_RESULT = "NON_SUCCESS_RESULT"


class ProviderStatus(str, Enum):
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INCOMPLETE = "INCOMPLETE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RequestIdentity:
    repository: str
    issue_number: int
    surface: str
    request_id: str
    action: str
    branch: str
    head: str
    expected_result_protocol: str = RESULT_PROTOCOL


@dataclass(frozen=True)
class EvidenceComment:
    evidence_id: str
    repository: str
    issue_number: int
    surface: str
    author: str
    body: str


@dataclass(frozen=True)
class EvidenceReadResult:
    status: ProviderStatus
    comments: tuple[EvidenceComment, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationResult:
    decision: ReconciliationDecision
    reason: ReconciliationReason
    matched_evidence_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]


class DurableEvidenceProvider(Protocol):
    def read_result_comments(
        self,
        request: RequestIdentity,
    ) -> EvidenceReadResult:
        ...


@dataclass(frozen=True)
class _ParsedCandidate:
    evidence_id: str
    author: str
    repository: str
    issue_number: int
    surface: str
    request_id: str
    action: str
    branch: str
    head: str
    result_value: Any


def resolve_durable_completion(
    request: RequestIdentity,
    provider: DurableEvidenceProvider,
    trusted_authors: frozenset[str],
) -> ReconciliationResult:
    if request.surface != SUPPORTED_SURFACE:
        return _result(
            ReconciliationDecision.BLOCKED,
            ReconciliationReason.SURFACE_MISMATCH,
            diagnostics=(f"request_surface_mismatch:{request.surface}",),
        )
    if request.expected_result_protocol != RESULT_PROTOCOL:
        return _result(
            ReconciliationDecision.BLOCKED,
            ReconciliationReason.UNSUPPORTED_PROTOCOL,
            diagnostics=(f"request_protocol_unsupported:{request.expected_result_protocol}",),
        )

    try:
        read_result = provider.read_result_comments(request)
    except Exception as error:
        return _result(
            ReconciliationDecision.ERROR,
            ReconciliationReason.PROVIDER_ERROR,
            diagnostics=(f"provider_exception:{type(error).__name__}",),
        )

    provider_result = _provider_status_result(read_result)
    if provider_result is not None:
        return provider_result

    diagnostics = set(_sorted_strings(read_result.diagnostics))
    parsed_candidates: list[_ParsedCandidate] = []
    malformed_ids: list[str] = []
    unsupported_ids: list[str] = []
    outer_repository_mismatch_ids: list[str] = []
    outer_issue_mismatch_ids: list[str] = []
    outer_surface_mismatch_ids: list[str] = []
    for comment in read_result.comments:
        parsed = _parse_comment(comment, request.expected_result_protocol)
        diagnostics.update(parsed["diagnostics"])
        if comment.repository != request.repository:
            outer_repository_mismatch_ids.append(comment.evidence_id)
            diagnostics.add(f"outer_repository_mismatch:{comment.evidence_id}")
        if comment.issue_number != request.issue_number:
            outer_issue_mismatch_ids.append(comment.evidence_id)
            diagnostics.add(f"outer_issue_mismatch:{comment.evidence_id}")
        if comment.surface != request.surface:
            outer_surface_mismatch_ids.append(comment.evidence_id)
            diagnostics.add(f"outer_surface_mismatch:{comment.evidence_id}")
        kind = parsed["kind"]
        if kind == "ordinary":
            continue
        if kind == "malformed":
            malformed_ids.append(comment.evidence_id)
            continue
        if kind == "unsupported":
            unsupported_ids.append(comment.evidence_id)
            continue
        parsed_candidates.append(parsed["candidate"])

    precedence_results = (
        (malformed_ids, ReconciliationReason.MALFORMED_EVIDENCE),
        (unsupported_ids, ReconciliationReason.UNSUPPORTED_PROTOCOL),
        (outer_repository_mismatch_ids, ReconciliationReason.REPOSITORY_MISMATCH),
        (outer_issue_mismatch_ids, ReconciliationReason.ISSUE_MISMATCH),
        (outer_surface_mismatch_ids, ReconciliationReason.SURFACE_MISMATCH),
    )
    for matched_ids, reason in precedence_results:
        if matched_ids:
            return _result(
                ReconciliationDecision.BLOCKED,
                reason,
                matched_ids=tuple(matched_ids),
                diagnostics=tuple(diagnostics),
            )

    same_request_candidates = [
        candidate for candidate in parsed_candidates if candidate.request_id == request.request_id
    ]
    if not same_request_candidates:
        return _result(
            ReconciliationDecision.NOT_FOUND,
            ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
            diagnostics=tuple(diagnostics),
        )

    untrusted = [
        candidate
        for candidate in same_request_candidates
        if candidate.author not in trusted_authors
    ]
    if untrusted:
        return _result(
            ReconciliationDecision.BLOCKED,
            ReconciliationReason.UNTRUSTED_AUTHOR,
            matched_ids=_candidate_ids(untrusted),
            diagnostics=tuple(diagnostics),
        )

    mismatch_result = _identity_mismatch_result(request, same_request_candidates, diagnostics)
    if mismatch_result is not None:
        return mismatch_result

    successes = [
        candidate
        for candidate in same_request_candidates
        if candidate.result_value == SUCCESS_RESULT
    ]
    non_successes = [
        candidate
        for candidate in same_request_candidates
        if candidate.result_value != SUCCESS_RESULT
    ]

    if successes and non_successes:
        return _result(
            ReconciliationDecision.BLOCKED,
            ReconciliationReason.CONFLICTING_EVIDENCE,
            matched_ids=_candidate_ids(same_request_candidates),
            diagnostics=tuple(diagnostics),
        )
    if len(successes) > 1:
        return _result(
            ReconciliationDecision.BLOCKED,
            ReconciliationReason.MULTIPLE_MATCHING_COMPLETIONS,
            matched_ids=_candidate_ids(successes),
            diagnostics=tuple(diagnostics),
        )
    if non_successes:
        return _result(
            ReconciliationDecision.BLOCKED,
            ReconciliationReason.NON_SUCCESS_RESULT,
            matched_ids=_candidate_ids(non_successes),
            diagnostics=tuple(diagnostics),
        )

    return _result(
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        matched_ids=_candidate_ids(successes),
        diagnostics=tuple(diagnostics),
    )


def _provider_status_result(read_result: EvidenceReadResult) -> ReconciliationResult | None:
    if read_result.status != ProviderStatus.COMPLETE:
        mapping = {
            ProviderStatus.UNAVAILABLE: ReconciliationReason.PROVIDER_UNAVAILABLE,
            ProviderStatus.PERMISSION_DENIED: ReconciliationReason.PERMISSION_DENIED,
            ProviderStatus.INCOMPLETE: ReconciliationReason.PAGINATION_INCOMPLETE,
            ProviderStatus.ERROR: ReconciliationReason.PROVIDER_ERROR,
        }
        reason = mapping.get(read_result.status, ReconciliationReason.PROVIDER_ERROR)
        diagnostics = list(read_result.diagnostics)
        if reason == ReconciliationReason.PROVIDER_ERROR and read_result.status != ProviderStatus.ERROR:
            diagnostics.append(f"provider_status_unknown:{read_result.status}")
        return _result(
            ReconciliationDecision.ERROR,
            reason,
            diagnostics=tuple(diagnostics),
        )
    return None


def _parse_comment(
    comment: EvidenceComment,
    expected_protocol: str,
) -> dict[str, Any]:
    lines = comment.body.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        if line.strip():
            header_index = index
            break
    if header_index is None:
        return {"kind": "ordinary", "diagnostics": ()}

    header = lines[header_index]
    if not header.startswith(RESULT_MARKER):
        return {"kind": "ordinary", "diagnostics": ()}

    header_parts = header.split()
    if len(header_parts) != 2 or header_parts[0] != RESULT_MARKER:
        return {
            "kind": "malformed",
            "diagnostics": (f"marker_header_malformed:{comment.evidence_id}",),
        }
    protocol_part = header_parts[1]
    if not protocol_part.startswith("protocol="):
        return {
            "kind": "malformed",
            "diagnostics": (f"marker_header_malformed:{comment.evidence_id}",),
        }
    header_protocol = protocol_part.removeprefix("protocol=")
    if not header_protocol:
        return {
            "kind": "malformed",
            "diagnostics": (f"marker_header_malformed:{comment.evidence_id}",),
        }
    if header_protocol != expected_protocol:
        return {
            "kind": "unsupported",
            "diagnostics": (f"header_protocol_unsupported:{comment.evidence_id}",),
        }
    json_text = "\n".join(lines[header_index + 1 :])
    if not json_text.strip():
        return {
            "kind": "malformed",
            "diagnostics": (f"payload_missing:{comment.evidence_id}",),
        }

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        return {
            "kind": "malformed",
            "diagnostics": (f"payload_json_invalid:{comment.evidence_id}",),
        }
    if not isinstance(payload, dict):
        return {
            "kind": "malformed",
            "diagnostics": (f"payload_not_object:{comment.evidence_id}",),
        }

    payload_protocol_values = [
        payload[key] for key in ("schema", "protocol") if key in payload
    ]
    if not payload_protocol_values or any(
        protocol_value != expected_protocol for protocol_value in payload_protocol_values
    ):
        return {
            "kind": "unsupported",
            "diagnostics": (f"protocol_unsupported:{comment.evidence_id}",),
        }

    required_fields = ("request_id", "repo", "issue", "action", "branch", "head", "result")
    for field in required_fields:
        if field not in payload:
            return {
                "kind": "malformed",
                "diagnostics": (f"missing_field:{comment.evidence_id}:{field}",),
            }

    request_id = payload["request_id"]
    repo = payload["repo"]
    issue = payload["issue"]
    action = payload["action"]
    branch = payload["branch"]
    head = payload["head"]
    if not all(isinstance(value, str) and value.strip() for value in (request_id, repo, action, branch, head)):
        return {
            "kind": "malformed",
            "diagnostics": (f"invalid_identity_field:{comment.evidence_id}",),
        }
    if type(issue) is not int or issue <= 0:
        return {
            "kind": "malformed",
            "diagnostics": (f"invalid_issue:{comment.evidence_id}",),
        }

    return {
        "kind": "candidate",
        "diagnostics": (),
        "candidate": _ParsedCandidate(
            evidence_id=comment.evidence_id,
            author=comment.author,
            repository=repo,
            issue_number=issue,
            surface=comment.surface,
            request_id=request_id,
            action=action,
            branch=branch,
            head=head,
            result_value=payload["result"],
        ),
    }


def _identity_mismatch_result(
    request: RequestIdentity,
    candidates: list[_ParsedCandidate],
    diagnostics: set[str],
) -> ReconciliationResult | None:
    checks = (
        ("repository", ReconciliationReason.REPOSITORY_MISMATCH),
        ("issue_number", ReconciliationReason.ISSUE_MISMATCH),
        ("surface", ReconciliationReason.SURFACE_MISMATCH),
        ("action", ReconciliationReason.ACTION_MISMATCH),
        ("branch", ReconciliationReason.BRANCH_MISMATCH),
        ("head", ReconciliationReason.HEAD_MISMATCH),
    )
    for field_name, reason in checks:
        mismatches = [
            candidate
            for candidate in candidates
            if getattr(candidate, field_name) != getattr(request, field_name)
        ]
        if mismatches:
            diagnostics.add(f"{reason.value.lower()}:{','.join(_candidate_ids(mismatches))}")
            return _result(
                ReconciliationDecision.BLOCKED,
                reason,
                matched_ids=_candidate_ids(mismatches),
                diagnostics=tuple(diagnostics),
            )
    return None


def _candidate_ids(candidates: list[_ParsedCandidate]) -> tuple[str, ...]:
    return tuple(sorted(candidate.evidence_id for candidate in candidates))


def _result(
    decision: ReconciliationDecision,
    reason: ReconciliationReason,
    *,
    matched_ids: tuple[str, ...] = (),
    diagnostics: tuple[str, ...] = (),
) -> ReconciliationResult:
    return ReconciliationResult(
        decision=decision,
        reason=reason,
        matched_evidence_ids=tuple(sorted(matched_ids)),
        diagnostics=_sorted_strings(diagnostics),
    )


def _sorted_strings(values: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    return tuple(sorted(str(value) for value in values))
