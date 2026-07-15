import json
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
    end = source.index("\nif ($ToolResolutionPreflight)")
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


def init_git_repo(path: Path) -> str:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Runner Test"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "runner-test@example.invalid"],
        check=True,
    )
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "seed"], check=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_normal_runner_modes_still_require_issue_number():
    result = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "IssueNumber is required" in (result.stdout + result.stderr)


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


def test_resolve_github_cli_command_rejects_ps1_and_unknown_extensions(tmp_path):
    ps1 = tmp_path / "gh.ps1"
    unknown = tmp_path / "gh.sh"
    ps1.write_text("fake ps1", encoding="utf-8")
    unknown.write_text("fake shell", encoding="utf-8")
    missing_default = tmp_path / "missing-program-files-gh.exe"
    missing_portable = tmp_path / "missing-portable-gh.exe"

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $commands = @(
            [pscustomobject]@{{ CommandType = "ExternalScript"; Source = "{ps1.as_posix()}"; Definition = "{ps1.as_posix()}" }},
            [pscustomobject]@{{ CommandType = "Application"; Source = "{unknown.as_posix()}"; Definition = "{unknown.as_posix()}" }}
        )
        $failed = $false
        try {{
            Resolve-GitHubCliCommand `
                -Commands $commands `
                -DefaultPath "{missing_default.as_posix()}" `
                -PortablePath "{missing_portable.as_posix()}" `
                -ExtraCandidatePaths @() | Out-Null
        }}
        catch {{
            $failed = $true
        }}
        if (-not $failed) {{ throw "Expected unsafe GitHub CLI candidates to fail closed." }}
        """,
    )
    assert_success(result)


def test_resolve_github_cli_command_rejects_alias_and_function_even_with_exe_leaf(tmp_path):
    alias_exe = tmp_path / "alias-gh.exe"
    function_exe = tmp_path / "function-gh.exe"
    alias_exe.write_text("fake alias", encoding="utf-8")
    function_exe.write_text("fake function", encoding="utf-8")
    missing_default = tmp_path / "missing-program-files-gh.exe"
    missing_portable = tmp_path / "missing-portable-gh.exe"

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $commands = @(
            [pscustomobject]@{{ CommandType = "Alias"; Source = "{alias_exe.as_posix()}"; Definition = "{alias_exe.as_posix()}" }},
            [pscustomobject]@{{ CommandType = "Function"; Source = "{function_exe.as_posix()}"; Definition = "{function_exe.as_posix()}" }}
        )
        $failed = $false
        try {{
            Resolve-GitHubCliCommand `
                -Commands $commands `
                -DefaultPath "{missing_default.as_posix()}" `
                -PortablePath "{missing_portable.as_posix()}" `
                -ExtraCandidatePaths @() | Out-Null
        }}
        catch {{
            $failed = $true
        }}
        if (-not $failed) {{ throw "Expected Alias/Function GitHub CLI metadata to fail closed." }}
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


def test_resolve_codex_command_prefers_cmd_over_exe(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $commands = @(
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.cmd"; Definition = "C:/fake/codex.cmd" },
            [pscustomobject]@{ CommandType = "Application"; Source = "C:/fake/codex.exe"; Definition = "C:/fake/codex.exe" }
        )
        $resolved = Resolve-CodexCommand -Commands $commands
        if ($resolved.Source -ne "C:/fake/codex.cmd") {
            throw "Expected codex.cmd, got $($resolved.Source)"
        }
        if ($resolved.FilePath -ne $env:COMSPEC) {
            throw "Expected cmd.exe FilePath, got $($resolved.FilePath)"
        }
        if (@($resolved.ArgumentPrefix).Count -ne 5) {
            throw "Batch launcher must have cmd.exe argument prefix."
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
        if ($resolved.Source -ne "C:/fake/codex.cmd") {
            throw "Expected codex.cmd, got $($resolved.Source)"
        }

        $onlyExe = @($commands | Where-Object { $_.Source -like "*.exe" })
        $resolved = Resolve-CodexCommand -Commands $onlyExe
        if ($resolved.Source -ne "C:/fake/codex.exe") {
            throw "Expected codex.exe when it is the only safe launcher, got $($resolved.Source)"
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


def test_resolve_codex_command_uses_reviewed_cmd_even_when_path_contains_exe(tmp_path):
    reviewed_cmd = tmp_path / "npm" / "codex.cmd"
    reviewed_cmd.parent.mkdir()
    reviewed_cmd.write_text("@echo off\n", encoding="ascii")
    windowsapps_exe = tmp_path / "WindowsApps" / "codex.exe"
    windowsapps_exe.parent.mkdir()
    windowsapps_exe.write_text("fake exe", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $commands = @(
            [pscustomobject]@{{ CommandType = "Application"; Source = {windowsapps_exe.as_posix()!r}; Definition = {windowsapps_exe.as_posix()!r} }},
            [pscustomobject]@{{ CommandType = "Application"; Source = {reviewed_cmd.as_posix()!r}; Definition = {reviewed_cmd.as_posix()!r} }}
        )
        $resolved = Resolve-CodexCommand -Commands $commands -ReviewedCodexPath {reviewed_cmd.as_posix()!r}
        $expected = [System.IO.Path]::GetFullPath({reviewed_cmd.as_posix()!r})
        if ($resolved.Source -ne $expected) {{
            throw "Expected reviewed codex.cmd, got $($resolved.Source)"
        }}
        if ($resolved.FilePath -ne $env:COMSPEC) {{
            throw "Expected reviewed cmd to launch through COMSPEC, got $($resolved.FilePath)"
        }}
        if ($resolved.LauncherType -ne "cmd") {{
            throw "Expected cmd launcher type, got $($resolved.LauncherType)"
        }}
        if (-not $resolved.PathBindingMatch) {{
            throw "Expected reviewed path binding to match."
        }}
        if ((@($resolved.ArgumentPrefix) -join "|") -notmatch [regex]::Escape($expected)) {{
            throw "Expected exact reviewed path in argument prefix: $($resolved.ArgumentPrefix -join '|')"
        }}
        """,
    )
    assert_success(result)


def test_resolve_codex_command_rejects_invalid_reviewed_path_before_path_fallback(tmp_path):
    unsafe_ps1 = tmp_path / "codex.ps1"
    unsafe_ps1.write_text("Write-Output bad", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        foreach ($path in @("codex.cmd", {unsafe_ps1.as_posix()!r}, {str(tmp_path / 'missing.cmd')!r})) {{
            $failed = $false
            try {{
                Resolve-CodexCommand -ReviewedCodexPath $path -Commands @(
                    [pscustomobject]@{{ CommandType = "Application"; Source = "C:/fallback/codex.exe"; Definition = "C:/fallback/codex.exe" }}
                ) | Out-Null
            }}
            catch {{
                $failed = $true
            }}
            if (-not $failed) {{
                throw "Expected invalid reviewed path to fail closed before fallback: $path"
            }}
        }}
        """,
    )
    assert_success(result)


def test_reviewed_codex_cmd_version_probe_and_task_share_launch_spec(tmp_path):
    reviewed_cmd = tmp_path / "npm" / "codex.cmd"
    reviewed_cmd.parent.mkdir()
    reviewed_cmd.write_text("@echo off\n", encoding="ascii")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:ProbeCalls = 0
        $script:TaskCalls = 0
        $script:ProbeFilePath = ""
        $script:TaskFilePath = ""
        $script:ProbeArgs = @()
        $script:TaskArgs = @()
        function New-FakeNativeResult {{
            param([string]$FilePath, [string[]]$Arguments, [int]$ExitCode = 0, [bool]$TimedOut = $false)
            return [pscustomobject]@{{
                ExitCode = $ExitCode; Stdout = ""; Stderr = ""; TimedOut = $TimedOut; TimeoutSeconds = 30
                FilePath = $FilePath; Arguments = @($Arguments); CommandLine = "fake"
                LastStdoutLine = ""; LastStderrLine = ""; ProcessId = 10; StopAttempted = $false; StoppedProcessIds = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding, [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding, [int]$TimeoutSeconds, [string]$Action
            )
            if ($Action -eq "codex --version reviewed exact launcher") {{
                $script:ProbeCalls += 1; $script:ProbeFilePath = $FilePath; $script:ProbeArgs = @($Arguments)
                return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments
            }}
            if ($Action -eq "codex ReviewBundle candidate generation") {{
                $script:TaskCalls += 1; $script:TaskFilePath = $FilePath; $script:TaskArgs = @($Arguments)
                return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments
            }}
            throw "unexpected action $Action"
        }}
        $codexCommand = Resolve-CodexCommand -ReviewedCodexPath {reviewed_cmd.as_posix()!r}
        $probe = Invoke-ReviewedCodexVersionProbe -CodexCommand $codexCommand -TimeoutSeconds 30
        if (-not $probe.Passed) {{ throw "Probe should pass: $($probe.FailureReason)" }}
        $taskArguments = @($codexCommand.ArgumentPrefix) + @("--ask-for-approval", "never")
        Invoke-CapturedNativeProcess `
            -FilePath $codexCommand.FilePath `
            -Arguments $taskArguments `
            -WorkingDirectory $script:RepoPath `
            -StandardInput "" `
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardErrorEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -TimeoutSeconds 10 `
            -Action "codex ReviewBundle candidate generation" | Out-Null

        $expectedSource = [System.IO.Path]::GetFullPath({reviewed_cmd.as_posix()!r})
        if ($script:ProbeCalls -ne 1 -or $script:TaskCalls -ne 1) {{ throw "Expected one probe and one task." }}
        if ($script:ProbeFilePath -ne $env:COMSPEC -or $script:TaskFilePath -ne $env:COMSPEC) {{ throw "Expected COMSPEC for cmd launcher." }}
        foreach ($prefix in @("/d", "/s", "/c", "call", $expectedSource)) {{
            if ($script:ProbeArgs -notcontains $prefix) {{ throw "Probe missing prefix $prefix" }}
            if ($script:TaskArgs -notcontains $prefix) {{ throw "Task missing prefix $prefix" }}
        }}
        if ($script:ProbeArgs[-1] -ne "--version") {{ throw "Probe must end with --version." }}
        if (-not (Test-StringArrayEqual -Left ([string[]]$script:ProbeArgs[0..4]) -Right ([string[]]$script:TaskArgs[0..4]))) {{
            throw "Probe and task cmd prefix differ."
        }}
        """,
    )
    assert_success(result)


def test_reviewed_codex_exe_version_probe_and_task_use_exact_exe(tmp_path):
    reviewed_exe = tmp_path / "bin" / "codex.exe"
    reviewed_exe.parent.mkdir()
    reviewed_exe.write_text("fake exe", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:ProbeCalls = 0
        $script:TaskCalls = 0
        function New-FakeNativeResult {{
            param([string]$FilePath, [string[]]$Arguments)
            return [pscustomobject]@{{
                ExitCode = 0; Stdout = ""; Stderr = ""; TimedOut = $false; TimeoutSeconds = 30
                FilePath = $FilePath; Arguments = @($Arguments); CommandLine = "fake"
                LastStdoutLine = ""; LastStderrLine = ""; ProcessId = 10; StopAttempted = $false; StoppedProcessIds = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding, [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding, [int]$TimeoutSeconds, [string]$Action
            )
            if ($Action -eq "codex --version reviewed exact launcher") {{ $script:ProbeCalls += 1; return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments }}
            if ($Action -eq "codex ReviewBundle candidate generation") {{ $script:TaskCalls += 1; return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments }}
            throw "unexpected action $Action"
        }}
        $codexCommand = Resolve-CodexCommand -ReviewedCodexPath {reviewed_exe.as_posix()!r}
        $probe = Invoke-ReviewedCodexVersionProbe -CodexCommand $codexCommand -TimeoutSeconds 30
        if (-not $probe.Passed) {{ throw "Probe should pass: $($probe.FailureReason)" }}
        Invoke-CapturedNativeProcess `
            -FilePath $codexCommand.FilePath `
            -Arguments (@($codexCommand.ArgumentPrefix) + @("--ask-for-approval", "never")) `
            -WorkingDirectory $script:RepoPath `
            -StandardInput "" `
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardErrorEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -TimeoutSeconds 10 `
            -Action "codex ReviewBundle candidate generation" | Out-Null

        $expected = [System.IO.Path]::GetFullPath({reviewed_exe.as_posix()!r})
        if ($codexCommand.FilePath -ne $expected) {{ throw "Expected exact exe FilePath." }}
        if (@($codexCommand.ArgumentPrefix).Count -ne 0) {{ throw "Exe launch spec must not use a prefix." }}
        if ($probe.ProcessFilePath -ne $expected) {{ throw "Probe did not use exact exe." }}
        if (($probe.Arguments -join "|") -ne "--version") {{ throw "Probe exe args must be only --version." }}
        if ($script:ProbeCalls -ne 1 -or $script:TaskCalls -ne 1) {{ throw "Expected one probe and one task." }}
        """,
    )
    assert_success(result)


@pytest.mark.parametrize(
    ("probe_setup", "expected_reason"),
    [
        ("return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments -ExitCode 7", "probe_nonzero_exit"),
        ("return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments -TimedOut $true", "probe_timeout"),
        ('throw "start failed"', "process_start_exception"),
    ],
)
def test_reviewed_codex_version_probe_failure_blocks_task_without_fallback(
    tmp_path, probe_setup, expected_reason
):
    reviewed_cmd = tmp_path / "npm" / "codex.cmd"
    reviewed_cmd.parent.mkdir()
    reviewed_cmd.write_text("@echo off\n", encoding="ascii")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:TaskCalls = 0
        $script:FallbackCalls = 0
        function Resolve-ComSpecPath {{ return $env:COMSPEC }}
        function Get-Command {{ $script:FallbackCalls += 1; throw "PATH fallback must not be used" }}
        function New-FakeNativeResult {{
            param([string]$FilePath, [string[]]$Arguments, [int]$ExitCode = 0, [bool]$TimedOut = $false)
            return [pscustomobject]@{{
                ExitCode = $ExitCode; Stdout = ""; Stderr = ""; TimedOut = $TimedOut; TimeoutSeconds = 30
                FilePath = $FilePath; Arguments = @($Arguments); CommandLine = "fake"
                LastStdoutLine = ""; LastStderrLine = ""; ProcessId = 10; StopAttempted = $false; StoppedProcessIds = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding, [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding, [int]$TimeoutSeconds, [string]$Action
            )
            if ($Action -eq "codex --version reviewed exact launcher") {{ {probe_setup} }}
            if ($Action -eq "codex ReviewBundle candidate generation") {{ $script:TaskCalls += 1; return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments }}
            throw "unexpected action $Action"
        }}
        $codexCommand = Resolve-CodexCommand -ReviewedCodexPath {reviewed_cmd.as_posix()!r}
        $probe = Invoke-ReviewedCodexVersionProbe -CodexCommand $codexCommand -TimeoutSeconds 30
        if ($probe.Passed) {{ throw "Probe should fail." }}
        if ($probe.FailureReason -ne {expected_reason!r}) {{ throw "Wrong failure reason: $($probe.FailureReason)" }}
        if ($script:TaskCalls -ne 0) {{ throw "Task must not run after failed probe." }}
        if ($script:FallbackCalls -ne 0) {{ throw "PATH fallback must not be used." }}
        """,
    )
    assert_success(result)


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ('$codexCommand.Source = "C:/Other/codex.cmd"; $codexCommand.PathBindingMatch = $true', "probe_launcher_source_mismatch"),
        ('$script:ProbeFilePathOverride = "C:/Other/cmd.exe"', "probe_file_path_mismatch"),
        ('$script:ProbeArgumentsOverride = @("--version")', "probe_argument_prefix_mismatch"),
    ],
)
def test_reviewed_codex_version_probe_mismatch_blocks_task(tmp_path, mutation, expected_reason):
    reviewed_cmd = tmp_path / "npm" / "codex.cmd"
    reviewed_cmd.parent.mkdir()
    reviewed_cmd.write_text("@echo off\n", encoding="ascii")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:TaskCalls = 0
        $script:ProbeFilePathOverride = ""
        $script:ProbeArgumentsOverride = $null
        function New-FakeNativeResult {{
            param([string]$FilePath, [string[]]$Arguments)
            return [pscustomobject]@{{
                ExitCode = 0; Stdout = ""; Stderr = ""; TimedOut = $false; TimeoutSeconds = 30
                FilePath = $FilePath; Arguments = @($Arguments); CommandLine = "fake"
                LastStdoutLine = ""; LastStderrLine = ""; ProcessId = 10; StopAttempted = $false; StoppedProcessIds = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding, [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding, [int]$TimeoutSeconds, [string]$Action
            )
            if ($Action -eq "codex --version reviewed exact launcher") {{
                $resultFilePath = if ([string]::IsNullOrWhiteSpace($script:ProbeFilePathOverride)) {{ $FilePath }} else {{ $script:ProbeFilePathOverride }}
                $resultArguments = if ($null -eq $script:ProbeArgumentsOverride) {{ $Arguments }} else {{ @($script:ProbeArgumentsOverride) }}
                return New-FakeNativeResult -FilePath $resultFilePath -Arguments $resultArguments
            }}
            if ($Action -eq "codex ReviewBundle candidate generation") {{ $script:TaskCalls += 1; return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments }}
            throw "unexpected action $Action"
        }}
        $codexCommand = Resolve-CodexCommand -ReviewedCodexPath {reviewed_cmd.as_posix()!r}
        {mutation}
        $probe = Invoke-ReviewedCodexVersionProbe -CodexCommand $codexCommand -TimeoutSeconds 30
        if ($probe.Passed) {{ throw "Probe mismatch should fail." }}
        if ($probe.FailureReason -ne {expected_reason!r}) {{ throw "Wrong failure reason: $($probe.FailureReason)" }}
        if ($script:TaskCalls -ne 0) {{ throw "Task must not run after probe mismatch." }}
        """,
    )
    assert_success(result)


def test_reviewed_cmd_blocks_windowsapps_exe_during_probe_and_task(tmp_path):
    reviewed_cmd = tmp_path / "npm" / "codex.cmd"
    reviewed_cmd.parent.mkdir()
    reviewed_cmd.write_text("@echo off\n", encoding="ascii")
    windowsapps_exe = tmp_path / "WindowsApps" / "codex.exe"
    windowsapps_exe.parent.mkdir()
    windowsapps_exe.write_text("fake exe", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:WindowsAppsInvocationCount = 0
        $script:TaskCalls = 0
        function New-FakeNativeResult {{
            param([string]$FilePath, [string[]]$Arguments)
            return [pscustomobject]@{{
                ExitCode = 0; Stdout = ""; Stderr = ""; TimedOut = $false; TimeoutSeconds = 30
                FilePath = $FilePath; Arguments = @($Arguments); CommandLine = "fake"
                LastStdoutLine = ""; LastStderrLine = ""; ProcessId = 10; StopAttempted = $false; StoppedProcessIds = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory, [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding, [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding, [int]$TimeoutSeconds, [string]$Action
            )
            if ($FilePath -like "*WindowsApps*" -or (($Arguments -join "|") -like "*WindowsApps*")) {{ $script:WindowsAppsInvocationCount += 1 }}
            if ($Action -eq "codex --version reviewed exact launcher") {{ return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments }}
            if ($Action -eq "codex ReviewBundle candidate generation") {{ $script:TaskCalls += 1; return New-FakeNativeResult -FilePath $FilePath -Arguments $Arguments }}
            throw "unexpected action $Action"
        }}
        $commands = @(
            [pscustomobject]@{{ CommandType = "Application"; Source = {windowsapps_exe.as_posix()!r}; Definition = {windowsapps_exe.as_posix()!r} }},
            [pscustomobject]@{{ CommandType = "Application"; Source = {reviewed_cmd.as_posix()!r}; Definition = {reviewed_cmd.as_posix()!r} }}
        )
        $codexCommand = Resolve-CodexCommand -Commands $commands -ReviewedCodexPath {reviewed_cmd.as_posix()!r}
        $probe = Invoke-ReviewedCodexVersionProbe -CodexCommand $codexCommand -TimeoutSeconds 30
        if (-not $probe.Passed) {{ throw "Probe should pass: $($probe.FailureReason)" }}
        Invoke-CapturedNativeProcess `
            -FilePath $codexCommand.FilePath `
            -Arguments (@($codexCommand.ArgumentPrefix) + @("--ask-for-approval", "never")) `
            -WorkingDirectory $script:RepoPath `
            -StandardInput "" `
            -StandardInputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardOutputEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -StandardErrorEncoding ([System.Text.UTF8Encoding]::new($false, $true)) `
            -TimeoutSeconds 10 `
            -Action "codex ReviewBundle candidate generation" | Out-Null
        if ($script:WindowsAppsInvocationCount -ne 0) {{ throw "WindowsApps exe must not be used." }}
        if ($script:TaskCalls -ne 1) {{ throw "Task should run once after successful reviewed cmd probe." }}
        """,
    )
    assert_success(result)


def test_child_process_summary_reports_codex_version_probe_diagnostics(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $codexCommand = [pscustomobject]@{
            Source = "C:/Tools/codex.cmd"
            FilePath = "C:/Windows/System32/cmd.exe"
            ArgumentPrefix = @("/d", "/s", "/c", "call", "C:/Tools/codex.cmd")
            LauncherType = "cmd"
            PathBindingMatch = $true
        }
        $probe = [pscustomobject]@{
            Attempted = $true
            Passed = $true
            ExitCode = 0
            TimedOut = $false
            ProcessFilePath = "C:/Windows/System32/cmd.exe"
            LauncherSource = "C:/Tools/codex.cmd"
            PathBindingMatch = $true
        }
        $task = [pscustomobject]@{
            ExitCode = 0
            TimedOut = $false
            TimeoutSeconds = 1200
            FilePath = "C:/Windows/System32/cmd.exe"
            CommandLine = "cmd.exe /d /s /c call C:/Tools/codex.cmd"
            LastStdoutLine = "ok"
            LastStderrLine = ""
            StopAttempted = $false
            StoppedProcessIds = @()
        }
        $summary = New-ChildProcessReviewBundleSummary -Result $task -FinalStatus "" -CodexCommand $codexCommand -ReviewedCodexPath "C:/Tools/codex.cmd" -CodexVersionProbe $probe
        foreach ($expected in @(
            "codex_version_probe_attempted=true",
            "codex_version_probe_exit_code=0",
            "codex_version_probe_timed_out=false",
            "codex_version_probe_passed=true",
            "codex_version_probe_process_file_path=C:/Windows/System32/cmd.exe",
            "codex_version_probe_launcher_source=C:/Tools/codex.cmd",
            "codex_version_probe_path_binding_match=true"
        )) {
            if (-not $summary.Contains($expected)) {
                throw "Expected summary to contain $expected. Summary: $summary"
            }
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


def test_tool_resolution_preflight_runs_without_issue_number_and_probes_versions_only(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:RequiredAction = "run-reviewbundle"
        $script:IssueNumber = 0
        $script:ProbeCalls = @()
        function Resolve-GitHubCliCommand {{ return {str(tmp_path / 'gh.exe')!r} }}
        function Resolve-PythonRuntimeCommand {{ return {str(tmp_path / 'python.exe')!r} }}
        function Get-RuntimeContractEvaluatorIdentity {{
            return [pscustomobject]@{{
                EvaluatorPath = {str(tmp_path / 'runtime_contract_binding.py')!r}
                Fingerprint = "trusted-evaluator"
                Files = [ordered]@{{ "runtime_contract_binding.py" = "abc" }}
            }}
        }}
        function Resolve-CodexCommand {{
            return [pscustomobject]@{{
                Source = {str(tmp_path / 'codex.cmd')!r}
                FilePath = "cmd.exe"
                ArgumentPrefix = @("/d", "/s", "/c", "call", {str(tmp_path / 'codex.cmd')!r})
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath,
                [string[]]$Arguments,
                [string]$WorkingDirectory,
                [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding,
                [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding,
                [int]$TimeoutSeconds,
                [string]$Action
            )
            $script:ProbeCalls += "$Action|$FilePath|$($Arguments -join ',')"
            if (($Arguments -join " ") -match "\\b(exec|review|workspace-write)\\b") {{
                throw "preflight passed execution arguments: $($Arguments -join ' ')"
            }}
            return [pscustomobject]@{{ ExitCode = 0; TimedOut = $false; Stdout = "version"; Stderr = "" }}
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["protocol"] == "lawb.rv2_03_tool_resolution_preflight.v1"
    assert summary["component"] == "runner"
    assert summary["result"] == "success"
    assert summary["required_action"] == "run-reviewbundle"
    assert summary["tools"]["runner_gh"] == {
        "selected_path": str(tmp_path / "gh.exe"),
        "suffix": ".exe",
        "selection_source": "other existing source",
        "version_probe": {
            "executed": True,
            "exit_code": 0,
            "ok": True,
            "safe_message": "ok",
        },
    }
    assert summary["tools"]["codex"] == {
        "selected_path": str(tmp_path / "codex.cmd"),
        "suffix": ".cmd",
        "selection_source": "path",
        "version_probe": {
            "executed": True,
            "exit_code": 0,
            "ok": True,
            "safe_message": "ok",
        },
    }
    assert summary["tools"]["python"] == {
        "selected_path": str(tmp_path / "python.exe"),
        "suffix": ".exe",
        "selection_source": "direct executable on PATH",
        "version_probe": {
            "executed": True,
            "exit_code": 0,
            "ok": True,
            "safe_message": "ok",
        },
    }
    assert summary["tools"]["runtime_contract_evaluator"]["available"] is True
    assert (
        summary["tools"]["runtime_contract_evaluator"]["identity_fingerprint"]
        == "trusted-evaluator"
    )
    assert summary["safety"]["github_issue_read_performed"] is False
    assert summary["safety"]["runner_work_invoked"] is False
    assert summary["safety"]["codex_task_executed"] is False


@pytest.mark.parametrize(
    ("suffix", "expected_file_kind"),
    [
        (".exe", "direct"),
        (".cmd", "cmd-wrapper"),
        (".bat", "cmd-wrapper"),
    ],
)
def test_tool_resolution_preflight_gh_probe_uses_expected_launcher_composition(
    tmp_path, suffix, expected_file_kind
):
    gh_launcher = tmp_path / f"gh{suffix}"
    gh_launcher.write_text("fake gh", encoding="utf-8")
    codex_launcher = tmp_path / "codex.exe"
    codex_launcher.write_text("fake codex", encoding="utf-8")
    fake_cmd = tmp_path / "cmd.exe"
    fake_cmd.write_text("fake cmd", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:RequiredAction = "run-reviewbundle"
        $script:IssueNumber = 0
        $script:Mode = "ReviewBundle"
        $script:ApprovalToken = ""
        function Resolve-GitHubCliCommand {{ return {gh_launcher.as_posix()!r} }}
        function Resolve-PythonRuntimeCommand {{ return {str(tmp_path / 'python.exe')!r} }}
        function Get-RuntimeContractEvaluatorIdentity {{
            return [pscustomobject]@{{
                EvaluatorPath = {str(tmp_path / 'runtime_contract_binding.py')!r}
                Fingerprint = "trusted-evaluator"
                Files = [ordered]@{{ "runtime_contract_binding.py" = "abc" }}
            }}
        }}
        function Resolve-ComSpecPath {{ return {fake_cmd.as_posix()!r} }}
        function Resolve-CodexCommand {{
            return [pscustomobject]@{{
                Source = {codex_launcher.as_posix()!r}
                FilePath = {codex_launcher.as_posix()!r}
                ArgumentPrefix = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            param(
                [string]$FilePath,
                [string[]]$Arguments,
                [string]$WorkingDirectory,
                [string]$StandardInput,
                [System.Text.Encoding]$StandardInputEncoding,
                [System.Text.Encoding]$StandardOutputEncoding,
                [System.Text.Encoding]$StandardErrorEncoding,
                [int]$TimeoutSeconds,
                [string]$Action
            )
            if ($Action -eq "gh --version") {{
                Write-Host "GH_PROBE_FILE=$FilePath"
                Write-Host "GH_PROBE_ARGS=$($Arguments -join '|')"
            }}
            return [pscustomobject]@{{ ExitCode = 0; TimedOut = $false; Stdout = "version"; Stderr = "" }}
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    if expected_file_kind == "direct":
        assert f"GH_PROBE_FILE={gh_launcher.as_posix()}" in result.stdout
        assert "GH_PROBE_ARGS=--version" in result.stdout
    else:
        assert f"GH_PROBE_FILE={fake_cmd.as_posix()}" in result.stdout
        assert f"GH_PROBE_ARGS=/d|/s|/c|call|{gh_launcher.as_posix()}|--version" in result.stdout
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["result"] == "success"


def test_tool_resolution_preflight_blocks_when_gh_or_codex_missing(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:RequiredAction = "run-reviewbundle"
        function Resolve-GitHubCliCommand {{ throw "missing gh" }}
        function Resolve-CodexCommand {{ throw "missing codex" }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "blocked"
    assert "runner_gh_unavailable" in summary["blocked_reasons"]
    assert "codex_unavailable" in summary["blocked_reasons"]
    assert summary["safety"]["github_write_performed"] is False


def test_tool_resolution_preflight_blocks_structurally_when_python_is_missing(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:RequiredAction = "run-reviewbundle"
        function Resolve-GitHubCliCommand {{ return {str(tmp_path / 'gh.exe')!r} }}
        function Resolve-PythonRuntimeCommand {{ throw "missing python" }}
        function Get-RuntimeContractEvaluatorIdentity {{
            return [pscustomobject]@{{
                EvaluatorPath = {str(tmp_path / 'runtime_contract_binding.py')!r}
                Fingerprint = "trusted-evaluator"
                Files = [ordered]@{{ "runtime_contract_binding.py" = "abc" }}
            }}
        }}
        function Resolve-CodexCommand {{
            return [pscustomobject]@{{
                Source = {str(tmp_path / 'codex.exe')!r}
                FilePath = {str(tmp_path / 'codex.exe')!r}
                ArgumentPrefix = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            return [pscustomobject]@{{ ExitCode = 0; TimedOut = $false; Stdout = "version"; Stderr = "" }}
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "blocked"
    assert "runner_python_unavailable" in summary["blocked_reasons"]
    assert summary["tools"]["python"]["selected_path"] is None
    assert summary["safety"]["runner_work_invoked"] is False


def test_tool_resolution_preflight_blocks_structurally_when_evaluator_is_missing(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:RequiredAction = "run-reviewbundle"
        function Resolve-GitHubCliCommand {{ return {str(tmp_path / 'gh.exe')!r} }}
        function Resolve-PythonRuntimeCommand {{ return {str(tmp_path / 'python.exe')!r} }}
        function Get-RuntimeContractEvaluatorIdentity {{ throw "missing evaluator" }}
        function Resolve-CodexCommand {{
            return [pscustomobject]@{{
                Source = {str(tmp_path / 'codex.exe')!r}
                FilePath = {str(tmp_path / 'codex.exe')!r}
                ArgumentPrefix = @()
            }}
        }}
        function Invoke-CapturedNativeProcess {{
            return [pscustomobject]@{{ ExitCode = 0; TimedOut = $false; Stdout = "version"; Stderr = "" }}
        }}
        Invoke-ToolResolutionPreflight
        """,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "blocked"
    assert "runtime_contract_evaluator_unavailable" in summary["blocked_reasons"]
    assert summary["tools"]["runtime_contract_evaluator"]["available"] is False


@pytest.mark.parametrize(
    "setup",
    [
        '$script:IssueNumber = 123; $script:Mode = "ReviewBundle"; $script:ApprovalToken = ""',
        '$script:IssueNumber = 0; $script:Mode = "CommitApproved"; $script:ApprovalToken = ""',
        '$script:IssueNumber = 0; $script:Mode = "ApprovalStateDiagnostic"; $script:ApprovalToken = ""',
        '$script:IssueNumber = 0; $script:Mode = "ReviewBundle"; $script:ApprovalToken = "token"',
    ],
)
def test_tool_resolution_preflight_rejects_execution_parameters_before_probes(tmp_path, setup):
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {tmp_path.as_posix()!r}
        $script:RequiredAction = "run-reviewbundle"
        {setup}
        function Resolve-GitHubCliCommand {{ throw "resolver must not run" }}
        function Resolve-CodexCommand {{ throw "codex resolver must not run" }}
        $failed = $false
        try {{
            Invoke-ToolResolutionPreflight
        }}
        catch {{
            $failed = $true
            if ($_.Exception.Message -notmatch "does not accept IssueNumber") {{
                throw "Unexpected error: $($_.Exception.Message)"
            }}
        }}
        if (-not $failed) {{ throw "Expected parameter boundary failure." }}
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
            "parent_commit_push_close_continuation_after_timeout=false",
            "stopped_process_ids=111,222"
        )) {
            if (-not $summary.Contains($expected)) {
                throw "Expected summary to contain $expected. Summary: $summary"
            }
        }
        """,
    )
    assert_success(result)


def test_git_status_enumerates_each_untracked_file_in_new_directory(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    new_dir = repo / "newdir"
    new_dir.mkdir()
    (new_dir / "one.txt").write_text("one\n", encoding="utf-8")
    (new_dir / "two.txt").write_text("two\n", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $status = Get-GitStatusShort
        $files = @(Convert-FileTextToArray -Text (Get-ModifiedFilesFromStatus -Status $status))
        $payload = [ordered]@{{ status = $status; files = $files }}
        Write-Output ($payload | ConvertTo-Json -Compress)
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["files"] == ["newdir/one.txt", "newdir/two.txt"]
    assert "?? newdir/" not in payload["status"].splitlines()


def test_gitignore_visibility_bypass_fails_closed_with_unfiltered_untracked_delta(
    tmp_path,
):
    repo = tmp_path / "repo"
    head = init_git_repo(repo)
    (repo / ".gitignore").write_text("\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "tracked gitignore"],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    child = tmp_path / "gitignore_child.ps1"
    child.write_text(
        textwrap.dedent(
            f"""
            Set-Content -LiteralPath {str(repo / '.gitignore')!r} -Value "evil.py" -Encoding UTF8
            Set-Content -LiteralPath {str(repo / 'evil.py')!r} -Value "evil" -Encoding UTF8
            """
        ).strip(),
        encoding="utf-8-sig",
    )
    binding = json.dumps(
        _binding("passed", allowed_files=[".gitignore"], max_allowed_files=2)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-ReviewBundleGitObservation
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $child = Invoke-CapturedNativeProcess `
            -FilePath {_powershell()!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {repo.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 20 `
            -Action "simulated gitignore visibility bypass"
        if ($child.ExitCode -ne 0) {{ throw "Child failed: $($child.Stderr)" }}
        $after = Get-ReviewBundleGitObservation
        $ordinaryStatusFiles = @(Convert-FileTextToArray -Text (Get-ModifiedFilesFromStatus -Status $after.Status))
        $actualFiles = @(Get-ReviewBundleEffectiveChangedFiles `
            -Status $after.Status `
            -UntrackedFilesBefore @($before.UntrackedFiles) `
            -UntrackedFilesAfter @($after.UntrackedFiles) `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles))
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles) `
            -GitVisibilityMetadataFingerprintBefore $before.GitVisibilityMetadataFingerprint `
            -GitVisibilityMetadataFingerprintAfter $after.GitVisibilityMetadataFingerprint)
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles $actualFiles `
            -InvariantViolationReasons $reasons
        $noCommit = [string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $after.NoStage `
            -NoCommit $noCommit
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        [ordered]@{{
            child_exit = $child.ExitCode
            head_unchanged = $noCommit
            no_stage = $after.NoStage
            ordinary_status_files = $ordinaryStatusFiles
            actual_changed_files = $actualFiles
            binding = $binding
            approval_allowed = $approvalAllowed
            overall = $overall
        }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["child_exit"] == 0
    assert payload["head_unchanged"] is True
    assert payload["no_stage"] is True
    assert payload["ordinary_status_files"] == [".gitignore"]
    assert payload["actual_changed_files"] == [".gitignore", "evil.py"]
    assert payload["binding"]["status"] == "contract_violation"
    assert "changed_file_outside_allowed_files" in payload["binding"]["reasons"]
    assert payload["approval_allowed"] is False
    assert payload["overall"] == "failure"
    assert head == payload["binding"]["pre_execution"].get("head", head)


def test_benign_python_cache_delta_is_not_a_candidate_change(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".pytest_cache/\n__pycache__/\n*.pyc\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore caches"],
        check=True,
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-ReviewBundleGitObservation
        New-Item -ItemType Directory -Path {str(repo / '.pytest_cache' / 'v' / 'cache')!r} -Force | Out-Null
        Set-Content -LiteralPath {str(repo / '.pytest_cache' / 'v' / 'cache' / 'nodeids')!r} -Value "[]" -Encoding UTF8
        New-Item -ItemType Directory -Path {str(repo / 'pkg' / '__pycache__')!r} -Force | Out-Null
        Set-Content -LiteralPath {str(repo / 'pkg' / '__pycache__' / 'module.cpython-310.pyc')!r} -Value "cache" -Encoding ASCII
        Set-Content -LiteralPath {str(repo / 'loose.pyc')!r} -Value "cache" -Encoding ASCII
        $after = Get-ReviewBundleGitObservation
        $actualFiles = @(Get-ReviewBundleEffectiveChangedFiles `
            -Status $after.Status `
            -UntrackedFilesBefore @($before.UntrackedFiles) `
            -UntrackedFilesAfter @($after.UntrackedFiles) `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles))
        [ordered]@{{
            status = $after.Status
            observed_untracked = @($after.UntrackedFiles)
            actual_changed_files = $actualFiles
        }} | ConvertTo-Json -Depth 5 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["status"] == ""
    assert ".pytest_cache/v/cache/nodeids" in payload["observed_untracked"]
    assert "pkg/__pycache__/module.cpython-310.pyc" in payload["observed_untracked"]
    assert "loose.pyc" in payload["observed_untracked"]
    assert payload["actual_changed_files"] == []


@pytest.mark.parametrize(
    "index_option",
    ["--assume-unchanged", "--skip-worktree"],
    ids=["assume-unchanged", "skip-worktree"],
)
def test_index_visibility_bypass_fails_closed(index_option, tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    outside = repo / "outside.txt"
    outside.write_text("trusted\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "outside.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "tracked outside"],
        check=True,
    )
    child = tmp_path / "index_visibility_child.ps1"
    child.write_text(
        textwrap.dedent(
            f"""
            & git -C {repo.as_posix()!r} update-index {index_option} outside.txt
            if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
            Set-Content -LiteralPath {str(outside)!r} -Value "hidden change" -Encoding UTF8
            """
        ).strip(),
        encoding="utf-8-sig",
    )
    binding = json.dumps(
        _binding("passed", allowed_files=["seed.txt"], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-ReviewBundleGitObservation
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $child = Invoke-CapturedNativeProcess `
            -FilePath {_powershell()!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {repo.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 20 `
            -Action "simulated index visibility bypass"
        if ($child.ExitCode -ne 0) {{ throw "Child failed: $($child.Stderr)" }}
        $after = Get-ReviewBundleGitObservation
        $actualFiles = @(Get-ReviewBundleEffectiveChangedFiles `
            -Status $after.Status `
            -UntrackedFilesBefore @($before.UntrackedFiles) `
            -UntrackedFilesAfter @($after.UntrackedFiles) `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles))
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles) `
            -GitVisibilityMetadataFingerprintBefore $before.GitVisibilityMetadataFingerprint `
            -GitVisibilityMetadataFingerprintAfter $after.GitVisibilityMetadataFingerprint)
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles $actualFiles `
            -InvariantViolationReasons $reasons
        $noCommit = [string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $after.NoStage `
            -NoCommit $noCommit
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        [ordered]@{{
            child_exit = $child.ExitCode
            status = $after.Status
            head_unchanged = $noCommit
            no_stage = $after.NoStage
            index_visibility_files = @($after.IndexVisibilityFiles)
            actual_changed_files = $actualFiles
            binding = $binding
            approval_allowed = $approvalAllowed
            overall = $overall
        }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["child_exit"] == 0
    assert payload["status"] == ""
    assert payload["head_unchanged"] is True
    assert payload["no_stage"] is True
    assert payload["index_visibility_files"] == ["outside.txt"]
    assert payload["actual_changed_files"] == ["outside.txt"]
    assert payload["binding"]["status"] == "contract_violation"
    assert "git_index_visibility_flags_detected" in payload["binding"]["reasons"]
    assert payload["approval_allowed"] is False
    assert payload["overall"] == "failure"


def test_info_exclude_visibility_bypass_fails_closed_on_metadata_and_path_delta(
    tmp_path,
):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    child = tmp_path / "info_exclude_child.ps1"
    child.write_text(
        textwrap.dedent(
            f"""
            Add-Content -LiteralPath {str(repo / '.git' / 'info' / 'exclude')!r} -Value "evil.py" -Encoding UTF8
            Set-Content -LiteralPath {str(repo / 'evil.py')!r} -Value "evil" -Encoding UTF8
            """
        ).strip(),
        encoding="utf-8-sig",
    )
    binding = json.dumps(
        _binding("passed", allowed_files=["seed.txt"], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-ReviewBundleGitObservation
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $child = Invoke-CapturedNativeProcess `
            -FilePath {_powershell()!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {repo.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 20 `
            -Action "simulated info exclude visibility bypass"
        if ($child.ExitCode -ne 0) {{ throw "Child failed: $($child.Stderr)" }}
        $after = Get-ReviewBundleGitObservation
        $actualFiles = @(Get-ReviewBundleEffectiveChangedFiles `
            -Status $after.Status `
            -UntrackedFilesBefore @($before.UntrackedFiles) `
            -UntrackedFilesAfter @($after.UntrackedFiles) `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles))
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage `
            -IndexVisibilityFilesBefore @($before.IndexVisibilityFiles) `
            -IndexVisibilityFilesAfter @($after.IndexVisibilityFiles) `
            -GitVisibilityMetadataFingerprintBefore $before.GitVisibilityMetadataFingerprint `
            -GitVisibilityMetadataFingerprintAfter $after.GitVisibilityMetadataFingerprint)
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles $actualFiles `
            -InvariantViolationReasons $reasons
        $noCommit = [string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $after.NoStage `
            -NoCommit $noCommit
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        [ordered]@{{
            child_exit = $child.ExitCode
            status = $after.Status
            head_unchanged = $noCommit
            no_stage = $after.NoStage
            metadata_changed = -not [string]::Equals(
                $before.GitVisibilityMetadataFingerprint,
                $after.GitVisibilityMetadataFingerprint,
                [System.StringComparison]::Ordinal
            )
            actual_changed_files = $actualFiles
            binding = $binding
            approval_allowed = $approvalAllowed
            overall = $overall
        }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["child_exit"] == 0
    assert payload["status"] == ""
    assert payload["head_unchanged"] is True
    assert payload["no_stage"] is True
    assert payload["metadata_changed"] is True
    assert payload["actual_changed_files"] == ["evil.py"]
    assert payload["binding"]["status"] == "contract_violation"
    assert "changed_file_outside_allowed_files" in payload["binding"]["reasons"]
    assert "git_visibility_metadata_changed" in payload["binding"]["reasons"]
    assert payload["approval_allowed"] is False
    assert payload["overall"] == "failure"


def test_staged_area_observation_reports_no_stage_false(tmp_path):
    repo = tmp_path / "repo"
    head = init_git_repo(repo)
    (repo / "seed.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
    binding = json.dumps(
        _binding("passed", allowed_files=["seed.txt"], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $observation = Get-ReviewBundleGitObservation
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore {head!r} `
            -HeadAfter $observation.Head `
            -NoStage $observation.NoStage)
        $actualFiles = @(Convert-FileTextToArray -Text (Get-ModifiedFilesFromStatus -Status $observation.Status))
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles $actualFiles `
            -InvariantViolationReasons $reasons
        [ordered]@{{ observation = $observation; binding = $binding }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    observation = payload["observation"]
    assert observation["Head"] == head
    assert observation["NoStage"] is False
    assert payload["binding"]["status"] == "contract_violation"
    assert "staged_changes_detected" in payload["binding"]["reasons"]


def test_clean_observations_report_unchanged_head_and_empty_index(tmp_path):
    repo = tmp_path / "repo"
    head = init_git_repo(repo)

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-ReviewBundleGitObservation
        $after = Get-ReviewBundleGitObservation
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage)
        $payload = [ordered]@{{
            head = $after.Head
            no_stage = $after.NoStage
            no_commit = [string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
            reasons = $reasons
        }}
        Write-Output ($payload | ConvertTo-Json -Compress)
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload == {
        "head": head,
        "no_stage": True,
        "no_commit": True,
        "reasons": [],
    }


def test_allowed_preexisting_ignored_file_content_is_bound_by_bounded_manifest(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / ".gitignore").write_text("allowed-ignored.txt\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore allowed file"],
        check=True,
    )
    ignored = repo / "allowed-ignored.txt"
    ignored.write_text("before\n", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-BoundedCandidateManifest -AllowedFiles @("allowed-ignored.txt")
        Set-Content -LiteralPath {ignored.as_posix()!r} -Value "after" -Encoding UTF8
        $after = Get-BoundedCandidateManifest -AllowedFiles @("allowed-ignored.txt")
        $changed = @(Get-ChangedAllowedFilesFromManifests -Before $before -After $after)
        [ordered]@{{ before = $before; after = $after; changed = $changed }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["before"]["status"] == "verified"
    assert payload["after"]["status"] == "verified"
    assert payload["before"]["fingerprint"] != payload["after"]["fingerprint"]
    assert payload["changed"] == ["allowed-ignored.txt"]
    assert payload["after"]["entries"][0]["state"] == "regular_file"
    assert len(payload["after"]["entries"][0]["sha256"]) == 64


def test_directory_scope_is_invalid_and_manifest_failure_suppresses_eligibility(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    directory = repo / "directory-only"
    directory.mkdir()
    binding = json.dumps(
        _binding("passed", allowed_files=["directory-only"], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $binding = '{binding}' | ConvertFrom-Json
        $scopeReasons = @(Get-AllowedFileScopeViolationReasons -AllowedFiles @("directory-only"))
        $manifest = Get-BoundedCandidateManifest -AllowedFiles @("directory-only")
        $assurance = New-ExecutionAssurance `
            -RuntimeContractBinding $binding `
            -ObservableEvidence "unverified" `
            -CandidateManifest $manifest
        $eligible = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -FinalIndexClean $true `
            -FinalHeadMatchesInitial $true `
            -ExecutionAssurance $assurance
        [ordered]@{{ scope_reasons = $scopeReasons; manifest = $manifest; assurance = $assurance; eligible = $eligible }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert "allowed_file_is_directory" in payload["scope_reasons"]
    assert payload["manifest"]["status"] == "unverified"
    assert payload["assurance"]["observable_evidence"] == "unverified"
    assert payload["eligible"] is False


def test_passed_governance_without_bounded_evidence_suppresses_snapshot_eligibility(
    tmp_path,
):
    binding = json.dumps(_binding("passed"))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $binding = '{binding}' | ConvertFrom-Json
        $requestedAssurance = New-ExecutionAssurance `
            -RuntimeContractBinding $binding `
            -ObservableEvidence "verified"
        $eligible = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -FinalIndexClean $true `
            -FinalHeadMatchesInitial $true
        $stderrSummary = Get-StderrSummary -Text "" -ExitCode "0"
        $comment = New-ReviewBundleComment `
            -IssueNumberText "204" `
            -Branch "feature/runtime-contract" `
            -HeadBefore ("1" * 40) `
            -HeadAfter ("1" * 40) `
            -CodexExitCode "0" `
            -RepoCleanBefore "yes" `
            -ReviewId "review" `
            -DiffFingerprint ("2" * 64) `
            -FilesFingerprint ("3" * 64) `
            -ApprovalToken "SHOULD-NOT-APPEAR" `
            -ModifiedFiles "src/example.py" `
            -DiffStat "" `
            -CachedDiffStat "" `
            -CommandsSummary "fake" `
            -CodexFinalReport "DONE" `
            -StderrSummary $stderrSummary `
            -FinalStatus " M src/example.py" `
            -FinalIndexClean $true `
            -FinalHeadMatchesInitial $true `
            -RuntimeContractBinding $binding
        [ordered]@{{
            requested_assurance = $requestedAssurance
            eligible = $eligible
            comment = $comment
        }} | ConvertTo-Json -Depth 12 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["requested_assurance"]["governance_scope"] == "passed"
    assert payload["requested_assurance"]["observable_evidence"] == "unverified"
    assert payload["requested_assurance"]["evidence_profile"] is None
    assert payload["requested_assurance"]["candidate_manifest_fingerprint"] is None
    assert payload["eligible"] is False
    assert "SHOULD-NOT-APPEAR" not in payload["comment"]
    marker_index = payload["comment"].index(
        "LAWBRUNNER-RESULT protocol=lawb.runner_result.v1"
    )
    json_start = payload["comment"].index("{", marker_index)
    summary, _ = json.JSONDecoder().raw_decode(payload["comment"][json_start:])
    assert summary["execution_assurance"]["observable_evidence"] == "unverified"
    assert summary["candidate_acceptance"] == "ineligible"
    assert summary["approval_token_generated"] is False


def test_execution_assurance_is_bounded_and_provider_isolation_defaults_unverified(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    binding = json.dumps(_binding("passed", allowed_files=["seed.txt"]))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $binding = '{binding}' | ConvertFrom-Json
        $manifest = Get-BoundedCandidateManifest -AllowedFiles @("seed.txt")
        $assurance = New-ExecutionAssurance `
            -RuntimeContractBinding $binding `
            -ObservableEvidence "verified" `
            -CandidateManifest $manifest
        $eligible = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -FinalIndexClean $true `
            -FinalHeadMatchesInitial $true `
            -ExecutionAssurance $assurance
        [ordered]@{{ assurance = $assurance; manifest = $manifest; eligible = $eligible }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["assurance"]["governance_scope"] == "passed"
    assert payload["assurance"]["observable_evidence"] == "verified"
    assert payload["assurance"]["evidence_profile"] == (
        "local_git_candidate_observation.v1"
    )
    assert payload["assurance"]["candidate_manifest_fingerprint"] == payload[
        "manifest"
    ]["fingerprint"]
    assert payload["assurance"]["isolation_guarantee"] == "unverified"
    assert payload["assurance"]["isolation_provider"] == "codex_cli_workspace_write"
    assert payload["assurance"]["isolation_evidence_source"] is None
    assert payload["eligible"] is True


def test_candidate_token_binds_scope_manifest_evidence_and_rejects_drift_or_upgrade(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "seed.txt").write_text("candidate one\n", encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $manifest = Get-BoundedCandidateManifest -AllowedFiles @("seed.txt")
        $state = Get-ApprovalState -IssueNumberForState 204 -RequireChanges -AllowedFiles @("seed.txt") -CandidateManifest $manifest
        $token = ConvertFrom-ApprovalToken -Token $state.ApprovalToken
        Assert-ApprovalMatchesState -Token $token -State $state

        Set-Content -LiteralPath {str(repo / 'seed.txt')!r} -Value "candidate two" -Encoding UTF8
        $driftManifest = Get-BoundedCandidateManifest -AllowedFiles @("seed.txt")
        $driftState = Get-ApprovalState -IssueNumberForState 204 -RequireChanges -AllowedFiles @("seed.txt") -CandidateManifest $driftManifest
        $driftRejected = $false
        try {{ Assert-ApprovalMatchesState -Token $token -State $driftState }} catch {{ $driftRejected = $true }}

        $forgedText = $state.ApprovalToken.Replace("isolation=unverified", "isolation=verified")
        $forgedToken = ConvertFrom-ApprovalToken -Token $forgedText
        $upgradeRejected = $false
        try {{ Assert-ApprovalMatchesState -Token $forgedToken -State $state }} catch {{ $upgradeRejected = $true }}

        [ordered]@{{
            scope = $state.AllowedScopeFingerprint
            manifest = $state.CandidateManifestFingerprint
            evidence = $state.EvidenceProfile
            isolation = $state.IsolationGuarantee
            drift_rejected = $driftRejected
            upgrade_rejected = $upgradeRejected
        }} | ConvertTo-Json -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert len(payload["scope"]) == 64
    assert len(payload["manifest"]) == 64
    assert payload["evidence"] == "local_git_candidate_observation.v1"
    assert payload["isolation"] == "unverified"
    assert payload["drift_rejected"] is True
    assert payload["upgrade_rejected"] is True


def test_successful_child_commit_with_clean_worktree_fails_closed(tmp_path):
    repo = tmp_path / "repo"
    head_before = init_git_repo(repo)
    child = tmp_path / "commit_child.ps1"
    child.write_text(
        textwrap.dedent(
            f"""
            Set-Content -LiteralPath {str(repo / 'committed.txt')!r} -Value "committed" -Encoding UTF8
            & git -C {str(repo)!r} add committed.txt
            if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
            & git -C {str(repo)!r} commit -q -m "child commit"
            exit $LASTEXITCODE
            """
        ).strip(),
        encoding="utf-8-sig",
    )
    binding = json.dumps(
        _binding("passed", allowed_files=["seed.txt"], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $before = Get-ReviewBundleGitObservation
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $child = Invoke-CapturedNativeProcess `
            -FilePath {_powershell()!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {repo.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 20 `
            -Action "simulated successful child commit"
        if ($child.ExitCode -ne 0) {{ throw "Child failed: $($child.Stderr)" }}
        $after = Get-ReviewBundleGitObservation
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage)
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles @() `
            -InvariantViolationReasons $reasons
        $noCommit = [string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
        $approvalAllowed = Test-ApprovalContextAllowed -RuntimeContractBinding $binding -NoStage $after.NoStage -NoCommit $noCommit
        $json = New-RunnerResultSummaryJson `
            -IssueNumberText "204" `
            -Action "run-reviewbundle" `
            -Result "failure" `
            -Branch "test" `
            -Head $after.Head `
            -ReviewId "" `
            -DiffFingerprint "" `
            -FilesFingerprint "" `
            -ChangedFilesText "(none)" `
            -FinalStatus $after.Status `
            -CodexExitCode "0" `
            -NoStage $after.NoStage `
            -NoCommit $noCommit `
            -ApprovalTokenGenerated $approvalAllowed `
            -RuntimeContractBinding $binding
        Write-Output $json
        """,
    )

    assert_success(result)
    summary = json.loads(result.stdout[result.stdout.index("{") :])
    assert head_before != summary["head"]
    assert summary["runtime_contract_binding"]["status"] == "contract_violation"
    assert "unexpected_head_movement" in summary["runtime_contract_binding"]["reasons"]
    assert summary["observations"]["final_head_matches_initial"] is False
    assert summary["observations"]["final_index_clean"] is True
    assert summary["approval_token_generated"] is False
    assert summary["candidate_acceptance"] == "ineligible"


def test_import_shadow_attack_is_rejected_without_post_child_python(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    module_dir = repo / "src" / "local_runner_bridge"
    module_dir.mkdir(parents=True)
    for name in (
        "runtime_contract_binding.py",
        "task_packet_validator.py",
        "task_surface_resolver.py",
    ):
        (module_dir / name).write_text(f"# trusted {name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "src"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "trusted evaluator"],
        check=True,
    )
    marker = tmp_path / "malicious-json-imported.txt"
    malicious = (
        f"open(r'{marker.as_posix()}', 'w').write('imported')\n"
        "def load(stream):\n"
        "    return dict(runtime_contract_binding=dict(status='passed'), actual_changed_files=[])\n"
        "def dumps(value, **kwargs):\n"
        "    return '{\"status\":\"passed\"}'\n"
    )
    child = tmp_path / "shadow_child.ps1"
    child.write_text(
        "$payload = @'\n"
        + malicious
        + "'@\n"
        + f"Set-Content -LiteralPath {str(module_dir / 'json.py')!r} -Value $payload -Encoding UTF8\n",
        encoding="utf-8-sig",
    )
    binding = json.dumps(
        _binding("passed", allowed_files=["seed.txt"], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $script:PostEvaluatorCalls = 0
        function Invoke-RuntimeContractEvaluator {{
            param([string]$Action, [object]$Payload, [string]$PythonPath = "")
            if ($Action -eq "post") {{ $script:PostEvaluatorCalls += 1 }}
            return [pscustomobject]@{{ status = "passed" }}
        }}
        $before = Get-ReviewBundleGitObservation
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $child = Invoke-CapturedNativeProcess `
            -FilePath {_powershell()!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {repo.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 20 `
            -Action "simulated import-shadow child"
        if ($child.ExitCode -ne 0) {{ throw "Child failed: $($child.Stderr)" }}
        $after = Get-ReviewBundleGitObservation
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage)
        $actualFiles = @(Convert-FileTextToArray -Text (Get-ModifiedFilesFromStatus -Status $after.Status))
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles $actualFiles `
            -InvariantViolationReasons $reasons
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $after.NoStage `
            -NoCommit ([string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
        )
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        $payload = [ordered]@{{
            child_exit = $child.ExitCode
            post_evaluator_calls = $script:PostEvaluatorCalls
            malicious_module_imported = Test-Path -LiteralPath {marker.as_posix()!r}
            actual_changed_files = $actualFiles
            binding = $binding
            approval_allowed = $approvalAllowed
            overall = $overall
        }}
        Write-Output ($payload | ConvertTo-Json -Depth 8 -Compress)
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["child_exit"] == 0
    assert payload["post_evaluator_calls"] == 0
    assert payload["malicious_module_imported"] is False
    assert payload["actual_changed_files"] == ["src/local_runner_bridge/json.py"]
    assert payload["binding"]["status"] == "contract_violation"
    assert "changed_file_outside_allowed_files" in payload["binding"]["reasons"]
    assert payload["approval_allowed"] is False
    assert payload["overall"] == "failure"


def test_allowed_runtime_evaluator_change_uses_parent_judge_and_can_pass(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    evaluator = repo / "src" / "local_runner_bridge" / "runtime_contract_binding.py"
    evaluator.parent.mkdir(parents=True)
    evaluator.write_text("# trusted evaluator\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "src"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "trusted evaluator"],
        check=True,
    )
    child = tmp_path / "allowed_evaluator_child.ps1"
    child.write_text(
        f"Set-Content -LiteralPath {str(evaluator)!r} -Value '# legitimate allowed evaluator change' -Encoding UTF8\n",
        encoding="utf-8-sig",
    )
    allowed_path = "src/local_runner_bridge/runtime_contract_binding.py"
    binding = json.dumps(
        _binding("passed", allowed_files=[allowed_path], max_allowed_files=1)
    )

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $script:PostEvaluatorCalls = 0
        function Invoke-RuntimeContractEvaluator {{
            param([string]$Action, [object]$Payload, [string]$PythonPath = "")
            if ($Action -eq "post") {{ $script:PostEvaluatorCalls += 1 }}
            throw "Workspace evaluator must not run after child execution."
        }}
        $before = Get-ReviewBundleGitObservation
        $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
        $child = Invoke-CapturedNativeProcess `
            -FilePath {_powershell()!r} `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(child)!r}) `
            -WorkingDirectory {repo.as_posix()!r} `
            -StandardInput "" `
            -StandardInputEncoding $utf8 `
            -StandardOutputEncoding $utf8 `
            -StandardErrorEncoding $utf8 `
            -TimeoutSeconds 20 `
            -Action "simulated allowed evaluator child"
        if ($child.ExitCode -ne 0) {{ throw "Child failed: $($child.Stderr)" }}
        $after = Get-ReviewBundleGitObservation
        $reasons = @(Get-ReviewBundleInvariantViolationReasons `
            -HeadBefore $before.Head `
            -HeadAfter $after.Head `
            -NoStage $after.NoStage)
        $actualFiles = @(Convert-FileTextToArray -Text (Get-ModifiedFilesFromStatus -Status $after.Status))
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles $actualFiles `
            -InvariantViolationReasons $reasons
        $manifest = Get-BoundedCandidateManifest -AllowedFiles @($binding.allowed_files)
        $assurance = New-ExecutionAssurance `
            -RuntimeContractBinding $binding `
            -ObservableEvidence "verified" `
            -CandidateManifest $manifest
        $noCommit = [string]::Equals($before.Head, $after.Head, [System.StringComparison]::OrdinalIgnoreCase)
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $after.NoStage `
            -NoCommit $noCommit `
            -ExecutionAssurance $assurance
        $overall = Get-OverallRunnerResult `
            -CodexExitCode "0" `
            -RuntimeContractBinding $binding `
            -ExecutionAssurance $assurance
        [ordered]@{{
            child_exit = $child.ExitCode
            post_evaluator_calls = $script:PostEvaluatorCalls
            head_unchanged = $noCommit
            no_stage = $after.NoStage
            actual_changed_files = $actualFiles
            binding = $binding
            approval_allowed = $approvalAllowed
            overall = $overall
        }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["child_exit"] == 0
    assert payload["post_evaluator_calls"] == 0
    assert payload["head_unchanged"] is True
    assert payload["no_stage"] is True
    assert payload["actual_changed_files"] == [allowed_path]
    assert payload["binding"]["status"] == "passed"
    assert payload["approval_allowed"] is True
    assert payload["overall"] == "success"


def test_trusted_runtime_evaluator_uses_committed_baseline_not_candidate(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    module_dir = repo / "src" / "local_runner_bridge"
    module_dir.mkdir(parents=True)
    for name in (
        "runtime_contract_binding.py",
        "task_packet_validator.py",
        "task_surface_resolver.py",
    ):
        shutil.copy2(REPO_ROOT / "src" / "local_runner_bridge" / name, module_dir / name)
    subprocess.run(["git", "-C", str(repo), "add", "src"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "trusted evaluator"],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    surface = textwrap.dedent(
        f"""
        LOCAL-RUNNER-TASK-PACKET-V1
        BEGIN_TASK_PACKET
        protocol: lawb.local_runner.task_packet.v1.1
        packet_id: trusted-oracle-test
        logical_issue: 204
        phase: correction
        action_type: implementation
        risk_level: medium
        repository: example/repo
        branch: {branch}
        expected_head: {head}
        allowed_files:
          - seed.txt
        forbidden_operations:
          - push
        approval:
          required: true
        payload:
          kind: issue
        result_target:
          github_issue: 204
          marker: LAWBRUNNER-RESULT
        stop_condition: fail_closed
        task_mode: PATCH_ONLY
        objective: Update seed.
        max_allowed_files: 1
        context_scope:
          - seed.txt
        repair_attempt_limit: 1
        verification_command_policy: explicit_only
        verification_commands:
          - pytest -q
        scope_expansion_allowed: false
        END_TASK_PACKET
        """
    ).strip()
    payload = json.dumps(
        {
            "surface_text": surface,
            "logical_issue": 204,
            "repository": "example/repo",
            "branch": branch,
            "head": head,
        }
    )
    invalid_payload = json.dumps(
        {
            "surface_text": surface,
            "logical_issue": 999,
            "repository": "example/repo",
            "branch": branch,
            "head": head,
        }
    )
    malicious = (
        "import json\n"
        "print(json.dumps({'status':'passed','contract_present':True,"
        "'pre_execution':{'status':'passed','reasons':[]},"
        "'post_execution':{'status':'not_run','reasons':[]},"
        "'allowed_files':['seed.txt'],'actual_changed_files':[],"
        "'reasons':[],'runtime_contract':{'max_allowed_files':1}}))\n"
    )
    (module_dir / "runtime_contract_binding.py").write_text(malicious, encoding="utf-8")

    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $python = Resolve-PythonRuntimeCommand
        $normal = Invoke-RuntimeContractEvaluator `
            -Action "inspect" `
            -PythonPath $python `
            -TrustedCommittedBaseline `
            -Payload ('{payload}' | ConvertFrom-Json)
        $workspaceOracle = Invoke-RuntimeContractEvaluator `
            -Action "inspect" `
            -PythonPath $python `
            -Payload ('{invalid_payload}' | ConvertFrom-Json)
        $trustedOracle = Invoke-RuntimeContractEvaluator `
            -Action "inspect" `
            -PythonPath $python `
            -TrustedCommittedBaseline `
            -Payload ('{invalid_payload}' | ConvertFrom-Json)
        [ordered]@{{
            normal = $normal
            workspace_oracle = $workspaceOracle
            trusted_oracle = $trustedOracle
        }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    result_payload = json.loads(result.stdout)
    assert result_payload["normal"]["status"] == "passed"
    assert result_payload["workspace_oracle"]["status"] == "passed"
    assert result_payload["trusted_oracle"]["status"] == "contract_violation"
    assert "logical_issue_mismatch" in result_payload["trusted_oracle"]["reasons"]


def test_contract_violation_suppresses_approval_context(tmp_path):
    binding = json.dumps(_binding("contract_violation"))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $binding = '{binding}' | ConvertFrom-Json
        $allowed = Test-ApprovalContextAllowed -RuntimeContractBinding $binding -NoStage $true -NoCommit $true
        Write-Output ($allowed | ConvertTo-Json -Compress)
        """,
    )

    assert_success(result)
    assert json.loads(result.stdout) is False


def _binding(
    status: str,
    *,
    contract_present: bool = True,
    allowed_files: list[str] | None = None,
    max_allowed_files: int = 1,
) -> dict:
    stage_status = "passed" if status == "passed" else status
    allowed = ["src/example.py"] if allowed_files is None else allowed_files
    result = {
        "status": status,
        "contract_present": contract_present,
        "pre_execution": {"status": stage_status, "reasons": []},
        "post_execution": {"status": stage_status, "reasons": []},
        "allowed_files": allowed if contract_present else [],
        "actual_changed_files": ["src/example.py"] if contract_present else [],
        "reasons": (
            ["changed_file_outside_allowed_files"]
            if status == "contract_violation"
            else []
        ),
    }
    if contract_present:
        result["runtime_contract"] = {
            "allowed_files": allowed,
            "max_allowed_files": max_allowed_files,
            "verification_commands": ["python -m pytest -q"],
        }
    return result


def test_parent_controlled_enforcement_allows_normal_task(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    candidate = repo / "src" / "example.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("candidate\n", encoding="utf-8")
    binding = json.dumps(
        _binding("passed", allowed_files=["src/example.py"], max_allowed_files=1)
    )
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles @("src\\example.py") `
            -InvariantViolationReasons @()
        $manifest = Get-BoundedCandidateManifest -AllowedFiles @($binding.allowed_files)
        $assurance = New-ExecutionAssurance `
            -RuntimeContractBinding $binding `
            -ObservableEvidence "verified" `
            -CandidateManifest $manifest
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $true `
            -NoCommit $true `
            -ExecutionAssurance $assurance
        [ordered]@{{ binding = $binding; approval_allowed = $approvalAllowed }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["binding"]["status"] == "passed"
    assert payload["binding"]["post_execution"] == {
        "status": "passed",
        "reasons": [],
    }
    assert payload["binding"]["actual_changed_files"] == ["src/example.py"]
    assert payload["approval_allowed"] is True


@pytest.mark.parametrize(
    ("actual_files", "allowed_files", "maximum", "expected_reason"),
    [
        (["README.md"], ["src/example.py"], 1, "changed_file_outside_allowed_files"),
        (["a.py", "b.py"], ["a.py", "b.py"], 1, "changed_file_count_exceeds_max_allowed_files"),
        (["C:/outside.py"], ["src/example.py"], 1, "invalid_actual_changed_file"),
    ],
)
def test_parent_controlled_enforcement_fails_closed_on_scope_violations(
    tmp_path, actual_files, allowed_files, maximum, expected_reason
):
    binding = json.dumps(
        _binding(
            "passed",
            allowed_files=allowed_files,
            max_allowed_files=maximum,
        )
    )
    actual = ",".join(json.dumps(value) for value in actual_files)
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $binding = '{binding}' | ConvertFrom-Json
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding $binding `
            -ActualChangedFiles @({actual}) `
            -InvariantViolationReasons @()
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $true `
            -NoCommit $true
        [ordered]@{{ binding = $binding; approval_allowed = $approvalAllowed }} | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["binding"]["status"] == "contract_violation"
    assert expected_reason in payload["binding"]["reasons"]
    assert payload["approval_allowed"] is False


def test_parent_controlled_enforcement_preserves_legacy_reporting_but_suppresses_eligibility(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $binding = Invoke-ParentControlledRuntimeContractEnforcement `
            -RuntimeContractBinding (New-RuntimeContractNotPresent) `
            -ActualChangedFiles @("legacy.py") `
            -InvariantViolationReasons @()
        $approvalAllowed = Test-ApprovalContextAllowed `
            -RuntimeContractBinding $binding `
            -NoStage $true `
            -NoCommit $true
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        [ordered]@{ binding = $binding; approval_allowed = $approvalAllowed; overall = $overall } | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout)
    assert payload["binding"]["status"] == "not_present"
    assert payload["binding"]["post_execution"]["status"] == "not_present"
    assert payload["binding"]["actual_changed_files"] == ["legacy.py"]
    assert payload["approval_allowed"] is False
    assert payload["overall"] == "success"


def test_runner_result_explicitly_reports_legacy_runtime_contract_not_present(tmp_path):
    result = run_timeout_guard_script(
        tmp_path,
        """
        $binding = New-RuntimeContractNotPresent
        $json = New-RunnerResultSummaryJson `
            -IssueNumberText "204" `
            -Action "run-reviewbundle" `
            -Result "success" `
            -Branch "feature/runtime-contract" `
            -Head ("1" * 40) `
            -ReviewId "" `
            -DiffFingerprint "" `
            -FilesFingerprint "" `
            -ChangedFilesText "legacy.py" `
            -FinalStatus " M legacy.py" `
            -CodexExitCode "0" `
            -NoStage $true `
            -NoCommit $true `
            -ApprovalTokenGenerated $false `
            -RuntimeContractBinding $binding
        Write-Output $json
        """,
    )
    assert_success(result)
    summary = json.loads(result.stdout)
    assert summary["runtime_contract_binding"]["status"] == "not_present"
    assert summary["runtime_contract_binding"]["contract_present"] is False
    assert summary["runtime_contract_binding"]["pre_execution"]["status"] == "not_present"
    assert summary["execution_assurance"]["governance_scope"] == "not_present"
    assert summary["execution_assurance"]["isolation_guarantee"] == "unverified"
    assert summary["candidate_acceptance"] == "ineligible"
    assert summary["approval_token_generated"] is False


def test_runner_result_reports_snapshot_eligibility_without_isolation_overclaim(tmp_path):
    repo = tmp_path / "repo"
    init_git_repo(repo)
    binding = json.dumps(_binding("passed", allowed_files=["seed.txt"]))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $binding = '{binding}' | ConvertFrom-Json
        $manifest = Get-BoundedCandidateManifest -AllowedFiles @("seed.txt")
        $assurance = New-ExecutionAssurance `
            -RuntimeContractBinding $binding `
            -ObservableEvidence "verified" `
            -CandidateManifest $manifest
        $json = New-RunnerResultSummaryJson `
            -IssueNumberText "204" `
            -Action "run-reviewbundle" `
            -Result "success" `
            -Branch "feature/runtime-contract" `
            -Head ("1" * 40) `
            -ReviewId "review" `
            -DiffFingerprint ("2" * 64) `
            -FilesFingerprint ("3" * 64) `
            -ChangedFilesText "src/example.py" `
            -FinalStatus " M src/example.py" `
            -CodexExitCode "0" `
            -FinalIndexClean $true `
            -FinalHeadMatchesInitial $true `
            -ApprovalTokenGenerated $true `
            -RuntimeContractBinding $binding `
            -ExecutionAssurance $assurance `
            -CandidateEvidenceManifest $manifest
        Write-Output $json
        """,
    )

    assert_success(result)
    summary = json.loads(result.stdout)
    assert summary["candidate_acceptance"] == "eligible"
    assert summary["approval_token_semantics"] == "candidate_review_snapshot_not_human_approval"
    assert summary["execution_assurance"]["observable_evidence"] == "verified"
    assert summary["execution_assurance"]["isolation_guarantee"] == "unverified"
    assert summary["trusted_parent_actions"]["push_invoked"] is False


def test_pre_execution_contract_violation_blocks_before_fake_codex(tmp_path):
    binding = json.dumps(_binding("contract_violation"))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:CodexCalls = 0
        $binding = '{binding}' | ConvertFrom-Json
        try {{
            Assert-RuntimeContractAllowsCodex -RuntimeContractBinding $binding
            $script:CodexCalls += 1
        }}
        catch {{
            Write-Output "BLOCKED=$($_.Exception.Message)"
        }}
        Write-Output "CODEX_CALLS=$script:CodexCalls"
        """,
    )
    assert_success(result)
    assert "Runtime contract violation blocks Codex execution" in result.stdout
    assert "CODEX_CALLS=0" in result.stdout


def test_codex_exit_zero_cannot_override_runtime_contract_violation(tmp_path):
    binding = json.dumps(_binding("contract_violation"))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $binding = '{binding}' | ConvertFrom-Json
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        if ($overall -ne "failure") {{ throw "Contract violation was overridden: $overall" }}
        Write-Output "OVERALL=$overall"
        """,
    )
    assert_success(result)
    assert "OVERALL=failure" in result.stdout


def test_codex_exit_zero_with_passed_runtime_contract_may_succeed(tmp_path):
    binding = json.dumps(_binding("passed"))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $binding = '{binding}' | ConvertFrom-Json
        $overall = Get-OverallRunnerResult -CodexExitCode "0" -RuntimeContractBinding $binding
        if ($overall -ne "success") {{ throw "Passed contract did not permit success: $overall" }}
        Write-Output "OVERALL=$overall"
        """,
    )
    assert_success(result)
    assert "OVERALL=success" in result.stdout


def test_review_bundle_machine_result_contains_violation_and_reports_failure(tmp_path):
    binding = json.dumps(_binding("contract_violation"))
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $binding = '{binding}' | ConvertFrom-Json
        $stderrSummary = Get-StderrSummary -Text "" -ExitCode "0"
        $comment = New-ReviewBundleComment `
            -IssueNumberText "204" `
            -Branch "feature/runtime-contract" `
            -HeadBefore "1111111" `
            -HeadAfter "1111111" `
            -CodexExitCode "0" `
            -RepoCleanBefore "yes" `
            -ReviewId "" `
            -DiffFingerprint "" `
            -FilesFingerprint "" `
            -ApprovalToken "SHOULD-NOT-APPEAR" `
            -ModifiedFiles "README.md" `
            -DiffStat "" `
            -CachedDiffStat "" `
            -CommandsSummary "fake" `
            -CodexFinalReport "DONE" `
            -StderrSummary $stderrSummary `
            -FinalStatus " M README.md" `
            -NoStage $true `
            -NoCommit $true `
            -RuntimeContractBinding $binding
        Write-Output $comment
        """,
    )
    assert_success(result)
    marker_index = result.stdout.index("LAWBRUNNER-RESULT protocol=lawb.runner_result.v1")
    json_start = result.stdout.index("{", marker_index)
    decoder = json.JSONDecoder()
    summary, _ = decoder.raw_decode(result.stdout[json_start:])
    assert summary["result"] == "failure"
    assert summary["validations"]["codex"]["status"] == "passed"
    assert summary["runtime_contract_binding"]["status"] == "contract_violation"
    assert summary["runtime_contract_binding"]["actual_changed_files"] == [
        "src/example.py"
    ]
    assert summary["approval_token_generated"] is False
    assert summary["observations"]["final_index_clean"] is True
    assert summary["observations"]["final_head_matches_initial"] is True
    assert summary["trusted_parent_actions"]["push_invoked"] is False
    assert "SHOULD-NOT-APPEAR" not in result.stdout


def test_runner_main_orders_contract_checks_around_codex_invocation():
    source = RUNNER.read_text(encoding="utf-8")
    inspect_index = source.index('-Action "inspect"')
    assert_index = source.index("Assert-RuntimeContractAllowsCodex", inspect_index)
    pre_observation_index = source.index(
        "$preExecutionObservation = Get-ReviewBundleGitObservation", assert_index
    )
    codex_index = source.index('-Action "codex ReviewBundle candidate generation"')
    effective_changed_files_index = source.index(
        "Get-ReviewBundleEffectiveChangedFiles", codex_index
    )
    invariant_index = source.index("Get-ReviewBundleInvariantViolationReasons", codex_index)
    parent_enforcement_index = source.index(
        "Invoke-ParentControlledRuntimeContractEnforcement", codex_index
    )
    approval_gate_index = source.index(
        "Test-ApprovalContextAllowed", parent_enforcement_index
    )
    overall_index = source.index("$overallExitCode", parent_enforcement_index)

    assert (
        inspect_index
        < assert_index
        < pre_observation_index
        < codex_index
        < effective_changed_files_index
        < invariant_index
        < parent_enforcement_index
        < approval_gate_index
        < overall_index
    )
    assert "Invoke-RuntimeContractEvaluator" not in source[codex_index:]
    assert '-Action "post"' not in source


def test_commit_approved_rereads_changed_contract_source_and_blocks_before_stage(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_gh = tmp_path / "gh.exe"
    fake_gh.write_text("fixture", encoding="utf-8")
    result = run_timeout_guard_script(
        tmp_path,
        f"""
        $script:RepoPath = {repo.as_posix()!r}
        $script:Gh = {fake_gh.as_posix()!r}
        $script:IssueNumber = 204
        $script:ApprovalToken = "fixture-token"
        $script:IssueReadCount = 0
        $script:BoundBodies = @()
        $script:StageCalls = 0

        function Assert-RepositoryLocalGitIdentity {{ return $null }}
        function Test-IssueAllowsWriteCapableRun {{ return $true }}
        function Get-CommitApprovedIssueSnapshot {{
            $script:IssueReadCount += 1
            if ($script:IssueReadCount -eq 1) {{
                return [pscustomobject]@{{
                    number = 204
                    title = "initial title"
                    body = "initial contract source"
                }}
            }}
            return [pscustomobject]@{{
                number = 204
                title = "current title"
                body = "materially changed contract source"
            }}
        }}
        function Get-CommitApprovedBoundState {{
            param([string]$IssueBody)
            $script:BoundBodies += $IssueBody
            if ($IssueBody -ne "initial contract source") {{
                throw "current contract drift detected"
            }}
            return [pscustomobject]@{{
                ApprovalState = [pscustomobject]@{{
                    Branch = "feature/rebaseline"
                    Head = ("1" * 40)
                    ReviewId = "review"
                    DiffFingerprint = ("2" * 64)
                    FilesFingerprint = ("3" * 64)
                    ModifiedFilesText = "seed.txt"
                    ModifiedFiles = @("seed.txt")
                }}
            }}
        }}
        function ConvertFrom-ApprovalToken {{
            param([string]$Token)
            return [pscustomobject]@{{ raw = $Token }}
        }}
        function Assert-ApprovalMatchesState {{ param([object]$Token, [object]$State) }}
        function Invoke-Captured {{
            param([scriptblock]$ScriptBlock)
            $script:StageCalls += 1
            return [pscustomobject]@{{ ExitCode = 0; Stdout = ""; Stderr = "" }}
        }}

        $blocked = $false
        $blockMessage = ""
        try {{ Invoke-CommitApprovedMode }}
        catch {{
            $blocked = $true
            $blockMessage = $_.Exception.Message
        }}
        [ordered]@{{
            issue_reads = $script:IssueReadCount
            bound_bodies = @($script:BoundBodies)
            blocked = $blocked
            block_message = $blockMessage
            stage_calls = $script:StageCalls
        }} | ConvertTo-Json -Depth 6 -Compress
        """,
    )

    assert_success(result)
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["issue_reads"] == 2
    assert payload["bound_bodies"] == [
        "initial contract source",
        "materially changed contract source",
    ]
    assert payload["blocked"] is True
    assert "current contract drift detected" in payload["block_message"]
    assert payload["stage_calls"] == 0


def test_commit_approved_rebinds_current_contract_and_snapshot_before_staging():
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("function Invoke-CommitApprovedMode")
    end = source.index("\nif (-not (Test-Path -LiteralPath $RepoPath))", start)
    body = source[start:end]

    assert body.count("Get-CommitApprovedIssueSnapshot") == 2
    first_read = body.index("$issue = Get-CommitApprovedIssueSnapshot")
    first_rebind = body.index("Get-CommitApprovedBoundState -IssueBody $issueBody")
    token_parse = body.index("ConvertFrom-ApprovalToken", first_rebind)
    second_read = body.index("$currentIssue = Get-CommitApprovedIssueSnapshot", token_parse)
    second_rebind = body.index(
        "Get-CommitApprovedBoundState -IssueBody $currentIssueBody", second_read
    )
    token_match = body.index("Assert-ApprovalMatchesState", second_rebind)
    stage = body.index("git -C $RepoPath add", token_match)

    assert (
        first_read
        < first_rebind
        < token_parse
        < second_read
        < second_rebind
        < token_match
        < stage
    )
    bound_state_start = source.index("function Get-CommitApprovedBoundState")
    bound_state_end = source.index("function Get-CommitApprovedIssueSnapshot", bound_state_start)
    assert "-TrustedCommittedBaseline" in source[bound_state_start:bound_state_end]


def test_runtime_contract_integration_does_not_execute_verification_commands():
    source = RUNNER.read_text(encoding="utf-8")

    assert "verification_commands" not in source
    assert "Invoke-RuntimeContractEvaluator" in source
