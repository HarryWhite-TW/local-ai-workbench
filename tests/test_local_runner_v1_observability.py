import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "local_runner_v1.ps1"
sys.path.insert(0, str(REPO_ROOT / "src"))

from local_runner_bridge.workflow_observability import EventStore  # noqa: E402


def powershell() -> str:
    reviewed = os.environ.get("LAWB_TEST_POWERSHELL_PATH")
    if reviewed:
        return reviewed
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for local_runner_v1 tests")
    return shell


def runner_core() -> str:
    source = RUNNER.read_text(encoding="utf-8")
    start = source.index("Set-StrictMode -Version Latest")
    end = source.index("\nAssert-TargetRepositoryBinding")
    route_start = source.index("function Get-RuntimeContractExecutionRoute")
    route_end = source.index("\n$initialModifiedFiles = Get-ModifiedFilesFromStatus", route_start)
    return source[start:end] + "\n" + source[route_start:route_end]


def write_emitter(path: Path, *, delay: float, exit_code: int) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            import json
            import sys
            import time

            print(json.dumps({{"type": "thread.started", "thread_id": "thread-test"}}), flush=True)
            print(json.dumps({{"type": "turn.started"}}), flush=True)
            time.sleep({delay!r})
            print(json.dumps({{
                "type": "item.completed",
                "item": {{
                    "id": "cmd-test",
                    "type": "command_execution",
                    "command": "pytest -q --password must-not-persist",
                    "aggregated_output": "TOKEN=must-not-persist",
                    "exit_code": {exit_code},
                    "status": "completed"
                }}
            }}), flush=True)
            raise SystemExit({exit_code})
            """
        ).strip(),
        encoding="utf-8",
    )


def write_continuous_emitter(path: Path, *, duration: float, interval: float) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            import json
            import time

            deadline = time.monotonic() + {duration!r}
            while time.monotonic() < deadline:
                print(json.dumps({{"type": "turn.started"}}), flush=True)
                time.sleep({interval!r})
            """
        ).strip(),
        encoding="utf-8",
    )


def write_inherited_stdout_fixture(
    parent: Path,
    descendant: Path,
    *,
    descendant_duration: float,
    interval: float,
) -> None:
    write_continuous_emitter(
        descendant,
        duration=descendant_duration,
        interval=interval,
    )
    parent.write_text(
        textwrap.dedent(
            f"""
            import json
            import subprocess
            import sys

            subprocess.Popen(
                [sys.executable, {str(descendant)!r}],
                stdin=subprocess.DEVNULL,
                stdout=sys.stdout,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            print(json.dumps({{"type": "thread.started", "thread_id": "parent-thread"}}), flush=True)
            """
        ).strip(),
        encoding="utf-8",
    )


def write_harness(
    path: Path,
    *,
    emitter: Path,
    store_path: Path,
    timeout_seconds: int,
    result_path: Path | None = None,
) -> None:
    worktree = path.parent / "worktree"
    worktree.mkdir(exist_ok=True)
    result_statement = (
        "$result | ConvertTo-Json -Depth 10 -Compress"
        if result_path is None
        else (
            f"[System.IO.File]::WriteAllText({str(result_path)!r}, "
            "($result | ConvertTo-Json -Depth 10 -Compress), "
            "[System.Text.UTF8Encoding]::new($false))"
        )
    )
    path.write_text(
        runner_core()
        + "\n"
        + textwrap.dedent(
            f"""
            $ControlRepoRoot = {str(REPO_ROOT)!r}
            $RepoPath = {str(worktree)!r}
            $WorkflowObservationScriptRelativePath = "src\\local_runner_bridge\\workflow_observability.py"
            $config = New-WorkflowObservationConfig `
                -StorePath {str(store_path)!r} `
                -RequestId "obs-runner-request"
            $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
            $result = Invoke-CapturedNativeProcess `
                -FilePath {str(Path(sys.executable))!r} `
                -Arguments @({str(emitter)!r}) `
                -WorkingDirectory {str(worktree)!r} `
                -StandardInput "" `
                -StandardInputEncoding $utf8 `
                -StandardOutputEncoding $utf8 `
                -StandardErrorEncoding $utf8 `
                -TimeoutSeconds {timeout_seconds} `
                -Action "observability integration test" `
                -WorkflowObservation $config
            {result_statement}
            """
        ),
        encoding="utf-8-sig",
    )


def parse_last_json(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip().startswith("{")]
    assert lines, stdout
    return json.loads(lines[-1])


def test_runner_persists_structured_events_before_child_exit(tmp_path):
    emitter = tmp_path / "emit_events.py"
    store_path = (tmp_path / "state" / "events.jsonl").resolve()
    harness = tmp_path / "runner_observation_test.ps1"
    write_emitter(emitter, delay=2.0, exit_code=0)
    write_harness(
        harness,
        emitter=emitter,
        store_path=store_path,
        timeout_seconds=10,
    )

    process = subprocess.Popen(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    live_events = []
    # Windows PowerShell 5.1 can have a noticeably slower cold start than pwsh.
    # The emitter still leaves a two-second window in which the durable events
    # must be observable before the child exits.
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if store_path.exists():
            live_events, _ = EventStore(store_path).read()
            if len(live_events) >= 3:
                break
        if process.poll() is not None:
            break
        time.sleep(0.03)
    if len(live_events) < 3:
        stdout, stderr = process.communicate(timeout=10)
        pytest.fail(f"durable events were not observed before exit\n{stdout}\n{stderr}")
    assert process.poll() is None
    assert [event["kind"] for event in live_events[:3]] == [
        "execution.started",
        "codex.thread.started",
        "codex.turn.started",
    ]

    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr
    result = parse_last_json(stdout)
    assert result["ExitCode"] == 0
    assert result["Observability"]["status"] == "ok"
    assert result["Observability"]["completion_observed"] is True
    events, diagnostics = EventStore(store_path).read()
    assert diagnostics == []
    assert events[-1]["kind"] == "process.completed"
    assert events[-1]["payload"]["exit_code"] == 0
    durable_text = store_path.read_text(encoding="utf-8")
    assert "must-not-persist" not in durable_text


def test_observability_degradation_does_not_change_success_exit(tmp_path):
    emitter = tmp_path / "emit_events.py"
    store_path = (tmp_path / "events.jsonl").resolve()
    store_path.mkdir()
    harness = tmp_path / "runner_observation_test.ps1"
    write_emitter(emitter, delay=0.05, exit_code=0)
    write_harness(
        harness,
        emitter=emitter,
        store_path=store_path,
        timeout_seconds=5,
    )
    result = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        errors="replace",
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["ExitCode"] == 0
    assert payload["TimedOut"] is False
    assert payload["Observability"]["status"] == "degraded"
    assert payload["Observability"]["events_written"] == 0


def test_observed_non_success_and_timeout_preserve_native_result(tmp_path):
    failure_emitter = tmp_path / "emit_failure.py"
    failure_store = (tmp_path / "failure" / "events.jsonl").resolve()
    failure_harness = tmp_path / "failure.ps1"
    write_emitter(failure_emitter, delay=0.05, exit_code=7)
    write_harness(
        failure_harness,
        emitter=failure_emitter,
        store_path=failure_store,
        timeout_seconds=5,
    )
    failure = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(failure_harness)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        errors="replace",
        timeout=10,
    )
    assert failure.returncode == 0, failure.stdout + failure.stderr
    failure_result = parse_last_json(failure.stdout)
    assert failure_result["ExitCode"] == 7
    assert failure_result["TimedOut"] is False
    assert failure_result["Observability"]["status"] == "ok"
    failure_events, _ = EventStore(failure_store).read()
    assert failure_events[-2]["kind"] == "codex.command.failed"
    assert failure_events[-1]["payload"]["exit_code"] == 7

    timeout_emitter = tmp_path / "emit_timeout.py"
    timeout_store = (tmp_path / "timeout" / "events.jsonl").resolve()
    timeout_harness = tmp_path / "timeout.ps1"
    write_emitter(timeout_emitter, delay=8.0, exit_code=0)
    write_harness(
        timeout_harness,
        emitter=timeout_emitter,
        store_path=timeout_store,
        timeout_seconds=1,
    )
    timeout = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(timeout_harness)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        errors="replace",
        timeout=12,
    )
    assert timeout.returncode == 0, timeout.stdout + timeout.stderr
    timeout_result = parse_last_json(timeout.stdout)
    assert timeout_result["ExitCode"] == 124
    assert timeout_result["TimedOut"] is True
    timeout_events, _ = EventStore(timeout_store).read()
    assert timeout_events[-1]["kind"] == "process.completed"
    assert timeout_events[-1]["payload"]["timed_out"] is True
    assert timeout_events[-1]["payload"]["exit_code"] == 124


def test_continuous_structured_output_cannot_starve_timeout_checks(tmp_path):
    emitter = tmp_path / "emit_continuously.py"
    store_path = (tmp_path / "continuous-timeout" / "events.jsonl").resolve()
    harness = tmp_path / "continuous_timeout.ps1"
    write_continuous_emitter(emitter, duration=4.0, interval=0.01)
    write_harness(
        harness,
        emitter=emitter,
        store_path=store_path,
        timeout_seconds=1,
    )

    started = time.monotonic()
    completed = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        errors="replace",
        timeout=10,
    )
    elapsed = time.monotonic() - started

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = parse_last_json(completed.stdout)
    assert elapsed < 3.5
    assert result["TimedOut"] is True
    assert result["ExitCode"] == 124
    assert result["StopAttempted"] is True
    events, diagnostics = EventStore(store_path).read()
    assert diagnostics == []
    assert events[-1]["kind"] == "process.completed"
    assert events[-1]["payload"]["timed_out"] is True
    assert events[-1]["payload"]["exit_code"] == 124
    assert any(event["kind"] == "codex.turn.started" for event in events[:-1])


def test_parent_exit_with_inherited_stdout_obeys_bounded_drain(tmp_path):
    parent = tmp_path / "parent.py"
    descendant = tmp_path / "descendant.py"
    store_path = (tmp_path / "inherited-stdout" / "events.jsonl").resolve()
    result_path = (tmp_path / "inherited-stdout" / "result.json").resolve()
    harness = tmp_path / "inherited_stdout.ps1"
    write_inherited_stdout_fixture(
        parent,
        descendant,
        descendant_duration=8.0,
        interval=0.01,
    )
    write_harness(
        harness,
        emitter=parent,
        store_path=store_path,
        timeout_seconds=20,
        result_path=result_path,
    )

    started = time.monotonic()
    completed = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        errors="replace",
        timeout=12,
    )
    elapsed = time.monotonic() - started

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert 4.5 <= elapsed < 7.5
    assert result["TimedOut"] is False
    assert result["ExitCode"] == 0
    assert result["StopAttempted"] is False
    events, diagnostics = EventStore(store_path).read()
    assert diagnostics == []
    turn_events = [event for event in events if event["kind"] == "codex.turn.started"]
    assert len(turn_events) >= 100
    assert events[-1]["kind"] == "process.completed"
    assert 4_500 <= events[-1]["payload"]["duration_ms"] < 7_500
    assert events[-1]["payload"]["timed_out"] is False
    assert events[-1]["payload"]["exit_code"] == 0


def test_runner_result_truth_does_not_depend_on_observability(tmp_path):
    harness = tmp_path / "truth_test.ps1"
    harness.write_text(
        runner_core()
        + "\n"
        + textwrap.dedent(
            """
            $binding = [pscustomobject]@{ contract_present = $true; status = "passed" }
            $assurance = [pscustomobject]@{ observable_evidence = "verified" }
            $result = Get-OverallRunnerResult `
                -CodexExitCode "0" `
                -RuntimeContractBinding $binding `
                -ExecutionAssurance $assurance
            Write-Output $result
            """
        ),
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        errors="replace",
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("success")


def test_reviewbundle_uses_json_events_and_restores_final_message_stdout():
    source = RUNNER.read_text(encoding="utf-8")
    launch = source.split("$codexUtf8 =", 1)[1].split(
        "$postExecutionObservation =", 1
    )[0]
    assert '"--json"' in launch
    assert '"--output-last-message"' in launch
    assert "-WorkflowObservation $workflowObservation" in launch
    assert "$codexResult.Stdout = $codexFinalMessage.TrimEnd()" in launch
    assert "$codexResult.LastStdoutLine = Get-LastNonEmptyLine" in launch
