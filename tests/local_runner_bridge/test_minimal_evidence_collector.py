from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.minimal_evidence_collector import (  # noqa: E402
    CollectorError,
    begin_session,
    default_safety,
    finalize_session,
    run_command,
)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def begin_docs_session(tmp_path: Path) -> Path:
    return begin_session(
        repo_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        profile="docs",
        label="unit-test",
    )


def test_begin_creates_session_json(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)

    session = read_json(session_path)
    assert session_path.name == "session.json"
    assert session["profile"] == "docs"
    assert session["label"] == "unit-test"
    assert session["commands"] == []


def test_run_captures_stdout_artifact(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)

    result = run_command(
        session_path=session_path,
        command_id="stdout",
        argv=[sys.executable, "-c", "print('hello evidence')"],
    )

    stdout_path = Path(str(result["stdout_path"]))
    assert stdout_path.read_text(encoding="utf-8").strip() == "hello evidence"
    assert result["stdout_bytes"] > 0


def test_run_captures_stderr_artifact(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)

    result = run_command(
        session_path=session_path,
        command_id="stderr",
        argv=[sys.executable, "-c", "import sys; print('careful', file=sys.stderr)"],
    )

    stderr_path = Path(str(result["stderr_path"]))
    assert stderr_path.read_text(encoding="utf-8").strip() == "careful"
    assert result["stderr_bytes"] > 0


def test_empty_stdout_stderr_still_create_files_and_hashes(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)

    result = run_command(
        session_path=session_path,
        command_id="empty",
        argv=[sys.executable, "-c", "pass"],
    )

    assert Path(str(result["stdout_path"])).is_file()
    assert Path(str(result["stderr_path"])).is_file()
    assert result["stdout_bytes"] == 0
    assert result["stderr_bytes"] == 0
    assert result["stdout_sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )
    assert result["stderr_sha256"] == result["stdout_sha256"]


def test_nonzero_command_records_command_failed(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)
    run_command(
        session_path=session_path,
        command_id="nonzero",
        argv=[sys.executable, "-c", "raise SystemExit(7)"],
    )

    review_path = finalize_session(session_path=session_path)
    review = read_json(review_path)
    assert review["result"] == "command_failed"
    assert review["failed_command_count"] == 1


def test_finalize_writes_review_packet_json(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)
    run_command(session_path=session_path, command_id="ok", argv=[sys.executable, "-c", "pass"])

    review_path = finalize_session(session_path=session_path)

    assert review_path.name == "review_packet.json"
    review = read_json(review_path)
    assert review["result"] == "success"
    assert review["command_count"] == 1


def test_unsupported_profile_fails_closed(tmp_path) -> None:
    try:
        begin_session(
            repo_root=tmp_path,
            evidence_root=tmp_path / "evidence",
            profile="live",
            label="bad",
        )
    except CollectorError as exc:
        assert str(exc) == "unsupported_profile"
    else:
        raise AssertionError("unsupported profile was accepted")


def test_forbidden_command_fails_closed_before_execution(tmp_path, monkeypatch) -> None:
    session_path = begin_docs_session(tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("forbidden command should not execute")

    monkeypatch.setattr(subprocess, "run", fail_run)

    try:
        run_command(session_path=session_path, command_id="bad", argv=["git", "push"])
    except CollectorError as exc:
        assert "forbidden_command" in str(exc)
        assert "push" in str(exc)
    else:
        raise AssertionError("forbidden command was accepted")

    assert read_json(session_path)["commands"] == []


def test_embedded_forbidden_push_word_fails_closed_before_execution(tmp_path, monkeypatch) -> None:
    session_path = begin_docs_session(tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("embedded forbidden command should not execute")

    monkeypatch.setattr(subprocess, "run", fail_run)

    try:
        run_command(
            session_path=session_path,
            command_id="bad-powershell",
            argv=["powershell", "-Command", "git push"],
        )
    except CollectorError as exc:
        assert "forbidden_command" in str(exc)
        assert "push" in str(exc)
    else:
        raise AssertionError("embedded forbidden push was accepted")

    assert read_json(session_path)["commands"] == []


def test_embedded_forbidden_gh_word_fails_closed_before_execution(tmp_path, monkeypatch) -> None:
    session_path = begin_docs_session(tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("embedded forbidden command should not execute")

    monkeypatch.setattr(subprocess, "run", fail_run)

    try:
        run_command(
            session_path=session_path,
            command_id="bad-pwsh",
            argv=["pwsh", "-Command", "gh repo view"],
        )
    except CollectorError as exc:
        assert "forbidden_command" in str(exc)
        assert "gh" in str(exc)
    else:
        raise AssertionError("embedded forbidden gh was accepted")

    assert read_json(session_path)["commands"] == []


def test_embedded_python_command_words_fail_closed_before_execution(tmp_path, monkeypatch) -> None:
    session_path = begin_docs_session(tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("embedded forbidden command should not execute")

    monkeypatch.setattr(subprocess, "run", fail_run)

    try:
        run_command(
            session_path=session_path,
            command_id="bad-python",
            argv=[
                sys.executable,
                "-c",
                "print('before'); import subprocess; subprocess.run(['git','push'])",
            ],
        )
    except CollectorError as exc:
        assert "forbidden_command" in str(exc)
        assert "push" in str(exc)
    else:
        raise AssertionError("embedded forbidden python command was accepted")

    assert read_json(session_path)["commands"] == []


def test_no_shell_true_behavior(tmp_path, monkeypatch) -> None:
    session_path = begin_docs_session(tmp_path)
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        captured.update(kwargs)
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_command(session_path=session_path, command_id="shell", argv=[sys.executable, "-c", "pass"])

    assert captured["shell"] is False


def test_safety_flags_remain_false(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)
    run_command(session_path=session_path, command_id="ok", argv=[sys.executable, "-c", "pass"])
    review = read_json(finalize_session(session_path=session_path))

    assert review["safety"] == default_safety()
    assert all(value is False for value in review["safety"].values())


def test_review_packet_has_no_semantic_approval_fields(tmp_path) -> None:
    session_path = begin_docs_session(tmp_path)
    run_command(session_path=session_path, command_id="ok", argv=[sys.executable, "-c", "pass"])

    review = read_json(finalize_session(session_path=session_path))

    assert "accepted" not in review
    assert "approved" not in review
    assert "done" not in review
