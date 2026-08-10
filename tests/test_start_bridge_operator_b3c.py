from __future__ import annotations

import ast
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_SOURCE = REPO_ROOT / "scripts" / "start_bridge_operator_b3c.ps1"
EXPECTED_ORIGIN = "https://github.com/HarryWhite-TW/local-ai-workbench.git"
HAG_ORIGIN = "https://github.com/HarryWhite-TW/human-approval-automation-gateway.git"
sys.path.insert(0, str(REPO_ROOT / "src"))

from local_runner_bridge.bridge_operator_b1 import (  # noqa: E402
    CommentRecord,
    IssueRecord,
    LocalReadiness,
    run_bridge_operator_b1_dry_run,
)


def powershell() -> str:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("Windows PowerShell is required for B3-C launcher tests")
    return found


def run_process(args: list[str], *, cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        errors="replace",
        check=False,
    )


def run_process_bytes(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=False,
        timeout=timeout,
        check=False,
    )


def windows_process_is_running(process_id: int) -> bool:
    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    handle = ctypes.windll.kernel32.OpenProcess(
        synchronize,
        False,
        process_id,
    )
    if not handle:
        return False
    try:
        wait_result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
        if wait_result == wait_object_0:
            return False
        if wait_result == wait_timeout:
            return True
        raise ctypes.WinError()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def terminate_windows_process_tree(process_id: int) -> None:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    taskkill = Path(system_root) / "System32" / "taskkill.exe"
    if not taskkill.is_file():
        return
    subprocess.run(
        [str(taskkill), "/PID", str(process_id), "/T", "/F"],
        capture_output=True,
        timeout=5,
        check=False,
    )


def launcher_function_source(start_name: str, next_name: str) -> str:
    source = LAUNCHER_SOURCE.read_text(encoding="utf-8")
    start = source.index(f"function {start_name} {{")
    end = source.index(f"function {next_name} {{", start)
    return source[start:end]


def run_stderr_summary_probe(tmp_path: Path, text: str) -> str:
    function = launcher_function_source(
        "Get-SafeStderrSummary",
        "ConvertTo-WindowsCommandLineArgument",
    )
    encoded = __import__("base64").b64encode(text.encode("utf-8")).decode("ascii")
    probe = tmp_path / "stderr-summary-probe.ps1"
    probe.write_text(
        function
        + f"""
$text = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('{encoded}')
)
$result = [ordered]@{{ summary = Get-SafeStderrSummary -Text $text }}
$json = $result | ConvertTo-Json -Compress
$bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(
    $json + [Environment]::NewLine
)
[Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
""",
        encoding="ascii",
    )
    result = run_process_bytes(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.decode("utf-8", errors="strict"))["summary"]


def run_decoder_probe(tmp_path: Path, data: bytes, policy: str) -> dict:
    functions = launcher_function_source(
        "ConvertFrom-NativeBytes",
        "Invoke-CapturedNative",
    )
    byte_values = ", ".join(str(value) for value in data)
    probe = tmp_path / "decoder-probe.ps1"
    probe.write_text(
        functions
        + f"""
$result = ConvertFrom-NativeBytes `
    -Bytes ([byte[]]@({byte_values})) `
    -EncodingPolicy "{policy}"
$json = $result | ConvertTo-Json -Compress
$bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(
    $json + [Environment]::NewLine
)
[Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
""",
        encoding="ascii",
    )
    result = run_process_bytes(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


def run_status_outcome_probe(
    tmp_path: Path,
    native_result: dict,
    expected_comment_id: int | None = None,
) -> dict:
    functions = (
        launcher_function_source("Get-JsonObject", "Get-ObjectProperty")
        + launcher_function_source("Get-ObjectProperty", "Test-TrueProperty")
        + launcher_function_source(
            "Get-StatusWriteOutcome",
            "Test-AbsoluteExistingFile",
        )
    )
    encoded = __import__("base64").b64encode(
        json.dumps(native_result, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    expected = "$null" if expected_comment_id is None else str(expected_comment_id)
    probe = tmp_path / "status-outcome-probe.ps1"
    probe.write_text(
        functions
        + f"""
$nativeJson = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('{encoded}')
)
$nativeResult = $nativeJson | ConvertFrom-Json
$outcome = Get-StatusWriteOutcome `
    -NativeResult $nativeResult `
    -ExpectedCommentId {expected}
$json = $outcome | ConvertTo-Json -Compress
$bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(
    $json + [Environment]::NewLine
)
[Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
""",
        encoding="ascii",
    )
    result = run_process_bytes(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


def run_taskkill_success_verification_probe(tmp_path: Path) -> dict:
    fake_taskkill = tmp_path / "fake-taskkill.exe"
    taskkill_marker = tmp_path / "fake-taskkill-invoked.txt"
    child_pid_path = tmp_path / "fake-taskkill-child.pid"
    child_helper = tmp_path / "fake-taskkill-child.py"
    root_helper = tmp_path / "fake-taskkill-root.py"
    child_helper.write_text(
        "import time\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    root_helper.write_text(
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, os.environ['B3C_TEST_CHILD']])\n"
        "Path(os.environ['B3C_TEST_CHILD_PID']).write_text(\n"
        "    str(child.pid), encoding='ascii'\n"
        ")\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    source = launcher_function_source(
        "Stop-NativeProcessTree",
        "Invoke-CapturedNative",
    )
    trusted_taskkill = (
        'Join-Path ([System.Environment]::SystemDirectory) "taskkill.exe"'
    )
    assert source.count(trusted_taskkill) == 1
    source = source.replace(
        trusted_taskkill,
        f"'{str(fake_taskkill).replace(chr(39), chr(39) * 2)}'",
    )
    fake_taskkill_literal = str(fake_taskkill).replace("'", "''")
    python_literal = sys.executable.replace("'", "''")
    root_helper_argument = str(root_helper).replace('"', '\\"')
    working_directory_literal = str(tmp_path).replace("'", "''")
    probe = tmp_path / "taskkill-success-verification-probe.ps1"
    probe.write_text(
        f"""
$ProcessTreeTerminationTimeoutMilliseconds = 3000
$CleanupCommandKillWaitMilliseconds = 1000
Add-Type -Language CSharp -OutputType ConsoleApplication `
    -OutputAssembly '{fake_taskkill_literal}' `
    -TypeDefinition @'
using System;
using System.IO;

public static class Program
{{
    public static int Main(string[] arguments)
    {{
        File.WriteAllText(
            Environment.GetEnvironmentVariable("B3C_TEST_TASKKILL_MARKER"),
            String.Join(" ", arguments)
        );
        return 0;
    }}
}}
'@
{source}
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = '{python_literal}'
$startInfo.Arguments = '"{root_helper_argument}"'
$startInfo.WorkingDirectory = '{working_directory_literal}'
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$root = New-Object System.Diagnostics.Process
$root.StartInfo = $startInfo
[void]$root.Start()
$childDeadline = [DateTime]::UtcNow.AddSeconds(5)
while (-not (Test-Path -LiteralPath $env:B3C_TEST_CHILD_PID) -and
    [DateTime]::UtcNow -lt $childDeadline) {{
    Start-Sleep -Milliseconds 20
}}
if (-not (Test-Path -LiteralPath $env:B3C_TEST_CHILD_PID)) {{
    throw "child_pid_not_published"
}}
$childId = [int](
    Get-Content -LiteralPath $env:B3C_TEST_CHILD_PID -Raw -Encoding ASCII
)
$timer = [Diagnostics.Stopwatch]::StartNew()
$terminationSucceeded = Stop-NativeProcessTree -TargetProcessId $root.Id
$elapsedMilliseconds = $timer.ElapsedMilliseconds
$childRunningAfterStop = $false
try {{
    $child = [Diagnostics.Process]::GetProcessById($childId)
    $childRunningAfterStop = -not $child.HasExited
    if ($childRunningAfterStop) {{
        $child.Kill()
        [void]$child.WaitForExit(1000)
    }}
    $child.Dispose()
}}
catch [System.ArgumentException] {{
}}
$rootRunningAfterStop = -not $root.HasExited
if ($rootRunningAfterStop) {{
    $root.Kill()
    [void]$root.WaitForExit(1000)
}}
$root.Dispose()
$result = [ordered]@{{
    process_tree_termination_succeeded = [bool]$terminationSucceeded
    child_running_after_stop = $childRunningAfterStop
    root_running_after_stop = $rootRunningAfterStop
    elapsed_milliseconds = $elapsedMilliseconds
    taskkill_marker_exists = Test-Path -LiteralPath $env:B3C_TEST_TASKKILL_MARKER
}}
$json = $result | ConvertTo-Json -Compress
$bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(
    $json + [Environment]::NewLine
)
[Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "B3C_TEST_CHILD": str(child_helper),
            "B3C_TEST_CHILD_PID": str(child_pid_path),
            "B3C_TEST_TASKKILL_MARKER": str(taskkill_marker),
        }
    )
    result = run_process_bytes(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
        ],
        cwd=tmp_path,
        env=env,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.decode("utf-8", errors="strict"))


def run_cmd_argument_probe(tmp_path: Path, argument: str) -> tuple[dict, Path, Path]:
    functions = launcher_function_source(
        "ConvertTo-WindowsCommandLineArgument",
        "Test-NativeCaptureDecoded",
    )
    invoked_marker = tmp_path / "child-invoked.marker"
    injection_marker = tmp_path / "injected-command.marker"
    argument = argument.replace("{INJECTION_MARKER}", str(injection_marker))
    fake_cmd = tmp_path / "fake child with spaces.cmd"
    fake_cmd.write_text(
        '@echo off\r\n>"%B3C_TEST_CMD_INVOKED%" echo invoked\r\n'
        'echo {"result":"success"}\r\n',
        encoding="ascii",
    )
    escaped_argument = argument.replace("'", "''")
    probe = tmp_path / "cmd-argument-probe.ps1"
    probe.write_text(
        functions
        + f"""
$result = Invoke-CapturedNative `
    -CommandPath '{str(fake_cmd).replace("'", "''")}' `
    -Arguments @('{escaped_argument}') `
    -WorkingDirectory '{str(tmp_path).replace("'", "''")}' `
    -EncodingPolicy "utf-8"
$json = $result | ConvertTo-Json -Compress
$bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(
    $json + [Environment]::NewLine
)
[Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
""",
        encoding="ascii",
    )
    env = os.environ.copy()
    env["B3C_TEST_CMD_INVOKED"] = str(invoked_marker)
    result = run_process_bytes(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
        ],
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return (
        json.loads(result.stdout.decode("utf-8", errors="strict")),
        invoked_marker,
        injection_marker,
    )


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run_process(["git", "-C", str(root), *args], cwd=root)
    assert result.returncode == 0, result.stderr
    return result


def init_git_repo(root: Path, origin: str = EXPECTED_ORIGIN) -> None:
    root.mkdir(parents=True, exist_ok=True)
    result = run_process(["git", "init", "-b", "master", str(root)], cwd=root.parent)
    if result.returncode != 0:
        result = run_process(["git", "init", str(root)], cwd=root.parent)
        assert result.returncode == 0, result.stderr
        git(root, "checkout", "-b", "master")
    git(root, "config", "user.name", "Launcher Test")
    git(root, "config", "user.email", "launcher-test@example.invalid")
    git(root, "remote", "add", "origin", origin)


def write_fake_bootstrap(path: Path) -> None:
    path.write_text(
        r"""
param(
    [string]$RepoRoot,
    [switch]$Json,
    [switch]$Apply,
    [switch]$PersistUserPath,
    [switch]$CompleteRecovery
)
if (-not [string]::IsNullOrWhiteSpace($env:B3C_TEST_BOOTSTRAP_LOG)) {
    [ordered]@{
        RepoRoot = $RepoRoot
        Json = [bool]$Json
        Apply = [bool]$Apply
        PersistUserPath = [bool]$PersistUserPath
        CompleteRecovery = [bool]$CompleteRecovery
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $env:B3C_TEST_BOOTSTRAP_LOG -Encoding UTF8
}
if (-not [string]::IsNullOrWhiteSpace($env:B3C_TEST_BOOTSTRAP_STDERR)) {
    [Console]::Error.WriteLine($env:B3C_TEST_BOOTSTRAP_STDERR)
}
if (-not [string]::IsNullOrWhiteSpace($env:B3C_TEST_BOOTSTRAP_JSON)) {
    $bootstrapText = Get-Content -LiteralPath $env:B3C_TEST_BOOTSTRAP_JSON -Raw -Encoding UTF8
    if ($env:B3C_TEST_BOOTSTRAP_ENCODING -eq "invalid") {
        $bootstrapBytes = [byte[]]@(0x81)
        [Console]::OpenStandardOutput().Write(
            $bootstrapBytes,
            0,
            $bootstrapBytes.Length
        )
    }
    elseif ($env:B3C_TEST_BOOTSTRAP_ENCODING -eq "cp950") {
        $bootstrapBytes = [Text.Encoding]::GetEncoding(950).GetBytes($bootstrapText)
        [Console]::OpenStandardOutput().Write(
            $bootstrapBytes,
            0,
            $bootstrapBytes.Length
        )
    }
    else {
        $bootstrapText
    }
}
$exitCode = 0
if (-not [string]::IsNullOrWhiteSpace($env:B3C_TEST_BOOTSTRAP_EXIT)) {
    $exitCode = [int]$env:B3C_TEST_BOOTSTRAP_EXIT
}
exit $exitCode
""".strip()
        + "\n",
        encoding="utf-8",
    )


def write_fake_operator(path: Path) -> None:
    path.write_text(
        r"""@echo off
if not "%B3C_TEST_OPERATOR_LOG%"=="" >>"%B3C_TEST_OPERATOR_LOG%" echo INVOCATION
if not "%B3C_TEST_OPERATOR_LOG%"=="" >>"%B3C_TEST_OPERATOR_LOG%" echo ARGS=%*
if not "%B3C_TEST_OPERATOR_LOG%"=="" >>"%B3C_TEST_OPERATOR_LOG%" echo PATH=%PATH%
if not "%B3C_TEST_OPERATOR_LOG%"=="" >>"%B3C_TEST_OPERATOR_LOG%" echo PYTHONPATH=%PYTHONPATH%
if not "%B3C_TEST_OPERATOR_STDERR%"=="" 1>&2 echo %B3C_TEST_OPERATOR_STDERR%
if not "%B3C_TEST_OPERATOR_JSON%"=="" type "%B3C_TEST_OPERATOR_JSON%"
if "%B3C_TEST_OPERATOR_EXIT%"=="" exit /b 0
exit /b %B3C_TEST_OPERATOR_EXIT%
""",
        encoding="ascii",
    )


def write_fake_gh(path: Path, helper: Path) -> None:
    helper.write_text(
        r"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
method = args[args.index("--method") + 1]
endpoint = args[args.index("--method") + 2]
request_body = sys.stdin.buffer.read()
log_path = Path(os.environ["B3C_TEST_GH_LOG"])
invocation_count = 1
if log_path.exists():
    invocation_count += sum(
        1 for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()
    )
record = {
    "executable_path": os.environ["B3C_TEST_GH_EXECUTABLE"],
    "method": method,
    "endpoint": endpoint,
    "args": args,
    "request_body": request_body.decode("utf-8", errors="strict"),
    "invocation_count": invocation_count,
}
with log_path.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

mode = os.environ.get("B3C_TEST_GH_MODE", "success")
is_create = method == "POST"
if (is_create and mode == "create_failure") or (
    not is_create and mode == "update_failure"
):
    raise SystemExit(7)
if (is_create and mode == "create_timeout") or (
    not is_create and mode == "update_timeout"
):
    time.sleep(3)
if is_create and mode == "create_tree_timeout":
    Path(os.environ["B3C_TEST_GH_CHILD_PID"]).write_text(
        str(os.getpid()),
        encoding="ascii",
    )
    time.sleep(60)
if (is_create and mode == "create_invalid_utf8") or (
    not is_create and mode == "update_invalid_utf8"
):
    sys.stdout.buffer.write(b"\x81")
    raise SystemExit(0)
if (is_create and mode == "create_malformed") or (
    not is_create and mode == "update_malformed"
):
    sys.stdout.write("{not-json")
    raise SystemExit(0)
if is_create and mode == "create_missing_id":
    sys.stdout.write("{}")
    raise SystemExit(0)
if is_create and mode == "create_non_integer_id":
    sys.stdout.write('{"id":"45123"}')
    raise SystemExit(0)
comment_id = 45123
if not is_create and mode == "update_id_mismatch":
    comment_id = 45124
sys.stdout.write(json.dumps({"id": comment_id}, separators=(",", ":")))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    path.write_text(
        f'@echo off\r\n"{sys.executable}" "{helper}" %*\r\nexit /b %ERRORLEVEL%\r\n',
        encoding="ascii",
    )


def ready_bootstrap_payload(
    *,
    python_path: Path,
    gh_path: Path,
    codex_path: Path,
) -> dict:
    return {
        "overall_status": "READY",
        "blockers": [],
        "attention": [],
        "manual_actions_required": [],
        "venv": {
            "python": str(python_path),
            "pip_ready": True,
        },
        "dependencies": {"ready": True},
        "detected": {
            "gh": {
                "path": str(gh_path),
                "version": "gh version 2.95.0",
                "ready": True,
                "authenticated": True,
            },
            "codex": {
                "path": str(codex_path),
                "command_version": "codex-cli 0.106.0",
                "command_usable": True,
                "ready": True,
            },
        },
    }


class LauncherHarness:
    def __init__(self, base: Path, *, name: str = "control repo with spaces") -> None:
        self.base = base
        self.repo = base / name
        self.scripts = self.repo / "scripts"
        self.state = base / "operator state"
        self.tools = base / "reviewed tools"
        self.bootstrap_json = base / "bootstrap.json"
        self.bootstrap_log = base / "bootstrap-log.json"
        self.operator_json = base / "operator.json"
        self.operator_log = base / "operator-log.txt"
        self.gh_log = base / "status-gh-log.jsonl"
        self.gh_helper = base / "fake-status-gh.py"
        self.python = self.tools / "reviewed python.cmd"
        self.gh = self.tools / "reviewed status gh.cmd"
        self.codex = self.tools / "codex.cmd"

    def create(
        self,
        *,
        git_repo: bool = True,
        origin: str = EXPECTED_ORIGIN,
        state_dir: bool = True,
    ) -> "LauncherHarness":
        self.scripts.mkdir(parents=True)
        self.state.mkdir(parents=True, exist_ok=state_dir)
        self.tools.mkdir(parents=True)
        shutil.copy2(LAUNCHER_SOURCE, self.scripts / LAUNCHER_SOURCE.name)
        write_fake_bootstrap(self.scripts / "bootstrap_course_environment.ps1")
        write_fake_operator(self.python)
        write_fake_gh(self.gh, self.gh_helper)
        self.codex.write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")
        self.write_bootstrap(
            ready_bootstrap_payload(
                python_path=self.python,
                gh_path=self.gh,
                codex_path=self.codex,
            )
        )
        if git_repo:
            init_git_repo(self.repo, origin)
            git(self.repo, "add", "scripts")
            git(self.repo, "commit", "-m", "test fixture")
        return self

    def write_bootstrap(self, payload: dict | str) -> None:
        text = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False)
        )
        self.bootstrap_json.write_text(text, encoding="utf-8")

    def env(self, **overrides: str | None) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "B3C_TEST_BOOTSTRAP_JSON": str(self.bootstrap_json),
                "B3C_TEST_BOOTSTRAP_LOG": str(self.bootstrap_log),
                "B3C_TEST_OPERATOR_JSON": str(self.operator_json),
                "B3C_TEST_OPERATOR_LOG": str(self.operator_log),
                "B3C_TEST_OPERATOR_EXIT": "0",
                "B3C_TEST_GH_LOG": str(self.gh_log),
                "B3C_TEST_GH_EXECUTABLE": str(self.gh),
                "B3C_TEST_GH_MODE": "success",
                "LOCALAPPDATA": str(self.base / "local app data"),
            }
        )
        for name, value in overrides.items():
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
        return env

    def run(
        self,
        *extra: str,
        env: dict[str, str] | None = None,
        state: Path | None = None,
        wall_timeout: float | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        raw_result = self.run_raw(
            *extra,
            env=env,
            state=state,
            wall_timeout=wall_timeout,
        )
        assert not raw_result.stdout.startswith(b"\xef\xbb\xbf")
        stdout = raw_result.stdout.decode("utf-8")
        stderr = raw_result.stderr.decode("utf-8")
        result = subprocess.CompletedProcess(
            args=raw_result.args,
            returncode=raw_result.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 1, (result.stdout, result.stderr)
        return result, json.loads(lines[0])

    def run_raw(
        self,
        *extra: str,
        env: dict[str, str] | None = None,
        state: Path | None = None,
        wall_timeout: float | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        selected_state = self.state if state is None else state
        return run_process_bytes(
            [
                powershell(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.scripts / LAUNCHER_SOURCE.name),
                "-StateDir",
                str(selected_state),
                *extra,
            ],
            cwd=self.repo,
            env=env or self.env(),
            timeout=wall_timeout,
        )


def read_gh_calls(harness: LauncherHarness) -> list[dict]:
    if not harness.gh_log.exists():
        return []
    return [
        json.loads(line)
        for line in harness.gh_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def status_payload(call: dict) -> dict:
    api_input = json.loads(call["request_body"])
    comment_body = api_input["body"].replace("\r\n", "\n")
    assert comment_body.startswith(
        "LAWBRIDGE-STATUS protocol=lawb.bridge_status.v1\n\n```json\n"
    )
    assert comment_body.endswith("\n```")
    return json.loads(comment_body.split("```json\n", 1)[1].rsplit("\n```", 1)[0])


@pytest.fixture
def harness(tmp_path: Path) -> LauncherHarness:
    return LauncherHarness(tmp_path).create()


def test_powershell_resolver_skips_safely_when_unavailable(monkeypatch):
    discoveries: list[str] = []

    def unavailable(name: str) -> None:
        discoveries.append(name)
        return None

    monkeypatch.setattr(shutil, "which", unavailable)

    with pytest.raises(pytest.skip.Exception, match="Windows PowerShell is required"):
        powershell()

    assert discoveries == ["powershell.exe", "powershell"]


def test_powershell_subprocess_invocations_are_mediated_by_resolver():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    process_call_names = {"run_process", "run_process_bytes", "subprocess.run"}
    process_calls: list[ast.Call] = []
    powershell_process_calls: list[ast.Call] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        ):
            call_name = f"{node.func.value.id}.{node.func.attr}"
        else:
            continue
        if call_name not in process_call_names or not node.args:
            continue

        process_calls.append(node)
        command = node.args[0]
        if not isinstance(command, (ast.List, ast.Tuple)) or not command.elts:
            continue
        executable = command.elts[0]
        assert not (
            isinstance(executable, ast.Constant)
            and isinstance(executable.value, str)
            and executable.value.lower() in {"powershell.exe", "powershell"}
        )
        arguments = {
            element.value
            for element in command.elts[1:]
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        if arguments.intersection({"-NoProfile", "-ExecutionPolicy"}):
            assert (
                isinstance(executable, ast.Call)
                and isinstance(executable.func, ast.Name)
                and executable.func.id == "powershell"
            )
            powershell_process_calls.append(node)
        elif (
            isinstance(executable, ast.Call)
            and isinstance(executable.func, ast.Name)
            and executable.func.id == "powershell"
        ):
            powershell_process_calls.append(node)

    assert 'shutil.which("powershell.exe") or shutil.which("powershell")' in source
    assert process_calls
    assert powershell_process_calls


def test_default_invocation_is_preflight_only_and_ready(harness: LauncherHarness):
    result, payload = harness.run()

    assert result.returncode == 0
    assert payload["protocol"] == "lawb.bridge_operator_b3c_launcher.v1"
    assert payload["result"] == "ready"
    assert payload["phase"] == "preflight"
    assert payload["launch_requested"] is False
    assert payload["operator_invoked"] is False
    assert payload["target_repo_root"] == str(harness.repo)
    assert payload["bootstrap_status"] == "READY"
    assert not harness.operator_log.exists()


def test_default_preflight_outputs_exactly_one_json_object(harness: LauncherHarness):
    result, payload = harness.run()

    assert len([line for line in result.stdout.splitlines() if line.strip()]) == 1
    assert payload["blocked_reasons"] == []
    assert result.stderr == ""


def test_bootstrap_blocked_fails_closed_without_operator(harness: LauncherHarness):
    payload = ready_bootstrap_payload(
        python_path=harness.python,
        gh_path=harness.gh,
        codex_path=harness.codex,
    )
    payload["overall_status"] = "BLOCKED"
    payload["blockers"] = ["fixture_blocker"]
    harness.write_bootstrap(payload)

    result, summary = harness.run("-StartForeground")

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert "bootstrap_not_ready" in summary["blocked_reasons"]
    assert "bootstrap_blockers_present" in summary["blocked_reasons"]
    assert summary["operator_invoked"] is False
    assert not harness.operator_log.exists()


@pytest.mark.parametrize(
    ("update", "expected_reason"),
    [
        ({"ready": False}, "reviewed_gh_not_ready_or_authenticated"),
        ({"authenticated": False}, "reviewed_gh_not_ready_or_authenticated"),
        ({"path": ""}, "reviewed_gh_not_ready_or_authenticated"),
    ],
)
def test_gh_not_ready_or_authenticated_fails_closed(
    harness: LauncherHarness, update: dict, expected_reason: str
):
    payload = ready_bootstrap_payload(
        python_path=harness.python,
        gh_path=harness.gh,
        codex_path=harness.codex,
    )
    payload["detected"]["gh"].update(update)
    harness.write_bootstrap(payload)

    result, summary = harness.run("-StartForeground")

    assert result.returncode == 2
    assert expected_reason in summary["blocked_reasons"]
    assert summary["operator_invoked"] is False


@pytest.mark.parametrize("field", ["ready", "command_usable"])
def test_codex_missing_unusable_or_mismatched_fails_closed(
    harness: LauncherHarness, field: str
):
    payload = ready_bootstrap_payload(
        python_path=harness.python,
        gh_path=harness.gh,
        codex_path=harness.codex,
    )
    payload["detected"]["codex"][field] = False
    harness.write_bootstrap(payload)

    result, summary = harness.run("-StartForeground")

    assert result.returncode == 2
    assert "reviewed_codex_not_ready" in summary["blocked_reasons"]
    assert summary["operator_invoked"] is False


def test_dirty_worktree_fails_closed(harness: LauncherHarness):
    (harness.repo / "dirty.txt").write_text("dirty", encoding="utf-8")

    result, payload = harness.run("-PublishStatus")
    remote = status_payload(read_gh_calls(harness)[0])

    assert result.returncode == 2
    assert "control_repository_worktree_dirty" in payload["blocked_reasons"]
    assert remote["repository"] == "HarryWhite-TW/local-ai-workbench"
    assert remote["branch"] == ""
    assert remote["head"] == ""


def test_staged_files_are_reported_separately(harness: LauncherHarness):
    (harness.repo / "staged.txt").write_text("staged", encoding="utf-8")
    git(harness.repo, "add", "staged.txt")

    result, payload = harness.run("-PublishStatus")
    remote = status_payload(read_gh_calls(harness)[0])

    assert result.returncode == 2
    assert "control_repository_worktree_dirty" in payload["blocked_reasons"]
    assert "control_repository_staged_changes_present" in payload["blocked_reasons"]
    assert remote["branch"] == ""
    assert remote["head"] == ""


def test_wrong_origin_fails_closed(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create(origin="https://github.com/example/wrong.git")

    result, payload = fixture.run("-PublishStatus")
    remote = status_payload(read_gh_calls(fixture)[0])

    assert result.returncode == 2
    assert "control_repository_origin_mismatch" in payload["blocked_reasons"]
    assert remote["repository"] == "HarryWhite-TW/local-ai-workbench"
    assert remote["branch"] == ""
    assert remote["head"] == ""


def test_non_git_root_fails_closed(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create(git_repo=False)

    result, payload = fixture.run()

    assert result.returncode == 2
    assert "control_repository_not_git_repository" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


def test_missing_state_directory_fails_closed_without_creating_it(harness: LauncherHarness):
    missing = harness.base / "missing state"

    result, payload = harness.run(state=missing)

    assert result.returncode == 2
    assert "state_directory_unavailable" in payload["blocked_reasons"]
    assert not missing.exists()


def test_active_lock_fails_closed_and_is_not_deleted(harness: LauncherHarness):
    lock = harness.state / "operator.lock"
    lock.write_text('{"protocol":"test"}', encoding="utf-8")

    result, payload = harness.run("-StartForeground")

    assert result.returncode == 2
    assert "operator_lock_present" in payload["blocked_reasons"]
    assert lock.exists()
    assert payload["operator_invoked"] is False


def test_complete_lifecycle_lock_and_in_flight_are_handed_to_foreground_only(
    harness: LauncherHarness,
):
    session = "a" * 32
    identity = {
        "platform": "windows",
        "pid": 4101,
        "start_token": "windows-filetime:41010000",
        "started_at_utc": "2026-08-05T03:59:00Z",
    }
    lock = {
        "protocol": "lawb.bridge_operator_b3_lock.v2",
        "schema_version": 2,
        "operator_session_id": session,
        "process_identity": identity,
        "created_at_utc": "2026-08-05T04:00:00Z",
        "repo": "HarryWhite-TW/local-ai-workbench",
        "inbox_issue": 147,
        "mode": "b3c-run-reviewbundle",
        "descendant_recovery_policy": "require_no_live_descendants",
    }
    in_flight = {
        "protocol": "lawb.bridge_operator_b3_in_flight.v1",
        "schema_version": 1,
        "request_id": "ov1-launcher-request",
        "target_repository": "HarryWhite-TW/local-ai-workbench",
        "target_issue": 151,
        "dispatch_request_id": "ov1-launcher-dispatch",
        "action": "maybe-status-check",
        "branch": "ov1-test",
        "expected_head": "1" * 40,
        "operator_session_id": session,
        "process_identity": identity,
        "prepared_at_utc": "2026-08-05T04:00:00Z",
        "updated_at_utc": "2026-08-05T04:00:00Z",
        "stage": "PREPARED",
        "dispatcher_invoked": False,
        "terminal_evidence": None,
    }
    (harness.state / "operator.lock").write_text(
        json.dumps(lock), encoding="utf-8"
    )
    (harness.state / "in_flight.json").write_text(
        json.dumps(in_flight), encoding="utf-8"
    )
    harness.operator_json.write_text(
        json.dumps({"result": "success"}), encoding="utf-8"
    )

    preflight_result, preflight = harness.run()
    foreground_result, foreground = harness.run("-StartForeground")

    assert preflight_result.returncode == 2
    assert "operator_lock_present" in preflight["blocked_reasons"]
    assert "unresolved_in_flight_present" in preflight["blocked_reasons"]
    assert preflight["operator_invoked"] is False
    assert foreground_result.returncode == 0
    assert foreground["operator_invoked"] is True
    assert (harness.state / "operator.lock").exists()
    assert (harness.state / "in_flight.json").exists()


@pytest.mark.parametrize(
    ("flag_name", "reason"),
    [("pause.flag", "pause_flag_present"), ("stop.flag", "stop_flag_present")],
)
def test_pause_and_stop_flags_are_surfaced_without_deletion(
    harness: LauncherHarness, flag_name: str, reason: str
):
    flag = harness.state / flag_name
    flag.write_text("", encoding="utf-8")

    result, payload = harness.run()

    assert result.returncode == 2
    assert reason in payload["blocked_reasons"]
    assert flag.exists()


def test_invalid_state_evidence_fails_closed_without_repair(harness: LauncherHarness):
    state_file = harness.state / "state.json"
    state_file.write_text("{invalid", encoding="utf-8")

    result, payload = harness.run()

    assert result.returncode == 2
    assert "state_evidence_invalid_or_unreadable" in payload["blocked_reasons"]
    assert state_file.read_text(encoding="utf-8") == "{invalid"


def test_paths_containing_spaces_work(harness: LauncherHarness):
    result, payload = harness.run()

    assert result.returncode == 0
    assert payload["repo_root"] == str(harness.repo)
    assert payload["state_dir"] == str(harness.state)
    assert payload["reviewed_python_path"] == str(harness.python)


def test_non_ascii_paths_work_directly(tmp_path: Path):
    fixture = LauncherHarness(tmp_path, name="控制 repo").create()
    fixture.state = tmp_path / "操作員 狀態"
    fixture.state.mkdir()

    result, payload = fixture.run()
    expected_head = git(fixture.repo, "rev-parse", "HEAD").stdout.strip()

    assert result.returncode == 0
    assert payload["result"] == "ready"
    assert payload["repo_root"] == str(fixture.repo)
    assert payload["state_dir"] == str(fixture.state)
    assert payload["branch"] == "master"
    assert payload["head"] == expected_head
    assert "\ufffd" not in result.stdout


def test_cp950_native_bootstrap_output_is_decoded_exactly(tmp_path: Path):
    fixture = LauncherHarness(tmp_path, name="控制 repo").create()
    cp950_python = fixture.tools / "控制 python.cmd"
    shutil.copy2(fixture.python, cp950_python)
    payload = ready_bootstrap_payload(
        python_path=cp950_python,
        gh_path=fixture.gh,
        codex_path=fixture.codex,
    )
    fixture.write_bootstrap(payload)

    result, summary = fixture.run(
        env=fixture.env(B3C_TEST_BOOTSTRAP_ENCODING="cp950")
    )

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert summary["reviewed_python_path"] == str(cp950_python)
    assert "\ufffd" not in result.stdout


def test_cp950_ambiguous_bytes_follow_explicit_cp950_policy(tmp_path: Path):
    result = run_decoder_probe(tmp_path, bytes.fromhex("CB B1"), "cp950")

    assert result == {
        "succeeded": True,
        "text": "丳",
        "encoding": "cp950",
        "error": "",
    }


def test_generic_decoder_fails_closed_for_cp950_utf8_ambiguity(tmp_path: Path):
    result = run_decoder_probe(tmp_path, bytes.fromhex("CB B1"), "auto")

    assert result["succeeded"] is False
    assert result["text"] == ""
    assert result["error"] == "native_output_encoding_ambiguous"


def test_generic_decoder_fails_closed_when_no_allowed_encoding_is_valid(
    tmp_path: Path,
):
    result = run_decoder_probe(tmp_path, bytes.fromhex("81"), "auto")

    assert result["succeeded"] is False
    assert result["text"] == ""
    assert result["error"] == "native_output_not_utf8_or_cp950"


def test_native_call_sites_declare_authoritative_encoding_policies():
    source = LAUNCHER_SOURCE.read_text(encoding="utf-8")

    assert source.count('-EncodingPolicy "utf-8"') >= 2
    assert source.count('-EncodingPolicy "cp950"') == 1


def test_invalid_cp950_bootstrap_bytes_fail_closed_precisely(
    harness: LauncherHarness,
):
    result, payload = harness.run(
        env=harness.env(B3C_TEST_BOOTSTRAP_ENCODING="invalid")
    )

    assert result.returncode == 2
    assert "bootstrap_output_undecodable" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


def test_non_ascii_protocol_is_one_bomless_utf8_json_object(tmp_path: Path):
    fixture = LauncherHarness(tmp_path, name="控制 repo").create()
    fixture.state = tmp_path / "操作員 狀態"
    fixture.state.mkdir()

    result = fixture.run_raw()
    text = result.stdout.decode("utf-8", errors="strict")
    lines = [line for line in text.splitlines() if line.strip()]
    payload = json.loads(lines[0])

    assert result.returncode == 0
    assert not result.stdout.startswith(b"\xef\xbb\xbf")
    assert len(lines) == 1
    assert payload["repo_root"] == str(fixture.repo)
    assert payload["state_dir"] == str(fixture.state)
    assert "\ufffd" not in text
    assert result.stderr == b""


def test_benign_native_stderr_with_exit_zero_and_valid_json_succeeds(
    harness: LauncherHarness,
):
    result, payload = harness.run(
        env=harness.env(B3C_TEST_BOOTSTRAP_STDERR="benign bootstrap warning")
    )

    assert result.returncode == 0
    assert payload["result"] == "ready"


def test_nonzero_native_bootstrap_exit_is_blocked(harness: LauncherHarness):
    result, payload = harness.run(env=harness.env(B3C_TEST_BOOTSTRAP_EXIT="7"))

    assert result.returncode == 2
    assert "bootstrap_process_failed" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


@pytest.mark.parametrize("bootstrap_text", ["", "{not-json"])
def test_invalid_or_missing_bootstrap_json_is_blocked(
    harness: LauncherHarness, bootstrap_text: str
):
    harness.write_bootstrap(bootstrap_text)

    result, payload = harness.run()

    assert result.returncode == 2
    assert payload["bootstrap_status"] == "INVALID_JSON"
    assert "bootstrap_json_invalid_or_missing" in payload["blocked_reasons"]


def test_bootstrap_is_invoked_audit_only(harness: LauncherHarness):
    result, _ = harness.run()
    logged = json.loads(harness.bootstrap_log.read_text(encoding="utf-8-sig"))

    assert result.returncode == 0
    assert logged == {
        "RepoRoot": str(harness.repo),
        "Json": True,
        "Apply": False,
        "PersistUserPath": False,
        "CompleteRecovery": False,
    }


def test_foreground_child_receives_process_local_path_and_pythonpath(
    harness: LauncherHarness,
):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")
    parent_path = os.environ["PATH"]

    result, payload = harness.run("-StartForeground")
    log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert str(harness.python.parent) in log
    assert str(harness.gh.parent) in log
    assert str(harness.codex.parent) in log
    assert str(harness.repo / "src") in log
    assert os.environ["PATH"] == parent_path
    assert payload["path_binding_scope"] == "process_only"
    assert payload["path_persisted"] is False


def test_foreground_fake_child_handles_inherited_path_with_parentheses(
    harness: LauncherHarness,
):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")
    inherited_segment = r"C:\Program Files (x86)\B3CTest"

    result, payload = harness.run(
        "-StartForeground",
        env=harness.env(PATH=os.environ["PATH"] + ";" + inherited_segment),
    )
    log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert "INVOCATION" in log
    path_line = next(line for line in log.splitlines() if line.startswith("PATH="))
    assert inherited_segment in path_line


def test_cmd_ampersand_argument_is_rejected_without_command_injection(
    tmp_path: Path,
):
    result, invoked_marker, injection_marker = run_cmd_argument_probe(
        tmp_path,
        'safe & type nul > "{INJECTION_MARKER}"',
    )

    assert result["contract_error"] == "native_cmd_argument_unsupported_metacharacter"
    assert result["invocation_error"] == ""
    assert result["process_started"] is False
    assert result["stdout"] == ""
    assert not invoked_marker.exists()
    assert not injection_marker.exists()


def test_cmd_percent_argument_is_rejected_without_environment_expansion(
    tmp_path: Path,
):
    result, invoked_marker, injection_marker = run_cmd_argument_probe(
        tmp_path,
        "%PATH%",
    )

    assert result["contract_error"] == "native_cmd_argument_unsupported_metacharacter"
    assert result["process_started"] is False
    assert result["stdout"] == ""
    assert not invoked_marker.exists()
    assert not injection_marker.exists()


@pytest.mark.parametrize("argument", ["left|right", "left<right", "left>right", "left^right"])
def test_other_cmd_metacharacters_fail_closed_before_process_start(
    tmp_path: Path,
    argument: str,
):
    result, invoked_marker, injection_marker = run_cmd_argument_probe(
        tmp_path,
        argument,
    )

    assert result["contract_error"] == "native_cmd_argument_unsupported_metacharacter"
    assert result["process_started"] is False
    assert not invoked_marker.exists()
    assert not injection_marker.exists()


@pytest.mark.parametrize(
    ("overrides", "expected_comment_id", "classification", "comment_id"),
    [
        (
            {
                "process_started": False,
                "invocation_error": "process did not start",
            },
            None,
            "failed",
            None,
        ),
        (
            {
                "contract_error": "native_cmd_argument_unsupported_metacharacter",
            },
            None,
            "failed",
            None,
        ),
        ({"exit_code": 7}, None, "uncertain", None),
        (
            {"exit_code": 9009, "invocation_error": "failure after process start"},
            None,
            "uncertain",
            None,
        ),
        ({"timed_out": True}, None, "uncertain", None),
        (
            {"cleanup_error": "native_process_tree_cleanup_unverified"},
            None,
            "uncertain",
            None,
        ),
        ({"stream_drain_timed_out": True}, None, "uncertain", None),
        (
            {"decode_error": "stdout:native_output_not_utf8"},
            None,
            "uncertain",
            None,
        ),
        ({"stdout": "{}"}, None, "uncertain", None),
        ({"stdout": '{"id":45123}'}, None, "success", 45123),
        ({"stdout": '{"id":45123}'}, 45123, "success", 45123),
        ({"stdout": '{"id":45124}'}, 45123, "uncertain", None),
    ],
)
def test_status_write_outcome_requires_verified_success_after_process_start(
    tmp_path: Path,
    overrides: dict,
    expected_comment_id: int | None,
    classification: str,
    comment_id: int | None,
):
    native_result = {
        "exit_code": 0,
        "stdout": '{"id":45123}',
        "decode_error": "",
        "contract_error": "",
        "invocation_error": "",
        "cleanup_error": "",
        "process_started": True,
        "timed_out": False,
        "process_tree_termination_attempted": False,
        "process_tree_termination_succeeded": False,
        "post_kill_wait_timed_out": False,
        "stream_drain_timed_out": False,
    }
    native_result.update(overrides)

    outcome = run_status_outcome_probe(
        tmp_path,
        native_result,
        expected_comment_id,
    )

    assert outcome == {
        "classification": classification,
        "comment_id": comment_id,
    }


REDACTION_CASES = [
    (
        "authorization_bearer",
        "Authorization: Bearer ghp_REDACTION_SENTINEL_12345678",
        "ghp_REDACTION_SENTINEL_12345678",
    ),
    (
        "json_token",
        '{"token":"github_pat_REDACTION_SENTINEL_12345678"}',
        "github_pat_REDACTION_SENTINEL_12345678",
    ),
    (
        "password",
        "password=REDACTION_SENTINEL_PASSWORD_12345678",
        "REDACTION_SENTINEL_PASSWORD_12345678",
    ),
    (
        "gho",
        "gho_REDACTION_SENTINEL_12345678",
        "gho_REDACTION_SENTINEL_12345678",
    ),
    (
        "ghs",
        "ghs_REDACTION_SENTINEL_12345678",
        "ghs_REDACTION_SENTINEL_12345678",
    ),
    (
        "ghu",
        "ghu_REDACTION_SENTINEL_12345678",
        "ghu_REDACTION_SENTINEL_12345678",
    ),
    (
        "ghr",
        "ghr_REDACTION_SENTINEL_12345678",
        "ghr_REDACTION_SENTINEL_12345678",
    ),
    (
        "openai",
        "sk-REDACTION_SENTINEL_12345678",
        "sk-REDACTION_SENTINEL_12345678",
    ),
    (
        "openai_project",
        "sk-proj-REDACTION_SENTINEL_12345678",
        "sk-proj-REDACTION_SENTINEL_12345678",
    ),
]


@pytest.mark.parametrize(
    ("case_name", "credential_text", "sentinel"),
    REDACTION_CASES,
    ids=[case[0] for case in REDACTION_CASES],
)
def test_safe_stderr_summary_redacts_credential_sentinels_before_truncation(
    tmp_path: Path,
    case_name: str,
    credential_text: str,
    sentinel: str,
):
    text = f"diagnostic before {credential_text} diagnostic after " + ("x" * 700)

    summary = run_stderr_summary_probe(tmp_path, text)

    assert case_name
    assert sentinel not in summary
    assert "diagnostic before" in summary
    assert "[REDACTED]" in summary
    assert summary.endswith("...[truncated]")


def test_final_launcher_json_stderr_summary_contains_no_credential_sentinel(
    harness: LauncherHarness,
):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")
    stderr_text = " ; ".join(case[1] for case in REDACTION_CASES)

    result, payload = harness.run(
        "-StartForeground",
        env=harness.env(B3C_TEST_OPERATOR_STDERR=stderr_text),
    )
    serialized = json.dumps(payload, ensure_ascii=False)

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert "[REDACTED]" in payload["operator_stderr_summary"]
    for _, _, sentinel in REDACTION_CASES:
        assert sentinel not in payload["operator_stderr_summary"]
        assert sentinel not in serialized


def test_explicit_foreground_uses_existing_b3_cli_and_mode(harness: LauncherHarness):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")

    result, payload = harness.run(
        "-StartForeground",
        "-MaxCycles",
        "3",
        "-PollIntervalSeconds",
        "1.5",
        "-TimeoutSeconds",
        "42",
    )
    log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 0
    assert payload["operator_invoked"] is True
    assert "-m local_runner_bridge.bridge_operator_b3_cli" in log
    assert "--mode b3c-run-reviewbundle" in log
    assert "--max-cycles 3" in log
    assert "--poll-interval-seconds 1.5" in log
    assert "--timeout-seconds 42" in log
    assert "--operator-session-id" in log
    assert payload["status_publication_run_id"] in log


def test_b3_cli_utf8_json_policy_preserves_ambiguous_unicode(
    harness: LauncherHarness,
):
    child = {"result": "success", "message": "丳"}
    harness.operator_json.write_text(
        json.dumps(child, ensure_ascii=False),
        encoding="utf-8",
    )

    result, payload = harness.run("-StartForeground")

    assert result.returncode == 0
    assert payload["operator_invoked"] is True
    assert payload["operator_summary"] == child


def test_argument_array_preserves_hag_target_path_with_spaces(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create()
    target = tmp_path / "HAG target with spaces"
    init_git_repo(target, HAG_ORIGIN)
    (target / "tracked.txt").write_text("tracked", encoding="utf-8")
    git(target, "add", "tracked.txt")
    git(target, "commit", "-m", "target fixture")
    fixture.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")

    result, payload = fixture.run(
        "-StartForeground",
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(target),
    )
    log = fixture.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 0
    assert payload["target_repo_root"] == str(target)
    assert f'--target-repo-root "{target}"' in log


def test_hag_preflight_requires_explicit_target_root(harness: LauncherHarness):
    result, payload = harness.run(
        "-PublishStatus",
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
    )
    remote = status_payload(read_gh_calls(harness)[0])

    assert result.returncode == 2
    assert "target_repo_root_required" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False
    assert remote["repository"] == "HarryWhite-TW/human-approval-automation-gateway"
    assert remote["branch"] == ""
    assert remote["head"] == ""


def test_hag_preflight_rejects_invalid_target_root_syntax(harness: LauncherHarness):
    result, payload = harness.run(
        "-PublishStatus",
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(harness.base / "invalid<root"),
    )
    remote = status_payload(read_gh_calls(harness)[0])

    assert result.returncode == 2
    assert "target_repo_root_invalid" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False
    assert remote["repository"] == "HarryWhite-TW/human-approval-automation-gateway"
    assert remote["branch"] == ""
    assert remote["head"] == ""


def test_hag_preflight_rejects_missing_target_repository(harness: LauncherHarness):
    missing = harness.base / "missing HAG repo"

    result, payload = harness.run(
        "-PublishStatus",
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(missing),
    )
    remote = status_payload(read_gh_calls(harness)[0])

    assert result.returncode == 2
    assert "target_repository_root_unavailable" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False
    assert not missing.exists()
    assert remote["repository"] == "HarryWhite-TW/human-approval-automation-gateway"
    assert remote["branch"] == ""
    assert remote["head"] == ""


def test_hag_preflight_rejects_wrong_origin(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create()
    target = tmp_path / "wrong origin HAG"
    init_git_repo(target, "https://github.com/example/wrong.git")
    (target / "tracked.txt").write_text("tracked", encoding="utf-8")
    git(target, "add", "tracked.txt")
    git(target, "commit", "-m", "target fixture")

    result, payload = fixture.run(
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(target),
    )

    assert result.returncode == 2
    assert "target_repository_origin_mismatch" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


def test_hag_preflight_rejects_dirty_repository(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create()
    target = tmp_path / "dirty HAG"
    init_git_repo(target, HAG_ORIGIN)
    (target / "tracked.txt").write_text("tracked", encoding="utf-8")
    git(target, "add", "tracked.txt")
    git(target, "commit", "-m", "target fixture")
    (target / "dirty.txt").write_text("dirty", encoding="utf-8")

    result, payload = fixture.run(
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(target),
    )

    assert result.returncode == 2
    assert "target_repository_worktree_dirty" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


def test_valid_hag_preflight_is_ready_without_operator_invocation(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create()
    target = tmp_path / "clean HAG"
    init_git_repo(target, HAG_ORIGIN)
    (target / "tracked.txt").write_text("tracked", encoding="utf-8")
    git(target, "add", "tracked.txt")
    git(target, "commit", "-m", "target fixture")

    result, payload = fixture.run(
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(target),
    )

    assert result.returncode == 0
    assert payload["result"] == "ready"
    assert payload["target_repo_root"] == str(target.resolve())
    assert payload["operator_invoked"] is False
    assert not fixture.operator_log.exists()


def test_fake_operator_success_is_retained_losslessly(harness: LauncherHarness):
    child = {
        "protocol": "lawb.bridge_operator_b3_dry_run_loop_summary.v1",
        "result": "success",
        "phase": "max_cycles_completed",
        "nested": {"request_id": "req-123", "values": [1, 2, 3]},
    }
    harness.operator_json.write_text(json.dumps(child), encoding="utf-8")

    result, payload = harness.run("-StartForeground")

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert payload["phase"] == "operator"
    assert payload["operator_exit_code"] == 0
    assert payload["operator_summary"] == child


def test_fake_operator_blocked_is_retained_without_retry(harness: LauncherHarness):
    child = {
        "protocol": "lawb.bridge_operator_b3_dry_run_loop_summary.v1",
        "result": "blocked",
        "blocked_reasons": ["operator_lock_exists"],
    }
    harness.operator_json.write_text(json.dumps(child), encoding="utf-8")
    result, payload = harness.run(
        "-StartForeground", env=harness.env(B3C_TEST_OPERATOR_EXIT="2")
    )
    log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 2
    assert payload["result"] == "blocked"
    assert payload["operator_summary"] == child
    assert "operator_reported_blocked" in payload["blocked_reasons"]
    assert "operator_process_failed" in payload["blocked_reasons"]
    assert log.count("INVOCATION") == 1


def test_operator_invalid_json_is_blocked(harness: LauncherHarness):
    harness.operator_json.write_text("not-json", encoding="utf-8")

    result, payload = harness.run("-StartForeground")

    assert result.returncode == 2
    assert "operator_json_invalid_or_missing" in payload["blocked_reasons"]


def test_operator_benign_stderr_exit_zero_remains_successful(harness: LauncherHarness):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")

    result, payload = harness.run(
        "-StartForeground",
        env=harness.env(B3C_TEST_OPERATOR_STDERR="benign child warning"),
    )

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert payload["operator_exit_code"] == 0
    assert payload["operator_summary"] == {"result": "success"}
    assert "operator_process_failed" not in payload["blocked_reasons"]
    assert "operator_json_invalid_or_missing" not in payload["blocked_reasons"]
    assert "benign child warning" in payload["operator_stderr_summary"]
    assert "PATH=" not in payload["operator_stderr_summary"]
    assert "B3C_TEST_" not in payload["operator_stderr_summary"]


def test_status_publication_is_not_requested_by_default(harness: LauncherHarness):
    result, payload = harness.run()

    assert result.returncode == 0
    assert read_gh_calls(harness) == []
    assert payload["status_publication_requested"] is False
    assert payload["status_publication_attempted"] is False
    assert payload["status_comment_create_attempted"] is False
    assert payload["status_comment_create_succeeded"] is False
    assert payload["status_comment_update_attempted"] is False
    assert payload["status_comment_update_succeeded"] is False
    assert payload["status_comment_id"] is None
    assert payload["status_publication_result"] == "not_requested"
    assert payload["status_publication_blocked_reason"] == ""
    assert len(payload["status_publication_run_id"]) == 32
    assert payload["github_write_performed_directly"] is False


def test_ready_preflight_publish_status_creates_one_fixed_comment(
    harness: LauncherHarness,
):
    control_branch = git(harness.repo, "branch", "--show-current").stdout.strip()
    control_head = git(harness.repo, "rev-parse", "HEAD").stdout.strip()
    result, payload = harness.run(
        "-PublishStatus",
        "-MaxCycles",
        "960",
        "-PollIntervalSeconds",
        "30",
        env=harness.env(
            GH_HOST="example.invalid",
            GH_REPO="attacker/redirected-repository",
        ),
    )
    calls = read_gh_calls(harness)
    remote = status_payload(calls[0])

    assert result.returncode == 0
    assert payload["result"] == "ready"
    assert len(calls) == 1
    assert calls[0]["executable_path"] == str(harness.gh)
    assert calls[0]["method"] == "POST"
    hostname_index = calls[0]["args"].index("--hostname")
    assert calls[0]["args"][hostname_index + 1] == "github.com"
    assert (
        calls[0]["endpoint"]
        == "repos/HarryWhite-TW/local-ai-workbench/issues/147/comments"
    )
    assert remote["protocol"] == "lawb.bridge_status.v1"
    assert remote["operator_session_id"] == remote["run_id"]
    assert remote["run_id"] == payload["status_publication_run_id"]
    started = datetime.strptime(
        remote["started_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    valid_until = datetime.strptime(
        remote["valid_until_utc"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    assert (valid_until - started).total_seconds() == 28800
    assert remote["configured_max_cycles"] == 960
    assert remote["configured_poll_interval_seconds"] == 30
    assert remote["configured_timeout_seconds"] == 600
    assert remote["stage"] == "preflight"
    assert remote["result"] == "ready"
    assert remote["repository"] == "HarryWhite-TW/local-ai-workbench"
    assert remote["branch"] == control_branch
    assert remote["head"] == control_head
    assert remote["next_action"] == "start_foreground"
    assert payload["status_comment_create_succeeded"] is True
    assert payload["status_comment_update_attempted"] is False
    assert payload["status_comment_id"] == 45123
    assert payload["status_publication_result"] == "created"
    assert payload["github_write_performed_directly"] is True


def test_foreground_publish_status_creates_then_updates_same_comment_once(
    harness: LauncherHarness,
):
    child = {
        "result": "success",
        "request_id": "status-request-001",
        "target_issue": 188,
        "dispatcher_invoked": True,
        "dispatcher_result_writeback_reached": True,
        "dispatcher_result_writeback_verified": True,
        "target_result_verified": True,
    }
    harness.operator_json.write_text(json.dumps(child), encoding="utf-8")

    result, payload = harness.run("-StartForeground", "-PublishStatus")
    calls = read_gh_calls(harness)
    create_payload = status_payload(calls[0])
    update_payload = status_payload(calls[1])
    operator_log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert [call["method"] for call in calls] == ["POST", "PATCH"]
    assert calls[0]["endpoint"].endswith("/issues/147/comments")
    assert (
        calls[1]["endpoint"]
        == "repos/HarryWhite-TW/local-ai-workbench/issues/comments/45123"
    )
    assert create_payload["result"] == "running"
    assert create_payload["operator_invoked"] is False
    assert create_payload["repository"] == update_payload["repository"]
    assert create_payload["branch"] == update_payload["branch"]
    assert create_payload["head"] == update_payload["head"]
    assert update_payload["stage"] == "final"
    assert update_payload["result"] == "completed"
    assert update_payload["operator_invoked"] is True
    assert update_payload["request_id"] == "status-request-001"
    assert update_payload["target_issue"] == 188
    assert update_payload["dispatcher_invoked"] is True
    assert operator_log.count("INVOCATION") == 1
    assert payload["status_comment_create_succeeded"] is True
    assert payload["status_comment_update_succeeded"] is True
    assert payload["status_publication_result"] == "updated"


@pytest.mark.parametrize(
    ("child", "expected_reasons"),
    [
        (
            {
                "result": "blocked",
                "blocked_reasons": ["target_issue_closed"],
            },
            [
                "operator_process_failed",
                "operator_reported_blocked",
                "target_issue_closed",
            ],
        ),
        (
            {
                "result": "blocked",
                "blocked_reasons": [
                    "operator_process_failed",
                    "target_issue_closed",
                    "target_issue_closed",
                ],
            },
            [
                "operator_process_failed",
                "operator_reported_blocked",
                "target_issue_closed",
            ],
        ),
        (
            {
                "result": "blocked",
                "blocked_reasons": ["token=OPERATOR_STATUS_SENTINEL_SECRET"],
            },
            [
                "operator_process_failed",
                "operator_reported_blocked",
                "unknown_blocked_reason",
            ],
        ),
        (
            {"result": "blocked"},
            ["operator_process_failed", "operator_reported_blocked"],
        ),
        (
            {"result": "blocked", "blocked_reasons": None},
            ["operator_process_failed", "operator_reported_blocked"],
        ),
        (
            {
                "result": "blocked",
                "blocked_reasons": "target_issue_closed",
            },
            [
                "operator_process_failed",
                "operator_reported_blocked",
                "unknown_blocked_reason",
            ],
        ),
        (
            {
                "result": "blocked",
                "blocked_reasons": [{"token": "OPERATOR_STATUS_SENTINEL_SECRET"}],
            },
            [
                "operator_process_failed",
                "operator_reported_blocked",
                "unknown_blocked_reason",
            ],
        ),
    ],
    ids=[
        "actionable-code",
        "deduplicated-wrapper-and-child",
        "unsafe-code-redacted",
        "missing",
        "null",
        "unexpected-scalar-type",
        "nested-object",
    ],
)
def test_foreground_blocked_status_safely_includes_operator_reason_codes(
    harness: LauncherHarness,
    child: dict,
    expected_reasons: list[str],
):
    harness.operator_json.write_text(json.dumps(child), encoding="utf-8")

    result, payload = harness.run(
        "-StartForeground",
        "-PublishStatus",
        env=harness.env(B3C_TEST_OPERATOR_EXIT="2"),
    )
    calls = read_gh_calls(harness)
    create_remote = status_payload(calls[0])
    update_remote = status_payload(calls[1])
    all_request_bodies = "\n".join(call["request_body"] for call in calls)
    operator_log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 2
    assert [call["method"] for call in calls] == ["POST", "PATCH"]
    assert create_remote["blocked_reasons"] == []
    assert update_remote["result"] == "blocked"
    assert update_remote["next_action"] == "review_blocked_reasons"
    assert update_remote["blocked_reasons"] == expected_reasons
    assert payload["operator_summary"] == child
    assert payload["operator_invoked"] is True
    assert operator_log.count("INVOCATION") == 1
    assert "operator_summary" not in all_request_bodies
    assert "OPERATOR_STATUS_SENTINEL_SECRET" not in all_request_bodies


def test_blocked_preflight_publishes_one_blocked_comment_without_operator(
    harness: LauncherHarness,
):
    control_branch = git(harness.repo, "branch", "--show-current").stdout.strip()
    control_head = git(harness.repo, "rev-parse", "HEAD").stdout.strip()
    (harness.state / "operator.lock").write_text("active", encoding="utf-8")

    result, payload = harness.run("-StartForeground", "-PublishStatus")
    calls = read_gh_calls(harness)
    remote = status_payload(calls[0])

    assert result.returncode == 2
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert remote["result"] == "blocked"
    assert remote["blocked_reasons"] == ["operator_lock_present"]
    assert remote["branch"] == control_branch
    assert remote["head"] == control_head
    assert remote["next_action"] == "review_blocked_reasons"
    assert payload["operator_invoked"] is False
    assert payload["status_comment_update_attempted"] is False
    assert not harness.operator_log.exists()


def test_unavailable_status_publication_blocks_without_write_or_operator(
    harness: LauncherHarness,
):
    bootstrap = ready_bootstrap_payload(
        python_path=harness.python,
        gh_path=harness.gh,
        codex_path=harness.codex,
    )
    bootstrap["detected"]["gh"]["authenticated"] = False
    harness.write_bootstrap(bootstrap)

    result, payload = harness.run("-StartForeground", "-PublishStatus")

    assert result.returncode == 2
    assert read_gh_calls(harness) == []
    assert payload["operator_invoked"] is False
    assert "status_publication_unavailable" in payload["blocked_reasons"]
    assert payload["status_publication_attempted"] is False
    assert payload["status_publication_result"] == "unavailable"
    assert (
        payload["status_publication_blocked_reason"]
        == "status_publication_unavailable"
    )
    assert payload["github_write_performed_directly"] is False


def test_create_process_started_nonzero_is_uncertain_without_retry_or_operator(
    harness: LauncherHarness,
):
    result, payload = harness.run(
        "-StartForeground",
        "-PublishStatus",
        env=harness.env(B3C_TEST_GH_MODE="create_failure"),
    )

    assert result.returncode == 2
    assert len(read_gh_calls(harness)) == 1
    assert payload["operator_invoked"] is False
    assert (
        "status_publication_create_outcome_uncertain"
        in payload["blocked_reasons"]
    )
    assert payload["status_comment_create_attempted"] is True
    assert payload["status_comment_create_succeeded"] is False
    assert payload["status_comment_update_attempted"] is False
    assert payload["status_comment_id"] is None
    assert payload["status_publication_result"] == "create_outcome_uncertain"
    assert payload["github_write_performed_directly"] is False
    assert not harness.operator_log.exists()


def test_create_prestart_contract_failure_is_explicit_and_blocks_operator(
    harness: LauncherHarness,
):
    unsafe_gh = harness.tools / "reviewed status gh%blocked.cmd"
    shutil.copy2(harness.gh, unsafe_gh)
    harness.write_bootstrap(
        ready_bootstrap_payload(
            python_path=harness.python,
            gh_path=unsafe_gh,
            codex_path=harness.codex,
        )
    )

    result, payload = harness.run("-StartForeground", "-PublishStatus")

    assert result.returncode == 2
    assert read_gh_calls(harness) == []
    assert payload["operator_invoked"] is False
    assert "status_publication_create_failed" in payload["blocked_reasons"]
    assert payload["status_comment_create_attempted"] is True
    assert payload["status_comment_create_succeeded"] is False
    assert payload["status_comment_update_attempted"] is False
    assert payload["status_publication_result"] == "create_failed"
    assert payload["github_write_performed_directly"] is False
    assert not harness.operator_log.exists()


@pytest.mark.parametrize(
    "mode",
    [
        "create_invalid_utf8",
        "create_malformed",
        "create_missing_id",
        "create_non_integer_id",
        "create_timeout",
    ],
)
def test_create_uncertain_outcome_fails_closed_without_retry_or_operator(
    harness: LauncherHarness,
    mode: str,
):
    args = ["-StartForeground", "-PublishStatus"]
    if mode == "create_timeout":
        args += ["-TimeoutSeconds", "1"]
    result, payload = harness.run(
        *args,
        env=harness.env(B3C_TEST_GH_MODE=mode),
    )

    assert result.returncode == 2
    assert len(read_gh_calls(harness)) == 1
    assert payload["operator_invoked"] is False
    assert (
        "status_publication_create_outcome_uncertain"
        in payload["blocked_reasons"]
    )
    assert payload["status_publication_result"] == "create_outcome_uncertain"
    assert payload["status_comment_id"] is None
    assert payload["status_comment_update_attempted"] is False
    assert not harness.operator_log.exists()


def test_create_timeout_terminates_process_tree_with_bounded_stream_drain(
    harness: LauncherHarness,
):
    child_pid_path = harness.base / "timed-out-gh-child.pid"
    path_hijack = harness.base / "path hijack"
    path_hijack.mkdir()
    taskkill_marker = harness.base / "path-taskkill-was-used.txt"
    (path_hijack / "taskkill.cmd").write_text(
        '@echo off\r\n'
        '>"%B3C_TEST_TASKKILL_MARKER%" echo PATH taskkill was used\r\n'
        "exit /b 0\r\n",
        encoding="ascii",
    )
    env = harness.env(
        B3C_TEST_GH_MODE="create_tree_timeout",
        B3C_TEST_GH_CHILD_PID=str(child_pid_path),
        B3C_TEST_TASKKILL_MARKER=str(taskkill_marker),
    )
    env["PATH"] = str(path_hijack) + os.pathsep + env["PATH"]

    child_pid: int | None = None
    started_at = time.monotonic()
    try:
        result, payload = harness.run(
            "-StartForeground",
            "-PublishStatus",
            "-TimeoutSeconds",
            "1",
            env=env,
            wall_timeout=12,
        )
        elapsed_seconds = time.monotonic() - started_at
        assert child_pid_path.is_file()
        child_pid = int(child_pid_path.read_text(encoding="ascii"))

        assert result.returncode == 2
        assert elapsed_seconds < 12
        assert len(read_gh_calls(harness)) == 1
        assert payload["operator_invoked"] is False
        assert payload["status_publication_result"] == "create_outcome_uncertain"
        assert payload["status_comment_update_attempted"] is False
        assert not harness.operator_log.exists()
        assert not windows_process_is_running(child_pid)
        assert not taskkill_marker.exists()
    finally:
        if child_pid is not None and windows_process_is_running(child_pid):
            terminate_windows_process_tree(child_pid)


def test_taskkill_exit_zero_still_verifies_and_terminates_descendants(tmp_path):
    result = run_taskkill_success_verification_probe(tmp_path)

    assert result["taskkill_marker_exists"] is True
    assert result["process_tree_termination_succeeded"] is True
    assert result["child_running_after_stop"] is False
    assert result["root_running_after_stop"] is False
    assert result["elapsed_milliseconds"] < 3000


def test_native_timeout_cleanup_uses_only_trusted_bounded_primitives():
    source = launcher_function_source(
        "Stop-NativeProcessTree",
        "Test-NativeCaptureDecoded",
    )

    assert (
        'Join-Path ([System.Environment]::SystemDirectory) "taskkill.exe"'
        in source
    )
    assert '"/PID " + [string]$TargetProcessId + " /T /F"' in source
    assert "$taskkill.WaitForExit($taskkillWaitMilliseconds)" in source
    assert "$taskkill.WaitForExit($cleanupCommandWaitMilliseconds)" in source
    assert "CreateToolhelp32Snapshot" in source
    assert "Process32FirstW" in source
    assert "Process32NextW" in source
    assert "ProcessTerminate | Synchronize" in source
    assert "right.Depth.CompareTo(left.Depth)" in source
    assert "TerminateProcess(" in source
    assert "WaitForSingleObject(" in source
    assert source.count("CaptureSnapshot()") >= 2
    assert "verificationSnapshot" in source
    assert "evidenceByProcess" in source
    assert "[B3CLauncherProcessTree]::Bind(" in source
    assert "[B3CLauncherProcessTree]::TryTerminate(" in source
    assert "[B3CLauncherProcessTree]::Release(" in source
    stop_source = launcher_function_source(
        "Stop-NativeProcessTree",
        "New-NativeProcessTreeEvidence",
    )
    assert stop_source.index("New-NativeProcessTreeEvidence") < (
        stop_source.index("$taskkill.Start()")
    )
    assert "if ($taskkillSucceeded)" not in stop_source
    assert (
        "$ProcessTreeTerminationTimeoutMilliseconds -\n"
        "            [int]$cleanupTimer.ElapsedMilliseconds"
        in source
    )
    assert "Get-CimInstance" not in source
    assert "Get-WmiObject" not in source
    assert "Stop-Process" not in source
    assert "Process.GetProcessById" not in source
    assert (
        "$process.WaitForExit(\n"
        "                    $PostTerminationWaitTimeoutMilliseconds\n"
        "                )"
        in source
    )
    assert (
        "[System.Threading.Tasks.Task]::WaitAll(\n"
        "                [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask),\n"
        "                $StreamDrainTimeoutMilliseconds\n"
        "            )"
        in source
    )


def test_update_process_started_nonzero_is_uncertain_without_operator_rerun(
    harness: LauncherHarness,
):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")

    result, payload = harness.run(
        "-StartForeground",
        "-PublishStatus",
        env=harness.env(B3C_TEST_GH_MODE="update_failure"),
    )
    calls = read_gh_calls(harness)
    operator_log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 2
    assert [call["method"] for call in calls] == ["POST", "PATCH"]
    assert operator_log.count("INVOCATION") == 1
    assert (
        "status_publication_update_outcome_uncertain"
        in payload["blocked_reasons"]
    )
    assert payload["operator_summary"] == {"result": "success"}
    assert payload["status_comment_create_succeeded"] is True
    assert payload["status_comment_update_succeeded"] is False
    assert payload["status_publication_result"] == "update_outcome_uncertain"
    assert payload["github_write_performed_directly"] is True


@pytest.mark.parametrize(
    "mode",
    [
        "update_invalid_utf8",
        "update_malformed",
        "update_id_mismatch",
        "update_timeout",
    ],
)
def test_update_uncertain_outcome_does_not_retry_or_replace_comment(
    harness: LauncherHarness,
    mode: str,
):
    harness.operator_json.write_text(json.dumps({"result": "success"}), encoding="utf-8")

    args = ["-StartForeground", "-PublishStatus"]
    if mode == "update_timeout":
        args += ["-TimeoutSeconds", "1"]
    result, payload = harness.run(
        *args,
        env=harness.env(B3C_TEST_GH_MODE=mode),
    )
    calls = read_gh_calls(harness)
    operator_log = harness.operator_log.read_text(encoding="utf-8", errors="replace")

    assert result.returncode == 2
    assert [call["method"] for call in calls] == ["POST", "PATCH"]
    assert len([call for call in calls if call["method"] == "POST"]) == 1
    assert len([call for call in calls if call["method"] == "PATCH"]) == 1
    assert operator_log.count("INVOCATION") == 1
    assert (
        "status_publication_update_outcome_uncertain"
        in payload["blocked_reasons"]
    )
    assert payload["status_publication_result"] == "update_outcome_uncertain"


def test_hag_target_keeps_status_destination_fixed_to_control_inbox(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create()
    target = tmp_path / "clean status HAG"
    init_git_repo(target, HAG_ORIGIN)
    (target / "tracked.txt").write_text("tracked", encoding="utf-8")
    git(target, "add", "tracked.txt")
    git(target, "commit", "-m", "target fixture")
    target_branch = git(target, "branch", "--show-current").stdout.strip()
    target_head = git(target, "rev-parse", "HEAD").stdout.strip()
    control_head = git(fixture.repo, "rev-parse", "HEAD").stdout.strip()
    fixture.operator_json.write_text(
        json.dumps({"result": "success"}),
        encoding="utf-8",
    )

    result, payload = fixture.run(
        "-StartForeground",
        "-PublishStatus",
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(target),
        env=fixture.env(
            GH_HOST="example.invalid",
            GH_REPO="attacker/redirected-repository",
        ),
    )
    calls = read_gh_calls(fixture)
    create_remote = status_payload(calls[0])
    update_remote = status_payload(calls[1])

    assert result.returncode == 0
    assert payload["result"] == "completed"
    assert len(calls) == 2
    assert (
        calls[0]["endpoint"]
        == "repos/HarryWhite-TW/local-ai-workbench/issues/147/comments"
    )
    assert (
        calls[1]["endpoint"]
        == "repos/HarryWhite-TW/local-ai-workbench/issues/comments/45123"
    )
    for call in calls:
        hostname_index = call["args"].index("--hostname")
        assert call["args"][hostname_index + 1] == "github.com"
    assert (
        create_remote["repository"]
        == "HarryWhite-TW/human-approval-automation-gateway"
    )
    assert create_remote["branch"] == target_branch
    assert create_remote["head"] == target_head
    assert create_remote["head"] != control_head
    assert update_remote["repository"] == create_remote["repository"]
    assert update_remote["branch"] == create_remote["branch"]
    assert update_remote["head"] == create_remote["head"]


STATUS_SENTINELS = (
    "ghp_STATUS_SENTINEL_12345678",
    "github_pat_STATUS_SENTINEL_12345678",
    "sk-STATUS_SENTINEL_12345678",
    "sk-proj-STATUS_SENTINEL_12345678",
    "Authorization: Bearer STATUS_SENTINEL_12345678",
    "password=STATUS_SENTINEL_PASSWORD_12345678",
)


def test_remote_payload_is_whitelisted_and_contains_no_local_or_credential_data(
    harness: LauncherHarness,
):
    secret_text = " ; ".join(STATUS_SENTINELS)
    child = {
        "result": "success",
        "request_id": "safe-request-001",
        "target_issue": 147,
        "dispatcher_invoked": True,
        "dispatcher_result_writeback_reached": True,
        "dispatcher_result_writeback_verified": False,
        "target_result_verified": False,
        "repo_root": str(harness.repo),
        "target_repo_root": str(harness.base / "target"),
        "state_dir": str(harness.state),
        "reviewed_python_path": str(harness.python),
        "reviewed_gh_path": str(harness.gh),
        "reviewed_codex_path": str(harness.codex),
        "dispatcher_stdout": secret_text,
        "dispatcher_stderr": secret_text,
        "arbitrary_environment": dict(os.environ),
    }
    harness.operator_json.write_text(
        json.dumps(child, ensure_ascii=False),
        encoding="utf-8",
    )

    result, payload = harness.run(
        "-StartForeground",
        "-PublishStatus",
        env=harness.env(B3C_TEST_OPERATOR_STDERR=secret_text),
    )
    calls = read_gh_calls(harness)
    remote = status_payload(calls[1])
    all_request_bodies = "\n".join(call["request_body"] for call in calls)
    allowed = [
        "protocol",
        "run_id",
        "operator_session_id",
        "started_at_utc",
        "valid_until_utc",
        "configured_max_cycles",
        "configured_poll_interval_seconds",
        "configured_timeout_seconds",
        "observed_at_utc",
        "stage",
        "result",
        "repository",
        "branch",
        "head",
        "launch_requested",
        "operator_invoked",
        "request_id",
        "target_issue",
        "dispatcher_invoked",
        "dispatcher_result_writeback_reached",
        "dispatcher_result_writeback_verified",
        "target_result_verified",
        "blocked_reasons",
        "next_action",
    ]

    assert result.returncode == 0
    assert list(remote) == allowed
    assert set(remote) <= set(allowed)
    assert remote["request_id"] == "safe-request-001"
    assert remote["target_issue"] == 147
    for forbidden in (
        str(harness.repo),
        str(harness.state),
        str(harness.python),
        str(harness.gh),
        str(harness.codex),
        "repo_root",
        "target_repo_root",
        "state_dir",
        "reviewed_python_path",
        "reviewed_gh_path",
        "reviewed_codex_path",
        "dispatcher_stdout",
        "dispatcher_stderr",
        "arbitrary_environment",
    ):
        assert forbidden not in all_request_bodies
    for sentinel in STATUS_SENTINELS:
        assert sentinel not in all_request_bodies
    assert payload["operator_summary"] == child


def _b1_request_marker() -> str:
    return (
        "BRIDGE-INBOX-REQUEST "
        "protocol=lawb.bridge_inbox_request.v1 "
        "request_id=status-isolation-001 "
        "repo=HarryWhite-TW/local-ai-workbench "
        "target_issue=137 "
        "target_dispatch_request_id=status-isolation-dispatch "
        "branch=feature/status-isolation "
        "head=4c46cb02738c55f06884eff989598182a6070a92 "
        "expires=20260730T010000Z "
        "action=run-reviewbundle "
        "requested_by=chatgpt"
    )


def _b1_dispatch_marker() -> str:
    return (
        "CHATGPT-DISPATCH "
        "protocol=lawb.dispatch.v1 "
        "action=run-reviewbundle "
        "issue=137 "
        "repo=HarryWhite-TW/local-ai-workbench "
        "branch=feature/status-isolation "
        "head=4c46cb02738c55f06884eff989598182a6070a92 "
        "expires=20260730T010000Z "
        "requested_by=chatgpt "
        "request_id=status-isolation-dispatch"
    )


class StatusIsolationGitHub:
    def __init__(self, inbox_comments: list[CommentRecord]) -> None:
        self.inbox_comments = inbox_comments

    def get_issue(self, issue_number: int) -> IssueRecord:
        return IssueRecord(number=issue_number, state="open", body="")

    def list_issue_comments(self, issue_number: int) -> list[CommentRecord]:
        if issue_number == 147:
            return self.inbox_comments
        return [
            CommentRecord(
                id=9002,
                body=_b1_dispatch_marker(),
                author="HarryWhite-TW",
            )
        ]


def _run_b1_status_isolation(comments: list[CommentRecord]) -> dict:
    return run_bridge_operator_b1_dry_run(
        inbox_issue=147,
        repo_root=REPO_ROOT,
        github_client=StatusIsolationGitHub(comments),
        local_checker=lambda root: LocalReadiness(
            repo_root=str(REPO_ROOT.resolve()),
            branch="feature/status-isolation",
            head="4c46cb02738c55f06884eff989598182a6070a92",
            clean=True,
            gh_available=True,
            gh_authenticated=True,
            gh_read_available=True,
        ),
        now_utc=datetime(2026, 7, 29, 1, 0, 0, tzinfo=timezone.utc),
    )


def test_b1_ignores_status_marker_without_expanding_request_authority():
    status_comment = CommentRecord(
        id=9000,
        body=(
            "LAWBRIDGE-STATUS protocol=lawb.bridge_status.v1\n\n"
            '```json\n{"repo":"HarryWhite-TW/local-ai-workbench",'
            '"action":"run-reviewbundle","branch":"feature/status-isolation",'
            '"head":"4c46cb02738c55f06884eff989598182a6070a92"}\n```'
        ),
        author="HarryWhite-TW",
    )
    request_comment = CommentRecord(
        id=9001,
        body=_b1_request_marker(),
        author="HarryWhite-TW",
    )

    mixed = _run_b1_status_isolation([status_comment, request_comment])
    status_only = _run_b1_status_isolation([status_comment])

    assert mixed["result"] == "success"
    assert mixed["request_id"] == "status-isolation-001"
    assert mixed["inbox_comment_id"] == 9001
    assert status_only["result"] == "blocked"
    assert status_only["blocked_reasons"] == ["missing_request"]
    assert status_only.get("request_id") is None
    assert status_only.get("target_issue") is None
    assert status_only.get("requested_action") is None
    assert status_only.get("expected_branch") is None
    assert status_only.get("expected_head") is None


def test_safety_flags_remain_false_and_no_direct_higher_authority(
    harness: LauncherHarness,
):
    result, payload = harness.run()

    assert result.returncode == 0
    for field in (
        "background_service_started",
        "dispatcher_invoked_directly",
        "runner_invoked_directly",
        "codex_invoked_directly",
        "github_write_performed_directly",
        "path_persisted",
        "authentication_repair_performed",
        "install_performed",
        "commit_performed",
        "push_performed",
        "pr_created",
        "merge_performed",
    ):
        assert payload[field] is False
    source = LAUNCHER_SOURCE.read_text(encoding="utf-8")
    assert "gh auth login" not in source
    assert '"-Apply"' not in source
    assert '"-PersistUserPath"' not in source
    assert '"-CompleteRecovery"' not in source
    assert "local_dispatcher_v1.ps1" not in source
    assert "local_runner_v1.ps1" not in source
