from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "restore_course_computer_environment.ps1"
DOC = ROOT / "docs" / "COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md"


def test_recovery_script_is_visible_bounded_and_non_destructive():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "Read-Host" in text
    assert "@openai/codex" in text
    assert "https://api.github.com/repos/cli/cli/releases/latest" in text
    assert "tools\\gh-portable\\bin\\gh.exe" in text
    assert "gh auth login --web" in text
    assert "No Dispatcher, Runner, Codex task" in text

    forbidden_commands = [
        "local_runner.ps1",
        "local_dispatcher_v1.ps1",
        "local_runner_v1.ps1",
        "& git commit",
        "& git push",
        " gh issue close",
        " gh label",
        " gh pr create",
        " gh pr merge",
        "Register-ScheduledTask",
        "New-Service",
        "Set-ItemProperty",
    ]
    lowered = text.lower()
    for term in forbidden_commands:
        assert term.lower() not in lowered


def test_recovery_script_requires_real_repository_root():
    text = SCRIPT.read_text(encoding="utf-8")

    required = [
        "function Assert-RepositoryRoot",
        "rev-parse --show-toplevel",
        "repository subdirectory",
        "local-ai-workbench",
        "HarryWhite-TW[\\\\/]+local-ai-workbench",
    ]
    for phrase in required:
        assert phrase in text


def test_recovery_script_prefers_native_codex_and_rejects_ps1_only():
    text = SCRIPT.read_text(encoding="utf-8")

    required = [
        '"codex.exe", "codex.cmd", "codex.bat", "codex"',
        '".exe" { 0 }',
        '".cmd" { 1 }',
        '".bat" { 2 }',
        '$extension -ne ".ps1" -and $_.CommandType -eq "Application"',
        'GetExtension($codexPath).ToLowerInvariant() -ne ".ps1"',
    ]
    for phrase in required:
        assert phrase in text


def test_recovery_script_reruns_auth_after_login_before_ready():
    text = SCRIPT.read_text(encoding="utf-8")

    required = [
        "function Test-GhAuth",
        "$ghAuthenticated = Test-GhAuth -GhPath $ghPath",
        "& $ghPath auth login --web",
        "throw \"GitHub CLI authentication is required. 'gh auth status' still fails after login.\"",
        "$ghReady = (Test-VersionReady $ghVersion) -and $ghAuthenticated",
        "gh=$(if ($ghReady) { 'ready' } else { 'blocked' })",
    ]
    for phrase in required:
        assert phrase in text


def test_recovery_doc_covers_logout_and_authority_boundary():
    text = DOC.read_text(encoding="utf-8")

    required = [
        ".\\scripts\\restore_course_computer_environment.ps1",
        "what it installs",
        "what it only verifies",
        "restore-card course computer",
        "Manual Fallback Steps",
        "%USERPROFILE%\\tools\\gh-portable\\bin\\gh.exe",
        "Shared-Computer Logout Checklist",
        "restore card does not replace explicit logout",
        "environment support tooling only",
    ]
    lowered = text.lower()
    for phrase in required:
        assert phrase.lower() in lowered
