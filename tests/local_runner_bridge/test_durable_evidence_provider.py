import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.bridge_operator_b1 import CommentRecord
from local_runner_bridge.durable_evidence_provider import (
    GitHubIssueCommentEvidenceProvider,
)
from local_runner_bridge.durable_evidence_reconciliation import (
    ProviderStatus,
    RequestIdentity,
)


REQUEST = RequestIdentity(
    repository="HarryWhite-TW/local-ai-workbench",
    issue_number=175,
    surface="issue_comment",
    request_id="dispatch-175",
    action="run-reviewbundle",
    branch="master",
    head="d96b1dcd12f063b119977de966c58686b834f723",
)


class FakeClient:
    def __init__(self, *, comments=(), error=None):
        self.comments = comments
        self.error = error
        self.issues_read = []

    def list_issue_comments(self, issue_number):
        self.issues_read.append(issue_number)
        if self.error is not None:
            raise self.error
        return self.comments


def test_provider_reads_only_request_issue_and_maps_comment_fields():
    client = FakeClient(
        comments=(
            CommentRecord(id=123, author="HarryWhite-TW", body="result body"),
        )
    )
    provider = GitHubIssueCommentEvidenceProvider(client)

    result = provider.read_result_comments(REQUEST)

    assert client.issues_read == [175]
    assert result.status == ProviderStatus.COMPLETE
    assert result.diagnostics == ("provider_complete",)
    assert len(result.comments) == 1
    comment = result.comments[0]
    assert comment.evidence_id == "123"
    assert comment.repository == REQUEST.repository
    assert comment.issue_number == REQUEST.issue_number
    assert comment.surface == "issue_comment"
    assert comment.author == "HarryWhite-TW"
    assert comment.body == "result body"


def test_provider_empty_comments_returns_complete_empty_tuple():
    result = GitHubIssueCommentEvidenceProvider(FakeClient()).read_result_comments(REQUEST)

    assert result.status == ProviderStatus.COMPLETE
    assert result.comments == ()


def test_provider_repository_mismatch_fails_closed_without_client_read():
    client = FakeClient()
    request = RequestIdentity(
        repository="other/repo",
        issue_number=REQUEST.issue_number,
        surface=REQUEST.surface,
        request_id=REQUEST.request_id,
        action=REQUEST.action,
        branch=REQUEST.branch,
        head=REQUEST.head,
    )

    result = GitHubIssueCommentEvidenceProvider(client).read_result_comments(request)

    assert client.issues_read == []
    assert result.status == ProviderStatus.ERROR
    assert result.diagnostics == ("provider_repository_mismatch",)


def test_provider_permission_error_maps_to_permission_denied():
    result = GitHubIssueCommentEvidenceProvider(
        FakeClient(error=PermissionError("ghp_SECRET should not leak"))
    ).read_result_comments(REQUEST)

    assert result.status == ProviderStatus.PERMISSION_DENIED
    assert result.diagnostics == ("provider_permission_denied",)


def test_provider_gh_missing_maps_to_unavailable():
    result = GitHubIssueCommentEvidenceProvider(
        FakeClient(error=RuntimeError("gh_missing"))
    ).read_result_comments(REQUEST)

    assert result.status == ProviderStatus.UNAVAILABLE
    assert result.diagnostics == ("provider_unavailable:gh_missing",)


def test_provider_unexpected_pagination_maps_to_incomplete():
    result = GitHubIssueCommentEvidenceProvider(
        FakeClient(error=RuntimeError("gh_api_pagination_unexpected_payload"))
    ).read_result_comments(REQUEST)

    assert result.status == ProviderStatus.INCOMPLETE
    assert result.diagnostics == ("provider_incomplete:pagination",)


def test_provider_generic_exception_maps_to_error_without_secret_message():
    result = GitHubIssueCommentEvidenceProvider(
        FakeClient(error=ValueError("token=ghp_SECRET should not leak"))
    ).read_result_comments(REQUEST)

    assert result.status == ProviderStatus.ERROR
    assert result.diagnostics == ("provider_error:ValueError",)
    assert "ghp_SECRET" not in " ".join(result.diagnostics)
