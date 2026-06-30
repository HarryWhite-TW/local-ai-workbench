import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_check_v1.ps1"


def powershell():
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("PowerShell is required for wrapper tests")
    return found


def test_wrapper_uses_argument_vector_and_no_invoke_expression():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "$arguments = @(" in text
    assert '"-B",' in text
    assert "& $ReviewedPythonPath @arguments" in text
    assert "Invoke-Expression" not in text
    assert "Start-Process" not in text
    assert "gh auth login" not in text
    assert "$env:PATH =" not in text


@pytest.mark.parametrize("exit_code", [0, 2, 3])
def test_wrapper_sets_bytecode_env_restores_environment_and_preserves_exit_code(tmp_path, exit_code):
    fake_python = tmp_path / "python.cmd"
    pythonpath_log = tmp_path / "pythonpath.log"
    bytecode_log = tmp_path / "bytecode.log"
    args_log = tmp_path / "args.log"
    fake_python.write_text(
        f"""@echo off
> "{pythonpath_log}" echo %PYTHONPATH%
> "{bytecode_log}" echo %PYTHONDONTWRITEBYTECODE%
> "{args_log}" echo %*
exit /b {exit_code}
""",
        encoding="utf-8",
        newline="\r\n",
    )
    command = (
        "$env:PYTHONPATH = 'ORIGINAL_VALUE'; "
        "$env:PYTHONDONTWRITEBYTECODE = 'ORIGINAL_BYTECODE_VALUE'; "
        f"& '{SCRIPT}' "
        f"-RepoRoot '{tmp_path}' "
        "-ExpectedRepository 'HarryWhite-TW/local-ai-workbench' "
        "-ExpectedBranch 'rv2-03-phase-a-host-hardening' "
        "-ExpectedHead 'fcfc7c462aff1cb8df06ec4742567523c72f6473' "
        f"-ReviewedPythonPath '{fake_python}' "
        f"-ReviewedGhPath '{tmp_path / 'gh.exe'}' "
        f"-ReviewedCodexPath '{tmp_path / 'codex.cmd'}' "
        "-Pretty; "
        "$script:exitCode = $LASTEXITCODE; "
        "Write-Output ('AFTER_PYTHONPATH=' + $env:PYTHONPATH); "
        "Write-Output ('AFTER_BYTECODE=' + $env:PYTHONDONTWRITEBYTECODE); "
        "exit $script:exitCode"
    )
    result = subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == exit_code
    assert pythonpath_log.read_text(encoding="utf-8").startswith(str(tmp_path / "src"))
    assert bytecode_log.read_text(encoding="utf-8").strip() == "1"
    assert args_log.read_text(encoding="utf-8").split()[0] == "-B"
    assert "AFTER_PYTHONPATH=ORIGINAL_VALUE" in result.stdout
    assert "AFTER_BYTECODE=ORIGINAL_BYTECODE_VALUE" in result.stdout


def test_wrapper_reports_missing_python_path(tmp_path):
    result = subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(tmp_path),
            "-ExpectedRepository",
            "HarryWhite-TW/local-ai-workbench",
            "-ExpectedBranch",
            "rv2-03-phase-a-host-hardening",
            "-ExpectedHead",
            "fcfc7c462aff1cb8df06ec4742567523c72f6473",
            "-ReviewedPythonPath",
            str(tmp_path / "missing-python.exe"),
            "-ReviewedGhPath",
            str(tmp_path / "gh.exe"),
            "-ReviewedCodexPath",
            str(tmp_path / "codex.cmd"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Reviewed Python path does not exist" in result.stderr


def test_wrapper_preserves_child_unexpected_failure_exit_code(tmp_path):
    fake_python = tmp_path / "python.cmd"
    fake_python.write_text(
        """@echo off
exit /b 3
""",
        encoding="utf-8",
        newline="\r\n",
    )

    result = subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(tmp_path),
            "-ExpectedRepository",
            "HarryWhite-TW/local-ai-workbench",
            "-ExpectedBranch",
            "rv2-03-phase-a-host-hardening",
            "-ExpectedHead",
            "fcfc7c462aff1cb8df06ec4742567523c72f6473",
            "-ReviewedPythonPath",
            str(fake_python),
            "-ReviewedGhPath",
            str(tmp_path / "gh.exe"),
            "-ReviewedCodexPath",
            str(tmp_path / "codex.cmd"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3


def test_wrapper_has_bounded_catch_for_wrapper_failures():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "catch {" in text
    assert "Unexpected host_check_v1 wrapper failure" in text
    assert "exit 3" in text
