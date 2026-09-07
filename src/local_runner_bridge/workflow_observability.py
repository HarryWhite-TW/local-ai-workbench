"""Bounded, read-only observability for the local Workflow execution path.

This module deliberately records observed facts only.  It does not decide or
settle Workflow lifecycle state, and its HTTP surface exposes no write or
control operation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit


EVENT_SCHEMA = "lawb.workflow_observation.v1"
EVENT_PROTOCOL = "lawb.workflow_observation_stream.v1"
MAX_SOURCE_LINE_BYTES = 65_536
MAX_RECORD_BYTES = 8_192
MAX_PAYLOAD_BYTES = 4_096
MAX_REPLAY_EVENTS = 1_000
MAX_PATHS_PER_EVENT = 16

_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:-]{0,79}$")
_COMMAND_TOKEN_PATTERN = re.compile(r"^\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))")
_SAFE_STATUSES = {
    "in_progress",
    "completed",
    "failed",
    "declined",
    "cancelled",
    "unknown",
}


class ObservationError(ValueError):
    """Raised when a local observation contract is invalid."""


class RecordTooLarge(ObservationError):
    """Raised when a projected event exceeds the durable record boundary."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_identity(value: str, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ObservationError(f"invalid_{label}")
    return value


def validate_request_id(value: str) -> str:
    return _validate_identity(value, label="request_id", pattern=_IDENTITY_PATTERN)


def validate_run_id(value: str) -> str:
    return _validate_identity(value, label="run_id", pattern=_RUN_ID_PATTERN)


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(ord(character) < 32 for character in value):
        return None
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    clipped = encoded[:limit]
    while clipped:
        try:
            return clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return None


def _safe_name(value: Any) -> str | None:
    candidate = _bounded_text(value, 80)
    if candidate is None or not _SAFE_NAME_PATTERN.fullmatch(candidate):
        return None
    return candidate


def _safe_status(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value in _SAFE_STATUSES else "unknown"


def _safe_integer(value: Any, *, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if minimum <= value <= maximum:
        return value
    return None


def _command_name(command: Any) -> str | None:
    if not isinstance(command, str):
        return None
    match = _COMMAND_TOKEN_PATTERN.match(command)
    if match is None:
        return None
    token = next((group for group in match.groups() if group), "")
    token = token.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return _safe_name(token)


def _safe_relative_path(value: Any) -> str | None:
    candidate = _bounded_text(value, 320)
    if candidate is None:
        return None
    normalized = candidate.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return None
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return normalized


def _file_paths(item: dict[str, Any]) -> tuple[list[str], int]:
    values: list[Any] = []
    for key in ("path", "file_path"):
        if key in item:
            values.append(item[key])
    changes = item.get("changes")
    if isinstance(changes, list):
        for change in changes:
            if isinstance(change, dict):
                for key in ("path", "file_path"):
                    if key in change:
                        values.append(change[key])
            elif isinstance(change, str):
                values.append(change)
    paths: list[str] = []
    for value in values:
        path = _safe_relative_path(value)
        if path is not None and path not in paths and len(paths) < MAX_PATHS_PER_EVENT:
            paths.append(path)
    return paths, len(values)


def _event(
    *,
    request_id: str,
    run_id: str,
    observed_at_utc: str,
    source: str,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_request_id(request_id)
    validate_run_id(run_id)
    result: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "request_id": request_id,
        "run_id": run_id,
        "observed_at_utc": observed_at_utc,
        "source": source,
        "kind": kind,
        "payload": payload or {},
    }
    payload_bytes = json.dumps(
        result["payload"], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise RecordTooLarge("payload_too_large")
    return result


def _source_warning(
    *,
    request_id: str,
    run_id: str,
    observed_at_utc: str,
    reason: str,
    source_event_type: str | None = None,
    item_type: str | None = None,
    source_line_bytes: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason": reason}
    safe_event_type = _safe_name(source_event_type)
    safe_item_type = _safe_name(item_type)
    if safe_event_type is not None:
        payload["source_event_type"] = safe_event_type
    if safe_item_type is not None:
        payload["item_type"] = safe_item_type
    if source_line_bytes is not None:
        payload["source_line_bytes"] = min(max(source_line_bytes, 0), 2**31 - 1)
    return _event(
        request_id=request_id,
        run_id=run_id,
        observed_at_utc=observed_at_utc,
        source="codex_exec_jsonl",
        kind="observability.source_warning",
        payload=payload,
    )


def project_codex_line(
    line: str | bytes,
    *,
    request_id: str,
    run_id: str,
    observed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Project one Codex JSONL line into an allow-listed observed fact."""

    observed_at_utc = observed_at_utc or utc_now()
    if isinstance(line, bytes):
        source_bytes = line
        try:
            source_text = line.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _source_warning(
                request_id=request_id,
                run_id=run_id,
                observed_at_utc=observed_at_utc,
                reason="malformed_utf8",
                source_line_bytes=len(source_bytes),
            )
    elif isinstance(line, str):
        source_text = line
        source_bytes = line.encode("utf-8")
    else:
        raise ObservationError("source_line_must_be_text_or_bytes")

    if len(source_bytes) > MAX_SOURCE_LINE_BYTES:
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="source_line_too_large",
            source_line_bytes=len(source_bytes),
        )
    try:
        source = json.loads(source_text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="malformed_json",
            source_line_bytes=len(source_bytes),
        )
    if not isinstance(source, dict):
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="source_event_not_object",
            source_line_bytes=len(source_bytes),
        )

    source_type = source.get("type")
    if not isinstance(source_type, str):
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="source_event_type_missing",
        )

    if source_type == "thread.started":
        payload: dict[str, Any] = {}
        thread_id = _bounded_text(source.get("thread_id"), 128)
        if thread_id is not None:
            payload["thread_id"] = thread_id
        return _event(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            source="codex_exec_jsonl",
            kind="codex.thread.started",
            payload=payload,
        )

    turn_kinds = {
        "turn.started": "codex.turn.started",
        "turn.completed": "codex.turn.completed",
        "turn.failed": "codex.turn.failed",
        "error": "codex.error",
    }
    if source_type in turn_kinds:
        return _event(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            source="codex_exec_jsonl",
            kind=turn_kinds[source_type],
        )

    if source_type not in {"item.started", "item.updated", "item.completed"}:
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="unknown_source_event_type",
            source_event_type=source_type,
        )

    item = source.get("item")
    if not isinstance(item, dict):
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="item_missing",
            source_event_type=source_type,
        )
    item_type = item.get("type")
    if not isinstance(item_type, str):
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="item_type_missing",
            source_event_type=source_type,
        )
    phase = source_type.rsplit(".", 1)[-1]
    payload = {}
    item_id = _bounded_text(item.get("id"), 128)
    item_status = _safe_status(item.get("status"))
    if item_id is not None:
        payload["item_id"] = item_id
    if item_status is not None:
        payload["status"] = item_status

    if item_type == "reasoning":
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="sensitive_item_omitted",
            source_event_type=source_type,
            item_type=item_type,
        )

    if item_type == "command_execution":
        command_name = _command_name(item.get("command"))
        exit_code = _safe_integer(item.get("exit_code"), minimum=-(2**31), maximum=2**31 - 1)
        if command_name is not None:
            payload["command_name"] = command_name
        if exit_code is not None:
            payload["exit_code"] = exit_code
        kind = f"codex.command.{phase}"
        if phase == "completed" and exit_code not in (None, 0):
            kind = "codex.command.failed"
        return _event(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            source="codex_exec_jsonl",
            kind=kind,
            payload=payload,
        )

    if item_type == "file_change":
        paths, observed_path_count = _file_paths(item)
        if paths:
            payload["paths"] = paths
        if observed_path_count:
            payload["observed_path_count"] = min(observed_path_count, 2**31 - 1)
        return _event(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            source="codex_exec_jsonl",
            kind=f"codex.file.{phase}",
            payload=payload,
        )

    item_kind_map = {
        "agent_message": "message",
        "mcp_tool_call": "tool",
        "web_search": "tool",
        "plan_update": "plan",
    }
    projected_kind = item_kind_map.get(item_type)
    if projected_kind is None:
        return _source_warning(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            reason="unknown_item_type",
            source_event_type=source_type,
            item_type=item_type,
        )
    if item_type in {"mcp_tool_call", "web_search"}:
        payload["tool_kind"] = "mcp" if item_type == "mcp_tool_call" else "web_search"
    return _event(
        request_id=request_id,
        run_id=run_id,
        observed_at_utc=observed_at_utc,
        source="codex_exec_jsonl",
        kind=f"codex.{projected_kind}.{phase}",
        payload=payload,
    )


def project_runner_control(
    control: dict[str, Any],
    *,
    request_id: str,
    run_id: str,
) -> dict[str, Any]:
    if not isinstance(control, dict):
        raise ObservationError("runner_control_not_object")
    control_type = control.get("type")
    observed_at_utc = _bounded_text(control.get("observed_at_utc"), 64) or utc_now()
    if control_type == "process.completed":
        exit_code = _safe_integer(control.get("exit_code"), minimum=-(2**31), maximum=2**31 - 1)
        timed_out = control.get("timed_out")
        duration_ms = _safe_integer(control.get("duration_ms"), minimum=0, maximum=2**31 - 1)
        payload: dict[str, Any] = {
            "timed_out": timed_out if isinstance(timed_out, bool) else False,
        }
        if exit_code is not None:
            payload["exit_code"] = exit_code
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return _event(
            request_id=request_id,
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            source="runner",
            kind="process.completed",
            payload=payload,
        )
    raise ObservationError("unknown_runner_control_type")


def execution_started_event(
    *,
    request_id: str,
    run_id: str,
    process_id: int,
    observed_at_utc: str,
) -> dict[str, Any]:
    safe_process_id = _safe_integer(process_id, minimum=1, maximum=2**31 - 1)
    payload: dict[str, Any] = {"interface": "codex_exec_jsonl"}
    if safe_process_id is not None:
        payload["process_id"] = safe_process_id
    return _event(
        request_id=request_id,
        run_id=run_id,
        observed_at_utc=observed_at_utc,
        source="runner",
        kind="execution.started",
        payload=payload,
    )


def _serialized_record(record: dict[str, Any]) -> bytes:
    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RECORD_BYTES:
        raise RecordTooLarge("record_too_large")
    return encoded + b"\n"


def _valid_record(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("schema") != EVENT_SCHEMA:
        return False
    sequence = value.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        return False
    try:
        validate_request_id(value.get("request_id"))
        validate_run_id(value.get("run_id"))
    except ObservationError:
        return False
    return (
        isinstance(value.get("observed_at_utc"), str)
        and isinstance(value.get("source"), str)
        and isinstance(value.get("kind"), str)
        and isinstance(value.get("payload"), dict)
    )


def _iter_bounded_lines(path: Path) -> Iterable[tuple[bytes, bool, bool]]:
    """Yield (line, complete, oversized) without unbounded line allocation."""

    with path.open("rb") as handle:
        while True:
            chunk = handle.readline(MAX_RECORD_BYTES + 2)
            if not chunk:
                return
            if chunk.endswith(b"\n"):
                yield chunk[:-1], True, len(chunk) - 1 > MAX_RECORD_BYTES
                continue
            if len(chunk) <= MAX_RECORD_BYTES + 1:
                yield chunk, False, False
                return
            while chunk and not chunk.endswith(b"\n"):
                chunk = handle.readline(MAX_RECORD_BYTES + 2)
            yield b"", True, True


class EventStore:
    """Single-writer append-only JSONL store with multi-reader replay."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ObservationError("event_store_path_must_be_absolute")
        self._lock = threading.Lock()
        self._next_sequence = self._discover_next_sequence()

    def _discover_next_sequence(self) -> int:
        maximum = 0
        if not self.path.exists():
            return 1
        for line, complete, oversized in _iter_bounded_lines(self.path):
            if not complete or oversized:
                continue
            try:
                record = json.loads(line.decode("utf-8", errors="strict"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if _valid_record(record):
                maximum = max(maximum, int(record["sequence"]))
        return maximum + 1

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        if "sequence" in event:
            raise ObservationError("sequence_is_store_owned")
        with self._lock:
            record = dict(event)
            record["sequence"] = self._next_sequence
            encoded = _serialized_record(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab+") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                if size:
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) != b"\n":
                        handle.seek(0, os.SEEK_END)
                        handle.write(b"\n")
                handle.seek(0, os.SEEK_END)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            self._next_sequence += 1
            return record

    def read(
        self,
        *,
        after_sequence: int = 0,
        request_id: str | None = None,
        run_id: str | None = None,
        limit: int = MAX_REPLAY_EVENTS,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if isinstance(after_sequence, bool) or after_sequence < 0:
            raise ObservationError("invalid_after_sequence")
        if request_id is not None:
            validate_request_id(request_id)
        if run_id is not None:
            validate_run_id(run_id)
        if isinstance(limit, bool) or not 1 <= limit <= MAX_REPLAY_EVENTS:
            raise ObservationError("invalid_replay_limit")
        if not self.path.exists():
            return [], []

        events: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        last_sequence = 0
        for line, complete, oversized in _iter_bounded_lines(self.path):
            if not complete:
                diagnostics.append("incomplete_tail_ignored")
                continue
            if oversized:
                diagnostics.append("oversized_record_ignored")
                continue
            try:
                record = json.loads(line.decode("utf-8", errors="strict"))
            except UnicodeDecodeError:
                diagnostics.append("malformed_utf8_record_ignored")
                continue
            except json.JSONDecodeError:
                diagnostics.append("malformed_json_record_ignored")
                continue
            if not _valid_record(record):
                diagnostics.append("invalid_record_ignored")
                continue
            sequence = int(record["sequence"])
            if sequence <= last_sequence:
                diagnostics.append("non_monotonic_record_ignored")
                continue
            last_sequence = sequence
            if sequence <= after_sequence:
                continue
            if request_id is not None and record["request_id"] != request_id:
                continue
            if run_id is not None and record["run_id"] != run_id:
                continue
            events.append(record)
            if len(events) >= limit:
                break
        return events, list(dict.fromkeys(diagnostics))


class ObservationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        store: EventStore,
        *,
        poll_interval: float = 0.1,
        heartbeat_interval: float = 10.0,
        handler_class: type[BaseHTTPRequestHandler] | None = None,
    ) -> None:
        self.store = store
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.stop_event = threading.Event()
        super().__init__(
            server_address,
            handler_class or ObservationRequestHandler,
        )

    def shutdown(self) -> None:
        self.stop_event.set()
        super().shutdown()


class ObservationRequestHandler(BaseHTTPRequestHandler):
    server_version = "LAWbWorkflowObservation/1"
    protocol_version = "HTTP/1.1"

    @property
    def observation_server(self) -> ObservationHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle_get(head_only=True)

    def do_GET(self) -> None:  # noqa: N802
        self._handle_get(head_only=False)

    def _handle_get(self, *, head_only: bool) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self._write_json(
                200,
                {
                    "protocol": EVENT_PROTOCOL,
                    "mode": "read_only",
                    "bind": "loopback",
                    "writer_concurrency": "single",
                    "reader_concurrency": "multiple",
                },
            )
            return
        if parsed.path != "/events":
            self._write_json(404, {"error": "not_found"})
            return
        if head_only:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False)
            after_text = query.get("after", [self.headers.get("Last-Event-ID", "0")])[0]
            after = int(after_text)
            if after < 0:
                raise ValueError
            follow = query.get("follow", ["1"])[0]
            if follow not in {"0", "1"}:
                raise ValueError
            request_id = query.get("request_id", [None])[0]
            run_id = query.get("run_id", [None])[0]
            if request_id is not None:
                validate_request_id(request_id)
            if run_id is not None:
                validate_run_id(run_id)
        except (ValueError, ObservationError):
            self._write_json(400, {"error": "invalid_cursor_or_filter"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive" if follow == "1" else "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        if follow == "0":
            self.close_connection = True
        cursor = after
        last_write = time.monotonic()
        try:
            while not self.observation_server.stop_event.is_set():
                events, _diagnostics = self.observation_server.store.read(
                    after_sequence=cursor,
                    request_id=request_id,
                    run_id=run_id,
                )
                for event in events:
                    sequence = int(event["sequence"])
                    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    frame = (
                        f"id: {sequence}\n"
                        "event: workflow-observation\n"
                        f"data: {data}\n\n"
                    ).encode("utf-8")
                    self.wfile.write(frame)
                    self.wfile.flush()
                    cursor = sequence
                    last_write = time.monotonic()
                if follow == "0":
                    return
                if time.monotonic() - last_write >= self.observation_server.heartbeat_interval:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_write = time.monotonic()
                self.observation_server.stop_event.wait(self.observation_server.poll_interval)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            return


def create_sse_server(
    store_path: str | os.PathLike[str],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    poll_interval: float = 0.1,
    heartbeat_interval: float = 10.0,
) -> ObservationHTTPServer:
    if host != "127.0.0.1":
        raise ObservationError("sse_host_must_be_ipv4_loopback")
    if isinstance(port, bool) or not 0 <= port <= 65_535:
        raise ObservationError("invalid_sse_port")
    return ObservationHTTPServer(
        (host, port),
        EventStore(store_path),
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
    )


def _append_best_effort(
    store: EventStore,
    event: dict[str, Any],
    *,
    summary: dict[str, Any],
) -> None:
    try:
        record = store.append(event)
        summary["events_written"] += 1
        summary["last_sequence"] = record["sequence"]
    except (OSError, ObservationError) as exc:
        summary["status"] = "degraded"
        reason = type(exc).__name__
        if reason not in summary["reasons"]:
            summary["reasons"].append(reason)


def ingest_stream(
    stream: Any,
    *,
    store: EventStore,
    request_id: str,
    run_id: str,
    process_id: int,
    started_at_utc: str,
) -> dict[str, Any]:
    validate_request_id(request_id)
    validate_run_id(run_id)
    summary: dict[str, Any] = {
        "protocol": EVENT_PROTOCOL,
        "status": "ok",
        "request_id": request_id,
        "run_id": run_id,
        "events_written": 0,
        "last_sequence": None,
        "completion_observed": False,
        "reasons": [],
    }
    _append_best_effort(
        store,
        execution_started_event(
            request_id=request_id,
            run_id=run_id,
            process_id=process_id,
            observed_at_utc=started_at_utc,
        ),
        summary=summary,
    )

    while True:
        raw = stream.readline(MAX_SOURCE_LINE_BYTES + 2)
        if not raw:
            break
        oversized = len(raw) > MAX_SOURCE_LINE_BYTES and not raw.endswith(b"\n")
        if oversized:
            while raw and not raw.endswith(b"\n"):
                raw = stream.readline(MAX_SOURCE_LINE_BYTES + 2)
            event = _source_warning(
                request_id=request_id,
                run_id=run_id,
                observed_at_utc=utc_now(),
                reason="source_line_too_large",
                source_line_bytes=MAX_SOURCE_LINE_BYTES + 1,
            )
            _append_best_effort(store, event, summary=summary)
            continue
        raw = raw.rstrip(b"\r\n")
        try:
            prefix, payload = raw.split(b"\t", 1)
        except ValueError:
            event = _source_warning(
                request_id=request_id,
                run_id=run_id,
                observed_at_utc=utc_now(),
                reason="ingest_frame_malformed",
                source_line_bytes=len(raw),
            )
            _append_best_effort(store, event, summary=summary)
            continue
        if prefix == b"codex":
            event = project_codex_line(
                payload,
                request_id=request_id,
                run_id=run_id,
                observed_at_utc=utc_now(),
            )
        elif prefix == b"runner":
            try:
                control = json.loads(payload.decode("utf-8", errors="strict"))
                event = project_runner_control(
                    control,
                    request_id=request_id,
                    run_id=run_id,
                )
                if event["kind"] == "process.completed":
                    summary["completion_observed"] = True
            except (UnicodeDecodeError, json.JSONDecodeError, ObservationError):
                event = _source_warning(
                    request_id=request_id,
                    run_id=run_id,
                    observed_at_utc=utc_now(),
                    reason="runner_control_malformed",
                    source_line_bytes=len(payload),
                )
        else:
            event = _source_warning(
                request_id=request_id,
                run_id=run_id,
                observed_at_utc=utc_now(),
                reason="ingest_frame_unknown",
                source_line_bytes=len(raw),
            )
        _append_best_effort(store, event, summary=summary)

    if not summary["completion_observed"]:
        _append_best_effort(
            store,
            _event(
                request_id=request_id,
                run_id=run_id,
                observed_at_utc=utc_now(),
                source="observer",
                kind="observability.source_warning",
                payload={"reason": "sink_eof_without_process_completion"},
            ),
            summary=summary,
        )
        summary["status"] = "degraded"
        summary["reasons"].append("process_completion_not_observed")
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append and stream bounded local Workflow observation events."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="Ingest runner-framed Codex JSONL from stdin.")
    ingest.add_argument("--store", required=True)
    ingest.add_argument("--request-id", required=True)
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--process-id", required=True, type=int)
    ingest.add_argument("--started-at-utc", required=True)
    serve = subparsers.add_parser("serve", help="Serve read-only replay/follow SSE on loopback.")
    serve.add_argument("--store", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "ingest":
        store = EventStore(args.store)
        summary = ingest_stream(
            sys.stdin.buffer,
            store=store,
            request_id=args.request_id,
            run_id=args.run_id,
            process_id=args.process_id,
            started_at_utc=args.started_at_utc,
        )
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        return 0
    server = create_sse_server(args.store, host=args.host, port=args.port)
    ready = {
        "protocol": EVENT_PROTOCOL,
        "status": "ready",
        "host": server.server_address[0],
        "port": server.server_address[1],
        "mode": "read_only",
    }
    sys.stdout.write(json.dumps(ready, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
