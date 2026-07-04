"""Read-only durable-evidence providers for B3 reconciliation."""

from __future__ import annotations

from typing import Any

from local_runner_bridge.bridge_operator_b1 import DEFAULT_REPOSITORY
from local_runner_bridge.durable_evidence_reconciliation import (
    EvidenceComment,
    EvidenceReadResult,
    ProviderStatus,
    RequestIdentity,
)

SUPPORTED_SURFACE = "issue_comment"


class GitHubIssueCommentEvidenceProvider:
    """Adapt the existing issue-scoped GitHub client to D1 evidence reads."""

    def __init__(
        self,
        client: Any,
        *,
        repository: str = DEFAULT_REPOSITORY,
    ) -> None:
        self.client = client
        self.repository = repository

    def read_result_comments(self, request: RequestIdentity) -> EvidenceReadResult:
        if request.repository != self.repository:
            return EvidenceReadResult(
                status=ProviderStatus.ERROR,
                comments=(),
                diagnostics=("provider_repository_mismatch",),
            )
        if request.surface != SUPPORTED_SURFACE:
            return EvidenceReadResult(
                status=ProviderStatus.ERROR,
                comments=(),
                diagnostics=("provider_surface_unsupported",),
            )

        try:
            comments = self.client.list_issue_comments(request.issue_number)
        except PermissionError:
            return EvidenceReadResult(
                status=ProviderStatus.PERMISSION_DENIED,
                comments=(),
                diagnostics=("provider_permission_denied",),
            )
        except RuntimeError as error:
            return _runtime_error_result(error)
        except Exception as error:
            return EvidenceReadResult(
                status=ProviderStatus.ERROR,
                comments=(),
                diagnostics=(f"provider_error:{type(error).__name__}",),
            )

        evidence = tuple(
            EvidenceComment(
                evidence_id=str(comment.id),
                repository=self.repository,
                issue_number=request.issue_number,
                surface=SUPPORTED_SURFACE,
                author=str(comment.author),
                body=str(comment.body),
            )
            for comment in comments
        )
        return EvidenceReadResult(
            status=ProviderStatus.COMPLETE,
            comments=evidence,
            diagnostics=("provider_complete",),
        )


def _runtime_error_result(error: RuntimeError) -> EvidenceReadResult:
    message = str(error)
    if message == "gh_missing":
        return EvidenceReadResult(
            status=ProviderStatus.UNAVAILABLE,
            comments=(),
            diagnostics=("provider_unavailable:gh_missing",),
        )
    if message == "gh_api_pagination_unexpected_payload":
        return EvidenceReadResult(
            status=ProviderStatus.INCOMPLETE,
            comments=(),
            diagnostics=("provider_incomplete:pagination",),
        )
    return EvidenceReadResult(
        status=ProviderStatus.ERROR,
        comments=(),
        diagnostics=("provider_error:RuntimeError",),
    )
