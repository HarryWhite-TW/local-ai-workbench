from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "start_workflow_runtime.ps1"


def powershell() -> str:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("Windows PowerShell is required")
    return found


def panel_command_line(
    state_dir: Path,
    store: Path,
    *,
    include_state_dir: bool = True,
    include_store: bool = True,
) -> str:
    arguments = [
        "python.exe",
        "-m",
        "local_runner_bridge.workflow_panel",
    ]
    if include_state_dir:
        arguments.extend(["--state-dir", str(state_dir)])
    if include_store:
        arguments.extend(["--store", str(store)])
    arguments.extend(["--host", "127.0.0.1", "--port", "8765"])
    return subprocess.list2cmdline(arguments)


def run_plan(
    port_state: str,
    *,
    enable_guard: bool = True,
    panel_binding: str = "canonical",
):
    env = os.environ.copy()
    if enable_guard:
        env["LAWB_WORKFLOW_RUNTIME_TEST_ONLY"] = "1"
    else:
        env.pop("LAWB_WORKFLOW_RUNTIME_TEST_ONLY", None)
    state_dir = ROOT / ".test-state"
    store = state_dir / "observability" / "events.jsonl"
    command = panel_command_line(state_dir, store)
    lineage = ROOT / "scripts" / "start_workflow_panel.ps1"
    if panel_binding == "wrong_state_dir":
        command = panel_command_line(ROOT / ".wrong-state", store)
    elif panel_binding == "wrong_store":
        command = panel_command_line(state_dir, ROOT / ".wrong-store" / "events.jsonl")
    elif panel_binding == "missing_state_dir":
        command = panel_command_line(state_dir, store, include_state_dir=False)
    elif panel_binding == "missing_store":
        command = panel_command_line(state_dir, store, include_store=False)
    elif panel_binding == "missing_lineage":
        lineage = Path("")
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
        "-TestOnlyTargetRepoRoot",
        str(ROOT),
    ]
    if command:
        arguments.extend(["-TestOnlyPanelCommandLine", command])
    if str(lineage):
        arguments.extend(["-TestOnlyPanelLineagePath", str(lineage)])
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
def test_safe_plan_uses_fixed_panel_and_existing_operator_launchers(
    port_state, panel_action
):
    result, summary = run_plan(port_state)

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert summary["reason"] == "test_plan_only"
    assert summary["panel_action"] == panel_action
    assert summary["operator_action"] == "would_start"
    assert summary["processes_started"] is False
    assert summary["target_repo_root"] == str(ROOT)
    assert summary["panel_host"] == "127.0.0.1"
    assert summary["panel_port"] == 8765


def test_unknown_port_owner_blocks_both_launches_without_process_action():
    result, summary = run_plan("unknown")

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "panel_port_occupied_unknown"
    assert summary["panel_action"] == "blocked"
    assert summary["operator_action"] == "blocked"
    assert summary["processes_started"] is False


@pytest.mark.parametrize(
    "panel_binding",
    [
        "wrong_state_dir",
        "wrong_store",
        "missing_state_dir",
        "missing_store",
        "missing_lineage",
    ],
)
def test_workflow_panel_with_unproven_canonical_binding_is_blocked(panel_binding):
    result, summary = run_plan("workflow_panel", panel_binding=panel_binding)

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "panel_port_occupied_unknown"
    assert summary["panel_action"] == "blocked"
    assert summary["operator_action"] == "blocked"
    assert summary["processes_started"] is False


def test_test_only_plan_requires_explicit_environment_guard():
    result, summary = run_plan("free", enable_guard=False)

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "test_only_override_rejected"
    assert summary["processes_started"] is False


def test_source_preserves_single_authority_and_hidden_loopback_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "repository_routing.json" in text
    assert "start_bridge_operator_b3c.ps1" in text
    assert "start_workflow_panel.ps1" in text
    assert "Get-NetTCPConnection" in text
    assert "CommandLineToArgvW" in text
    assert "Test-ExactWindowsPath" in text
    assert "lawb.workflow_panel.v1" in text
    assert '"127.0.0.1"' in text
    assert "[int]$PanelPort = 8765" in text
    assert text.count("-WindowStyle Hidden") >= 2
    assert "Start-Process" in text
    assert "-StartForeground -PublishStatus" in text
    assert "target_runtime_head_mismatch" in text
    assert "target_runtime_not_clean" in text
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
