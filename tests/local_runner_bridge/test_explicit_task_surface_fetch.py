import json
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.explicit_task_surface_fetch import (
    classify_explicit_task_surface_reference,
    run_explicit_task_surface_fetch,
)


VALID_PACKET = """protocol: lawb.local_runner.task_packet.v1
packet_id: task-145-explicit-task-surface-fetch
logical_issue: 145
phase: read_only_explicit_github_task_surface_fetch_reviewbundle
action_type: read_only_audit
risk_level: low
repository: HarryWhite-TW/local-ai-workbench
branch: master
expected_head: 361498fe24492b299e9063a4590b64594fbecded
allowed_files:
  - src/local_runner_bridge/explicit_task_surface_fetch.py
  - tests/local_runner_bridge/test_explicit_task_surface_fetch.py
forbidden_operations:
  - commit
  - push
approval:
  required: false
payload:
  kind: none
result_target:
  github_issue: 114
  marker: REVIEWBUNDLE-AUDIT-VISIBLE
stop_condition: stop_after_local_validation
"""


EXPECTED = {
    "logical_issue": 145,
    "phase": "read_only_explicit_github_task_surface_fetch_reviewbundle",
}


def surface(packet_text=VALID_PACKET):
    return (
        "LOCAL-RUNNER-TASK-PACKET-V1\n"
        "BEGIN_TASK_PACKET\n"
        f"{packet_text}"
        "END_TASK_PACKET\n"
    )


def assert_no_write_or_action(summary):
    assert summary["broad_issue_scan_performed"] is False
    assert summary["github_write_performed"] is False
    assert summary["result_packet_written"] is False
    assert summary["codex_side_action_executed"] is False
    assert summary["commit_triggered"] is False
    assert summary["push_triggered"] is False
    assert summary["pr_triggered"] is False
    assert summary["issue_closed"] is False
    assert summary["label_changed"] is False


def test_rejects_missing_reference():
    summary = run_explicit_task_surface_fetch(None, expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert summary["errors"] == ["missing_reference"]
    assert summary["bounded_read_performed"] is False
    assert_no_write_or_action(summary)


def test_rejects_broad_reference():
    summary = run_explicit_task_surface_fetch("latest issue", expected=EXPECTED)

    assert summary["result"] == "blocked"
    assert summary["errors"] == ["broad_reference_rejected"]
    assert summary["broad_issue_scan_performed"] is False
    assert_no_write_or_action(summary)


def test_rejects_multiple_references():
    summary = run_explicit_task_surface_fetch(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145 "
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/146",
        expected=EXPECTED,
    )

    assert summary["result"] == "blocked"
    assert summary["errors"] == ["multiple_references"]
    assert summary["bounded_read_performed"] is False
    assert_no_write_or_action(summary)


def test_rejects_arbitrary_urls_without_read_or_write_behavior():
    inputs = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "file:///etc/passwd",
        "https://example.com/foo",
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues",
        "https://github.com/search?q=local-ai-workbench",
    ]

    for reference in inputs:
        summary = run_explicit_task_surface_fetch(reference, expected=EXPECTED)

        assert summary["result"] == "blocked"
        assert summary["bounded_read_performed"] is False
        assert_no_write_or_action(summary)


def test_classifies_explicit_issue_comment_url():
    summary = classify_explicit_task_surface_reference(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145"
        "#issuecomment-123"
    )

    assert summary["result"] == "success"
    assert summary["reference_type"] == "issue_comment_url"
    assert summary["owner"] == "HarryWhite-TW"
    assert summary["repo"] == "local-ai-workbench"
    assert summary["issue"] == 145
    assert summary["comment_id"] == 123


def test_accepts_local_text_and_routes_through_validation_dry_run():
    summary = run_explicit_task_surface_fetch(surface(), expected=EXPECTED)

    assert summary["result"] == "success"
    assert summary["reference_type"] == "local_text"
    assert summary["bounded_read_performed"] is True
    assert summary["source_surface_text"] == surface()
    assert summary["validation_summary"]["result"] == "success"
    assert_no_write_or_action(summary)


def test_blocked_validation_does_not_authorize_write_or_action():
    summary = run_explicit_task_surface_fetch(
        "LOCAL-RUNNER-TASK-PACKET-V1\nBEGIN_TASK_PACKET\nEND_TASK_PACKET\n",
        expected=EXPECTED,
    )

    assert summary["result"] == "blocked"
    assert summary["errors"] == ["validation_summary_not_success"]
    assert summary["validation_summary"]["result"] == "blocked"
    assert_no_write_or_action(summary)


def test_http_error_fails_closed_without_read_or_write_behavior():
    def fake_get_json(url, token):
        raise urllib.error.HTTPError(
            url=url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    summary = run_explicit_task_surface_fetch(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145",
        expected=EXPECTED,
        http_get_json=fake_get_json,
    )

    assert summary["result"] == "blocked"
    assert summary["bounded_read_performed"] is False
    assert summary["errors"][0] == "github_fetch_failed"
    assert_no_write_or_action(summary)


def test_url_error_fails_closed_without_read_or_write_behavior():
    def fake_get_json(url, token):
        raise urllib.error.URLError("network unavailable")

    summary = run_explicit_task_surface_fetch(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145",
        expected=EXPECTED,
        http_get_json=fake_get_json,
    )

    assert summary["result"] == "blocked"
    assert summary["bounded_read_performed"] is False
    assert summary["errors"][0] == "github_fetch_failed"
    assert_no_write_or_action(summary)


def test_github_token_reaches_getter_but_is_not_in_summary():
    seen_tokens = []

    def fake_get_json(url, token):
        seen_tokens.append(token)
        return {"body": surface()}

    summary = run_explicit_task_surface_fetch(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145",
        expected=EXPECTED,
        github_token="ghp_TEST_SECRET_DO_NOT_LEAK",
        http_get_json=fake_get_json,
    )

    assert seen_tokens == ["ghp_TEST_SECRET_DO_NOT_LEAK"]
    assert summary["result"] == "success"
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in json.dumps(summary)
    assert_no_write_or_action(summary)


def test_malformed_repository_fails_closed_without_read_or_write_behavior():
    summary = run_explicit_task_surface_fetch(
        "#145",
        expected=EXPECTED,
        repository="bad-repo-format",
    )

    assert summary["result"] == "blocked"
    assert summary["bounded_read_performed"] is False
    assert "invalid_repository" in summary["errors"]
    assert_no_write_or_action(summary)


def test_explicit_issue_url_uses_single_stubbed_github_read_and_validates():
    calls = []

    def fake_get_json(url, token):
        calls.append((url, token))
        return {"body": surface()}

    summary = run_explicit_task_surface_fetch(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145",
        expected=EXPECTED,
        http_get_json=fake_get_json,
    )

    assert summary["result"] == "success"
    assert summary["reference_type"] == "issue_url"
    assert summary["bounded_read_performed"] is True
    assert calls == [
        (
            "https://api.github.com/repos/HarryWhite-TW/local-ai-workbench/issues/145",
            None,
        )
    ]
    assert summary["validation_summary"]["result"] == "success"
    assert_no_write_or_action(summary)


def test_explicit_comment_url_uses_single_stubbed_github_read_and_validates():
    calls = []

    def fake_get_json(url, token):
        calls.append((url, token))
        return {"body": surface()}

    summary = run_explicit_task_surface_fetch(
        "https://github.com/HarryWhite-TW/local-ai-workbench/issues/145"
        "#issuecomment-123",
        expected=EXPECTED,
        http_get_json=fake_get_json,
    )

    assert summary["result"] == "success"
    assert summary["reference_type"] == "issue_comment_url"
    assert calls == [
        (
            "https://api.github.com/repos/HarryWhite-TW/local-ai-workbench/"
            "issues/comments/123",
            None,
        )
    ]
    assert summary["validation_summary"]["result"] == "success"
    assert_no_write_or_action(summary)
