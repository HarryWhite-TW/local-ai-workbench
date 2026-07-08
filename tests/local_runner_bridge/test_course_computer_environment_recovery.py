import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "restore_course_computer_environment.ps1"
REVIEW_SCRIPT = ROOT / "scripts" / "course_environment_restore_review.ps1"
DOC = ROOT / "docs" / "COURSE_COMPUTER_ENVIRONMENT_RECOVERY.md"


def _powershell():
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    assert found, "PowerShell is required for recovery script tests"
    return found


def _ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def _write_function_harness(tmp_path):
    text = SCRIPT.read_text(encoding="utf-8")
    marker = 'Write-Host "Local AI Workbench course-computer environment recovery"'
    assert marker in text
    harness = tmp_path / "recovery_functions.ps1"
    harness.write_text(text.split(marker, 1)[0], encoding="utf-8")
    return harness


def _run_powershell(script):
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )


def _write_cmd(path, body):
    path.write_text("@echo off\r\n" + textwrap.dedent(body).strip() + "\r\n", encoding="utf-8")


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


def test_native_helper_is_bounded_and_argument_list_free():
    text = SCRIPT.read_text(encoding="utf-8")

    required = [
        "function Invoke-NativeCommand",
        "1> $stdoutPath 2> $stderrPath",
        "$exitCode = $LASTEXITCODE",
        "$ErrorActionPreference = $previousErrorActionPreference",
        "Remove-Item -LiteralPath $tempRoot -Recurse -Force",
        "LaunchError",
    ]
    for phrase in required:
        assert phrase in text

    assert "ProcessStartInfo.ArgumentList" not in text
    assert ".ArgumentList" not in text


def test_invoke_version_captures_successful_exe_version(tmp_path):
    harness = _write_function_harness(tmp_path)
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            Invoke-Version -Command $env:ComSpec -Arguments @('/d', '/c', 'echo exe version 1.2.3')
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "exe version 1.2.3"


def test_invoke_version_captures_successful_cmd_version(tmp_path):
    harness = _write_function_harness(tmp_path)
    tool = tmp_path / "version.cmd"
    _write_cmd(tool, "echo cmd version 2.0.0\nexit /b 0")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            Invoke-Version -Command {_ps(tool)} -Arguments @()
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cmd version 2.0.0"


def test_invoke_version_preserves_actual_nonzero_exit_code(tmp_path):
    harness = _write_function_harness(tmp_path)
    tool = tmp_path / "fail.cmd"
    _write_cmd(tool, "echo failure text 1>&2\nexit /b 17")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            Invoke-Version -Command {_ps(tool)} -Arguments @()
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "version check failed: exit_code=17"


def test_invoke_version_stderr_does_not_replace_success_exit_code(tmp_path):
    harness = _write_function_harness(tmp_path)
    tool = tmp_path / "stderr-success.cmd"
    _write_cmd(tool, "echo warning text 1>&2\necho clean version\nexit /b 0")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            Invoke-Version -Command {_ps(tool)} -Arguments @()
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean version"


def test_invoke_version_launch_failure_remains_blocked(tmp_path):
    harness = _write_function_harness(tmp_path)
    missing = tmp_path / "missing-tool.exe"
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            $before = $ErrorActionPreference
            $version = Invoke-Version -Command {_ps(missing)} -Arguments @('--version')
            Write-Output $version
            Write-Output "preference=$ErrorActionPreference"
            if ($ErrorActionPreference -ne $before) {{ throw "preference was not restored" }}
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert "version check failed:" in result.stdout
    assert "preference=Stop" in result.stdout


def test_native_helper_removes_temporary_stdout_stderr_files(tmp_path):
    harness = _write_function_harness(tmp_path)
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    tool = tmp_path / "version.cmd"
    _write_cmd(tool, "echo clean version\necho warning text 1>&2\nexit /b 0")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            $env:TEMP = {_ps(temp_root)}
            $env:TMP = {_ps(temp_root)}
            $result = Invoke-NativeCommand -Command {_ps(tool)} -Arguments @()
            Write-Output "exit=$($result.ExitCode)"
            $leftovers = Get-ChildItem -LiteralPath {_ps(temp_root)} -Filter 'lawb-native-*' -Force
            Write-Output "leftovers=$($leftovers.Count)"
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert "exit=0" in result.stdout
    assert "leftovers=0" in result.stdout


def test_unauthenticated_gh_status_returns_false_without_terminating(tmp_path):
    harness = _write_function_harness(tmp_path)
    gh = tmp_path / "gh.cmd"
    _write_cmd(gh, "echo not logged in 1>&2\nexit /b 4")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            $ErrorActionPreference = "Stop"
            $authenticated = Test-GhAuth -GhPath {_ps(gh)}
            Write-Output "authenticated=$authenticated"
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert "authenticated=False" in result.stdout


def test_unauthenticated_flow_reaches_login_confirmation_and_decline_blocks(tmp_path):
    harness = _write_function_harness(tmp_path)
    gh = tmp_path / "gh.cmd"
    _write_cmd(gh, "echo not logged in 1>&2\nexit /b 4")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            function Confirm-Step($Prompt) {{
                Write-Host "CONFIRM:$Prompt"
                return $false
            }}
            $ghAuthenticated = Test-GhAuth -GhPath {_ps(gh)}
            if (-not $ghAuthenticated) {{
                Write-Output "GitHub CLI is not authenticated. The normal browser login flow can be started now."
                if (Confirm-Step "Run 'gh auth login --web' for interactive browser authentication?") {{
                    throw "unexpected login"
                }}
                else {{
                    throw "GitHub CLI authentication is required. Login skipped by user."
                }}
            }}
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode != 0
    assert "CONFIRM:Run 'gh auth login --web' for interactive browser authentication?" in result.stdout
    assert "Login skipped by user" in result.stderr


def test_authenticated_gh_status_skips_login_confirmation(tmp_path):
    harness = _write_function_harness(tmp_path)
    gh = tmp_path / "gh.cmd"
    _write_cmd(gh, "echo logged in\nexit /b 0")
    runner = tmp_path / "run.ps1"
    runner.write_text(
        textwrap.dedent(
            f"""
            . {_ps(harness)}
            function Confirm-Step($Prompt) {{
                throw "unexpected confirmation: $Prompt"
            }}
            $ghAuthenticated = Test-GhAuth -GhPath {_ps(gh)}
            if (-not $ghAuthenticated) {{
                Confirm-Step "Run 'gh auth login --web' for interactive browser authentication?"
            }}
            Write-Output "authenticated=$ghAuthenticated"
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_powershell(runner)

    assert result.returncode == 0, result.stderr
    assert "authenticated=True" in result.stdout


def test_ready_gh_and_codex_paths_do_not_trigger_reinstall_prompts():
    text = SCRIPT.read_text(encoding="utf-8")

    gh_install_check = text.index("if (-not (Test-Path -LiteralPath $ghPath))")
    gh_install = text.index("Install-PortableGitHubCli -TargetPath $ghPath")
    codex_install_check = text.index("if (-not $codexPath) {")
    codex_install = text.index("& $npmPath install -g @openai/codex")

    assert gh_install_check < gh_install
    assert codex_install_check < codex_install
    assert "Install the official npm package @openai/codex globally?" in text
    assert "Portable GitHub CLI is missing at $TargetPath" in text


def test_recovery_script_introduces_no_dispatcher_runner_codex_task_or_write_actions():
    text = SCRIPT.read_text(encoding="utf-8").lower()

    forbidden = [
        "pollonce",
        "local_dispatcher_v1.ps1",
        "local_runner_v1.ps1",
        "codex exec",
        "codex run",
        "git add",
        "git commit",
        "git push",
        "gh issue",
        "gh pr",
        "gh label",
    ]
    for phrase in forbidden:
        assert phrase not in text


def test_recovery_doc_covers_logout_and_authority_boundary():
    text = DOC.read_text(encoding="utf-8")

    required = [
        ".\\scripts\\restore_course_computer_environment.ps1",
        ".\\scripts\\course_environment_restore_review.ps1",
        "what it installs",
        "what it only verifies",
        "2026-07-08 incident note",
        "AUDIT -> APPLY -> JSON review -> focused repair -> Host Check -> STOP",
        "Do not manually activate the venv during recovery",
        "Bootstrap READY differs from Host Check READY",
        "git_identity_missing",
        "must not silently set `git config user.name`",
        "PATH and fresh-shell drift should be presented separately from tool usability",
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


def test_restore_review_wrapper_has_expected_parameters_and_evidence_outputs():
    text = REVIEW_SCRIPT.read_text(encoding="utf-8")

    required = [
        "[string]$RepoRoot",
        "[switch]$Apply",
        '[string]$ExpectedRepository = "HarryWhite-TW/local-ai-workbench"',
        "[string]$ExpectedBranch",
        "[string]$ExpectedHead",
        "[string]$EvidenceRoot",
        "bootstrap_audit.json",
        "bootstrap_apply.json",
        "bootstrap_post_restore_audit.json",
        "focused_pytest.stdout.txt",
        "host_check.json",
        "course_environment_restore_review_summary.json",
        "final_git_state",
        "status_porcelain",
        "staged_files",
        "1> $StdoutPath 2> $StderrPath",
        "--basetemp",
    ]
    for phrase in required:
        assert phrase in text


def test_restore_review_wrapper_records_final_git_evidence_in_summary():
    text = REVIEW_SCRIPT.read_text(encoding="utf-8")

    required = [
        '$finalGitState = [ordered]@{',
        '@("status", "--porcelain=v1", "-uall")',
        '@("diff", "--cached", "--name-only")',
        '@("rev-parse", "HEAD")',
        '@("branch", "--show-current")',
        "final_git_state = $finalGitState",
    ]
    for phrase in required:
        assert phrase in text


def test_restore_review_wrapper_stop_marker_and_safety_boundary_are_explicit():
    text = REVIEW_SCRIPT.read_text(encoding="utf-8")

    required = [
        "COURSE_ENVIRONMENT_RESTORE_REVIEW_DONE",
        "NO_LIVE_ACCEPTANCE_NO_DISPATCHER_NO_RUNNER_NO_CODEX_TASK_NO_GITHUB_WRITE",
        "live_acceptance_invoked = $false",
        "dispatcher_invoked = $false",
        "runner_invoked = $false",
        "codex_task_invoked = $false",
        "github_write_performed = $false",
        "gh_auth_token_invoked = $false",
        "permanent_path_modified = $false",
        "git_identity_written = $false",
    ]
    for phrase in required:
        assert phrase in text


def test_restore_review_wrapper_avoids_power_shell_and_forbidden_command_mistakes():
    text = REVIEW_SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "<<EOF" not in text
    assert "@'" not in text
    assert '"@' not in text
    assert "$Host" not in text

    forbidden = [
        "git commit",
        "git push",
        "gh pr create",
        "gh pr merge",
        "gh issue close",
        "gh auth token",
        "codex exec",
        "codex review",
        "local_dispatcher_v1.ps1",
        "local_runner_v1.ps1",
    ]
    for phrase in forbidden:
        assert phrase not in lowered
