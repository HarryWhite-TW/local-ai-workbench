import http.client
import io
import json
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from local_runner_bridge.workflow_observability import (  # noqa: E402
    EVENT_SCHEMA,
    MAX_RECORD_BYTES,
    EventStore,
    ObservationError,
    RecordTooLarge,
    create_sse_server,
    ingest_stream,
    project_codex_line,
)


REQUEST_ID = "obs-request-001"
RUN_ID = "obs-run-001"


def projected(source: dict, observed_at: str = "2026-09-05T00:00:00Z") -> dict:
    return project_codex_line(
        json.dumps(source, ensure_ascii=False),
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        observed_at_utc=observed_at,
    )


def start_server(store_path: Path):
    server = create_sse_server(store_path, poll_interval=0.02, heartbeat_interval=0.1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_server(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def sse_data(body: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def test_projector_allowlists_facts_and_omits_sensitive_content():
    message = projected(
        {
            "type": "item.completed",
            "item": {
                "id": "msg-1",
                "type": "agent_message",
                "text": "secret=sk-proj-do-not-store hidden reasoning",
            },
        }
    )
    assert message["kind"] == "codex.message.completed"
    assert message["payload"] == {"item_id": "msg-1"}

    reasoning = projected(
        {
            "type": "item.completed",
            "item": {
                "id": "reason-1",
                "type": "reasoning",
                "text": "private chain of thought",
                "summary": ["do not retain"],
            },
        }
    )
    assert reasoning["kind"] == "observability.source_warning"
    assert reasoning["payload"] == {
        "reason": "sensitive_item_omitted",
        "source_event_type": "item.completed",
        "item_type": "reasoning",
    }

    command = projected(
        {
            "type": "item.completed",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "command": '"C:\\Tools\\pytest.exe" -q --password supersecret',
                "aggregated_output": "TOKEN=private-output",
                "exit_code": 7,
                "status": "completed",
            },
        }
    )
    assert command["kind"] == "codex.command.failed"
    assert command["payload"] == {
        "item_id": "cmd-1",
        "status": "completed",
        "command_name": "pytest.exe",
        "exit_code": 7,
    }
    persisted = json.dumps([message, reasoning, command], ensure_ascii=False)
    assert "sk-proj" not in persisted
    assert "chain of thought" not in persisted
    assert "supersecret" not in persisted
    assert "private-output" not in persisted


def test_projector_preserves_safe_unicode_file_facts_without_absolute_paths():
    event = projected(
        {
            "type": "item.completed",
            "item": {
                "id": "file-1",
                "type": "file_change",
                "status": "completed",
                "changes": [
                    {"path": "docs/測試文件.md"},
                    {"path": "C:\\Users\\private\\secret.txt"},
                    {"path": "../outside.txt"},
                ],
                "content": "must not persist",
            },
        }
    )
    assert event["kind"] == "codex.file.completed"
    assert event["payload"]["paths"] == ["docs/測試文件.md"]
    assert event["payload"]["observed_path_count"] == 3
    assert "content" not in json.dumps(event, ensure_ascii=False)


def test_unknown_malformed_and_oversized_source_events_become_bounded_warnings():
    unknown = projected(
        {
            "type": "future.event",
            "arbitrary": "secret value that must not be promoted",
        }
    )
    assert unknown["kind"] == "observability.source_warning"
    assert unknown["payload"] == {
        "reason": "unknown_source_event_type",
        "source_event_type": "future.event",
    }

    malformed = project_codex_line(
        b"{broken-json",
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        observed_at_utc="2026-09-05T00:00:01Z",
    )
    assert malformed["payload"]["reason"] == "malformed_json"

    oversized = project_codex_line(
        b"x" * 70_000,
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        observed_at_utc="2026-09-05T00:00:02Z",
    )
    assert oversized["payload"]["reason"] == "source_line_too_large"
    assert len(json.dumps(oversized).encode("utf-8")) < MAX_RECORD_BYTES


def test_store_sequence_replay_and_incomplete_tail_recovery(tmp_path):
    store_path = (tmp_path / "events.jsonl").resolve()
    store = EventStore(store_path)
    first = store.append(projected({"type": "thread.started", "thread_id": "thread-1"}))
    second = store.append(projected({"type": "turn.started"}))
    assert [first["sequence"], second["sequence"]] == [1, 2]

    historical = store_path.read_bytes()
    with store_path.open("ab") as handle:
        handle.write(b'{"incomplete":true')

    replay, diagnostics = store.read()
    assert [event["sequence"] for event in replay] == [1, 2]
    assert diagnostics == ["incomplete_tail_ignored"]

    recovered_store = EventStore(store_path)
    third = recovered_store.append(projected({"type": "turn.completed"}))
    assert third["sequence"] == 3
    assert store_path.read_bytes().startswith(historical)

    replay, diagnostics = recovered_store.read(after_sequence=1)
    assert [event["sequence"] for event in replay] == [2, 3]
    assert "malformed_json_record_ignored" in diagnostics


def test_store_enforces_record_and_filter_bounds(tmp_path):
    store = EventStore((tmp_path / "events.jsonl").resolve())
    event = projected({"type": "turn.started"})
    event["payload"] = {"bad": "x" * (MAX_RECORD_BYTES + 1)}
    with pytest.raises(RecordTooLarge):
        store.append(event)
    with pytest.raises(ObservationError):
        store.read(after_sequence=-1)
    with pytest.raises(ObservationError):
        store.read(limit=1_001)


def test_ingest_stream_orders_runner_codex_and_completion_events(tmp_path):
    store = EventStore((tmp_path / "events.jsonl").resolve())
    frames = b"".join(
        [
            b'codex\t{"type":"thread.started","thread_id":"thread-1"}\n',
            b"codex\t{malformed}\n",
            b'codex\t{"type":"item.completed","item":{"id":"r1","type":"reasoning","text":"private"}}\n',
            b'runner\t{"type":"process.completed","observed_at_utc":"2026-09-05T00:00:04Z","exit_code":0,"timed_out":false,"duration_ms":4000}\n',
        ]
    )
    summary = ingest_stream(
        io.BytesIO(frames),
        store=store,
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        process_id=123,
        started_at_utc="2026-09-05T00:00:00Z",
    )
    assert summary["status"] == "ok"
    assert summary["completion_observed"] is True
    assert summary["events_written"] == 5
    events, diagnostics = store.read()
    assert diagnostics == []
    assert [event["sequence"] for event in events] == [1, 2, 3, 4, 5]
    assert events[0]["kind"] == "execution.started"
    assert events[-1]["kind"] == "process.completed"
    assert events[-1]["payload"] == {
        "timed_out": False,
        "exit_code": 0,
        "duration_ms": 4000,
    }


def test_ingest_eof_without_completion_is_degraded_but_replayable(tmp_path):
    store = EventStore((tmp_path / "events.jsonl").resolve())
    summary = ingest_stream(
        io.BytesIO(b'codex\t{"type":"turn.started"}\n'),
        store=store,
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        process_id=456,
        started_at_utc="2026-09-05T00:00:00Z",
    )
    assert summary["status"] == "degraded"
    assert summary["reasons"] == ["process_completion_not_observed"]
    events, _ = store.read()
    assert events[-1]["kind"] == "observability.source_warning"
    assert events[-1]["payload"]["reason"] == "sink_eof_without_process_completion"


def test_sse_replay_reconnect_health_and_read_only_methods(tmp_path):
    store_path = (tmp_path / "events.jsonl").resolve()
    store = EventStore(store_path)
    for source in (
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {"type": "turn.completed"},
    ):
        store.append(projected(source))
    server, thread = start_server(store_path)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base}/events?after=1&follow=0", timeout=2) as response:
            events = sse_data(response.read().decode("utf-8"))
        assert [event["sequence"] for event in events] == [2, 3]

        request = Request(f"{base}/events?follow=0", headers={"Last-Event-ID": "2"})
        with urlopen(request, timeout=2) as response:
            resumed = sse_data(response.read().decode("utf-8"))
        assert [event["sequence"] for event in resumed] == [3]

        with urlopen(f"{base}/health", timeout=2) as response:
            health = json.loads(response.read())
        assert health == {
            "protocol": "lawb.workflow_observation_stream.v1",
            "mode": "read_only",
            "bind": "loopback",
            "writer_concurrency": "single",
            "reader_concurrency": "multiple",
        }

        with pytest.raises(HTTPError) as error:
            urlopen(Request(f"{base}/events", method="POST"), timeout=2)
        assert error.value.code == 405
    finally:
        stop_server(server, thread)


def test_sse_follow_delivers_one_append_to_multiple_clients(tmp_path):
    store_path = (tmp_path / "events.jsonl").resolve()
    store = EventStore(store_path)
    server, thread = start_server(store_path)
    port = server.server_address[1]
    ready = threading.Barrier(3)
    received: list[dict] = []
    failures: list[str] = []

    def reader() -> None:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request("GET", "/events?after=0&follow=1")
            response = connection.getresponse()
            if response.status != 200:
                failures.append(f"status={response.status}")
                return
            ready.wait(timeout=2)
            while True:
                line = response.readline().decode("utf-8")
                if line.startswith("data: "):
                    received.append(json.loads(line.removeprefix("data: ")))
                    return
        except Exception as exc:  # pragma: no cover - diagnostic only
            failures.append(type(exc).__name__)
        finally:
            connection.close()

    clients = [threading.Thread(target=reader) for _ in range(2)]
    for client in clients:
        client.start()
    try:
        ready.wait(timeout=2)
        store.append(projected({"type": "turn.started"}))
        for client in clients:
            client.join(timeout=3)
        assert failures == []
        assert len(received) == 2
        assert {event["sequence"] for event in received} == {1}
    finally:
        stop_server(server, thread)


def test_sse_rejects_non_loopback_binding(tmp_path):
    with pytest.raises(ObservationError, match="sse_host_must_be_ipv4_loopback"):
        create_sse_server((tmp_path / "events.jsonl").resolve(), host="0.0.0.0")

