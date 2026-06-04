"""Read-only explicit task surface fetch boundary."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable, Any

from local_runner_bridge.task_surface_dry_run import run_validation_dry_run
from local_runner_bridge.task_surface_resolver import (
    BEGIN_MARKER,
    END_MARKER,
    PROTOCOL_MARKER,
)

SUMMARY_PROTOCOL = "lawb.local_runner.explicit_task_surface_fetch_summary.v1"
DEFAULT_REPOSITORY = "HarryWhite-TW/local-ai-workbench"

_ISSUE_URL_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/issues/(?P<issue>\d+)"
    r"(?:#issuecomment-(?P<comment_id>\d+))?$"
)
_ISSUE_NUMBER_RE = re.compile(r"^#?(?P<issue>\d+)$")
_COMMENT_ID_RE = re.compile(r"^(?:comment_id[:=]|issuecomment-)(?P<comment_id>\d+)$")
_GITHUB_URL_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/issues/\d+(?:#issuecomment-\d+)?"
)

_BROAD_REFERENCE_PHRASES = (
    "latest issue",
    "next issue",
    "all open issues",
    "repo scan",
    "search all comments",
    "find the newest task",
    "infer task from roadmap",
    "broad query",
)


def _base_summary(reference: str | None) -> dict:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "explicit_input_preserved": reference is not None,
        "input_reference": reference,
        "reference_type": None,
        "bounded_read_performed": False,
        "broad_issue_scan_performed": False,
        "github_write_performed": False,
        "result_packet_written": False,
        "codex_side_action_executed": False,
        "commit_triggered": False,
        "push_triggered": False,
        "pr_triggered": False,
        "issue_closed": False,
        "label_changed": False,
        "drift_detected": False,
        "errors": [],
        "next_recommended_action": "chatgpt_review",
    }


def _blocked(reference: str | None, error: str) -> dict:
    summary = _base_summary(reference)
    summary["errors"].append(error)
    return summary


def _contains_local_task_surface(text: str) -> bool:
    return (
        PROTOCOL_MARKER in text
        and BEGIN_MARKER in text
        and END_MARKER in text
    )


def classify_explicit_task_surface_reference(
    reference: str | None,
    *,
    repository: str = DEFAULT_REPOSITORY,
) -> dict:
    """Classify one explicit reference, or fail closed."""
    if reference is None:
        return _blocked(reference, "missing_reference")
    if not isinstance(reference, str):
        return _blocked(None, "reference_not_string")

    text = reference.strip()
    if not text:
        return _blocked(reference, "missing_reference")

    if _contains_local_task_surface(text):
        return {
            "result": "success",
            "reference_type": "local_text",
            "surface_text": reference,
        }

    lowered = text.lower()
    if any(phrase in lowered for phrase in _BROAD_REFERENCE_PHRASES):
        return _blocked(reference, "broad_reference_rejected")

    github_urls = _GITHUB_URL_RE.findall(text)
    if len(github_urls) > 1:
        return _blocked(reference, "multiple_references")
    if len(github_urls) == 1 and github_urls[0] != text:
        return _blocked(reference, "ambiguous_reference")

    issue_url_match = _ISSUE_URL_RE.match(text)
    if issue_url_match:
        groups = issue_url_match.groupdict()
        reference_type = "issue_comment_url" if groups.get("comment_id") else "issue_url"
        return {
            "result": "success",
            "reference_type": reference_type,
            "owner": groups["owner"],
            "repo": groups["repo"],
            "issue": int(groups["issue"]),
            "comment_id": (
                int(groups["comment_id"]) if groups.get("comment_id") else None
            ),
        }

    comment_match = _COMMENT_ID_RE.match(text)
    if comment_match:
        owner, repo = _split_repository(repository)
        return {
            "result": "success",
            "reference_type": "comment_id",
            "owner": owner,
            "repo": repo,
            "comment_id": int(comment_match.group("comment_id")),
        }

    issue_match = _ISSUE_NUMBER_RE.match(text)
    if issue_match:
        owner, repo = _split_repository(repository)
        return {
            "result": "success",
            "reference_type": "issue_number",
            "owner": owner,
            "repo": repo,
            "issue": int(issue_match.group("issue")),
        }

    return _blocked(reference, "unsupported_reference")


def run_explicit_task_surface_fetch(
    reference: str | None,
    *,
    expected: dict | None = None,
    repository: str = DEFAULT_REPOSITORY,
    github_token: str | None = None,
    http_get_json: Callable[[str, str | None], dict[str, Any]] | None = None,
) -> dict:
    """Read one explicit surface and route its text through the dry-run validator."""
    summary = _base_summary(reference)
    try:
        classified = classify_explicit_task_surface_reference(
            reference,
            repository=repository,
        )
    except ValueError:
        summary["errors"] = ["invalid_repository"]
        return summary
    if classified["result"] != "success":
        summary["errors"] = classified["errors"]
        return summary

    summary["reference_type"] = classified["reference_type"]

    if classified["reference_type"] == "local_text":
        surface_text = classified["surface_text"]
    else:
        try:
            surface_text = _fetch_github_surface_text(
                classified,
                github_token=github_token,
                http_get_json=http_get_json,
            )
        except Exception as error:
            summary["errors"] = ["github_fetch_failed", type(error).__name__]
            return summary

    summary["bounded_read_performed"] = True
    summary["source_surface_text"] = surface_text
    validation_summary = run_validation_dry_run(surface_text, expected=expected)
    summary["validation_summary"] = validation_summary
    summary["result"] = validation_summary.get("result", "blocked")
    if validation_summary.get("result") != "success":
        summary["errors"] = ["validation_summary_not_success"]

    return summary


def _split_repository(repository: str) -> tuple[str, str]:
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise ValueError("repository must be owner/repo")
    owner, repo = repository.split("/", 1)
    if not owner or not repo:
        raise ValueError("repository must be owner/repo")
    return owner, repo


def _fetch_github_surface_text(
    classified: dict,
    *,
    github_token: str | None,
    http_get_json: Callable[[str, str | None], dict[str, Any]] | None,
) -> str:
    getter = http_get_json or _github_get_json
    owner = classified["owner"]
    repo = classified["repo"]

    if classified["reference_type"] in {"issue_comment_url", "comment_id"}:
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/issues/comments/"
            f"{classified['comment_id']}"
        )
    else:
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/issues/"
            f"{classified['issue']}"
        )

    payload = getter(url, github_token)
    body = payload.get("body")
    if not isinstance(body, str):
        raise ValueError("github response missing body")
    return body


def _github_get_json(url: str, github_token: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "local-ai-workbench-read-only-task-surface-fetch",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))
