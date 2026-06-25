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
        encoding="utf-8-sig",
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


def test_resolve_github_cli_command_uses_portable_path_when_program_files_missing(tmp_path):
    portable = tmp_path / "tools" / "gh-portable" / "bin" / "gh.exe"
    portable.parent.mkdir(parents=True)
    portable.write_text("fake gh", encoding="utf-8")

    missing_default = tmp_path / "missing-program-files-gh.exe"

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $resolved = Resolve-GitHubCliCommand `
            -Commands @() `
            -DefaultPath "{missing_default.as_posix()}" `
            -PortablePath "{portable.as_posix()}" `
            -ExtraCandidatePaths @()

        $actual = [System.IO.Path]::GetFullPath($resolved)
        $expected = [System.IO.Path]::GetFullPath("{portable.as_posix()}")
        if ($actual -ne $expected) {{
            throw "Expected portable gh path $expected, got $actual"
        }}
        """,
    )
    assert_success(result)


def test_resolve_github_cli_command_prefers_get_command_over_portable_path(tmp_path):
    command_gh = tmp_path / "path-gh" / "gh.exe"
    command_gh.parent.mkdir(parents=True)
    command_gh.write_text("fake gh from path", encoding="utf-8")

    portable = tmp_path / "tools" / "gh-portable" / "bin" / "gh.exe"
    portable.parent.mkdir(parents=True)
    portable.write_text("fake portable gh", encoding="utf-8")

    missing_default = tmp_path / "missing-program-files-gh.exe"

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $commands = @(
            [pscustomobject]@{{ CommandType = "Application"; Source = "{command_gh.as_posix()}"; Definition = "{command_gh.as_posix()}" }}
        )

        $resolved = Resolve-GitHubCliCommand `
            -Commands $commands `
            -DefaultPath "{missing_default.as_posix()}" `
            -PortablePath "{portable.as_posix()}" `
            -ExtraCandidatePaths @()

        $actual = [System.IO.Path]::GetFullPath($resolved)
        $expected = [System.IO.Path]::GetFullPath("{command_gh.as_posix()}")
        if ($actual -ne $expected) {{
            throw "Expected PATH gh path $expected, got $actual"
        }}
        """,
    )
    assert_success(result)


def test_resolve_github_cli_command_rejects_missing_candidates(tmp_path):
    missing_default = tmp_path / "missing-program-files-gh.exe"
    missing_portable = tmp_path / "tools" / "gh-portable" / "bin" / "gh.exe"

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $failed = $false
        try {{
            Resolve-GitHubCliCommand `
                -Commands @() `
                -DefaultPath "{missing_default.as_posix()}" `
                -PortablePath "{missing_portable.as_posix()}" `
                -ExtraCandidatePaths @() | Out-Null
        }}
        catch {{
            $failed = $true
            if ($_.Exception.Message -notmatch "GitHub CLI was not found") {{
                throw "Unexpected error message: $($_.Exception.Message)"
            }}
        }}

        if (-not $failed) {{
            throw "Expected Resolve-GitHubCliCommand to fail when no candidates exist."
        }}
        """,
    )
    assert_success(result)


def test_resolve_codex_command_prefers_cmd_over_ps1(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $commands = @(
            [pscustomobject]@{ CommandType = "ExternalScript"; Source = "C:/fake/codex.ps1"; Definition = "C:/fake/codex.ps1" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex"; Definition = "C:/fake/codex" },
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
        if ($resolved.FilePath -ne "C:/fake/codex.exe") {
            throw "Expected direct exe FilePath, got $($resolved.FilePath)"
        }
        if (@($resolved.ArgumentPrefix).Count -ne 0) {
            throw "Direct exe must not have an argument prefix."
        }
        """,
    )
    assert_success(result)


def test_resolved_cmd_launch_spec_executes_production_composition_without_real_codex(tmp_path):
    helper = tmp_path / "fake_codex_helper.ps1"
    helper.write_text(
        textwrap.dedent(
            """
            $inputStream = [Console]::OpenStandardInput()
            $memory = New-Object System.IO.MemoryStream
            $buffer = New-Object byte[] 1024
            while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $memory.Write($buffer, 0, $count)
            }
            [Console]::Out.WriteLine("STDINHEX:" + [BitConverter]::ToString($memory.ToArray()))
            [Console]::Error.Write("FAKE-CODEX-STDERR")
            """
        ).strip(),
        encoding="utf-8-sig",
    )
    launcher = tmp_path / "fake codex.cmd"
    launcher.write_text(
        textwrap.dedent(
            f"""
            @echo off
            setlocal
            :args
            if "%~1"=="" goto stdin
            echo ARG:%~1
            shift
            goto args
            :stdin
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{helper}"
            exit /b %ERRORLEVEL%
            """
        ).strip(),
        encoding="ascii",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $commands = @(
            [pscustomobject]@{{
                CommandType = "Application"
                Source = {launcher.as_posix()!r}
                Definition = {launcher.as_posix()!r}
            }}
        )
        $resolved = Resolve-CodexCommand -Commands $commands
        $codexArgs = @(
            "--ask-for-approval", "never", "exec", "--sandbox",
            "workspace-write", "-C", ".", "-"
        )
        $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $prompt = "PROMPT " + [string][char]0x5C08 + [string][char]0x6848
        $result = Invoke-CapturedNativeProcess `
            -FilePath $resolved.FilePath `
            -Arguments (@($resolved.ArgumentPrefix) + $codexArgs) `
            -WorkingDirectory {tmp_path.as_posix()!r} `
            -StandardInput $prompt `
            -StandardInputEncoding $strictUtf8 `
            -StandardOutputEncoding $strictUtf8 `
            -StandardErrorEncoding $strictUtf8 `
            -TimeoutSeconds 10 `
            -Action "fake codex cmd integration"

        if ($resolved.Source -ne {launcher.as_posix()!r}) {{
            throw "Resolver did not preserve selected source."
        }}
        if ($resolved.FilePath -ne $env:COMSPEC) {{
            throw "Expected cmd launcher through COMSPEC, got $($resolved.FilePath)"
        }}
        if ($result.ExitCode -ne 0) {{ throw "Fake cmd launcher failed: $($result.Stderr)" }}
        $argumentLines = @($result.Stdout -split "`r?`n" | Where-Object {{ $_ -like "ARG:*" }})
        if ($argumentLines.Count -ne $codexArgs.Count) {{
            throw "Expected $($codexArgs.Count) arguments exactly once, got $($argumentLines.Count): $($argumentLines -join ',')"
        }}
        for ($index = 0; $index -lt $codexArgs.Count; $index += 1) {{
            if ($argumentLines[$index] -ne "ARG:$($codexArgs[$index])") {{
                throw "Argument mismatch at $index`: $($argumentLines[$index])"
            }}
        }}
        $expectedHex = [BitConverter]::ToString($strictUtf8.GetBytes($prompt))
        if ($result.Stdout -notmatch [regex]::Escape("STDINHEX:$expectedHex")) {{
            throw "UTF-8 stdin mismatch: $($result.Stdout)"
        }}
        if ($result.Stderr -ne "FAKE-CODEX-STDERR") {{
            throw "stderr boundary mismatch: $($result.Stderr)"
        }}
        if ($result.Stdout -match "FAKE-CODEX-STDERR") {{
            throw "stderr leaked into stdout."
        }}
        """,
    )
    assert_success(result)


def test_resolve_codex_command_uses_safe_priority_independent_of_input_order(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $commands = @(
            [pscustomobject]@{ CommandType = "ExternalScript"; Source = "C:/fake/codex.ps1"; Definition = "C:/fake/codex.ps1" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.bat"; Definition = "C:/fake/codex.bat" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.cmd"; Definition = "C:/fake/codex.cmd" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.exe"; Definition = "C:/fake/codex.exe" }
        )
        $resolved = Resolve-CodexCommand -Commands $commands
        if ($resolved.Source -ne "C:/fake/codex.exe") {
            throw "Expected codex.exe, got $($resolved.Source)"
        }

        $withoutExe = @($commands | Where-Object { $_.Source -notlike "*.exe" })
        $resolved = Resolve-CodexCommand -Commands $withoutExe
        if ($resolved.Source -ne "C:/fake/codex.cmd") {
            throw "Expected codex.cmd, got $($resolved.Source)"
        }

        $withoutExeOrCmd = @($commands | Where-Object {
            $_.Source -notlike "*.exe" -and $_.Source -notlike "*.cmd"
        })
        $resolved = Resolve-CodexCommand -Commands $withoutExeOrCmd
        if ($resolved.Source -ne "C:/fake/codex.bat") {
            throw "Expected codex.bat, got $($resolved.Source)"
        }
        """,
    )
    assert_success(result)


def test_resolve_codex_command_rejects_extensionless_and_unsafe_wrappers(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        foreach ($source in @("C:/fake/codex", "C:/fake/codex.sh", "C:/fake/codex.ps1")) {
            $failed = $false
            try {
                Resolve-CodexCommand -Commands @(
                    [pscustomobject]@{ CommandType = "Application"; Source = $source; Definition = $source }
                ) | Out-Null
            }
            catch {
                $failed = $true
            }
            if (-not $failed) {
                throw "Expected unsafe launcher to fail closed: $source"
            }
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
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardErrorEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
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
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.ASCIIEncoding]::new()) `
            -StandardErrorEncoding ([System.Text.ASCIIEncoding]::new()) `
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


def test_captured_native_process_writes_standard_input_as_utf8(tmp_path):
    child = tmp_path / "stdin_bytes.ps1"
    child.write_text(
        textwrap.dedent(
            """
            $stream = [Console]::OpenStandardInput()
            $memory = New-Object System.IO.MemoryStream
            $buffer = New-Object byte[] 1024
            while (($count = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $memory.Write($buffer, 0, $count)
            }
            Write-Output ([BitConverter]::ToString($memory.ToArray()))
            """
        ).strip(),
        encoding="utf-8",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $prompt = "ASCII " + [string][char]0x5C08 + [string][char]0x6848
        $result = Invoke-CapturedNativeProcess `
            -FilePath {str(_powershell())!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {str(tmp_path)!r} `
            -StandardInput $prompt `
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.ASCIIEncoding]::new()) `
            -StandardErrorEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -TimeoutSeconds 10 `
            -Action "stdin utf8 test"

        if ($result.TimedOut) {{ throw "Did not expect timeout" }}
        if ($result.ExitCode -ne 0) {{ throw "Expected exit code 0, got $($result.ExitCode): $($result.Stderr)" }}
        if ($result.Stdout -ne "41-53-43-49-49-20-E5-B0-88-E6-A1-88") {{
            throw "Expected UTF-8 stdin bytes, got $($result.Stdout)"
        }}
        """,
    )
    assert_success(result)


def test_captured_native_process_decodes_explicit_utf8_without_child_console_encoding(tmp_path):
    unicode_dir = tmp_path / "中文路徑"
    unicode_dir.mkdir()
    child = unicode_dir / "unicode_streams.ps1"
    child.write_text(
        textwrap.dedent(
            """
            $stdout = [Console]::OpenStandardOutput()
            $stderr = [Console]::OpenStandardError()
            $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
            $payload = [ordered]@{
                cwd = (Get-Location).ProviderPath
                stdout_value = "標準輸出"
            } | ConvertTo-Json -Compress
            $stdoutBytes = $utf8.GetBytes($payload)
            $stdout.Write($stdoutBytes, 0, $stdoutBytes.Length)
            $stderrBytes = $utf8.GetBytes("標準錯誤")
            $stderr.Write($stderrBytes, 0, $stderrBytes.Length)
            """
        ).strip(),
        encoding="utf-8-sig",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $expectedCwd = [System.IO.Path]::GetFullPath({unicode_dir.as_posix()!r})
        $result = Invoke-CapturedNativeProcess `
            -FilePath {str(_powershell())!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {child.as_posix()!r}) `
            -WorkingDirectory $expectedCwd `
            -StandardInput "" `
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardErrorEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -TimeoutSeconds 10 `
            -Action "unicode cwd test"

        if ($result.ExitCode -ne 0) {{ throw "Child failed: $($result.Stderr)" }}
        if ($result.Stdout.Contains([char]0xFFFD) -or $result.Stderr.Contains([char]0xFFFD)) {{
            throw "Replacement character found in captured streams."
        }}
        $payload = $result.Stdout | ConvertFrom-Json
        if ($payload.cwd -ne $expectedCwd) {{
            throw "Expected cwd $expectedCwd, got $($payload.cwd)"
        }}
        if ($payload.stdout_value -ne "標準輸出") {{
            throw "Unexpected stdout value: $($payload.stdout_value)"
        }}
        if ($result.Stderr -ne "標準錯誤") {{
            throw "Unexpected stderr value: $($result.Stderr)"
        }}
        if ($result.Stdout -match "標準錯誤" -or $result.Stderr -match "標準輸出") {{
            throw "stdout/stderr stream boundary was merged."
        }}
        """,
    )
    assert_success(result)


def test_captured_native_process_decodes_explicit_cp950_and_keeps_streams_separate(tmp_path):
    child = tmp_path / "cp950_streams.ps1"
    child.write_text(
        textwrap.dedent(
            """
            $stdout = [Console]::OpenStandardOutput()
            $stderr = [Console]::OpenStandardError()
            $encoding = [System.Text.Encoding]::GetEncoding(950)
            $stdoutBytes = $encoding.GetBytes('{"value":"繁體輸出"}')
            $stderrBytes = $encoding.GetBytes("繁體錯誤")
            $stdout.Write($stdoutBytes, 0, $stdoutBytes.Length)
            $stderr.Write($stderrBytes, 0, $stderrBytes.Length)
            """
        ).strip(),
        encoding="utf-8-sig",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $cp950 = [System.Text.Encoding]::GetEncoding(
            950,
            [System.Text.EncoderExceptionFallback]::new(),
            [System.Text.DecoderExceptionFallback]::new()
        )
        $result = Invoke-CapturedNativeProcess `
            -FilePath {str(_powershell())!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {child.as_posix()!r}) `
            -WorkingDirectory {tmp_path.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $cp950 `
            -StandardOutputEncoding $cp950 `
            -StandardErrorEncoding $cp950 `
            -TimeoutSeconds 10 `
            -Action "cp950 stream test"

        if ($result.ExitCode -ne 0) {{ throw "Child failed: $($result.Stderr)" }}
        $payload = $result.Stdout | ConvertFrom-Json
        if ($payload.value -ne "繁體輸出") {{ throw "Wrong CP950 stdout: $($result.Stdout)" }}
        if ($result.Stderr -ne "繁體錯誤") {{ throw "Wrong CP950 stderr: $($result.Stderr)" }}
        if ($result.Stdout -match "繁體錯誤" -or $result.Stderr -match "繁體輸出") {{
            throw "stdout/stderr stream boundary was merged."
        }}
        """,
    )
    assert_success(result)


def test_captured_native_process_wrong_encoding_fails_structured_output(tmp_path):
    child = tmp_path / "cp950_json.ps1"
    child.write_text(
        textwrap.dedent(
            """
            $stdout = [Console]::OpenStandardOutput()
            $encoding = [System.Text.Encoding]::GetEncoding(950)
            $bytes = $encoding.GetBytes('{"value":"繁體輸出"}')
            $stdout.Write($bytes, 0, $bytes.Length)
            """
        ).strip(),
        encoding="utf-8-sig",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $result = Invoke-CapturedNativeProcess `
            -FilePath {str(_powershell())!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {child.as_posix()!r}) `
            -WorkingDirectory {tmp_path.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $strictUtf8 `
            -StandardOutputEncoding $strictUtf8 `
            -StandardErrorEncoding $strictUtf8 `
            -TimeoutSeconds 10 `
            -Action "wrong encoding test"

        if ($result.ExitCode -eq 0) {{
            throw "Wrong encoding was silently accepted as successful structured output: $($result.Stdout)"
        }}
        """,
    )
    assert_success(result)


def test_timeout_preserves_metadata_when_strict_output_decoding_fails(tmp_path):
    child = tmp_path / "invalid_utf8_then_timeout.ps1"
    child.write_text(
        textwrap.dedent(
            """
            $stdout = [Console]::OpenStandardOutput()
            $invalid = [byte[]](0xC3, 0x28)
            $stdout.Write($invalid, 0, $invalid.Length)
            $stdout.Flush()
            Start-Sleep -Seconds 10
            """
        ).strip(),
        encoding="utf-8-sig",
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $result = Invoke-CapturedNativeProcess `
            -FilePath {str(_powershell())!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {child.as_posix()!r}) `
            -WorkingDirectory {tmp_path.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $strictUtf8 `
            -StandardOutputEncoding $strictUtf8 `
            -StandardErrorEncoding $strictUtf8 `
            -TimeoutSeconds 1 `
            -Action "timeout decode failure"

        if (-not $result.TimedOut) {{ throw "Timeout metadata was lost." }}
        if ($result.ExitCode -ne 124) {{ throw "Expected timeout exit code 124, got $($result.ExitCode)" }}
        if (-not $result.StopAttempted) {{ throw "StopAttempted metadata was lost." }}
        if (@($result.StoppedProcessIds).Count -lt 1) {{ throw "Stopped process IDs were lost." }}
        if ($result.Stderr -notmatch "timeout decode failure failed") {{
            throw "Expected decoding failure in stderr: $($result.Stderr)"
        }}
        """,
    )
    assert_success(result)


@pytest.mark.parametrize(
    ("configure_name", "configure_email", "expected_error"),
    [
        (False, True, "repository-local git user.name is missing"),
        (True, False, "repository-local git user.email is missing"),
    ],
)
def test_repository_local_git_identity_missing_fails_before_stage(
    tmp_path, configure_name, configure_email, expected_error
):
    repo = tmp_path / "identity-repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    if configure_name:
        subprocess.run(
            ["git", "-C", str(repo), "config", "--local", "user.name", "Test User"],
            check=True,
        )
    if configure_email:
        subprocess.run(
            ["git", "-C", str(repo), "config", "--local", "user.email", "test@example.com"],
            check=True,
        )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {str(repo)!r}
        $failed = $false
        try {{
            Assert-RepositoryLocalGitIdentity
        }}
        catch {{
            $failed = $true
            if ($_.Exception.Message -notmatch {expected_error!r}) {{
                throw "Unexpected error: $($_.Exception.Message)"
            }}
        }}
        if (-not $failed) {{ throw "Expected missing local identity to fail closed." }}
        if (-not [string]::IsNullOrWhiteSpace((git -C $script:RepoPath diff --cached --name-only))) {{
            throw "Identity preflight staged files."
        }}
        """,
    )
    assert_success(result)


def test_repository_local_git_identity_present_reaches_next_gate_without_stage(tmp_path):
    repo = tmp_path / "identity-repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "--local", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "--local", "user.email", "test@example.com"],
        check=True,
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {str(repo)!r}
        $identity = Assert-RepositoryLocalGitIdentity
        if ($identity.UserName -ne "Test User") {{ throw "Wrong local user.name." }}
        if ($identity.UserEmail -ne "test@example.com") {{ throw "Wrong local user.email." }}
        if (-not [string]::IsNullOrWhiteSpace((git -C $script:RepoPath diff --cached --name-only))) {{
            throw "Identity preflight staged files."
        }}
        """,
    )
    assert_success(result)


def test_commit_approved_missing_identity_stops_before_github_stage_or_commit(tmp_path):
    repo = tmp_path / "commit-approved-repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    tracked = repo / "change.txt"
    tracked.write_text("candidate\n", encoding="utf-8")
    fake_gh_marker = tmp_path / "fake-gh-invoked.txt"
    fake_gh = tmp_path / "fake-gh.cmd"
    fake_gh.write_text(
        f"@echo off\r\necho invoked>{fake_gh_marker}\r\nexit /b 99\r\n",
        encoding="ascii",
    )
    git_trace = tmp_path / "git-trace.txt"

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $script:Gh = {fake_gh.as_posix()!r}
        $script:IssueNumber = 123
        $env:GIT_TRACE = {git_trace.as_posix()!r}
        $failed = $false
        try {{
            Invoke-CommitApprovedMode
        }}
        catch {{
            $failed = $true
            if ($_.Exception.Message -notmatch "repository-local git user.name is missing") {{
                throw "Unexpected error: $($_.Exception.Message)"
            }}
        }}
        finally {{
            Remove-Item Env:GIT_TRACE -ErrorAction SilentlyContinue
        }}
        if (-not $failed) {{ throw "Expected CommitApproved to fail on missing identity." }}
        if (Test-Path -LiteralPath {fake_gh_marker.as_posix()!r}) {{
            throw "Fake GitHub CLI was invoked before identity gate."
        }}
        $trace = if (Test-Path -LiteralPath {git_trace.as_posix()!r}) {{
            Get-Content -LiteralPath {git_trace.as_posix()!r} -Raw
        }} else {{ "" }}
        if ($trace -match "(?m)\\s(add|commit)(\\s|$)") {{
            throw "Git add or commit was attempted before identity gate: $trace"
        }}
        if (-not [string]::IsNullOrWhiteSpace((git -C $script:RepoPath diff --cached --name-only))) {{
            throw "CommitApproved staged files before identity gate."
        }}
        """,
    )
    assert_success(result)
    assert not fake_gh_marker.exists()
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == ""
    )


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
