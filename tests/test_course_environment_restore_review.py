import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


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
    assert "if ($AuditPayload -and $AuditPayload.overall_status)" not in text
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


def _powershell() -> str:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    assert found
    return found


@pytest.fixture(scope="session")
def fake_rec02_tool(tmp_path_factory):
    root = tmp_path_factory.mktemp("rec02-tool")
    source_path = root / "tool.cs"
    exe_path = root / "tool.exe"
    source_path.write_text(
        r'''
using System;
using System.IO;
using System.Linq;
class Tool {
  static int EnvInt(string name, int fallback) {
    int value; return Int32.TryParse(Environment.GetEnvironmentVariable(name), out value) ? value : fallback;
  }
  static void Log(string[] args) {
    var path = Environment.GetEnvironmentVariable("REC02_COMMAND_LOG");
    if (!String.IsNullOrEmpty(path)) File.AppendAllText(path, Path.GetFileName(Environment.GetCommandLineArgs()[0]) + " " + String.Join(" ", args) + Environment.NewLine);
  }
  static int Main(string[] args) {
    Log(args);
    var name = Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]).ToLowerInvariant();
    if (name == "python") return EnvInt("REC02_PYTEST_EXIT", 0);
    if (name != "gh") return 0;
    var state = Environment.GetEnvironmentVariable("REC02_AUTH_STATE");
    bool authenticated = Environment.GetEnvironmentVariable("REC02_AUTH_VALID") != "0" || (!String.IsNullOrEmpty(state) && File.Exists(state));
    if (args.Length >= 2 && args[0] == "auth" && args[1] == "status") return authenticated ? 0 : 4;
    if (args.Length >= 2 && args[0] == "auth" && args[1] == "login") {
      int code = EnvInt("REC02_LOGIN_EXIT", 0);
      if (code == 0 && !String.IsNullOrEmpty(state)) File.WriteAllText(state, "ready");
      return code;
    }
    if (args.Length >= 2 && args[0] == "api" && args[1] == "user") {
      int code = EnvInt("REC02_IDENTITY_EXIT", 0);
      if (code == 0) Console.WriteLine(Environment.GetEnvironmentVariable("REC02_ACTOR") ?? "HarryWhite-TW");
      return code;
    }
    if (args.Length >= 2 && args[0] == "repo" && args[1] == "view") {
      int code = EnvInt("REC02_REPO_EXIT", 0);
      if (code == 0) Console.WriteLine("{\"nameWithOwner\":\"" + (Environment.GetEnvironmentVariable("REC02_REPO_NAME") ?? "HarryWhite-TW/local-ai-workbench") + "\"}");
      return code;
    }
    if (args.Length > 0 && args[0] == "--version") { Console.WriteLine("gh version 2.95.0"); return 0; }
    return 0;
  }
}
''',
        encoding="utf-8",
    )
    compile_script = root / "compile.ps1"
    compile_script.write_text(
        f"Add-Type -TypeDefinition (Get-Content -Raw -LiteralPath '{source_path}') -OutputAssembly '{exe_path}' -OutputType ConsoleApplication",
        encoding="utf-8",
    )
    result = subprocess.run([_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(compile_script)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return exe_path


def _write_ps(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _make_wrapper_host(tmp_path: Path, fake_rec02_tool: Path, *, identity_ready: bool = True):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    (scripts / "bootstrap_manifest.json").write_text(json.dumps({"paths": {"venv": ".venv-course"}}), encoding="utf-8")
    _write_ps(
        scripts / "bootstrap_course_environment.ps1",
        r'''
param([string]$RepoRoot,[switch]$Apply,[switch]$Json)
$countPath=$env:REC02_BOOTSTRAP_COUNT
$count=if(Test-Path $countPath){[int](Get-Content $countPath)}else{0}; $count++; Set-Content $countPath $count
Add-Content $env:REC02_COMMAND_LOG ("bootstrap " + $(if($Apply){"APPLY"}else{"AUDIT"}))
$mode=if($count -eq 1){$env:REC02_INITIAL_MODE}elseif($Apply){"READY"}else{$env:REC02_POST_MODE}
if(-not $mode){$mode="READY"}
if($mode -eq "FAIL"){Write-Output '{"overall_status":"READY"}'; exit 7}
if($mode -eq "INVALID"){Write-Output 'not-json'; exit 0}
$ready=($mode -eq "READY")
[ordered]@{overall_status=$(if($ready){"READY"}else{"BLOCKED"});blockers=$(if($ready){@()}else{@("fake_blocker")});venv=@{pip_ready=$ready};dependencies=@{ready=$ready};detected=@{gh=@{ready=$ready};codex=@{ready=$ready}}} | ConvertTo-Json -Depth 8
exit $(if($ready){0}else{2})
''',
    )
    _write_ps(
        scripts / "host_check_v1.ps1",
        r'''
param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Rest)
Add-Content $env:REC02_COMMAND_LOG "host-check"
$mode=$env:REC02_HOST_MODE; if(-not $mode){$mode="READY"}
if($mode -eq "FAIL"){Write-Output '{"status":"READY","operational_readiness":true}'; exit 8}
if($mode -eq "MISSING"){exit 0}
if($mode -eq "BLOCKED"){Write-Output '{"status":"BLOCKED","operational_readiness":false,"status_reasons":["fake"]}'; exit 0}
Write-Output '{"status":"READY","operational_readiness":true,"status_reasons":[]}'
''',
    )
    python = repo / ".venv-course" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    shutil.copy2(fake_rec02_tool, python)
    localappdata = tmp_path / "localappdata"
    gh = localappdata / "LocalAIWorkbench" / "gh" / "current" / "gh.exe"
    gh.parent.mkdir(parents=True)
    shutil.copy2(fake_rec02_tool, gh)
    codex = localappdata / "LocalAIWorkbench" / "npm" / "codex.cmd"
    codex.parent.mkdir(parents=True)
    codex.write_text("@echo off\r\necho codex-cli 0.141.0\r\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
    _git(repo, "init", "-b", "rec02-test")
    _git(repo, "remote", "add", "origin", "https://github.com/HarryWhite-TW/local-ai-workbench.git")
    _git(repo, "config", "user.name", "HarryWhite-TW")
    _git(repo, "config", "user.email", "harry061892@gmail.com")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    _git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
    if not identity_ready:
        _git(repo, "config", "--unset", "user.name")
        _git(repo, "config", "--unset", "user.email")
    return repo, localappdata


def _run_wrapper(tmp_path: Path, fake_rec02_tool: Path, *, complete: bool = True, identity_ready: bool = True, **settings):
    repo, localappdata = _make_wrapper_host(tmp_path, fake_rec02_tool, identity_ready=identity_ready)
    evidence = tmp_path / "evidence"
    log = tmp_path / "commands.log"
    env = os.environ.copy()
    env.update({
        "LAWB_BOOTSTRAP_LOCALAPPDATA": str(localappdata),
        "REC02_COMMAND_LOG": str(log),
        "REC02_BOOTSTRAP_COUNT": str(tmp_path / "bootstrap-count.txt"),
        "REC02_AUTH_STATE": str(tmp_path / "auth-state.txt"),
        "REC02_AUTH_VALID": "1",
        "REC02_ACTOR": "HarryWhite-TW",
        "REC02_REPO_NAME": "HarryWhite-TW/local-ai-workbench",
        "REC02_INITIAL_MODE": "READY",
        "REC02_POST_MODE": "READY",
        "REC02_HOST_MODE": "READY",
        "REC02_PYTEST_EXIT": "0",
    })
    env.update({key: str(value) for key, value in settings.items()})
    head = _git(repo, "rev-parse", "HEAD")
    command = [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(repo / "scripts" / SCRIPT.name), "-RepoRoot", str(repo), "-ExpectedBranch", "rec02-test", "-ExpectedHead", head, "-EvidenceRoot", str(evidence)]
    if complete:
        command.append("-CompleteRecovery")
    result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True, timeout=60)
    summary_path = evidence / "course_environment_restore_review_summary.json"
    assert summary_path.exists(), f"wrapper did not write summary\nstdout={result.stdout}\nstderr={result.stderr}"
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    return result, summary, log.read_text(encoding="utf-8") if log.exists() else "", repo, evidence


def test_behavior_audit_only_is_read_only(tmp_path, fake_rec02_tool):
    result, summary, log, repo, _ = _run_wrapper(tmp_path, fake_rec02_tool, complete=False)
    assert result.returncode == 0
    assert summary["verdict"] == "READY"
    assert "APPLY" not in log and "auth login" not in log
    assert summary["git_identity_action"] == "none"
    assert summary["safety"]["permanent_path_modified"] is False
    assert summary["safety"]["github_write_performed"] is False


def test_behavior_complete_healthy_is_idempotent_and_ready(tmp_path, fake_rec02_tool):
    result, summary, log, _, _ = _run_wrapper(tmp_path, fake_rec02_tool)
    assert result.returncode == 0 and summary["verdict"] == "READY"
    assert "APPLY" not in log and "auth login" not in log
    assert summary["git_identity_action"] == "none"
    assert summary["github_identity"]["login_matches"] is True
    assert summary["github_identity"]["repository_read_ready"] is True


@pytest.mark.parametrize("post_mode", ["FAIL", "INVALID"])
def test_behavior_post_audit_failure_blocks_old_ready(tmp_path, fake_rec02_tool, post_mode):
    result, summary, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_POST_MODE=post_mode)
    assert result.returncode == 2 and summary["verdict"] == "BLOCKED"
    assert any(item.startswith("post_audit_") for item in summary["current_blockers"])


def test_behavior_focused_pytest_failure_blocks(tmp_path, fake_rec02_tool):
    result, summary, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_PYTEST_EXIT=9)
    assert result.returncode == 2
    assert "focused_pytest_failed" in summary["current_blockers"]


@pytest.mark.parametrize("host_mode,reason", [("FAIL", "host_check_failed"), ("MISSING", "host_check_invalid"), ("BLOCKED", "host_check_blocked")])
def test_behavior_host_check_failure_blocks(tmp_path, fake_rec02_tool, host_mode, reason):
    result, summary, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_HOST_MODE=host_mode)
    assert result.returncode == 2 and reason in summary["current_blockers"]


def test_behavior_complete_sets_repo_local_identity_only(tmp_path, fake_rec02_tool):
    result, summary, _, repo, _ = _run_wrapper(tmp_path, fake_rec02_tool, identity_ready=False)
    assert result.returncode == 0
    assert summary["git_identity_action"] == "set_repo_local"
    assert _git(repo, "config", "--local", "user.name") == "HarryWhite-TW"
    assert summary["safety"]["global_git_identity_modified"] is False


def test_behavior_auth_missing_uses_browser_then_rechecks(tmp_path, fake_rec02_tool):
    result, summary, log, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_AUTH_VALID=0)
    assert result.returncode == 0 and "auth login --web" in log
    assert log.count("auth status") == 2
    assert summary["github_identity"]["auth_ready"] is True


def test_behavior_auth_failure_blocks(tmp_path, fake_rec02_tool):
    result, summary, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_AUTH_VALID=0, REC02_LOGIN_EXIT=7)
    assert result.returncode == 2 and "gh_auth_failed" in summary["current_blockers"]


def test_behavior_wrong_account_blocks_even_when_repo_readable(tmp_path, fake_rec02_tool):
    result, summary, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_ACTOR="AnotherUser")
    assert result.returncode == 2 and "gh_account_mismatch" in summary["current_blockers"]
    assert summary["github_identity"]["repository_read_ready"] is True


def test_behavior_repository_read_failure_is_blocked_not_not_checked(tmp_path, fake_rec02_tool):
    result, summary, *_ = _run_wrapper(tmp_path, fake_rec02_tool, REC02_REPO_EXIT=5)
    assert result.returncode == 2 and "gh_repository_read_failed" in summary["current_blockers"]
    assert summary["components"]["gh_repository_read"] == "BLOCKED"


def test_behavior_empty_evidence_artifacts_have_zero_bytes(tmp_path, fake_rec02_tool):
    _, _, _, _, evidence = _run_wrapper(tmp_path, fake_rec02_tool)
    assert (evidence / "gh_auth.stdout.txt").exists()
    assert (evidence / "gh_auth.stdout.txt").stat().st_size == 0
    assert (evidence / "gh_auth.stderr.txt").stat().st_size == 0
