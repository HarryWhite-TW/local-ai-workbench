import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v1.ps1"


def _runner_core() -> str:
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index('\nif ($Mode -eq "ApprovalStateDiagnostic")')
    return source[start:end]


def _powershell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local_runner_v1 tests")
    return shell


def run_timeout_guard_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "timeout_guard_test.ps1"
    script.write_text(
        _runner_core()
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


def test_resolve_codex_command_prefers_cmd_over_ps1(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $commands = @(
            [pscustomobject]@{ CommandType = "ExternalScript"; Source = "C:/fake/codex.ps1"; Definition = "C:/fake/codex.ps1" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.cmd"; Definition = "C:/fake/codex.cmd" }
        )
        $resolved = Resolve-CodexCommand -Commands $commands
        if ($resolved.Source -ne "C:/fake/codex.cmd") {
            throw "Expected codex.cmd, got $($resolved.Source)"
        }
        """,
    )
    assert_success(result)


def test_resolve_codex_command_prefers_exe_over_cmd(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $commands = @(
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.cmd"; Definition = "C:/fake/codex.cmd" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.exe"; Definition = "C:/fake/codex.exe" }
        )
        $resolved = Resolve-CodexCommand -Commands $commands
        if ($resolved.Source -ne "C:/fake/codex.exe") {
            throw "Expected codex.exe, got $($resolved.Source)"
        }
        """,
    )
    assert_success(result)


def test_resolve_codex_command_rejects_ps1_only(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $commands = @(
            [pscustomobject]@{ CommandType = "ExternalScript"; Source = "C:/fake/codex.ps1"; Definition = "C:/fake/codex.ps1" }
        )

        $failed = $false
        try {
            Resolve-CodexCommand -Commands $commands | Out-Null
        }
        catch {
            $failed = $true
            if ($_.Exception.Message -notmatch "only PowerShell script wrappers") {
                throw "Unexpected error message: $($_.Exception.Message)"
            }
        }

        if (-not $failed) {
            throw "Expected Resolve-CodexCommand to fail for ps1-only candidates."
        }
        """,
    )
    assert_success(result)


def test_captured_native_process_times_out_and_records_command_output_and_duration(tmp_path):
    child = tmp_path / "slow_child.ps1"
    child.write_text(
        textwrap.dedent(
            """
            Write-Output "stdout-before-timeout"
            [Console]::Error.WriteLine("stderr-before-timeout")
            Start-Sleep -Seconds 10
            """
        ).strip(),
        encoding="utf-8",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $result = Invoke-CapturedNativeProcess `
            -FilePath {str(_powershell())!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {str(tmp_path)!r} `
            -StandardInput "" `
            -TimeoutSeconds 1 `
            -Action "timeout test"

        if (-not $result.TimedOut) {{ throw "Expected timeout" }}
        if ($result.ExitCode -ne 124) {{ throw "Expected timeout exit code 124, got $($result.ExitCode)" }}
        if ($result.TimeoutSeconds -ne 1) {{ throw "Expected timeout duration 1" }}
        if ($result.CommandLine -notmatch "slow_child\\.ps1") {{ throw "Expected command line to name child script: $($result.CommandLine)" }}
        if ($result.LastStdoutLine -ne "stdout-before-timeout") {{ throw "Wrong stdout line: $($result.LastStdoutLine)" }}
        if ($result.LastStderrLine -ne "stderr-before-timeout") {{ throw "Wrong stderr line: $($result.LastStderrLine)" }}
        if (-not $result.StopAttempted) {{ throw "Expected process stop attempt" }}
        if (@($result.StoppedProcessIds).Count -lt 1) {{ throw "Expected at least one stopped process id" }}
        if (Get-Process -Id $result.ProcessId -ErrorAction SilentlyContinue) {{ throw "Timed-out child process is still running" }}
        """,
    )
    assert_success(result)


def test_captured_native_process_non_timeout_path_preserves_exit_code_and_output(tmp_path):
    child = tmp_path / "fast_child.cmd"
    child.write_text(
        textwrap.dedent(
            """
            @echo off
            echo fast stdout
            echo fast stderr 1>&2
            exit /b 7
            """
        ).strip(),
        encoding="utf-8",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $result = Invoke-CapturedNativeProcess `
            -FilePath "cmd.exe" `
            -Arguments @("/c", {str(child)!r}) `
            -WorkingDirectory {str(tmp_path)!r} `
            -StandardInput "" `
            -TimeoutSeconds 10 `
            -Action "fast test"

        if ($result.TimedOut) {{ throw "Did not expect timeout" }}
        if ($result.ExitCode -ne 7) {{ throw "Expected exit code 7, got $($result.ExitCode)" }}
        if ($result.LastStdoutLine -ne "fast stdout") {{ throw "Wrong stdout line: $($result.LastStdoutLine)" }}
        if ($result.LastStderrLine -ne "fast stderr") {{ throw "Wrong stderr line: $($result.LastStderrLine)" }}
        if ($result.StopAttempted) {{ throw "Non-timeout path must not stop processes" }}
        """,
    )
    assert_success(result)


def test_timeout_summary_reports_fail_closed_partial_candidate_and_no_followup_actions(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $result = [pscustomobject]@{
            ExitCode = 124
            TimedOut = $true
            TimeoutSeconds = 3
            CommandLine = "codex.exe --ask-for-approval never exec --sandbox workspace-write -C . -"
            LastStdoutLine = "last out"
            LastStderrLine = "last err"
            StopAttempted = $true
            StoppedProcessIds = @(111, 222)
        }
        $summary = New-ChildProcessReviewBundleSummary -Result $result -FinalStatus " M scripts/local_runner_v1.ps1"
        foreach ($expected in @(
            "child_process_timed_out=true",
            "child_process_timeout_seconds=3",
            "last_stdout_line=last out",
            "last_stderr_line=last err",
            "partial_candidate_exists=true",
            "fail_closed_on_timeout=true",
            "no_tests_after_timeout=true",
            "no_smoke_after_timeout=true",
            "no_commit_push_close_after_timeout=true",
            "stopped_process_ids=111,222"
        )) {
            if (-not $summary.Contains($expected)) {
                throw "Expected summary to contain $expected. Summary: $summary"
            }
        }
        """,
    )
    assert_success(result)
