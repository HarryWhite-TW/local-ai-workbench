from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "start_workflow_runtime.ps1"
PANEL_LAUNCHER = ROOT / "scripts" / "start_workflow_panel.ps1"
OPERATOR_LAUNCHER = ROOT / "scripts" / "start_bridge_operator_b3c.ps1"


def powershell() -> str:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("Windows PowerShell is required")
    return found


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


def run_plan(
    port_state: str,
    *,
    enable_guard: bool = True,
    state_dir: Path | None = None,
    panel_command: str | None = None,
    panel_lineage: Path | None = PANEL_LAUNCHER,
):
    env = os.environ.copy()
    if enable_guard:
        env["LAWB_WORKFLOW_RUNTIME_TEST_ONLY"] = "1"
    else:
        env.pop("LAWB_WORKFLOW_RUNTIME_TEST_ONLY", None)
    state_dir = state_dir or ROOT / ".test-state"
    store = state_dir / "observability" / "events.jsonl"
    if panel_command is None:
        panel_command = panel_command_line(state_dir, store)
    arguments = [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-StateDir",
        str(state_dir),
        "-TestOnlyPortState",
        port_state,
    ]
    if panel_command:
        arguments.extend(["-TestOnlyPanelCommandLine", panel_command])
    if panel_lineage is not None:
        arguments.extend(["-TestOnlyPanelLineagePath", str(panel_lineage)])
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        check=False,
    )
    return result, json.loads(result.stdout)


@pytest.mark.parametrize(
    ("port_state", "panel_action"),
    [("free", "would_start"), ("workflow_panel", "would_reuse")],
)
def test_safe_plan_uses_control_panel_and_canonical_operator(
    port_state: str, panel_action: str
):
    result, summary = run_plan(port_state)

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert summary["reason"] == "test_plan_only"
    assert summary["panel_action"] == panel_action
    assert summary["operator_action"] == "would_start"
    assert summary["processes_started"] is False
    assert Path(summary["control_repo_root"]) == ROOT
    assert Path(summary["state_dir"]) == ROOT / ".test-state"
    assert Path(summary["observation_store"]) == (
        ROOT / ".test-state" / "observability" / "events.jsonl"
    )
    assert summary["routing_authority"] == OPERATOR_LAUNCHER.name
    assert summary["panel_host"] == "127.0.0.1"
    assert summary["panel_port"] == 8765
    assert summary["panel_lifetime_seconds"] == 43200


def test_routing_mutation_cannot_change_cold_start_authority_path(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    routing = state_dir / "repository_routing.json"
    routing.write_bytes(b'{"selected_target":"A"}')
    first_result, first = run_plan("free", state_dir=state_dir)

    routing.write_bytes(b'{"selected_target":"B","mutated":true}')
    second_result, second = run_plan("free", state_dir=state_dir)

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


def test_unknown_port_owner_blocks_both_launches_without_process_action():
    result, summary = run_plan("unknown")

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "panel_port_occupied_unknown"
    assert summary["panel_action"] == "blocked"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


@pytest.mark.parametrize(
    "binding",
    [
        "wrong_state_dir",
        "wrong_store",
        "wrong_host",
        "wrong_port",
        "missing_lifetime",
        "unbounded_lifetime",
        "wrong_lineage",
    ],
)
def test_reused_panel_requires_exact_control_binding_and_finite_lifetime(
    tmp_path: Path, binding: str
):
    state_dir = tmp_path / "state"
    store = state_dir / "observability" / "events.jsonl"
    command_state = state_dir
    command_store = store
    host = "127.0.0.1"
    port = 8765
    lifetime: int | None = 43200
    lineage: Path | None = PANEL_LAUNCHER
    if binding == "wrong_state_dir":
        command_state = tmp_path / "wrong-state"
    elif binding == "wrong_store":
        command_store = tmp_path / "wrong-store" / "events.jsonl"
    elif binding == "wrong_host":
        host = "0.0.0.0"
    elif binding == "wrong_port":
        port = 9999
    elif binding == "missing_lifetime":
        lifetime = None
    elif binding == "unbounded_lifetime":
        lifetime = 0
    elif binding == "wrong_lineage":
        lineage = tmp_path / "start_workflow_panel.ps1"

    result, summary = run_plan(
        "workflow_panel",
        state_dir=state_dir,
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
    assert summary["reason"] == "panel_port_occupied_unknown"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


def test_test_only_plan_requires_explicit_environment_guard():
    result, summary = run_plan("free", enable_guard=False)

    assert result.returncode == 2
    assert summary["reason"] == "test_only_override_rejected"
    assert summary["processes_started"] is False


def test_source_has_one_routing_authority_and_no_second_supervisor():
    text = SCRIPT.read_text(encoding="utf-8")
    body = text.split("#>", 1)[1]
    operator = OPERATOR_LAUNCHER.read_text(encoding="utf-8")
    lowered = body.lower()

    assert "repository_routing.json" not in body
    assert "RoutingProtocol" not in body
    assert "TargetRepoRoot" not in body
    assert "Resolve-TargetRuntime" not in body
    assert "Get-CanonicalOperatorSummary" not in body
    assert "WaitForExit" not in body
    assert ".Kill(" not in body
    assert "start_workflow_panel.ps1" in body
    assert "start_bridge_operator_b3c.ps1" in body
    assert "-StartForeground -PublishStatus" in body
    assert " -TargetRepoRoot " not in body
    assert "repository_routing.json" in operator
    assert "--lifetime-seconds" in body
    assert "[int]$PanelLifetimeSeconds = 43200" in body
    assert body.count("-WindowStyle Hidden") >= 2
    assert "Get-NetTCPConnection" in body
    assert "CommandLineToArgvW" in body
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
