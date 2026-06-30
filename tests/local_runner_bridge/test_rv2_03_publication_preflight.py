import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.rv2_03_publication_preflight_cli as cli_module
from local_runner_bridge.b4d_smoke_manifest import (
    MANIFEST_PROTOCOL,
    MAX_EXPIRY_WINDOW,
    SAFETY_FIELDS,
    canonical_dispatch_marker,
    canonical_inbox_marker,
    validate_manifest,
)
from local_runner_bridge.bridge_operator_b1 import CommentRecord, IssueRecord, LocalReadiness
from local_runner_bridge.bridge_operator_b3 import read_processed_request_ids
from local_runner_bridge.rv2_03_publication_preflight import (
    MAX_EXECUTION_TTL_SECONDS,
    PROTOCOL,
    run_publication_preflight,
)

NOW = datetime(2026, 6, 27, 4, 0, 0, tzinfo=timezone.utc)
HEAD = "b" * 40
REPO_ROOT = r"C:\Users\harry\Desktop\local-ai-workbench"


def utc_basic(value):
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def expected_approvals(manifest):
    return {
        "approval_a": {
            "github_comment_writes": [
                {
                    "kind": "chatgpt_dispatch",
                    "issue": manifest["target_issue"],
                    "body": manifest["markers"]["dispatch"],
                },
                {
                    "kind": "bridge_inbox_request",
                    "issue": 147,
                    "body": manifest["markers"]["inbox"],
                },
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
            "allowed_paths": manifest["allowed_paths"],
            "expected_result_writes": [
                {"kind": "runner_review_bundle", "issue": manifest["target_issue"]},
                {"kind": "dispatcher_lawbrunner_result", "issue": manifest["target_issue"]},
            ],
        },
    }


def valid_manifest(*, expires=None, target_issue=200, inbox_request_id="rv2-a3-inbox"):
    manifest = {
        "protocol": MANIFEST_PROTOCOL,
        "repo": "HarryWhite-TW/local-ai-workbench",
        "inbox_issue": 147,
        "target_issue": target_issue,
        "branch": "master",
        "head": HEAD,
        "action": "run-reviewbundle",
        "requested_by": "chatgpt",
        "expires": expires or utc_basic(NOW + timedelta(minutes=20)),
        "inbox_request_id": inbox_request_id,
        "dispatch_request_id": f"{inbox_request_id}-dispatch",
        "allowed_paths": ["docs/a3.md"],
        "markers": {},
        "approvals": {},
        "safety": {field: True for field in SAFETY_FIELDS},
    }
    manifest["markers"] = {
        "dispatch": canonical_dispatch_marker(manifest),
        "inbox": canonical_inbox_marker(manifest),
    }
    manifest["approvals"] = expected_approvals(manifest)
    return manifest


def manifest_with_expiry(expires):
    return valid_manifest(expires=utc_basic(expires))


def inbox_comment_from(manifest, *, comment_id=1, author="HarryWhite-TW", expires=None):
    copy = dict(manifest)
    if expires is not None:
        copy["expires"] = utc_basic(expires)
    return CommentRecord(id=comment_id, body=canonical_inbox_marker(copy), author=author)


def dispatch_comment_from(manifest, *, comment_id=10, author="HarryWhite-TW"):
    return CommentRecord(id=comment_id, body=canonical_dispatch_marker(manifest), author=author)


class FakeGitHub:
    def __init__(self, *, inbox_comments=None, target_comments=None, fail=False):
        self.inbox_comments = inbox_comments if inbox_comments is not None else []
        self.target_comments = target_comments if target_comments is not None else []
        self.fail = fail
        self.issues_read = []
        self.comments_read = []

    def get_issue(self, issue_number):
        self.issues_read.append(issue_number)
        if self.fail:
            raise RuntimeError("network")
        return IssueRecord(number=issue_number, state="open", body="")

    def list_issue_comments(self, issue_number):
        self.comments_read.append(issue_number)
        if self.fail:
            raise RuntimeError("network")
        if issue_number == 147:
            return self.inbox_comments
        return self.target_comments


def ready(root):
    return LocalReadiness(
        repo_root=str(Path(root).resolve()),
        branch="master",
        head=HEAD,
        clean=True,
        gh_available=True,
        gh_authenticated=True,
        gh_read_available=True,
        errors=(),
    )


def readiness(**overrides):
    values = {
        "repo_root": str(Path(REPO_ROOT).resolve()),
        "branch": "master",
        "head": HEAD,
        "clean": True,
        "gh_available": True,
        "gh_authenticated": True,
        "gh_read_available": True,
        "errors": (),
    }
    values.update(overrides)
    return LocalReadiness(**values)


class CountingChecker:
    def __init__(self, result=None, exc=None):
        self.result = result or readiness()
        self.exc = exc
        self.calls = []

    def __call__(self, root):
        self.calls.append(root)
        if self.exc is not None:
            raise self.exc
        return self.result


def run(tmp_path, manifest=None, client=None):
    return run_publication_preflight(
        manifest or valid_manifest(),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=client or FakeGitHub(),
        local_checker=ready,
        now_utc=NOW,
    )


def write_processed(path, request_id):
    payload = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "request_id": request_id,
        "lifecycle_state": "CONSUMED",
        "target_issue": 200,
        "target_dispatch_request_id": f"{request_id}-dispatch",
        "requested_action": "run-reviewbundle",
        "expected_branch": "master",
        "expected_head": HEAD,
    }
    (path / "processed_requests.jsonl").write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def assert_safe(summary):
    assert summary["protocol"] == PROTOCOL
    assert summary["result"] == "success"
    assert summary["publication_safe"] is True
    assert summary["blocked_reasons"] == []
    assert summary["approval_a"]["github_comment_writes"]
    assert len(summary["approval_a"]["github_comment_writes"]) == 2
    assert summary["next_required_action"] == "human_review_approval_a"
    assert all(value is False for value in summary["safety"].values())


def assert_blocked(summary, reason):
    assert summary["result"] == "blocked"
    assert summary["publication_safe"] is False
    assert reason in summary["blocked_reasons"]
    assert summary["approval_a"] is None
    assert summary["next_required_action"] == "stop_and_review"
    assert all(value is False for value in summary["safety"].values())


def assert_cli_error(payload, code):
    assert payload["protocol"] == PROTOCOL
    assert payload["result"] == "blocked"
    assert payload["publication_safe"] is False
    assert payload["approval_a"] is None
    assert payload["next_required_action"] == "stop_and_review"
    assert code in payload["blocked_reasons"]
    assert payload["errors"][0]["code"] == code
    assert all(value is False for value in payload["safety"].values())


def test_no_inbox_request_is_publication_safe(tmp_path):
    client = FakeGitHub(inbox_comments=[])

    summary = run(tmp_path, client=client)

    assert_safe(summary)
    assert summary["remaining_ttl_seconds"] == MAX_EXECUTION_TTL_SECONDS
    assert summary["inbox_telemetry"]["b1_blocked_reasons"] == ["missing_request"]
    assert summary["inbox_telemetry"]["current_request_count"] == 0
    assert client.comments_read == [147]


def test_no_request_path_calls_local_checker(tmp_path):
    checker = CountingChecker()

    summary = run_publication_preflight(
        valid_manifest(),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=FakeGitHub(inbox_comments=[]),
        local_checker=checker,
        now_utc=NOW,
    )

    assert_safe(summary)
    assert checker.calls == [REPO_ROOT]
    assert summary["local_readiness_telemetry"]["check_performed"] is True


def test_consumed_only_is_publication_safe(tmp_path):
    manifest = valid_manifest()
    write_processed(tmp_path, manifest["inbox_request_id"])
    client = FakeGitHub(inbox_comments=[inbox_comment_from(manifest)])

    summary = run(tmp_path, manifest, client)

    assert_safe(summary)
    assert summary["processed_request_count"] == 1
    assert summary["inbox_telemetry"]["b1_blocked_reasons"] == [
        "no_current_request_after_consumption"
    ]
    assert summary["inbox_telemetry"]["consumed_request_count"] == 1
    assert client.comments_read == [147]


def test_consumed_identity_mismatch_blocks_publication(tmp_path):
    manifest = valid_manifest()
    payload = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "request_id": manifest["inbox_request_id"],
        "lifecycle_state": "CONSUMED",
        "target_issue": 999,
        "target_dispatch_request_id": manifest["dispatch_request_id"],
        "requested_action": manifest["action"],
        "expected_branch": manifest["branch"],
        "expected_head": manifest["head"],
    }
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    client = FakeGitHub(inbox_comments=[inbox_comment_from(manifest)])

    summary = run(tmp_path, manifest, client)

    assert_blocked(summary, "processed_request_identity_mismatch")
    assert summary["publication_safe"] is False
    assert summary["approval_a"] is None
    assert summary["inbox_telemetry"]["b1_blocked_reasons"] == [
        "processed_request_identity_mismatch"
    ]
    assert client.comments_read == [147]


def test_consumed_only_calls_local_checker(tmp_path):
    manifest = valid_manifest()
    write_processed(tmp_path, manifest["inbox_request_id"])
    checker = CountingChecker()

    summary = run_publication_preflight(
        manifest,
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=FakeGitHub(inbox_comments=[inbox_comment_from(manifest)]),
        local_checker=checker,
        now_utc=NOW,
    )

    assert_safe(summary)
    assert checker.calls == [REPO_ROOT]


def test_expired_only_is_publication_safe(tmp_path):
    manifest = valid_manifest()
    client = FakeGitHub(
        inbox_comments=[inbox_comment_from(manifest, expires=NOW - timedelta(seconds=1))]
    )

    summary = run(tmp_path, manifest, client)

    assert_safe(summary)
    assert summary["inbox_telemetry"]["b1_blocked_reasons"] == ["missing_current_request"]
    assert summary["inbox_telemetry"]["expired_request_count"] == 1


def test_expired_only_calls_local_checker(tmp_path):
    manifest = valid_manifest()
    checker = CountingChecker()

    summary = run_publication_preflight(
        manifest,
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=FakeGitHub(
            inbox_comments=[inbox_comment_from(manifest, expires=NOW - timedelta(seconds=1))]
        ),
        local_checker=checker,
        now_utc=NOW,
    )

    assert_safe(summary)
    assert checker.calls == [REPO_ROOT]


def test_consumed_plus_expired_without_current_is_publication_safe(tmp_path):
    consumed = valid_manifest(inbox_request_id="rv2-a3-consumed")
    expired = valid_manifest(inbox_request_id="rv2-a3-expired", target_issue=201)
    write_processed(tmp_path, consumed["inbox_request_id"])
    client = FakeGitHub(
        inbox_comments=[
            inbox_comment_from(consumed, comment_id=1),
            inbox_comment_from(expired, comment_id=2, expires=NOW - timedelta(seconds=1)),
        ]
    )

    summary = run(tmp_path, valid_manifest(), client)

    assert_safe(summary)
    assert summary["inbox_telemetry"]["consumed_request_count"] == 1
    assert summary["inbox_telemetry"]["expired_request_count"] == 1
    assert len(summary["inbox_telemetry"]["request_lifecycle"]) == 2


def test_consumed_plus_expired_calls_local_checker(tmp_path):
    consumed = valid_manifest(inbox_request_id="rv2-a3-consumed")
    expired = valid_manifest(inbox_request_id="rv2-a3-expired", target_issue=201)
    write_processed(tmp_path, consumed["inbox_request_id"])
    checker = CountingChecker()

    summary = run_publication_preflight(
        valid_manifest(),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=FakeGitHub(
            inbox_comments=[
                inbox_comment_from(consumed, comment_id=1),
                inbox_comment_from(expired, comment_id=2, expires=NOW - timedelta(seconds=1)),
            ]
        ),
        local_checker=checker,
        now_utc=NOW,
    )

    assert_safe(summary)
    assert checker.calls == [REPO_ROOT]


@pytest.mark.parametrize(
    ("ready_value", "reason"),
    [
        (readiness(repo_root=r"C:\other\repo"), "wrong_repo_root"),
        (readiness(branch="other-branch"), "wrong_branch"),
        (readiness(head="a" * 40), "wrong_head"),
        (readiness(clean=False), "dirty_repository"),
        (readiness(gh_available=False), "missing_github_cli"),
        (readiness(gh_authenticated=False), "github_read_unavailable"),
        (readiness(gh_read_available=False), "github_read_unavailable"),
    ],
)
def test_local_readiness_failures_block_before_github_read(tmp_path, ready_value, reason):
    checker = CountingChecker(ready_value)
    client = FakeGitHub(inbox_comments=[inbox_comment_from(valid_manifest())])

    summary = run_publication_preflight(
        valid_manifest(),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=client,
        local_checker=checker,
        now_utc=NOW,
    )

    assert_blocked(summary, reason)
    assert checker.calls == [REPO_ROOT]
    assert client.issues_read == []
    assert client.comments_read == []


def test_local_checker_exception_blocks_safely_without_github_read(tmp_path):
    checker = CountingChecker(exc=RuntimeError("secret readiness failure"))
    client = FakeGitHub(inbox_comments=[inbox_comment_from(valid_manifest())])

    summary = run_publication_preflight(
        valid_manifest(),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=client,
        local_checker=checker,
        now_utc=NOW,
    )

    assert_blocked(summary, "local_readiness_unavailable")
    assert "secret readiness failure" not in json.dumps(summary)
    assert checker.calls == [REPO_ROOT]
    assert client.issues_read == []
    assert client.comments_read == []


def test_one_current_blocks_with_selected_marker_telemetry(tmp_path):
    manifest = valid_manifest()
    client = FakeGitHub(
        inbox_comments=[inbox_comment_from(manifest, comment_id=123)],
        target_comments=[dispatch_comment_from(manifest)],
    )

    summary = run(tmp_path, manifest, client)

    assert_blocked(summary, "current_request_already_present")
    assert summary["inbox_telemetry"]["current_request_count"] == 1
    assert summary["inbox_telemetry"]["selected_inbox_comment_id"] == 123
    assert summary["inbox_telemetry"]["selected_request_id"] == manifest["inbox_request_id"]
    assert summary["inbox_telemetry"]["selected_expiry"] == manifest["expires"]


def test_multiple_current_blocks_with_full_lifecycle_telemetry(tmp_path):
    first = valid_manifest(inbox_request_id="rv2-a3-current-a", target_issue=200)
    second = valid_manifest(inbox_request_id="rv2-a3-current-b", target_issue=201)
    client = FakeGitHub(
        inbox_comments=[
            inbox_comment_from(first, comment_id=1),
            inbox_comment_from(second, comment_id=2),
        ]
    )

    summary = run(tmp_path, first, client)

    assert_blocked(summary, "multiple_current_requests")
    assert summary["inbox_telemetry"]["current_request_count"] == 2
    assert [item["inbox_comment_id"] for item in summary["inbox_telemetry"]["request_lifecycle"]] == [
        1,
        2,
    ]


def test_malformed_marker_blocks(tmp_path):
    client = FakeGitHub(
        inbox_comments=[
            CommentRecord(
                id=1,
                body=canonical_inbox_marker(valid_manifest()) + "\nextra",
                author="HarryWhite-TW",
            )
        ]
    )

    summary = run(tmp_path, client=client)

    assert_blocked(summary, "malformed_marker")


def test_untrusted_marker_blocks(tmp_path):
    manifest = valid_manifest()
    client = FakeGitHub(inbox_comments=[inbox_comment_from(manifest, author="other-user")])

    summary = run(tmp_path, manifest, client)

    assert_blocked(summary, "untrusted_inbox_author")


def test_github_read_failure_blocks(tmp_path):
    summary = run(tmp_path, client=FakeGitHub(fail=True))

    assert_blocked(summary, "github_read_unavailable")


def b1_wait_summary(**overrides):
    values = {
        "result": "blocked",
        "blocked_reasons": ["missing_request"],
        "current_request_count": 0,
        "fixed_inbox_read_performed": True,
        "github_read_available": True,
        "repository": "HarryWhite-TW/local-ai-workbench",
        "configured_inbox_issue": 147,
    }
    values.update(overrides)
    return values


def run_with_b1_summary(tmp_path, b1_summary):
    return run_publication_preflight(
        valid_manifest(),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=FakeGitHub(),
        local_checker=ready,
        now_utc=NOW,
        b1_runner=lambda **_kwargs: b1_summary,
    )


def test_safe_real_b1_shape_passes(tmp_path):
    summary = run_with_b1_summary(tmp_path, b1_wait_summary())

    assert_safe(summary)


@pytest.mark.parametrize(
    "b1_summary",
    [
        b1_wait_summary(result="success", blocked_reasons=["missing_request"]),
        b1_wait_summary(fixed_inbox_read_performed=None),
        b1_wait_summary(github_read_available=None),
        b1_wait_summary(github_read_available=False),
        b1_wait_summary(repository="other/repo"),
        b1_wait_summary(configured_inbox_issue=148),
        {
            "blocked_reasons": ["missing_request"],
            "current_request_count": 0,
            "fixed_inbox_read_performed": True,
            "github_read_available": True,
            "repository": "HarryWhite-TW/local-ai-workbench",
            "configured_inbox_issue": 147,
        },
        b1_wait_summary(blocked_reasons=["missing_request", "missing_current_request"]),
        b1_wait_summary(current_request_count="0"),
    ],
)
def test_inconsistent_b1_safe_wait_shape_blocks_as_unexpected(tmp_path, b1_summary):
    summary = run_with_b1_summary(tmp_path, b1_summary)

    assert_blocked(summary, "unexpected_b1_result")


def test_corrupted_processed_history_blocks_before_publication_or_github_read(tmp_path):
    (tmp_path / "processed_requests.jsonl").write_text("{not-json}\n", encoding="utf-8")
    client = FakeGitHub(inbox_comments=[inbox_comment_from(valid_manifest())])

    summary = run(tmp_path, client=client)

    assert_blocked(summary, "corrupted_processed_history")
    assert client.issues_read == []
    assert client.comments_read == []


def test_semantically_invalid_processed_history_blocks_before_github_read(tmp_path):
    payload = {
        "protocol": "lawb.bridge_operator_b3_processed_request.v1",
        "request_id": None,
    }
    (tmp_path / "processed_requests.jsonl").write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    client = FakeGitHub(inbox_comments=[inbox_comment_from(valid_manifest())])

    summary = run(tmp_path, client=client)

    assert_blocked(summary, "corrupted_processed_history")
    assert client.issues_read == []
    assert client.comments_read == []


def test_invalid_manifest_blocks_without_github_read(tmp_path):
    manifest = valid_manifest()
    manifest["repo"] = "other/repo"
    client = FakeGitHub(inbox_comments=[inbox_comment_from(valid_manifest())])
    checker = CountingChecker()

    summary = run_publication_preflight(
        manifest,
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=client,
        local_checker=checker,
        now_utc=NOW,
    )

    assert_blocked(summary, "invalid_manifest")
    assert summary["manifest_validation"]["valid"] is False
    assert checker.calls == []
    assert client.issues_read == []
    assert client.comments_read == []


def test_expired_manifest_blocks_without_github_read(tmp_path):
    client = FakeGitHub(inbox_comments=[inbox_comment_from(valid_manifest())])

    summary = run(tmp_path, manifest_with_expiry(NOW - timedelta(seconds=1)), client)

    assert_blocked(summary, "invalid_manifest")
    assert client.issues_read == []
    assert client.comments_read == []


def test_remaining_ttl_exactly_20_minutes_is_accepted(tmp_path):
    summary = run(tmp_path, manifest_with_expiry(NOW + timedelta(minutes=20)))

    assert_safe(summary)
    assert summary["remaining_ttl_seconds"] == 1200


def test_remaining_ttl_20_minutes_plus_one_second_blocks_without_github_read(tmp_path):
    client = FakeGitHub()
    checker = CountingChecker()

    summary = run_publication_preflight(
        manifest_with_expiry(NOW + timedelta(minutes=20, seconds=1)),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=client,
        local_checker=checker,
        now_utc=NOW,
    )

    assert_blocked(summary, "execution_ttl_too_long")
    assert checker.calls == []
    assert client.issues_read == []
    assert client.comments_read == []


def test_remaining_ttl_1200_seconds_plus_one_microsecond_blocks_without_truncation(tmp_path):
    evaluated_at = NOW.replace(microsecond=999999)
    checker = CountingChecker()
    client = FakeGitHub()

    summary = run_publication_preflight(
        manifest_with_expiry(NOW + timedelta(minutes=20, seconds=1)),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=client,
        local_checker=checker,
        now_utc=evaluated_at,
    )

    assert_blocked(summary, "execution_ttl_too_long")
    assert summary["remaining_ttl_seconds"] == pytest.approx(1200.000001)
    assert checker.calls == []
    assert client.issues_read == []
    assert client.comments_read == []


def test_microsecond_evaluated_at_does_not_allow_ttl_truncation(tmp_path):
    evaluated_at = NOW - timedelta(microseconds=500000)
    checker = CountingChecker()

    summary = run_publication_preflight(
        manifest_with_expiry(NOW + timedelta(minutes=20)),
        repo_root=REPO_ROOT,
        state_dir=tmp_path,
        github_client=FakeGitHub(),
        local_checker=checker,
        now_utc=evaluated_at,
    )

    assert_blocked(summary, "execution_ttl_too_long")
    assert summary["remaining_ttl_seconds"] == pytest.approx(1200.5)
    assert checker.calls == []


@pytest.mark.parametrize("offset", [timedelta(seconds=0), timedelta(seconds=-1)])
def test_remaining_ttl_zero_or_negative_blocks_without_github_read(tmp_path, offset):
    client = FakeGitHub()

    summary = run(tmp_path, manifest_with_expiry(NOW + offset), client)

    assert_blocked(summary, "invalid_manifest")
    assert client.issues_read == []
    assert client.comments_read == []


def test_historical_four_hour_manifest_validator_remains_unchanged():
    result = validate_manifest(
        valid_manifest(expires=utc_basic(NOW + MAX_EXPIRY_WINDOW)),
        now=NOW,
    )

    assert result["valid"] is True


def test_approval_a_preview_appears_only_when_safe(tmp_path):
    safe = run(tmp_path / "safe", client=FakeGitHub())
    current_manifest = valid_manifest()
    blocked = run(
        tmp_path / "blocked",
        current_manifest,
        FakeGitHub(
            inbox_comments=[inbox_comment_from(current_manifest)],
            target_comments=[dispatch_comment_from(current_manifest)],
        ),
    )

    assert safe["approval_a"] is not None
    assert blocked["approval_a"] is None


def test_public_b3_processed_history_helper_is_read_only(tmp_path):
    write_processed(tmp_path, "processed-a")
    path = tmp_path / "processed_requests.jsonl"
    before = path.read_bytes()

    assert read_processed_request_ids(path) == {"processed-a"}
    assert path.read_bytes() == before


def test_cli_success_output_and_exit_code(tmp_path, capsys, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    monkeypatch.setattr(
        cli_module,
        "run_publication_preflight",
        lambda *_, **__: {
            "protocol": PROTOCOL,
            "publication_safe": True,
            "result": "success",
        },
    )

    returncode = cli_module.main(["--manifest", str(path), "--repo-root", REPO_ROOT])
    captured = capsys.readouterr()

    assert returncode == 0
    assert json.loads(captured.out)["publication_safe"] is True


def test_cli_blocked_output_and_exit_code(tmp_path, capsys, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    monkeypatch.setattr(
        cli_module,
        "run_publication_preflight",
        lambda *_, **__: {
            "protocol": PROTOCOL,
            "publication_safe": False,
            "result": "blocked",
        },
    )

    returncode = cli_module.main(["--manifest", str(path), "--repo-root", REPO_ROOT])
    captured = capsys.readouterr()

    assert returncode == 2
    assert json.loads(captured.out)["publication_safe"] is False


def test_cli_invalid_arguments_use_a3_protocol(capsys):
    returncode = cli_module.main(["--manifest", "only-manifest.json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_cli_error(payload, "invalid_cli_arguments")


def test_cli_manifest_read_failure_uses_a3_protocol(tmp_path, capsys):
    path = tmp_path / "missing.json"

    returncode = cli_module.main(["--manifest", str(path), "--repo-root", REPO_ROOT])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_cli_error(payload, "manifest_read_failed")


def test_cli_malformed_json_uses_a3_protocol(tmp_path, capsys):
    path = tmp_path / "manifest.json"
    path.write_text("{not-json}", encoding="utf-8")

    returncode = cli_module.main(["--manifest", str(path), "--repo-root", REPO_ROOT])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_cli_error(payload, "malformed_json")


def test_cli_rejects_duplicate_json_key(tmp_path, capsys):
    path = tmp_path / "manifest.json"
    text = json.dumps(valid_manifest(), separators=(",", ":"))
    path.write_text(text.replace('"target_issue":200', '"target_issue":200,"target_issue":201'), encoding="utf-8")

    returncode = cli_module.main(["--manifest", str(path), "--repo-root", REPO_ROOT])
    captured = capsys.readouterr()

    assert returncode == 2
    payload = json.loads(captured.out)
    assert_cli_error(payload, "duplicate_json_key")


def test_cli_internal_failure(tmp_path, capsys, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise RuntimeError("secret failure detail")

    monkeypatch.setattr(cli_module, "run_publication_preflight", fail)

    returncode = cli_module.main(["--manifest", str(path), "--repo-root", REPO_ROOT])
    captured = capsys.readouterr()

    assert returncode == 1
    payload = json.loads(captured.out)
    assert_cli_error(payload, "internal_preflight_failure")
    assert "secret failure detail" not in captured.out
