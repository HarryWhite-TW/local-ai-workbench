from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "course_environment_restore_review.ps1"


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_audit_only_and_complete_recovery_are_explicit():
    text = source()
    assert "[switch]$CompleteRecovery" in text
    assert "if ($CompleteRecovery -and $auditPayload" in text
    assert "if ($Apply)" not in text


def test_complete_recovery_uses_fresh_post_audit_truth():
    text = source()
    assert "Get-LayerOneStatus" in text
    assert "if ($PostAuditPayload -and $PostAuditPayload.overall_status)" in text
    assert "historical_action_failures" in text
    assert "superseded_action_failures" in text
    assert "current_blockers" in text


def test_recovery_preserves_process_local_and_no_runtime_boundaries():
    text = source()
    for phrase in (
        "function Add-PathEntry",
            "& $gitPath config --local user.name",
            "& $gitPath config --local user.email",
        "auth login --web",
        "gh_auth_token_invoked = $false",
        "permanent_path_modified = $false",
        "dispatcher_invoked = $false",
        "runner_invoked = $false",
        "codex_task_invoked = $false",
        "github_write_performed = $false",
    ):
        assert phrase in text
    assert "config --global" not in text
    assert "setx" not in text.lower()


def test_captured_commands_always_report_artifact_metadata():
    text = source()
    for phrase in (
        "New-Item -ItemType File -Force -Path $StdoutPath",
        "New-Item -ItemType File -Force -Path $StderrPath",
        "stdout_bytes",
        "stderr_bytes",
        "first_safe_error",
        "started_at",
        "ended_at",
    ):
        assert phrase in text
