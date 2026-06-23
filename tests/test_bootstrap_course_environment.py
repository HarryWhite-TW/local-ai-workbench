import json
import os
import shutil
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap_course_environment.ps1"


def powershell():
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("PowerShell is required for bootstrap tests")
    return found


def write_cmd(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="\r\n")
    return path


def command_log(tmp_path: Path) -> Path:
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")
    return log


def fake_git(bin_dir: Path) -> None:
    write_cmd(
        bin_dir / "git.cmd",
        """@echo off
echo git %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo git version 2.53.0.windows.1& exit /b 0
exit /b 0
""",
    )


def fake_python(
    bin_dir: Path,
    *,
    version="3.14.3",
    imports_ready=True,
    pip_ready=True,
    ensurepip_succeeds=True,
) -> None:
    import_exit = "0" if imports_ready else "1"
    pip_default_exit = "0" if pip_ready else "1"
    ensurepip_exit = "0" if ensurepip_succeeds else "1"
    write_cmd(
        bin_dir / "python.cmd",
        f"""@echo off
echo python %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo Python {version}& exit /b 0
if "%1"=="-m" if "%2"=="venv" mkdir "%~3\\Scripts" 2>nul & copy /Y "%~f0" "%~3\\Scripts\\python.cmd" >nul & exit /b 0
if "%1"=="-m" if "%2"=="pip" if "%3"=="--version" if exist "%~dp0pip-ready" echo pip 25.1& exit /b 0
if "%1"=="-m" if "%2"=="pip" if "%3"=="--version" exit /b {pip_default_exit}
if "%1"=="-m" if "%2"=="ensurepip" if {ensurepip_exit}==0 type nul > "%~dp0pip-ready"
if "%1"=="-m" if "%2"=="ensurepip" exit /b {ensurepip_exit}
if "%1"=="-m" if "%2"=="pip" exit /b 0
if "%1"=="-m" if "%2"=="local_runner_bridge.bridge_diagnostics" echo {{""status"":""READY"",""status_reasons"":[""ready""]}}& exit /b 0
if "%1"=="-c" exit /b {import_exit}
exit /b 0
""",
    )


def fake_node_npm(bin_dir: Path) -> None:
    write_cmd(
        bin_dir / "node.cmd",
        """@echo off
echo node %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo v18.20.8& exit /b 0
exit /b 0
""",
    )
    write_cmd(
        bin_dir / "npm.cmd",
        """@echo off
echo npm %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo 10.8.2& exit /b 0
if "%1"=="install" if "%2"=="--global" (
  mkdir "%~4" 2>nul
  > "%~4\\codex.cmd" echo @echo off
  >> "%~4\\codex.cmd" echo echo codex %%*^>^> "%%LAW_BOOTSTRAP_COMMAND_LOG%%"
  >> "%~4\\codex.cmd" echo if "%%1"=="--version" echo codex-cli 0.141.0^& exit /b 0
  exit /b 0
)
exit /b 0
""",
    )


def fake_gh(bin_dir: Path, *, authenticated=False) -> None:
    auth_exit = "0" if authenticated else "1"
    write_cmd(
        bin_dir / "gh.cmd",
        f"""@echo off
echo gh %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo gh version 2.95.0 (2026-06-17)& exit /b 0
if "%1"=="auth" if "%2"=="status" exit /b {auth_exit}
if "%1"=="auth" if "%2"=="login" exit /b 9
exit /b 0
""",
    )


def fake_codex(bin_dir: Path) -> None:
    write_cmd(
        bin_dir / "codex.cmd",
        """@echo off
echo codex %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo codex-cli 0.141.0& exit /b 0
exit /b 9
""",
    )


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "src").mkdir()
    (repo / "requirements-course.txt").write_text(
        (ROOT / "requirements-course.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return repo


def make_env(tmp_path: Path, bin_dir: Path, log: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env["LAW_BOOTSTRAP_COMMAND_LOG"] = str(log)
    env["LAWB_BOOTSTRAP_LOCALAPPDATA"] = str(tmp_path / "localappdata")
    env["LAWB_BOOTSTRAP_NODE_FALLBACK"] = str(tmp_path / "missing-node-fallback")
    env["COMSPEC"] = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    return env


def run_bootstrap(repo: Path, env: dict[str, str], *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    command = [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-RepoRoot",
        str(repo),
        "-Json",
        *args,
    ]
    result = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(result.stdout + result.stderr) from error
    return result, payload


def seed_working_venv(repo: Path, source_bin: Path) -> None:
    scripts = repo / ".venv-course" / "Scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(source_bin / "python.cmd", scripts / "python.cmd")


def seed_expected_codex(local_appdata: Path, *, name="codex.cmd") -> None:
    target = local_appdata / "LocalAIWorkbench" / "npm"
    target.mkdir(parents=True)
    write_cmd(
        target / name,
        """@echo off
echo codex %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo codex-cli 0.141.0& exit /b 0
exit /b 9
""",
    )


def seed_expected_codex_wrong_version(local_appdata: Path, *, version="0.140.0") -> None:
    target = local_appdata / "LocalAIWorkbench" / "npm"
    target.mkdir(parents=True)
    write_cmd(
        target / "codex.cmd",
        f"""@echo off
echo codex %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
if "%1"=="--version" echo codex-cli {version}& exit /b 0
exit /b 9
""",
    )


def seed_expected_codex_package(local_appdata: Path, version="0.141.0") -> None:
    package_dir = local_appdata / "LocalAIWorkbench" / "npm" / "node_modules" / "@openai" / "codex"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        json.dumps({"name": "@openai/codex", "version": version}),
        encoding="utf-8",
    )


def test_cmd_invocation_uses_comspec_argument_vector():
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'return & $cmd "/d" "/c" $CommandPath @Arguments 2>&1' in script
    assert '"/s"' not in script
    assert "ConvertTo-CmdArgument" not in script
    assert "$line =" not in script
    assert "$allArgs" not in script


def test_audit_mode_creates_or_modifies_nothing(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["mode"] == "AUDIT"
    assert not (repo / ".venv-course").exists()
    assert not (tmp_path / "localappdata").exists()
    assert payload["safety"]["credentials_written"] is False
    assert payload["safety"]["gh_login_invoked"] is False


def test_audit_reports_missing_venv_and_tools_without_installing(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert "venv_missing" in payload["attention"]
    assert "gh_missing_or_wrong_version" in payload["attention"]
    assert "codex_missing_or_wrong_version" in payload["attention"]
    assert "create_venv" not in payload["actions_planned"]
    assert "install_gh_2.95.0" not in payload["actions_planned"]


def test_apply_reuses_working_venv_gh_and_codex(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "reused_venv" in payload["actions_skipped_reused"]
    assert "reused_gh" in payload["actions_skipped_reused"]
    assert "reused_codex" in payload["actions_skipped_reused"]
    assert "python -m venv" not in commands
    assert "npm install" not in commands


def test_audit_reports_broken_venv_pip_without_repairing(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir, pip_ready=False)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert payload["venv"]["status"] == "pip_unusable"
    assert payload["venv"]["pip_ready"] is False
    assert "venv_pip_unusable" in payload["attention"]
    assert "reused_venv" not in payload["actions_skipped_reused"]
    assert "python -m pip --version" in commands
    assert "python -m ensurepip" not in commands


def test_apply_repairs_broken_venv_pip_and_continues(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir, pip_ready=False)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert payload["venv"]["status"] == "usable"
    assert payload["venv"]["pip_ready"] is True
    assert "repaired_venv_pip" in payload["actions_performed"]
    assert commands.count("python -m pip --version") == 2
    assert "python -m ensurepip --upgrade --default-pip" in commands
    assert "installed_requirements_course" in payload["actions_performed"]


def test_apply_reports_venv_pip_repair_failure(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir, pip_ready=False, ensurepip_succeeds=False)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 2
    assert payload["venv"]["status"] == "pip_repair_failed"
    assert payload["venv"]["pip_ready"] is False
    assert "venv_pip_repair_failed" in payload["blockers"]
    assert "python -m ensurepip --upgrade --default-pip" in commands
    assert "python -m pip install" not in commands


def test_missing_python_is_blocked_and_causes_no_partial_repair(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")

    assert result.returncode == 2
    assert "python_missing" in payload["blockers"]
    assert not (repo / ".venv-course").exists()
    assert not (tmp_path / "localappdata").exists()


def test_unsupported_python_version_is_blocked(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir, version="3.9.13")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")

    assert result.returncode == 2
    assert "python_unsupported" in payload["blockers"]


def test_missing_node_npm_prevents_codex_install_without_corrupting_other_tools(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "node_npm_required_for_codex" in payload["manual_actions_required"]
    assert "npm install" not in commands
    assert "reused_gh" in payload["actions_skipped_reused"]


def test_gh_zip_checksum_mismatch_aborts_before_activation(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    zip_path = cache / "gh_2.95.0_windows_amd64.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gh_2.95.0_windows_amd64/bin/gh.exe", "not executable")
    (cache / "gh_2.95.0_checksums.txt").write_text(
        "0" * 64 + "  gh_2.95.0_windows_amd64.zip\n",
        encoding="utf-8",
    )
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply", "-ArtifactCacheDir", str(cache))

    assert result.returncode == 2
    assert "gh_checksum_mismatch" in payload["blockers"]
    assert not (tmp_path / "localappdata" / "LocalAIWorkbench" / "gh" / "current" / "gh.exe").exists()


def test_local_artifact_cache_path_is_used_without_network_for_gh(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    with ZipFile(cache / "gh_2.95.0_windows_amd64.zip", "w", ZIP_DEFLATED) as archive:
        archive.writestr("gh.exe", "bad")
    (cache / "gh_2.95.0_checksums.txt").write_text("bad checksum\n", encoding="utf-8")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply", "-ArtifactCacheDir", str(cache))

    assert result.returncode == 2
    assert "gh_checksum_mismatch" in payload["blockers"]
    assert "Invoke-WebRequest" in SCRIPT.read_text(encoding="utf-8")


def test_gh_checksum_exact_match_passes_checksum_gate(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    zip_path = cache / "gh_2.95.0_windows_amd64.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("not-gh.txt", "checksum ok, archive content wrong")
    digest = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"(Get-FileHash -Algorithm SHA256 -LiteralPath '{zip_path}').Hash"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    (cache / "gh_2.95.0_checksums.txt").write_text(
        f"{digest}  gh_2.95.0_windows_amd64.zip\n",
        encoding="utf-8",
    )
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply", "-ArtifactCacheDir", str(cache))

    assert result.returncode == 2
    assert "gh_checksum_mismatch" not in payload["blockers"]
    assert "gh_archive_missing_exe" in payload["blockers"]


def test_gh_checksum_wrong_hash_for_exact_filename_fails(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    zip_path = cache / "gh_2.95.0_windows_amd64.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gh.exe", "bad")
    (cache / "gh_2.95.0_checksums.txt").write_text(
        f"{'1' * 64}  gh_2.95.0_windows_amd64.zip\n",
        encoding="utf-8",
    )
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply", "-ArtifactCacheDir", str(cache))

    assert result.returncode == 2
    assert "gh_checksum_mismatch" in payload["blockers"]


def test_gh_checksum_missing_filename_fails(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    zip_path = cache / "gh_2.95.0_windows_amd64.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gh.exe", "bad")
    digest = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"(Get-FileHash -Algorithm SHA256 -LiteralPath '{zip_path}').Hash"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    (cache / "gh_2.95.0_checksums.txt").write_text(
        f"{digest}  other.zip\n",
        encoding="utf-8",
    )
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply", "-ArtifactCacheDir", str(cache))

    assert result.returncode == 2
    assert "gh_checksum_mismatch" in payload["blockers"]


def test_gh_checksum_hash_elsewhere_does_not_pass_wrong_filename_line(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    zip_path = cache / "gh_2.95.0_windows_amd64.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gh.exe", "bad")
    digest = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"(Get-FileHash -Algorithm SHA256 -LiteralPath '{zip_path}').Hash"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    (cache / "gh_2.95.0_checksums.txt").write_text(
        f"{digest}  other.zip\n{'2' * 64}  gh_2.95.0_windows_amd64.zip\n",
        encoding="utf-8",
    )
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply", "-ArtifactCacheDir", str(cache))

    assert result.returncode == 2
    assert "gh_checksum_mismatch" in payload["blockers"]


def test_current_process_path_additions_are_deduplicated_and_user_path_unchanged(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "localappdata"
    seed_expected_codex(local_appdata)
    env = make_env(tmp_path, bin_dir, log)
    gh_dir = local_appdata / "LocalAIWorkbench" / "gh" / "current"
    codex_dir = local_appdata / "LocalAIWorkbench" / "npm"
    env["PATH"] = f"{gh_dir};{codex_dir};{bin_dir}"

    result, payload = run_bootstrap(repo, env, "-Apply")

    assert result.returncode == 0
    assert payload["path"]["current_process_added"] == []
    assert payload["path"]["persisted_user_added"] == []


def test_audit_detects_expected_codex_cmd_in_localappdata(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "localappdata"
    seed_expected_codex(local_appdata, name="codex.cmd")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert payload["detected"]["codex"]["ready"] is True
    assert payload["detected"]["codex"]["command_usable"] is True
    assert payload["detected"]["codex"]["command_version"] == "codex-cli 0.141.0"
    assert payload["detected"]["codex"]["installed_version_source"] == "command"
    assert "codex_missing_or_wrong_version" not in payload["attention"]
    assert "codex --version" in commands
    assert "codex login" not in commands


def test_audit_detects_expected_codex_cmd_in_path_with_spaces(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "Local App Data With Spaces"
    seed_expected_codex(local_appdata, name="codex.cmd")
    env = make_env(tmp_path, bin_dir, log)
    env["LAWB_BOOTSTRAP_LOCALAPPDATA"] = str(local_appdata)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["detected"]["codex"]["command_usable"] is True
    assert payload["detected"]["codex"]["command_version"] == "codex-cli 0.141.0"
    assert payload["detected"]["codex"]["ready"] is True
    assert "reused_codex" in payload["actions_skipped_reused"]


def test_audit_detects_expected_codex_cmd_case_variant(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "localappdata"
    seed_expected_codex(local_appdata, name="codex.CMD")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["detected"]["codex"]["ready"] is True
    assert payload["detected"]["codex"]["command_usable"] is True
    assert payload["detected"]["codex"]["path"].lower().endswith("codex.cmd")
    assert "codex_missing_or_wrong_version" not in payload["attention"]


def test_codex_command_failure_with_package_metadata_is_not_ready(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "localappdata"
    target = local_appdata / "LocalAIWorkbench" / "npm"
    target.mkdir(parents=True)
    write_cmd(
        target / "codex.cmd",
        """@echo off
echo codex %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
exit /b 1
""",
    )
    seed_expected_codex_package(local_appdata, "0.141.0")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["detected"]["codex"]["ready"] is False
    assert payload["detected"]["codex"]["command_usable"] is False
    assert payload["detected"]["codex"]["command_version"] is None
    assert payload["detected"]["codex"]["installed_version"] == "0.141.0"
    assert payload["detected"]["codex"]["installed_version_source"] == "package_json"
    assert "reused_codex" not in payload["actions_skipped_reused"]
    assert "codex_command_unusable" in payload["attention"]
    assert "codex_missing_or_wrong_version" not in payload["attention"]


def test_codex_install_uses_global_prefix_and_real_shim_layout(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")
    commands = log.read_text(encoding="utf-8")
    expected = tmp_path / "localappdata" / "LocalAIWorkbench" / "npm" / "codex.cmd"

    assert result.returncode == 0
    assert f"npm install --global --prefix {expected.parent} @openai/codex@0.141.0" in commands
    assert expected.is_file()
    assert payload["detected"]["codex"]["path"].lower() == str(expected).lower()
    assert payload["detected"]["codex"]["command_usable"] is True
    assert payload["detected"]["codex"]["ready"] is True


def test_codex_command_failure_in_path_with_spaces_is_not_ready(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "Local App Data With Spaces"
    target = local_appdata / "LocalAIWorkbench" / "npm"
    target.mkdir(parents=True)
    write_cmd(
        target / "codex.cmd",
        """@echo off
echo codex %*>> "%LAW_BOOTSTRAP_COMMAND_LOG%"
exit /b 1
""",
    )
    seed_expected_codex_package(local_appdata, "0.141.0")
    env = make_env(tmp_path, bin_dir, log)
    env["LAWB_BOOTSTRAP_LOCALAPPDATA"] = str(local_appdata)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["detected"]["codex"]["command_usable"] is False
    assert payload["detected"]["codex"]["installed_version"] == "0.141.0"
    assert payload["detected"]["codex"]["ready"] is False
    assert "reused_codex" not in payload["actions_skipped_reused"]
    assert "codex_command_unusable" in payload["attention"]


def test_codex_missing_command_with_package_metadata_is_not_ready(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "localappdata"
    seed_expected_codex_package(local_appdata, "0.141.0")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["detected"]["codex"]["ready"] is False
    assert payload["detected"]["codex"]["path"] is None
    assert payload["detected"]["codex"]["installed_version"] == "0.141.0"
    assert "reused_codex" not in payload["actions_skipped_reused"]
    assert "codex_missing_or_wrong_version" in payload["attention"]


def test_codex_wrong_command_version_with_correct_package_metadata_is_not_ready(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    seed_working_venv(repo, bin_dir)
    local_appdata = tmp_path / "localappdata"
    seed_expected_codex_wrong_version(local_appdata, version="0.140.0")
    seed_expected_codex_package(local_appdata, "0.141.0")
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.returncode == 0
    assert payload["detected"]["codex"]["ready"] is False
    assert payload["detected"]["codex"]["command_usable"] is True
    assert payload["detected"]["codex"]["command_version"] == "codex-cli 0.140.0"
    assert payload["detected"]["codex"]["installed_version"] == "0.141.0"
    assert "reused_codex" not in payload["actions_skipped_reused"]
    assert "codex_missing_or_wrong_version" in payload["attention"]


def test_repeated_apply_runs_are_idempotent(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    first = run_bootstrap(repo, env, "-Apply")[1]
    second = run_bootstrap(repo, env, "-Apply")[1]

    assert "reused_venv" in first["actions_skipped_reused"]
    assert "reused_venv" in second["actions_skipped_reused"]
    assert "created_venv" not in second["actions_performed"]


def test_gh_auth_missing_is_manual_action_and_login_is_not_invoked(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir, authenticated=False)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env, "-Apply")
    commands = log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "gh_auth_login_required" in payload["manual_actions_required"]
    assert "auth login" not in commands


def test_codex_validation_uses_version_only(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    run_bootstrap(repo, env, "-Apply")
    codex_lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("codex ")]

    assert codex_lines
    assert all(line == "codex --version" for line in codex_lines)


def test_no_bridge_operator_state_files_are_created_or_modified(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)
    state_dir = tmp_path / "localappdata" / "LocalAIWorkbench" / "BridgeOperator"

    run_bootstrap(repo, env)

    assert not state_dir.exists()


def test_json_output_is_valid(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    result, payload = run_bootstrap(repo, env)

    assert result.stdout.strip().startswith("{")
    assert payload["protocol"] == "lawb.bootstrap_course_environment.v1"


def test_b4b_diagnostics_invoked_only_when_venv_can_run_it(tmp_path):
    repo = make_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = command_log(tmp_path)
    fake_git(bin_dir)
    fake_python(bin_dir, imports_ready=False)
    fake_node_npm(bin_dir)
    fake_gh(bin_dir)
    fake_codex(bin_dir)
    seed_working_venv(repo, bin_dir)
    env = make_env(tmp_path, bin_dir, log)

    payload = run_bootstrap(repo, env)[1]
    commands = log.read_text(encoding="utf-8")

    assert payload["diagnostics"]["invoked"] is False
    assert "python -m local_runner_bridge.bridge_diagnostics" not in commands


def test_course_requirements_pin_python_314_compatible_pydantic():
    requirements = (ROOT / "requirements-course.txt").read_text(encoding="utf-8")

    assert "pydantic==2.13.4" in requirements.splitlines()
    assert "pydantic==2.9.2" not in requirements.splitlines()
