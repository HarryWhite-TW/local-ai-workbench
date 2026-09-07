"""Localhost-only, read-only Workflow lifecycle and activity panel."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from local_runner_bridge.bridge_operator_b3 import (
    DEFAULT_REPOSITORY,
    FAILURE_PROTOCOL,
    read_processed_request_records,
)
from local_runner_bridge.bridge_operator_lifecycle_state import (
    DISPATCHED_NOT_LOCALLY_SETTLED,
    PREPARED,
    PROCESSED,
    REJECTED_BEFORE_RUNNER,
    LifecycleEvidenceError,
    load_in_flight,
    load_review_candidate,
    parse_utc,
)
from local_runner_bridge.workflow_observability import (
    EVENT_PROTOCOL,
    MAX_REPLAY_EVENTS,
    EventStore,
    ObservationError,
    ObservationHTTPServer,
    ObservationRequestHandler,
    validate_request_id,
)


PANEL_PROTOCOL = "lawb.workflow_panel.v1"
STATE_PROTOCOL = "lawb.bridge_operator_b3_state.v1"
HEARTBEAT_PROTOCOL = "lawb.bridge_operator_b3_heartbeat.v1"
MAX_STATE_FILE_BYTES = 1_048_576
MAX_PROCESSED_HISTORY_BYTES = 8_388_608

_ASSET_ROUTES = {
    "/": ("workflow_panel.html", "text/html; charset=utf-8"),
    "/workflow_panel.js": ("workflow_panel.js", "text/javascript; charset=utf-8"),
    "/workflow_panel.css": ("workflow_panel.css", "text/css; charset=utf-8"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _read_source(path: Path, *, protocol: str) -> tuple[str, dict[str, Any] | None]:
    if not path.exists():
        return "missing", None
    try:
        size = path.stat().st_size
        if size > MAX_STATE_FILE_BYTES:
            return "invalid", None
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return "invalid", None
    if not isinstance(value, dict) or value.get("protocol") != protocol:
        return "invalid", None
    return "available", value


def _safe_text(value: Any, *, limit: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    return value


def _safe_positive_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _safe_request_id(value: Any) -> str | None:
    try:
        return validate_request_id(value)
    except ObservationError:
        return None


def _valid_operator_source(value: dict[str, Any] | None, *, heartbeat: bool) -> bool:
    if value is None:
        return False
    counter_key = "cycle" if heartbeat else "cycles_completed"
    counter = value.get(counter_key)
    return (
        _safe_text(value.get("status")) is not None
        and _safe_text(value.get("mode")) is not None
        and parse_utc(value.get("updated_at_utc")) is not None
        and isinstance(counter, int)
        and not isinstance(counter, bool)
        and counter >= 0
    )


def _operator_state(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "status": _safe_text(value.get("status")),
        "mode": _safe_text(value.get("mode")),
        "repository": _safe_text(value.get("repo")),
        "cycles_completed": value.get("cycles_completed")
        if isinstance(value.get("cycles_completed"), int)
        and not isinstance(value.get("cycles_completed"), bool)
        and value["cycles_completed"] >= 0
        else None,
        "updated_at_utc": _safe_text(value.get("updated_at_utc")),
    }


def _heartbeat_state(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "status": _safe_text(value.get("status")),
        "mode": _safe_text(value.get("mode")),
        "cycle": value.get("cycle")
        if isinstance(value.get("cycle"), int)
        and not isinstance(value.get("cycle"), bool)
        and value["cycle"] >= 0
        else None,
        "updated_at_utc": _safe_text(value.get("updated_at_utc")),
    }


def _in_flight_lifecycle(in_flight: dict[str, Any]) -> dict[str, str]:
    stage = in_flight["stage"]
    terminal = in_flight.get("terminal_evidence")
    terminal_result = terminal.get("result") if isinstance(terminal, dict) else None
    if stage == REJECTED_BEFORE_RUNNER or terminal_result in {"failure", "blocked"}:
        visible_stage = "BLOCKED_OR_FAILED"
    elif stage == PROCESSED and terminal_result == "success":
        visible_stage = (
            "WAITING_FOR_CHATGPT_REVIEW"
            if in_flight.get("action") == "run-reviewbundle"
            else "COMPLETED_OR_LAST_COMPLETED"
        )
    else:
        visible_stage = "RUNNING"
    return {
        "stage": visible_stage,
        "certainty": "verified",
        "basis": f"in_flight:{stage}",
    }


def _read_processed_source(
    path: Path, *, repository: str
) -> tuple[str, dict[str, dict[str, Any]]]:
    if not path.exists():
        return "missing", {}
    try:
        if path.stat().st_size > MAX_PROCESSED_HISTORY_BYTES:
            return "invalid", {}
        return "available", read_processed_request_records(path, repository=repository)
    except (OSError, UnicodeError, ValueError):
        return "invalid", {}


def _record_time(record: dict[str, Any]) -> datetime | None:
    for key in ("terminal_observed_at_utc", "processed_at_utc"):
        parsed = parse_utc(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _latest_terminal_record(
    records: dict[str, dict[str, Any]], *, preferred_request_id: str | None
) -> dict[str, Any] | None:
    candidates = [
        record
        for record in records.values()
        if record.get("terminal_result") in {"success", "failure", "blocked"}
        and _record_time(record) is not None
    ]
    if preferred_request_id is not None:
        return next(
            (record for record in candidates if record["request_id"] == preferred_request_id),
            None,
        )
    return max(candidates, key=lambda record: _record_time(record) or datetime.min.replace(tzinfo=timezone.utc), default=None)


def _processed_lifecycle(record: dict[str, Any]) -> dict[str, str]:
    if record["terminal_result"] in {"failure", "blocked"}:
        stage = "BLOCKED_OR_FAILED"
    elif record.get("requested_action") == "run-reviewbundle":
        stage = "WAITING_FOR_CHATGPT_REVIEW"
    else:
        stage = "COMPLETED_OR_LAST_COMPLETED"
    return {
        "stage": stage,
        "certainty": "verified",
        "basis": f"processed_request:{record['terminal_result']}",
    }


def _valid_failure(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    reason = _safe_text(value.get("reason"))
    failed_at = _safe_text(value.get("failed_at_utc"))
    request_id_value = value.get("request_id")
    request_id = None if request_id_value is None else _safe_request_id(request_id_value)
    if (
        reason is None
        or failed_at is None
        or parse_utc(failed_at) is None
        or (request_id_value is not None and request_id is None)
        or value.get("current_failure_recorded") is not True
        or value.get("last_failure_json_applies_to_current_run") is not True
        or value.get("last_failure_json_status") != "current_failure"
    ):
        return None
    return {
        "request_id": request_id,
        "reason": reason,
        "failed_at_utc": failed_at,
    }


def _failure_is_current(
    failure: dict[str, Any],
    *,
    in_flight: dict[str, Any] | None,
    state: dict[str, Any] | None,
    heartbeat: dict[str, Any] | None,
    processed_records: dict[str, dict[str, Any]],
) -> bool:
    request_id = failure["request_id"]
    if in_flight is not None:
        return request_id == in_flight["request_id"]
    status_values = {
        _safe_text(source.get("status"))
        for source in (state, heartbeat)
        if source is not None
    }
    if "blocked" not in status_values:
        return False
    last_request_id = _safe_request_id(state.get("last_request_id")) if state else None
    if request_id is not None and request_id != last_request_id:
        return False
    processed = processed_records.get(request_id) if request_id is not None else None
    processed_at = _record_time(processed) if processed is not None else None
    failed_at = parse_utc(failure["failed_at_utc"])
    return processed_at is None or failed_at is None or processed_at < failed_at


def _review_candidate_matches(
    candidate: dict[str, Any] | None, record: dict[str, Any] | None
) -> bool:
    if candidate is None or record is None:
        return False
    return all(
        (
            candidate.get("target_repository") == (record.get("target_repository") or DEFAULT_REPOSITORY),
            candidate.get("target_issue") == record.get("target_issue"),
            candidate.get("dispatch_request_id") == record.get("target_dispatch_request_id"),
            candidate.get("action") == record.get("requested_action"),
            candidate.get("branch") == record.get("expected_branch"),
            candidate.get("expected_head") == record.get("expected_head"),
        )
    )


def _safe_comment_id(value: Any) -> str | None:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        return None
    return value if 1 <= len(value) <= 19 and not value.startswith("0") else None


def _warning_projection(
    failure: dict[str, Any] | None, request_events: list[dict[str, Any]]
) -> dict[str, Any]:
    if failure is not None:
        return {
            "status": "available",
            "code": failure["reason"],
            "source": "current_failure",
            "observed_at_utc": failure["failed_at_utc"],
        }
    for event in reversed(request_events):
        if event["kind"] not in {
            "observability.source_warning",
            "codex.turn.failed",
            "codex.command.failed",
            "codex.error",
        }:
            continue
        reason = _safe_text(event["payload"].get("reason"))
        return {
            "status": "available",
            "code": reason or event["kind"],
            "source": f"workflow_observation:{event['kind']}",
            "observed_at_utc": event["observed_at_utc"],
        }
    return {
        "status": "unavailable",
        "code": None,
        "source": None,
        "observed_at_utc": None,
    }


def _review_projection(
    record: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    warning: dict[str, Any],
) -> dict[str, Any]:
    evidence_pointer = None
    evidence_summary = None
    if _review_candidate_matches(candidate, record):
        comment_id = _safe_comment_id(candidate.get("review_bundle_comment_id"))
        if comment_id is not None:
            evidence_pointer = f"issue_comment:{comment_id}"
            evidence_summary = (
                "Trusted review bundle; candidate manifest "
                f"{candidate['candidate_manifest_fingerprint']}"
            )
    if evidence_pointer is None and record is not None:
        comment_id = _safe_comment_id(record.get("target_result_comment_id"))
        if comment_id is not None:
            evidence_pointer = f"issue_comment:{comment_id}"
            evidence_summary = "Trusted terminal result"
    return {
        "warning_or_error": warning,
        "changed_files": {"status": "unavailable", "items": []},
        "test_summary": {"status": "unavailable", "summary": None},
        "evidence": {
            "status": "available" if evidence_pointer else "unavailable",
            "pointer": evidence_pointer,
            "summary": evidence_summary,
        },
    }


def build_workflow_snapshot(state_dir: Path, store: EventStore) -> dict[str, Any]:
    """Build a bounded projection without treating missing evidence as completion."""

    diagnostics: list[str] = []
    state_status, state = _read_source(state_dir / "state.json", protocol=STATE_PROTOCOL)
    heartbeat_status, heartbeat = _read_source(
        state_dir / "heartbeat.json", protocol=HEARTBEAT_PROTOCOL
    )
    if state_status == "available" and not _valid_operator_source(state, heartbeat=False):
        state_status, state = "invalid", None
    if heartbeat_status == "available" and not _valid_operator_source(
        heartbeat, heartbeat=True
    ):
        heartbeat_status, heartbeat = "invalid", None
    for name, status in (("state", state_status), ("heartbeat", heartbeat_status)):
        if status == "invalid":
            diagnostics.append(f"{name}_evidence_invalid")

    repository = (
        _safe_text(state.get("repo")) if state is not None else None
    ) or DEFAULT_REPOSITORY
    processed_status, processed_records = _read_processed_source(
        state_dir / "processed_requests.jsonl",
        repository=repository,
    )
    if processed_status == "invalid":
        diagnostics.append("processed_request_evidence_invalid")

    failure_status, failure_value = _read_source(
        state_dir / "last_failure.json", protocol=FAILURE_PROTOCOL
    )
    failure = _valid_failure(failure_value)
    if failure_status == "available" and failure is None:
        failure_status = "invalid"
        diagnostics.append("last_failure_evidence_invalid")

    review_candidate_status = "missing"
    review_candidate: dict[str, Any] | None = None
    try:
        review_candidate = load_review_candidate(state_dir / "review_candidate.json")
        if review_candidate is not None:
            review_candidate_status = "available"
    except LifecycleEvidenceError:
        review_candidate_status = "invalid"
        diagnostics.append("review_candidate_evidence_invalid")

    in_flight_status = "missing"
    in_flight: dict[str, Any] | None = None
    try:
        in_flight = load_in_flight(state_dir / "in_flight.json")
        if in_flight is not None:
            in_flight_status = "available"
    except LifecycleEvidenceError:
        in_flight_status = "invalid"
        diagnostics.append("in_flight_evidence_invalid")

    events, event_diagnostics = store.read(limit=MAX_REPLAY_EVENTS)
    diagnostics.extend(f"observation_store:{item}" for item in event_diagnostics)

    preferred_request_id = _safe_request_id(state.get("last_request_id")) if state else None
    processed_record = _latest_terminal_record(
        processed_records,
        preferred_request_id=preferred_request_id,
    )

    request_id: str | None = None
    issue_number: int | None = None
    if in_flight is not None:
        request_id = in_flight["request_id"]
        issue_number = in_flight["target_issue"]
    elif processed_record is not None:
        request_id = processed_record["request_id"]
        issue_number = _safe_positive_integer(processed_record.get("target_issue"))

    applicable_failure = (
        failure
        if failure is not None
        and _failure_is_current(
            failure,
            in_flight=in_flight,
            state=state,
            heartbeat=heartbeat,
            processed_records=processed_records,
        )
        else None
    )
    if in_flight_status == "invalid":
        lifecycle = {
            "stage": "UNKNOWN",
            "certainty": "unknown",
            "basis": "in_flight_evidence_invalid",
        }
        updated_at_utc = None
        terminal_result = None
    elif applicable_failure is not None:
        lifecycle = {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "current_failure",
        }
        updated_at_utc = applicable_failure["failed_at_utc"]
        terminal_result = None
        request_id = applicable_failure["request_id"] or request_id
    elif in_flight is not None:
        lifecycle = _in_flight_lifecycle(in_flight)
        updated_at_utc = in_flight["updated_at_utc"]
        terminal = in_flight.get("terminal_evidence")
        terminal_result = terminal.get("result") if isinstance(terminal, dict) else None
    elif processed_record is not None:
        lifecycle = _processed_lifecycle(processed_record)
        updated_at_utc = _safe_text(processed_record.get("terminal_observed_at_utc"))
        terminal_result = processed_record["terminal_result"]
    elif "blocked" in {
        _safe_text(source.get("status"))
        for source in (state, heartbeat)
        if source is not None
    }:
        lifecycle = {
            "stage": "BLOCKED_OR_FAILED",
            "certainty": "verified",
            "basis": "operator_status:blocked",
        }
        updated_at_utc = _safe_text(
            (heartbeat or {}).get("updated_at_utc")
            or (state or {}).get("updated_at_utc")
        )
        terminal_result = None
    elif {"running", "polling"}.intersection(
        {
            _safe_text(source.get("status"))
            for source in (state, heartbeat)
            if source is not None
        }
    ):
        lifecycle = {
            "stage": "IDLE",
            "certainty": "verified",
            "basis": "operator_evidence:no_in_flight",
        }
        updated_at_utc = _safe_text(
            (heartbeat or {}).get("updated_at_utc")
            or (state or {}).get("updated_at_utc")
        )
        terminal_result = None
    else:
        lifecycle = {
            "stage": "UNKNOWN",
            "certainty": "unknown",
            "basis": "no_current_request_evidence",
        }
        updated_at_utc = None
        terminal_result = None

    if failure_status == "available" and applicable_failure is None:
        failure_status = "historical_not_current"
    candidate_matches = _review_candidate_matches(review_candidate, processed_record)
    if review_candidate_status == "available" and not candidate_matches:
        review_candidate_status = "historical_or_unmatched"

    request_events = [event for event in events if event["request_id"] == request_id]
    latest_event = request_events[-1] if request_events else None
    matching_events = (
        [event for event in request_events if event["run_id"] == latest_event["run_id"]]
        if latest_event is not None
        else []
    )
    warning = _warning_projection(applicable_failure, request_events)
    review = _review_projection(processed_record, review_candidate, warning)
    global_latest_event = events[-1] if events else None

    return {
        "protocol": PANEL_PROTOCOL,
        "mode": "read_only",
        "bind": "loopback",
        "observed_at_utc": utc_now(),
        "current_task": {
            "request_id": request_id,
            "issue_number": issue_number,
            "lifecycle": lifecycle,
            "updated_at_utc": updated_at_utc,
            "terminal_result": terminal_result,
        },
        "operator": {
            "state": _operator_state(state),
            "heartbeat": _heartbeat_state(heartbeat),
        },
        "observability": {
            "protocol": EVENT_PROTOCOL,
            "event_count": len(events),
            "request_event_count": len(matching_events),
            "latest_sequence": global_latest_event["sequence"] if global_latest_event else None,
            "run_id": latest_event["run_id"] if latest_event else None,
            "stream_url": f"/events?{urlencode({'follow': '1'})}",
        },
        "review": review,
        "source_status": {
            "state": state_status,
            "heartbeat": heartbeat_status,
            "in_flight": in_flight_status,
            "processed_requests": processed_status,
            "last_failure": failure_status,
            "review_candidate": review_candidate_status,
            "observation_store": "available" if store.path.exists() else "missing",
        },
        "diagnostics": list(dict.fromkeys(diagnostics)),
    }


class WorkflowPanelHTTPServer(ObservationHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        state_dir: Path,
        store: EventStore,
        asset_dir: Path,
        poll_interval: float = 0.1,
        heartbeat_interval: float = 10.0,
    ) -> None:
        self.state_dir = state_dir
        self.asset_dir = asset_dir
        super().__init__(
            server_address,
            store,
            poll_interval=poll_interval,
            heartbeat_interval=heartbeat_interval,
            handler_class=WorkflowPanelRequestHandler,
        )


class WorkflowPanelRequestHandler(ObservationRequestHandler):
    server_version = "LAWbWorkflowPanel/1"

    @property
    def panel_server(self) -> WorkflowPanelHTTPServer:
        return self.server  # type: ignore[return-value]

    def _write_panel_response(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        head_only: bool,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle_get(self, *, head_only: bool) -> None:
        path = urlsplit(self.path).path
        if path in {"/api/state", "/api/snapshot"}:
            snapshot = build_workflow_snapshot(
                self.panel_server.state_dir,
                self.panel_server.store,
            )
            body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            self._write_panel_response(
                200,
                body,
                "application/json; charset=utf-8",
                head_only=head_only,
            )
            return
        if path == "/health":
            body = json.dumps(
                {
                    "protocol": PANEL_PROTOCOL,
                    "status": "ready",
                    "mode": "read_only",
                    "bind": "loopback",
                    "observation_protocol": EVENT_PROTOCOL,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            self._write_panel_response(
                200,
                body,
                "application/json; charset=utf-8",
                head_only=head_only,
            )
            return
        asset = _ASSET_ROUTES.get(path)
        if asset is not None:
            filename, content_type = asset
            try:
                body = (self.panel_server.asset_dir / filename).read_bytes()
            except OSError:
                self._write_panel_response(
                    500,
                    b'{"error":"asset_unavailable"}',
                    "application/json; charset=utf-8",
                    head_only=head_only,
                )
                return
            self._write_panel_response(
                200,
                body,
                content_type,
                head_only=head_only,
            )
            return
        super()._handle_get(head_only=head_only)


def create_workflow_panel_server(
    state_dir: str | os.PathLike[str],
    store_path: str | os.PathLike[str],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    asset_dir: str | os.PathLike[str] | None = None,
    poll_interval: float = 0.1,
    heartbeat_interval: float = 10.0,
) -> WorkflowPanelHTTPServer:
    if host != "127.0.0.1":
        raise ObservationError("panel_host_must_be_ipv4_loopback")
    if isinstance(port, bool) or not 0 <= port <= 65_535:
        raise ObservationError("invalid_panel_port")
    state_root = Path(state_dir)
    event_path = Path(store_path)
    assets = Path(asset_dir) if asset_dir is not None else Path(__file__).resolve().parent
    if not state_root.is_absolute():
        raise ObservationError("panel_state_dir_must_be_absolute")
    if not event_path.is_absolute():
        raise ObservationError("event_store_path_must_be_absolute")
    if not assets.is_absolute():
        raise ObservationError("panel_asset_dir_must_be_absolute")
    missing_assets = [name for name, _ in _ASSET_ROUTES.values() if not (assets / name).is_file()]
    if missing_assets:
        raise ObservationError("panel_assets_missing")
    return WorkflowPanelHTTPServer(
        (host, port),
        state_dir=state_root,
        store=EventStore(event_path),
        asset_dir=assets,
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the read-only local Workflow Panel on IPv4 loopback."
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    server = create_workflow_panel_server(
        args.state_dir,
        args.store,
        host=args.host,
        port=args.port,
    )
    ready = {
        "protocol": PANEL_PROTOCOL,
        "status": "ready",
        "url": f"http://127.0.0.1:{server.server_address[1]}/",
        "mode": "read_only",
        "bind": "loopback",
    }
    print(json.dumps(ready, separators=(",", ":")), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
