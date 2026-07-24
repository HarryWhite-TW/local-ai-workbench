import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from local_runner_bridge import display_pilot_operator_cli as cli


REPO = Path(__file__).resolve().parents[2]


def _setup_argv(state, lawb, hgw, target):
    return [
        "setup",
        "--state-root",
        str(state),
        "--lawb-root",
        str(lawb),
        "--hgw-root",
        str(hgw),
        "--target-repo-root",
        str(target),
    ]


def test_setup_is_idempotent_and_creates_only_state_layout(tmp_path, capsys):
    state = tmp_path / "state"
    roots = [tmp_path / name for name in ("lawb", "hgw", "hag")]
    for root in roots:
        root.mkdir()
    for _ in range(2):
        assert cli.main(_setup_argv(state, *roots)) == 0
        assert json.loads(capsys.readouterr().out)["result"] == "success"
    assert sorted(path.name for path in state.iterdir()) == ["requests"]


def test_setup_rejects_state_inside_control_repository(capsys):
    state = REPO / "must-not-create-display-pilot-state"
    assert not state.exists()
    assert cli.main(
        _setup_argv(
            state,
            REPO,
            REPO.parent / "reviewed-hgw",
            REPO.parent / "reviewed-hag",
        )
    ) == 2
    assert json.loads(capsys.readouterr().out)["blocked_reasons"] == [
        "state_root_inside_git_worktree"
    ]
    assert not state.exists()


def test_setup_missing_required_protected_root_fails_closed(tmp_path, capsys):
    state = tmp_path / "state"

    assert cli.main(
        [
            "setup",
            "--state-root",
            str(state),
            "--lawb-root",
            str(tmp_path / "lawb"),
            "--hgw-root",
            str(tmp_path / "hgw"),
        ]
    ) == 2
    assert json.loads(capsys.readouterr().out)["blocked_reasons"] == [
        "required_setup_root_missing"
    ]
    assert not state.exists()


@pytest.mark.parametrize("root_name", ["lawb", "hgw", "hag"])
@pytest.mark.parametrize("location", ["equal", "child"])
def test_setup_rejects_each_protected_root_and_child(
    tmp_path,
    capsys,
    root_name,
    location,
):
    roots = {name: tmp_path / name for name in ("lawb", "hgw", "hag")}
    for root in roots.values():
        root.mkdir()
    state = roots[root_name]
    if location == "child":
        state = state / "state"

    assert cli.main(
        _setup_argv(state, roots["lawb"], roots["hgw"], roots["hag"])
    ) == 2
    assert json.loads(capsys.readouterr().out)["blocked_reasons"] == [
        "state_root_inside_git_worktree"
    ]
    assert not (state / "requests").exists()


def test_setup_normalizes_paths_before_containment_check(tmp_path, capsys):
    lawb = tmp_path / "lawb"
    hgw = tmp_path / "hgw"
    hag = tmp_path / "hag"
    for root in (lawb, hgw, hag):
        root.mkdir()
    state = lawb / "state"
    normalized_lawb = lawb / "unused" / ".."

    assert cli.main(_setup_argv(state, normalized_lawb, hgw, hag)) == 2
    assert json.loads(capsys.readouterr().out)["blocked_reasons"] == [
        "state_root_inside_git_worktree"
    ]
    assert not state.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path case semantics")
def test_setup_windows_containment_is_case_insensitive(tmp_path, capsys):
    lawb = tmp_path / "LawbRoot"
    hgw = tmp_path / "HgwRoot"
    hag = tmp_path / "HagRoot"
    for root in (lawb, hgw, hag):
        root.mkdir()
    state = Path(str(lawb).swapcase()) / "state"

    assert cli.main(_setup_argv(state, lawb, hgw, hag)) == 2
    assert json.loads(capsys.readouterr().out)["blocked_reasons"] == [
        "state_root_inside_git_worktree"
    ]
    assert not state.exists()


def test_setup_accepts_genuine_external_sibling(tmp_path, capsys):
    roots_parent = tmp_path / "worktrees"
    roots_parent.mkdir()
    roots = [roots_parent / name for name in ("lawb", "hgw", "hag")]
    for root in roots:
        root.mkdir()
    state = tmp_path / "operator-state"

    assert cli.main(_setup_argv(state, *roots)) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "success"
    assert (state / "requests").is_dir()


def test_verify_is_read_only_and_does_not_create_state(tmp_path, monkeypatch, capsys):
    state = tmp_path / "verify-must-not-exist"
    monkeypatch.setattr(
        cli,
        "verify_start_prerequisites",
        lambda arguments: cli._summary("success"),
    )

    assert cli.main(["verify", "--state-root", str(state)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["result"] == "success"
    assert output["github_write_performed"] is False
    assert output["runner_invoked"] is False
    assert not state.exists()


def test_start_routes_to_real_foreground_boundary_with_injected_fake(tmp_path, monkeypatch, capsys):
    observed = {}
    config = {
        name: str((tmp_path / name).resolve())
        for name in cli._VERIFIED_RUNTIME_PATH_FIELDS
    }
    monkeypatch.setattr(
        cli,
        "verify_start_prerequisites",
        lambda arguments: {
            **cli._summary("success"),
            "verified_runtime_config": config,
        },
    )

    def fake_start(runtime_config, *, max_cycles, poll_interval_seconds):
        observed["runtime_config"] = runtime_config
        observed["max_cycles"] = max_cycles
        observed["interval"] = poll_interval_seconds
        return {
            **cli._summary("success"),
            "cycles": 2,
            "polling_outcome": "no_eligible_request",
        }

    monkeypatch.setattr(cli, "_start", fake_start)
    code = cli.main(
        [
            "start",
            "--state-root",
            str(tmp_path),
            "--max-cycles",
            "2",
            "--poll-interval-seconds",
            "0",
        ]
    )
    assert code == 0
    assert observed == {
        "runtime_config": config,
        "max_cycles": 2,
        "interval": 0.0,
    }
    assert json.loads(capsys.readouterr().out)["cycles"] == 2


def test_start_failure_exit_is_propagated(tmp_path, monkeypatch, capsys):
    config = {
        name: str((tmp_path / name).resolve())
        for name in cli._VERIFIED_RUNTIME_PATH_FIELDS
    }
    monkeypatch.setattr(
        cli,
        "verify_start_prerequisites",
        lambda arguments: {
            **cli._summary("success"),
            "verified_runtime_config": config,
        },
    )
    monkeypatch.setattr(
        cli,
        "_start",
        lambda runtime_config, **kwargs: cli._summary(
            "blocked",
            ["simulated_failure"],
        ),
    )
    assert cli.main(["start", "--state-root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["blocked_reasons"] == [
        "simulated_failure"
    ]


def test_invalid_arguments_and_sensitive_paths_are_not_dumped(tmp_path, monkeypatch, capsys):
    assert cli.main([]) == 2
    assert json.loads(capsys.readouterr().out)["result"] == "blocked"

    secret_path = tmp_path / "secret-value"
    monkeypatch.setattr(
        cli,
        "verify_start_prerequisites",
        lambda arguments: cli._summary("blocked", ["reviewed_executable_missing"]),
    )
    cli.main(
        [
            "verify",
            "--state-root",
            str(tmp_path / "state"),
            "--codex-path",
            str(secret_path),
        ]
    )
    assert "secret-value" not in capsys.readouterr().out


def test_powershell_wrapper_propagates_cli_exit_code(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required")
    completed = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO / "scripts" / "display_pilot.ps1"),
            "-Action",
            "verify",
            "-StateRoot",
            str(tmp_path / "state"),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["result"] == "blocked"


def test_powershell_wrapper_resolves_src_layout_for_successful_setup(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required")
    state = tmp_path / "state"
    lawb = tmp_path / "lawb"
    hgw = tmp_path / "hgw"
    hag = tmp_path / "hag"
    for root in (lawb, hgw, hag):
        root.mkdir()
    completed = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO / "scripts" / "display_pilot.ps1"),
            "-Action",
            "setup",
            "-StateRoot",
            str(state),
            "-LawbRoot",
            str(lawb),
            "-HgwRoot",
            str(hgw),
            "-TargetRepoRoot",
            str(hag),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["result"] == "success"
    assert (state / "requests").is_dir()


def _start_arguments(tmp_path):
    roots = {
        "lawb": tmp_path / "lawb",
        "hgw": tmp_path / "hgw",
        "target": tmp_path / "target",
    }
    for root in roots.values():
        root.mkdir()
    executables = {}
    for name in ("python", "powershell", "gh", "codex"):
        path = tmp_path / f"{name}.exe"
        path.write_text("", encoding="utf-8")
        executables[name] = path
    runner = roots["lawb"] / "scripts" / "local_runner_v1.ps1"
    runner.parent.mkdir()
    runner.write_text("", encoding="utf-8")
    arguments = cli._parser().parse_args(
        [
            "verify",
            "--state-root",
            str(tmp_path / "state"),
            "--lawb-root",
            str(roots["lawb"]),
            "--lawb-branch",
            "candidate",
            "--lawb-head",
            "a" * 40,
            "--hgw-root",
            str(roots["hgw"]),
            "--target-repo-root",
            str(roots["target"]),
            "--python-path",
            str(executables["python"]),
            "--powershell-path",
            str(executables["powershell"]),
            "--gh-path",
            str(executables["gh"]),
            "--codex-path",
            str(executables["codex"]),
            "--runner-path",
            str(runner),
        ]
    )
    return arguments, roots, executables, runner


def _runtime_config_from_arguments(arguments):
    return {
        name: str(Path(getattr(arguments, name)).resolve())
        for name in cli._VERIFIED_RUNTIME_PATH_FIELDS
    }


@pytest.mark.parametrize("root_name", ["lawb", "hgw", "target"])
def test_verify_rejects_state_root_inside_each_git_worktree(
    tmp_path,
    monkeypatch,
    root_name,
):
    arguments, roots, _, _ = _start_arguments(tmp_path)
    arguments.state_root = str(roots[root_name] / "state")
    monkeypatch.setattr(cli, "_verify_lawb_checkout", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_verify_git_root", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli,
        "verify_hgw_checkout",
        lambda root: {"result": "success", "reason": None},
    )

    result = cli.verify_start_prerequisites(arguments)

    assert result["result"] == "blocked"
    assert "state_root_inside_git_worktree" in result["blocked_reasons"]


def test_verify_uses_exact_lawb_branch_head_and_candidate_file_set(
    tmp_path,
    monkeypatch,
):
    observed = {}
    arguments, _, _, _ = _start_arguments(tmp_path)
    arguments.lawb_expected_modified_file = ["src/example.py"]

    def verify_lawb(root, **kwargs):
        observed["root"] = root
        observed.update(kwargs)
        return True

    monkeypatch.setattr(cli, "_verify_lawb_checkout", verify_lawb)
    monkeypatch.setattr(cli, "_verify_git_root", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli,
        "verify_hgw_checkout",
        lambda root: {"result": "success", "reason": None},
    )

    result = cli.verify_start_prerequisites(arguments)

    assert result["result"] == "success"
    assert observed["branch"] == "candidate"
    assert observed["head"] == "a" * 40
    assert observed["expected_modified_files"] == ["src/example.py"]
    assert result["verified_runtime_config"] == _runtime_config_from_arguments(
        arguments
    )


@pytest.mark.parametrize(
    "field",
    [
        "python_path",
        "powershell_path",
        "gh_path",
        "codex_path",
        "runner_path",
    ],
)
def test_verify_rejects_each_relative_reviewed_file_path(
    tmp_path,
    monkeypatch,
    field,
):
    arguments, _, _, _ = _start_arguments(tmp_path)
    setattr(arguments, field, Path(getattr(arguments, field)).name)
    monkeypatch.setattr(cli, "_verify_lawb_checkout", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_verify_git_root", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli,
        "verify_hgw_checkout",
        lambda root: {"result": "success", "reason": None},
    )

    result = cli.verify_start_prerequisites(arguments)

    assert result["result"] == "blocked"
    assert "reviewed_path_not_absolute" in result["blocked_reasons"]
    assert "verified_runtime_config" not in result


def test_verify_accepts_absolute_paths_and_returns_only_resolved_runtime_paths(
    tmp_path,
    monkeypatch,
):
    arguments, _, _, _ = _start_arguments(tmp_path)
    monkeypatch.setattr(cli, "_verify_lawb_checkout", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_verify_git_root", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli,
        "verify_hgw_checkout",
        lambda root: {"result": "success", "reason": None},
    )

    result = cli.verify_start_prerequisites(arguments)

    assert result["result"] == "success"
    config = result["verified_runtime_config"]
    assert set(config) == set(cli._VERIFIED_RUNTIME_PATH_FIELDS)
    assert all(Path(value).is_absolute() for value in config.values())
    assert config == _runtime_config_from_arguments(arguments)


def test_start_uses_verified_paths_after_cwd_and_raw_arguments_change(
    tmp_path,
    monkeypatch,
):
    arguments, _, _, _ = _start_arguments(tmp_path)
    monkeypatch.setattr(cli, "_verify_lawb_checkout", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_verify_git_root", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli,
        "verify_hgw_checkout",
        lambda root: {"result": "success", "reason": None},
    )
    verified = cli.verify_start_prerequisites(arguments)[
        "verified_runtime_config"
    ]
    original = dict(verified)
    observed = {"reads": [], "runner": None, "renderer": None}

    def fake_read_issue(gh_path, repository, issue):
        observed["reads"].append((gh_path, repository, issue))
        return {}

    def fake_runner(request, evidence_path, **kwargs):
        observed["runner"] = kwargs
        return 0

    def fake_renderer(**kwargs):
        observed["renderer"] = kwargs
        return {"result": "success"}

    def fake_foreground(**kwargs):
        observed["foreground"] = kwargs
        kwargs["selector_reader"]()
        kwargs["target_reader"](9)
        kwargs["runner"](
            {"selector": {"target_issue": 9, "request_id": "req-9"}},
            tmp_path / "evidence.json",
        )
        kwargs["hgw_renderer"]({}, "req-9", "created")
        return cli._summary("success")

    monkeypatch.setattr(cli, "_read_issue", fake_read_issue)
    monkeypatch.setattr(cli, "_invoke_runner", fake_runner)
    monkeypatch.setattr(cli, "render_from_evidence", fake_renderer)
    monkeypatch.setattr(cli, "run_foreground", fake_foreground)

    for field in cli._VERIFIED_RUNTIME_PATH_FIELDS:
        setattr(arguments, field, f"relative-decoy-{field}")
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    result = cli._start(
        verified,
        max_cycles=3,
        poll_interval_seconds=0.25,
    )

    assert result["result"] == "success"
    assert all(read[0] == original["gh_path"] for read in observed["reads"])
    assert observed["runner"] == {
        "powershell_path": original["powershell_path"],
        "runner_path": original["runner_path"],
        "target_repo_root": original["target_repo_root"],
        "codex_path": original["codex_path"],
        "gh_path": original["gh_path"],
    }
    assert observed["renderer"]["root"] == original["hgw_root"]
    assert observed["renderer"]["python_path"] == original["python_path"]
    assert observed["foreground"]["python_path"] == original["python_path"]
    assert observed["foreground"]["state_root"] == original["state_root"]
    assert observed["foreground"]["target_repo_root"] == original[
        "target_repo_root"
    ]
    assert observed["foreground"]["max_cycles"] == 3
    assert observed["foreground"]["poll_interval_seconds"] == 0.25


def test_start_fails_closed_for_incomplete_verified_runtime_config(
    tmp_path,
    monkeypatch,
):
    arguments, _, _, _ = _start_arguments(tmp_path)
    incomplete = _runtime_config_from_arguments(arguments)
    incomplete.pop("python_path")
    monkeypatch.setattr(
        cli,
        "run_foreground",
        lambda **kwargs: pytest.fail("start boundary must not be reached"),
    )

    result = cli._start(incomplete)

    assert result == cli._summary(
        "blocked",
        ["verified_runtime_config_invalid"],
    )


def test_runner_invocation_uses_reviewed_powershell_gh_and_timeout(
    tmp_path,
    monkeypatch,
):
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        return type("Completed", (), {"returncode": 2})()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    request = {"selector": {"target_issue": 9, "request_id": "req-reviewed-9"}}
    code = cli._invoke_runner(
        request,
        tmp_path / "evidence.json",
        powershell_path=str(tmp_path / "reviewed-pwsh.exe"),
        runner_path=str(tmp_path / "runner.ps1"),
        target_repo_root=str(tmp_path / "target"),
        codex_path=str(tmp_path / "reviewed-codex.cmd"),
        gh_path=str(tmp_path / "reviewed-gh.exe"),
    )

    assert code == 2
    assert observed["argv"][0] == str(tmp_path / "reviewed-pwsh.exe")
    gh_index = observed["argv"].index("-ReviewedGhPath")
    assert observed["argv"][gh_index + 1] == str(tmp_path / "reviewed-gh.exe")
    request_index = observed["argv"].index("-DisplayPilotRequestId")
    assert observed["argv"][request_index + 1] == "req-reviewed-9"
    assert observed["timeout"] == cli.RUNNER_TIMEOUT_SECONDS
    assert observed["shell"] is False


def test_start_production_issue_reader_treats_missing_selector_as_idle(
    tmp_path,
    monkeypatch,
):
    body = "No DP4-B selector is currently published."
    reads = []

    def fake_read_issue(gh_path, repository, issue):
        reads.append((gh_path, repository, issue))
        return {
            "repository": repository,
            "number": issue,
            "body": body,
            "state": "OPEN",
            "creator": "HarryWhite-TW",
            "body_sha256": cli.body_sha256(body),
        }

    monkeypatch.setattr(cli, "_read_issue", fake_read_issue)
    arguments = cli._parser().parse_args(
        [
            "start",
            "--state-root",
            str(tmp_path / "state"),
            "--lawb-root",
            str(tmp_path / "lawb"),
            "--hgw-root",
            str(tmp_path / "hgw"),
            "--target-repo-root",
            str(tmp_path / "target"),
            "--python-path",
            str(tmp_path / "python.exe"),
            "--powershell-path",
            str(tmp_path / "pwsh.exe"),
            "--gh-path",
            str(tmp_path / "gh.exe"),
            "--codex-path",
            str(tmp_path / "codex.cmd"),
            "--runner-path",
            str(tmp_path / "runner.ps1"),
            "--max-cycles",
            "2",
            "--poll-interval-seconds",
            "0",
        ]
    )

    result = cli._start(
        _runtime_config_from_arguments(arguments),
        max_cycles=arguments.max_cycles,
        poll_interval_seconds=arguments.poll_interval_seconds,
    )

    assert result["result"] == "success"
    assert result["polling_outcome"] == "no_eligible_request"
    assert result["cycles"] == 2
    assert result["github_write_performed"] is False
    assert reads == [
        (str(tmp_path / "gh.exe"), cli.SELECTOR_REPOSITORY, cli.SELECTOR_ISSUE),
        (str(tmp_path / "gh.exe"), cli.SELECTOR_REPOSITORY, cli.SELECTOR_ISSUE),
    ]


def test_lawb_checkout_binding_checks_origin_branch_head_status_and_stage(tmp_path):
    repo = tmp_path / "lawb"
    subprocess.run(
        ["git", "init", "-b", "candidate", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = repo / "tracked.txt"
    tracked.write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=DP4 Test",
            "-c",
            "user.email=dp4@example.invalid",
            "commit",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", cli.LAWB_ORIGIN],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert cli._verify_lawb_checkout(
        repo,
        branch="candidate",
        head=head,
        expected_modified_files=[],
    )
    assert not cli._verify_lawb_checkout(
        repo,
        branch="other",
        head=head,
        expected_modified_files=[],
    )
    tracked.write_text("modified\n", encoding="utf-8")
    assert cli._verify_lawb_checkout(
        repo,
        branch="candidate",
        head=head,
        expected_modified_files=["tracked.txt"],
    )
    assert not cli._verify_lawb_checkout(
        repo,
        branch="candidate",
        head=head,
        expected_modified_files=[],
    )
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    assert not cli._verify_lawb_checkout(
        repo,
        branch="candidate",
        head=head,
        expected_modified_files=["tracked.txt"],
    )
