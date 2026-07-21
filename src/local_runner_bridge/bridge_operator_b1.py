"""Bridge Operator B1 fixed-inbox read-only dry run."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUMMARY_PROTOCOL = "lawb.bridge_operator_b1_dry_run_summary.v1"
REQUEST_PROTOCOL = "lawb.bridge_inbox_request.v1"
REQUEST_MARKER = "BRIDGE-INBOX-REQUEST"
DISPATCH_PROTOCOL = "lawb.dispatch.v1"
DISPATCH_MARKER = "CHATGPT-DISPATCH"
DEFAULT_REPOSITORY = "HarryWhite-TW/local-ai-workbench"
HAG_REPOSITORY = "HarryWhite-TW/human-approval-automation-gateway"
SUPPORTED_TARGET_REPOSITORIES = (DEFAULT_REPOSITORY, HAG_REPOSITORY)
TRUSTED_ACTORS = ("HarryWhite-TW",)
ALLOWED_ACTIONS = ("maybe-status-check", "run-reviewbundle")
UTC_BASIC_FORMAT = "%Y%m%dT%H%M%SZ"
CURRENT = "CURRENT"
CONSUMED = "CONSUMED"
EXPIRED = "EXPIRED"

_FIELD_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^ \t\r\n]+)$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{2,127}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,255}$")


@dataclass(frozen=True)
class IssueRecord:
    number: int
    state: str
    body: str


@dataclass(frozen=True)
class CommentRecord:
    id: int | str
    body: str
    author: str


@dataclass(frozen=True)
class LocalReadiness:
    repo_root: str
    branch: str | None
    head: str | None
    clean: bool | None
    gh_available: bool
    gh_authenticated: bool
    gh_read_available: bool
    errors: tuple[str, ...] = ()
    origin_repository: str | None = DEFAULT_REPOSITORY
    git_root_matches: bool = True
    staged_clean: bool | None = True


def run_bridge_operator_b1_dry_run(
    *,
    inbox_issue: int,
    repo_root: str | Path,
    repository: str = DEFAULT_REPOSITORY,
    github_client: Any | None = None,
    target_github_client: Any | None = None,
    local_checker: Callable[[str | Path], LocalReadiness] | None = None,
    now_utc: datetime | None = None,
    consumed_request_ids: Iterable[str] | Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate one fixed Bridge Inbox request without delegating execution."""
    summary = _base_summary(repository, inbox_issue, repo_root)
    now_utc = _normalize_now(now_utc)
    summary["evaluated_at_utc"] = _format_time(now_utc)
    consumed_records = _normalize_consumed_request_records(consumed_request_ids)

    if repository not in SUPPORTED_TARGET_REPOSITORIES:
        _block(summary, "unsupported_target_repository")
        return summary
    if not isinstance(inbox_issue, int) or inbox_issue <= 0:
        _block(summary, "invalid_inbox_issue")
        return summary

    control_client = github_client or GitHubApiClient(DEFAULT_REPOSITORY)
    target_client = target_github_client
    if target_client is None:
        target_client = (
            control_client if repository == DEFAULT_REPOSITORY else GitHubApiClient(repository)
        )
    checker = local_checker or check_local_readiness

    try:
        inbox_issue_record = control_client.get_issue(inbox_issue)
        inbox_comments = control_client.list_issue_comments(inbox_issue)
    except Exception as error:
        _block(summary, "github_read_unavailable")
        summary["github_read_error_type"] = type(error).__name__
        return summary

    summary["fixed_inbox_read_performed"] = True
    summary["github_read_available"] = True
    summary["inbox_issue_state"] = inbox_issue_record.state

    markers = _collect_request_markers(inbox_issue_record, inbox_comments)
    if not markers:
        _block(summary, "missing_request")
        return summary

    current_markers = []
    for marker in markers:
        if marker["author"] not in TRUSTED_ACTORS:
            _block(summary, "untrusted_inbox_author")
            return summary
        request = parse_bridge_inbox_request(marker["line"])
        if request["result"] != "success":
            _block(summary, "malformed_marker")
            summary["parse_errors"] = request["errors"]
            return summary
        fields = request["fields"]
        _validate_request_fields(fields, summary, now_utc, enforce_expiry=False)
        if summary["blocked_reasons"]:
            return summary
        expires = _parse_utc_basic(str(fields["expires"]))
        if expires is None:
            _block(summary, "invalid_expiry")
            return summary
        request_id = str(fields["request_id"])
        if request_id in consumed_records:
            if not _processed_identity_matches(fields, consumed_records[request_id]):
                _block(summary, "processed_request_identity_mismatch")
                summary["processed_request_identity_mismatch_request_id"] = request_id
                return summary
            lifecycle_state = CONSUMED
        elif expires <= now_utc:
            lifecycle_state = EXPIRED
        else:
            lifecycle_state = CURRENT
        summary["request_lifecycle"].append(
            {
                "inbox_comment_id": marker["comment_id"],
                "request_id": request_id,
                "expires": fields["expires"],
                "lifecycle_state": lifecycle_state,
            }
        )
        if lifecycle_state == CONSUMED:
            summary["consumed_request_count"] += 1
            continue
        if lifecycle_state == EXPIRED:
            summary["expired_request_count"] += 1
            summary["expired_historical_request_count"] = (
                summary.get("expired_historical_request_count", 0) + 1
            )
            continue
        summary["current_request_count"] += 1
        current_markers.append({"marker": marker, "fields": fields})

    if not current_markers:
        if summary["consumed_request_count"] > 0:
            _block(summary, "no_current_request_after_consumption")
            return summary
        _block(summary, "missing_current_request")
        return summary
    if len(current_markers) > 1:
        _block(summary, "multiple_current_requests")
        summary["current_marker_count"] = len(current_markers)
        return summary

    selected = current_markers[0]
    marker = selected["marker"]
    fields = selected["fields"]

    summary["inbox_comment_id"] = marker["comment_id"]
    summary["inbox_request_author"] = marker["author"]
    summary["request_id"] = fields["request_id"]
    summary["target_issue"] = fields["target_issue"]
    summary["target_dispatch_request_id"] = fields["target_dispatch_request_id"]
    summary["requested_action"] = fields["action"]
    summary["expected_branch"] = fields["branch"]
    summary["expected_head"] = fields["head"]
    summary["expires"] = fields["expires"]
    summary["selected_request_state"] = CURRENT

    _validate_request_fields(fields, summary, now_utc)
    if summary["blocked_reasons"]:
        return summary

    try:
        target_issue = target_client.get_issue(fields["target_issue"])
    except Exception as error:
        _block(summary, "target_issue_missing")
        summary["target_issue_error_type"] = type(error).__name__
        return summary

    summary["target_issue_read_performed"] = True
    summary["target_issue_state"] = target_issue.state
    if target_issue.state.lower() != "open":
        _block(summary, "target_issue_closed")
        return summary

    try:
        target_comments = target_client.list_issue_comments(fields["target_issue"])
    except Exception as error:
        _block(summary, "github_read_unavailable")
        summary["target_comments_error_type"] = type(error).__name__
        return summary

    _validate_target_dispatch_identity(target_comments, fields, summary, now_utc)
    if summary["blocked_reasons"]:
        return summary

    readiness = checker(repo_root)
    summary["local_readiness"] = {
        "repo_root": readiness.repo_root,
        "branch": readiness.branch,
        "head": readiness.head,
        "clean": readiness.clean,
        "gh_available": readiness.gh_available,
        "gh_authenticated": readiness.gh_authenticated,
        "gh_read_available": readiness.gh_read_available,
        "errors": list(readiness.errors),
    }
    _validate_local_readiness(readiness, fields, repo_root, summary)
    if summary["blocked_reasons"]:
        return summary

    summary["result"] = "success"
    summary["dry_run_result"] = "ready_without_delegation"
    summary["validations"]["request"] = "passed"
    summary["validations"]["target_issue"] = "passed"
    summary["validations"]["local_readiness"] = "passed"
    return summary


def _normalize_consumed_request_records(
    consumed_request_ids: Iterable[str] | Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any] | None]:
    if consumed_request_ids is None:
        return {}
    if isinstance(consumed_request_ids, Mapping):
        records: dict[str, Mapping[str, Any] | None] = {}
        for request_id, record in consumed_request_ids.items():
            records[str(request_id)] = record if isinstance(record, Mapping) else None
        return records
    return {str(request_id): None for request_id in consumed_request_ids}


def _processed_identity_matches(
    fields: Mapping[str, Any], record: Mapping[str, Any] | None
) -> bool:
    if not isinstance(record, Mapping):
        return False
    expected = {
        "target_repository": fields.get("repo"),
        "target_issue": fields.get("target_issue"),
        "target_dispatch_request_id": fields.get("target_dispatch_request_id"),
        "requested_action": fields.get("action"),
        "expected_branch": fields.get("branch"),
        "expected_head": fields.get("head"),
    }
    record_repository = record.get("target_repository")
    if record_repository is None:
        record_repository = DEFAULT_REPOSITORY
    if record_repository != expected["target_repository"]:
        return False
    if not all(key in record for key in expected if key != "target_repository"):
        return False
    if type(record.get("target_issue")) is not int:
        return False
    for key, value in expected.items():
        if key == "target_repository":
            continue
        if record.get(key) != value:
            return False
    return True


def parse_bridge_inbox_request(line: str) -> dict[str, Any]:
    """Parse one standalone B1 inbox request marker."""
    if not isinstance(line, str):
        return {"result": "blocked", "errors": ["marker_not_string"]}
    text = line.strip()
    if "\n" in text or "\r" in text:
        return {"result": "blocked", "errors": ["marker_not_standalone"]}
    prefix = f"{REQUEST_MARKER} "
    if not text.startswith(prefix):
        return {"result": "blocked", "errors": ["missing_marker_prefix"]}

    fields, errors = _parse_marker_fields(text[len(prefix) :])
    if errors:
        return {"result": "blocked", "errors": errors}

    required = (
        "protocol",
        "request_id",
        "repo",
        "target_issue",
        "target_dispatch_request_id",
        "branch",
        "head",
        "expires",
        "action",
        "requested_by",
    )
    missing = [field for field in required if field not in fields]
    if missing:
        return {"result": "blocked", "errors": ["missing_fields"], "missing": missing}

    extras = sorted(set(fields) - set(required))
    if extras:
        return {"result": "blocked", "errors": ["unexpected_fields"], "extras": extras}

    try:
        target_issue = int(fields["target_issue"])
    except ValueError:
        return {"result": "blocked", "errors": ["target_issue_not_integer"]}
    fields["target_issue"] = target_issue  # type: ignore[assignment]
    return {"result": "success", "fields": fields}


def parse_chatgpt_dispatch_marker(line: str) -> dict[str, Any]:
    """Parse one standalone target dispatch marker for identity binding only."""
    if not isinstance(line, str):
        return {"result": "blocked", "errors": ["marker_not_string"]}
    text = line.strip()
    if "\n" in text or "\r" in text:
        return {"result": "blocked", "errors": ["marker_not_standalone"]}
    prefix = f"{DISPATCH_MARKER} "
    if not text.startswith(prefix):
        return {"result": "blocked", "errors": ["missing_marker_prefix"]}

    fields, errors = _parse_marker_fields(text[len(prefix) :])
    if errors:
        return {"result": "blocked", "errors": errors}

    required = (
        "protocol",
        "action",
        "issue",
        "repo",
        "branch",
        "head",
        "expires",
        "requested_by",
        "request_id",
    )
    missing = [field for field in required if field not in fields]
    if missing:
        return {"result": "blocked", "errors": ["missing_fields"], "missing": missing}

    optional = ("mode", "expected_state", "reason")
    extras = sorted(set(fields) - set(required) - set(optional))
    if extras:
        return {"result": "blocked", "errors": ["unexpected_fields"], "extras": extras}

    try:
        issue = int(fields["issue"])
    except ValueError:
        return {"result": "blocked", "errors": ["issue_not_integer"]}
    fields["issue"] = issue  # type: ignore[assignment]
    return {"result": "success", "fields": fields}


def check_local_readiness(repo_root: str | Path) -> LocalReadiness:
    """Inspect local state without repairing anything."""
    root = str(Path(repo_root).resolve())
    errors: list[str] = []

    branch = _git_output(root, "rev-parse", "--abbrev-ref", "HEAD", errors=errors)
    head = _git_output(root, "rev-parse", "HEAD", errors=errors)
    status = _git_output(root, "status", "--porcelain", errors=errors)
    clean = status == "" if status is not None else None
    staged = _git_output(root, "diff", "--cached", "--name-only", errors=errors)
    staged_clean = staged == "" if staged is not None else None
    top_level = _git_output(root, "rev-parse", "--show-toplevel", errors=errors)
    git_root_matches = (
        top_level is not None
        and os.path.normcase(os.path.normpath(top_level)) == os.path.normcase(os.path.normpath(root))
    )
    origin_url = _git_output(root, "remote", "get-url", "origin", errors=errors)
    origin_repository = _normalize_github_repository(origin_url) if origin_url else None

    gh_path = _resolve_gh_path()
    gh_available = gh_path is not None
    gh_authenticated = False
    gh_read_available = False
    if gh_path is None:
        errors.append("gh_missing")
    else:
        auth = _run_command([gh_path, "auth", "status"], cwd=root)
        gh_authenticated = auth.returncode == 0
        if not gh_authenticated:
            errors.append("gh_auth_unavailable")
        read = _run_command(
            [gh_path, "repo", "view", DEFAULT_REPOSITORY, "--json", "nameWithOwner"],
            cwd=root,
        )
        gh_read_available = read.returncode == 0
        if not gh_read_available:
            errors.append("gh_read_unavailable")

    return LocalReadiness(
        repo_root=root,
        branch=branch,
        head=head,
        clean=clean,
        gh_available=gh_available,
        gh_authenticated=gh_authenticated,
        gh_read_available=gh_read_available,
        errors=tuple(errors),
        origin_repository=origin_repository,
        git_root_matches=git_root_matches,
        staged_clean=staged_clean,
    )


class GitHubApiClient:
    """Minimal read-only GitHub client for one configured repository."""

    def __init__(
        self,
        repository: str,
        *,
        token: str | None = None,
        get_json: Callable[[list[str], str | None, bool], Any] | None = None,
    ) -> None:
        self.repository = repository
        self.token = token
        self._get_json = get_json or _github_get_json_with_gh

    def get_issue(self, issue_number: int) -> IssueRecord:
        payload = self._get_json(
            [f"repos/{self.repository}/issues/{issue_number}"],
            self.token,
            False,
        )
        return IssueRecord(
            number=int(payload["number"]),
            state=str(payload["state"]),
            body=str(payload.get("body") or ""),
        )

    def list_issue_comments(self, issue_number: int) -> list[CommentRecord]:
        payload = self._get_json(
            [
                f"repos/{self.repository}/issues/{issue_number}/comments",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                "-f",
                "per_page=100",
            ],
            self.token,
            True,
        )
        if payload and isinstance(payload[0], list):
            payload = [item for page in payload for item in page]
        comments = []
        for item in payload:
            comments.append(
                CommentRecord(
                    id=item["id"],
                    body=str(item.get("body") or ""),
                    author=str((item.get("user") or {}).get("login") or ""),
                )
            )
        return comments


def _base_summary(repository: str, inbox_issue: int, repo_root: str | Path) -> dict[str, Any]:
    return {
        "protocol": SUMMARY_PROTOCOL,
        "result": "blocked",
        "repository": repository,
        "control_repository": DEFAULT_REPOSITORY,
        "target_repository": repository,
        "configured_inbox_issue": inbox_issue,
        "repo_root": str(repo_root),
        "trusted_actors": list(TRUSTED_ACTORS),
        "allowed_actions": list(ALLOWED_ACTIONS),
        "fixed_inbox_read_performed": False,
        "target_issue_read_performed": False,
        "broad_issue_scan_performed": False,
        "latest_next_inference_performed": False,
        "dispatcher_invoked": False,
        "runner_invoked": False,
        "codex_invoked": False,
        "github_write_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "issue_closed": False,
        "label_changed": False,
        "pr_created": False,
        "merge_performed": False,
        "approval_consumed": False,
        "dry_run_result": "blocked",
        "validations": {},
        "blocked_reasons": [],
        "evaluated_at_utc": None,
        "current_request_count": 0,
        "consumed_request_count": 0,
        "expired_request_count": 0,
        "expired_historical_request_count": 0,
        "selected_request_state": None,
        "request_lifecycle": [],
        "next_recommended_action": "chatgpt_review",
    }


def _block(summary: dict[str, Any], reason: str) -> None:
    if reason not in summary["blocked_reasons"]:
        summary["blocked_reasons"].append(reason)
    summary["result"] = "blocked"
    summary["dry_run_result"] = "blocked"


def _collect_request_markers(
    inbox_issue: IssueRecord,
    comments: Iterable[CommentRecord],
) -> list[dict[str, Any]]:
    markers = []
    if inbox_issue.body.strip().startswith(REQUEST_MARKER):
        # Issue body text is not authoritative identity metadata for B1 requests.
        pass
    for comment in comments:
        body = comment.body.strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if len(lines) == 1 and lines[0].startswith(REQUEST_MARKER):
            markers.append(
                {
                    "line": lines[0],
                    "author": comment.author,
                    "comment_id": comment.id,
                }
            )
        elif any(line.startswith(REQUEST_MARKER) for line in lines):
            markers.append(
                {
                    "line": body,
                    "author": comment.author,
                    "comment_id": comment.id,
                }
            )
    return markers


def _collect_dispatch_markers(comments: Iterable[CommentRecord]) -> list[dict[str, Any]]:
    markers = []
    for comment in comments:
        body = comment.body.strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if len(lines) == 1 and lines[0].startswith(DISPATCH_MARKER):
            markers.append(
                {
                    "line": lines[0],
                    "author": comment.author,
                    "comment_id": comment.id,
                }
            )
        elif any(line.startswith(DISPATCH_MARKER) for line in lines):
            markers.append(
                {
                    "line": body,
                    "author": comment.author,
                    "comment_id": comment.id,
                }
            )
    return markers


def _parse_marker_fields(body: str) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    if not body:
        return fields, ["malformed_key_value"]
    for token in body.split(" "):
        if token == "" or not _FIELD_RE.match(token):
            return {}, ["malformed_key_value"]
        key, value = token.split("=", 1)
        if key in fields:
            return {}, ["duplicate_fields"]
        fields[key] = value
    return fields, []


def _validate_request_fields(
    fields: Mapping[str, Any],
    summary: dict[str, Any],
    now_utc: datetime,
    *,
    enforce_expiry: bool = True,
) -> None:
    checks = (
        (fields["protocol"] == REQUEST_PROTOCOL, "unsupported_protocol"),
        (_REQUEST_ID_RE.match(str(fields["request_id"])) is not None, "invalid_request_id"),
        (fields["repo"] in SUPPORTED_TARGET_REPOSITORIES, "unsupported_target_repository"),
        (fields["repo"] == summary["target_repository"], "wrong_repository"),
        (isinstance(fields["target_issue"], int) and fields["target_issue"] > 0, "invalid_target_issue"),
        (
            _REQUEST_ID_RE.match(str(fields["target_dispatch_request_id"])) is not None,
            "invalid_target_dispatch_request_id",
        ),
        (_BRANCH_RE.match(str(fields["branch"])) is not None, "invalid_branch"),
        (_SHA_RE.match(str(fields["head"])) is not None, "invalid_head"),
        (fields["action"] in ALLOWED_ACTIONS, "unsupported_action"),
        (fields["requested_by"] == "chatgpt", "requested_by_mismatch"),
    )
    for passed, reason in checks:
        if not passed:
            _block(summary, reason)

    if enforce_expiry:
        expires = _parse_utc_basic(str(fields["expires"]))
        if expires is None:
            _block(summary, "invalid_expiry")
        elif expires <= now_utc:
            _block(summary, "expired_request")


def _validate_target_dispatch_identity(
    comments: Iterable[CommentRecord],
    inbox_fields: Mapping[str, Any],
    summary: dict[str, Any],
    now_utc: datetime,
) -> None:
    markers = _collect_dispatch_markers(comments)
    matches = []
    for marker in markers:
        parsed = parse_chatgpt_dispatch_marker(marker["line"])
        if parsed["result"] != "success":
            _block(summary, "malformed_target_dispatch_marker")
            summary["target_dispatch_parse_errors"] = parsed["errors"]
            return
        fields = parsed["fields"]
        if fields["request_id"] == inbox_fields["target_dispatch_request_id"]:
            matches.append({"marker": marker, "fields": fields})

    if not matches:
        _block(summary, "target_dispatch_request_not_found")
        return
    if len(matches) > 1:
        _block(summary, "ambiguous_target_dispatch_request")
        summary["target_dispatch_match_count"] = len(matches)
        return

    marker = matches[0]["marker"]
    fields = matches[0]["fields"]
    summary["target_dispatch_comment_id"] = marker["comment_id"]
    summary["target_dispatch_author"] = marker["author"]
    if marker["author"] not in TRUSTED_ACTORS:
        _block(summary, "untrusted_target_dispatch_author")
    checks = (
        (fields["protocol"] == DISPATCH_PROTOCOL, "unsupported_target_dispatch_protocol"),
        (fields["issue"] == inbox_fields["target_issue"], "target_dispatch_issue_mismatch"),
        (fields["repo"] == inbox_fields["repo"], "target_dispatch_repo_mismatch"),
        (fields["branch"] == inbox_fields["branch"], "target_dispatch_branch_mismatch"),
        (fields["head"] == inbox_fields["head"], "target_dispatch_head_mismatch"),
        (fields["action"] == inbox_fields["action"], "target_dispatch_action_mismatch"),
        (fields["requested_by"] == "chatgpt", "target_dispatch_requested_by_mismatch"),
    )
    for passed, reason in checks:
        if not passed:
            _block(summary, reason)

    expires = _parse_utc_basic(str(fields["expires"]))
    if expires is None:
        _block(summary, "target_dispatch_invalid_expiry")
    elif expires <= now_utc:
        _block(summary, "target_dispatch_expired")


def _validate_local_readiness(
    readiness: LocalReadiness,
    fields: Mapping[str, Any],
    expected_repo_root: str | Path,
    summary: dict[str, Any],
) -> None:
    expected_root = str(Path(expected_repo_root).resolve())
    if readiness.repo_root != expected_root:
        _block(summary, "wrong_repo_root")
    if not readiness.git_root_matches:
        _block(summary, "target_not_git_repository_root")
    if readiness.origin_repository != fields["repo"]:
        _block(summary, "wrong_target_origin")
    if readiness.branch != fields["branch"]:
        _block(summary, "wrong_branch")
    if readiness.head != fields["head"]:
        _block(summary, "wrong_head")
    if fields["action"] == "run-reviewbundle" and readiness.clean is not True:
        _block(summary, "dirty_repository")
    if fields["action"] == "run-reviewbundle" and readiness.staged_clean is not True:
        _block(summary, "staged_files_present")
    if not readiness.gh_available:
        _block(summary, "missing_github_cli")
    if not readiness.gh_authenticated or not readiness.gh_read_available:
        _block(summary, "github_read_unavailable")
    for error in readiness.errors:
        summary.setdefault("local_readiness_errors", [])
        if error not in summary["local_readiness_errors"]:
            summary["local_readiness_errors"].append(error)


def _normalize_now(now_utc: datetime | None) -> datetime:
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_basic(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, UTC_BASIC_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _resolve_gh_path() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        portable = Path(user_profile) / "tools" / "gh-portable" / "bin" / "gh.exe"
        if portable.exists():
            return str(portable)
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        installed = Path(program_files) / "GitHub CLI" / "gh.exe"
        if installed.exists():
            return str(installed)
    return None


def _normalize_github_repository(url: str) -> str | None:
    value = url.strip().replace("\\", "/")
    patterns = (
        r"^https?://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<repo>[^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.match(pattern, value, flags=re.IGNORECASE)
        if match:
            repository = match.group("repo")
            return repository[:-4] if repository.lower().endswith(".git") else repository
    return None


def _git_output(root: str, *args: str, errors: list[str]) -> str | None:
    result = _run_command(["git", *args], cwd=root)
    if result.returncode != 0:
        errors.append(f"git_{args[0]}_failed")
        return None
    return result.stdout.strip()


def _run_command(command: list[str], *, cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=20,
    )


def _github_get_json_with_gh(args: list[str], token: str | None, paginate: bool) -> Any:
    gh_path = _resolve_gh_path()
    if gh_path is None:
        raise RuntimeError("gh_missing")
    command = [gh_path, "api", *args]
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=30,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError("gh_api_read_failed")
    payload = json.loads(result.stdout or "null")
    if paginate and not isinstance(payload, list):
        raise RuntimeError("gh_api_pagination_unexpected_payload")
    return payload
