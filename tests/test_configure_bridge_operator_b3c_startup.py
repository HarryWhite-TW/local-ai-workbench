from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "configure_bridge_operator_b3c_startup.ps1"
MANAGED_NAME = "LocalAIWorkbench-BridgeOperator-B3C.cmd"


def powershell() -> str:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if not found:
        pytest.skip("Windows PowerShell is required")
    return found


def run_adapter(startup: Path, *args: str):
    env = os.environ.copy()
    env["LAWB_STARTUP_ADAPTER_TEST_ONLY"] = "1"
    command = [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        *args,
        "-TestOnlyStartupDirectory",
        str(startup),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        check=False,
    )
    return result, json.loads(result.stdout)


def test_operations_are_mutually_exclusive_and_no_operation_is_blocked(tmp_path):
    startup = tmp_path / "startup"
    startup.mkdir()
    for args in ((), ("-Enable", "-Status"), ("-Status", "-Disable")):
        result, summary = run_adapter(startup, *args)
        assert result.returncode == 2
        assert summary["state"] == "blocked"
        assert summary["reason"] == "exactly_one_operation_required"
        assert not (startup / MANAGED_NAME).exists()


def test_absent_status_is_read_only(tmp_path):
    startup = tmp_path / "startup"
    startup.mkdir()
    before = set(startup.iterdir())
    result, summary = run_adapter(startup, "-Status")
    assert result.returncode == 0
    assert summary["state"] == "absent"
    assert summary["changed"] is False
    assert set(startup.iterdir()) == before


def test_enable_is_deterministic_bomless_exact_and_idempotent(tmp_path):
    startup = tmp_path / "startup with spaces"
    startup.mkdir()
    first, first_summary = run_adapter(startup, "-Enable")
    managed = startup / MANAGED_NAME
    first_bytes = managed.read_bytes()
    second, second_summary = run_adapter(startup, "-Enable")

    assert first.returncode == second.returncode == 0
    assert first_summary["changed"] is True
    assert second_summary["changed"] is False
    assert second_summary["reason"] == "already_enabled"
    fixed_session = {
        "max_cycles": 100,
        "poll_interval_seconds": 30,
        "timeout_seconds": 600,
    }
    assert {
        key: first_summary[key] for key in fixed_session
    } == fixed_session
    assert {
        key: second_summary[key] for key in fixed_session
    } == fixed_session
    assert managed.read_bytes() == first_bytes
    assert not first_bytes.startswith(b"\xef\xbb\xbf")
    text = first_bytes.decode("utf-8")
    assert "LAWBRIDGE-B3C-STARTUP-MANAGED" in text
    assert f'-File "{ROOT}\\scripts\\start_bridge_operator_b3c.ps1"' in text
    assert "-StartForeground -MaxCycles 100 -PollIntervalSeconds 30" in text
    assert re.search(r"(?<!\d)-MaxCycles 1(?!\d)", text) is None
    assert "-TimeoutSeconds 600" in text
    assert '-StateDir "%LOCALAPPDATA%\\LocalAIWorkbench\\BridgeOperator"' in text
    assert "start \"Local AI Workbench Bridge Operator\"" in text
    assert "WindowsPowerShell\\v1.0\\powershell.exe" in text


def test_exact_status_and_exact_only_disable_are_idempotent(tmp_path):
    startup = tmp_path / "startup"
    startup.mkdir()
    run_adapter(startup, "-Enable")
    status, status_summary = run_adapter(startup, "-Status")
    disabled, disabled_summary = run_adapter(startup, "-Disable")
    repeated, repeated_summary = run_adapter(startup, "-Disable")
    assert status.returncode == disabled.returncode == repeated.returncode == 0
    assert status_summary["state"] == "exact_enabled"
    assert disabled_summary["changed"] is True
    assert repeated_summary["changed"] is False
    assert repeated_summary["reason"] == "already_absent"


@pytest.mark.parametrize("kind", ["unrecognized", "drifted"])
def test_unrecognized_or_drifted_file_reports_and_blocks_enable_disable(
    tmp_path, kind
):
    startup = tmp_path / "startup"
    startup.mkdir()
    managed = startup / MANAGED_NAME
    if kind == "unrecognized":
        original = b"@echo off\r\necho foreign\r\n"
    else:
        run_adapter(startup, "-Enable")
        original = managed.read_bytes() + b"REM drift\r\n"
    managed.write_bytes(original)

    status, summary = run_adapter(startup, "-Status")
    expected = "unrecognized" if kind == "unrecognized" else "drifted_invalid"
    assert status.returncode == 0
    assert summary["state"] == expected
    for operation in ("-Enable", "-Disable"):
        result, blocked = run_adapter(startup, operation)
        assert result.returncode == 2
        assert blocked["state"] == expected
        assert managed.read_bytes() == original


def test_test_override_is_rejected_without_explicit_test_environment(tmp_path):
    startup = tmp_path / "startup"
    startup.mkdir()
    env = os.environ.copy()
    env.pop("LAWB_STARTUP_ADAPTER_TEST_ONLY", None)
    result = subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Status",
            "-TestOnlyStartupDirectory",
            str(startup),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        check=False,
    )
    summary = json.loads(result.stdout)
    assert result.returncode == 2
    assert summary["state"] == "blocked"
    assert summary["reason"] == "test_only_startup_override_rejected"


def test_source_contains_no_alternate_persistence_or_sensitive_behavior():
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()
    for forbidden in (
        "scheduledtasks",
        "schtasks",
        "currentversion\\run",
        "new-service",
        "setx",
        "gh auth",
        "github_token",
        "openai_api_key",
        "get-childitem env:",
    ):
        assert forbidden not in lowered


def test_tests_use_only_the_temporary_startup_seam():
    source = Path(__file__).read_text(encoding="utf-8")
    assert "LAWB_STARTUP_ADAPTER_TEST_ONLY" in source
    assert "-TestOnlyStartupDirectory" in source
    assert "run_adapter(startup" in source
