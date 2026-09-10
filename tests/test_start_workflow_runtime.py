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
    state_dir: Path | None = None,
    target_repo_root: Path | None = ROOT,
    control_repo_root: Path | None = None,
    scenario: str = "",
):
    env = os.environ.copy()
    if enable_guard:
        env["LAWB_WORKFLOW_RUNTIME_TEST_ONLY"] = "1"
    else:
        env.pop("LAWB_WORKFLOW_RUNTIME_TEST_ONLY", None)
    state_dir = state_dir or ROOT / ".test-state"
    store = state_dir / "observability" / "events.jsonl"
    command = panel_command_line(state_dir, store)
    lineage_root = target_repo_root or control_repo_root or ROOT
    lineage = lineage_root / "scripts" / "start_workflow_panel.ps1"
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
    ]
    if target_repo_root is not None:
        arguments.extend(["-TestOnlyTargetRepoRoot", str(target_repo_root)])
    if control_repo_root is not None:
        arguments.extend(["-TestOnlyControlRepoRoot", str(control_repo_root)])
    if command:
        arguments.extend(["-TestOnlyPanelCommandLine", command])
    if str(lineage):
        arguments.extend(["-TestOnlyPanelLineagePath", str(lineage)])
    if scenario:
        arguments.extend(["-TestOnlyScenario", scenario])
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


def init_runtime_repo(
    path: Path,
    *,
    branch: str,
    origin: str = "https://github.com/HarryWhite-TW/local-ai-workbench.git",
) -> str:
    path.mkdir(parents=True)
    scripts = path / "scripts"
    scripts.mkdir()
    (scripts / "start_workflow_panel.ps1").write_text(
        "# test-only canonical panel launcher\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=path, check=True)
    subprocess.run(["git", "add", "--", "scripts/start_workflow_panel.ps1"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def write_routing(state_dir: Path, payload: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "repository_routing.json").write_bytes(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


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
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


def test_no_routing_file_uses_supported_control_repo_fallback(tmp_path):
    control_root = tmp_path / "control-runtime"
    init_runtime_repo(control_root, branch="control")
    state_dir = tmp_path / "state"

    result, summary = run_plan(
        "free",
        state_dir=state_dir,
        target_repo_root=None,
        control_repo_root=control_root,
    )

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert Path(summary["target_repo_root"]) == control_root


@pytest.mark.parametrize("protocol", ["v1", "v2"])
def test_supported_routing_schemas_accept_non_ascii_target_and_non_master_branch(
    tmp_path, protocol
):
    target_root = tmp_path / "使用者 工作區"
    branch = "codex/routed-runtime"
    head = init_runtime_repo(target_root, branch=branch)
    state_dir = tmp_path / "狀態"
    if protocol == "v1":
        payload = {
            "protocol": "lawb.bridge_operator_local_routing.v1",
            "repository": "HarryWhite-TW/local-ai-workbench",
            "target_repo_root": str(target_root),
        }
    else:
        payload = {
            "protocol": "lawb.bridge_operator_local_routing.v2",
            "repository": "HarryWhite-TW/local-ai-workbench",
            "selected_target": {
                "selection_id": "routed-non-master",
                "target_repo_root": str(target_root),
                "branch": branch,
                "head": head,
            },
        }
    write_routing(state_dir, payload)

    result, summary = run_plan(
        "free", state_dir=state_dir, target_repo_root=None
    )

    assert result.returncode == 0
    assert summary["result"] == "ready"
    assert Path(summary["target_repo_root"]) == target_root


def test_routing_v1_rejects_clean_git_repo_with_wrong_origin_before_launch(tmp_path):
    target_root = tmp_path / "untrusted-runtime"
    init_runtime_repo(
        target_root,
        branch="codex/routed-runtime",
        origin="https://github.com/example/not-the-canonical-repository.git",
    )
    state_dir = tmp_path / "state"
    write_routing(
        state_dir,
        {
            "protocol": "lawb.bridge_operator_local_routing.v1",
            "repository": "HarryWhite-TW/local-ai-workbench",
            "target_repo_root": str(target_root),
        },
    )

    result, summary = run_plan("free", state_dir=state_dir, target_repo_root=None)

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "target_runtime_origin_mismatch"
    assert summary["panel_action"] == "not_started"
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


@pytest.mark.parametrize(
    ("mismatch", "expected_reason"),
    [
        ("branch", "target_runtime_branch_mismatch"),
        ("head", "target_runtime_head_mismatch"),
    ],
)
def test_routing_v2_fails_closed_on_recorded_branch_or_head_mismatch(
    tmp_path, mismatch, expected_reason
):
    target_root = tmp_path / "runtime"
    head = init_runtime_repo(target_root, branch="codex/actual")
    state_dir = tmp_path / "state"
    payload = {
        "protocol": "lawb.bridge_operator_local_routing.v2",
        "repository": "HarryWhite-TW/local-ai-workbench",
        "selected_target": {
            "selection_id": "mismatch",
            "target_repo_root": str(target_root),
            "branch": "codex/actual",
            "head": head,
        },
    }
    if mismatch == "branch":
        payload["selected_target"]["branch"] = "codex/wrong"
    else:
        payload["selected_target"]["head"] = "0" * 40
    write_routing(state_dir, payload)

    result, summary = run_plan("free", state_dir=state_dir, target_repo_root=None)

    assert result.returncode == 2
    assert summary["reason"] == expected_reason
    assert summary["processes_started"] is False


def test_routing_file_requires_strict_utf8_before_any_process_action(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "repository_routing.json").write_bytes(b'"\xff"')

    result, summary = run_plan("free", state_dir=state_dir, target_repo_root=None)

    assert result.returncode == 2
    assert summary["reason"] == "repository_routing_invalid"
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
    assert summary["operator_action"] == "not_started"
    assert summary["processes_started"] is False


def test_test_only_plan_requires_explicit_environment_guard():
    result, summary = run_plan("free", enable_guard=False)

    assert result.returncode == 2
    assert summary["result"] == "blocked"
    assert summary["reason"] == "test_only_override_rejected"
    assert summary["processes_started"] is False


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (
            "panel_verification_failed",
            {
                "panel_action": "started_unverified",
                "operator_action": "not_started",
                "panel_ownership": "owned",
                "panel_cleanup": "residual_unverified",
                "processes_started": True,
            },
        ),
        (
            "operator_launch_failed_owned",
            {
                "panel_action": "started",
                "operator_action": "launch_failed",
                "panel_ownership": "owned",
                "panel_cleanup": "stopped",
                "processes_started": True,
            },
        ),
        (
            "operator_launch_failed_reused",
            {
                "panel_action": "reused",
                "operator_action": "launch_failed",
                "panel_ownership": "reused",
                "panel_cleanup": "not_owned",
                "processes_started": False,
            },
        ),
        (
            "owned_lifecycle_complete",
            {
                "panel_action": "started",
                "operator_action": "completed",
                "panel_ownership": "owned",
                "panel_cleanup": "stopped",
                "processes_started": True,
            },
        ),
        (
            "owned_lifecycle_residual",
            {
                "result": "blocked",
                "reason": "owned_panel_cleanup_residual_unverified",
                "panel_action": "started",
                "operator_action": "completed",
                "panel_ownership": "owned",
                "panel_cleanup": "residual_unverified",
                "processes_started": True,
            },
        ),
        (
            "panel_launch_failed",
            {
                "result": "blocked",
                "reason": "panel_launch_failed",
                "panel_action": "starting",
                "operator_action": "not_started",
                "panel_ownership": "none",
                "panel_cleanup": "not_needed",
                "processes_started": False,
            },
        ),
    ],
)
def test_partial_start_and_panel_ownership_summaries_are_truthful(scenario, expected):
    result, summary = run_plan("free", scenario=scenario)

    assert result.returncode == (0 if scenario == "owned_lifecycle_complete" else 2)
    for key, value in expected.items():
        assert summary[key] == value


@pytest.mark.parametrize(
    ("scenario", "expected_result", "expected_returncode"),
    [
        ("operator_waiting_review", "waiting_review", 0),
        ("operator_running", "running", 0),
        ("operator_completed", "completed", 0),
        ("operator_blocked", "blocked", 2),
    ],
)
def test_runtime_preserves_canonical_operator_semantic_result(
    scenario, expected_result, expected_returncode
):
    result, summary = run_plan("workflow_panel", scenario=scenario)

    assert result.returncode == expected_returncode
    assert summary["result"] == expected_result
    assert summary["reason"] == "canonical_operator_result"
    assert summary["operator_action"] == expected_result
    assert summary["panel_action"] == "reused"
    assert summary["panel_ownership"] == "reused"
    assert summary["panel_cleanup"] == "not_owned"


def test_source_preserves_single_authority_and_hidden_loopback_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "repository_routing.json" in text
    assert "start_bridge_operator_b3c.ps1" in text
    assert "start_workflow_panel.ps1" in text
    assert "Get-NetTCPConnection" in text
    assert "CommandLineToArgvW" in text
    assert "Test-ExactWindowsPath" in text
    assert "UTF8Encoding($false, $true)" in text
    assert 'lawb.bridge_operator_local_routing.v1' in text
    assert 'lawb.bridge_operator_local_routing.v2' in text
    assert "lawb.workflow_panel.v1" in text
    assert '"127.0.0.1"' in text
    assert "[int]$PanelPort = 8765" in text
    assert text.count("-WindowStyle Hidden") >= 2
    assert "Start-Process" in text
    assert "-StartForeground -PublishStatus" in text
    assert "target_runtime_head_mismatch" in text
    assert "target_runtime_git_root_mismatch" in text
    assert "target_runtime_origin_mismatch" in text
    assert "target_runtime_not_clean" in text
    assert "lawb.bridge_operator_b3c_launcher.v1" in text
    assert "Get-CanonicalOperatorSummary" in text
    assert "$operatorProcess.WaitForExit()" in text
    assert "Stop-OwnedPanelRuntime" in text
    assert "Test-ProcessDescendsFrom" in text
    assert "$remainingListeners.Count -eq 0" in text
    assert "terminate only a" in lowered
    assert "never terminates a reused or unknown process" in lowered
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
