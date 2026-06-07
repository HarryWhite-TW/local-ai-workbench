import json
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import local_runner_bridge.result_surface_cli as cli
from local_runner_bridge.result_surface import REQUIRED_SAFETY_FLAGS


def read_stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_sample_prints_valid_json(capsys):
    result = cli.main(["--sample"])
    surface = read_stdout_json(capsys)

    assert result == 0
    assert surface["result_surface_version"] == "lawb.local_result_surface.v0.draft"
    assert surface["result_id"] == "result-160-local-stdout-smoke"
    assert surface["status"] == "success"


def test_cli_output_contains_no_secrets_or_token_values(monkeypatch, capsys):
    monkeypatch.setenv("RESULT_SURFACE_TEST_TOKEN", "ghp_TEST_SECRET_DO_NOT_LEAK")

    result = cli.main(["--sample"])
    output = capsys.readouterr().out

    assert result == 0
    assert "ghp_TEST_SECRET_DO_NOT_LEAK" not in output
    assert "RESULT_SURFACE_TEST_TOKEN" not in output


def test_cli_does_not_write_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    result = cli.main(["--sample"])
    surface = read_stdout_json(capsys)

    assert result == 0
    assert surface["safety_flags"]["github_write_performed"] is False
    assert list(tmp_path.iterdir()) == []


def test_cli_sample_does_not_call_github(monkeypatch, capsys):
    def fail_if_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", fail_if_network)

    result = cli.main(["--sample"])
    surface = read_stdout_json(capsys)

    assert result == 0
    assert surface["safety_flags"]["github_write_performed"] is False


def test_cli_sample_does_not_execute_tasks(monkeypatch, capsys):
    def fail_if_subprocess(*args, **kwargs):
        raise AssertionError("task execution attempted")

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess)

    result = cli.main(["--sample"])
    surface = read_stdout_json(capsys)

    assert result == 0
    assert surface["safety_flags"]["codex_side_action_executed"] is False
    assert surface["safety_flags"]["runner_invoked"] is False
    assert surface["safety_flags"]["dispatcher_invoked"] is False
    assert surface["safety_flags"]["watcher_invoked"] is False


def test_cli_sample_has_required_safety_flags_false(capsys):
    result = cli.main(["--sample"])
    surface = read_stdout_json(capsys)

    assert result == 0
    assert set(surface["safety_flags"]) == set(REQUIRED_SAFETY_FLAGS)
    assert all(value is False for value in surface["safety_flags"].values())
    assert surface["requires_user_approval"] is True

