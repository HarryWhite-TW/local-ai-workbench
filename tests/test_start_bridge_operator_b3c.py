from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_SOURCE = REPO_ROOT / "scripts" / "start_bridge_operator_b3c.ps1"
EXPECTED_ORIGIN = "https://github.com/HarryWhite-TW/local-ai-workbench.git"
HAG_ORIGIN = "https://github.com/HarryWhite-TW/human-approval-automation-gateway.git"


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
    args: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=False,
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
        self.python = self.tools / "reviewed python.cmd"
        self.gh = self.tools / "gh.exe"
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
        self.gh.write_bytes(b"fake-gh")
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
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        raw_result = self.run_raw(*extra, env=env, state=state)
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
        )


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

    result, payload = harness.run()

    assert result.returncode == 2
    assert "control_repository_worktree_dirty" in payload["blocked_reasons"]


def test_staged_files_are_reported_separately(harness: LauncherHarness):
    (harness.repo / "staged.txt").write_text("staged", encoding="utf-8")
    git(harness.repo, "add", "staged.txt")

    result, payload = harness.run()

    assert result.returncode == 2
    assert "control_repository_worktree_dirty" in payload["blocked_reasons"]
    assert "control_repository_staged_changes_present" in payload["blocked_reasons"]


def test_wrong_origin_fails_closed(tmp_path: Path):
    fixture = LauncherHarness(tmp_path).create(origin="https://github.com/example/wrong.git")

    result, payload = fixture.run()

    assert result.returncode == 2
    assert "control_repository_origin_mismatch" in payload["blocked_reasons"]


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
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
    )

    assert result.returncode == 2
    assert "target_repo_root_required" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


def test_hag_preflight_rejects_invalid_target_root_syntax(harness: LauncherHarness):
    result, payload = harness.run(
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(harness.base / "invalid<root"),
    )

    assert result.returncode == 2
    assert "target_repo_root_invalid" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False


def test_hag_preflight_rejects_missing_target_repository(harness: LauncherHarness):
    missing = harness.base / "missing HAG repo"

    result, payload = harness.run(
        "-Repository",
        "HarryWhite-TW/human-approval-automation-gateway",
        "-TargetRepoRoot",
        str(missing),
    )

    assert result.returncode == 2
    assert "target_repository_root_unavailable" in payload["blocked_reasons"]
    assert payload["operator_invoked"] is False
    assert not missing.exists()


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
