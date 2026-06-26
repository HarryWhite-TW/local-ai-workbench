import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.host_check as host_check

EXPECTED_REPO = "HarryWhite-TW/local-ai-workbench"
EXPECTED_BRANCH = "rv2-03-phase-a-host-hardening"
EXPECTED_HEAD = "fcfc7c462aff1cb8df06ec4742567523c72f6473"


def completed(command, returncode=0, stdout=""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


class FakeRunner:
    def __init__(
        self,
        *,
        repo=EXPECTED_REPO,
        branch=EXPECTED_BRANCH,
        head=EXPECTED_HEAD,
        upstream="origin/" + EXPECTED_BRANCH,
        upstream_head=EXPECTED_HEAD,
        dirty=False,
        changed_after=False,
        git_identity=True,
        python_version_rc=0,
        imports_ready=True,
        gh_auth_rc=0,
        gh_repo_rc=0,
        gh_repo=EXPECTED_REPO,
        codex_suffix=".cmd",
        codex_version="codex-cli 0.142.2",
        codex_rc=0,
        gh_version_rc=0,
        fail_commands=(),
        origin_url=None,
    ):
        self.repo = repo
        self.branch = branch
        self.head = head
        self.upstream = upstream
        self.upstream_head = upstream_head
        self.dirty = dirty
        self.changed_after = changed_after
        self.git_identity = git_identity
        self.python_version_rc = python_version_rc
        self.imports_ready = imports_ready
        self.gh_auth_rc = gh_auth_rc
        self.gh_repo_rc = gh_repo_rc
        self.gh_repo = gh_repo
        self.codex_suffix = codex_suffix
        self.codex_version = codex_version
        self.codex_rc = codex_rc
        self.gh_version_rc = gh_version_rc
        self.fail_commands = set(fail_commands)
        self.origin_url = origin_url
        self.calls = []
        self.status_calls = 0

    def __call__(self, command, cwd):
        self.calls.append(command)
        git_key = tuple(command)
        if git_key in self.fail_commands:
            return completed(command, returncode=1)
        if command[:2] == ["git", "status"]:
            self.status_calls += 1
            if ("git-status-after",) in self.fail_commands and self.status_calls > 1:
                return completed(command, returncode=1)
            if self.changed_after and self.status_calls > 1:
                return completed(command, stdout=" M later.txt\n")
            return completed(command, stdout=" M dirty.txt\n" if self.dirty else "")
        if command[:3] == ["git", "config", "--get"]:
            origin = self.origin_url or f"https://github.com/{self.repo}.git"
            return completed(command, stdout=f"{origin}\n")
        if command[:4] == ["git", "config", "--local", "--get"]:
            value = command[-1]
            if not self.git_identity:
                return completed(command, returncode=1)
            return completed(command, stdout=("User\n" if value == "user.name" else "user@example.com\n"))
        if command == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return completed(command, stdout=f"{self.branch}\n")
        if command[:4] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name"]:
            if self.upstream is None:
                return completed(command, returncode=1)
            return completed(command, stdout=f"{self.upstream}\n")
        if command[:3] == ["git", "rev-parse", "--verify"]:
            return completed(command, stdout=f"{self.upstream_head}\n")
        if command == ["git", "rev-parse", "HEAD"]:
            return completed(command, stdout=f"{self.head}\n")
        launcher = launcher_name(command)
        args = launcher_args(command)
        if args == ["--version"] and launcher.startswith("python"):
            return completed(command, returncode=self.python_version_rc, stdout="Python 3.14.3\n")
        if args == ["-m", "pytest", "--version"] and launcher.startswith("python"):
            return completed(command, stdout="pytest 8.3.3\n")
        if args == ["-m", "pip", "--version"] and launcher.startswith("python"):
            return completed(command, stdout="pip 25.1\n")
        if args == ["--version"] and launcher.startswith("gh"):
            return completed(command, returncode=self.gh_version_rc, stdout="gh version 2.95.0 (2026-06-17)\n")
        if args == ["--version"] and launcher.startswith("codex"):
            return completed(command, returncode=self.codex_rc, stdout=f"{self.codex_version}\n")
        if args == ["auth", "status"] and launcher.startswith("gh"):
            return completed(command, returncode=self.gh_auth_rc)
        if len(args) >= 5 and args[:2] == ["repo", "view"] and launcher.startswith("gh"):
            return completed(command, returncode=self.gh_repo_rc, stdout=json.dumps({"nameWithOwner": self.gh_repo}))
        if len(args) >= 2 and args[0] == "-c" and launcher.startswith("python"):
            failures = [] if self.imports_ready else ["pypdf"]
            return completed(command, returncode=0 if self.imports_ready else 1, stdout=json.dumps({"failures": failures}))
        return completed(command)


def launcher_name(command):
    if len(command) >= 6 and command[1:5] == ["/d", "/s", "/c", "call"]:
        return Path(command[5]).name.lower()
    return Path(command[0]).name.lower()


def launcher_args(command):
    if len(command) >= 6 and command[1:5] == ["/d", "/s", "/c", "call"]:
        return command[6:]
    return command[1:]


def make_paths(tmp_path, *, codex_name="codex.cmd"):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "bootstrap_manifest.json").write_text(
        json.dumps(
            {
                "protocol": "lawb.bootstrap_course_environment_manifest.v1",
                "paths": {"venv": ".venv-course"},
                "codex": {"version": "0.141.0"},
            }
        ),
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    py = tmp_path / "venv" / "Scripts" / "python.exe"
    gh = tmp_path / "tools" / "gh.exe"
    codex = tmp_path / "node" / codex_name
    for path in (py, gh, codex):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return repo, py, gh, codex


def run_check(tmp_path, runner=None, fresh=None, codex_name="codex.cmd", monkeypatch=None):
    repo, py, gh, codex = make_paths(tmp_path, codex_name=codex_name)
    if monkeypatch:
        monkeypatch.setattr(host_check.sys, "executable", str(py))
        monkeypatch.setattr(host_check.shutil, "which", lambda name, path=None: { "python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name))
    return host_check.run_host_check(
        repo_root=repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=runner or FakeRunner(),
        fresh_shell_runner=fresh or (lambda name, cwd: {"python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name)),
        environment={"PATH": "fixture"} if monkeypatch else {},
    )


def test_correct_repository_branch_head_upstream_and_clean_tree(monkeypatch, tmp_path):
    summary = run_check(tmp_path, monkeypatch=monkeypatch)

    assert summary["status"] == "ATTENTION"
    assert summary["operational_readiness"] is True
    assert summary["repository"]["repository_matches"] is True
    assert summary["repository"]["branch_matches"] is True
    assert summary["repository"]["head_matches"] is True
    assert summary["repository"]["upstream_matches_head"] is True
    assert summary["repository"]["working_tree_clean_before"] is True
    assert "operational_venv_differs_from_manifest" in summary["status_reasons"]


def test_wrong_repository_branch_head_missing_upstream_and_upstream_mismatch_block(monkeypatch, tmp_path):
    cases = [
        (FakeRunner(repo="Other/repo"), "repository_mismatch"),
        (FakeRunner(branch="other"), "branch_mismatch"),
        (FakeRunner(head="0" * 40), "head_mismatch"),
        (FakeRunner(upstream=None), "upstream_missing"),
        (FakeRunner(upstream_head="1" * 40), "upstream_head_mismatch"),
    ]
    for runner, reason in cases:
        summary = run_check(tmp_path / reason, runner=runner, monkeypatch=monkeypatch)
        assert summary["status"] == "BLOCKED"
        assert reason in summary["status_reasons"]


def test_origin_url_is_sanitized_without_changing_repository_identity(monkeypatch, tmp_path):
    cases = [
        (
            "https://github.com/HarryWhite-TW/local-ai-workbench.git",
            "https://github.com/HarryWhite-TW/local-ai-workbench.git",
        ),
        (
            "https://alice:ghp_SECRET_VALUE@github.com/HarryWhite-TW/local-ai-workbench.git",
            "https://github.com/HarryWhite-TW/local-ai-workbench.git",
        ),
        (
            "ssh://git:SECRET_VALUE@github.com/HarryWhite-TW/local-ai-workbench.git",
            "ssh://github.com/HarryWhite-TW/local-ai-workbench.git",
        ),
        (
            "https://github.com/HarryWhite-TW/local-ai-workbench.git?token=SECRET_VALUE#fragment",
            "https://github.com/HarryWhite-TW/local-ai-workbench.git",
        ),
        (
            "git@github.com:HarryWhite-TW/local-ai-workbench.git",
            "git@github.com:HarryWhite-TW/local-ai-workbench.git",
        ),
    ]
    for index, (origin_url, expected_safe) in enumerate(cases):
        summary = run_check(
            tmp_path / f"origin-safe-{index}",
            runner=FakeRunner(origin_url=origin_url),
            monkeypatch=monkeypatch,
        )
        serialized = json.dumps(summary)

        assert summary["repository"]["repository_matches"] is True
        assert summary["repository"]["origin_url"] == expected_safe
        assert "ghp_SECRET_VALUE" not in serialized
        assert "SECRET_VALUE" not in serialized
        assert "alice" not in serialized


def test_origin_url_sanitization_different_and_unusual_remotes(monkeypatch, tmp_path):
    different = run_check(
        tmp_path / "origin-different",
        runner=FakeRunner(origin_url="https://alice:ghp_SECRET_VALUE@github.com/Other/repo.git"),
        monkeypatch=monkeypatch,
    )
    different_serialized = json.dumps(different)

    assert different["repository"]["repository_matches"] is False
    assert "repository_mismatch" in different["status_reasons"]
    assert different["repository"]["origin_url"] == "https://github.com/Other/repo.git"
    assert "ghp_SECRET_VALUE" not in different_serialized
    assert "SECRET_VALUE" not in different_serialized
    assert "alice" not in different_serialized

    unusual = run_check(
        tmp_path / "origin-unusual",
        runner=FakeRunner(origin_url="alice:SECRET_VALUE@github.com:HarryWhite-TW/local-ai-workbench.git?token=ghp_SECRET_VALUE#fragment"),
        monkeypatch=monkeypatch,
    )
    unusual_serialized = json.dumps(unusual)

    assert unusual["repository"]["origin_url"] == "github.com:HarryWhite-TW/local-ai-workbench.git"
    assert "ghp_SECRET_VALUE" not in unusual_serialized
    assert "SECRET_VALUE" not in unusual_serialized
    assert "alice" not in unusual_serialized


def test_malformed_origin_url_sanitizer_removes_userinfo():
    cases = [
        (
            "https://alice:SECRET_VALUE@github.com:notaport/owner/repo.git",
            "https://github.com:notaport/owner/repo.git",
        ),
        (
            "ssh://git:SECRET_VALUE@github.com:bad/owner/repo.git",
            "ssh://github.com:bad/owner/repo.git",
        ),
        (
            "https://alice:SECRET_VALUE@[::1/owner/repo.git",
            "https://[::1/owner/repo.git",
        ),
        (
            "https://alice:SECRET_VALUE@proxy@github.com:notaport/owner/repo.git",
            "https://github.com:notaport/owner/repo.git",
        ),
        (
            "https://alice:SECRET_VALUE@github.com:notaport/owner/repo.git?token=ghp_SECRET_VALUE#fragment",
            "https://github.com:notaport/owner/repo.git",
        ),
    ]
    for raw, expected in cases:
        sanitized = host_check._sanitize_origin_url(raw)

        assert sanitized == expected
        assert "alice" not in sanitized
        assert "SECRET_VALUE" not in sanitized
        assert "ghp_SECRET_VALUE" not in sanitized


def test_malformed_origin_url_summary_never_exposes_userinfo(monkeypatch, tmp_path):
    origins = [
        "https://alice:SECRET_VALUE@github.com:notaport/owner/repo.git",
        "ssh://git:SECRET_VALUE@github.com:bad/owner/repo.git",
        "https://alice:SECRET_VALUE@[::1/owner/repo.git",
        "https://alice:SECRET_VALUE@proxy@github.com:notaport/owner/repo.git",
        "https://alice:SECRET_VALUE@github.com:notaport/owner/repo.git?token=ghp_SECRET_VALUE#fragment",
    ]
    for index, origin_url in enumerate(origins):
        summary = run_check(
            tmp_path / f"malformed-origin-{index}",
            runner=FakeRunner(origin_url=origin_url),
            monkeypatch=monkeypatch,
        )
        serialized = json.dumps(summary)

        assert "alice" not in serialized
        assert "SECRET_VALUE" not in serialized
        assert "ghp_SECRET_VALUE" not in serialized


def test_repository_read_command_failures_block(monkeypatch, tmp_path):
    cases = [
        (("git", "config", "--get", "remote.origin.url"), "origin_url_unavailable"),
        (("git", "rev-parse", "--abbrev-ref", "HEAD"), "branch_unavailable"),
        (("git", "rev-parse", "HEAD"), "head_unavailable"),
        (("git", "status", "--porcelain"), "working_tree_status_unavailable"),
        (("git-status-after",), "final_working_tree_status_unavailable"),
    ]
    for command, reason in cases:
        summary = run_check(
            tmp_path / reason,
            runner=FakeRunner(fail_commands={command}),
            monkeypatch=monkeypatch,
        )
        assert summary["status"] == "BLOCKED"
        assert summary["operational_readiness"] is False
        assert reason in summary["status_reasons"]


def test_dirty_tree_changed_tree_and_missing_git_identity_block(monkeypatch, tmp_path):
    cases = [
        (FakeRunner(dirty=True), "working_tree_dirty"),
        (FakeRunner(changed_after=True), "working_tree_changed_during_check"),
        (FakeRunner(git_identity=False), "git_identity_missing"),
    ]
    for runner, reason in cases:
        summary = run_check(tmp_path / reason, runner=runner, monkeypatch=monkeypatch)
        assert summary["status"] == "BLOCKED"
        assert reason in summary["status_reasons"]


def test_repository_integrity_semantics_are_conservative(monkeypatch, tmp_path):
    after_fails = run_check(
        tmp_path / "after-fails",
        runner=FakeRunner(fail_commands={("git-status-after",)}),
        monkeypatch=monkeypatch,
    )
    assert after_fails["repository"]["working_tree_clean_after"] is None
    assert after_fails["repository"]["working_tree_unchanged"] is False
    assert after_fails["repository"]["repository_integrity_verified"] is False
    assert after_fails["safety"]["repository_modified_by_check"] is True

    both_fail = run_check(
        tmp_path / "both-fail",
        runner=FakeRunner(fail_commands={("git", "status", "--porcelain"), ("git-status-after",)}),
        monkeypatch=monkeypatch,
    )
    assert both_fail["repository"]["working_tree_unchanged"] is False
    assert both_fail["repository"]["repository_integrity_verified"] is False
    assert both_fail["safety"]["repository_modified_by_check"] is True

    changed = run_check(tmp_path / "changed", runner=FakeRunner(changed_after=True), monkeypatch=monkeypatch)
    assert changed["repository"]["working_tree_unchanged"] is False
    assert changed["repository"]["repository_integrity_verified"] is False

    same_dirty = run_check(tmp_path / "same-dirty", runner=FakeRunner(dirty=True), monkeypatch=monkeypatch)
    assert same_dirty["repository"]["working_tree_clean_before"] is False
    assert same_dirty["repository"]["working_tree_clean_after"] is False
    assert same_dirty["repository"]["working_tree_unchanged"] is True
    assert same_dirty["repository"]["repository_integrity_verified"] is True


def test_python_selection_path_drift_missing_probe_failure_and_import_failure(monkeypatch, tmp_path):
    summary = run_check(tmp_path / "ok", monkeypatch=monkeypatch)
    assert summary["python"]["reviewed_python_exists"] is True
    assert summary["python"]["required_imports_ready"] is True

    monkeypatch.setattr(host_check.shutil, "which", lambda name, path=None: "C:/Other/python.exe" if name == "python.exe" else None)
    drift = run_check(tmp_path / "drift", monkeypatch=None)
    assert "path_python_differs_from_reviewed_python" in drift["status_reasons"]

    missing_repo, py, gh, codex = make_paths(tmp_path / "missing")
    py.unlink()
    missing = host_check.run_host_check(
        repo_root=missing_repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=FakeRunner(),
        fresh_shell_runner=lambda name, cwd: None,
        environment={},
    )
    assert "reviewed_python_missing" in missing["status_reasons"]

    probe = run_check(tmp_path / "probe", runner=FakeRunner(python_version_rc=1), monkeypatch=monkeypatch)
    assert "python_version_probe_failed" in probe["status_reasons"]

    imports = run_check(tmp_path / "imports", runner=FakeRunner(imports_ready=False), monkeypatch=monkeypatch)
    assert "required_imports_failed" in imports["status_reasons"]
    assert imports["python"]["required_import_failures"] == ["pypdf"]


def test_github_cli_checks_auth_repo_mismatch_and_safe_auth_output(monkeypatch, tmp_path):
    auth = run_check(tmp_path / "auth", runner=FakeRunner(gh_auth_rc=1), monkeypatch=monkeypatch)
    assert "gh_auth_failed" in auth["status_reasons"]
    assert "raw" not in auth["github_cli"]

    repo_fail = run_check(tmp_path / "repo-fail", runner=FakeRunner(gh_repo_rc=1), monkeypatch=monkeypatch)
    assert "gh_repository_read_failed" in repo_fail["status_reasons"]

    repo_mismatch = run_check(tmp_path / "repo-mismatch", runner=FakeRunner(gh_repo="Other/repo"), monkeypatch=monkeypatch)
    assert "gh_repository_mismatch" in repo_mismatch["status_reasons"]

    missing_repo, py, gh, codex = make_paths(tmp_path / "missing-gh")
    gh.unlink()
    missing = host_check.run_host_check(
        repo_root=missing_repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=FakeRunner(),
        fresh_shell_runner=lambda name, cwd: None,
        environment={},
    )
    assert "reviewed_gh_missing" in missing["status_reasons"]


def test_gh_version_probe_failure_and_case_insensitive_repo_match(monkeypatch, tmp_path):
    version = run_check(tmp_path / "gh-version", runner=FakeRunner(gh_version_rc=1), monkeypatch=monkeypatch)
    assert "gh_version_probe_failed" in version["status_reasons"]
    assert version["github_cli"]["probes"]["gh_version"]["stage"] == "gh_version"
    assert version["github_cli"]["probes"]["gh_version"]["ok"] is False

    case_match = run_check(
        tmp_path / "case-match",
        runner=FakeRunner(gh_repo="harrywhite-tw/local-ai-workbench"),
        monkeypatch=monkeypatch,
    )
    assert "gh_repository_mismatch" not in case_match["status_reasons"]
    assert case_match["github_cli"]["repository_read_matches"] is True


def test_path_and_fresh_shell_drift_are_attention(monkeypatch, tmp_path):
    monkeypatch.setattr(host_check.shutil, "which", lambda name, path=None: "C:/Other/tool.exe")
    summary = run_check(tmp_path, fresh=lambda name, cwd: "C:/Other/fresh.exe")

    assert summary["operational_readiness"] is True
    assert "path_gh_differs_from_reviewed_gh" in summary["status_reasons"]
    assert "fresh_shell_codex_differs_from_reviewed_codex" in summary["status_reasons"]
    assert "path_resolution_differs_from_reviewed_path" in summary["bootstrap_contract"]["contract_drift_reasons"]


def test_codex_suffixes_safe_cmd_uses_comspec_and_tasks_are_not_invoked(monkeypatch, tmp_path):
    for name in ("codex.exe", "codex.cmd", "codex.bat", "codex.com"):
        runner = FakeRunner()
        summary = run_check(tmp_path / name, runner=runner, codex_name=name, monkeypatch=monkeypatch)
        assert summary["codex_cli"]["safe_launcher"] is True
        assert all("exec" not in call and "review" not in call for cmd in runner.calls for call in cmd)

    cmd_runner = FakeRunner()
    run_check(tmp_path / "cmd-vector", runner=cmd_runner, codex_name="codex.cmd", monkeypatch=monkeypatch)
    cmd_calls = [call for call in cmd_runner.calls if "codex.cmd" in " ".join(call)]
    assert cmd_calls
    assert all(call[:5] == ["cmd.exe", "/d", "/s", "/c", "call"] for call in cmd_calls)
    assert all(call[-1] == "--version" for call in cmd_calls)


def test_windows_launcher_command_vectors_keep_launcher_path_separate(monkeypatch, tmp_path):
    env = {"COMSPEC": "C:/Windows/System32/cmd.exe"}
    exe = host_check._launcher_command("C:/Tools/Codex/codex.exe", ["--version"], env)
    com = host_check._launcher_command("C:/Tools/Codex/codex.com", ["--version"], env)
    cmd = host_check._launcher_command("C:/Tools With Spaces/codex.cmd", ["--version"], env)
    bat = host_check._launcher_command("C:/Tools With Spaces/codex.bat", ["--version"], env)

    assert exe == ["C:/Tools/Codex/codex.exe", "--version"]
    assert com == ["C:/Tools/Codex/codex.com", "--version"]
    assert cmd == [
        "C:/Windows/System32/cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
        "C:/Tools With Spaces/codex.cmd",
        "--version",
    ]
    assert bat == [
        "C:/Windows/System32/cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
        "C:/Tools With Spaces/codex.bat",
        "--version",
    ]
    assert "C:/Tools With Spaces/codex.cmd" in cmd
    assert "C:/Tools With Spaces/codex.bat" in bat


def test_codex_rejects_unsafe_launchers_without_execution(monkeypatch, tmp_path):
    for name in ("codex.ps1", "codex", "codex.sh", "codex.unknown"):
        runner = FakeRunner()
        summary = run_check(tmp_path / name, runner=runner, codex_name=name, monkeypatch=monkeypatch)
        assert "codex_unsafe_launcher" in summary["status_reasons"]
        assert "codex_version_probe_failed" not in summary["status_reasons"]
        assert summary["codex_cli"]["probes"]["codex_version"] == {
            "stage": "codex_version",
            "ok": False,
            "executed": False,
            "exit_code": None,
            "error_type": "NotExecuted",
            "safe_message": "unsafe_launcher",
        }
        assert all(str(summary["codex_cli"]["reviewed_path"]) not in " ".join(call) for call in runner.calls)


def test_codex_missing_reviewed_path_without_execution(monkeypatch, tmp_path):
    repo, py, gh, codex = make_paths(tmp_path / "missing-codex")
    codex.unlink()
    runner = FakeRunner()
    summary = host_check.run_host_check(
        repo_root=repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=runner,
        fresh_shell_runner=lambda name, cwd: {"python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name),
        environment={},
    )

    assert "reviewed_codex_missing" in summary["status_reasons"]
    assert "codex_version_probe_failed" not in summary["status_reasons"]
    assert summary["codex_cli"]["probes"]["codex_version"] == {
        "stage": "codex_version",
        "ok": False,
        "executed": False,
        "exit_code": None,
        "error_type": "NotExecuted",
        "safe_message": "missing_reviewed_path",
    }
    assert all(str(codex) not in " ".join(call) for call in runner.calls)


def test_codex_safe_launchers_execute_one_version_probe(monkeypatch, tmp_path):
    exe_runner = FakeRunner()
    exe_summary = run_check(tmp_path / "safe-exe", runner=exe_runner, codex_name="codex.exe", monkeypatch=monkeypatch)
    exe_calls = [call for call in exe_runner.calls if launcher_name(call).startswith("codex")]
    assert exe_summary["codex_cli"]["safe_launcher"] is True
    assert exe_calls == [[exe_summary["codex_cli"]["reviewed_path"], "--version"]]

    cmd_runner = FakeRunner()
    cmd_summary = run_check(tmp_path / "safe-cmd", runner=cmd_runner, codex_name="codex.cmd", monkeypatch=monkeypatch)
    cmd_calls = [call for call in cmd_runner.calls if launcher_name(call).startswith("codex")]
    assert cmd_summary["codex_cli"]["safe_launcher"] is True
    assert len(cmd_calls) == 1
    assert cmd_calls[0][:5] == ["cmd.exe", "/d", "/s", "/c", "call"]
    assert cmd_calls[0][5:] == [cmd_summary["codex_cli"]["reviewed_path"], "--version"]

    failed = run_check(tmp_path / "failed", runner=FakeRunner(codex_rc=1), monkeypatch=monkeypatch)
    assert "codex_version_probe_failed" in failed["status_reasons"]


def test_windows_path_normalization_is_case_slash_and_separator_tolerant():
    assert host_check._same_path(r"C:\Tools\gh.exe", r"c:\tools\GH.EXE") is True
    assert host_check._same_path(r"C:\Tools\gh.exe", "C:/Tools/gh.exe") is True
    assert host_check._same_path(r"C:\Tools\bin\\", r"C:\Tools\bin") is True
    assert host_check._same_path(r"C:\Tools\gh.exe", r"C:\Other\gh.exe") is False


def test_contract_drift_reasons_are_deterministic(monkeypatch, tmp_path):
    summary = run_check(tmp_path, monkeypatch=monkeypatch)

    assert summary["bootstrap_contract"]["contract_drift_reasons"] == [
        "operational_venv_differs_from_manifest",
        "manifest_venv_not_gitignored",
        "codex_version_differs_from_manifest",
    ]
    assert summary["status"] == "ATTENTION"
    assert summary["operational_readiness"] is True


def test_manifest_invalid_schema_blocks(monkeypatch, tmp_path):
    invalid_manifests = [
        None,
        "invalid_json",
        [],
        {},
        {"protocol": "x", "paths": [], "codex": {"version": "0.141.0"}},
        {"protocol": "x", "paths": {}, "codex": {"version": "0.141.0"}},
        {"protocol": "x", "paths": {"venv": ".venv-course"}, "codex": []},
        {"protocol": "x", "paths": {"venv": ".venv-course"}, "codex": {}},
    ]
    for index, manifest in enumerate(invalid_manifests):
        repo, py, gh, codex = make_paths(tmp_path / f"manifest-{index}")
        manifest_path = repo / "scripts" / "bootstrap_manifest.json"
        if manifest is None:
            manifest_path.unlink()
            expected = "manifest_unreadable"
        elif manifest == "invalid_json":
            manifest_path.write_text("{", encoding="utf-8")
            expected = "manifest_unreadable"
        else:
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            expected = "manifest_invalid"
        summary = host_check.run_host_check(
            repo_root=repo,
            expected_repository=EXPECTED_REPO,
            expected_branch=EXPECTED_BRANCH,
            expected_head=EXPECTED_HEAD,
            reviewed_python_path=py,
            reviewed_gh_path=gh,
            reviewed_codex_path=codex,
            command_runner=FakeRunner(),
            fresh_shell_runner=lambda name, cwd: {"python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name),
            environment={},
        )
        assert summary["status"] == "BLOCKED"
        assert summary["operational_readiness"] is False
        assert expected in summary["status_reasons"]


def test_environment_injected_path_and_comspec(tmp_path):
    root_name = "pytest-python-gh-codex-root"
    repo, py, gh, codex = make_paths(tmp_path / root_name)
    env = {
        "PATH": f"{py.parent};{gh.parent};{codex.parent}",
        "COMSPEC": "C:/Injected/cmd.exe",
    }
    runner = FakeRunner()
    summary = host_check.run_host_check(
        repo_root=repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=runner,
        fresh_shell_runner=lambda name, cwd: {"python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name),
        environment=env,
    )

    assert summary["fresh_shell"]["python"]["current_matches_reviewed"] is True
    assert summary["fresh_shell"]["gh"]["current_matches_reviewed"] is True
    assert summary["fresh_shell"]["codex"]["current_matches_reviewed"] is True
    codex_calls = [call for call in runner.calls if launcher_name(call).startswith("codex")]
    assert codex_calls
    assert all(call[0] == "C:/Injected/cmd.exe" for call in codex_calls)


def test_explicit_empty_environment_does_not_leak_global_path(monkeypatch, tmp_path):
    repo, py, gh, codex = make_paths(tmp_path / "empty-env")
    monkeypatch.setattr(
        host_check.shutil,
        "which",
        lambda name, path=None: "C:/Global/tool.exe" if path is None else None,
    )

    summary = host_check.run_host_check(
        repo_root=repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=FakeRunner(),
        fresh_shell_runner=lambda name, cwd: {"python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name),
        environment={},
    )

    assert summary["python"]["path_resolved_path"] is None
    assert summary["github_cli"]["path_resolved_path"] is None
    assert summary["codex_cli"]["path_resolved_path"] is None
    assert summary["fresh_shell"]["python"]["current_process_resolved_path"] is None
    assert summary["fresh_shell"]["gh"]["current_process_resolved_path"] is None
    assert summary["fresh_shell"]["codex"]["current_process_resolved_path"] is None


def test_default_fresh_shell_runner_receives_injected_environment(monkeypatch, tmp_path):
    repo, py, gh, codex = make_paths(tmp_path / "fresh-env")
    captured_envs = []

    def fake_run_command(command, cwd, env=None):
        captured_envs.append(dict(env or {}))
        name = command[-1].split()[1].strip('"')
        resolved = {"python.exe": str(py), "gh.exe": str(gh), "codex.cmd": str(codex)}.get(name, "")
        return completed(command, stdout=resolved)

    monkeypatch.setattr(host_check, "_run_command", fake_run_command)
    injected = {"PATH": "C:/Injected/Path", "COMSPEC": "C:/Injected/cmd.exe"}
    summary = host_check.run_host_check(
        repo_root=repo,
        expected_repository=EXPECTED_REPO,
        expected_branch=EXPECTED_BRANCH,
        expected_head=EXPECTED_HEAD,
        reviewed_python_path=py,
        reviewed_gh_path=gh,
        reviewed_codex_path=codex,
        command_runner=FakeRunner(),
        environment=injected,
    )

    assert summary["fresh_shell"]["python"]["fresh_shell_resolved_path"] == str(py)
    assert captured_envs
    assert all(env == injected for env in captured_envs)


def test_tool_failure_stage_metadata(monkeypatch, tmp_path):
    summary = run_check(
        tmp_path,
        runner=FakeRunner(python_version_rc=1, gh_version_rc=1, gh_auth_rc=1, gh_repo_rc=1, codex_rc=1),
        monkeypatch=monkeypatch,
    )

    assert summary["python"]["probes"]["python_version"]["stage"] == "python_version"
    assert summary["github_cli"]["probes"]["gh_version"]["stage"] == "gh_version"
    assert summary["github_cli"]["probes"]["gh_auth"]["stage"] == "gh_auth"
    assert summary["github_cli"]["probes"]["gh_repository_read"]["stage"] == "gh_repository_read"
    assert summary["codex_cli"]["probes"]["codex_version"]["stage"] == "codex_version"
    assert "stdout" not in summary["github_cli"]["probes"]["gh_auth"]


def test_ready_exit_attention_exit_blocked_exit_and_json_human(monkeypatch, capsys, tmp_path):
    repo, py, gh, codex = make_paths(tmp_path)
    (repo / ".gitignore").write_text(".venv-course\n", encoding="utf-8")
    manifest = json.loads((repo / "scripts" / "bootstrap_manifest.json").read_text())
    manifest["paths"]["venv"] = str(py.parents[1].relative_to(repo)) if py.parents[1].is_relative_to(repo) else ".venv-course"
    (repo / "scripts" / "bootstrap_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def fake_ready(**kwargs):
        return {
            "protocol": host_check.PROTOCOL,
            "status": "READY",
            "status_reasons": [],
            "operational_readiness": True,
            "repository": {"repository_matches": True, "current_branch": EXPECTED_BRANCH, "head": EXPECTED_HEAD},
            "python": {"reviewed_python_path": str(py), "python_version": "Python 3.14.3", "required_imports_ready": True},
            "github_cli": {"selected_path": str(gh), "version": "gh version 2.95.0", "authenticated": True, "repository_read_matches": True},
            "codex_cli": {"selected_path": str(codex), "version": "0.141.0", "safe_launcher": True},
            "fresh_shell": {
                "python": {"fresh_shell_resolved_path": str(py)},
                "gh": {"fresh_shell_resolved_path": str(gh)},
                "codex": {"fresh_shell_resolved_path": str(codex)},
            },
            "bootstrap_contract": {"contract_drift_detected": False, "contract_drift_reasons": []},
            "safety": {"read_only": True, "repository_modified_by_check": False},
        }

    monkeypatch.setattr(host_check, "run_host_check", fake_ready)
    assert host_check.main(["--repo-root", str(repo), "--expected-repository", EXPECTED_REPO, "--expected-branch", EXPECTED_BRANCH, "--expected-head", EXPECTED_HEAD, "--reviewed-python-path", str(py), "--reviewed-gh-path", str(gh), "--reviewed-codex-path", str(codex), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "READY"

    def fake_attention(**kwargs):
        payload = fake_ready(**kwargs)
        payload["status"] = "ATTENTION"
        payload["status_reasons"] = ["manifest_venv_not_gitignored"]
        payload["operational_readiness"] = True
        return payload

    monkeypatch.setattr(host_check, "run_host_check", fake_attention)
    assert host_check.main(["--repo-root", str(repo), "--expected-repository", EXPECTED_REPO, "--expected-branch", EXPECTED_BRANCH, "--expected-head", EXPECTED_HEAD, "--reviewed-python-path", str(py), "--reviewed-gh-path", str(gh), "--reviewed-codex-path", str(codex), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ATTENTION"

    def fake_blocked(**kwargs):
        payload = fake_ready(**kwargs)
        payload["status"] = "BLOCKED"
        payload["status_reasons"] = ["working_tree_dirty"]
        payload["operational_readiness"] = False
        return payload

    monkeypatch.setattr(host_check, "run_host_check", fake_blocked)
    assert host_check.main(["--repo-root", str(repo), "--expected-repository", EXPECTED_REPO, "--expected-branch", EXPECTED_BRANCH, "--expected-head", EXPECTED_HEAD, "--reviewed-python-path", str(py), "--reviewed-gh-path", str(gh), "--reviewed-codex-path", str(codex)]) == 2
    human = capsys.readouterr().out
    assert "protocol:" in human
    assert "token" not in human.lower()
    assert "oauth" not in human.lower()
    assert "credential" not in human.lower()

    def boom(**kwargs):
        raise RuntimeError("hidden")

    monkeypatch.setattr(host_check, "run_host_check", boom)
    assert host_check.main(["--repo-root", str(repo), "--expected-repository", EXPECTED_REPO, "--expected-branch", EXPECTED_BRANCH, "--expected-head", EXPECTED_HEAD, "--reviewed-python-path", str(py), "--reviewed-gh-path", str(gh), "--reviewed-codex-path", str(codex)]) == 3


def test_safety_assertions_and_no_repository_write(monkeypatch, tmp_path):
    summary = run_check(tmp_path, monkeypatch=monkeypatch)
    safety = summary["safety"]

    assert safety["read_only"] is True
    assert safety["packages_installed"] is False
    assert safety["venv_created"] is False
    assert safety["path_modified"] is False
    assert safety["github_write_performed"] is False
    assert safety["dispatcher_invoked"] is False
    assert safety["runner_invoked"] is False
    assert safety["pollonce_invoked"] is False
    assert safety["codex_task_executed"] is False
    assert safety["repository_modified_by_check"] is False
