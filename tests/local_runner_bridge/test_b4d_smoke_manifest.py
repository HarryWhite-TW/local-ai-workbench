import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.b4d_smoke_manifest as manifest_module
import local_runner_bridge.b4d_smoke_manifest_cli as cli_module
from local_runner_bridge.b4d_smoke_manifest import (
    B2_COMMAND,
    MANIFEST_PROTOCOL,
    SAFETY_FIELDS,
    canonical_dispatch_marker,
    canonical_inbox_marker,
    validate_manifest,
)

NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)
HEAD = "a" * 40


def valid_manifest():
    base = {
        "protocol": MANIFEST_PROTOCOL,
        "repo": "HarryWhite-TW/local-ai-workbench",
        "inbox_issue": 147,
        "target_issue": 200,
        "branch": "master",
        "head": HEAD,
        "action": "run-reviewbundle",
        "requested_by": "chatgpt",
        "expires": "20260624T120000Z",
        "inbox_request_id": "b4d-inbox-200",
        "dispatch_request_id": "b4d-dispatch-200",
        "allowed_paths": ["docs/smoke.md", r"src\local_runner_bridge\sample.py"],
        "markers": {},
        "approvals": {},
        "safety": {field: True for field in SAFETY_FIELDS},
    }
    base["markers"] = {
        "dispatch": canonical_dispatch_marker(base),
        "inbox": canonical_inbox_marker(base),
    }
    base["approvals"] = expected_approvals(base)
    return base


def expected_approvals(manifest):
    normalized = [path.replace("\\", "/") for path in manifest["allowed_paths"]]
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
            "allowed_paths": normalized,
            "expected_result_writes": [
                {"kind": "runner_review_bundle", "issue": manifest["target_issue"]},
                {"kind": "dispatcher_lawbrunner_result", "issue": manifest["target_issue"]},
            ],
        },
    }


def validate(value):
    return validate_manifest(value, now=NOW)


def error_codes(result):
    return [error["code"] for error in result["errors"]]


def assert_invalid_without_partial_result(result, code):
    assert result["valid"] is False
    assert code in error_codes(result)
    assert result["canonical_manifest"] is None
    assert result["preview"] is None


def test_valid_manifest_and_preview():
    result = validate(valid_manifest())

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == []
    assert result["canonical_manifest"]["allowed_paths"] == [
        "docs/smoke.md",
        "src/local_runner_bridge/sample.py",
    ]
    assert result["preview"]["approval_b"]["command"] == B2_COMMAND
    assert result["preview"]["next_required_action"] == "human_review_approval_a"


def test_canonical_markers_are_exact_and_ordered():
    manifest = valid_manifest()

    assert manifest["markers"]["dispatch"] == (
        "CHATGPT-DISPATCH protocol=lawb.dispatch.v1 action=run-reviewbundle "
        f"issue=200 repo=HarryWhite-TW/local-ai-workbench branch=master head={HEAD} "
        "expires=20260624T120000Z requested_by=chatgpt request_id=b4d-dispatch-200"
    )
    assert manifest["markers"]["inbox"] == (
        "BRIDGE-INBOX-REQUEST protocol=lawb.bridge_inbox_request.v1 "
        "request_id=b4d-inbox-200 repo=HarryWhite-TW/local-ai-workbench "
        "target_issue=200 target_dispatch_request_id=b4d-dispatch-200 "
        f"branch=master head={HEAD} expires=20260624T120000Z "
        "action=run-reviewbundle requested_by=chatgpt"
    )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("repo", "other/repo", "fixed_value_mismatch"),
        ("inbox_issue", 148, "fixed_value_mismatch"),
        ("branch", "feature/x", "fixed_value_mismatch"),
        ("head", "A" * 40, "invalid_head"),
        ("head", "a" * 39, "invalid_head"),
        ("expires", "20260623T110000Z", "expired_manifest"),
        ("expires", "20261399T999999Z", "invalid_expiry"),
        ("inbox_request_id", "x", "invalid_request_id"),
        ("dispatch_request_id", "bad id", "invalid_request_id"),
    ],
)
def test_invalid_scalar_contracts(field, value, code):
    manifest = valid_manifest()
    manifest[field] = value
    result = validate(manifest)
    assert_invalid_without_partial_result(result, code)


def test_target_equals_inbox():
    manifest = valid_manifest()
    manifest["target_issue"] = 147
    assert "target_equals_inbox" in error_codes(validate(manifest))


def test_same_request_ids():
    manifest = valid_manifest()
    manifest["dispatch_request_id"] = manifest["inbox_request_id"]
    assert "request_ids_not_distinct" in error_codes(validate(manifest))


@pytest.mark.parametrize(
    ("marker", "suffix", "code"),
    [
        ("dispatch", " extra=yes", "dispatch_marker_mismatch"),
        ("inbox", " extra=yes", "inbox_marker_mismatch"),
        ("dispatch", " prose", "dispatch_marker_mismatch"),
        ("inbox", "\nprose", "inbox_marker_mismatch"),
    ],
)
def test_marker_mismatch_and_extra_prose(marker, suffix, code):
    manifest = valid_manifest()
    manifest["markers"][marker] += suffix
    assert code in error_codes(validate(manifest))


@pytest.mark.parametrize(
    ("paths", "code"),
    [
        ([], "invalid_allowed_paths"),
        ([r"C:\repo\file.txt"], "absolute_allowed_path"),
        (["../file.txt"], "unsafe_path_segment"),
        (["docs/*.md"], "wildcard_allowed_path"),
        ([".git/config"], "git_path_forbidden"),
        (["docs/file.md", r"docs\file.md"], "duplicate_allowed_path"),
        (["docs//file.md"], "empty_path_segment"),
    ],
)
def test_invalid_allowed_paths(paths, code):
    manifest = valid_manifest()
    manifest["allowed_paths"] = paths
    assert_invalid_without_partial_result(validate(manifest), code)


@pytest.mark.parametrize(
    ("paths", "code"),
    [
        (["docs/file.txt:stream"], "path_colon_forbidden"),
        (["docs/file\x00.txt"], "path_nul_forbidden"),
        (["docs/file\tname.txt"], "path_control_character"),
        (["docs/file\nname.txt"], "path_control_character"),
        (["docs/file\x1fname.txt"], "path_control_character"),
        ([" docs/file.txt"], "path_outer_whitespace"),
        (["docs/file.txt "], "path_outer_whitespace"),
        (["docs/file./name.txt"], "path_segment_trailing_space_or_period"),
        (["docs/file /name.txt"], "path_segment_trailing_space_or_period"),
        (["docs/ file/name.txt"], "path_segment_whitespace"),
        (["docs/CON/file.txt"], "windows_reserved_device"),
        (["docs/NUL.txt"], "windows_reserved_device"),
        (["Docs/file.md", "docs/file.md"], "duplicate_allowed_path"),
        ([r"SRC\Example.py", "src/example.py"], "duplicate_allowed_path"),
    ],
)
def test_windows_path_authority_rejections(paths, code):
    manifest = valid_manifest()
    manifest["allowed_paths"] = paths
    assert_invalid_without_partial_result(validate(manifest), code)


def test_valid_mixed_case_path_preserves_case_and_normalizes_slashes():
    manifest = valid_manifest()
    manifest["allowed_paths"] = [r"Docs\Smoke\File.MD"]
    manifest["approvals"] = expected_approvals(manifest)

    result = validate(manifest)

    assert result["valid"] is True
    assert result["canonical_manifest"]["allowed_paths"] == ["Docs/Smoke/File.MD"]
    assert result["preview"]["approval_b"]["allowed_paths"] == ["Docs/Smoke/File.MD"]


def test_missing_unknown_and_false_safety_fields():
    missing = valid_manifest()
    del missing["safety"]["no_retry"]
    unknown = valid_manifest()
    unknown["safety"]["allow_retry"] = True
    false_value = valid_manifest()
    false_value["safety"]["no_retry"] = False

    assert "missing_field" in error_codes(validate(missing))
    assert "unknown_field" in error_codes(validate(unknown))
    assert "safety_not_true" in error_codes(validate(false_value))


def test_approval_a_extra_write_is_rejected():
    manifest = valid_manifest()
    manifest["approvals"]["approval_a"]["github_comment_writes"].append(
        {"kind": "extra", "issue": 200, "body": "extra"}
    )
    assert "approval_structure_mismatch" in error_codes(validate(manifest))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda approval: approval.update({"retry": True}),
        lambda approval: approval.update({"another_request": True}),
        lambda approval: approval.update({"commit": True}),
        lambda approval: approval.update({"codex_execution": "twice"}),
        lambda approval: approval["expected_result_writes"].append(
            {"kind": "extra", "issue": 200}
        ),
    ],
)
def test_approval_b_extra_authority_is_rejected(mutation):
    manifest = valid_manifest()
    mutation(manifest["approvals"]["approval_b"])
    assert "approval_structure_mismatch" in error_codes(validate(manifest))


def test_unknown_top_level_field():
    manifest = valid_manifest()
    manifest["publish"] = True
    assert "unknown_field" in error_codes(validate(manifest))


def test_deterministic_sha256_and_preview():
    first = validate(valid_manifest())
    reordered = json.loads(json.dumps(valid_manifest(), sort_keys=True))
    second = validate(reordered)

    assert first["preview"] == second["preview"]
    canonical = first["canonical_manifest"]
    compact = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert first["preview"]["manifest_sha256"] == hashlib.sha256(compact.encode("utf-8")).hexdigest()
    assert first["preview"]["forbidden_actions"] == list(manifest_module.FORBIDDEN_ACTIONS)


def run_cli(tmp_path, content, capsys):
    path = tmp_path / "manifest.json"
    path.write_text(content, encoding="utf-8")
    returncode = cli_module.main(["--manifest", str(path)])
    captured = capsys.readouterr()
    return returncode, captured


def duplicate_json(base, old, new):
    text = json.dumps(base, separators=(",", ":"))
    assert old in text
    return text.replace(old, new, 1)


@pytest.mark.parametrize(
    "content",
    [
        lambda manifest: duplicate_json(
            manifest,
            '"target_issue":200',
            '"target_issue":200,"target_issue":201',
        ),
        lambda manifest: duplicate_json(
            manifest,
            '"dispatch":"CHATGPT-DISPATCH',
            '"dispatch":"duplicate","dispatch":"CHATGPT-DISPATCH',
        ),
        lambda manifest: duplicate_json(
            manifest,
            '"approval_b":{',
            '"approval_b":{},"approval_b":{',
        ),
        lambda manifest: duplicate_json(
            manifest,
            '"no_retry":true',
            '"no_retry":true,"no_retry":false',
        ),
    ],
)
def test_cli_rejects_duplicate_json_keys_at_any_nesting_level(tmp_path, capsys, content):
    returncode, captured = run_cli(tmp_path, content(valid_manifest()), capsys)
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_invalid_without_partial_result(payload, "duplicate_json_key")
    assert "Traceback" not in captured.err


def test_cli_valid_exit_zero(tmp_path, capsys):
    returncode, captured = run_cli(tmp_path, json.dumps(valid_manifest()), capsys)
    payload = json.loads(captured.out)
    assert returncode == 0
    assert payload["valid"] is True


def test_cli_invalid_exit_two(tmp_path, capsys):
    manifest = valid_manifest()
    manifest["repo"] = "other/repo"
    returncode, captured = run_cli(tmp_path, json.dumps(manifest), capsys)
    payload = json.loads(captured.out)
    assert returncode == 2
    assert payload["valid"] is False


def test_cli_malformed_json_is_structured(tmp_path, capsys):
    returncode, captured = run_cli(tmp_path, "{", capsys)
    payload = json.loads(captured.out)
    assert returncode == 2
    assert payload["errors"][0]["code"] == "malformed_json"
    assert "Traceback" not in captured.err


def test_cli_missing_manifest_is_structured_exit_two(capsys):
    returncode = cli_module.main([])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_invalid_without_partial_result(payload, "invalid_cli_arguments")
    assert "Traceback" not in captured.err


def test_cli_unknown_option_is_structured_exit_two(capsys):
    returncode = cli_module.main(["--unknown"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_invalid_without_partial_result(payload, "invalid_cli_arguments")
    assert "Traceback" not in captured.err


def test_cli_manifest_read_failure_is_structured_exit_two(tmp_path, capsys):
    returncode = cli_module.main(["--manifest", str(tmp_path / "missing.json")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 2
    assert_invalid_without_partial_result(payload, "manifest_read_failed")


def test_cli_unexpected_validation_failure_is_structured_exit_one(tmp_path, capsys, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

    def fail(_manifest):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(cli_module, "validate_manifest", fail)
    returncode = cli_module.main(["--manifest", str(path)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert returncode == 1
    assert_invalid_without_partial_result(payload, "internal_validation_failure")
    assert "sensitive internal detail" not in captured.out
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("request_id", "valid"),
    [
        ("a12", True),
        ("a" + "b" * 127, True),
        ("A0._:-z", True),
        ("ab", False),
        ("a" + "b" * 128, False),
        ("é12", False),
        ("a 2", False),
        ("a/2", False),
    ],
)
def test_request_id_parity_boundaries(request_id, valid):
    manifest = valid_manifest()
    manifest["inbox_request_id"] = request_id
    manifest["markers"]["inbox"] = canonical_inbox_marker(manifest)
    manifest["approvals"] = expected_approvals(manifest)

    result = validate(manifest)

    assert result["valid"] is valid
    if not valid:
        assert_invalid_without_partial_result(result, "invalid_request_id")


def test_validation_source_has_no_external_execution_or_network_capabilities():
    source = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (manifest_module, cli_module)
    )
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import socket",
        "from socket",
        "os.system",
        "popen(",
    )
    lowered = source.lower()
    for term in forbidden:
        assert term.lower() not in lowered


def test_validation_does_not_mutate_input():
    manifest = valid_manifest()
    original = deepcopy(manifest)
    validate(manifest)
    assert manifest == original
