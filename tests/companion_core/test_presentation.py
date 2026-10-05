from dataclasses import replace
import io
import os
import subprocess
import sys

import pytest

from src.companion_core import __main__ as cli
from src.companion_core.core import Companion
from src.companion_core.domain import Acceptance, Authority, Execution, Failure, Progress
from src.companion_core.presentation import HumanView, safe_text
from src.companion_core.runtime import EventKind, RuntimeEvent, RuntimeFailure


class Runtime:
    provider_id = "test-provider"

    def run(self, request):
        assert request.authority is Authority.READ_ONLY
        yield RuntimeEvent(EventKind.SESSION, session_id="session-1")
        for _ in range(1000):
            yield RuntimeEvent(EventKind.INSPECTING)
            yield RuntimeEvent(EventKind.RECEIVING)
        yield RuntimeEvent(EventKind.COMPLETED, text="專案驗收結果 → café — 只讀檢視")


def test_human_loop_coalesces_and_preserves_identity(tmp_path):
    output = []
    view = HumanView(output.append, details=True)
    core = Companion(Runtime(), "Inspect", str(tmp_path), Authority.READ_ONLY)
    task = core.run(view.progress)
    view.result(task)
    assert len(output) == 11  # Five phases, result, status, authority/id, three details.
    text = "\n".join(output)
    assert "專案驗收結果 → café — 只讀檢視" in text
    assert text.count("正在接收") == text.count("正在檢視") == 1
    assert "RESULT_PENDING_REVIEW" in text and "ACCEPTED" not in text
    assert "jsonrpc" not in text and "receiving_result" not in text
    for value in (task.id, task.provider, task.session_id, "READ_ONLY"):
        assert value in text
    assert task.acceptance == Acceptance.UNREVIEWED


def test_default_view_omits_internal_identity_details_and_unknown_events(tmp_path):
    output = []
    view = HumanView(output.append)
    view.progress(Progress("x", "raw provider body"))
    task = Companion(Runtime(), "Inspect", str(tmp_path), Authority.READ_ONLY).run(view.progress)
    view.result(task)
    text = "\n".join(output)
    assert "session-1" not in text and "test-provider" not in text
    assert "raw provider body" not in text and str(tmp_path) not in text


@pytest.mark.parametrize("reason", list(Failure))
def test_failure_projection_uses_only_bounded_reasons(tmp_path, reason):
    class Broken(Runtime):
        def run(self, request):
            raise RuntimeFailure(reason)
    output = []
    view = HumanView(output.append)
    task = Companion(Broken(), "Inspect", str(tmp_path), Authority.READ_ONLY).run(view.progress)
    view.result(task)
    assert task.state == "FAILED" and task.failure == reason
    assert output and "RESULT_PENDING_REVIEW" not in "\n".join(output)


def test_raw_exception_is_withheld_and_disconnect_is_not_cancellation(tmp_path):
    class Broken(Runtime):
        def run(self, request):
            raise RuntimeError('Set-Cookie: private-cookie; access_token=private-token; {"jsonrpc":"2.0"}')
    output = []
    view = HumanView(output.append)
    task = Companion(Broken(), "Inspect", str(tmp_path), Authority.READ_ONLY).run(view.progress)
    view.result(task)
    assert task.failure == Failure.UNKNOWN
    assert not any(word in "\n".join(output) for word in ("private", "jsonrpc", "Set-Cookie"))

    def disconnected(text):
        raise BrokenPipeError("private body")
    view = HumanView(disconnected)
    task = Companion(Runtime(), "Inspect", str(tmp_path), Authority.READ_ONLY).run(view.progress)
    view.result(task)
    assert not view.available and task.state == "RESULT_PENDING_REVIEW"
    assert task.result and task.acceptance == Acceptance.UNREVIEWED


@pytest.mark.parametrize("text,secret", [
    ("Cookie: session=secret-cookie\n folded-secret", "secret"),
    ("Set-Cookie: secret-cookie; Secure", "secret-cookie"),
    ('{"access_token": "secret-token"}', "secret-token"),
    ("Authorization: Bearer secret-auth", "secret-auth"),
    ("Bearer secret-bearer", "secret-bearer"),
    ("eyJabc.def.ghi", "eyJabc.def.ghi"),
    ("sk-test-secret", "sk-test-secret"),
    ("Coo\x1bkie: secret-cookie", "secret-cookie"),
    ('"access_token":\n"secret-token"', "secret-token"),
])
def test_display_redacts_credentials(text, secret):
    assert secret not in safe_text(text)


def test_result_controls_and_raw_protocol_are_not_presented(tmp_path):
    task = Companion(Runtime(), "Inspect", str(tmp_path), Authority.READ_ONLY).run()
    output = []
    view = HumanView(output.append)
    view.result(replace(task, result='{"jsonrpc":"2.0","params":{"private":"body"}}'))
    assert "jsonrpc" not in "\n".join(output) and "body" not in "\n".join(output)
    assert "\x1b" not in safe_text("\x1b[2J text\r\u202e")
    assert "\r" not in safe_text("a\rb") and "\u202e" not in safe_text("\u202e")


def test_cli_actual_entry_uses_human_output(tmp_path, monkeypatch, capsys):
    received = []
    def runtime(executable, model, credential):
        received.append((executable, model, credential()))
        return Runtime()
    monkeypatch.setattr(cli, "CodexRuntime", runtime)
    monkeypatch.setattr(sys, "stdin", io.StringIO("synthetic-host-token\n"))
    monkeypatch.setattr(sys, "argv", ["companion", "--codex", "test", "--model", "test",
        "--workspace", str(tmp_path), "--intent", "檢視專案", "--details"])
    assert cli.main() == 0
    output = capsys.readouterr()
    assert "RESULT_PENDING_REVIEW" in output.out and "專案驗收結果" in output.out
    assert "synthetic-host-token" not in output.out + output.err
    assert received == [("test", "test", "synthetic-host-token")]


def test_cli_bad_workspace_does_not_traceback_or_echo_input(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("synthetic\n"))
    monkeypatch.setattr(sys, "argv", ["companion", "--codex", "unused", "--model", "test",
        "--workspace", str(tmp_path / "missing-private-path"), "--intent", "private-intent"])
    assert cli.main() == 1
    output = capsys.readouterr()
    assert "private" not in output.out + output.err and "Traceback" not in output.err


def test_failure_and_cancelled_views_do_not_claim_pending_or_accepted(tmp_path):
    core = Companion(Runtime(), "Inspect", str(tmp_path), Authority.READ_ONLY)
    output = []
    view = HumanView(output.append)
    view.result(core.cancel())
    assert "已取消" in "\n".join(output)
    assert "RESULT_PENDING_REVIEW" not in "\n".join(output)
    assert "ACCEPTED" not in "\n".join(output)


def test_cli_pipe_is_utf8_even_with_legacy_stdout_encoding(tmp_path):
    process = subprocess.run([sys.executable, "-m", "src.companion_core",
        "--codex", "never-launched", "--model", "unused", "--workspace", str(tmp_path),
        "--intent", "Inspect"], input=b"\n", capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONDONTWRITEBYTECODE": "1"})
    assert process.returncode == 1
    text = process.stdout.decode("utf-8", errors="strict")
    assert "無法取得可用的 ChatGPT 授權" in text
    assert not process.stderr and "RESULT_PENDING_REVIEW" not in text
