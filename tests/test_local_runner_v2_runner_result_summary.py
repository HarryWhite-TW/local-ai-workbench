import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v2.ps1"
MARKER = "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1"
ALLOWED_VALIDATION_STATUSES = {"passed", "failed", "not_run", "warning", "reported"}
REQUIRED_FIELDS = {
    "schema",
    "repo",
    "issue",
    "action",
    "result",
    "branch",
    "head",
    "selected_issue",
    "review_id",
    "diff_fingerprint",
    "files_fingerprint",
    "changed_files",
    "validations",
    "safety",
    "next_recommended_action",
}
REQUIRED_SAFETY_FLAGS = {
    "no_stage",
    "no_commit",
    "no_push",
    "no_issue_close",
    "no_label",
    "no_pr",
    "no_merge",
    "no_approval_chaining",
}


def _runner_core() -> str:
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index("\ntry {")
    return source[start:end]


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local_runner_v2 tests")
    return shell


def run_summary_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "runner_result_summary_test.ps1"
    script.write_text(
        _runner_core()
        + textwrap.dedent(
            """

            $Repo = "HarryWhite-TW/local-ai-workbench"
            """
        )
        + "\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    return subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def assert_success(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def extract_summary(stdout: str) -> tuple[list[str], dict]:
    lines = stdout.splitlines()
    marker_index = lines.index(MARKER)
    assert lines[marker_index + 1].startswith("{")

    json_lines = []
    depth = 0
    started = False
    for line in lines[marker_index + 1 :]:
        json_lines.append(line)
        depth += line.count("{") - line.count("}")
        started = started or "{" in line
        if started and depth == 0:
            break

    return lines, json.loads("\n".join(json_lines))


def test_runner_result_summary_marker_is_followed_immediately_by_parseable_json(tmp_path):
    result = run_summary_script(
        tmp_path,
        """
        Write-RunnerResultSummary -Issue 81 -Action "run-reviewbundle" -Result "success" -Branch "master" -Head "abc123" -SelectedIssue 81
        """,
    )
    assert_success(result)

    lines, summary = extract_summary(result.stdout)
    assert lines[lines.index(MARKER) + 1].startswith("{")
    assert summary["action"] == "run-reviewbundle"


def test_runner_result_summary_has_required_fields_and_exact_schema(tmp_path):
    result = run_summary_script(
        tmp_path,
        """
        Write-RunnerResultSummary -Issue 81 -Action "push-dryrun" -Result "success" -Branch "master" -Head "abc123" -SelectedIssue 81
        """,
    )
    assert_success(result)

    _, summary = extract_summary(result.stdout)
    assert set(summary) == REQUIRED_FIELDS
    assert summary["schema"] == "lawb.runner_result.v1"
    assert summary["repo"] == "HarryWhite-TW/local-ai-workbench"


def test_runner_result_summary_validation_entries_are_structured(tmp_path):
    result = run_summary_script(
        tmp_path,
        """
        $validation = @{ git_status_clean = (New-RunnerValidationResult -Status "passed" -Summary "clean") }
        Write-RunnerResultSummary -Issue 81 -Action "push-dryrun" -Result "success" -Branch "master" -Head "abc123" -SelectedIssue 81 -ValidationOverrides $validation
        """,
    )
    assert_success(result)

    _, summary = extract_summary(result.stdout)
    assert summary["validations"]
    for validation in summary["validations"].values():
        assert set(validation) == {"status", "summary"}
        assert validation["status"] in ALLOWED_VALIDATION_STATUSES
        assert isinstance(validation["summary"], str)
        assert validation["summary"]


def test_runner_result_summary_safety_flags_are_booleans(tmp_path):
    result = run_summary_script(
        tmp_path,
        """
        Write-RunnerResultSummary -Issue 81 -Action "push-once" -Result "success" -Branch "master" -Head "abc123" -SelectedIssue 81 -SafetyOverrides @{ no_push = $false }
        """,
    )
    assert_success(result)

    _, summary = extract_summary(result.stdout)
    assert set(summary["safety"]) == REQUIRED_SAFETY_FLAGS
    for value in summary["safety"].values():
        assert isinstance(value, bool)
    assert summary["safety"]["no_push"] is False


def test_runner_result_summary_changed_files_array_and_next_action(tmp_path):
    result = run_summary_script(
        tmp_path,
        """
        Write-RunnerResultSummary -Issue 81 -Action "run-reviewbundle" -Result "success" -Branch "master" -Head "abc123" -SelectedIssue 81 -ChangedFilesText "docs/RUNNER_V2.md`nscripts/local_runner_v2.ps1"
        """,
    )
    assert_success(result)

    _, summary = extract_summary(result.stdout)
    assert summary["changed_files"] == [
        "docs/RUNNER_V2.md",
        "scripts/local_runner_v2.ps1",
    ]
    assert summary["next_recommended_action"] == "chatgpt_review"
