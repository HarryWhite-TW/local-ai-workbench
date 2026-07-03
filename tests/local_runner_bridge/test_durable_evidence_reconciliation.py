import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.durable_evidence_reconciliation import (
    DurableEvidenceProvider,
    EvidenceComment,
    EvidenceReadResult,
    ProviderStatus,
    ReconciliationDecision,
    ReconciliationReason,
    RequestIdentity,
    resolve_durable_completion,
)


REQUEST = RequestIdentity(
    repository="HarryWhite-TW/local-ai-workbench",
    issue_number=175,
    surface="issue_comment",
    request_id="dispatch-175",
    action="run-reviewbundle",
    branch="master",
    head="4e6178cbfd5e79c1cb96d50968681dea58a3b6df",
)
TRUSTED_AUTHORS = frozenset({"HarryWhite-TW"})


class FakeProvider(DurableEvidenceProvider):
    def __init__(self, result: EvidenceReadResult):
        self._result = result
        self.calls: list[RequestIdentity] = []

    def read_result_comments(self, request: RequestIdentity) -> EvidenceReadResult:
        self.calls.append(request)
        return self._result


def make_comment(
    evidence_id: str,
    *,
    request_id: object = REQUEST.request_id,
    repository: str = REQUEST.repository,
    comment_repository: str | None = None,
    issue_number: int = REQUEST.issue_number,
    comment_issue_number: int | None = None,
    surface: str = REQUEST.surface,
    comment_surface: str | None = None,
    action: str = REQUEST.action,
    branch: str = REQUEST.branch,
    head: str = REQUEST.head,
    result: object = "success",
    author: str = "HarryWhite-TW",
    protocol_key: str = "schema",
    protocol_value: str = REQUEST.expected_result_protocol,
    header_protocol: str = REQUEST.expected_result_protocol,
    include_header_protocol: bool = True,
    include_result: bool = True,
    include_payload: bool = True,
    body_override: str | None = None,
    extra_payload: dict[str, object] | None = None,
) -> EvidenceComment:
    if body_override is not None:
        body = body_override
    elif not include_payload:
        if include_header_protocol:
            body = f"LAWBRUNNER-RESULT protocol={header_protocol}"
        else:
            body = "LAWBRUNNER-RESULT"
    else:
        payload = {
            protocol_key: protocol_value,
            "repo": repository,
            "issue": issue_number,
            "action": action,
            "branch": branch,
            "head": head,
            "request_id": request_id,
        }
        if include_result:
            payload["result"] = result
        if extra_payload:
            payload.update(extra_payload)
        import json

        if include_header_protocol:
            header = f"LAWBRUNNER-RESULT protocol={header_protocol}"
        else:
            header = "LAWBRUNNER-RESULT"
        body = header + "\n" + json.dumps(payload)

    return EvidenceComment(
        evidence_id=evidence_id,
        repository=comment_repository or REQUEST.repository,
        issue_number=comment_issue_number or REQUEST.issue_number,
        surface=comment_surface or surface,
        author=author,
        body=body,
    )


def make_body(**kwargs: object) -> str:
    return make_comment("body", **kwargs).body


def read_result(
    status: ProviderStatus = ProviderStatus.COMPLETE,
    comments: tuple[EvidenceComment, ...] = (),
    diagnostics: tuple[str, ...] = (),
) -> EvidenceReadResult:
    return EvidenceReadResult(status=status, comments=comments, diagnostics=diagnostics)


CASES = [
    pytest.param(
        read_result(comments=(make_comment("c1"),)),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-001",
    ),
    pytest.param(
        read_result(comments=()),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-002",
    ),
    pytest.param(
        read_result(
            comments=(
                EvidenceComment(
                    evidence_id="c1",
                    repository=REQUEST.repository,
                    issue_number=REQUEST.issue_number,
                    surface=REQUEST.surface,
                    author="HarryWhite-TW",
                    body="ordinary comment",
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-003",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", request_id="other-request"),)),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-004",
    ),
    pytest.param(
        read_result(status=ProviderStatus.UNAVAILABLE),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PROVIDER_UNAVAILABLE,
        (),
        id="D1-005",
    ),
    pytest.param(
        read_result(status=ProviderStatus.PERMISSION_DENIED),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PERMISSION_DENIED,
        (),
        id="D1-006",
    ),
    pytest.param(
        read_result(status=ProviderStatus.INCOMPLETE),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PAGINATION_INCOMPLETE,
        (),
        id="D1-007",
    ),
    pytest.param(
        read_result(status=ProviderStatus.ERROR),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PROVIDER_ERROR,
        (),
        id="D1-008",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", include_payload=False),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MALFORMED_EVIDENCE,
        ("c1",),
        id="D1-009",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", protocol_value="wrong.protocol"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNSUPPORTED_PROTOCOL,
        ("c1",),
        id="D1-010",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", author="outsider"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNTRUSTED_AUTHOR,
        ("c1",),
        id="D1-011",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", repository="other/repo"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.REPOSITORY_MISMATCH,
        ("c1",),
        id="D1-012",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", issue_number=999),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.ISSUE_MISMATCH,
        ("c1",),
        id="D1-013",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", surface="issue_body"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.SURFACE_MISMATCH,
        ("c1",),
        id="D1-014",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", action="maybe-status-check"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.ACTION_MISMATCH,
        ("c1",),
        id="D1-015",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", branch="feature/other"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.BRANCH_MISMATCH,
        ("c1",),
        id="D1-016",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", head="1111111111111111111111111111111111111111"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.HEAD_MISMATCH,
        ("c1",),
        id="D1-017",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", result="failure"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.NON_SUCCESS_RESULT,
        ("c1",),
        id="D1-018",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", include_result=False),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MALFORMED_EVIDENCE,
        ("c1",),
        id="D1-019",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1"), make_comment("c2"))),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MULTIPLE_MATCHING_COMPLETIONS,
        ("c1", "c2"),
        id="D1-020",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1"), make_comment("c2"))),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MULTIPLE_MATCHING_COMPLETIONS,
        ("c1", "c2"),
        id="D1-021",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1"), make_comment("c2", result="failure"))),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.CONFLICTING_EVIDENCE,
        ("c1", "c2"),
        id="D1-022",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1"), make_comment("c2", request_id="other-request"))),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-023",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", request_id="other-request", author="outsider"),)),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-024",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", request_id=""),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MALFORMED_EVIDENCE,
        ("c1",),
        id="D1-025",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment("c1"),
                EvidenceComment(
                    evidence_id="c2",
                    repository=REQUEST.repository,
                    issue_number=REQUEST.issue_number,
                    surface=REQUEST.surface,
                    author="HarryWhite-TW",
                    body="ordinary comment",
                ),
            )
        ),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-026",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", protocol_key="protocol"),)),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-027",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    extra_payload={
                        "selected_issue": REQUEST.issue_number,
                        "review_id": "review-175",
                        "diff_fingerprint": "diff-1",
                        "files_fingerprint": "files-1",
                        "changed_files": ["src/example.py"],
                        "validations": {"pytest": "reported"},
                        "safety": {"no_push": True},
                    },
                ),
            )
        ),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-028",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1"), make_comment("c2", author="outsider"))),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNTRUSTED_AUTHOR,
        ("c2",),
        id="D1-029",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1"), make_comment("c2", branch="feature/other"))),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.BRANCH_MISMATCH,
        ("c2",),
        id="D1-030",
    ),
    pytest.param(
        read_result(status=ProviderStatus.ERROR, comments=(make_comment("c1"),)),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PROVIDER_ERROR,
        (),
        id="D1-031",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", result="failure"), make_comment("c2", result="blocked"))),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.NON_SUCCESS_RESULT,
        ("c1", "c2"),
        id="D1-032",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", comment_repository="other/repo"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.REPOSITORY_MISMATCH,
        ("c1",),
        id="D1-033",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", comment_issue_number=999),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.ISSUE_MISMATCH,
        ("c1",),
        id="D1-034",
    ),
    pytest.param(
        read_result(
            comments=(
                EvidenceComment(
                    evidence_id="c1",
                    repository="other/repo",
                    issue_number=REQUEST.issue_number,
                    surface=REQUEST.surface,
                    author="HarryWhite-TW",
                    body="ordinary comment",
                ),
            )
        ),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.REPOSITORY_MISMATCH,
        ("c1",),
        id="D1-035",
    ),
    pytest.param(
        read_result(status="UNKNOWN", comments=(make_comment("c1"),)),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PROVIDER_ERROR,
        (),
        id="D1-036",
    ),
    pytest.param(
        read_result(status=None),
        ReconciliationDecision.ERROR,
        ReconciliationReason.PROVIDER_ERROR,
        (),
        id="D1-037",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment("c1", include_payload=False),
                make_comment("c2", header_protocol="lawb.runner_result.v2"),
            )
        ),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MALFORMED_EVIDENCE,
        ("c1",),
        id="D1-038",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment("c2", header_protocol="lawb.runner_result.v2"),
                make_comment("c1", include_payload=False),
            )
        ),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MALFORMED_EVIDENCE,
        ("c1",),
        id="D1-039",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", comment_repository="other/repo", branch="feature/other"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.REPOSITORY_MISMATCH,
        ("c1",),
        id="D1-040",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", header_protocol="lawb.runner_result.v2"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNSUPPORTED_PROTOCOL,
        ("c1",),
        id="D1-041",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", include_header_protocol=False),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.MALFORMED_EVIDENCE,
        ("c1",),
        id="D1-042",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", protocol_value="lawb.runner_result.v2"),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNSUPPORTED_PROTOCOL,
        ("c1",),
        id="D1-043",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    body_override=(
                        "Documentation mentions LAWBRUNNER-RESULT "
                        "protocol=lawb.runner_result.v1 for troubleshooting."
                    ),
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-044",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    body_override="Notes before evidence:\n" + make_body(),
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-045",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    body_override="```text\n" + make_body() + "\n```",
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-046",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    body_override="    " + make_body().replace("\n", "\n    "),
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-047",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    body_override="> " + make_body().replace("\n", "\n> "),
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-048",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    body_override="- " + make_body().replace("\n", "\n  "),
                ),
            )
        ),
        ReconciliationDecision.NOT_FOUND,
        ReconciliationReason.ZERO_MATCHING_COMPLETIONS,
        (),
        id="D1-049",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", body_override="\n\n" + make_body()),)),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-050",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", extra_payload={"protocol": REQUEST.expected_result_protocol}),)),
        ReconciliationDecision.COMPLETED,
        ReconciliationReason.EXACTLY_ONE_TRUSTED_MATCH,
        ("c1",),
        id="D1-051",
    ),
    pytest.param(
        read_result(
            comments=(
                make_comment(
                    "c1",
                    protocol_value="lawb.runner_result.v2",
                    extra_payload={"protocol": REQUEST.expected_result_protocol},
                ),
            )
        ),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNSUPPORTED_PROTOCOL,
        ("c1",),
        id="D1-052",
    ),
    pytest.param(
        read_result(comments=(make_comment("c1", extra_payload={"protocol": "lawb.runner_result.v2"}),)),
        ReconciliationDecision.BLOCKED,
        ReconciliationReason.UNSUPPORTED_PROTOCOL,
        ("c1",),
        id="D1-053",
    ),
]


@pytest.mark.parametrize(
    ("provider_result", "expected_decision", "expected_reason", "expected_ids"),
    CASES,
)
def test_resolve_durable_completion_cases(
    provider_result: EvidenceReadResult,
    expected_decision: ReconciliationDecision,
    expected_reason: ReconciliationReason,
    expected_ids: tuple[str, ...],
) -> None:
    provider = FakeProvider(provider_result)

    result = resolve_durable_completion(REQUEST, provider, TRUSTED_AUTHORS)

    assert provider.calls == [REQUEST]
    assert result.decision == expected_decision
    assert result.reason == expected_reason
    assert result.matched_evidence_ids == expected_ids
    assert result.diagnostics == tuple(sorted(result.diagnostics))


def test_request_surface_mismatch_blocks_before_provider_read() -> None:
    request = RequestIdentity(
        repository=REQUEST.repository,
        issue_number=REQUEST.issue_number,
        surface="issue_body",
        request_id=REQUEST.request_id,
        action=REQUEST.action,
        branch=REQUEST.branch,
        head=REQUEST.head,
        expected_result_protocol=REQUEST.expected_result_protocol,
    )
    provider = FakeProvider(read_result(comments=(make_comment("c1"),)))

    result = resolve_durable_completion(request, provider, TRUSTED_AUTHORS)

    assert provider.calls == []
    assert result.decision == ReconciliationDecision.BLOCKED
    assert result.reason == ReconciliationReason.SURFACE_MISMATCH
    assert result.matched_evidence_ids == ()


def test_request_protocol_mismatch_blocks_before_provider_read() -> None:
    request = RequestIdentity(
        repository=REQUEST.repository,
        issue_number=REQUEST.issue_number,
        surface=REQUEST.surface,
        request_id=REQUEST.request_id,
        action=REQUEST.action,
        branch=REQUEST.branch,
        head=REQUEST.head,
        expected_result_protocol="lawb.runner_result.v2",
    )
    provider = FakeProvider(read_result(comments=(make_comment("c1"),)))

    result = resolve_durable_completion(request, provider, TRUSTED_AUTHORS)

    assert provider.calls == []
    assert result.decision == ReconciliationDecision.BLOCKED
    assert result.reason == ReconciliationReason.UNSUPPORTED_PROTOCOL
    assert result.matched_evidence_ids == ()


def test_provider_exception_maps_to_provider_error() -> None:
    class RaisingProvider(DurableEvidenceProvider):
        def read_result_comments(self, request: RequestIdentity) -> EvidenceReadResult:
            raise RuntimeError("boom")

    result = resolve_durable_completion(REQUEST, RaisingProvider(), TRUSTED_AUTHORS)

    assert result.decision == ReconciliationDecision.ERROR
    assert result.reason == ReconciliationReason.PROVIDER_ERROR
    assert result.matched_evidence_ids == ()
    assert result.diagnostics == ("provider_exception:RuntimeError",)


def test_comment_input_order_does_not_change_result() -> None:
    first = resolve_durable_completion(
        REQUEST,
        FakeProvider(read_result(comments=(make_comment("c2"), make_comment("c1")))),
        TRUSTED_AUTHORS,
    )
    second = resolve_durable_completion(
        REQUEST,
        FakeProvider(read_result(comments=(make_comment("c1"), make_comment("c2")))),
        TRUSTED_AUTHORS,
    )

    assert first.decision == second.decision == ReconciliationDecision.BLOCKED
    assert first.reason == second.reason == ReconciliationReason.MULTIPLE_MATCHING_COMPLETIONS
    assert first.matched_evidence_ids == second.matched_evidence_ids == ("c1", "c2")
    assert first.diagnostics == second.diagnostics


def test_diagnostics_are_sorted_and_deduplicated() -> None:
    provider = FakeProvider(
        read_result(
            comments=(make_comment("c1", include_payload=False),),
            diagnostics=("zeta", "alpha", "zeta"),
        )
    )

    result = resolve_durable_completion(REQUEST, provider, TRUSTED_AUTHORS)

    assert result.decision == ReconciliationDecision.BLOCKED
    assert result.reason == ReconciliationReason.MALFORMED_EVIDENCE
    assert result.diagnostics == ("alpha", "payload_missing:c1", "zeta")


def test_request_object_is_not_mutated() -> None:
    provider = FakeProvider(read_result(comments=(make_comment("c1"),)))
    before = REQUEST

    resolve_durable_completion(REQUEST, provider, TRUSTED_AUTHORS)

    assert REQUEST == before
