from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = ROOT / "scripts" / "start_workflow_runtime.ps1"
OPERATOR_LAUNCHER = ROOT / "scripts" / "start_bridge_operator_b3c.ps1"
CANONICAL_ORIGIN = "https://github.com/HarryWhite-TW/local-ai-workbench.git"


def powershell() -> str:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("Windows PowerShell is required")
    return found


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def make_control_repo(
    tmp_path: Path,
    *,
    origin: str = CANONICAL_ORIGIN,
    nested_runtime: bool = False,
) -> tuple[Path, Path]:
    repository = tmp_path / "control"
    script_root = repository / "nested" if nested_runtime else repository
    scripts = script_root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(SOURCE_SCRIPT, scripts / SOURCE_SCRIPT.name)
    (scripts / "start_workflow_panel.ps1").write_text(
        'throw "test_stub_must_not_execute"\n', encoding="utf-8"
    )
    (scripts / "start_bridge_operator_b3c.ps1").write_text(
        'throw "test_stub_must_not_execute"\n', encoding="utf-8"
    )
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    git(repository, "config", "user.name", "Cold Start Test")
    git(repository, "config", "user.email", "cold-start@example.invalid")
    git(repository, "remote", "add", "origin", origin)
    git(repository, "add", "--all")
    git(repository, "commit", "-q", "-m", "fixture")
    return scripts / SOURCE_SCRIPT.name, repository


def panel_command_line(
    state_dir: Path,
    store: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    lifetime_seconds: int | None = 43200,
) -> str:
    arguments = [
        "python.exe",
        "-m",
        "local_runner_bridge.workflow_panel",
        "--state-dir",
        str(state_dir),
        "--store",
        str(store),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if lifetime_seconds is not None:
        arguments.extend(["--lifetime-seconds", str(lifetime_seconds)])
    return subprocess.list2cmdline(arguments)


def run_runtime(
    script: Path,
    tmp_path: Path,
    *,
    port_state: str = "free",
    post_launch_state: str = "",
    enable_guard: bool = True,
    state_dir: Path | None = None,
    panel_command: str | None = None,
    panel_lineage: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    env = os.environ.copy()
    if enable_guard:
        env["LAWB_WORKFLOW_RUNTIME_TEST_ONLY"] = "1"
    else:
        env.pop("LAWB_WORKFLOW_RUNTIME_TEST_ONLY", None)
    resolved_state = state_dir or tmp_path / "state"
    store = resolved_state / "observability" / "events.jsonl"
    arguments = [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-StateDir",
        str(resolved_state),
        "-TestOnlyPortState",
        port_state,
    ]
    if post_launch_state:
        arguments.extend(["-TestOnlyPostLaunchState", post_launch_state])
        if panel_command is None:
            panel_command = panel_command_line(resolved_state, store)
        if panel_lineage is None:
            panel_lineage = script.parent / "start_workflow_panel.ps1"
    if panel_command is not None:
        arguments.extend(["-TestOnlyPanelCommandLine", panel_command])
    if panel_lineage is not None:
        arguments.extend(["-TestOnlyPanelLineagePath", str(panel_lineage)])
    result = subprocess.run(
        arguments,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        check=False,
    )
    return result, json.loads(result.stdout)


def test_clean_canonical_control_checkout_proceeds(tmp_path: Path):
    script, repository = make_control_repo(tmp_path)
    result, summary = run_runtime(script, tmp_path)

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert summary["reason"] == "test_plan_only"
    assert summary["panel_action"] == "would_start"
    assert summary["operator_action"] == "would_start"
    assert summary["processes_started"] is False
    assert Path(str(summary["control_repo_root"])) == repository
    assert summary["routing_authority"] == OPERATOR_LAUNCHER.name
    assert summary["panel_host"] == "127.0.0.1"
    assert summary["panel_port"] == 8765
    assert summary["panel_lifetime_seconds"] == 43200


@pytest.mark.parametrize("pollution", ["dirty", "staged", "untracked"])
def test_polluted_control_checkout_blocks_before_panel_execution(
    tmp_path: Path, pollution: str
):
    script, repository = make_control_repo(tmp_path)
    if pollution == "dirty":
        (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    elif pollution == "staged":
        (repository / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(repository, "add", "staged.txt")
    else:
        (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    result, summary = run_runtime(script, tmp_path)

    assert result.returncode == 2
    assert summary["reason"] == "control_repository_worktree_dirty"
    assert summary["panel_action"] == "not_started"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


def test_wrong_control_origin_blocks_before_panel_execution(tmp_path: Path):
    script, _ = make_control_repo(
        tmp_path, origin="https://github.com/example/not-canonical.git"
    )
    result, summary = run_runtime(script, tmp_path)

    assert result.returncode == 2
    assert summary["reason"] == "control_repository_origin_mismatch"
    assert summary["panel_action"] == "not_started"
    assert summary["operator_action"] == "not_started"


def test_non_root_control_checkout_blocks_before_panel_execution(tmp_path: Path):
    script, _ = make_control_repo(tmp_path, nested_runtime=True)
    result, summary = run_runtime(script, tmp_path)

    assert result.returncode == 2
    assert summary["reason"] == "control_repository_root_mismatch"
    assert summary["panel_action"] == "not_started"
    assert summary["operator_action"] == "not_started"


def test_occupied_port_always_blocks_without_panel_reuse(tmp_path: Path):
    script, _ = make_control_repo(tmp_path)
    result, summary = run_runtime(
        script,
        tmp_path,
        port_state="occupied",
        post_launch_state="owned",
    )

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "panel_port_occupied"
    assert summary["panel_action"] == "blocked"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


def test_free_port_verifies_this_invocations_bounded_panel(tmp_path: Path):
    script, _ = make_control_repo(tmp_path)
    result, summary = run_runtime(
        script,
        tmp_path,
        post_launch_state="owned",
    )

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert summary["reason"] == "test_plan_only"
    assert summary["panel_action"] == "would_start_verified"
    assert summary["operator_action"] == "would_start"
    assert summary["processes_started"] is False


def test_competing_listener_race_fails_closed_before_operator(tmp_path: Path):
    script, _ = make_control_repo(tmp_path)
    result, summary = run_runtime(
        script,
        tmp_path,
        post_launch_state="competing",
    )

    assert result.returncode == 2
    assert summary["reason"] == "workflow_panel_start_not_verified"
    assert summary["panel_action"] == "would_start_unverified"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


@pytest.mark.parametrize(
    "binding",
    [
        "wrong_state_dir",
        "wrong_store",
        "wrong_host",
        "wrong_port",
        "wrong_lifetime",
        "wrong_lineage",
    ],
)
def test_new_panel_requires_exact_control_binding(tmp_path: Path, binding: str):
    script, _ = make_control_repo(tmp_path)
    state_dir = tmp_path / "state"
    store = state_dir / "observability" / "events.jsonl"
    command_state = state_dir
    command_store = store
    host = "127.0.0.1"
    port = 8765
    lifetime = 43200
    lineage = script.parent / "start_workflow_panel.ps1"
    if binding == "wrong_state_dir":
        command_state = tmp_path / "wrong-state"
    elif binding == "wrong_store":
        command_store = tmp_path / "wrong-store" / "events.jsonl"
    elif binding == "wrong_host":
        host = "0.0.0.0"
    elif binding == "wrong_port":
        port = 9999
    elif binding == "wrong_lifetime":
        lifetime = 43199
    else:
        lineage = tmp_path / "wrong" / "start_workflow_panel.ps1"

    result, summary = run_runtime(
        script,
        tmp_path,
        post_launch_state="owned",
        panel_command=panel_command_line(
            command_state,
            command_store,
            host=host,
            port=port,
            lifetime_seconds=lifetime,
        ),
        panel_lineage=lineage,
    )

    assert result.returncode == 2
    assert summary["reason"] == "workflow_panel_start_not_verified"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


def test_routing_mutation_cannot_change_cold_start_authority_path(tmp_path: Path):
    script, _ = make_control_repo(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    routing = state_dir / "repository_routing.json"
    routing.write_bytes(b'{"selected_target":"A"}')
    first_result, first = run_runtime(script, tmp_path, state_dir=state_dir)

    routing.write_bytes(b'{"selected_target":"B","mutated":true}')
    second_result, second = run_runtime(script, tmp_path, state_dir=state_dir)

    assert first_result.returncode == second_result.returncode == 0
    stable_fields = {
        "control_repo_root",
        "state_dir",
        "observation_store",
        "routing_authority",
        "panel_action",
        "operator_action",
    }
    assert {key: first[key] for key in stable_fields} == {
        key: second[key] for key in stable_fields
    }
    assert "target_repo_root" not in first
    assert routing.read_bytes() == b'{"selected_target":"B","mutated":true}'


def test_test_only_plan_requires_explicit_environment_guard(tmp_path: Path):
    script, _ = make_control_repo(tmp_path)
    result, summary = run_runtime(script, tmp_path, enable_guard=False)

    assert result.returncode == 2
    assert summary["reason"] == "test_only_override_rejected"
    assert summary["processes_started"] is False


def test_source_has_one_routing_authority_and_no_panel_reuse_or_supervisor():
    text = SOURCE_SCRIPT.read_text(encoding="utf-8")
    body = text.split("#>", 1)[1]
    main = body.split('$resolvedStateDir = ""', 1)[1]
    operator = OPERATOR_LAUNCHER.read_text(encoding="utf-8")
    lowered = body.lower()

    assert "repository_routing.json" not in body
    assert "RoutingProtocol" not in body
    assert "TargetRepoRoot" not in body
    assert "Resolve-TargetRuntime" not in body
    assert "Get-CanonicalOperatorSummary" not in body
    assert "WaitForExit" not in body
    assert ".Kill(" not in body
    assert "reuse" not in lowered
    assert "Get-PanelPortState" not in body
    assert "start_workflow_panel.ps1" in body
    assert "start_bridge_operator_b3c.ps1" in body
    assert "-StartForeground -PublishStatus" in body
    assert " -TargetRepoRoot " not in body
    assert "repository_routing.json" in operator
    assert "--lifetime-seconds" in body
    assert "$observedLifetime -ne $PanelLifetimeSeconds" in body
    assert "Test-ProcessDescendsFrom" in body
    assert body.count("-WindowStyle Hidden") >= 2
    assert "Get-NetTCPConnection" in body
    assert "CommandLineToArgvW" in body
    assert main.index("Assert-ControlRuntimeIntegrity") < main.index("Test-PanelPortFree")
    assert '"status", "--porcelain=v1", "--untracked-files=all"' in body
    assert '"remote", "get-url", "origin"' in body
    assert '"rev-parse", "HEAD"' in body
    assert '"branch"' not in body
    assert '"fetch"' not in body
    for lifecycle_result in ("waiting_review", "completed"):
        assert lifecycle_result not in body
    for forbidden in (
        "stop-process",
        "taskkill",
        "stop-computer",
        "scheduledtasks",
        "schtasks",
        "currentversion\\run",
        "new-service",
        "sc.exe",
        "new-netfirewallrule",
        "gh auth",
    ):
        assert forbidden not in lowered
