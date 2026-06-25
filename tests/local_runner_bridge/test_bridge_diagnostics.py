import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.bridge_diagnostics as diagnostics

HEAD = "5f698e500774a469c29ff036fc234d5c9aa03048"


def completed(command, returncode=0, stdout=""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


class FakeCommands:
    def __init__(self, *, dirty=False, origin_known=True, origin_head=HEAD):
        self.dirty = dirty
        self.origin_known = origin_known
        self.origin_head = origin_head
        self.calls = []

    def __call__(self, command, cwd):
        self.calls.append(command)
        if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return completed(command, stdout="b4-b-readonly-bridge-diagnostics\n")
        if command[:2] == ["git", "rev-parse"] and command[-1] == "HEAD":
            return completed(command, stdout=f"{HEAD}\n")
        if command[:3] == ["git", "status", "--porcelain"]:
            return completed(command, stdout=" M file.txt\n" if self.dirty else "")
        if command[:3] == ["git", "rev-parse", "--verify"]:
            if not self.origin_known:
                return completed(command, returncode=1, stdout="")
            return completed(command, stdout=f"{self.origin_head}\n")
        if command[-1:] == ["--version"]:
            return completed(command, stdout=f"{Path(command[0]).name} version 1.0\n")
        return completed(command, returncode=1, stdout="")


def tool_which(name):
    return f"C:/tools/{name}.exe"


def none_which(name):
    return None


def run(
    tmp_path,
    *,
    dirty=False,
    origin_known=True,
    origin_head=HEAD,
    which=tool_which,
    command_runner=None,
):
    return diagnostics.run_bridge_diagnostics(
        repo_root=tmp_path / "repo",
        state_dir=tmp_path / "state",
        command_runner=command_runner
        or FakeCommands(dirty=dirty, origin_known=origin_known, origin_head=origin_head),
        which=which,
    )


def write_json(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def write_state_baseline(state_dir):
    state_dir.mkdir(parents=True)
    write_json(state_dir / "state.json", {"status": "max_cycles_completed"})
    write_json(
        state_dir / "heartbeat.json",
        {"status": "max_cycles_completed", "cycle": 2, "request_id": "req-2"},
    )


def test_clean_repo_and_clear_state_returns_ready(tmp_path):
    write_state_baseline(tmp_path / "state")

    summary = run(tmp_path)

    assert summary["status"] == "READY"
    assert summary["repository"]["working_tree_clean"] is True
    assert summary["repository"]["origin_master_known"] is True
    assert summary["repository"]["head_equals_origin_master"] is True
    assert summary["bridge_operator_state"]["lock_file_present"] is False
    assert summary["tools"]["gh_available"] is True
    assert summary["tools"]["codex_available"] is True
    assert summary["read_only"] is True
    assert summary["dispatcher_invoked"] is False
    assert summary["runner_invoked"] is False
    assert summary["codex_invoked"] is False
    assert summary["github_api_called"] is False


def test_diagnostics_are_read_only_and_do_not_modify_state_files_or_flags(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    paths = {
        "lock": state_dir / "operator.lock",
        "pause": state_dir / "pause.flag",
        "stop": state_dir / "stop.flag",
        "processed": state_dir / "processed_requests.jsonl",
        "observed": state_dir / "dry_run_observations.jsonl",
        "log": state_dir / "operator.log",
    }
    paths["lock"].write_text('{"pid": 1}\n', encoding="utf-8")
    paths["pause"].write_text("", encoding="utf-8")
    paths["stop"].write_text("", encoding="utf-8")
    paths["processed"].write_text('{"request_id": "p1"}\n', encoding="utf-8")
    paths["observed"].write_text('{"request_id": "o1"}\n', encoding="utf-8")
    paths["log"].write_text(
        '{"event": "started", "reason": "x", "request_id": "r1"}\n',
        encoding="utf-8",
    )
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in state_dir.iterdir()
    }

    summary = run(tmp_path)

    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in state_dir.iterdir()
    }
    assert before == after
    assert summary["status"] == "BLOCKED"
    assert summary["lock_created"] is False
    assert summary["lock_removed"] is False
    assert paths["lock"].exists()
    assert paths["pause"].exists()
    assert paths["stop"].exists()


def test_dirty_repo_returns_blocked(tmp_path):
    write_state_baseline(tmp_path / "state")

    summary = run(tmp_path, dirty=True)

    assert summary["status"] == "BLOCKED"
    assert "working_tree_dirty" in summary["status_reasons"]


def test_active_lock_returns_blocked(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    (state_dir / "operator.lock").write_text('{"pid": 1}\n', encoding="utf-8")

    summary = run(tmp_path)

    assert summary["status"] == "BLOCKED"
    assert "active_lock_present" in summary["status_reasons"]
    assert summary["bridge_operator_state"]["lock_file_present"] is True


def test_historical_last_failure_returns_attention_not_blocked(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    write_json(
        state_dir / "last_failure.json",
        {
            "protocol": "lawb.bridge_operator_b3_failure.v1",
            "reason": "dispatcher_timeout",
            "request_id": "old-request",
            "last_failure_json_status": "historical_not_current_run",
        },
    )

    summary = run(tmp_path)

    assert summary["status"] == "ATTENTION"
    assert summary["failure_clarity"]["last_failure_json_status"] == "historical_not_current_run"
    assert summary["failure_clarity"]["last_failure_reason"] == "dispatcher_timeout"
    assert summary["failure_clarity"]["last_failure_request_id"] == "old-request"


def test_current_failure_marker_with_later_processed_log_becomes_historical(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    write_json(
        state_dir / "last_failure.json",
        {
            "reason": "dispatcher_timeout",
            "request_id": "req-1",
            "last_failure_json_status": "current_failure",
            "last_failure_json_applies_to_current_run": True,
            "current_failure_recorded": True,
        },
    )
    (state_dir / "operator.log").write_text(
        '{"event": "failed", "reason": "dispatcher_timeout", "request_id": "req-1"}\n'
        '{"event": "processed", "reason": "verified", "request_id": "req-2"}\n',
        encoding="utf-8",
    )

    summary = run(tmp_path)

    assert summary["status"] == "ATTENTION"
    assert summary["failure_clarity"]["last_failure_json_status"] == "historical_not_current_run"
    assert "historical_last_failure_present" in summary["status_reasons"]


def test_matching_latest_failed_log_keeps_current_failure_and_attention(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    write_json(
        state_dir / "last_failure.json",
        {
            "reason": "dispatcher_timeout",
            "request_id": "req-1",
            "last_failure_json_status": "current_failure",
        },
    )
    (state_dir / "operator.log").write_text(
        '{"event": "failed", "reason": "dispatcher_timeout", "request_id": "req-1"}\n',
        encoding="utf-8",
    )

    summary = run(tmp_path)

    assert summary["status"] == "ATTENTION"
    assert summary["failure_clarity"]["last_failure_json_status"] == "current_failure"
    assert "current_last_failure_present" in summary["status_reasons"]


def test_invalid_last_failure_returns_blocked_and_invalid_json(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    (state_dir / "last_failure.json").write_text("{", encoding="utf-8")

    summary = run(tmp_path)

    assert summary["status"] == "BLOCKED"
    assert summary["failure_clarity"]["last_failure_json_status"] == "invalid_json"
    assert "last_failure_json_invalid_json" in summary["status_reasons"]


def test_processed_observation_counts_and_latest_log_are_read(tmp_path):
    state_dir = tmp_path / "state"
    write_state_baseline(state_dir)
    (state_dir / "processed_requests.jsonl").write_text(
        '{"request_id": "p1"}\n{"request_id": "p2"}\n',
        encoding="utf-8",
    )
    (state_dir / "dry_run_observations.jsonl").write_text(
        '{"request_id": "o1"}\n{"request_id": "o2"}\n{"request_id": "o3"}\n',
        encoding="utf-8",
    )
    (state_dir / "operator.log").write_text(
        '{"event": "started", "reason": "first", "request_id": "r1"}\n'
        '{"event": "processed", "reason": "verified", "request_id": "r2"}\n',
        encoding="utf-8",
    )

    summary = run(tmp_path)
    activity = summary["activity"]

    assert activity["processed_request_count"] == 2
    assert activity["observation_count"] == 3
    assert activity["latest_operator_log_event"] == "processed"
    assert activity["latest_operator_log_reason"] == "verified"
    assert activity["latest_operator_log_request_id"] == "r2"


def test_origin_master_unknown_returns_attention(tmp_path):
    write_state_baseline(tmp_path / "state")

    summary = run(tmp_path, origin_known=False)

    assert summary["status"] == "ATTENTION"
    assert summary["repository"]["origin_master_known"] is False
    assert "origin_master_unknown" in summary["status_reasons"]


def test_missing_tools_return_attention_with_reasons(tmp_path):
    write_state_baseline(tmp_path / "state")

    summary = run(tmp_path, which=none_which)

    assert summary["status"] == "ATTENTION"
    assert summary["tools"]["gh_available"] is False
    assert summary["tools"]["codex_available"] is False
    assert "gh_unavailable" in summary["status_reasons"]
    assert "codex_unavailable" in summary["status_reasons"]


def test_head_different_from_origin_master_returns_attention(tmp_path):
    write_state_baseline(tmp_path / "state")

    summary = run(tmp_path, origin_head="0" * 40)

    assert summary["status"] == "ATTENTION"
    assert summary["repository"]["head_equals_origin_master"] is False
    assert "head_differs_from_origin_master" in summary["status_reasons"]


def test_cmd_tool_version_uses_comspec_without_shell(monkeypatch, tmp_path):
    write_state_baseline(tmp_path / "state")
    commands = FakeCommands()
    monkeypatch.setenv("COMSPEC", "C:/Windows/System32/cmd.exe")

    summary = run(
        tmp_path,
        command_runner=commands,
        which=lambda name: f"C:/tools/{name}.cmd",
    )

    assert summary["tools"]["codex_available"] is True
    assert ["C:/Windows/System32/cmd.exe", "/d", "/c", "C:/tools/codex.cmd", "--version"] in commands.calls
    assert ["C:/Windows/System32/cmd.exe", "/d", "/c", "C:/tools/gh.cmd", "--version"] in commands.calls


def test_diagnostics_codex_resolver_prefers_cmd_over_ps1_and_extensionless(tmp_path):
    write_state_baseline(tmp_path / "state")
    commands = FakeCommands()
    candidates = {
        "gh": "C:/tools/gh.exe",
        "codex": "C:/tools/codex.ps1",
        "codex.cmd": "C:/tools/codex.cmd",
        "codex-no-extension": "C:/tools/codex",
    }

    summary = run(
        tmp_path,
        command_runner=commands,
        which=lambda name: candidates.get(name),
    )

    assert summary["tools"]["codex_available"] is True
    assert summary["tools"]["codex_path"] == "C:/tools/codex.cmd"
    assert all("codex.ps1" not in part for call in commands.calls for part in call)


def test_diagnostics_codex_resolver_rejects_ps1_only(tmp_path):
    write_state_baseline(tmp_path / "state")

    summary = run(
        tmp_path,
        which=lambda name: "C:/tools/codex.ps1" if name == "codex" else (
            "C:/tools/gh.exe" if name == "gh" else None
        ),
    )

    assert summary["tools"]["codex_available"] is False
    assert summary["tools"]["codex_path"] is None
    assert "codex_unavailable" in summary["status_reasons"]


def test_diagnostics_windows_rejects_extensionless_and_unsafe_shell_wrappers():
    assert (
        diagnostics._resolve_safe_application(
            "codex",
            lambda name: {
                "codex": "C:/tools/codex",
                "codex.sh": "C:/tools/codex.sh",
            }.get(name),
            platform="win32",
        )
        is None
    )


def test_diagnostics_non_windows_preserves_genuine_extensionless_executable():
    assert diagnostics._resolve_safe_application(
        "codex",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
        platform="linux",
    ) == "/usr/local/bin/codex"


def test_cli_returns_zero_and_prints_valid_json(monkeypatch, capsys):
    def fake_run(**kwargs):
        return {
            "protocol": diagnostics.DIAGNOSTIC_PROTOCOL,
            "status": "READY",
            "repository": {"repo_root": str(kwargs["repo_root"])},
        }

    monkeypatch.setattr(diagnostics, "run_bridge_diagnostics", fake_run)

    result = diagnostics.main(["--repo-root", "C:/repo", "--state-dir", "C:/state"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["protocol"] == diagnostics.DIAGNOSTIC_PROTOCOL
    assert payload["status"] == "READY"
